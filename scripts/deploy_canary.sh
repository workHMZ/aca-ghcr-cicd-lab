#!/bin/bash
set -euo pipefail

RG="${1:-}"
APP="${2:-}"

if [ -z "$RG" ] || [ -z "$APP" ]; then
  echo "Usage: $0 <resource-group> <container-app-name>"
  exit 1
fi

# --- Utility functions / ユーティリティ関数 ---

# Retry up to 5 times with 10s interval
# 最大5回、10秒間隔でリトライ
run_with_retry() {
  local n=1
  local max=5
  local delay=10
  while true; do
    "$@" && break || {
      if [[ $n -lt $max ]]; then
        ((n++))
        echo "  Retry $n/$max..."
        sleep $delay
      else
        echo "  Failed after $max attempts"
        return 1
      fi
    }
  done
}

# Health check / ヘルスチェック
check_health() {
  local url="$1"
  local timeout="${2:-10}"
  local attempts="${3:-24}"
  echo "Health check: $url"
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time "$timeout" "$url" >/dev/null 2>&1; then
      echo "  OK"
      return 0
    fi
    echo "  Waiting ($i/$attempts)..."
    sleep 10
  done
  echo "  Timed out, health check failed"
  return 1
}

# Warmup: preload embedding model / ウォームアップ: 埋め込みモデルを事前読み込み
warmup_model() {
  local url="$1"
  local timeout="${2:-300}"
  local attempts="${3:-2}"
  echo "Warmup: $url"
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time "$timeout" "$url" >/dev/null 2>&1; then
      echo "  Warmup complete"
      return 0
    fi
    echo "  Warmup failed, retrying ($i/$attempts)..."
    sleep 10
  done
  echo "  Warmup ultimately failed"
  return 1
}

# Verify traffic weight has been applied / トラフィックの重みが適用されたか検証
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
    echo "  Verifying traffic ($i/$attempts): current=$CURRENT_WEIGHT expected=$expected"
    sleep 5
  done
  return 1
}

# Rollback: disable set -e to ensure full execution
# ロールバック: 完全に実行するために set -e を無効化
rollback() {
  echo "Starting rollback..."
  set +e

  if [ -z "${STABLE_REV:-}" ] || [ "$STABLE_REV" = "None" ]; then
    echo "No stable revision found, cannot rollback"
    exit 1
  fi

  echo "Routing all traffic back to $STABLE_REV..."
  run_with_retry az containerapp ingress traffic set \
    -g "$RG" -n "$APP" \
    --revision-weight "$STABLE_REV=100"

  if [ $? -ne 0 ]; then
    echo "Rollback failed! Manual intervention required"
    exit 1
  fi

  echo "Verifying traffic..."
  if ! verify_traffic "$STABLE_REV" 100 8; then
    echo "Traffic verification failed"
    exit 1
  fi
  echo "Traffic restored to stable revision"

  # Deactivate the faulty revision (ignore errors)
  # 問題のあるリビジョンを無効化（エラーは無視）
  echo "Deactivating $NEW_REV..."
  az containerapp revision deactivate -g "$RG" -n "$APP" --revision "$NEW_REV" 2>/dev/null || true

  echo "Rollback complete"
  exit 1
}

# --- Main flow / メインフロー ---

echo "Querying FQDN..."
FQDN=$(az containerapp show -g "$RG" -n "$APP" --query "properties.configuration.ingress.fqdn" -o tsv)
if [ -z "$FQDN" ] || [ "$FQDN" = "None" ]; then
  echo "Cannot retrieve FQDN, check if External Ingress is enabled"
  exit 1
fi

# Latest revision = just deployed / 最新のリビジョン = デプロイ直後のもの
NEW_REV=$(az containerapp revision list -g "$RG" -n "$APP" \
  --query "sort_by([].{name:name, created:properties.createdTime}, &created)[-1].name" -o tsv)

if [ -z "$NEW_REV" ] || [ "$NEW_REV" = "None" ]; then
  echo "Cannot find new revision"
  exit 1
fi

# Revision with highest traffic = stable / トラフィック最大のリビジョン = stable
STABLE_REV=$(az containerapp revision list -g "$RG" -n "$APP" \
  --query "sort_by([?properties.trafficWeight!=null && properties.trafficWeight>\`0\`].{name:name, w:properties.trafficWeight}, &w)[-1].name" -o tsv || true)

echo "new:    $NEW_REV"
echo "stable: ${STABLE_REV:-<none>}"

# Build health check URLs (label URL: {app}---{label}.{domain})
# ヘルスチェック URL を構築（ラベル URL: {app}---{label}.{domain}）
APP_NAME="${FQDN%%.*}"
ENV_DOMAIN="${FQDN#*.}"
CANARY_URL="https://${APP_NAME}---canary.${ENV_DOMAIN}/health"
MAIN_URL="https://${FQDN}/health"

echo "canary: $CANARY_URL"
echo "main:   $MAIN_URL"

# Initial deployment (no stable or same revision)
# 初回デプロイ（stable がないか、新旧同一の場合）
if [ -z "${STABLE_REV:-}" ] || [ "$STABLE_REV" = "None" ] || [ "$NEW_REV" = "$STABLE_REV" ]; then
  echo "Initial deployment, routing 100% to $NEW_REV"
  run_with_retry az containerapp ingress traffic set -g "$RG" -n "$APP" --revision-weight "$NEW_REV=100"
  sleep 15
  if ! check_health "$MAIN_URL" 15 24; then
    echo "Initial deployment health check failed"
    exit 1
  fi
  if ! warmup_model "${MAIN_URL%/health}/warmup" 300 2; then
    echo "Initial deployment warmup failed"
    exit 1
  fi
  echo "Initial deployment complete"
  exit 0
fi

# --- Canary rollout / カナリアリリース ---

# Remove any existing canary label / 既存の canary ラベルを削除
az containerapp revision label remove --name "$APP" --resource-group "$RG" --label canary 2>/dev/null || true

# Assign canary label to new revision / 新しいリビジョンに canary ラベルを付与
echo "label canary -> $NEW_REV"
run_with_retry az containerapp revision label add \
  --name "$APP" \
  --resource-group "$RG" \
  --revision "$NEW_REV" \
  --label canary

# 0% — Smoke test (label URL only, no production traffic impact)
# 0% — スモークテスト（ラベル URL のみ、本番トラフィックへの影響なし）
echo "=== 0% Smoke Test ==="
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

# Deactivate old revision / 旧リビジョンを無効化
echo "Deactivating old revision: $STABLE_REV"
az containerapp revision deactivate -g "$RG" -n "$APP" --revision "$STABLE_REV" 2>/dev/null || true

echo "Deployment complete: $NEW_REV (100%), $STABLE_REV (deactivated)"
