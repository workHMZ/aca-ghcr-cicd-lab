# Multi-stage build for efficient container / 効率的なコンテナのためのマルチステージビルド
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies / ビルド依存関係のインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies / Python 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage / 本番ステージ
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder / ビルダーからインストール済みパッケージをコピー
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Build-time version info (injected by CI) / ビルド時のバージョン情報（CI から注入）
ARG APP_VERSION=unknown
ARG BUILD_SHA=unknown
ARG IMAGE_TAG=unknown
ENV APP_VERSION=$APP_VERSION
ENV BUILD_SHA=$BUILD_SHA
ENV IMAGE_TAG=$IMAGE_TAG
ENV DD_VERSION=$APP_VERSION

# Copy application code / アプリケーションコードをコピー
COPY app/ ./app/

# Pre-download embedding model during build (cache in image)
# ビルド時に埋め込みモデルを事前ダウンロード（イメージにキャッシュ）
ARG PRELOAD_EMBEDDING_MODEL=1
RUN if [ "$PRELOAD_EMBEDDING_MODEL" = "1" ]; then \
      python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"; \
    else \
      echo "Skipping embedding model preload (PRELOAD_EMBEDDING_MODEL=$PRELOAD_EMBEDDING_MODEL)"; \
    fi

# Expose port / ポートの公開
EXPOSE 8000

# Health check / ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application with Datadog APM tracer / Datadog APM トレーサーでアプリケーションを実行
CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
