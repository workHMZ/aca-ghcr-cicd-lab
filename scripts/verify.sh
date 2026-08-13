#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

ruff format --check app scripts tests
ruff check app scripts tests
mypy app
mkdir -p .cache
uv export \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-hashes \
  --format requirements-txt \
  --output-file .cache/runtime-requirements.txt >/dev/null
# The exported lock is already transitive and fully pinned. Auditing it without
# invoking pip also preserves uv's explicit PyTorch CPU index on Linux; PyPI
# does not publish the `+cpu` wheel selected by uv.lock.
python -m pip_audit \
  -r .cache/runtime-requirements.txt \
  --no-deps \
  --disable-pip
pytest \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-fail-under=80

python -m compileall -q app scripts tests
git diff --check
