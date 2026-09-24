#!/usr/bin/env bash
# Boot the image exactly as a 0.5 vCPU / 1 GiB Container Apps replica would,
# with networking disabled, and prove that it serves without Azure, OpenAI,
# or Hugging Face: /health answers, the pinned model loads offline, and memory
# stays under the replica limit.
set -euo pipefail

IMAGE="${1:?Usage: $0 <image>}"
CPUS="${SMOKE_CPUS:-0.5}"
MEMORY="${SMOKE_MEMORY:-1g}"
MAX_MEMORY_MIB="${SMOKE_MAX_MEMORY_MIB:-900}"
TIMEOUT_SECONDS="${SMOKE_TIMEOUT_SECONDS:-90}"
# Space-separated KEY=VALUE pairs, e.g. SMOKE_ENV="DD_TRACE_ENABLED=true" to
# boot the traced (Datadog sidecar) configuration without an Agent present.
SMOKE_ENV="${SMOKE_ENV:-}"

env_args=()
for pair in $SMOKE_ENV; do
  env_args+=(--env "$pair")
done

container=$(docker run --detach --network none --cpus "$CPUS" --memory "$MEMORY" \
  ${env_args[@]+"${env_args[@]}"} "$IMAGE")
cleanup() {
  docker logs "$container" 2>&1 | tail -n 20 || true
  docker rm --force "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

probe() {
  docker exec "$container" python -c '
import json, sys, urllib.error, urllib.request
try:
    response = urllib.request.urlopen("http://127.0.0.1:8000" + sys.argv[1], timeout=5)
    print(response.status, response.read().decode())
except urllib.error.HTTPError as error:
    print(error.code, error.read().decode())
' "$1"
}

started=$(date +%s)
until probe /health 2>/dev/null | grep -q '^200 '; do
  if (( $(date +%s) - started > TIMEOUT_SECONDS )); then
    echo "Container did not answer /health within ${TIMEOUT_SECONDS}s" >&2
    exit 1
  fi
  sleep 1
done
echo "health: $(( $(date +%s) - started ))s after start"

# Without Azure/OpenAI configuration the service must report exactly those
# two dependencies as missing, which proves the embedding model loaded.
until ready=$(probe /ready) && grep -q '"missing":\["azure_search","openai"\]' <<< "$ready"; do
  if (( $(date +%s) - started > TIMEOUT_SECONDS )); then
    echo "Model did not load offline: $ready" >&2
    exit 1
  fi
  sleep 1
done
echo "model ready: $(( $(date +%s) - started ))s after start"

# ddtrace-run puts its bootstrap directory on PYTHONPATH of the server process.
traced=false
if docker exec "$container" sh -c 'tr "\0" "\n" < /proc/1/environ' | grep -q 'ddtrace/bootstrap'; then
  traced=true
fi
expected_traced=false
if grep -Eq '(^| )DD_TRACE_ENABLED=(1|true|yes|on)( |$)' <<< "$SMOKE_ENV"; then
  expected_traced=true
fi
if [ "$traced" != "$expected_traced" ]; then
  echo "ddtrace-run active=$traced, expected $expected_traced" >&2
  exit 1
fi
echo "ddtrace-run active: $traced"

warmup=$(probe /warmup)
grep -q '^200 ' <<< "$warmup" || { echo "Warmup failed: $warmup" >&2; exit 1; }
grep -q '"embedding_variant":"onnx-qint8"' <<< "$warmup" || { echo "Unexpected variant: $warmup" >&2; exit 1; }

usage=$(docker stats --no-stream --format '{{.MemUsage}}' "$container" | awk '{print $1}')
mib=$(python3 -c '
import re, sys
value, unit = re.match(r"([0-9.]+)([A-Za-z]+)", sys.argv[1]).groups()
print(int(float(value) * {"B": 1 / 2**20, "KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[unit]))
' "$usage")
echo "memory after warmup: ${mib} MiB (limit ${MEMORY}, budget ${MAX_MEMORY_MIB} MiB)"
if (( mib > MAX_MEMORY_MIB )); then
  echo "Memory ${mib} MiB exceeds the ${MAX_MEMORY_MIB} MiB budget" >&2
  exit 1
fi
echo "Container smoke test passed"
