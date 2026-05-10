#!/usr/bin/env python3
"""Entrypoint — starts the SSH tunnel + FastAPI proxy."""

import logging
import sys

import uvicorn
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)


class _QuietAccessFilter(logging.Filter):
    """Suppress uvicorn access logs for dashboard polling and health checks."""

    _NOISY = ("/health", "/dashboard/api/")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._NOISY)


logging.getLogger("uvicorn.access").addFilter(_QuietAccessFilter())


def main() -> None:
    print("┌──────────────────────────────────────────────────┐")
    print("│               TunneLLM Proxy                     │")
    print("└──────────────────────────────────────────────────┘")
    print(f"  Proxy:    http://{settings.local_host}:{settings.local_port}")
    print(f"  Model:    {settings.model_name}")
    print(f"  SSH:      {settings.ssh_user}@{settings.ssh_host}:{settings.ssh_port}")
    print(
        f"  Tunnel:   localhost:{settings.tunnel_port} → {settings.remote_host}:{settings.remote_port}"
    )
    print()
    print("  OpenAI-compatible endpoints:")
    print(
        f"    POST http://{settings.local_host}:{settings.local_port}/v1/chat/completions"
    )
    print(f"    POST http://{settings.local_host}:{settings.local_port}/v1/completions")
    print(f"    POST http://{settings.local_host}:{settings.local_port}/v1/embeddings")
    print(f"    GET  http://{settings.local_host}:{settings.local_port}/v1/models")
    print()
    print("  Dashboard:")
    print(f"    http://{settings.local_host}:{settings.local_port}/dashboard")
    print()
    print("  Monitoring:")
    print(f"    GET  http://{settings.local_host}:{settings.local_port}/health")
    print(f"    GET  http://{settings.local_host}:{settings.local_port}/metrics")
    print()
    print(f"  Max concurrent inferences: {settings.max_concurrent_inferences}")
    print(f"  Retry policy: {settings.max_retries}x with exponential backoff")
    print()

    uvicorn.run(
        "server:app",
        host=settings.local_host,
        port=settings.local_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
