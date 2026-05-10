import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
from config import settings
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from metrics import RequestMetric, metrics
from request_log import request_log
from tunnel import tunnel_manager

logger = logging.getLogger(__name__)

OLLAMA_BASE = f"http://127.0.0.1:{settings.tunnel_port}"
TIMEOUT = httpx.Timeout(
    connect=settings.connect_timeout,
    read=settings.read_timeout,
    write=settings.write_timeout,
    pool=settings.connect_timeout,
)

# ── Runtime config (mutable at runtime via dashboard) ───────

_runtime_config: dict = {
    "model_name": settings.model_name,
    "max_retries": settings.max_retries,
    "retry_base_delay": settings.retry_base_delay,
    "max_concurrent_inferences": settings.max_concurrent_inferences,
    "connect_timeout": settings.connect_timeout,
    "read_timeout": settings.read_timeout,
}

# Semaphore to limit concurrent inference requests
_inference_sem: asyncio.Semaphore | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    global _inference_sem
    _inference_sem = asyncio.Semaphore(_runtime_config["max_concurrent_inferences"])
    tunnel_manager.start()
    yield
    tunnel_manager.stop()


app = FastAPI(title="TunneLLM Proxy", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared HTTP client ──────────────────────────────────────

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=TIMEOUT)
    return _client


# ── Utilities ───────────────────────────────────────────────


def _gen_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _resolve_model(requested: str | None) -> str:
    """Always map to the runtime-configured model name."""
    return _runtime_config["model_name"]


async def _retry_send(
    client: httpx.AsyncClient,
    request: httpx.Request,
    *,
    stream: bool = False,
) -> httpx.Response:
    last_err: Exception | None = None
    max_retries = _runtime_config["max_retries"]
    base_delay = _runtime_config["retry_base_delay"]
    for attempt in range(1, max_retries + 1):
        try:
            return await client.send(request, stream=stream)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_err = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    "Attempt %d/%d failed (%s) — retrying in %.1fs",
                    attempt,
                    max_retries,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
    raise last_err  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════
#  Dashboard — served as single-page HTML
# ═══════════════════════════════════════════════════════════

_DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    if _DASHBOARD_HTML.exists():
        return HTMLResponse(_DASHBOARD_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>dashboard.html not found</h1>", status_code=404)


@app.get("/dashboard/api/requests")
async def dashboard_requests() -> JSONResponse:
    return JSONResponse(request_log.get_all_summaries())


@app.get("/dashboard/api/requests/{entry_id}")
async def dashboard_request_detail(entry_id: str) -> JSONResponse:
    detail = request_log.get_detail(entry_id)
    if detail is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(detail)


@app.get("/dashboard/api/config")
async def dashboard_get_config() -> JSONResponse:
    return JSONResponse(_runtime_config)


@app.post("/dashboard/api/config")
async def dashboard_set_config(request: Request) -> JSONResponse:
    body = await request.json()
    updated = []
    for key in (
        "model_name",
        "max_retries",
        "retry_base_delay",
        "max_concurrent_inferences",
        "connect_timeout",
        "read_timeout",
    ):
        if key in body:
            old = _runtime_config[key]
            _runtime_config[key] = type(old)(body[key])
            if old != _runtime_config[key]:
                updated.append(f"{key}: {old} → {_runtime_config[key]}")
                logger.info(
                    "Config updated: %s: %s → %s", key, old, _runtime_config[key]
                )
    return JSONResponse({"updated": updated, "config": _runtime_config})


@app.get("/dashboard/api/metrics")
async def dashboard_metrics() -> JSONResponse:
    return JSONResponse(metrics.get_summary())


# ═══════════════════════════════════════════════════════════
#  Standard endpoints
# ═══════════════════════════════════════════════════════════


@app.get("/")
async def root() -> Response:
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
        "model": _runtime_config["model_name"],
        "metrics": metrics.get_summary(),
    }


