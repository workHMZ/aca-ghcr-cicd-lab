这套流程设计得非常棒。它精准地避开了 Azure 学生订阅的“扣费陷阱”（如 ACR、Gateway），同时保留了“企业级架构”的核心骨架（ACA + AI Search + Entra ID）。
特别是你提到的 mock embedding 思路，对于验证工程链路非常有效。但既然我们要让面试官眼前一亮，我建议在代码实现时做一个微小的升级：引入一个轻量级的本地 Embedding 模型（sentence-transformers）。这不会增加任何云成本（跑在你的 CPU/Container 里），但能让你的 RAG 真正具备“语义搜索”能力，而不是返回随机结果。
下面我按照你的清单，带你完成 第 0 步 到 第 3 步 的核心代码实现。
第 0 步：准备工作与环境配置
先在本地建立项目结构。请务必添加 .gitignore，防止把 .env 里的 Key 推送到 GitHub（这是初学者最容易犯的错误）。
目录结构：
serverless-rag-api/
├── .env                # 你的密钥 (不要提交!)
├── .gitignore          # 新增
├── Dockerfile
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── embed.py        # 向量化逻辑
│   └── search_client.py
├── scripts/
│   ├── create_index.py
│   └── ingest.py
└── data/               # 放你的 PDF/MD 文件

1. .gitignore 内容：
__pycache__/
.env
.venv/
.DS_Store
data/

2. requirements.txt (稍微调整以支持本地向量模型)：
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-dotenv==1.0.1
azure-core==1.34.0
azure-search-documents==11.6.0b12
numpy==1.26.4
pypdf==4.3.1
# 新增：用于生成真实的语义向量 (CPU友好，模型很小)
sentence-transformers==2.7.0

第 1 步：核心代码实现 (FastAPI + Embedding)
这里我们将 Embedding 升级为 all-MiniLM-L6-v2。它生成的向量维度是 384（请记住这个数字，后面建索引要用），而不是 OpenAI 的 1536。
1. app/embed.py (升级版)：
from sentence_transformers import SentenceTransformer

# 这是一个非常轻量的模型，首次运行会自动下载 (~80MB)，缓存在本地
# 在容器里运行时，也会下载到容器内
model = SentenceTransformer('all-MiniLM-L6-v2')

def embed_text(text: str) -> list[float]:
    """
    生成真实的语义向量。
    模型: all-MiniLM-L6-v2
    维度: 384
    """
    if not text:
        return []
    # convert to list for JSON serialization
    return model.encode(text).tolist()

def get_dimension() -> int:
    return 384

2. app/search_client.py (保持不变，封装好)：
import os
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

def get_search_client() -> SearchClient:
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
    api_key = os.environ["AZURE_SEARCH_API_KEY"]
    
    return SearchClient(
        endpoint=endpoint, 
        index_name=index_name, 
        credential=AzureKeyCredential(api_key)
    )

3. app/main.py (API 主入口)：
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from azure.search.documents.models import VectorizedQuery
from app.embed import embed_text, get_dimension
from app.search_client import get_search_client

load_dotenv(override=True)

app = FastAPI(title="Serverless RAG API", version="0.1.0")

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=10)

class ContextHit(BaseModel):
    id: str
    source: str | None = None
    score: float | None = None
    content: str

class QueryResponse(BaseModel):
    answer: str
    contexts: list[ContextHit]

@app.get("/health")
def health():
    return {"status": "ok", "service": "azure-rag-student"}

