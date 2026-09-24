# Security policy

## Supported version

Security fixes apply to the latest `3.x` line on `main` (currently `3.1.0`). Earlier
interview-lab releases are retained for learning and are not supported.

## Reporting a vulnerability

Please use [GitHub private vulnerability reporting](https://github.com/workHMZ/aca-ghcr-cicd-lab/security/advisories/new). Do not open a public issue with credentials, exploit payloads, private document content, tenant identifiers, or non-public resource details.

Include the affected version or commit, reproduction steps, impact, and a suggested mitigation if available. The maintainer will acknowledge a report as soon as practical and coordinate disclosure after a fix is ready.

## Current trust boundary

This repository is an interview and learning project, not a hosted multi-tenant product.

- The FastAPI ingress is public unless authentication is configured outside the app. Do not ingest confidential documents into a public deployment.
- Retrieved text is untrusted data. The generation prompt isolates it as context, but prompt injection cannot be eliminated by prompting alone.
- Request length and `top_k` are bounded, and uncached queries are capped per minute and per UTC day
  (`QUERY_RATE_LIMIT_PER_MINUTE`, `QUERY_DAILY_LIMIT`) to bound OpenAI and semantic-ranker spend on the
  anonymous endpoint. The budget is in-process (per replica); production deployments should add
  identity-aware access, a shared/edge rate limiter, and abuse monitoring.
- Azure AI Search and OpenAI credentials are injected as secrets and must never be committed. Rotate a credential immediately if it is exposed.
- A query sends the user's question and retrieved chunks to OpenAI for generation, even with
  `store=false`. The API response also returns full retrieved chunk text to the caller. Corpus
  owners must treat both paths as deliberate data-disclosure boundaries.
- GitHub Actions currently uses a long-lived Azure service-principal credential as an explicit lab trade-off. A production deployment should use a narrowly scoped federated identity.
- Terraform creates that one-year service-principal password. Its value enters Terraform state,
  so initialization must use the declared Azure Storage backend with access control, encryption,
  locking, and a reviewed state-retention policy; never use or commit a local state file.
- PDF ingestion processes untrusted files. Run ingestion in an isolated environment, keep `pypdf` patched, and enforce file-size/page/time limits before exposing uploads to users.
  Ingestion is an operator-only CLI (`pypdf` is not in the serving image); use `--glob` to select
  exactly the public documents, because everything ingested is returned verbatim by the public API.
- The embedding model is downloaded from an immutable Hugging Face revision and every file is
  checked against a pinned SHA-256 (`app/model_manifest.py`) before it enters the image.

## Dependency and image controls

The local quality gate audits locked Python runtime dependencies. CI scans the exact image digest, produces an SBOM, signs the digest with Cosign, and CD verifies that signature before a canary rollout. A valid signature proves provenance, not the absence of application vulnerabilities.
