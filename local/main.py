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


def main() -> None:
    print(f"Starting Abusive-LLM proxy on {settings.local_host}:{settings.local_port}")
    print(f"  SSH tunnel port: {settings.tunnel_port} → {settings.remote_host}:{settings.remote_port}")
    print(f"  SSH target: {settings.ssh_user}@{settings.ssh_host}:{settings.ssh_port}")
    print(f"  Model: {settings.model_name}")
    print()

    uvicorn.run(
        "server:app",
        host=settings.local_host,
        port=settings.local_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