@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    # 1. 生成向量
    qvec = embed_text(req.question)
    
    # 2. 构造向量查询
    vector_query = VectorizedQuery(
        vector=qvec,
        k_nearest_neighbors=req.top_k,
        fields="contentVector",
        exhaustiveness=True # 小数据集建议开启，保证召回率
    )

    search_client = get_search_client()

    # 3. 执行检索 (Hybrid: Vector + Keyword)
    try:
        results = search_client.search(
            search_text=req.question, # 混合检索的关键
            vector_queries=[vector_query],
            top=req.top_k,
            select=["id", "content", "source", "createdAt"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    # 4. 格式化结果
    contexts = []
    for r in results:
        contexts.append(ContextHit(
            id=r.get("id"),
            source=r.get("source"),
            score=r.get("@search.score"),
            content=r.get("content"),
        ))

    # Mock answer (下一阶段再接 LLM)
    mock_answer = f"基于检索到的 {len(contexts)} 个片段，我分析如下... (这里是 Mock 回答)"
    
    return QueryResponse(answer=mock_answer, contexts=contexts)

第 2 步：Azure AI Search 索引创建
去 Azure Portal 创建好 Search Service（Free Tier），拿到 Endpoint 和 Key 填入 .env。
scripts/create_index.py (关键修正：维度 384)：
import os
import sys
# 添加父目录到 sys.path 以便导入 app 模块
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SearchableField, SimpleField, VectorSearch,
    VectorSearchProfile, HnswAlgorithmConfiguration
)
from app.embed import get_dimension

load_dotenv(override=True)

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
api_key = os.environ["AZURE_SEARCH_API_KEY"]

def create_index():
    client = SearchIndexClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
    dim = get_dimension() # 获取 384

    # 定义字段
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="zh-Hans.microsoft"), # 加上中文分词器，面试加分细节！
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dim, # 必须是 384
            vector_search_profile_name="my-vector-profile"
        ),
        SearchableField(name="source", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="createdAt", type=SearchFieldDataType.String)
    ]

    # 配置向量算法 (HNSW)
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="my-hnsw-config", kind="hnsw")],
        profiles=[VectorSearchProfile(name="my-vector-profile", algorithm_configuration_name="my-hnsw-config")]
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    
    print(f"Creating index '{index_name}' with dimension {dim}...")
    client.create_or_update_index(index)
    print("✅ Index created successfully!")

if __name__ == "__main__":
    create_index()

第 3 步：Ingestion (写入数据)
把你的 PDF/MD 文件放到 data/ 目录下。
scripts/ingest.py：
import os
import sys
import glob
from uuid import uuid4
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from pypdf import PdfReader
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from app.embed import embed_text

load_dotenv(override=True)

endpoint = os.environ["AZURE_SEARCH_ENDPOINT"]
index_name = os.environ["AZURE_SEARCH_INDEX_NAME"]
api_key = os.environ["AZURE_SEARCH_API_KEY"]

def read_pdf(path):
    reader = PdfReader(path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def chunk_text(text, size=500):
    # 简单的切分，生产环境推荐用 LangChain RecursiveCharacterTextSplitter
    return [text[i:i+size] for i in range(0, len(text), size)]

def main():
    client = SearchClient(endpoint=endpoint, index_name=index_name, credential=AzureKeyCredential(api_key))
    
    # 扫描 data 目录
    files = glob.glob("data/*.pdf") + glob.glob("data/*.md")
    docs_to_upload = []

    print(f"Found {len(files)} files.")

    for file_path in files:
        filename = os.path.basename(file_path)
        print(f"Processing {filename}...")
        
        if file_path.endswith(".pdf"):
            content = read_pdf(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

        chunks = chunk_text(content)
        
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            doc = {
                "id": f"{uuid4()}", # 生成唯一ID
                "content": chunk,
                "contentVector": embed_text(chunk),
                "source": filename,
                "createdAt": datetime.now().isoformat()
            }
            docs_to_upload.append(doc)

    if docs_to_upload:
        print(f"Uploading {len(docs_to_upload)} chunks...")
        # 批量上传
        client.upload_documents(documents=docs_to_upload)
        print("✅ Ingestion complete.")
    else:
        print("No documents to upload.")

if __name__ == "__main__":
    main()

现在的任务清单
请在本地执行以下操作，测试代码是否跑通：
 * 安装依赖： pip install -r requirements.txt
 * 创建索引： python scripts/create_index.py (确保 .env 填好了)
 * 写入数据： python scripts/ingest.py
 * 启动 API： uvicorn app.main:app --reload
 * 测试查询：
   打开浏览器访问 http://127.0.0.1:8000/docs，在 POST /query 里输入：
   {
  "question": "这里写你PDF里的某个关键词",
  "top_k": 3
}

告诉我你的测试结果！ 如果这一步跑通了（能搜到数据），我们下一条立刻做 Docker 镜像构建 + 推送到 GHCR，然后正式上云。
