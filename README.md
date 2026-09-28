# Serverless Multilingual RAG on Azure

[![CI](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml)
[![Security](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB.svg)](https://www.python.org/)
[![Version 3.2.0](https://img.shields.io/badge/version-3.2.0-6f42c1.svg)](#configuration-reference)

Cost-optimized serverless multilingual Retrieval-Augmented Generation (RAG) service on Azure Container Apps: local multilingual embeddings on ONNX Runtime, Azure AI Search hybrid retrieval with semantic reranking, and OpenAI Structured Outputs — sized to run inside Azure's free tiers.

[English](#english) | [中文](#中文) | [日本語](#日本語)

**Project video:** [Watch the 30-second Japanese introduction](assets/videos/rag-launch-ja-30s.mp4) · Japanese narration · 1080p / 60 fps

| 3.2.0 snapshot | Status |
|---|---|
| Release | [v3.2.0](https://github.com/workHMZ/aca-ghcr-cicd-lab/releases/tag/v3.2.0) · Python 3.14.7 |
| Deployment | Azure Container Apps · Japan East · v3.2.0 (verified 2026-09-27) |
| Verification | **123 tests passed · 91.74% coverage** (2026-09-27) |
| Runtime target | Application **0.5 vCPU / 1 GiB**; **1 vCPU / 2 GiB** including Datadog sidecar |
| Retrieval benchmark | **96% / 98% Page Hit Rate@1 / Page Hit Rate@3 · MRR@10 0.966667** (2026-09-26) |
| Cold start, initial 3.2 image | **21.255 s median** · 3 runs, 20.263–23.191 s (2026-09-27) |

---

<details>
<summary>Project structure</summary>

```text
├── app/
│   ├── config.py                          # Validated Pydantic runtime settings
│   ├── model_manifest.py                  # Pinned model revision + SHA-256 of every file, verified downloader
│   ├── embed.py                           # E5 query/passage embeddings on ONNX Runtime (int8, 384-dim)
│   ├── chunking.py                        # Outline-aware, cross-page chunking with TOC detection
│   ├── guardrails.py                      # Answer cache and per-minute/per-day query budget
│   ├── search_client.py                   # Cached Azure AI Search client
│   ├── telemetry.py                       # Metadata-only Datadog workflow / stage / LLM spans
│   ├── main.py                            # Async FastAPI: retrieval, reranker floor, structured generation
│   └── __main__.py                        # Container entrypoint (ddtrace-run only when tracing is on)
├── eval/
│   ├── golden_corpus.jsonl                # 50 labelled zh/ja/en questions about the real corpus (page-level)
│   ├── corpus.jsonl                       # Synthetic multilingual fixture (offline CI regression)
│   └── golden.jsonl                       # Labels for the synthetic fixture
├── scripts/
│   ├── create_index.py                    # Versioned index (HNSW + semantic + zh/ja lexical fields)
│   ├── ingest.py                          # PDF/MD/TXT → chunks → embeddings → index (idempotent, --glob)
│   ├── clear_index.py                     # Confirmed purge of every document in an index
│   ├── evaluate_retrieval.py              # Page Hit Rate@K / MRR: local fixture or Azure ablation per mode
│   ├── smoke_container.sh                 # Offline boot under 0.5 vCPU / 1 GiB with memory budget
│   ├── deploy_canary.sh                   # Progressive ACA canary rollout & automated rollback
│   ├── test_api.py                        # API smoke testing
│   ├── verify.sh                          # Local quality gate (Ruff, Mypy, pip-audit, Pytest)
│   ├── setup-azure.sh                     # One-time bootstrap (capped logs, free-tier sizing)
│   ├── sync_datadog_catalog.sh            # Datadog Service Catalog sync
│   └── send_datadog_dora_deployment.sh    # Datadog DORA deployment tracking
├── .github/workflows/
│   ├── ci.yml                             # Quality gates → container smoke → image → SBOM → Cosign
│   ├── cd.yml                             # Signature verification → canary deployment → rollback
│   └── security.yml                       # CodeQL, filesystem/IaC/secret and image scanning
├── terraform/                             # Container Apps, Log Analytics and CI identity as code
├── data/                                  # Source documents (git-ignored)
├── service.datadog.yaml                   # Datadog Service Catalog metadata
└── pyproject.toml                         # Unified project configuration & dependencies
```

</details>

---

<a id="english"></a>

## English

### Overview & Core Value

Production RAG usually brings recurring embedding API costs, uneven retrieval across languages, and risky deployments. This project shows how to avoid all three on a budget of zero Azure spend:

- **Local multilingual embeddings on ONNX Runtime**: `multilingual-e5-small` (pinned revision, SHA-256-verified int8 ONNX export) with asymmetric `query:` / `passage:` prefixes. No embedding API, no PyTorch in the image, and a 0.5 vCPU / 1 GiB application container.
- **Structure-aware retrieval**: outline-aligned, cross-page chunks with heading context, table-of-contents pages removed, Chinese/Japanese word-level BM25 fused with HNSW vectors (RRF) and the Azure AI Search semantic ranker.
- **Grounded structured outputs**: OpenAI Responses API returns validated citations; low-relevance contexts are dropped before generation, and off-topic questions skip the LLM entirely.
- **Public-endpoint cost guardrails**: answer cache plus per-minute and per-day query budgets protect the OpenAI bill and the free semantic-ranker quota.
- **Supply chain security & canary releases**: exact-digest Trivy scans, CycloneDX SBOM, Cosign keyless signing verified by CD, and progressive traffic shifting (0% → 10% → 50% → 100%) with automated rollback.
- **Measured quality**: a 50-question labelled benchmark on the real corpus evaluates every retrieval mode on Azure; a synthetic fixture gates CI offline.

---

### 3.0 → 3.2

3.2 retains the v4 index and ONNX int8 runtime, adds review fixes and metadata-only LLM monitoring, and is measured below against the historical 3.0 baseline.

| Area | 3.0 | 3.2 |
|---|---|---|
| Embedding runtime | PyTorch fp32 | ONNX int8 |
| Application + sidecar allocation | 1.5 vCPU / 3 GiB | 1 vCPU / 2 GiB (tested) |
| Datadog | APM + DORA | APM + DORA + workflow, retrieval and LLM token traces |
| Page Hit Rate@1 / Page Hit Rate@3 | 84% / 94% | **96% / 98%** |
| MRR@10 | 0.900 | **0.966667** |
| Cold start | ~60 s (historical) | **21.255 s median** (3 runs: 20.263–23.191 s) |

Measured 2026-09-26: 50 labelled questions (zh 25 / ja 12 / en 13), the 521-chunk Java corpus in `ragdocs-v4`, and the current semantic retrieval path. Page Hit Rate measures whether a relevant page appears, not answer correctness. In the same run, BM25 / vector / hybrid / semantic Hit@1 were **80% / 82% / 84% / 96%**.

Cold start measured 2026-09-27 with the initial 3.2 image before the privacy-only rebuild: Japan East ACA, Python 3.14.7, application 0.5 vCPU / 1 GiB plus the same-sized Datadog sidecar. Each request started after replica count reached zero; timed to the first HTTP 200 from `/health`. `/ready` passed within 0.050 s afterward. The test used a 30 s scale-down cooldown; image caches were not cleared, and the sidecar used an invalid placeholder credential. The historical 3.0 value came from system logs, so this is not a controlled A/B speedup claim or a Datadog delivery test.

New in 3.2: fail closed on semantic failures, require a read-only Search key, authenticate cache bypass, validate citations, make ingestion cleanup explicit, and configure Azure OIDC deployment.

---

### Azure Free-Tier Fit

| Service | Free allowance | How this project stays inside it |
|---|---|---|
| Container Apps (Consumption) | 180,000 vCPU-s, 360,000 GiB-s, 2 M requests / month | `min_replicas = 0`, 0.5 vCPU / 1 GiB → ~100 replica-hours (half with the optional Datadog sidecar); each cold visit bills at least the 300 s cooldown, i.e. ~1,200 cold visits / month |
| Azure AI Search (Free) | 50 MB, 3 indexes, semantic ranker monthly free allowance | v4 index uses 3.2 MB (vectors are `stored=False`); cache + daily budget protect the semantic quota, and semantic errors/missing scores fail closed before generation (free allowance exhaustion returns HTTP 402 from Search) |
| Log Analytics | 5 GB ingestion / month, 31-day retention | 30-day retention; Terraform and `setup-azure.sh` set a 0.16 GB/day best-effort ingestion cap (overshoot can still be billed); Azure SDK request logging is silenced in the app |
| GitHub Container Registry | free for public images | immutable digests, signed |

Cost Management shows **¥0** for the project resource group from June to September 2026. The only metered dependency is OpenAI, which is bounded by the answer cache, `QUERY_RATE_LIMIT_PER_MINUTE`, `QUERY_DAILY_LIMIT`, and the reranker floor (off-topic questions never reach the LLM). Datadog APM stays available as an experimental opt-in (`enable_datadog_sidecar = true`; CD turns tracing on automatically when the Agent sidecar is present). It doubles the application allocation from 0.5 vCPU / 1 GiB to 1 vCPU / 2 GiB, halving the runtime covered by the free grant.

---

### End-to-End Pipelines

#### 1. Data Ingestion Pipeline

```mermaid
flowchart LR
    Docs["Documents<br/>(PDF / MD / TXT, --glob)"] --> TOC["Drop table-of-contents pages"]
    TOC --> Chunk["Outline-aware chunks<br/>(≤384 tokens, cross-page, heading path)"]
    Chunk --> Embed["E5 int8 on ONNX Runtime (passage:)<br/>384-dim normalized vectors"]
    Embed --> Index[("Azure AI Search ragdocs-v4<br/>HNSW + zh/ja lexical fields + semantic title")]
```

#### 2. Online Query Pipeline

```mermaid
flowchart LR
    Client["Client"] --> API["FastAPI<br/>rag.query"]
    API --> Guard["Cache + query budget"]
    Guard -- "Cache hit" --> Response["Answer + citations"]
    Guard -- "Cache miss" --> QVec["E5 query embedding<br/>rag.embed"]
    QVec --> Search["Azure AI Search<br/>Hybrid + semantic · rag.search"]
    Search --> Evidence{"Evidence passes floor?"}
    Evidence -- "Yes" --> LLM["OpenAI Responses<br/>rag.generate"]
    Evidence -- "No: insufficient evidence" --> Response
    LLM --> Response
    API -. "Workflow + stage spans" .-> Agent["Datadog Agent sidecar<br/>Same replica · :8126"]
    Agent -.-> DD["Datadog<br/>APM + LLM Observability"]
```

**Datadog: APM + LLM Observability.** `rag.query` groups the stages below and sends metadata through the existing Agent sidecar at `127.0.0.1:8126`. Live delivery was verified on 2026-09-27: all four spans, stage latency and LLM input/output tokens appeared under `serverless-rag-api`, version `3.2.0`, without question or answer text. The optional DORA deployment event was skipped because GitHub `DD_API_KEY` is not configured.

| Trace | Recorded data |
|---|---|
| `rag.query` | Total duration, cache hit, no evidence, refusal and groundedness flags |
| `rag.embed` / `rag.search` | Stage duration, retained context count and semantic score range |
| `rag.generate` | Model, duration, input/output/total, cached-input and reasoning tokens |

Cache hits skip the model and do not count tokens again. Questions, answers and document text are not captured. These metrics diagnose behavior; labelled evaluation measures retrieval quality.

#### 3. Secure CI/CD Canary Pipeline

```mermaid
flowchart LR
    PR["PR / Main Push"] --> Lint["Quality Gate<br/>Ruff + Mypy + Pytest + Audit + Retrieval regression"]
    Lint --> Smoke["Container smoke test<br/>offline, 0.5 vCPU / 1 GiB"]
    Smoke --> Build["Build Immutable Image<br/>(SHA Digest)"]
    Build --> Scan["Trivy Security Scan"]
    Scan --> SBOM["Generate SBOM &<br/>Cosign Keyless Signature"]
    SBOM --> Canary["ACA Canary (0%)<br/>Health & Real Query"]
    Canary --> Promote["Traffic Progression<br/>10% → 50% → 100%"]
    Canary -. "Failure" .-> Rollback["Automated Rollback<br/>to Previous Revision"]
    Promote -. "Success" .-> DORA["Datadog DORA<br/>deployment event"]
```

---

### Key Features

1. **Multilingual hybrid retrieval**
   - Fixed model revision `intfloat/multilingual-e5-small@614241f...`; the ONNX file and tokenizer are SHA-256-pinned in `app/model_manifest.py`.
   - Outline-aware chunking: numbered/Markdown/chapter headings drive cut points, sub-points stay with their question, chunks may span pages, and chunk text is sliced from the source (never re-decoded).
   - Index `ragdocs-v4`: cosine HNSW, semantic configuration with a `title` field, word-segmented Chinese/Japanese lexical copies, page ranges, and `embeddingVariant` on every chunk.
2. **Grounded synthesis & safety**
   - Retrieved chunks are wrapped as untrusted evidence; Pydantic validates response structure; the app checks citation indices. Groundedness is model-reported, not independently fact-checked. Retrieval thresholds and required citations reduce unsupported answers.
   - Contexts under the semantic reranker floor are dropped; if none remain, the service answers "insufficient evidence" without calling the LLM.
3. **Cost guardrails & observability**
   - TTL answer cache (only an authenticated `X-Canary-Token` bypasses it), per-minute token bucket, and per-UTC-day ceiling with `429 Retry-After`.
   - Per-request `embedding_ms` / `search_ms` / `generation_ms` timings in the response and structured JSON logs; Datadog APM, metadata-only LLM traces and DORA deployment events.
4. **Evaluation**
   - `eval/golden_corpus.jsonl` measures the real index per retrieval mode and prints a reranker-floor calibration; the synthetic fixture remains the fast offline CI gate.

---

<details>
<summary>Runbook & configuration</summary>

### Runbook

#### 1. Local Setup

```bash
# Install dependencies with locked environment
uv sync --frozen --dev

# Configure environment variables
cp .env.example .env
# Edit .env and supply AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_QUERY_KEY, OPENAI_API_KEY
```
The embedding model is downloaded on first use into `~/.cache/serverless-rag` and verified against the pinned SHA-256 values (container images bake it in and run offline).

#### 2. Index Management & Data Ingestion

```bash
# Create the versioned Azure AI Search index
uv run python scripts/create_index.py --index-name ragdocs-v4

# Preview chunking without embedding or uploading
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --dry-run

# Ingest only the public documents you select
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --index-name ragdocs-v4
```
Everything ingested is returned verbatim by a public API: select files with `--glob` and never point ingestion at private notes. Re-ingestion is idempotent and prunes stale chunks per source.

#### 3. Run Locally & Probe API

```bash
# Start FastAPI application
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Probe health & readiness
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready

# Test query endpoint
curl -fsS http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  --data '{"question": "How does HashMap handle collisions in Java 8?", "top_k": 3}'
```

#### 4. Retrieval Evaluation

```bash
# Real corpus on Azure: ablation across retrieval modes (uses 50 semantic-ranker requests per semantic run)
uv run python scripts/evaluate_retrieval.py --backend azure --index-name ragdocs-v4 \
  --mode semantic --mode hybrid --mode vector --mode bm25

# Offline model comparison on the synthetic fixture (the CI regression gate)
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --model intfloat/multilingual-e5-small --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```
The Azure run also prints `reranker_calibration`: how many labelled and unlabelled top-k contexts each candidate floor would keep. The served floor of 1.5 keeps every labelled hit (lowest 1.90) while off-topic questions peak between 0.5 and 1.6.

`--backend local` reads only `eval/corpus.jsonl` and `eval/golden.jsonl`; the pinned E5 model runs through the production ONNX encoder, other models through sentence-transformers. Result on the bundled fixture (9 passages, 6 queries, 2 each in `en` / `ja` / `zh`), with dated baselines and the current Linux run:

| Model | Page Hit Rate@1 | Page Hit Rate@3 | MRR | `ja` Page Hit Rate@1 |
|---|---|---|---|---|
| `all-MiniLM-L6-v2` (English-only baseline) | 0.833 | 1.000 | 0.917 | 0.500 |
| `multilingual-e5-small`, fp32 (3.0) | 1.000 | 1.000 | 1.000 | 1.000 |
| `multilingual-e5-small`, ONNX int8 (3.2, Linux recheck) | **1.000** | **1.000** | **1.000** | **1.000** |

The 3.2 ONNX row was rerun on Linux on 2026-09-26; the MiniLM and 3.0 fp32 rows are historical baselines. All six current queries ranked the expected passage first. Near ties can still flip across quantized CPU kernels, so CI requires every expected passage in the top 3 and MRR ≥ 0.9. This nine-passage/six-query fixture is a regression gate, not production answer accuracy.

#### 5. Local Quality Gate

```bash
# Run full verification (formatting, linting, type checks, dependency audit, coverage)
# `uv run` puts .venv/bin on PATH, exactly as the CI job does.
uv run bash scripts/verify.sh
```
This is the same script CI executes: `ruff format --check`, `ruff check`, `mypy`, `pip-audit` against the exported runtime lock, and `pytest` with an 80% coverage floor. CI additionally boots the built image with `--network none --cpus 0.5 --memory 1g` (`scripts/smoke_container.sh`) and fails if the model cannot load offline or memory exceeds 900 MiB.

#### 6. Rollback Procedure
If canary checks fail, the pipeline restores 100% traffic to the stable revision automatically. After a successful rollout every other revision is deactivated (inactive revisions cost nothing and stay available). To restore traffic manually:
```bash
az containerapp revision activate --name <app-name> --resource-group <resource-group> --revision <stable-revision-name>
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision-weight <stable-revision-name>=100
```

---

### Configuration Reference

| Environment Variable | Default Value | Description |
|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | - | Azure AI Search service endpoint URL |
| `AZURE_SEARCH_QUERY_KEY` | - | Read-only Azure AI Search query key (admin scripts use `AZURE_SEARCH_ADMIN_KEY`) |
| `AZURE_SEARCH_INDEX_NAME` | `ragdocs-v4` | Index the running application queries |
| `AZURE_SEARCH_INDEX_NAME_V4` | `ragdocs-v4` | Index targeted by `scripts/` (create, ingest, clear, evaluate) |
| `SEARCH_MIN_RERANKER_SCORE` | `1.5` | Semantic ranker floor (0–4) below which contexts are dropped |
| `OPENAI_API_KEY` | - | OpenAI API authentication key |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Generation model ID |
| `OPENAI_REASONING_EFFORT` | `low` | Reasoning effort budget for generation |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_REVISION` | `intfloat/multilingual-e5-small` / `614241f...` | Defaults from the manifest; mismatches fail startup. Do not override in deployment |
| `EMBEDDING_VARIANT` | `onnx-qint8` | ONNX file served (`onnx-fp32` needs ~0.9 GB more memory); must match the index |
| `EMBEDDING_MODEL_PATH` | - | Pre-downloaded model directory (the image sets it); unset uses `~/.cache/serverless-rag` |
| `EMBEDDING_OFFLINE` | `false` | Forbid model downloads at runtime (`HF_HUB_OFFLINE` is also accepted) |
| `EMBEDDING_THREADS` | `1` | ONNX Runtime intra-op threads; keep ≤ the replica's vCPU quota |
| `EMBEDDING_BATCH_SIZE` | `16` | Batch size for passage encoding |
| `ANSWER_CACHE_TTL_SECONDS` | `3600` | Answer cache lifetime (0 disables) |
| `QUERY_RATE_LIMIT_PER_MINUTE` / `QUERY_DAILY_LIMIT` | `20` / `500` | Uncached query budget per replica (0 disables) |
| `DD_TRACE_ENABLED` | `false` | Wrap uvicorn with `ddtrace-run`; CD sets it from the presence of the Datadog Agent sidecar (repository variable overrides) |
| `DD_LLMOBS_ENABLED` | `false` | Enable LLM spans; CD follows `DD_TRACE_ENABLED`. Existing Agent sidecar, no app-side Datadog key |
| `DD_LLMOBS_ML_APP` | `serverless-rag-api` | LLM application name; entrypoint disables automatic OpenAI content capture, Agentless mode stays off |
| `SEARCH_TOP_K_DEFAULT` / `SEARCH_TOP_K_MAX` | `5` / `10` | Default and maximum `top_k` |

---

</details>

### Design Decisions & Trade-offs

- **ONNX int8 vs. PyTorch fp32**: the pinned revision already publishes an int8 ONNX export. Serving it removes PyTorch from the image, and the int8 session adds ~0.3 GB of resident memory versus ~1.2 GB for fp32 (the whole embedding runtime is ~0.45 GB on Linux), which is what makes 0.5 vCPU / 1 GiB replicas possible. On the benchmark the two are equal within one query; the trade-off is that the index must be embedded by the same variant, which `embeddingVariant` enforces.
- **Outline-aware chunking vs. page chunking**: interview-style documents are lists of questions. Cutting at top-level headings keeps each answer whole, heading paths give continuation chunks context, and the TOC detector (headings that reappear later) removes pages that match everything but answer nothing. Heading-level recovery from plain PDF text is heuristic; when it fails the chunker falls back to line and sentence boundaries.
- **Lexical copies per language vs. one analyzer**: `standard.lucene` splits Chinese into single characters. Hidden `contentZh` / `contentJa` copies add word-level BM25 at little storage cost (the whole v4 index is 3.2 MB); the semantic ranker still reads the language-neutral `content`.
- **Reranker floor vs. always generating**: dropping contexts below 1.5 avoids feeding the LLM noise and skips generation for off-topic questions. The threshold is calibrated from the benchmark and printed by every Azure evaluation run.
- **In-process guardrails vs. API Management**: an answer cache and token bucket inside the app cost nothing and are exact with `max_replicas = 1`; a multi-replica or multi-region deployment would move them to Azure API Management or a shared store.
- **Serverless scale-to-zero vs. cold start**: idle costs nothing; a visit after idleness pays scheduling, image pull, and model load. The ONNX image preloads the model in the background so `/ready` flips as soon as queries can be served. A latency-sensitive deployment would set `min_replicas = 1`, which leaves the free grant.
- **Index isolation (`ragdocs-v4`)**: every chunk carries `embeddingModel`, `embeddingRevision`, and `embeddingVariant`; the service rejects mismatched results, so a stale index fails loudly instead of returning wrong neighbours.
- **Bash canary vs. Operator**: progressive delivery is a reviewable shell script (`scripts/deploy_canary.sh`), keeping revision state and rollback logic transparent in workflow logs.

---

<a id="中文"></a>

## 中文

### 项目概述与核心价值

在生产环境落地 RAG 时，通常要面对持续的 Embedding API 费用、跨语言检索不稳定、以及发布风险。本项目演示如何在 **Azure 零花费** 的前提下同时解决这三点：

- **基于 ONNX Runtime 的本地多语言向量化**：`multilingual-e5-small`（锁定版本，SHA-256 校验的 int8 ONNX 导出）+ `query:` / `passage:` 非对称前缀。无 Embedding API 费用、镜像中不含 PyTorch，应用容器仅需 0.5 vCPU / 1 GiB。
- **结构感知检索**：按题目大纲跨页切块并附带标题上下文，剔除目录页；中文/日文分词级 BM25 与 HNSW 向量经 RRF 融合，再由 Azure AI Search 语义重排序。
- **结构化可信生成**：OpenAI Responses API 输出带校验引用的 JSON；低相关上下文在生成前被丢弃，离题问题直接跳过大模型调用。
- **公开接口成本护栏**：答案缓存 + 每分钟/每日查询预算，保护 OpenAI 账单与免费语义重排额度。
- **供应链安全与金丝雀发布**：按镜像摘要执行 Trivy 扫描、CycloneDX SBOM、Cosign 无密钥签名（CD 校验签名），0% → 10% → 50% → 100% 灰度放量与自动回滚。
- **可量化的质量**：基于真实语料的 50 题标注评测集在 Azure 上逐检索模式评估；合成评测集作为 CI 离线门禁。

---

### 3.0 → 3.2

3.2 保留 v4 索引与 ONNX int8 运行时，加入审查修复和仅采集运行指标的 LLM 监控。下表使用本轮实测对照 3.0 历史基线。

| 项目 | 3.0 | 3.2 |
|---|---|---|
| 向量化运行时 | PyTorch fp32 | ONNX int8 |
| 应用 + 边车资源 | 1.5 vCPU / 3 GiB | 1 vCPU / 2 GiB（实测配置） |
| Datadog | APM + DORA | 增加问答链路、检索与 LLM token 追踪 |
| Page Hit Rate@1 / Page Hit Rate@3 | 84% / 94% | **96% / 98%** |
| MRR@10 | 0.900 | **0.966667** |
| 冷启动 | 约 60 秒（历史记录） | **中位数 21.255 秒**（3 轮：20.263–23.191 秒） |

实测日期 2026-09-26：50 道标注题（中文 25 / 日文 12 / 英文 13），`ragdocs-v4` 中的 Java 资料共 521 个片段，使用当前语义检索路径。Page Hit Rate 表示是否命中相关页面，不是答案准确率。同轮 BM25 / 向量 / 混合 / 语义重排的 Hit@1 分别为 **80% / 82% / 84% / 96%**。

冷启动于 2026-09-27 使用隐私修订前的初版 3.2 镜像实测：日本东部 ACA，Python 3.14.7，应用 0.5 vCPU / 1 GiB，加同等资源的 Datadog 边车。每轮先确认副本数为零，再从发起请求计时至 `/health` 首次返回 HTTP 200；随后 0.050 秒内 `/ready` 均通过。测试缩容冷却期为 30 秒，未清空镜像缓存，边车使用无效占位凭据。3.0 的历史值来自系统日志，因此不能据此声称严格 A/B 加速比例，也不代表 Datadog 上报已经验证。

3.2 新增：语义失败时停止生成、Search 只读密钥、缓存绕过鉴权、引用检查、显式摄取清理，以及 Azure OIDC 部署配置。

---

### Azure 免费额度适配

| 服务 | 免费额度 | 本项目如何控制在额度内 |
|---|---|---|
| Container Apps（Consumption） | 每月 180,000 vCPU 秒、360,000 GiB 秒、200 万次请求 | `min_replicas = 0`，0.5 vCPU / 1 GiB → 约 100 副本小时（启用可选 Datadog 边车时减半）；每次冷启动访问至少计费 300 秒冷却期，约可支撑每月 1,200 次冷访问 |
| Azure AI Search（Free） | 50 MB、3 个索引、语义重排每月免费额度 | v4 索引仅占 3.2 MB（向量 `stored=False`）；缓存 + 每日预算保护语义额度，语义失败或缺少评分时停止生成；免费额度耗尽时 Search 返回 HTTP 402 |
| Log Analytics | 每月 5 GB 摄取、31 天保留 | 保留 30 天；Terraform 与 `setup-azure.sh` 设置每日 0.16 GB 尽力摄取上限（超额仍可能计费）；应用内关闭 Azure SDK 请求日志 |
| GitHub Container Registry | 公开镜像免费 | 不可变摘要 + 签名 |

Cost Management 显示本项目资源组 2026 年 6–9 月花费为 **¥0**。唯一计费的外部依赖是 OpenAI，由答案缓存、`QUERY_RATE_LIMIT_PER_MINUTE`、`QUERY_DAILY_LIMIT` 与重排分数下限共同约束（离题问题不会到达大模型）。Datadog APM 保留为试验性可选项（`enable_datadog_sidecar = true`；检测到 Agent 边车时 CD 会自动开启追踪），启用边车后整副本从 0.5 vCPU / 1 GiB 增至 1 vCPU / 2 GiB，免费额度可覆盖的运行时长减半。

---

### 端到端核心链路

#### 1. 数据摄取链路 (Data Ingestion Pipeline)

```mermaid
flowchart LR
    Docs["原始文档<br/>(PDF / MD / TXT，--glob 选择)"] --> TOC["剔除目录页"]
    TOC --> Chunk["按大纲切块<br/>(≤384 tokens，可跨页，带标题路径)"]
    Chunk --> Embed["E5 int8 + ONNX Runtime (passage:)<br/>384 维归一化向量"]
    Embed --> Index[("Azure AI Search ragdocs-v4<br/>HNSW + 中日文词法字段 + 语义标题")]
```

#### 2. 在线检索与生成链路 (Online Query Pipeline)

```mermaid
flowchart LR
    Client["用户"] --> API["FastAPI<br/>rag.query"]
    API --> Guard["缓存 + 查询预算"]
    Guard -- "缓存命中" --> Response["答案 + 引用"]
    Guard -- "未命中" --> QVec["E5 问题向量化<br/>rag.embed"]
    QVec --> Search["Azure AI Search<br/>混合检索 + 语义重排 · rag.search"]
    Search --> Evidence{"证据通过分数门槛？"}
    Evidence -- "是" --> LLM["OpenAI Responses<br/>rag.generate"]
    Evidence -- "否：返回证据不足" --> Response
    LLM --> Response
    API -. "问答与各阶段追踪" .-> Agent["Datadog Agent 边车<br/>同一副本 · :8126"]
    Agent -.-> DD["Datadog<br/>APM + LLM Observability"]
```

**Datadog：APM + LLM 监控。** `rag.query` 串起以下步骤，通过现有 Agent 边车的 `127.0.0.1:8126` 上报运行指标。2026-09-27 已在后台确认 `serverless-rag-api`、版本 `3.2.0` 的四段调用链、分段耗时和模型输入/输出 token，未采集问题或答案正文。GitHub 未配置 `DD_API_KEY`，本次可选的 DORA 发布事件跳过。

| 追踪记录 | 展示数据 |
|---|---|
| `rag.query` | 总耗时、缓存命中、证据不足、拒答与 groundedness 标记 |
| `rag.embed` / `rag.search` | 分段耗时、保留片段数、语义分数范围 |
| `rag.generate` | 模型、耗时、输入/输出/总 token、缓存输入与推理 token |

缓存命中不调用模型、不重复累计 token；不采集问题、答案和文档正文。监控用于定位问题，检索质量仍由标注评测衡量。

#### 3. 安全 CI/CD 金丝雀发布链路 (Canary Delivery Pipeline)

```mermaid
flowchart LR
    PR["代码提交 / PR"] --> Lint["质量门禁<br/>Ruff + Mypy + Pytest + 依赖审计 + 检索回归"]
    Lint --> Smoke["容器冒烟测试<br/>断网、0.5 vCPU / 1 GiB"]
    Smoke --> Build["构建不可变镜像<br/>(SHA 摘要)"]
    Build --> Scan["Trivy 镜像安全扫描"]
    Scan --> SBOM["生成 SBOM 物料清单<br/>Cosign 无密钥签名"]
    SBOM --> Canary["ACA 金丝雀发布 (0% 流量)<br/>健康检查与真实 Query"]
    Canary --> Promote["阶梯放量<br/>10% → 50% → 100%"]
    Canary -. "检测失败" .-> Rollback["自动回滚<br/>切回上一稳定版本"]
    Promote -. "发布成功" .-> DORA["Datadog DORA<br/>部署事件"]
```

---

### 核心技术特性

1. **多语言混合检索**
   - 锁定模型版本 `intfloat/multilingual-e5-small@614241f...`，ONNX 文件与分词器的 SHA-256 固定在 `app/model_manifest.py`。
   - 结构感知切块：编号/Markdown/章节标题决定切分点，子要点留在所属题目内，块可跨页，块文本直接从原文切片（不经分词器解码还原）。
   - `ragdocs-v4` 索引：余弦 HNSW、带 `title` 字段的语义配置、中日文分词词法副本、页码区间，每个块记录 `embeddingVariant`。
2. **结构化生成与防注入**
   - 检索内容作为不可信证据隔离；Pydantic 校验响应结构，应用校验引用编号。可信度由模型自报，不等于独立事实核验；检索阈值与强制引用用于降低无依据回答风险。
   - 低于语义重排下限的上下文被丢弃；若全部被丢弃则直接返回"资料不足"，不调用大模型。
3. **成本护栏与可观测性**
   - TTL 答案缓存（仅有效的 `X-Canary-Token` 可绕过）、每分钟令牌桶与每日（UTC）上限，超限返回 `429 Retry-After`。
   - 响应与结构化 JSON 日志中包含 `embedding_ms` / `search_ms` / `generation_ms` 分段耗时；Datadog APM、仅含运行指标的 LLM 追踪与 DORA 部署事件可选开启。
4. **评测体系**
   - `eval/golden_corpus.jsonl` 按检索模式评估真实索引，并输出重排下限校准数据；合成评测集继续作为快速的 CI 离线门禁。

---

<details>
<summary>操作手册与配置（展开）</summary>

### 运维手册 (Runbook)

#### 1. 本地环境初始化

```bash
# 使用 uv 安装锁定依赖
uv sync --frozen --dev

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 AZURE_SEARCH_ENDPOINT、AZURE_SEARCH_QUERY_KEY 与 OPENAI_API_KEY
```
向量模型首次使用时下载到 `~/.cache/serverless-rag` 并按固定的 SHA-256 校验（容器镜像在构建时内置模型并离线运行）。

#### 2. 索引创建与文档摄取

```bash
# 创建版本化的 Azure AI Search 索引
uv run python scripts/create_index.py --index-name ragdocs-v4

# 仅预览切块结果，不向量化也不上传
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --dry-run

# 只摄取你选定的公开文档
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --index-name ragdocs-v4
```
摄取的所有内容都会被公开 API 原样返回：请用 `--glob` 精确选择文件，切勿把私人笔记放进索引。重复摄取是幂等的，并会按来源清理过期块。

#### 3. 本地启动与接口验证

```bash
# 启动 FastAPI 服务
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# 探测健康与就绪探针
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready

# 验证 RAG 查询接口
curl -fsS http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  --data '{"question": "Java 中 HashMap 的工作原理是什么？", "top_k": 3}'
```

#### 4. 检索质量评测

```bash
# 在 Azure 上评测真实语料：各检索模式消融（每次语义模式运行消耗 50 次语义重排额度）
uv run python scripts/evaluate_retrieval.py --backend azure --index-name ragdocs-v4 \
  --mode semantic --mode hybrid --mode vector --mode bm25

# 在合成评测集上离线对比模型（CI 回归门禁）
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --model intfloat/multilingual-e5-small --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```
Azure 评测还会输出 `reranker_calibration`：每个候选下限在 top-k 中会保留多少标注命中与非标注结果。线上下限 1.5 保留了全部标注命中（最低 1.90），而离题问题的最高分在 0.5–1.6 之间。

`--backend local` 仅读取 `eval/corpus.jsonl` 与 `eval/golden.jsonl`；锁定的 E5 模型走线上同款 ONNX 编码器，其他模型走 sentence-transformers。内置评测集（9 条 passage、6 条 query，`en` / `ja` / `zh` 各 2 条）的历史基线与本轮 Linux 结果：

| 模型 | Page Hit Rate@1 | Page Hit Rate@3 | MRR | `ja` Page Hit Rate@1 |
|---|---|---|---|---|
| `all-MiniLM-L6-v2`（英语单语基线） | 0.833 | 1.000 | 0.917 | 0.500 |
| `multilingual-e5-small`，fp32（3.0） | 1.000 | 1.000 | 1.000 | 1.000 |
| `multilingual-e5-small`，ONNX int8（3.2，本轮 Linux 实测） | **1.000** | **1.000** | **1.000** | **1.000** |

3.2 ONNX 行于 2026-09-26 在 Linux 重跑，6 题全部 top-1 命中；MiniLM 与 3.0 fp32 行保留为历史基线。量化内核的近似并列仍可能换序，因此 CI 要求各语言 top-3 全部命中且 MRR ≥ 0.9。这个 9 段/6 题合成集只是回归门禁，不能当作生产答案准确率。

#### 5. 本地质量门禁检查

```bash
# 执行完整质检（代码格式、类型检查、依赖漏洞扫描、单元测试与覆盖率）
# uv run 会把 .venv/bin 加入 PATH，与 CI 中的执行方式一致。
uv run bash scripts/verify.sh
```
该脚本与 CI 完全相同：`ruff format --check`、`ruff check`、`mypy`、针对导出运行时锁文件的 `pip-audit`，以及 80% 覆盖率下限的 `pytest`。CI 还会以 `--network none --cpus 0.5 --memory 1g` 启动构建出的镜像（`scripts/smoke_container.sh`），若模型无法离线加载或内存超过 900 MiB 则失败。

#### 6. 异常回滚流程
金丝雀检查失败时，流水线会自动把 100% 流量切回稳定版本。放量成功后其余版本全部停用（停用的版本不计费且可随时恢复）。手动回滚：
```bash
az containerapp revision activate --name <app-name> --resource-group <resource-group> --revision <stable-revision-name>
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision-weight <stable-revision-name>=100
```

---

### 环境变量配置说明

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | - | Azure AI Search 服务终端地址 |
| `AZURE_SEARCH_QUERY_KEY` | - | 只读 Query Key；管理脚本单独使用 `AZURE_SEARCH_ADMIN_KEY` |
| `AZURE_SEARCH_INDEX_NAME` | `ragdocs-v4` | 在线服务查询的索引 |
| `AZURE_SEARCH_INDEX_NAME_V4` | `ragdocs-v4` | `scripts/`（建索引、摄取、清理、评测）操作的索引 |
| `SEARCH_MIN_RERANKER_SCORE` | `1.5` | 语义重排分数下限（0–4），低于该值的上下文被丢弃 |
| `OPENAI_API_KEY` | - | OpenAI API 鉴权密钥 |
| `OPENAI_MODEL` | `gpt-5.6-terra` | 答案生成模型 |
| `OPENAI_REASONING_EFFORT` | `low` | 生成模型推理预算 |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_REVISION` | `intfloat/multilingual-e5-small` / `614241f...` | 默认值来自 manifest，不匹配则启动失败；部署不覆盖 |
| `EMBEDDING_VARIANT` | `onnx-qint8` | 使用的 ONNX 文件（`onnx-fp32` 需多约 0.9 GB 内存），必须与索引一致 |
| `EMBEDDING_MODEL_PATH` | - | 预下载的模型目录（镜像内已设置）；留空使用 `~/.cache/serverless-rag` |
| `EMBEDDING_OFFLINE` | `false` | 运行时禁止下载模型（也接受 `HF_HUB_OFFLINE`） |
| `EMBEDDING_THREADS` | `1` | ONNX Runtime 算子内线程数，不应超过副本 vCPU 配额 |
| `EMBEDDING_BATCH_SIZE` | `16` | 段落向量化批大小 |
| `ANSWER_CACHE_TTL_SECONDS` | `3600` | 答案缓存有效期（0 为关闭） |
| `QUERY_RATE_LIMIT_PER_MINUTE` / `QUERY_DAILY_LIMIT` | `20` / `500` | 每副本未命中缓存的查询预算（0 为关闭） |
| `DD_TRACE_ENABLED` | `false` | 用 `ddtrace-run` 启动 uvicorn；CD 根据是否存在 Datadog Agent 边车自动设置（仓库变量可覆盖） |
| `DD_LLMOBS_ENABLED` | `false` | 开启 LLM 追踪；CD 跟随 `DD_TRACE_ENABLED`。沿用边车，应用无需 Datadog Key |
| `DD_LLMOBS_ML_APP` | `serverless-rag-api` | LLM 应用名称；入口关闭 OpenAI 自动正文采集，保持 Agent 模式 |
| `SEARCH_TOP_K_DEFAULT` / `SEARCH_TOP_K_MAX` | `5` / `10` | 默认与最大 `top_k` |

---

</details>

### 架构设计与权衡

- **ONNX int8 vs. PyTorch fp32**：锁定版本本身就发布了 int8 ONNX 导出。改用它后镜像中不再有 PyTorch，int8 会话仅增加约 0.3 GB 常驻内存，而 fp32 需约 1.2 GB（Linux 上整个向量化运行时约 0.45 GB），这正是能使用 0.5 vCPU / 1 GiB 副本的前提。在评测集上二者相差不超过 1 题；代价是索引必须由同一变体生成，`embeddingVariant` 字段负责强制校验。
- **按大纲切块 vs. 按页切块**：面试题类文档本质是题目列表。在顶层标题处切分能保持答案完整，标题路径为续块提供上下文，目录页检测（后文会重复出现的标题）剔除了"匹配一切却不含答案"的页面。从纯 PDF 文本恢复标题层级是启发式的，失败时退化为按行、按句切分。
- **按语言的词法副本 vs. 单一分析器**：`standard.lucene` 会把中文切成单字。隐藏的 `contentZh` / `contentJa` 副本以很小的存储代价换来词级 BM25（整个 v4 索引仅 3.2 MB）；语义重排仍读取语言中立的 `content`。
- **重排下限 vs. 总是生成**：丢弃 1.5 以下的上下文可避免把噪声喂给大模型，并让离题问题跳过生成。阈值由评测集校准，每次 Azure 评测都会输出校准数据。
- **进程内护栏 vs. API Management**：应用内的答案缓存与令牌桶零成本，在 `max_replicas = 1` 时是精确的；多副本或多区域部署应迁移到 Azure API Management 或共享存储。
- **Serverless 缩容到零 vs. 冷启动**：空闲零费用；空闲后的首次访问要承担调度、拉镜像与加载模型的时间。ONNX 镜像在后台预加载模型，使 `/ready` 在可服务时立即转为就绪。对延迟敏感的部署可设 `min_replicas = 1`，但会超出免费额度。
- **索引隔离（`ragdocs-v4`）**：每个块都携带 `embeddingModel`、`embeddingRevision` 与 `embeddingVariant`，服务拒绝不匹配的结果——索引过期时直接报错，而不是悄悄返回错误的近邻。
- **Bash 金丝雀 vs. Operator**：渐进式发布采用可评审的 Shell 脚本（`scripts/deploy_canary.sh`），版本状态与回滚逻辑在流水线日志中透明可查。

---

<a id="日本語"></a>

## 日本語

### プロジェクト概要と提供価値

本番環境で RAG を運用する際は、Embedding API の継続コスト、多言語検索精度のばらつき、デプロイのリスクが課題になります。本プロジェクトは **Azure の利用料ゼロ** のまま、この 3 点を同時に解決する方法を示します：

- **ONNX Runtime によるローカル多言語 Embedding**：`multilingual-e5-small`（リビジョン固定・SHA-256 検証済みの int8 ONNX エクスポート）と `query:` / `passage:` 非対称プレフィックス。Embedding API 不要、イメージに PyTorch を含まず、アプリコンテナは 0.5 vCPU / 1 GiB で稼働。
- **構造を意識した検索**：設問の見出し構造に沿ってページをまたいでチャンク化し、見出しコンテキストを付与、目次ページを除外。中国語・日本語の単語単位 BM25 と HNSW ベクトルを RRF で統合し、Azure AI Search のセマンティックランカーで再順位付け。
- **根拠に基づく構造化出力**：OpenAI Responses API が検証済み引用付き JSON を返却。関連度の低いコンテキストは生成前に除外し、無関係な質問では LLM を呼び出しません。
- **公開エンドポイントのコストガードレール**：回答キャッシュと分単位・日単位のクエリ予算で OpenAI の請求と無料のセマンティックランカー枠を保護。
- **サプライチェーンセキュリティとカナリアリリース**：ダイジェスト単位の Trivy スキャン、CycloneDX SBOM、CD が検証する Cosign キーレス署名、0% → 10% → 50% → 100% の段階的移行と自動ロールバック。
- **定量的な品質評価**：実コーパスに対する 50 問のラベル付き評価セットで検索モードごとに Azure 上で測定し、合成フィクスチャで CI をオフライン検証。

---

### 3.0 → 3.2

3.2 は v4 インデックスと ONNX int8 を維持し、レビュー修正と実行メタデータのみの LLM 監視を追加します。以下は今回の実測と 3.0 の過去の基準値との比較です。

| 項目 | 3.0 | 3.2 |
|---|---|---|
| Embedding ランタイム | PyTorch fp32 | ONNX int8 |
| アプリ + サイドカーの割り当て | 1.5 vCPU / 3 GiB | 1 vCPU / 2 GiB（実測構成） |
| Datadog | APM + DORA | ワークフロー・検索・LLM token のトレースを追加 |
| Page Hit Rate@1 / Page Hit Rate@3 | 84% / 94% | **96% / 98%** |
| MRR@10 | 0.900 | **0.966667** |
| コールドスタート | 約 60 秒（過去の記録） | **中央値 21.255 秒**（3 回：20.263–23.191 秒） |

測定日 2026-09-26：ラベル付き 50 問（中文 25 / 日本語 12 / 英語 13）、`ragdocs-v4` の Java 資料 521 チャンク、現在のセマンティック検索を使用。Page Hit Rate は関連ページのヒット率であり、回答の正答率ではありません。同じ測定で BM25 / ベクトル / ハイブリッド / セマンティック再順位付けの Hit@1 は **80% / 82% / 84% / 96%** でした。

コールドスタートは 2026-09-27 にプライバシー修正前の初版 3.2 イメージで測定：東日本 ACA、Python 3.14.7、アプリ 0.5 vCPU / 1 GiB と同容量の Datadog サイドカー。各回でレプリカ数ゼロを確認し、リクエスト開始から `/health` の最初の HTTP 200 までを測定。その後 0.050 秒以内に `/ready` も通過。縮退クールダウンは 30 秒、イメージキャッシュは未消去、サイドカー認証情報は無効なプレースホルダーです。3.0 は過去のシステムログの値なので、厳密な A/B 高速化率や Datadog 送信の検証結果ではありません。

3.2 の追加内容：セマンティック障害時の生成停止、Search 読み取り専用キー、キャッシュバイパス認証、引用検証、明示的な取り込みクリーンアップ、Azure OIDC デプロイ設定。

---

### Azure 無料枠への適合

| サービス | 無料枠 | 本プロジェクトでの抑え方 |
|---|---|---|
| Container Apps（Consumption） | 月 180,000 vCPU 秒・360,000 GiB 秒・200 万リクエスト | `min_replicas = 0`、0.5 vCPU / 1 GiB → 約 100 レプリカ時間（任意の Datadog サイドカー使用時は半分）。コールド訪問ごとに最低 300 秒のクールダウンが課金され、月約 1,200 回に相当 |
| Azure AI Search（Free） | 50 MB・3 インデックス・セマンティックランカーの月間無料枠 | v4 インデックスは 3.2 MB（ベクトルは `stored=False`）。キャッシュと日次予算でセマンティック枠を保護し、セマンティック処理失敗・スコア欠落時は生成を中止（無料枠超過時は Search が HTTP 402 を返す） |
| Log Analytics | 月 5 GB の取り込み・31 日保持 | 保持 30 日。Terraform と `setup-azure.sh` が日次 0.16 GB のベストエフォート上限を設定（超過分は課金され得る）。Azure SDK のリクエストログはアプリ側で抑制 |
| GitHub Container Registry | 公開イメージは無料 | イミュータブルなダイジェスト + 署名 |

Cost Management 上、本プロジェクトのリソースグループは 2026 年 6–9 月に **¥0** です。課金される外部依存は OpenAI のみで、回答キャッシュ・`QUERY_RATE_LIMIT_PER_MINUTE`・`QUERY_DAILY_LIMIT`・リランカー下限（無関係な質問は LLM に届かない）で制御します。Datadog APM は試験的なオプトイン（`enable_datadog_sidecar = true`。Agent サイドカーがあれば CD が自動でトレースを有効化）として残しています。サイドカーを使うとレプリカ全体が 0.5 vCPU / 1 GiB から 1 vCPU / 2 GiB となり、無料枠で動かせる時間は半分になります。

---

### エンドツーエンドのパイプライン

#### 1. データ投入パイプライン (Data Ingestion)

```mermaid
flowchart LR
    Docs["元ドキュメント<br/>(PDF / MD / TXT、--glob で選択)"] --> TOC["目次ページを除外"]
    TOC --> Chunk["見出し構造に沿ったチャンク<br/>(≤384 tokens、ページ横断、見出しパス)"]
    Chunk --> Embed["E5 int8 + ONNX Runtime (passage:)<br/>384 次元正規化ベクトル"]
    Embed --> Index[("Azure AI Search ragdocs-v4<br/>HNSW + 中日語彙フィールド + セマンティックタイトル")]
```

#### 2. オンライン検索・生成パイプライン (Online Query)

```mermaid
flowchart LR
    Client["クライアント"] --> API["FastAPI<br/>rag.query"]
    API --> Guard["キャッシュ + クエリ予算"]
    Guard -- "キャッシュ命中" --> Response["回答 + 引用"]
    Guard -- "未命中" --> QVec["E5 クエリ Embedding<br/>rag.embed"]
    QVec --> Search["Azure AI Search<br/>ハイブリッド + セマンティック · rag.search"]
    Search --> Evidence{"根拠がしきい値を満たす？"}
    Evidence -- "はい" --> LLM["OpenAI Responses<br/>rag.generate"]
    Evidence -- "いいえ：根拠不足を返す" --> Response
    LLM --> Response
    API -. "ワークフローと各段階のトレース" .-> Agent["Datadog Agent サイドカー<br/>同一レプリカ · :8126"]
    Agent -.-> DD["Datadog<br/>APM + LLM Observability"]
```

**Datadog：APM + LLM Observability。** `rag.query` が各段階をまとめ、既存の Agent サイドカー（`127.0.0.1:8126`）経由で実行メタデータを送ります。2026-09-27 に `serverless-rag-api`、バージョン `3.2.0` の 4 スパン、処理時間、LLM 入出力トークンの受信を確認しました。質問・回答本文は収集しません。GitHub の `DD_API_KEY` が未設定のため、任意の DORA デプロイイベントはスキップされました。

| トレース | 記録するデータ |
|---|---|
| `rag.query` | 全体の所要時間、キャッシュ命中、根拠不足、拒否、groundedness フラグ |
| `rag.embed` / `rag.search` | 各段階の所要時間、採用チャンク数、セマンティックスコア範囲 |
| `rag.generate` | モデル、所要時間、入力/出力/合計、キャッシュ入力、推論 token |

キャッシュ命中時はモデルを呼ばず、token も重複計上しません。質問・回答・文書本文は収集しません。監視は問題の特定に使い、検索品質はラベル付き評価で測定します。

#### 3. 安全な CI/CD カナリアリリース (Canary Pipeline)

```mermaid
flowchart LR
    PR["コード Push / PR"] --> Lint["品質ゲート<br/>Ruff + Mypy + Pytest + 監査 + 検索回帰"]
    Lint --> Smoke["コンテナスモークテスト<br/>ネットワーク遮断・0.5 vCPU / 1 GiB"]
    Smoke --> Build["イミュータブルイメージ構築<br/>(SHA ダイジェスト)"]
    Build --> Scan["Trivy セキュリティスキャン"]
    Scan --> SBOM["SBOM 生成 &<br/>Cosign キーレス署名"]
    SBOM --> Canary["ACA カナリアデプロイ (0%)<br/>ヘルスチェック & 実クエリ検証"]
    Canary --> Promote["段階的トラフィック移行<br/>10% → 50% → 100%"]
    Canary -. "異常検知" .-> Rollback["自動ロールバック<br/>旧安定リビジョンへ復帰"]
    Promote -. "成功時" .-> DORA["Datadog DORA<br/>デプロイイベント"]
```

---

### 主要な技術的特徴

1. **多言語ハイブリッド検索**
   - モデルリビジョン `intfloat/multilingual-e5-small@614241f...` を固定し、ONNX ファイルとトークナイザーの SHA-256 を `app/model_manifest.py` で固定。
   - 構造を意識したチャンク化：番号・Markdown・章見出しで分割位置を決め、小項目は設問内に保持し、ページをまたいで結合。チャンク本文は原文から切り出し、トークナイザーで再デコードしません。
   - `ragdocs-v4` インデックス：コサイン HNSW、`title` フィールド付きセマンティック構成、中国語・日本語の分かち書き語彙コピー、ページ範囲、全チャンクに `embeddingVariant` を記録。
2. **根拠に基づく生成と安全性**
   - 検索結果は信頼できない証拠として隔離し、Pydantic は応答構造、アプリは引用番号を検証。根拠フラグはモデルの自己申告で、独立した事実検証ではありません。
   - セマンティックランカーの下限未満のコンテキストは除外し、何も残らなければ LLM を呼ばずに「根拠不足」と回答。
3. **コストガードレールと可観測性**
   - TTL 回答キャッシュ（有効な `X-Canary-Token` のみバイパス可能）、分単位トークンバケット、UTC 日単位の上限。超過時は `429 Retry-After`。
   - レスポンスと構造化 JSON ログに `embedding_ms` / `search_ms` / `generation_ms` の内訳を出力。Datadog APM・実行メタデータのみの LLM トレース・DORA デプロイイベントはオプション。
4. **評価フレームワーク**
   - `eval/golden_corpus.jsonl` で実インデックスを検索モード別に評価し、リランカー下限の校正データも出力。合成フィクスチャは高速なオフライン CI ゲートとして継続利用。

---

<details>
<summary>運用手順と設定（展開）</summary>

### 運用手順 (Runbook)

#### 1. ローカル環境の構築

```bash
# 依存関係のインストール
uv sync --frozen --dev

# 環境変数の設定
cp .env.example .env
# .env を開き、AZURE_SEARCH_ENDPOINT、AZURE_SEARCH_QUERY_KEY、OPENAI_API_KEY を設定
```
Embedding モデルは初回利用時に `~/.cache/serverless-rag` へダウンロードされ、固定された SHA-256 で検証されます（コンテナイメージはビルド時にモデルを同梱し、オフラインで動作します）。

#### 2. インデックス作成とデータ投入

```bash
# バージョン付き Azure AI Search インデックスの作成
uv run python scripts/create_index.py --index-name ragdocs-v4

# Embedding・アップロードを行わずにチャンク化結果だけを確認
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --dry-run

# 選択した公開ドキュメントだけを投入
uv run python scripts/ingest.py --data-dir data --glob '*.pdf' --index-name ragdocs-v4
```
投入した内容は公開 API からそのまま返されます。`--glob` で対象ファイルを明示し、個人的なメモを投入しないでください。再投入は冪等で、ソースごとに古いチャンクを削除します。

#### 3. アプリケーションの起動と検証

```bash
# FastAPI サーバーの起動
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# ヘルスチェック
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready

# 問い合わせテスト
curl -fsS http://127.0.0.1:8000/query \
  -H 'Content-Type: application/json' \
  --data '{"question": "Javaのガベージコレクションはどのように不要なオブジェクトを判定しますか？", "top_k": 3}'
```

#### 4. 検索品質の評価

```bash
# Azure 上で実コーパスを評価：検索モード別アブレーション（セマンティック 1 回につきランカー枠を 50 回消費）
uv run python scripts/evaluate_retrieval.py --backend azure --index-name ragdocs-v4 \
  --mode semantic --mode hybrid --mode vector --mode bm25

# 合成フィクスチャでのオフラインモデル比較（CI 回帰ゲート）
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --model intfloat/multilingual-e5-small --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```
Azure 評価は `reranker_calibration` も出力し、候補となる各下限が top-k のうちラベル付きヒットとそれ以外をどれだけ残すかを示します。本番の下限 1.5 はラベル付きヒットをすべて保持し（最小 1.90）、無関係な質問の最高スコアは 0.5–1.6 に収まります。

`--backend local` は `eval/corpus.jsonl` と `eval/golden.jsonl` のみを読み込みます。固定の E5 モデルは本番と同じ ONNX エンコーダーで、その他のモデルは sentence-transformers で推論します。同梱フィクスチャ（9 パッセージ / 6 クエリ、`en`・`ja`・`zh` 各 2 件）の過去の基準値と今回の Linux での結果：

| モデル | Page Hit Rate@1 | Page Hit Rate@3 | MRR | `ja` Page Hit Rate@1 |
|---|---|---|---|---|
| `all-MiniLM-L6-v2`（英語単言語ベースライン） | 0.833 | 1.000 | 0.917 | 0.500 |
| `multilingual-e5-small`、fp32（3.0） | 1.000 | 1.000 | 1.000 | 1.000 |
| `multilingual-e5-small`、ONNX int8（3.2、今回の Linux 実測） | **1.000** | **1.000** | **1.000** | **1.000** |

3.2 ONNX は 2026-09-26 に Linux で再測定し、6 問すべてで top-1 に正解が入りました。MiniLM と 3.0 fp32 は過去の基準値です。量子化カーネルでは僅差の順位が変わるため、CI は各言語の top-3 全問ヒットと MRR ≥ 0.9 を要求します。この 9 段落・6 問の合成データは回帰テスト用であり、本番の回答正答率を表しません。

#### 5. 品質ゲート（検証スクリプト）

```bash
# フォーマット、型検査、脆弱性監査、テストを一括実行
# uv run により .venv/bin が PATH に追加され、CI と同じ実行条件になります。
uv run bash scripts/verify.sh
```
CI と同一のスクリプトです：`ruff format --check`、`ruff check`、`mypy`、エクスポートしたランタイムロックに対する `pip-audit`、カバレッジ下限 80% の `pytest`。CI はさらにビルドしたイメージを `--network none --cpus 0.5 --memory 1g` で起動し（`scripts/smoke_container.sh`）、モデルがオフラインでロードできない場合やメモリが 900 MiB を超えた場合に失敗させます。

#### 6. ロールバック手順
カナリア検証に失敗すると、パイプラインは自動的に安定リビジョンへトラフィックを 100% 戻します。移行が成功すると他のリビジョンはすべて非アクティブ化されます（非アクティブなリビジョンは課金されず、いつでも再利用可能）。手動で戻す場合：
```bash
az containerapp revision activate --name <app-name> --resource-group <resource-group> --revision <stable-revision-name>
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision-weight <stable-revision-name>=100
```

---

### 環境変数リファレンス

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | - | Azure AI Search のエンドポイント URL |
| `AZURE_SEARCH_QUERY_KEY` | - | 読み取り専用 Query Key。管理スクリプトは `AZURE_SEARCH_ADMIN_KEY` |
| `AZURE_SEARCH_INDEX_NAME` | `ragdocs-v4` | 実行中アプリケーションが参照するインデックス |
| `AZURE_SEARCH_INDEX_NAME_V4` | `ragdocs-v4` | `scripts/`（作成・投入・削除・評価）が対象とするインデックス |
| `SEARCH_MIN_RERANKER_SCORE` | `1.5` | セマンティックランカーの下限（0–4）。未満のコンテキストは除外 |
| `OPENAI_API_KEY` | - | OpenAI API の認証キー |
| `OPENAI_MODEL` | `gpt-5.6-terra` | 生成に使用するモデル ID |
| `OPENAI_REASONING_EFFORT` | `low` | 生成時の推論バジェット |
| `EMBEDDING_MODEL` / `EMBEDDING_MODEL_REVISION` | `intfloat/multilingual-e5-small` / `614241f...` | manifest の既定値と照合。不一致は起動失敗。デプロイ時は上書きしない |
| `EMBEDDING_VARIANT` | `onnx-qint8` | 使用する ONNX ファイル（`onnx-fp32` は約 0.9 GB 多くメモリが必要）。インデックスと一致が必須 |
| `EMBEDDING_MODEL_PATH` | - | 事前ダウンロード済みモデルディレクトリ（イメージで設定済み）。未設定なら `~/.cache/serverless-rag` |
| `EMBEDDING_OFFLINE` | `false` | 実行時のモデルダウンロードを禁止（`HF_HUB_OFFLINE` も可） |
| `EMBEDDING_THREADS` | `1` | ONNX Runtime の演算子内スレッド数。レプリカの vCPU 割り当て以下に |
| `EMBEDDING_BATCH_SIZE` | `16` | パッセージ Embedding のバッチサイズ |
| `ANSWER_CACHE_TTL_SECONDS` | `3600` | 回答キャッシュの有効期間（0 で無効） |
| `QUERY_RATE_LIMIT_PER_MINUTE` / `QUERY_DAILY_LIMIT` | `20` / `500` | レプリカあたりのキャッシュ外クエリ予算（0 で無効） |
| `DD_TRACE_ENABLED` | `false` | uvicorn を `ddtrace-run` で起動。CD が Datadog Agent サイドカーの有無から自動設定（リポジトリ変数で上書き可） |
| `DD_LLMOBS_ENABLED` | `false` | LLM トレースを有効化。CD は `DD_TRACE_ENABLED` に連動。既存サイドカーを使い、アプリ側の Datadog Key は不要 |
| `DD_LLMOBS_ML_APP` | `serverless-rag-api` | LLM アプリ名。起動時に OpenAI の自動本文収集を無効化し、Agent モードを使用 |
| `SEARCH_TOP_K_DEFAULT` / `SEARCH_TOP_K_MAX` | `5` / `10` | `top_k` の既定値と上限 |

---

</details>

### 主要な設計判断とトレードオフ

- **ONNX int8 vs. PyTorch fp32**: 固定リビジョン自体が int8 の ONNX エクスポートを公開しています。これを使うことでイメージから PyTorch がなくなり、int8 セッションの常駐メモリ増加は約 0.3 GB（fp32 は約 1.2 GB、Linux での Embedding ランタイム全体は約 0.45 GB）に抑えられ、0.5 vCPU / 1 GiB のレプリカが可能になりました。評価セット上の差は 1 問以内です。代償としてインデックスは同じバリアントで作成する必要があり、`embeddingVariant` がそれを強制します。
- **見出し構造チャンク vs. ページチャンク**: 面接対策系のドキュメントは設問の一覧です。トップレベルの見出しで区切ることで回答を分断せず、見出しパスが続きのチャンクに文脈を与え、目次検出（後で見出しとして再登場する行）が「何にでも一致するが回答を含まない」ページを除外します。PDF のプレーンテキストからの見出し階層の復元はヒューリスティックであり、失敗時は行・文単位の分割にフォールバックします。
- **言語別語彙コピー vs. 単一アナライザー**: `standard.lucene` は中国語を 1 文字ずつに分割します。非表示の `contentZh` / `contentJa` コピーはわずかなストレージ（v4 インデックス全体で 3.2 MB）で単語単位の BM25 を実現し、セマンティックランカーは言語中立の `content` を読み続けます。
- **リランカー下限 vs. 常に生成**: 1.5 未満のコンテキストを除外することで LLM へのノイズ入力を防ぎ、無関係な質問では生成自体を省略します。しきい値は評価セットで校正し、Azure 評価のたびに校正データを出力します。
- **プロセス内ガードレール vs. API Management**: アプリ内の回答キャッシュとトークンバケットはコストゼロで、`max_replicas = 1` なら正確です。複数レプリカ・複数リージョン構成では Azure API Management や共有ストアへ移すべきです。
- **Serverless ゼロスケール vs. コールドスタート**: アイドル時はコストゼロですが、アイドル後の最初のアクセスはスケジューリング・イメージ取得・モデルロードを待ちます。ONNX イメージはモデルをバックグラウンドで先読みし、サービス可能になった時点で `/ready` を切り替えます。レイテンシ重視なら `min_replicas = 1` ですが、無料枠を超えます。
- **インデックスのバージョン分離（`ragdocs-v4`）**: 各チャンクは `embeddingModel`・`embeddingRevision`・`embeddingVariant` を保持し、一致しない結果はサービス側で拒否します。古いインデックスは沈黙して誤った近傍を返すのではなく、明示的に失敗します。
- **Bash カナリア vs. Operator**: 段階的リリースはレビュー可能なシェルスクリプト（`scripts/deploy_canary.sh`）で実装し、リビジョン状態とロールバック処理をワークフローログ上で透明に保ちます。


## Review hardening and migration

Before the first 3.2 deployment, configure Azure OIDC trust and the GitHub `stg` environment identifiers. Provision matching canary-token secrets in GitHub and Container Apps, plus a separate read-only Search query key. Preserve existing credentials until the new path and rollback are verified. The `main` branch auto-deploys; a version bump alone does not complete this migration.

- `POST /query` accepts `language: "auto" | "zh" | "ja" | "en"`; explicit language also controls fallback messages and cache identity. Cached responses report `usage: null` because this request made no model call.
- Set `AZURE_SEARCH_QUERY_KEY` for serving and Azure retrieval evaluation; set `AZURE_SEARCH_ADMIN_KEY` only for index creation, ingestion, or deletion. There is no legacy admin-key fallback in the serving app.
- `ingest.py --dry-run` previews chunking without inference/upload; a cold cache downloads only the tokenizer. Regular ingestion cleans obsolete chunks for every selected source, including empty sources. `--prune-missing` additionally removes missing sources from a dedicated index whose entire corpus is managed by `--data-dir`; it refuses `--glob` and an empty selection. Parsing/embedding/upload failures abort before cleanup. This is not a transactional index swap; failed runs can still leave successfully uploaded documents.
- Page Hit Rate@K measures the fraction of questions with at least one annotated page match in the top K (the local synthetic fixture matches passage IDs). It does not measure the fraction of all relevant pages retrieved. Historical numbers above are unchanged; evaluation JSON now uses `page_hit_rate@K` and `unlabelled_dropped`.
- Cost limits are per process/replica, reset on restart, and do not reserve Azure's monthly semantic allowance. No cache or daily cap guarantees zero cost.