@app.get("/metrics")
async def get_metrics() -> dict:
    return metrics.get_summary()


# ═══════════════════════════════════════════════════════════
#  Transparent proxy — ALL /api/* and /v1/* go to Ollama
# ═══════════════════════════════════════════════════════════


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_ollama_api(request: Request, path: str) -> Response:
    return await _proxy_request(request, f"/api/{path}")


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_openai_api(request: Request, path: str) -> Response:
    return await _proxy_request(request, f"/v1/{path}")


# ── Core proxy logic ────────────────────────────────────────

_OLLAMA_STREAM_ENDPOINTS = {"/api/generate", "/api/chat", "/api/embed"}
_INFERENCE_ENDPOINTS = {
    "/api/generate",
    "/api/chat",
    "/v1/chat/completions",
    "/v1/completions",
}


def _is_streaming(body: bytes, url: str) -> bool:
    if not body:
        return url in _OLLAMA_STREAM_ENDPOINTS
    try:
        data = json.loads(body)
        stream_value = data.get("stream")
        if stream_value is not None:
            return bool(stream_value)
        return url in _OLLAMA_STREAM_ENDPOINTS
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


async def _proxy_request(request: Request, url: str) -> Response:
    client = await get_client()

    headers = dict(request.headers)
    for h in ("host", "transfer-encoding"):
        headers.pop(h, None)

    body = await request.body()

    # Parse request body for logging
    request_data: dict | None = None
    original_model = ""
    if body:
        try:
            request_data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    # Rewrite model name
    if request_data and "model" in request_data:
        original_model = request_data["model"]
        request_data["model"] = _resolve_model(original_model)
        body = json.dumps(request_data).encode()
        headers["content-length"] = str(len(body))
        if original_model != request_data["model"]:
            logger.info(
                "→ %s  model: %s → %s", url, original_model, request_data["model"]
            )
        else:
            logger.info("→ %s  model: %s", url, original_model)
    else:
        logger.info("→ %s", url)

    is_stream = _is_streaming(body, url)
    is_inference = url in _INFERENCE_ENDPOINTS

    # Create log entry
    req_id = _gen_id()
    log_entry = request_log.new_entry(
        entry_id=req_id,
        method=request.method,
        url=url,
        model_original=original_model,
        model_resolved=_runtime_config["model_name"],
        request_body=request_data,
        streaming=is_stream,
    )

    # Track metrics for inference requests
    metric: RequestMetric | None = None
    if is_inference:
        metric = metrics.new_request(req_id, _runtime_config["model_name"], url)

    # Acquire semaphore for inference requests
    if is_inference and _inference_sem is not None:
        await _inference_sem.acquire()

    try:
        if is_stream:
            req = client.build_request(
                method=request.method, url=url, headers=headers, content=body
            )
            try:
                upstream = await _retry_send(client, req, stream=True)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                _fail_entry(log_entry, metric, str(exc), 502)
                logger.error("Cannot reach Ollama via tunnel at %s", OLLAMA_BASE)
                return Response(
                    content=b'{"error":"Cannot reach Ollama server. Check tunnel."}',
                    status_code=502,
                    media_type="application/json",
                )

            log_entry.response_status = upstream.status_code

            async def stream_body() -> AsyncIterator[bytes]:
                first_chunk = True
                try:
                    async for chunk in upstream.aiter_bytes():
                        if metric and first_chunk:
                            metric.first_token_time = time.time()
                            log_entry.first_token_time = time.time()
                            first_chunk = False

                        # Store chunk text for dashboard
                        try:
                            log_entry.response_chunks.append(
                                chunk.decode("utf-8", errors="replace")
                            )
                        except Exception:
                            pass

                        if metric:
                            _try_extract_metrics(chunk, metric)

                        yield chunk
                except Exception as exc:
                    _fail_entry(log_entry, metric, str(exc))
                    raise
                finally:
                    await upstream.aclose()
                    if metric and metric.status == "in_progress":
                        metric.end_time = time.time()
                        metric.status = "completed"
                    log_entry.end_time = time.time()
                    if log_entry.status == "in_progress":
                        log_entry.status = "completed"
                    if is_inference and _inference_sem is not None:
                        _inference_sem.release()

            return StreamingResponse(
                stream_body(),
                status_code=upstream.status_code,
                headers=dict(upstream.headers),
                media_type=upstream.headers.get("content-type"),
            )
        else:
            try:
                resp = await client.request(
                    method=request.method, url=url, headers=headers, content=body
                )
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                _fail_entry(log_entry, metric, str(exc), 502)
                logger.error("Cannot reach Ollama via tunnel at %s", OLLAMA_BASE)
                return Response(
                    content=b'{"error":"Cannot reach Ollama server. Check tunnel."}',
                    status_code=502,
                    media_type="application/json",
                )
            except httpx.ReadTimeout:
                _fail_entry(log_entry, metric, "read_timeout", 504)
                return Response(
                    content=b'{"error":"Ollama read timeout (model may be loading)."}',
                    status_code=504,
                    media_type="application/json",
                )

            log_entry.response_status = resp.status_code
            log_entry.end_time = time.time()
            log_entry.status = "completed"

            # Store response body
            try:
                log_entry.response_body = resp.json()
            except Exception:
                log_entry.response_body = resp.text[:5000] if resp.text else None

            if metric:
                metric.end_time = time.time()
                metric.status = "completed"
                try:
                    result = resp.json()
                    metric.prompt_tokens = result.get("prompt_eval_count", 0)
                    metric.completion_tokens = result.get("eval_count", 0)
                    usage = result.get("usage", {})
                    if usage:
                        metric.prompt_tokens = usage.get(
                            "prompt_tokens", metric.prompt_tokens
                        )
                        metric.completion_tokens = usage.get(
                            "completion_tokens", metric.completion_tokens
                        )
                except Exception:
                    pass

            _log_response_status(url, log_entry)

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=dict(resp.headers),
                media_type=resp.headers.get("content-type"),
            )
    finally:
        if is_inference and not is_stream and _inference_sem is not None:
            _inference_sem.release()


