import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

from config import settings
from tunnel import tunnel_manager

logger = logging.getLogger(__name__)

VLLM_BASE = f"http://127.0.0.1:{settings.tunnel_port}"
TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    tunnel_manager.start()
    yield
    tunnel_manager.stop()


app = FastAPI(title="Abusive-LLM Proxy", lifespan=lifespan)

# Shared async HTTP client — reuses connections
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        headers = {}
        if settings.vllm_api_key:
            headers["Authorization"] = f"Bearer {settings.vllm_api_key}"
        _client = httpx.AsyncClient(
            base_url=VLLM_BASE,
            timeout=TIMEOUT,
            headers=headers,
        )
    return _client


# ── Health ──────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict:
    tunnel_ok = tunnel_manager.is_active
    vllm_ok = False
    if tunnel_ok:
        try:
            client = await get_client()
            resp = await client.get("/v1/models")
            vllm_ok = resp.status_code == 200
        except Exception:
            pass
    return {
        "tunnel": "up" if tunnel_ok else "down",
        "vllm": "up" if vllm_ok else "down",
        "model": settings.model_name,
    }


# ── Proxy all /v1/* requests ────────────────────────────────


@app.api_route(
    "/v1/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_vllm(request: Request, path: str) -> Response:
    client = await get_client()
    url = f"/v1/{path}"

    headers = dict(request.headers)
    # Remove hop-by-hop headers
    for h in ("host", "transfer-encoding"):
        headers.pop(h, None)

    body = await request.body()

    # Detect if the caller wants streaming
    is_stream = b'"stream":true' in body or b'"stream": true' in body

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
        logger.error("Cannot reach vLLM via tunnel at %s", VLLM_BASE)
        return Response(
            content=b'{"error":"Cannot reach vLLM server. Check tunnel."}',
            status_code=502,
            media_type="application/json",
        )
    except httpx.ReadTimeout:
        return Response(
            content=b'{"error":"vLLM read timeout (model may be loading)."}',
            status_code=504,
            media_type="application/json",
        )
