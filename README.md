# Serverless RAG API

[English](#english) | [中文](#中文)

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
│   ├── ci.yml            # Build → GHCR
│   └── cd.yml            # Deploy → Azure Container Apps
├── data/                 # Documents directory
├── Dockerfile            # Multi-stage build
└── requirements.txt
```

### 🛠 Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI 0.115.0 |
| Embedding | sentence-transformers (all-MiniLM-L6-v2, 384-dim) |
| Search | Azure AI Search (Free Tier) |
| LLM | OpenAI GPT-5-mini (Responses API) |
| Container | Docker + GHCR |
| Deployment | Azure Container Apps |
| CI/CD | GitHub Actions |

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
│   ├── ci.yml            # 构建 → GHCR
│   └── cd.yml            # 部署 → Azure Container Apps
├── data/                 # 文档目录
├── Dockerfile            # 多阶段构建
└── requirements.txt
```

### 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 框架 | FastAPI 0.115.0 |
| 向量化 | sentence-transformers (all-MiniLM-L6-v2, 384 维) |
| 检索 | Azure AI Search (Free Tier) |
| 大模型 | OpenAI GPT-5-mini (Responses API) |
| 容器 | Docker + GHCR |
| 部署 | Azure Container Apps |
| CI/CD | GitHub Actions |

---

## 📄 License

[Apache-2.0](LICENSE)