# ── Logging helpers ──────────────────────────────────────────


def _fail_entry(log_entry, metric, error: str, status: int = 0) -> None:
    log_entry.status = "failed"
    log_entry.end_time = time.time()
    log_entry.error = error
    if status:
        log_entry.response_status = status
    if metric:
        metric.status = "failed"
        metric.end_time = time.time()
        metric.error = error


def _log_response_status(url: str, log_entry) -> None:
    """Log only status and latency — details are in the dashboard."""
    status = log_entry.response_status
    latency = log_entry.latency_ms
    if status >= 400:
        logger.warning(
            "  ← %s  %s  %sms  error=%s", url, status, latency, log_entry.error or ""
        )
    else:
        logger.info("  ← %s  %s  %sms", url, status, latency)


def _try_extract_metrics(chunk: bytes, metric: RequestMetric) -> None:
    try:
        for line in chunk.split(b"\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith(b"data: "):
                line = line[6:]
            if line == b"[DONE]":
                continue
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if data.get("done"):
                metric.prompt_tokens = data.get(
                    "prompt_eval_count", metric.prompt_tokens
                )
                metric.completion_tokens = data.get(
                    "eval_count", metric.completion_tokens
                )
                metric.end_time = time.time()
                metric.status = "completed"
            usage = data.get("usage")
            if usage:
                metric.prompt_tokens = usage.get("prompt_tokens", metric.prompt_tokens)
                metric.completion_tokens = usage.get(
                    "completion_tokens", metric.completion_tokens
                )
                metric.end_time = time.time()
                metric.status = "completed"
    except Exception:
        pass
