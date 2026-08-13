# Serverless Multilingual RAG on Azure

[![CI](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml)
[![Security](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://www.python.org/)
[![Version 3.0.0](https://img.shields.io/badge/version-3.0.0-6f42c1.svg)](#release-state)

FastAPI + pinned multilingual embeddings + Azure AI Search hybrid retrieval +
OpenAI Responses API, designed for a signed Azure Container Apps canary.

> **Release state:** the repository contains the local 3.0.0 release candidate.
> The Azure snapshot recorded on 2026-08-13 was still the 2.x deployment using
> the legacy ragdocs index. Creating ragdocs-v3, re-embedding the corpus,
> pushing the tag, and deploying remain explicit maintainer actions.

[中文摘要](#中文摘要) · [Architecture](#architecture) ·
[Measured results](#measured-results) · [Quick start](#quick-start) ·
[2.x → 3.0 migration](#2x--30-index-migration) ·
[面试讲解](INTERVIEW_GUIDE.md) · [Security policy](SECURITY.md)

## 中文摘要

这是一个面向面试演示的 Azure 多语言 RAG 项目。3.0 不只是把生成模型改成
gpt-5.6-terra，而是修复了旧版检索链路的根因：

- 将英语导向的 all-MiniLM-L6-v2 替换为固定 commit 的
  intfloat/multilingual-e5-small；
- 查询使用 query: 前缀，文档使用 passage: 前缀，并对两侧向量归一化；
- 按 tokenizer 做 384/48 token 分块，保存页码、chunk、内容哈希和模型 revision；
- 使用独立 ragdocs-v3 索引，避免新旧 384 维向量在不兼容的空间中混用；
- 使用关键词 + HNSW + Azure semantic ranker 的混合检索；
- 通过 OpenAI Responses API 返回结构化答案、引用、grounded 状态和 usage；
- 增加离线 retrieval eval、测试/覆盖率/依赖审计、锁文件、非 root 容器、
  SBOM、Cosign 和真实 RAG 金丝雀检查。

完整的 30 秒、2 分钟和 5 分钟面试陈述见
[INTERVIEW_GUIDE.md](INTERVIEW_GUIDE.md)。

## Why this project

The 2.x application could produce fluent answers, but fluent generation did
not prove that retrieval was correct. Its English-oriented embedding model,
fixed-character chunks, missing overlap and page metadata, and legacy index
made Chinese/Japanese retrieval difficult to diagnose.

Version 3.0 treats retrieval quality, reproducibility, and delivery safety as
one system:

1. **Measured retrieval** — a reproducible multilingual fixture separates
   embedding quality from answer-generation quality.
2. **Versioned data plane** — model revision, chunk metadata, stable IDs, and a
   new index prevent silent embedding-space mismatches.
3. **Grounded generation** — Terra receives numbered, untrusted contexts and
   returns a validated schema with citations.
4. **Verifiable delivery** — one immutable image digest is scanned, attested,
   signed, verified, and rolled out through 0/10/50/100% traffic gates.

## Architecture

### Data plane

~~~mermaid
flowchart LR
    subgraph Ingestion["Versioned ingestion"]
        Docs["PDF / Markdown / text"] --> Chunk["Tokenizer-aware chunks<br/>page + stable ID + content hash"]
        Chunk --> Passage["E5 passage: embedding<br/>normalized, 384 dimensions"]
        Passage --> Index["Azure AI Search<br/>ragdocs-v3"]
    end

    subgraph Query["Online query"]
        User["Client"] --> API["FastAPI on Azure Container Apps"]
        API --> QueryVec["E5 query: embedding"]
        QueryVec --> Hybrid["Keyword + HNSW + semantic hybrid"]
        Index --> Hybrid
        Hybrid --> Context["Numbered contexts<br/>source + page + chunk"]
        Context --> Terra["OpenAI gpt-5.6-terra<br/>Responses structured output"]
        Terra --> Result["Answer + citations + grounded + usage"]
        Result --> User
    end
~~~

The embedding model and generator have separate responsibilities. Terra does
not generate vectors, and replacing Terra cannot repair poor retrieval.

### Delivery plane

~~~mermaid
flowchart LR
    PR["Pull request"] --> Quality["Ruff + Mypy + Pytest<br/>pip-audit + Terraform validate"]
    Quality --> Build["Build immutable image once"]
    Build --> Candidate["GHCR immutable SHA digest"]
    Candidate --> Scan["Trivy exact digest"]
    Scan --> Evidence["CycloneDX SBOM<br/>Cosign attestation"]
    Evidence --> Promote["Upload evidence<br/>promote digest to latest"]
    Promote --> Authorize["Final deployment-authorization<br/>Cosign signature"]
    Authorize --> Verify["Verify signature + attestation<br/>ci.yml@main identity"]
    Verify --> Canary["ACA candidate at 0%<br/>health + warmup + real query"]
    Canary --> Traffic["10% → 50% → 100%<br/>weight verification"]
    Traffic --> Stable["Stable revision"]
    Canary -. "failure / cancellation" .-> Rollback["Restore previous revision"]
~~~

Datadog APM, Service Catalog sync, and DORA events are optional and only run
when their credentials are configured.

## Model decisions

| Component | 2.x baseline | 3.0 decision | Reason / trade-off |
|---|---|---|---|
| Embedding | all-MiniLM-L6-v2 | intfloat/multilingual-e5-small at 614241f622f53c4eeff9890bdc4f31cfecc418b3 | Multilingual retrieval, 384 dimensions, local inference; larger image and cold start |
| Generator | gpt-5.4-mini in the observed Azure revision | gpt-5.6-terra, reasoning low | Better grounded multilingual synthesis and Structured Outputs; higher latency/cost must be measured |
| Index | ragdocs | ragdocs-v3 | A new embedding model requires a new vector space even when both output 384 dimensions |
| Retrieval | legacy exact-vector baseline | keyword + non-exhaustive HNSW + semantic ranker | Keeps exact technical terms while adding multilingual semantic recall |

The Terra model ID was verified against the configured OpenAI account and with
a synthetic Responses Structured Outputs call. The runtime model remains
configurable through OPENAI_MODEL so a separately evaluated fallback can be
used for quota, latency, or cost reasons.

Why not BGE-M3? It is capable and multilingual, but its 1024-dimensional dense
vectors and much larger weights do not fit this small scale-to-zero design as
comfortably. E5-small is a deliberate resource/quality compromise, not a claim
that it wins every corpus.

## How retrieval works

Ingestion reads PDF files page by page and Markdown/text by document. Chunks
respect paragraph boundaries where possible, then use the embedding tokenizer
with a 384-token target and 48-token overlap. Each record includes:

- source and page number;
- stable chunk index and SHA-256-derived document ID;
- content hash;
- embedding model and immutable revision;
- the source file's UTC modification timestamp.

Uploads are batched and idempotent through merge-or-upload; each source is then
synchronized so stale tail chunks from a shortened file are deleted. The index uses
cosine HNSW and a semantic configuration over content/source. Online queries
create at least 50 vector candidates before returning the configured top K.

Deleting an entire source file from data does not automatically discover its
old namespace. For exact corpus replacement, ingest into a fresh versioned
index (the 3.0 migration path) or explicitly clear/delete the old source first.

The generator is instructed to treat retrieved text as untrusted evidence, use
only that evidence, cite valid one-based context numbers, and refuse when the
evidence is insufficient. Prompting reduces risk but cannot eliminate prompt
injection.

Before generation, runtime retrieval rejects any hit whose embedding model or
revision differs from the pinned E5 configuration. The prompt includes source,
page, and chunk metadata and wraps each retrieved body in an explicit untrusted
context boundary.

## Measured results

### Reproducible synthetic retrieval fixture

The bundled fixture contains 6 labelled ZH/JA/EN queries and 9 passages. It
executes real local model inference; it is a regression/ablation fixture, not a
measurement of the private PDF corpus.

| Model | Overall Recall@1 | Recall@3 | MRR | JA Recall@1 | JA MRR |
|---|---:|---:|---:|---:|---:|
| all-MiniLM-L6-v2 baseline | 0.833333 | 1.000000 | 0.916667 | 0.500000 | 0.750000 |
| multilingual-e5-small | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| Candidate minus baseline | +0.166667 | 0.000000 | +0.083333 | +0.500000 | +0.250000 |

Reproduce the comparison:

~~~bash
uv sync --frozen --dev
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
~~~

### Local engineering gates

The final local verification records:

- 26 tests passed;
- 83.30% branch-aware application coverage;
- Ruff formatting/lint and strict Mypy passed;
- locked runtime dependency audit reported no known vulnerabilities;
- E5 emitted normalized 384-dimensional query/passage vectors;
- measured E5 load/inference maximum resident memory was about 915 MiB on the
  development machine, making the 2 GiB app target a minimum rather than a
  generous allocation.

The private Java PDF was only dry-chunked locally: 282 pages became 498 chunks.
It was not uploaded, committed, or sent to OpenAI. A credible production claim
still requires a manually reviewed 60–100 question golden set over that corpus,
including unanswerable and multi-hop cases.

## Project layout

~~~text
app/
  config.py           validated runtime settings
  chunking.py         tokenizer-aware paragraph chunking
  embed.py            pinned E5 query/passage embeddings
  search_client.py    cached Azure Search client
  main.py             async FastAPI + structured Terra generation
eval/
  corpus.jsonl        small multilingual synthetic corpus
  golden.jsonl        labelled retrieval queries
scripts/
  create_index.py     safe versioned index creation
  ingest.py           idempotent page-aware ingestion
  evaluate_retrieval.py
  deploy_canary.sh    verified rollout and rollback
tests/                application unit and contract tests
terraform/            existing-environment reconciliation and ACA target state
.github/workflows/    quality, supply-chain, security, and CD gates
~~~

## Quick start

### Requirements

- Python 3.12.13 and uv 0.11.16;
- an OpenAI API key with access to the configured generator;
- an Azure AI Search service and admin key;
- Azure CLI/Terraform only for infrastructure or deployment work.

Install the locked environment:

~~~bash
uv python install 3.12.13
uv sync --frozen --dev
cp .env.example .env
~~~

Fill AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, and OPENAI_API_KEY in the
ignored .env file. Do not commit it.

Create a new versioned index and ingest local documents:

~~~bash
uv run python scripts/create_index.py --index-name ragdocs-v3
uv run python scripts/ingest.py --data-dir data --index-name ragdocs-v3
~~~

Index creation refuses to overwrite an existing index unless
--delete-existing is explicitly supplied. Clearing documents is similarly
protected by --yes.

Start and probe the API:

~~~bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/query \
  -H 'content-type: application/json' \
  --data '{"question":"Java 中 HashMap 的工作原理是什么？","top_k":3}'
~~~

Run the complete local gate:

~~~bash
PATH="$PWD/.venv/bin:$PATH" bash scripts/verify.sh
~~~

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| AZURE_SEARCH_INDEX_NAME | ragdocs-v3 | Runtime index |
| AZURE_SEARCH_INDEX_NAME_V3 | ragdocs-v3 | Safe migration-script target; never falls back to the legacy name |
| OPENAI_MODEL | gpt-5.6-terra | Generator |
| OPENAI_REASONING_EFFORT | low | Terra reasoning budget |
| OPENAI_VERBOSITY | low | Response verbosity |
| OPENAI_MAX_OUTPUT_TOKENS | 1200 | Output ceiling |
| EMBEDDING_MODEL | intfloat/multilingual-e5-small | Fixed supported embedding family |
| EMBEDDING_MODEL_REVISION | 614241f…18b3 | Immutable model commit |
| EMBEDDING_MODEL_PATH | unset locally; /opt/models/... in image | Preloaded offline model |
| EMBEDDING_BATCH_SIZE | 16 | Online/batch encoding size |
| EMBEDDING_QUERY_MAX_TOKENS | 512 | Online query encoder ceiling; ingestion chunks default to 384 |
| SEARCH_TOP_K_DEFAULT / MAX | 5 / 10 | Retrieval result bounds |
| MAX_QUESTION_CHARS | 4000 | Request abuse/size bound |

See [.env.example](.env.example) for the full set.

## API contract

- GET /health — process liveness only; no dependency calls.
- GET /ready — validates Search/OpenAI configuration and loads the local
  embedding model without calling external services.
- GET /warmup — explicitly loads and exercises the embedding model.
- POST /query — returns backward-compatible answer/contexts plus metadata:
  actual generator, response status, grounded/refused state, validated
  citations, and token usage.

Question text and retrieved private content are not written to normal
application logs. Query logs contain a hash and character count for
correlation.

## 2.x → 3.0 index migration

The migration is intentionally dual-index and reversible:

1. Keep the current ragdocs index and stable 2.x revision.
2. Create ragdocs-v3 without --delete-existing.
3. Re-embed the full corpus with the fixed E5 revision.
4. Replace the synthetic golden file with source-labelled questions, then run
   the Azure source-level smoke and manually inspect ZH/JA/EN results. Use a
   dedicated page/chunk-labelled evaluator before making recall claims.
5. Reconcile/import the existing Container App state, review Terraform plan,
   and apply the 1 vCPU / 2 GiB target plus HTTP probes using the encrypted
   remote backend. Confirm the live template before deploying E5.
6. Manually dispatch CD with the exact successful CI commit SHA and signed
   image digest; it changes the candidate to ragdocs-v3 and Terra.
7. At 0% production traffic, call /health, /warmup, and a real /query through
   the candidate label.
8. Progress 10% → 50% → 100%, verifying each weight; restore the captured
   stable revision on failure or cancellation.
9. Retain ragdocs through the observation window and delete it only through an
   explicit maintainer operation.

Example Azure-labelled retrieval run:

~~~bash
uv run python scripts/evaluate_retrieval.py \
  --backend azure \
  --index-name ragdocs-v3 \
  --golden eval/azure-golden.jsonl \
  --model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
~~~

The Azure evaluator matches expected_source and is therefore a source-level
smoke, not a chunk/page relevance metric. Build eval/azure-golden.jsonl from
manually labelled source names/questions before treating the result as corpus evidence.

## CI/CD and supply chain

Pull requests run the Python quality gate, Terraform formatting/validation,
filesystem/IaC/secret scanning, and a deployable-image scan. A main-branch
build:

1. builds and pushes one immutable SHA tag;
2. scans that exact digest for HIGH/CRITICAL findings;
3. generates a CycloneDX SBOM;
4. attests the same digest with its CycloneDX SBOM;
5. uploads the evidence, promotes latest, and only then creates the final
   keyless deployment-authorization signature.

Manual workflow dispatch runs quality checks only; only a successful main
`push` publishes the push-provenance image accepted by CD. CD is a manual
promotion step that requires an exact 40-character main commit
and sha256 digest. It verifies that the immutable SHA tag matches the digest and
that both Cosign's signature and CycloneDX attestation carry matching workflow,
ref, trigger, and commit claims before preserving
the prior revision, creating the candidate, and delegating
traffic/rollback to [scripts/deploy_canary.sh](scripts/deploy_canary.sh).

Azure login intentionally retains the existing long-lived
AZURE_CREDENTIALS service-principal JSON for this interview lab. Production
should use a protected GitHub Environment, federated identity, and a narrower
role.

The CD job targets the `stg` GitHub Environment. Create that environment and
configure its required reviewer before the first deployment; merely naming an
environment in YAML does not add approval protection to the current repository.

The Terraform configuration uses an Azure Storage backend and models the existing Container App topology,
including the Datadog sidecar and out-of-band secret references. It does not
put current application secret values in source or outputs. Treat it as
reconciliation/import-oriented IaC; for a fresh environment, create the named
Container App secrets securely before applying references, or use the guarded
setup script and then import/reconcile state.

Because Terraform creates the one-year Service Principal password, that value
is stored in Terraform state even though it is neither printed nor exposed as
an output. Initialize the declared backend with a protected Azure Storage
account/container/key; never use or commit local state for this configuration.

## Security and operational limits

Implemented controls include bounded requests, privacy-preserving logs, pinned
model/dependencies/base images/actions, a non-root offline-model image,
dependency and image scanning, SBOM generation/attestation, signature verification, digest deployment,
and rollback traps.

Known limits are equally important:

- the FastAPI application has no built-in end-user authentication or rate
  limiter, so a public endpoint must not expose sensitive corpora;
- retrieved documents are untrusted prompt input;
- each question and retrieved chunk is sent to OpenAI for generation, and full
  context text is returned to the API caller; `store=false` does not remove
  these deliberate processing/disclosure boundaries;
- the Search service currently uses an API key and has public network access;
- the Azure Student deployment is free/low-resource and has no production SLA;
- scale-to-zero saves cost but creates model cold starts;
- a health check cannot measure semantic answer quality, so the canary also
  runs a fixed full-path query; production should add p95/5xx/cost/SLO gates;
- Datadog sync/events skip when optional credentials are absent;
- repository policy still needs branch/ruleset enforcement on GitHub.

See [SECURITY.md](SECURITY.md) for reporting and trust-boundary details.

## Current Azure snapshot vs 3.0 target

Read-only Azure/portal inspection on 2026-08-13 produced this evidence:

| Area | Observed live 2.x | Local 3.0 target |
|---|---|---|
| App container | 0.5 vCPU / 1 GiB | 1 vCPU / 2 GiB |
| Scale | min 0 / max 1 | min 0 / max 1 |
| Revisions | Multiple | Multiple |
| Embedding/index | legacy ragdocs, 469 documents | pinned E5 + ragdocs-v3 |
| Generator | gpt-5.4-mini | gpt-5.6-terra, low reasoning |
| Datadog sidecar | 0.5 vCPU / 1 GiB, mutable latest tag | same allocation, pinned digest |
| Probes | TCP | HTTP startup/readiness/liveness |

The current Search service is Free tier with one replica/partition. These facts
describe the dated inspected environment, not a guarantee about future state.
No Azure key or secret value was retrieved during that audit.

## Evaluation roadmap

Before claiming production-quality improvement:

1. label 60–100 questions by ZH/JA/EN, fact/multi-hop/no-answer, source and page;
2. compare keyword-only, vector-only, hybrid E5, and optional reranking under
   identical chunks/top K;
3. record Recall@K, MRR, nDCG, page/source hit rate and no-answer false positives;
4. separately score answer correctness, faithfulness, citation precision/recall,
   refusal accuracy and language consistency;
5. record image size, RSS, cold/warm p50/p95, tokens, cost/query and error rate;
6. manually review samples from any LLM-as-judge evaluation.

Do not publish an unmeasured “accuracy improved by X%” claim.

## 日本語要約

3.0 は Azure Container Apps 上で動く多言語 RAG のローカル
リリース候補です。固定 revision の multilingual-E5、バージョン付き
ragdocs-v3、token-aware chunk、Azure AI Search hybrid retrieval、
gpt-5.6-terra の Structured Outputs、評価用 fixture、署名済み digest と
ロールバック可能な canary を一つの再現可能なプロジェクトとしてまとめています。
現在の Azure 2.x 環境とは明確に分離されており、クラウド移行と公開リリースは
maintainer が確認後に実行します。

## Release state

Version 3.0.0 is a breaking data-plane release because the embedding space and
index change. A valid release requires the version, Git tag, image digest,
model revision, index name, eval report, and deployment revision to refer to
the same source commit.

The repository owner performs the final push, GitHub Release, index migration,
and Azure deployment after reviewing the local commit/tag.

## License and responsible use

The code is an interview/learning project. Confirm the licenses and data-use
rights of every ingested document and model before adapting it for another
environment.
