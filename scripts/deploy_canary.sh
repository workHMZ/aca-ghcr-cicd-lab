#!/bin/bash
set -euo pipefail

RG="${1:-}"
APP="${2:-}"

if [ -z "$RG" ] || [ -z "$APP" ]; then
  echo "Usage: $0 <resource-group> <container-app-name>"
  exit 1
fi

# --- 工具函数 ---

# 重试，最多 5 次，间隔 10s
run_with_retry() {
  local n=1
  local max=5
  local delay=10
  while true; do
    "$@" && break || {
      if [[ $n -lt $max ]]; then
        ((n++))
        echo "  重试 $n/$max..."
        sleep $delay
      else
        echo "  $max 次都失败了"
        return 1
      fi
    }
  done
}

# 健康检查
check_health() {
  local url="$1"
  local timeout="${2:-10}"
  local attempts="${3:-24}"
  echo "health check: $url"
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time "$timeout" "$url" >/dev/null 2>&1; then
      echo "  OK"
      return 0
    fi
    echo "  等待中 ($i/$attempts)..."
    sleep 10
  done
  echo "  超时，health check 失败"
  return 1
}

# 预热（加载 embedding 模型）
warmup_model() {
  local url="$1"
  local timeout="${2:-300}"
  local attempts="${3:-2}"
  echo "warmup: $url"
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time "$timeout" "$url" >/dev/null 2>&1; then
      echo "  warmup 完成"
      return 0
    fi
    echo "  warmup 失败，重试 ($i/$attempts)..."
    sleep 10
  done
  echo "  warmup 最终失败"
  return 1
}

# 检查流量是否切到位
verify_traffic() {
  local rev="$1"
  local expected="${2:-100}"
  local attempts="${3:-6}"
  for i in $(seq 1 "$attempts"); do
    CURRENT_WEIGHT=$(az containerapp ingress traffic show -g "$RG" -n "$APP" \
      --query "sum([?revisionName=='$rev'].weight)" -o tsv 2>/dev/null || echo "0")
    if [ "$CURRENT_WEIGHT" = "$expected" ]; then
      return 0
    fi
    echo "  流量确认中 ($i/$attempts): 当前=$CURRENT_WEIGHT 期望=$expected"
    sleep 5
  done
  return 1
}

# 回滚：关掉 set -e 保证跑完
rollback() {
  echo "开始回滚..."
  set +e

  if [ -z "${STABLE_REV:-}" ] || [ "$STABLE_REV" = "None" ]; then
    echo "没有 stable revision，无法回滚"
    exit 1
  fi

  echo "流量全切回 $STABLE_REV..."
  run_with_retry az containerapp ingress traffic set \
    -g "$RG" -n "$APP" \
    --revision-weight "$STABLE_REV=100"

  if [ $? -ne 0 ]; then
    echo "回滚失败！需要手动处理"
    exit 1
  fi

  echo "确认流量..."
  if ! verify_traffic "$STABLE_REV" 100 8; then
    echo "流量确认失败"
    exit 1
  fi
  echo "流量已切回 stable"

  # 停掉有问题的 revision（失败也无所谓）
  echo "停用 $NEW_REV..."
  az containerapp revision deactivate -g "$RG" -n "$APP" --revision "$NEW_REV" 2>/dev/null || true

  echo "回滚完成"
  exit 1
}

# --- 主流程 ---

echo "查询 FQDN..."
FQDN=$(az containerapp show -g "$RG" -n "$APP" --query "properties.configuration.ingress.fqdn" -o tsv)
if [ -z "$FQDN" ] || [ "$FQDN" = "None" ]; then
  echo "拿不到 FQDN，检查 External Ingress 是否开启"
  exit 1
fi

# 最新的 revision = 刚部署的
NEW_REV=$(az containerapp revision list -g "$RG" -n "$APP" \
  --query "sort_by([].{name:name, created:properties.createdTime}, &created)[-1].name" -o tsv)

if [ -z "$NEW_REV" ] || [ "$NEW_REV" = "None" ]; then
  echo "找不到新 revision"
  exit 1
fi

# 当前流量最大的 = stable
STABLE_REV=$(az containerapp revision list -g "$RG" -n "$APP" \
  --query "sort_by([?properties.trafficWeight!=null && properties.trafficWeight>\`0\`].{name:name, w:properties.trafficWeight}, &w)[-1].name" -o tsv || true)

echo "new:    $NEW_REV"
echo "stable: ${STABLE_REV:-<无>}"

# 拼健康检查 URL（label URL: {app}---{label}.{domain}）
APP_NAME="${FQDN%%.*}"
ENV_DOMAIN="${FQDN#*.}"
CANARY_URL="https://${APP_NAME}---canary.${ENV_DOMAIN}/health"
MAIN_URL="https://${FQDN}/health"

echo "canary: $CANARY_URL"
echo "main:   $MAIN_URL"

# 首次部署（没有 stable 或新旧一样）
if [ -z "${STABLE_REV:-}" ] || [ "$STABLE_REV" = "None" ] || [ "$NEW_REV" = "$STABLE_REV" ]; then
  echo "首次部署，100% 切到 $NEW_REV"
  run_with_retry az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$NEW_REV=100"
  sleep 15
  if ! check_health "$MAIN_URL" 15 24; then
    echo "首次部署 health check 失败"
    exit 1
  fi
  if ! warmup_model "${MAIN_URL%/health}/warmup" 300 2; then
    echo "首次部署 warmup 失败"
    exit 1
  fi
  echo "首次部署完成"
  exit 0
fi

# --- Canary 流程 ---

# 清理旧的 canary label
az containerapp revision label remove --name "$APP" --resource-group "$RG" --label canary 2>/dev/null || true

# 给新 revision 打 canary label
echo "label canary -> $NEW_REV"
run_with_retry az containerapp revision label add \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$NEW_REV" \
  --label canary

# 0% — 冒烟测试（只走 label URL 不影响生产流量）
echo "=== 0% 冒烟测试 ==="
sleep 15
if ! check_health "$CANARY_URL" 15 24; then rollback; fi
if ! warmup_model "${CANARY_URL%/health}/warmup" 300 2; then rollback; fi

# 10%
echo "=== 10% ==="
run_with_retry az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$STABLE_REV=90" "$NEW_REV=10"
sleep 10
if ! check_health "$CANARY_URL" 10 24; then rollback; fi

# 50%
echo "=== 50% ==="
run_with_retry az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$STABLE_REV=50" "$NEW_REV=50"
sleep 10
if ! check_health "$CANARY_URL" 10 24; then rollback; fi

# 100%
echo "=== 100% ==="
run_with_retry az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$NEW_REV=100"
sleep 5
if ! check_health "$MAIN_URL" 10 24; then rollback; fi

# 停用旧版本
echo "停用旧 revision: $STABLE_REV"
az containerapp revision deactivate -g "$RG" -n "$APP" --revision "$STABLE_REV" 2>/dev/null || true

echo "部署完成: $NEW_REV (100%), $STABLE_REV (已停用)"
