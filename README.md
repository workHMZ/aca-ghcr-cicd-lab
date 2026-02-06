# Serverless RAG API

[English](#english) | [中文](#中文) | [日本語](#日本語)

---

<a id="english"></a>
## 🇺🇸 English

A serverless RAG (Retrieval-Augmented Generation) API built with FastAPI, Azure AI Search, and OpenAI. Features local embedding with sentence-transformers to eliminate API costs, and full CI/CD pipeline deploying to Azure Container Apps via GitHub Actions.

### ✨ Features

- 🔍 **Hybrid Search** – Vector + keyword search for optimal retrieval
- 🧠 **Local Embedding** – Uses `all-MiniLM-L6-v2` (384-dim), zero API costs
- 🤖 **GPT-5-mini Responses** – OpenAI Responses API for answer generation
- 📦 **Containerized** – Multi-stage Docker build, deploys to Azure Container Apps
- 💰 **Student-Friendly** – Avoids costly services (ACR, Azure OpenAI)
- 🔄 **Full CI/CD** – GitHub Actions → GHCR → Azure Container Apps
- 🔒 **Security Scanning** – Trivy scans for image + dependency vulnerabilities (PR gate)
- 🐦 **Canary Deployment** – Progressive rollout (0% → 10% → 50% → 100%) with auto-rollback

### 🚀 Quick Start

#### 1. Install Dependencies

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

#### 2. Configure Environment

```bash
cp .env.example .env
# Fill in your Azure Search endpoint, API key, and OpenAI API key
```

#### 3. Create Index & Ingest Data

```bash
python scripts/create_index.py
python scripts/ingest.py  # Place documents in data/ first
```

#### 4. Run Locally

```bash
uvicorn app.main:app --reload
# Visit http://127.0.0.1:8000/docs
```

### 🔄 CI/CD Deployment

#### Prerequisites

- Azure subscription (Student subscription works)
- GitHub repository

#### Step 1: Create Azure Resources

```bash
./scripts/setup-azure.sh
```

This creates: Resource Group, Container Apps Environment, Container App, and Service Principal.

#### Step 2: Configure GitHub Secrets

Add these in **Settings → Secrets and variables → Actions**:

| Secret | Description |
|--------|-------------|
| `AZURE_CREDENTIALS` | JSON from setup-azure.sh output |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint |
| `AZURE_SEARCH_API_KEY` | Azure AI Search API key |
| `AZURE_SEARCH_INDEX_NAME` | Index name |
| `OPENAI_API_KEY` | OpenAI API key |

#### Step 3: Push to Deploy

```bash
git push origin main
```

CI builds and pushes to GHCR, CD deploys to Azure Container Apps automatically.

### 📁 Project Structure

```
├── app/
│   ├── main.py           # FastAPI application
│   ├── embed.py          # Sentence-transformers (384-dim)
│   └── search_client.py  # Azure AI Search client
├── scripts/
│   ├── create_index.py   # Create search index
│   ├── ingest.py         # Document ingestion
│   ├── test_api.py       # API testing script
│   └── setup-azure.sh    # Azure infrastructure setup
├── .github/workflows/
│   ├── ci.yml            # Build → Trivy → SBOM → Cosign → GHCR
│   ├── cd.yml            # Canary Deploy → Azure Container Apps
│   └── security.yml      # Trivy security scan (PR gate)
├── data/                 # Documents directory
├── Dockerfile            # Multi-stage build
└── requirements.txt
```

### 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.99.1 |
| Embedding | sentence-transformers (all-MiniLM-L6-v2, 384-dim) |
| Search | Azure AI Search (Free Tier) |
| LLM | OpenAI GPT-5-mini (Responses API) |
| Container | Docker + GHCR |
| Deployment | Azure Container Apps (Canary) |
| CI/CD | GitHub Actions + Trivy + Cosign |

---

<a id="中文"></a>
## 🇨🇳 中文

基于 FastAPI、Azure AI Search 和 OpenAI 构建的无服务器 RAG（检索增强生成）API。采用本地 sentence-transformers 进行向量化以消除 API 成本，并通过 GitHub Actions 实现完整的 CI/CD 流水线部署到 Azure Container Apps。

### ✨ 特点

- 🔍 **混合检索** – 向量搜索 + 关键词搜索，检索效果最优
- 🧠 **本地 Embedding** – 使用 `all-MiniLM-L6-v2`（384 维），零 API 成本
- 🤖 **GPT-5-mini 回答** – 使用 OpenAI Responses API 生成回答
- 📦 **容器化部署** – 多阶段 Docker 构建，部署到 Azure Container Apps
- 💰 **学生友好** – 避开高成本服务（ACR、Azure OpenAI）
- 🔄 **完整 CI/CD** – GitHub Actions → GHCR → Azure Container Apps
- 🔒 **安全扫描** – Trivy 镜像 + 依赖漏洞扫描（PR 门禁）
- 🐦 **金丝雀部署** – 渐进式发布（0% → 10% → 50% → 100%）+ 自动回滚

### 🚀 快速开始

#### 1. 安装依赖

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
cp .env.example .env
# 填入你的 Azure Search 端点、API Key 和 OpenAI API Key
```

#### 3. 创建索引并导入数据

```bash
python scripts/create_index.py
python scripts/ingest.py  # 先将文档放入 data/ 目录
```

#### 4. 本地运行

```bash
uvicorn app.main:app --reload
# 访问 http://127.0.0.1:8000/docs
```

### 🔄 CI/CD 部署

#### 前置条件

- Azure 订阅（学生订阅可用）
- GitHub 仓库

#### Step 1: 创建 Azure 资源

```bash
./scripts/setup-azure.sh
```

此脚本会创建：资源组、Container Apps 环境、Container App 和 Service Principal。

#### Step 2: 配置 GitHub Secrets

在 **Settings → Secrets and variables → Actions** 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `AZURE_CREDENTIALS` | setup-azure.sh 输出的 JSON |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search 端点 |
| `AZURE_SEARCH_API_KEY` | Azure AI Search API Key |
| `AZURE_SEARCH_INDEX_NAME` | 索引名称 |
| `OPENAI_API_KEY` | OpenAI API Key |

#### Step 3: 推送代码触发部署

```bash
git push origin main
```

CI 自动构建镜像推送到 GHCR，CD 自动部署到 Azure Container Apps。

### 📁 项目结构

```
├── app/
│   ├── main.py           # FastAPI 应用入口
│   ├── embed.py          # sentence-transformers（384 维）
│   └── search_client.py  # Azure AI Search 客户端
├── scripts/
│   ├── create_index.py   # 创建搜索索引
│   ├── ingest.py         # 文档导入
│   ├── test_api.py       # API 测试脚本
│   └── setup-azure.sh    # Azure 基础设施创建脚本
├── .github/workflows/
│   ├── ci.yml            # 构建 → Trivy → SBOM → Cosign → GHCR
│   ├── cd.yml            # 金丝雀部署 → Azure Container Apps
│   └── security.yml      # Trivy 安全扫描（PR 门禁）
├── data/                 # 文档目录
├── Dockerfile            # 多阶段构建
└── requirements.txt
```

### 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | FastAPI 0.99.1 |
| 向量化 | sentence-transformers (all-MiniLM-L6-v2, 384 维) |
| 检索 | Azure AI Search (Free Tier) |
| 大模型 | OpenAI GPT-5-mini (Responses API) |
| 容器 | Docker + GHCR |
| 部署 | Azure Container Apps（金丝雀） |
| CI/CD | GitHub Actions + Trivy + Cosign |

---

<a id="日本語"></a>
## 🇯🇵 日本語

FastAPI、Azure AI Search、OpenAI を使用したサーバーレス RAG（検索拡張生成）API。API コストを削減するためにローカルの sentence-transformers を使用したベクトル化と、GitHub Actions による Azure Container Apps への完全な CI/CD パイプラインを実装しています。

### ✨ 特徴

- 🔍 **ハイブリッド検索** – ベクトル検索 + キーワード検索で最適な検索結果
- 🧠 **ローカル Embedding** – `all-MiniLM-L6-v2`（384次元）を使用、API コストゼロ
- 🤖 **GPT-5-mini 回答生成** – OpenAI Responses API による回答生成
- 📦 **コンテナ化** – マルチステージ Docker ビルド、Azure Container Apps にデプロイ
- 💰 **学生向け** – 高コストサービス（ACR、Azure OpenAI）を回避
- 🔄 **完全な CI/CD** – GitHub Actions → GHCR → Azure Container Apps
- 🔒 **セキュリティスキャン** – Trivy によるイメージ + 依存関係の脆弱性スキャン（PR ゲート）
- 🐦 **カナリアデプロイ** – 段階的リリース（0% → 10% → 50% → 100%）+ 自動ロールバック

### 🚀 クイックスタート

#### 1. 依存関係のインストール

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

#### 2. 環境変数の設定

```bash
cp .env.example .env
# Azure Search エンドポイント、API キー、OpenAI API キーを入力
```

#### 3. インデックス作成とデータ取り込み

```bash
python scripts/create_index.py
python scripts/ingest.py  # まず data/ ディレクトリにドキュメントを配置
```

#### 4. ローカル実行

```bash
uvicorn app.main:app --reload
# http://127.0.0.1:8000/docs にアクセス
```

### 🔄 CI/CD デプロイメント

#### 前提条件

- Azure サブスクリプション（学生サブスクリプション可）
- GitHub リポジトリ

#### Step 1: Azure リソースの作成

```bash
./scripts/setup-azure.sh
```

このスクリプトで作成されるもの：リソースグループ、Container Apps 環境、Container App、Service Principal

#### Step 2: GitHub Secrets の設定

**Settings → Secrets and variables → Actions** で以下を追加：

| Secret 名 | 説明 |
|----------|------|
| `AZURE_CREDENTIALS` | setup-azure.sh の出力 JSON |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search エンドポイント |
| `AZURE_SEARCH_API_KEY` | Azure AI Search API キー |
| `AZURE_SEARCH_INDEX_NAME` | インデックス名 |
| `OPENAI_API_KEY` | OpenAI API キー |

#### Step 3: プッシュしてデプロイ

```bash
git push origin main
```

CI が自動でイメージをビルドして GHCR にプッシュし、CD が Azure Container Apps に自動デプロイします。

### 📁 プロジェクト構造

```
├── app/
│   ├── main.py           # FastAPI アプリケーション
│   ├── embed.py          # sentence-transformers（384次元）
│   └── search_client.py  # Azure AI Search クライアント
├── scripts/
│   ├── create_index.py   # 検索インデックス作成
│   ├── ingest.py         # ドキュメント取り込み
│   ├── test_api.py       # API テストスクリプト
│   └── setup-azure.sh    # Azure インフラ構築スクリプト
├── .github/workflows/
│   ├── ci.yml            # ビルド → Trivy → SBOM → Cosign → GHCR
│   ├── cd.yml            # カナリアデプロイ → Azure Container Apps
│   └── security.yml      # Trivy セキュリティスキャン（PR ゲート）
├── data/                 # ドキュメントディレクトリ
├── Dockerfile            # マルチステージビルド
└── requirements.txt
```

### 🛠 技術スタック

| コンポーネント | 技術 |
|--------------|------|
| フレームワーク | FastAPI 0.99.1 |
| ベクトル化 | sentence-transformers (all-MiniLM-L6-v2, 384次元) |
| 検索 | Azure AI Search（Free Tier） |
| LLM | OpenAI GPT-5-mini (Responses API) |
| コンテナ | Docker + GHCR |
| デプロイ | Azure Container Apps（カナリア） |
| CI/CD | GitHub Actions + Trivy + Cosign |

---

## 📄 License

[Apache-2.0](LICENSE)

