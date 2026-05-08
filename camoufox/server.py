"""Camoufox stealth browser server for the Toolbox stack.

Endpoints:
  GET  /healthz  → liveness
  POST /fetch    → { html, text, title, status, screenshot_b64?, final_url }
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from camoufox.async_api import AsyncCamoufox

log = logging.getLogger("camoufox-server")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)

DEFAULT_LOCALE = os.environ.get("CAMOUFOX_LOCALE", "en-US")
DEFAULT_TZ = os.environ.get("CAMOUFOX_TZ", "America/Sao_Paulo")
FETCH_TIMEOUT_MS = int(os.environ.get("CAMOUFOX_TIMEOUT_MS", "30000"))


class FetchRequest(BaseModel):
    url: str
    wait_for: Optional[str] = Field(default=None, description="CSS selector to await")
    wait_ms: int = Field(default=0, ge=0, le=20000)
    screenshot: bool = False


class FetchResponse(BaseModel):
    url: str
    status: int
    title: str
    html: str
    text: str
    screenshot_b64: Optional[str] = None
    final_url: str


class BrowserPool:
    """Single long-lived Camoufox browser; per-request new context."""

    MAX_REQUESTS = int(os.environ.get("CAMOUFOX_MAX_REQUESTS", "500"))

    def __init__(self) -> None:
        self._cam: AsyncCamoufox | None = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._request_count = 0

    async def start(self) -> None:
        async with self._lock:
            if self._browser is not None:
                return
            log.info("launching camoufox browser")
            self._cam = AsyncCamoufox(
                headless=True,
                humanize=True,
                locale=DEFAULT_LOCALE,
            )
            self._browser = await self._cam.__aenter__()
            self._request_count = 0
            log.info("camoufox browser ready")

    async def stop(self) -> None:
        async with self._lock:
            if self._browser is None:
                return
            try:
                await self._cam.__aexit__(None, None, None)
            except Exception as e:
                log.warning("shutdown error: %s", e)
            self._browser = None
            self._cam = None

    async def _recycle_if_needed(self) -> None:
        if self._request_count >= self.MAX_REQUESTS:
            log.info("recycling browser after %d requests", self._request_count)
            await self.stop()
            await self.start()

    async def fetch(self, req: FetchRequest) -> FetchResponse:
        if self._browser is None:
            await self.start()
        await self._recycle_if_needed()
        self._request_count += 1

        ctx = await self._browser.new_context(
            locale=DEFAULT_LOCALE,
            timezone_id=DEFAULT_TZ,
        )
        try:
            page = await ctx.new_page()
            try:
                resp = await page.goto(
                    req.url, wait_until="domcontentloaded", timeout=FETCH_TIMEOUT_MS
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"navigation failed: {e}")

            status = resp.status if resp else 0

            if req.wait_for:
                try:
                    await page.wait_for_selector(req.wait_for, timeout=FETCH_TIMEOUT_MS)
                except Exception:
                    pass

            if req.wait_ms:
                await asyncio.sleep(req.wait_ms / 1000)

            title = await page.title()
            html = await page.content()
            try:
                text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            except Exception:
                text = ""

            shot = None
            if req.screenshot:
                data = await page.screenshot(type="png", full_page=False)
                shot = base64.b64encode(data).decode("ascii")

            return FetchResponse(
                url=req.url,
                status=status,
                title=title,
                html=html,
                text=text,
                screenshot_b64=shot,
                final_url=page.url,
            )
        finally:
            await ctx.close()


pool = BrowserPool()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pool.start()
    try:
        yield
    finally:
        await pool.stop()


app = FastAPI(title="Toolbox Camoufox Server", lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "browser": pool._browser is not None}


@app.post("/fetch", response_model=FetchResponse)
async def fetch_endpoint(req: FetchRequest):
    log.info("fetch %s", req.url)
    return await pool.fetch(req)
