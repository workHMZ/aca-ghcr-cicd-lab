# Serverless RAG API

基于 Azure AI Search + FastAPI 的无服务器 RAG 检索系统。

## ✨ 特点

- 🔍 **混合检索**：向量搜索 + 关键词搜索（Hybrid Search）
- 🧠 **本地 Embedding**：使用 `all-MiniLM-L6-v2`，无 API 成本
- 📦 **容器化部署**：支持部署到 Azure Container Apps
- 💰 **学生友好**：避开 ACR、Azure OpenAI 等付费服务
- 🔄 **CI/CD**：GitHub Actions 自动构建推送到 GHCR

## 🚀 快速开始

### 1. 安装依赖

```bash
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 Azure Search Endpoint 和 API Key
```

### 3. 创建索引 & 导入数据

```bash
python scripts/create_index.py
python scripts/ingest.py  # 需先将文档放入 data/ 目录
```

### 4. 启动 API

```bash
uvicorn app.main:app --reload
# 访问 http://127.0.0.1:8000/docs
```

## 🔄 CI/CD 部署

### 前置条件

1. Azure 订阅（学生订阅可用）
2. GitHub 仓库

### Step 1: 创建 Azure 资源

```bash
./scripts/setup-azure.sh
```

此脚本会创建：
- Resource Group
- Container Apps Environment  
- Container App
- Service Principal (用于 GitHub Actions)

### Step 2: 配置 GitHub Secrets

在 GitHub 仓库的 Settings → Secrets and variables → Actions 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `AZURE_CREDENTIALS` | setup-azure.sh 输出的 JSON |
| `AZURE_SEARCH_ENDPOINT` | Azure Search 端点 |
| `AZURE_SEARCH_API_KEY` | Azure Search API Key |
| `AZURE_SEARCH_INDEX_NAME` | 索引名称 |

### Step 3: 推送代码触发部署

```bash
git add . && git commit -m "feat: initial RAG API"
git push origin main
```

CI 会自动构建镜像推送到 GHCR，CD 会部署到 Container Apps。

## 📁 项目结构

```
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── embed.py          # sentence-transformers 384维
│   └── search_client.py  # Azure Search 客户端
├── scripts/
│   ├── create_index.py   # 创建索引
│   ├── ingest.py         # 数据导入
│   └── setup-azure.sh    # Azure 基础设施
├── .github/workflows/
│   ├── ci.yml            # 构建 → GHCR
│   └── cd.yml            # 部署 → ACA
├── data/                 # 文档目录
├── Dockerfile
└── requirements.txt
```

## 📝 技术栈

- **框架**：FastAPI 0.115.0
- **向量化**：sentence-transformers (all-MiniLM-L6-v2, 384 维)
- **检索**：Azure AI Search (Free Tier)
- **部署**：Azure Container Apps + GHCR
- **CI/CD**：GitHub Actions
