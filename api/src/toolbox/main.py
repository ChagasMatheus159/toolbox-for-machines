"""FastAPI application — main entry point for the Toolbox service."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from toolbox.config import settings
from toolbox.http_client import get_http_client, close_http_client
from toolbox.mcp_server import mcp as mcp_server


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared HTTP client and MCP session manager lifecycle."""
    app.state.http = get_http_client()
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        await close_http_client()


app = FastAPI(
    title="Toolbox",
    description="Self-contained tool service for AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health check ──────────────────────────────────────────────────────────────


@app.get("/healthz")
async def healthz():
    """Liveness check for the API itself."""
    http = app.state.http

    async def check_searxng():
        try:
            r = await http.get(f"{settings.searxng_url}/", timeout=3)
            return "healthy" if r.status_code == 200 else "unhealthy"
        except Exception:
            return "unreachable"

    async def check_camoufox():
        try:
            r = await http.get(f"{settings.camoufox_url}/healthz", timeout=5)
            return "healthy" if r.status_code == 200 else "unhealthy"
        except Exception:
            return "unreachable"

    async def check_whisper():
        try:
            r = await http.get(f"{settings.whisper_url}/health", timeout=3)
            return "healthy" if r.status_code == 200 else "unhealthy"
        except Exception:
            return "unreachable"

    async def check_llm():
        try:
            headers = {}
            if settings.llm_api_key:
                headers["Authorization"] = f"Bearer {settings.llm_api_key}"
            r = await http.get(f"{settings.llm_url}/models", headers=headers, timeout=5)
            return "healthy" if r.status_code == 200 else "unhealthy"
        except Exception:
            return "unreachable"

    results = await asyncio.gather(
        check_searxng(), check_camoufox(), check_whisper(), check_llm()
    )
    backends = dict(zip(["searxng", "camoufox", "whisper", "llm"], results))
    status = "ok" if all(v == "healthy" for v in backends.values()) else "degraded"
    return {"status": status, "backends": backends}


# ── Mount tool routers ────────────────────────────────────────────────────────

from toolbox.tools.search import router as search_router  # noqa: E402
from toolbox.tools.fetch import router as fetch_router  # noqa: E402
from toolbox.tools.describe import router as describe_router  # noqa: E402
from toolbox.tools.transcribe import router as transcribe_router  # noqa: E402
from toolbox.tools.summarize import router as summarize_router  # noqa: E402
from toolbox.tools.extract import router as extract_router  # noqa: E402
from toolbox.skills import router as skills_router  # noqa: E402

app.include_router(search_router, prefix="/v1")
app.include_router(fetch_router, prefix="/v1")
app.include_router(describe_router, prefix="/v1")
app.include_router(transcribe_router, prefix="/v1")
app.include_router(summarize_router, prefix="/v1")
app.include_router(extract_router, prefix="/v1")
app.include_router(skills_router, prefix="/v1")


# ── MCP server (Streamable HTTP at /mcp/) ────────────────────────────────────

app.mount("/mcp", mcp_server.streamable_http_app())
