# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install only locked production dependencies. Application source is copied in
# the runtime stage, so dependency layers remain cacheable across code changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Pin the embedding model to an immutable Hugging Face revision and store it in
# the image. Runtime network access to Hugging Face is intentionally disabled.
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
ARG EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
ARG EMBEDDING_MODEL_PATH=/opt/models/multilingual-e5-small
RUN --mount=type=cache,target=/root/.cache/huggingface \
    EMBEDDING_MODEL="${EMBEDDING_MODEL}" \
    EMBEDDING_MODEL_REVISION="${EMBEDDING_MODEL_REVISION}" \
    EMBEDDING_MODEL_PATH="${EMBEDDING_MODEL_PATH}" \
    /opt/venv/bin/python -c \
    'import os; from sentence_transformers import SentenceTransformer; model = SentenceTransformer(os.environ["EMBEDDING_MODEL"], revision=os.environ["EMBEDDING_MODEL_REVISION"]); model.save(os.environ["EMBEDDING_MODEL_PATH"])'

FROM ${PYTHON_IMAGE} AS runtime

ARG APP_VERSION=unknown
ARG BUILD_SHA=unknown
ARG IMAGE_TAG=unknown
ARG EMBEDDING_MODEL=intfloat/multilingual-e5-small
ARG EMBEDDING_MODEL_REVISION=614241f622f53c4eeff9890bdc4f31cfecc418b3
ARG EMBEDDING_MODEL_PATH=/opt/models/multilingual-e5-small

ENV PATH=/opt/venv/bin:$PATH \
    HOME=/home/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    BUILD_SHA=${BUILD_SHA} \
    IMAGE_TAG=${IMAGE_TAG} \
    DD_VERSION=${APP_VERSION} \
    EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    EMBEDDING_MODEL_REVISION=${EMBEDDING_MODEL_REVISION} \
    EMBEDDING_MODEL_PATH=${EMBEDDING_MODEL_PATH} \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-log-init --create-home --home-dir /home/app app

WORKDIR /app

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --from=builder --chown=10001:10001 /opt/models /opt/models
COPY --chown=10001:10001 app/ ./app/

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]

CMD ["ddtrace-run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
