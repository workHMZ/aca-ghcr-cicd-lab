# Serverless Multilingual RAG on Azure

[![CI](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/ci.yml)
[![Security](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml/badge.svg)](https://github.com/workHMZ/aca-ghcr-cicd-lab/actions/workflows/security.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB.svg)](https://www.python.org/)
[![Version 3.0.0](https://img.shields.io/badge/version-3.0.0-6f42c1.svg)](#configuration)

Production-ready, cost-optimized serverless multilingual Retrieval-Augmented Generation (RAG) service on Azure Container Apps, powered by local multilingual embeddings, Azure AI Search hybrid retrieval, and OpenAI Structured Outputs.

[English](#english) | [中文](#中文) | [日本語](#日本語)

---

## Project Structure

```text
├── app/
│   ├── config.py                          # Validated Pydantic runtime settings
│   ├── chunking.py                        # Tokenizer-aware overlapping chunking
│   ├── embed.py                           # Pinned E5 query/passage embeddings (384-dim)
│   ├── search_client.py                   # Cached Azure AI Search client
│   └── main.py                            # Async FastAPI + Datadog APM + Structured generation
├── eval/
│   ├── corpus.jsonl                       # Synthetic multilingual evaluation corpus
│   └── golden.jsonl                       # Labelled multi-lingual retrieval ground truth
├── scripts/
│   ├── create_index.py                    # Azure AI Search versioned index creation (HNSW + Semantic)
│   ├── ingest.py                          # Document ingestion (PDF/MD/TXT → chunks → embeddings)
│   ├── clear_index.py                     # Safe document purging by source prefix
│   ├── evaluate_retrieval.py              # Offline retrieval evaluation (Recall@K, MRR)
│   ├── deploy_canary.sh                   # Progressive ACA canary rollout & automated rollback
│   ├── test_api.py                        # API smoke testing
│   ├── verify.sh                          # Local quality gate (Ruff, Mypy, pip-audit, Pytest)
│   ├── sync_datadog_catalog.sh            # Datadog Service Catalog sync
│   └── send_datadog_dora_deployment.sh    # Datadog DORA deployment tracking
├── .github/workflows/
│   ├── ci.yml                             # Quality gates → Immutable image → SBOM → Cosign signature
│   ├── cd.yml                             # Verification → Canary deployment → Automated rollback
│   └── security.yml                       # Pull Request filesystem, secret & dependency scanning
├── terraform/                             # Azure Container Apps & Search infrastructure as code
├── data/                                  # Source knowledge documents
├── service.datadog.yaml                   # Datadog Service Catalog metadata
└── pyproject.toml                         # Unified project configuration & dependencies
```

---

<a id="english"></a>

## English

### Overview & Core Value

Building production RAG systems often introduces high recurring embedding API costs, unpredictable retrieval across languages, and complex deployment lifecycles. 

This project provides a cost-effective, enterprise-grade multilingual Serverless RAG solution:
- **Local Multilingual Embeddings**: Runs `multilingual-e5-small` in-container with asymmetric `query:` / `passage:` prefixes and L2 normalization, eliminating per-query embedding API costs and boosting multilingual recall.
- **Hybrid Retrieval**: Combines keyword search, HNSW dense vectors, and Azure AI Search Semantic Ranker for high-precision context retrieval.
- **Grounded Structured Outputs**: Uses OpenAI Responses API to enforce structured JSON responses with validated citations and context isolation.
- **Supply Chain Security & Canary Release**: Automated CycloneDX SBOM generation, Trivy vulnerability scanning, Cosign keyless signing, and progressive canary rollouts (0% → 10% → 50% → 100%) on Azure Container Apps.
- **Offline Quality Evaluation**: Built-in retrieval evaluation framework measuring Recall@K and MRR across English, Chinese, and Japanese.

---

### End-to-End Pipelines

#### 1. Data Ingestion Pipeline
```mermaid
flowchart LR
    Docs["Documents<br/>(PDF / MD / TXT)"] --> Chunk["Tokenizer-Aware Chunking<br/>(384 tokens / 48 overlap)"]
    Chunk --> Embed["E5 Model (passage:)<br/>384-dim Normalized Vectors"]
    Embed --> Index[("Azure AI Search<br/>ragdocs-v3 (HNSW)")]
```

#### 2. Online Query Pipeline
```mermaid
flowchart LR
    Client["Client Request"] --> API["FastAPI Application"]
    API --> QVec["E5 Model (query:)<br/>Query Embedding"]
    QVec --> Hybrid["Hybrid Retrieval<br/>BM25 + HNSW + Semantic Ranker"]
    Index[("Azure AI Search<br/>ragdocs-v3")] --> Hybrid
    Hybrid --> Context["Isolated Contexts<br/>(Source, Page, Chunk ID)"]
    Context --> LLM["OpenAI LLM<br/>(gpt-5.6-terra)"]
    LLM --> Response["Structured JSON<br/>(Answer + Citations + Usage)"]
```

#### 3. Secure CI/CD Canary Pipeline
```mermaid
flowchart LR
    PR["PR / Main Push"] --> Lint["Quality Gate<br/>Ruff + Mypy + Pytest + Audit"]
    Lint --> Build["Build Immutable Image<br/>(SHA Digest)"]
    Build --> Scan["Trivy Security Scan"]
    Scan --> SBOM["Generate SBOM &<br/>Cosign Keyless Signature"]
    SBOM --> Canary["ACA Canary (0%)<br/>Health & Query Warmup"]
    Canary --> Promote["Traffic Progression<br/>10% → 50% → 100%"]
    Canary -. "Failure" .-> Rollback["Automated Rollback<br/>to Previous Revision"]
```

---

### Key Features

1. **Multilingual Hybrid Retrieval**
   - Fixed model revision: `intfloat/multilingual-e5-small` (`614241f...`).
   - Token-aware chunking preserving page metadata, content hashes, and document lineage.
   - Azure AI Search index (`ragdocs-v3`) with cosine HNSW and semantic ranking.
2. **Grounded Synthesis & Safety**
   - Retrieved chunks wrapped inside untrusted evidence boundaries.
   - Pydantic schema validation for structured answers, citations, and groundedness flags.
3. **Observability & DORA Metrics**
   - Datadog APM tracing (`ddtrace`), structured JSON logging, and Service Catalog integration.
   - Automated deployment event emission for tracking lead time and deployment frequency.
4. **Offline Evaluation Framework**
   - Synthetic benchmark fixture (`eval/corpus.jsonl`, `eval/golden.jsonl`) to evaluate retrieval quality independently from LLM generation.

---

### Runbook

#### 1. Local Setup
```bash
# Install dependencies with locked environment
uv sync --frozen --dev

# Configure environment variables
cp .env.example .env
# Edit .env and supply AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, OPENAI_API_KEY
```

#### 2. Index Management & Data Ingestion
```bash
# Create versioned Azure AI Search index
uv run python scripts/create_index.py --index-name ragdocs-v3

# Ingest local documents from data/
uv run python scripts/ingest.py --data-dir data --index-name ragdocs-v3
```

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

#### 4. Run Offline Retrieval Evaluation
```bash
# Run local model comparison against synthetic golden fixture
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```

#### 5. Local Quality Gate
```bash
# Run full verification (formatting, linting, type checks, dependency audit, coverage)
bash scripts/verify.sh
```

#### 6. Rollback Procedure
If canary health checks fail during deployment, the pipeline automatically aborts and retains 100% traffic on the active stable revision. To manually restore traffic:
```bash
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision <stable-revision-name>=100
```

---

### Configuration Reference

| Environment Variable | Default Value | Description |
|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | - | Azure AI Search service endpoint URL |
| `AZURE_SEARCH_API_KEY` | - | Azure AI Search admin/query key |
| `AZURE_SEARCH_INDEX_NAME` | `ragdocs-v3` | Active target search index name |
| `OPENAI_API_KEY` | - | OpenAI API authentication key |
| `OPENAI_MODEL` | `gpt-5.6-terra` | Generation model ID |
| `OPENAI_REASONING_EFFORT` | `low` | Reasoning effort budget for generation |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Preloaded embedding model identifier |
| `EMBEDDING_MODEL_REVISION` | `614241f...` | Pinned Git commit hash of embedding model |
| `EMBEDDING_BATCH_SIZE` | `16` | Batch size for inference encoding |
| `SEARCH_TOP_K_DEFAULT` | `5` | Default number of retrieved contexts |
| `SEARCH_TOP_K_MAX` | `10` | Maximum allowable top_k limit |

---

### Design Decisions & Trade-offs

- **Local Embeddings vs. Embedding APIs**: Embedding locally eliminates per-query API latency and cost, but increases container image size (~1.5 GB) and baseline RAM requirement (allocated 2 GiB).
- **Serverless Scale-to-Zero vs. Cold Start**: ACA scale-to-zero minimizes idle compute cost. Startup latency is mitigated via `/warmup` probes and maintaining `min_replicas = 1` in production environments.
- **Index Isolation (`ragdocs-v3`)**: A distinct index name prevents incompatible vector space mixing when upgrading embedding models.

---

<a id="中文"></a>

## 中文

### 项目概述与核心价值

在云原生环境中落地 RAG 系统时，通常面临持续的 Embedding API 费用高昂、跨语言检索召回不准、以及无停机安全交付难度大等挑战。

本项目提供了一套面向生产、成本优化的 Serverless 多语言 RAG 架构方案：
- **容器内本地多语言向量计算**：集成 `multilingual-e5-small` 模型，采用 `query:` / `passage:` 非对称前缀与 L2 向量归一化，零 API 成本并大幅提升中文与日文的召回精度。
- **多路混合检索**：结合 BM25 关键词、HNSW 密集向量与 Azure AI Search 语义重排序（Semantic Ranker），实现高精度上下文检索。
- **结构化可信生成**：基于 OpenAI Responses API，强制输出包含证据引用的结构化 JSON，并对检索上下文实施严格隔离。
- **供应链安全与金丝雀发布**：集成了 Trivy 漏洞扫描、CycloneDX 软件物料清单 (SBOM)、Cosign 无密钥签名，并在 Azure Container Apps 上实现灰度放量（0% → 10% → 50% → 100%）与异常自动回滚。
- **离线质量评测体系**：内置检索评测基准，支持对 Recall@K 与 MRR 指标进行跨语言量化评估。

---

### 端到端核心链路

#### 1. 数据摄取链路 (Data Ingestion Pipeline)
```mermaid
flowchart LR
    Docs["原始文档<br/>(PDF / MD / TXT)"] --> Chunk["分词感知分块<br/>(384 tokens / 48 overlap)"]
    Chunk --> Embed["E5 模型向量化 (passage:)<br/>384 维归一化向量"]
    Embed --> Index[("Azure AI Search<br/>ragdocs-v3 索引 (HNSW)")]
```

#### 2. 在线检索与生成链路 (Online Query Pipeline)
```mermaid
flowchart LR
    Client["客户端请求"] --> API["FastAPI 服务"]
    API --> QVec["E5 模型向量化 (query:)<br/>生成查询向量"]
    QVec --> Hybrid["混合检索<br/>BM25 + HNSW + 语义重排"]
    Index[("Azure AI Search<br/>ragdocs-v3")] --> Hybrid
    Hybrid --> Context["编号证据上下文<br/>(来源、页码、Chunk ID)"]
    Context --> LLM["OpenAI 大模型<br/>(gpt-5.6-terra)"]
    LLM --> Response["结构化响应<br/>(答案 + 引用 + Token 统计)"]
```

#### 3. 安全 CI/CD 金丝雀发布链路 (Canary Delivery Pipeline)
```mermaid
flowchart LR
    PR["代码提交 / PR"] --> Lint["质量与安全门禁<br/>Ruff + Mypy + Pytest + 依赖审计"]
    Lint --> Build["构建不可变镜像<br/>(SHA 摘要)"]
    Build --> Scan["Trivy 镜像安全扫描"]
    Scan --> SBOM["生成 SBOM 物料清单<br/>Cosign 无密钥签名证明"]
    SBOM --> Canary["ACA 金丝雀发布 (0% 流量)<br/>健康检查与真实 Query 预热"]
    Canary --> Promote["阶梯放量<br/>10% → 50% → 100%"]
    Canary -. "检测失败" .-> Rollback["自动回滚<br/>切回上一稳定版本"]
```

---

### 核心技术特性

1. **多语言混合检索体系**
   - 锁定模型版本：`intfloat/multilingual-e5-small`（Git Commit: `614241f...`）。
   - 分词感知分块（Tokenizer-aware Chunking），保留页码元数据与内容哈希。
   - 独立的 `ragdocs-v3` 索引空间，避免不同维度与模型空间的向量污染。
2. **结构化生成与防注入**
   - 检索内容置于独立的不可信上下文边界，降低 Prompt 注入风险。
   - Pydantic 模型校验输出，确保答案具备确切引用（Citations）与可信度状态。
3. **企业级可观测性与 DORA 指标**
   - 集成 Datadog APM（`ddtrace`）、结构化 JSON 日志与 Service Catalog 同步。
   - 部署流水线自动发送部署事件，精准追踪变更前置时间与交付频率。
4. **离线检索评测基准**
   - 提供标准评测集（`eval/corpus.jsonl` 与 `eval/golden.jsonl`），将检索能力与生成能力完全解耦评估。

---

### 运维手册 (Runbook)

#### 1. 本地环境初始化
```bash
# 使用 uv 安装锁定依赖
uv sync --frozen --dev

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 AZURE_SEARCH_ENDPOINT、AZURE_SEARCH_API_KEY 与 OPENAI_API_KEY
```

#### 2. 索引创建与文档摄取
```bash
# 创建具有 HNSW 与语义重排配置的 Azure AI Search 索引
uv run python scripts/create_index.py --index-name ragdocs-v3

# 将 data/ 目录中的文档切分、向量化并批量写入索引
uv run python scripts/ingest.py --data-dir data --index-name ragdocs-v3
```

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

#### 4. 离线检索质量评测
```bash
# 本地对比 MiniLM 与 Multilingual-E5 模型在标准评测集上的表现
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```

#### 5. 本地质量门禁检查
```bash
# 执行完整质检（代码格式、类型检查、依赖漏洞扫描、单元测试与覆盖率）
bash scripts/verify.sh
```

#### 6. 异常回滚流程
若部署期间金丝雀探针失败，流水线将自动终止并保留旧版本 100% 流量。如需手动回滚，可通过 Azure CLI 一键切回稳定版本：
```bash
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision <stable-revision-name>=100
```

---

### 环境变量配置说明

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `AZURE_SEARCH_ENDPOINT` | - | Azure AI Search 服务终端地址 |
| `AZURE_SEARCH_API_KEY` | - | Azure AI Search 管理/查询密钥 |
| `AZURE_SEARCH_INDEX_NAME` | `ragdocs-v3` | 当前生效的目标搜索索引名称 |
| `OPENAI_API_KEY` | - | OpenAI API 鉴权密钥 |
| `OPENAI_MODEL` | `gpt-5.6-terra` | 答案生成模型名称 |
| `OPENAI_REASONING_EFFORT` | `low` | 生成模型的推理思考预算 |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | 预加载的本地 Embedding 模型标识 |
| `EMBEDDING_MODEL_REVISION` | `614241f...` | 锁定的 Embedding 模型 Git Commit 摘要 |
| `EMBEDDING_BATCH_SIZE` | `16` | 向量化推理批处理大小 |
| `SEARCH_TOP_K_DEFAULT` | `5` | 默认检索召回数量 |
| `SEARCH_TOP_K_MAX` | `10` | 允许的最大检索召回数量 |

---

### 架构设计与权衡

- **本地 Embedding vs. API 调用**：在容器内本地运行模型消除了按次调用的 API 费用与网络延迟，但增加了镜像体积（~1.5 GB）和容器常驻内存开销（配置为 2 GiB）。
- **Serverless 缩容到零 vs. 冷启动**：Azure Container Apps 支持缩容到 0 以节约成本；通过 `/warmup` 探针预热模型，生产环境推荐设置 `min_replicas = 1` 消除冷启动。
- **独立索引空间隔离 (`ragdocs-v3`)**：升级 Embedding 模型时采用全新的版本化索引，杜绝不同向量空间混用导致的召回失效。

---

<a id="日本語"></a>

## 日本語

### プロジェクト概要と提供価値

本番環境で RAG システムを構築・運用する際、Embedding API の継続的コスト、多言語における検索精度のばらつき、ゼロダウンタイムでの安全なデプロイが主要な課題となります。

本プロジェクトは、費用対効果が高くエンタープライズ品質の Serverless 多言語 RAG ソリューションを提供します：
- **コンテナ内ローカル多言語 Embedding**：`multilingual-e5-small` を採用し、非対称プレフィックス（`query:` / `passage:`）と L2 正規化を適用。API 呼び出しコストをゼロにし、日本語および中国語の検索精度を大幅に向上。
- **ハイブリッド検索**：BM25 キーワード検索、HNSW 高次元ベクトル検索、Azure AI Search セマンティックリランカーを統合し、高精度なコンテキスト抽出を実現。
- **引用付き構造化出力**：OpenAI Responses API を使用し、検証済み引用情報を含む構造化 JSON 出力とコンテキストの境界分離を徹底。
- **サプライチェーンセキュリティとカナリアリリース**：Trivy 脆弱性スキャン、CycloneDX SBOM 生成、Cosign キーレス署名、Azure Container Apps 上での段階的トラフィック移行（0% → 10% → 50% → 100%）と自動ロールバックを完備。
- **オフライン検索品質評価**：LLM の生成と検索精度を切り離して測定できる、Recall@K および MRR 評価フレームワークを内蔵。

---

### エンドツーエンドのパイプライン

#### 1. データ投入パイプライン (Data Ingestion)
```mermaid
flowchart LR
    Docs["元ドキュメント<br/>(PDF / MD / TXT)"] --> Chunk["トークナイザー認識チャンク分割<br/>(384 tokens / 48 overlap)"]
    Chunk --> Embed["E5 モデルベクトル化 (passage:)<br/>384 次元正規化ベクトル"]
    Embed --> Index[("Azure AI Search<br/>ragdocs-v3 インデックス")]
```

#### 2. オンライン検索・生成パイプライン (Online Query)
```mermaid
flowchart LR
    Client["クライアント要求"] --> API["FastAPI アプリケーション"]
    API --> QVec["E5 モデルベクトル化 (query:)<br/>クエリベクトル生成"]
    QVec --> Hybrid["ハイブリッド検索<br/>BM25 + HNSW + セマンティック"]
    Index[("Azure AI Search<br/>ragdocs-v3")] --> Hybrid
    Hybrid --> Context["番号付き証拠コンテキスト<br/>(ソース・ページ・チャンク ID)"]
    Context --> LLM["OpenAI LLM<br/>(gpt-5.6-terra)"]
    LLM --> Response["構造化レスポンス<br/>(回答 + 引用 + Token 統計)"]
```

#### 3. 安全な CI/CD カナリアリリース (Canary Pipeline)
```mermaid
flowchart LR
    PR["コード Push / PR"] --> Lint["品質・セキュリティ検証<br/>Ruff + Mypy + Pytest + 監査"]
    Lint --> Build["イミュータブルイメージ構築<br/>(SHA ダイジェスト)"]
    Build --> Scan["Trivy セキュリティスキャン"]
    Scan --> SBOM["SBOM 生成 &<br/>Cosign キーレス署名"]
    SBOM --> Canary["ACA カナリアデプロイ (0%)<br/>ヘルスチェック & 実クエリ検証"]
    Canary --> Promote["段階的トラフィック移行<br/>10% → 50% → 100%"]
    Canary -. "異常検知" .-> Rollback["自動ロールバック<br/>旧安定リビジョンへ復帰"]
```

---

### 運用手順 (Runbook)

#### 1. ローカル環境の構築
```bash
# 依存関係のインストール
uv sync --frozen --dev

# 環境変数の設定
cp .env.example .env
# .env を開き、AZURE_SEARCH_ENDPOINT、AZURE_SEARCH_API_KEY、OPENAI_API_KEY を設定
```

#### 2. インデックス作成とデータ投入
```bash
# Azure AI Search インデックスの作成
uv run python scripts/create_index.py --index-name ragdocs-v3

# data/ フォルダ内のドキュメントを投入
uv run python scripts/ingest.py --data-dir data --index-name ragdocs-v3
```

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

#### 4. オフライン検索評価の実行
```bash
# 標準評価セットを用いたモデル比較検証
uv run python scripts/evaluate_retrieval.py \
  --backend local \
  --model sentence-transformers/all-MiniLM-L6-v2 \
  --model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3
```

#### 5. 品質ゲート（検証スクリプト）
```bash
# フォーマット、型検査、脆弱性監査、テストを一括実行
bash scripts/verify.sh
```

#### 6. ロールバック手順
デプロイ中にカナリアリビジョンのヘルスチェックが失敗した場合、パイプラインは自動停止し旧リビジョンのトラフィックを 100% に維持します。手動で戻す場合：
```bash
az containerapp ingress traffic set \
  --name <app-name> \
  --resource-group <resource-group> \
  --revision <stable-revision-name>=100
```

---

### 主要な設計判断とトレードオフ

- **ローカル Embedding vs. API 呼び出し**: ローカル実行により API コストとレイテンシを削減できますが、コンテナイメージサイズ（約 1.5 GB）とメモリ使用量（2 GiB を推奨）が増加します。
- **Serverless ゼロスケール vs. コールドスタート**: ACA のゼロスケールはコスト削減に優れます。コールドスタートの影響は `/warmup` 呼び出しや本番環境で `min_replicas = 1` を維持することで抑制します。
- **インデックスのバージョン分離 (`ragdocs-v3`)**: Embedding モデルを更新する際、独立したインデックスを使用することで互換性のないベクトル空間の混在を防ぎます。
