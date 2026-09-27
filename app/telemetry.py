"""Metadata-only LLM observability through the existing Datadog Agent."""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

logger = logging.getLogger(__name__)


def _sdk() -> Any:
    # Keep tracing imports out of the default, uninstrumented cold-start path.
    if os.getenv("DD_LLMOBS_ENABLED", "false").lower() not in {"1", "true"}:
        return None
    from ddtrace.llmobs import LLMObs

    return LLMObs if LLMObs.enabled else None


def annotate(span: Any, *, tags: dict[str, Any] | None = None, metrics: dict[str, Any] | None = None) -> None:
    """Attach only explicitly supplied operational fields; never serialize arguments."""
    if span is None:
        return
    try:
        sdk = _sdk()
        if sdk is not None:
            sdk.annotate(
                span=span,
                tags={key: str(value) for key, value in (tags or {}).items() if value is not None},
                metrics={key: value for key, value in (metrics or {}).items() if value is not None},
            )
    except Exception:
        logger.warning("Datadog annotation unavailable")


@contextmanager
def observe(
    kind: Literal["workflow", "embedding", "retrieval", "llm"], name: str, **options: str
) -> Iterator[Any]:
    """Preserve application behavior when telemetry fails, including cancellation."""
    span = None
    try:
        sdk = _sdk()
        if sdk is not None:
            span = getattr(sdk, kind)(name=name, **options)
    except Exception:
        logger.warning("Datadog span unavailable")
    try:
        yield span
    except BaseException as exc:
        if span is not None:
            try:
                span.error = 1
                span.set_tag("error.type", type(exc).__name__)
                # Provider exceptions may contain request bodies. Export only the type.
                span.set_tag("error.message", "Operation failed")
            except Exception:
                logger.warning("Datadog error annotation unavailable")
        raise
    finally:
        if span is not None:
            try:
                span.finish()
            except Exception:
                logger.warning("Datadog span finalization unavailable")
