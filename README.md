# Serverless RAG API

[English](#english) | [中文](#中文) | [日本語](#日本語)

## 📁 Project Structure / 项目结构 / プロジェクト構造

```text
├── app/
│   ├── __init__.py                        # Package version
│   ├── main.py                            # FastAPI application + Datadog JSON logging
│   ├── embed.py                           # Sentence-transformers embedding (384-dim)
│   └── search_client.py                   # Azure AI Search client factory
├── scripts/
│   ├── create_index.py                    # Create Azure AI Search index (HNSW)
│   ├── ingest.py                          # Document ingestion (PDF/MD/TXT → chunks)
│   ├── clear_index.py                     # Clear all documents from index
│   ├── deploy_canary.sh                   # Canary rollout logic (0→10→50→100%)
│   ├── setup-azure.sh                     # Azure infrastructure provisioning
│   ├── test_api.py                        # API smoke test
│   ├── sync_datadog_catalog.sh            # Datadog Service Catalog sync
│   └── send_datadog_dora_deployment.sh    # Datadog DORA deployment event
├── .github/workflows/
│   ├── ci.yml                             # Build → Trivy → SBOM → Cosign → GHCR
│   ├── cd.yml                             # Canary Deploy → ACA → DORA Metrics
│   └── security.yml                       # Trivy vulnerability scan (PR gate)
├── data/                                  # Source documents (PDF/MD/TXT)
├── service.datadog.yaml                   # Datadog Service Catalog metadata
├── Dockerfile                             # Multi-stage build (ddtrace-run)
└── requirements.txt
```

---

<a id="english"></a>
## 🇺🇸 English

A production-ready, serverless RAG (Retrieval-Augmented Generation) API. Built with FastAPI and Azure AI Search, it eliminates recurring embedding API costs by running `sentence-transformers` locally. The project showcases robust engineering practices, including a full CI/CD pipeline, canary deployments, and deep Datadog observability—making it an ideal reference architecture for scalable AI applications.

### ✨ Key Features & Engineering Highlights

- **Cost-Optimized Hybrid RAG**: Combines vector and keyword search (Azure AI Search) with local `all-MiniLM-L6-v2` embeddings, eliminating recurring embedding API costs. Uses GPT-5 for generation.
- **Progressive Delivery (Canary)**: Zero-downtime deployments to Azure Container Apps with automated traffic shifting (0% → 10% → 50% → 100%), health checks, and auto-rollback.
- **Supply Chain Security**: Cosign keyless signing (OIDC), SBOM generation (CycloneDX), and Trivy vulnerability scanning — all automated in CI.
- **Enterprise Observability**: Datadog APM (`ddtrace`) with structured JSON logging, trace correlation, DORA metrics, and Service Catalog sync.

### 🔄 CI/CD Pipeline Flow
```text
git push main
  └─ CI: Build → Trivy Scan → Push GHCR → SBOM → Cosign Sign → Catalog Sync
       └─ CD: Cosign Verify → Deploy ACA → Canary (0→10→50→100%) → DORA Event
           └─ PR: Trivy Filesystem + Image Scan (Security Gate)
```

### 🛠 Tech Stack
- **Application**: Python 3.12, FastAPI, Sentence-Transformers, OpenAI GPT-5
- **Cloud & Infra**: Azure Container Apps, Azure AI Search, GHCR, Docker
- **CI/CD & Security**: GitHub Actions, Trivy, Cosign (OIDC), Syft (SBOM)
- **Observability**: Datadog APM / DORA Metrics / Service Catalog

### 🚀 Quick Start
```bash
# 1. Install dependencies
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Configure Environment (.env)
cp .env.example .env
# Set: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME, OPENAI_API_KEY

# 3. Create Index & Ingest Data
python scripts/create_index.py
python scripts/ingest.py # Put your PDF/MD/TXT documents in data/

# 4. Configure GitHub Secrets (Settings → Secrets and variables → Actions)
# Required for CI/CD pipeline:
# - AZURE_CREDENTIALS: JSON output from Azure Service Principal creation
# - AZURE_SEARCH_ENDPOINT: Your Azure AI Search endpoint
# - AZURE_SEARCH_API_KEY: Your Azure AI Search API key
# - AZURE_SEARCH_INDEX_NAME: The name of your index
# - OPENAI_API_KEY: Your OpenAI API key
# - GHCR_USERNAME: Your GitHub username (for Container Registry)
# - GHCR_TOKEN: Your GitHub PAT with read/write packages scope
# - DD_API_KEY: Datadog API Key (for APM)
# - DD_APP_KEY: Datadog Application Key (for Service Catalog)

# 5. Run Locally
uvicorn app.main:app --reload
```


---

<a id="中文"></a>
## 🇨🇳 中文

这是一个生产级标准的 Serverless RAG (检索增强生成) API。基于 FastAPI 和 Azure AI Search 构建，通过在本地运行 `sentence-transformers` 进行向量化，实现了零 Embedding API 成本。本项目不仅实现了核心算法，更展示了成熟的工程化实践，包含完整的 CI/CD 流水线、金丝雀发布以及深度的 Datadog 可观测性集成。

### ✨ 核心特性与工程亮点

- **成本优化的混合 RAG**：结合向量与关键词检索（Azure AI Search），配合本地 `all-MiniLM-L6-v2` 模型进行向量化，彻底免除 Embedding API 开销，并使用 GPT-5 进行内容生成。
- **渐进式交付（金丝雀发布）**：在 Azure Container Apps 上实现零故障部署，支持自动流量切换 (0% → 10% → 50% → 100%)、健康检查验证及自动回滚。
- **供应链安全**：Cosign 无密钥签名 (OIDC)、SBOM 生成 (CycloneDX) 以及 Trivy 漏洞扫描全部自动化集成在 CI 中。
- **企业级可观测性**：深度集成 Datadog APM (`ddtrace`)，支持结构化 JSON 日志、Trace 关联、DORA 指标追踪以及 Service Catalog 同步。

### 🔄 CI/CD 流水线流程
```text
git push main
  └─ CI: 构建 → Trivy 扫描 → 推送 GHCR → SBOM → Cosign 签名 → Catalog 同步
       └─ CD: Cosign 验签 → 部署 ACA → 金丝雀 (0→10→50→100%) → DORA 上报
           └─ PR: Trivy 文件系统 + 镜像扫描（安全门禁）
```

### 🛠 技术栈
- **应用层**：Python 3.12, FastAPI, Sentence-Transformers, OpenAI GPT-5
- **云底座**：Azure Container Apps, Azure AI Search, GHCR, Docker
- **CI/CD 与安全**：GitHub Actions, Trivy, Cosign (OIDC), Syft (SBOM)
- **可观测性**：Datadog APM / DORA Metrics / Service Catalog

### 🚀 快速上手
```bash
# 1. 安装依赖
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. 配置环境变量 (.env)
cp .env.example .env
# 需填入: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME, OPENAI_API_KEY

# 3. 创建索引并导入数据
python scripts/create_index.py
python scripts/ingest.py # 将 PDF/MD/TXT 文档放入 data/ 目录即可

# 4. 配置 GitHub Secrets (Settings → Secrets and variables → Actions)
# CI/CD 流水线必需的机密变量：
# - AZURE_CREDENTIALS: 创建 Azure Service Principal 时的 JSON 输出
# - AZURE_SEARCH_ENDPOINT: Azure AI Search 端点
# - AZURE_SEARCH_API_KEY: Azure AI Search API 密钥
# - AZURE_SEARCH_INDEX_NAME: 索引名称
# - OPENAI_API_KEY: OpenAI API 密钥
# - GHCR_USERNAME: GitHub 用户名（用于推送容器镜像）
# - GHCR_TOKEN: GitHub PAT（需包含包读写权限）
# - DD_API_KEY: Datadog API Key (用于 APM)
# - DD_APP_KEY: Datadog Application Key (用于服务目录同步)

# 5. 本地启动
uvicorn app.main:app --reload
```


---

<a id="日本語"></a>
## 🇯🇵 日本語

本番環境レベルのサーバーレス RAG (検索拡張生成) API です。FastAPI と Azure AI Search を基盤とし、ローカルで `sentence-transformers` を実行することで、埋め込み (Embedding) API のコストをゼロに抑えています。単なる API 実装にとどまらず、完全な CI/CD パイプライン、カナリアリリース、Datadog による高度な可観測性など、スケーラブルな AI アプリケーションのための実践的なエンジニアリング手法を網羅しています。

### ✨ 主な特徴とエンジニアリングのハイライト

- **コスト最適化されたハイブリッド RAG**: ベクトル検索とキーワード検索（Azure AI Search）を組み合わせ、ローカルの `all-MiniLM-L6-v2` モデルを活用。埋め込み API のランニングコストを完全に排除しました。生成には GPT-5 を使用します。
- **プログレッシブデリバリー（カナリアリリース）**: Azure Container Apps へのゼロダウンタイムデプロイ。自動トラフィック移行（0% → 10% → 50% → 100%）、ヘルスチェック、および自動ロールバック機構を備えています。
- **サプライチェーンセキュリティ**: Cosign キーレス署名 (OIDC)、SBOM 生成 (CycloneDX)、Trivy 脆弱性スキャンを CI で完全自動化。
- **エンタープライズ級の可観測性**: Datadog APM (`ddtrace`) との完全な統合。構造化 JSON ログ、トレース相関、DORA メトリクス追跡、Service Catalog 同期を実装しています。

### 🔄 CI/CD パイプラインフロー
```text
git push main
  └─ CI: ビルド → Trivy スキャン → GHCR プッシュ → SBOM → Cosign 署名 → Catalog 同期
       └─ CD: Cosign 検証 → ACA デプロイ → カナリア (0→10→50→100%) → DORA 送信
           └─ PR: Trivy ファイルシステム + イメージスキャン（セキュリティゲート）
```

### 🛠 技術スタック
- **アプリケーション**: Python 3.12, FastAPI, Sentence-Transformers, OpenAI GPT-5
- **インフラストラクチャ**: Azure Container Apps, Azure AI Search, GHCR, Docker
- **CI/CD ・ セキュリティ**: GitHub Actions, Trivy, Cosign (OIDC), Syft (SBOM)
- **可観測性**: Datadog APM / DORA Metrics / Service Catalog

### 🚀 クイックスタート
```bash
# 1. 依存関係のインストール
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 2. 環境変数の設定 (.env)
cp .env.example .env
# AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, AZURE_SEARCH_INDEX_NAME, OPENAI_API_KEY を設定

# 3. インデックス作成とデータ取り込み
python scripts/create_index.py
python scripts/ingest.py # ドキュメント (PDF/MD/TXT) を data/ フォルダに配置

# 4. GitHub Secrets の設定 (Settings → Secrets and variables → Actions)
# CI/CD パイプラインに必要なシークレット：
# - AZURE_CREDENTIALS: Azure Service Principal 作成時の JSON 出力
# - AZURE_SEARCH_ENDPOINT: Azure AI Search エンドポイント
# - AZURE_SEARCH_API_KEY: Azure AI Search API キー
# - AZURE_SEARCH_INDEX_NAME: インデックス名
# - OPENAI_API_KEY: OpenAI API キー
# - GHCR_USERNAME: GitHub ユーザー名（コンテナレジストリ用）
# - GHCR_TOKEN: GitHub PAT（パッケージの読み書き権限）
# - DD_API_KEY: Datadog API Key (APM用)
# - DD_APP_KEY: Datadog Application Key (Service Catalog同期用)

# 5. ローカル実行
uvicorn app.main:app --reload
```


