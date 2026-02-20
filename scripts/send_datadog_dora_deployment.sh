#!/usr/bin/env bash
set -euo pipefail

: "${DD_API_KEY:?DD_API_KEY is required}"
: "${DD_SITE:?DD_SITE is required}"
: "${DORA_SERVICE:?DORA_SERVICE is required}"
: "${DORA_ENV:?DORA_ENV is required}"
: "${DORA_STARTED_AT_NS:?DORA_STARTED_AT_NS is required}"
: "${DORA_VERSION:?DORA_VERSION is required}"
: "${DORA_REPOSITORY_URL:?DORA_REPOSITORY_URL is required}"
: "${WORKFLOW_EVENT_NAME:?WORKFLOW_EVENT_NAME is required}"
: "${GITHUB_SHA_CURRENT:?GITHUB_SHA_CURRENT is required}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to build the DORA API payload." >&2
  exit 1
fi

if [[ ! "${DORA_STARTED_AT_NS}" =~ ^[0-9]+$ ]]; then
  echo "DORA_STARTED_AT_NS must be an integer timestamp in nanoseconds." >&2
  exit 1
fi

COMMIT_SHA="${GITHUB_SHA_CURRENT}"
if [[ "${WORKFLOW_EVENT_NAME}" == "workflow_run" && -n "${WORKFLOW_HEAD_SHA:-}" ]]; then
  COMMIT_SHA="${WORKFLOW_HEAD_SHA}"
fi

FINISHED_AT_NS="$(date +%s%N)"
export FINISHED_AT_NS
export COMMIT_SHA

python3 - <<'PY' > dora-deployment.json
import json
import os

payload = {
    "data": {
        "attributes": {
            "service": os.environ["DORA_SERVICE"],
            "env": os.environ["DORA_ENV"],
            "started_at": int(os.environ["DORA_STARTED_AT_NS"]),
            "finished_at": int(os.environ["FINISHED_AT_NS"]),
            "version": os.environ["DORA_VERSION"],
            "git": {
                "repository_url": os.environ["DORA_REPOSITORY_URL"],
                "commit_sha": os.environ["COMMIT_SHA"],
            },
        },
        "type": "dora_deployment",
    }
}
print(json.dumps(payload, separators=(",", ":")))
PY

if [[ "${DRY_RUN:-0}" == "1" ]]; then
  echo "[DRY_RUN] Would send Datadog DORA deployment event:"
  cat dora-deployment.json
  rm -f dora-deployment.json
  exit 0
fi

curl -sS --fail-with-body \
  -X POST "https://api.${DD_SITE}/api/v2/dora/deployment" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  --data-binary @dora-deployment.json >/dev/null

rm -f dora-deployment.json

echo "Datadog DORA deployment event sent: service=${DORA_SERVICE}, version=${DORA_VERSION}"
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  echo "- **Datadog DORA:** deployment event sent (\`${DORA_SERVICE}\`, v\`${DORA_VERSION}\`)" >> "${GITHUB_STEP_SUMMARY}"
fi
