"""Container entrypoint: start uvicorn, wrapped by ddtrace-run only when tracing is on.

Skipping ddtrace-run when DD_TRACE_ENABLED is false avoids importing the
tracer on every cold start of the default (Agent-less) deployment.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

TRUTHY = {"1", "true", "yes", "on"}


def command(environ: Mapping[str, str] = os.environ) -> list[str]:
    args = [
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",  # noqa: S104 - the container must listen on its external interface
        "--port",
        environ.get("PORT", "8000"),
        # ACA ingress is the only client; trust its X-Forwarded-For for access logs.
        "--proxy-headers",
        "--forwarded-allow-ips",
        "*",
    ]
    if environ.get("DD_TRACE_ENABLED", "false").strip().lower() in TRUTHY:
        return ["ddtrace-run", *args]
    return args


def main() -> None:
    args = command()
    os.execvp(args[0], args)  # noqa: S606 - fixed argv, no shell


if __name__ == "__main__":
    main()
