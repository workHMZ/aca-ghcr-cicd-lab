## What changed

<!-- Describe the user-visible or operational outcome. -->

## Verification

- [ ] `uv sync --frozen --dev`
- [ ] `bash scripts/verify.sh`
- [ ] Index schema or embedding changes include a new-index and re-ingestion plan
- [ ] Deployment changes include rollback behavior
- [ ] No secret, private corpus, generated state, or local-only file is included

## Risk and rollback

<!-- Call out compatibility breaks, model/index coupling, and the exact rollback path. -->
