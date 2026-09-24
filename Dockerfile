# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

FROM ghcr.io/astral-sh/uv:0.12.18@sha256:3adc3706091ce7c2fe595e669628caedd6d951551b92b258b7e7dbe06d9440bc AS uv
FROM ${PYTHON_IMAGE} AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Install only locked production dependencies (ONNX Runtime, no PyTorch).
# Application source is copied in the runtime stage, so dependency layers
# remain cacheable across code changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Fetch the pinned ONNX model with the standard library only. The manifest
# pins the Hugging Face revision and the SHA-256 of every file, so this layer
# is invalidated only when the manifest changes.
FROM ${PYTHON_IMAGE} AS model

ARG EMBEDDING_VARIANT=onnx-qint8
ARG EMBEDDING_MODEL_PATH=/opt/models/multilingual-e5-small

WORKDIR /build
COPY app/__init__.py app/model_manifest.py ./app/
RUN python -m app.model_manifest --download "${EMBEDDING_MODEL_PATH}" --variant "${EMBEDDING_VARIANT}"

FROM ${PYTHON_IMAGE} AS runtime

ARG APP_VERSION=unknown
ARG BUILD_SHA=unknown
ARG IMAGE_TAG=unknown
ARG EMBEDDING_VARIANT=onnx-qint8
ARG EMBEDDING_MODEL_PATH=/opt/models/multilingual-e5-small

# Datadog tracing is opt-in: with DD_TRACE_ENABLED=true (set by CD when the
# Agent sidecar is deployed) uvicorn runs under ddtrace-run with ddtrace's
# normal defaults; otherwise the tracer is never started.
ENV PATH=/opt/venv/bin:$PATH \
    HOME=/home/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=${APP_VERSION} \
    BUILD_SHA=${BUILD_SHA} \
    IMAGE_TAG=${IMAGE_TAG} \
    DD_VERSION=${APP_VERSION} \
    DD_TRACE_ENABLED=false \
    EMBEDDING_VARIANT=${EMBEDDING_VARIANT} \
    EMBEDDING_MODEL_PATH=${EMBEDDING_MODEL_PATH} \
    EMBEDDING_OFFLINE=1

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-log-init --create-home --home-dir /home/app app

WORKDIR /app

COPY --from=builder --chown=10001:10001 /opt/venv /opt/venv
COPY --from=model --chown=10001:10001 /opt/models /opt/models
COPY --chown=10001:10001 app/ ./app/

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"]

CMD ["python", "-m", "app"]
