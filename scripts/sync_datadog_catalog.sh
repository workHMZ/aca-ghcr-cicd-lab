#!/usr/bin/env bash
set -euo pipefail

: "${DD_API_KEY:?DD_API_KEY is required}"
: "${DD_APP_KEY:?DD_APP_KEY is required}"
: "${DD_SITE:?DD_SITE is required}"

DEFINITION_FILE="${1:-service.datadog.yaml}"
if [[ ! -f "${DEFINITION_FILE}" ]]; then
  echo "Service definition file not found: ${DEFINITION_FILE}" >&2
  exit 1
fi

API_URL="https://api.${DD_SITE}/api/v2/catalog/entity"
SERVICE_NAME="$(awk -F': *' '$1=="dd-service"{print $2; exit}' "${DEFINITION_FILE}" | tr -d '"' || true)"
SERVICE_NAME="${SERVICE_NAME:-unknown}"
PAYLOAD_FILE="${DEFINITION_FILE}"
CONTENT_TYPE="application/yaml"

# Prefer JSON payload when Ruby is available; fallback to raw YAML otherwise.
if command -v ruby >/dev/null 2>&1; then
  PAYLOAD_FILE="$(mktemp)"
  trap 'rm -f "${PAYLOAD_FILE}"' EXIT
  ruby -ryaml -rjson -e 'print JSON.generate(YAML.safe_load(File.read(ARGV[0]), aliases: true))' "${DEFINITION_FILE}" > "${PAYLOAD_FILE}"
  CONTENT_TYPE="application/json"
fi

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "[DRY_RUN] Would sync Datadog catalog entity: ${SERVICE_NAME}"
  echo "[DRY_RUN] Endpoint: ${API_URL}"
  echo "[DRY_RUN] Content-Type: ${CONTENT_TYPE}"
  exit 0
fi

curl -sS --fail-with-body \
  -X POST "${API_URL}" \
  -H "Accept: application/json" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
  -H "Content-Type: ${CONTENT_TYPE}" \
  --data-binary @"${PAYLOAD_FILE}" >/dev/null

echo "Datadog Service Catalog synced: ${SERVICE_NAME}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "- **Datadog Service Catalog:** synced (\`${SERVICE_NAME}\`)" >> "${GITHUB_STEP_SUMMARY}"
fi
