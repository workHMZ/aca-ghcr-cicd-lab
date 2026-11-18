# Security Policy

## Supported Versions

This repository is at release `3.2.1`. Security fixes apply to the active `3.2.x` line on `main`; earlier tags remain archived as historical lab snapshots without backported patches.

## Reporting a Vulnerability

Report suspected vulnerabilities privately through [GitHub Security Advisories](https://github.com/workHMZ/aca-ghcr-cicd-lab/security/advisories/new). Keep credentials, exploit payloads, non-public corpus files, tenant identifiers, and raw cloud logs out of public issues and pull requests.

Include the affected release tag or commit SHA, minimal reproduction steps, security impact, and any proposed mitigation. Reports are acknowledged promptly and disclosed after a verified fix is deployed.

## Trust Boundaries & Runtime Controls

`aca-ghcr-cicd-lab` operates a public single-replica RAG service within Azure's free consumption tiers. Its security model relies on explicit boundaries across five layers:

- **Public ingress & spend guardrails**: The FastAPI endpoint accepts anonymous traffic unless an external gateway enforces authentication. Input length and `top_k` are strictly bounded, while an in-process `3600 s` TTL answer cache and per-replica `QUERY_RATE_LIMIT_PER_MINUTE` and `QUERY_DAILY_LIMIT` budgets cap uncached Azure AI Search semantic queries and OpenAI calls. Cache bypass via `X-Canary-Token` requires constant-time verification against `CANARY_CACHE_BYPASS_TOKEN`. Multi-replica or multi-tenant deployments should add identity-aware access control and a shared edge rate limiter.
- **Data disclosure & untrusted evidence**: Every indexed chunk can be returned verbatim in API citations and transmitted alongside the user question to OpenAI with `store=false`. Operators must treat the search index as a public disclosure boundary and scope `scripts/ingest.py` explicitly with `--glob` over approved public documents. At query time, retrieved chunks are wrapped inside an untrusted-data boundary, semantic ranking fails closed on missing scores or HTTP `402` quota exhaustion, hits below `SEARCH_MIN_RERANKER_SCORE` abort before LLM generation, chunks with mismatched `embeddingModel`, `embeddingRevision`, or `embeddingVariant` are rejected, and returned citation indices are validated against retained context bounds.
- **Least-privilege credentials & state isolation**: Online serving and `scripts/evaluate_retrieval.py` authenticate to Azure AI Search exclusively with a read-only `AZURE_SEARCH_QUERY_KEY`; `AZURE_SEARCH_ADMIN_KEY` is reserved for offline operator CLIs `create_index.py`, `ingest.py`, and `clear_index.py`. GitHub Actions authenticates to Azure through short-lived OIDC federated credentials scoped to this repository and the `stg` environment. Secrets are injected at runtime and rotated immediately upon suspected exposure. Terraform state must reside in an access-controlled, encrypted Azure Storage backend with state locking and must never be committed.
- **Metadata-only observability**: When the optional Datadog Agent sidecar is enabled, `app/telemetry.py` exports stage latency, chunk counts, reranker score bounds, and token usage over `127.0.0.1:8126` while keeping `DD_TRACE_OPENAI_ENABLED=false` and agentless export disabled. User questions, generated answers, corpus text, and raw exception strings are excluded from trace attributes, and the Datadog API key remains isolated inside the sidecar container.
- **Offline ingestion & container hardening**: PDF parsing via `pypdf` stays restricted to operator CLI tooling and is excluded from the production container image; run ingestion in an isolated environment over vetted inputs. During image build, `app/model_manifest.py` downloads tokenizer and ONNX weights from a pinned Hugging Face commit and verifies every file against hardcoded SHA-256 digests. The runtime stage starts from a digest-pinned Debian Bookworm Python image, strips `pip` and `ensurepip`, runs as non-root UID/GID `10001`, and enforces `EMBEDDING_OFFLINE=1`.

## Supply Chain & Continuous Verification

- **Static, dependency, and IaC gates**: `scripts/verify.sh` audits the locked runtime dependency graph via `pip-audit`. `.github/workflows/security.yml` runs CodeQL analysis over Python and GitHub Actions workflows alongside Trivy `HIGH/CRITICAL` gates covering filesystem dependencies, Terraform configuration, committed secrets, and the built container image.
- **Air-gapped smoke & cryptographic provenance**: `.github/workflows/ci.yml` verifies container startup and memory bounds under `--network none` via `scripts/smoke_container.sh`, scans the pushed `sha256` image digest with Trivy, attaches a Syft CycloneDX SBOM attestation, and signs the immutable digest keyless with Cosign as the final CI step. `.github/workflows/cd.yml` verifies both the Cosign signature and SBOM attestation against the exact CI workflow identity, `refs/heads/main`, and commit SHA before deploying a `0%`-traffic canary revision.
