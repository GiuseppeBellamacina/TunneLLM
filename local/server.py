import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from config import settings
from tunnel import tunnel_manager

logger = logging.getLogger(__name__)

OLLAMA_BASE = f"http://127.0.0.1:{settings.tunnel_port}"
TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    tunnel_manager.start()
    yield
    tunnel_manager.stop()


app = FastAPI(title="TunneLLM Proxy", lifespan=lifespan)

# Shared async HTTP client — reuses connections
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=OLLAMA_BASE,
            timeout=TIMEOUT,
        )
    return _client


# ── Ollama root endpoint ───────────────────────────────────


@app.get("/")
async def root() -> Response:
    """Ollama returns 'Ollama is running' on GET /."""
    try:
        client = await get_client()
        resp = await client.get("/")
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type"),
        )
    except Exception:
        return Response(content=b"Ollama is running", status_code=200)


# ── Health ──────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    tunnel_ok = tunnel_manager.is_active
    ollama_ok = False
    if tunnel_ok:
        try:
            client = await get_client()
            resp = await client.get("/api/tags")
            ollama_ok = resp.status_code == 200
        except Exception:
            pass
    return {
        "tunnel": "up" if tunnel_ok else "down",
        "ollama": "up" if ollama_ok else "down",
        "model": settings.model_name,
    }


# ── Proxy all Ollama API requests (/api/*) ──────────────────


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_ollama_api(request: Request, path: str) -> Response:
    return await _proxy_request(request, f"/api/{path}")


# ── Proxy OpenAI-compatible requests (/v1/*) ────────────────


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_openai_api(request: Request, path: str) -> Response:
    return await _proxy_request(request, f"/v1/{path}")


# ── Core proxy logic ────────────────────────────────────────

# Ollama API endpoints that stream by default (when "stream" is not explicitly set)
_OLLAMA_STREAM_ENDPOINTS = {"/api/generate", "/api/chat", "/api/embed"}


def _is_streaming(body: bytes, url: str) -> bool:
    """Detect if the request will produce a streaming response.

    Ollama behavior:
    - /api/generate, /api/chat: stream=true by DEFAULT (must send stream:false to disable)
    - /v1/chat/completions: stream=false by default (OpenAI convention)
    - Other endpoints: no streaming
    """
    if not body:
        return url in _OLLAMA_STREAM_ENDPOINTS

    try:
        data = json.loads(body)
        stream_value = data.get("stream")
        if stream_value is not None:
            return bool(stream_value)
        # No explicit "stream" field → use endpoint default
        return url in _OLLAMA_STREAM_ENDPOINTS
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


async def _proxy_request(request: Request, url: str) -> Response:
    client = await get_client()

    headers = dict(request.headers)
    for h in ("host", "transfer-encoding"):
        headers.pop(h, None)

    body = await request.body()

    # Rewrite model name to the configured one
    if body:
        try:
            data = json.loads(body)
            if "model" in data:
                original = data["model"]
                data["model"] = settings.model_name
                body = json.dumps(data).encode()
                headers["content-length"] = str(len(body))
                if original != settings.model_name:
                    logger.info("Request to %s — model: %s → %s", url, original, settings.model_name)
                else:
                    logger.info("Request to %s — model: %s", url, original)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    is_stream = _is_streaming(body, url)

    try:
        if is_stream:
            req = client.build_request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            upstream = await client.send(req, stream=True)

            async def stream_body() -> AsyncIterator[bytes]:
                try:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk
                finally:
                    await upstream.aclose()

            return StreamingResponse(
                stream_body(),
                status_code=upstream.status_code,
                headers=dict(upstream.headers),
                media_type=upstream.headers.get("content-type"),
            )
        else:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type"),
            )
    except httpx.ConnectError:
        logger.error("Cannot reach Ollama via tunnel at %s", OLLAMA_BASE)
        return Response(
            content=b'{"error":"Cannot reach Ollama server. Check tunnel."}',
            status_code=502,
            media_type="application/json",
        )
    except httpx.ReadTimeout:
        return Response(
            content=b'{"error":"Ollama read timeout (model may be loading)."}',
            status_code=504,
            media_type="application/json",
        )
