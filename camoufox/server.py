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
from urllib.parse import urlparse

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
FETCH_TIMEOUT_MS = int(os.environ.get("CAMOUFOX_TIMEOUT_MS", "20000"))

# Domains to block (trackers/analytics that slow pages down)
BLOCKED_DOMAINS = {
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "hotjar.com",
    "segment.com",
    "newrelic.com",
    "nr-data.net",
}


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
    """Single long-lived Camoufox browser; serialized requests (Firefox limitation)."""

    MAX_REQUESTS = int(os.environ.get("CAMOUFOX_MAX_REQUESTS", "200"))

    def __init__(self) -> None:
        self._cam: AsyncCamoufox | None = None
        self._browser = None
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(1)  # Firefox/Camoufox: one context at a time
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
                os="windows",
                block_webrtc=True,
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

    async def _do_fetch(self, req: FetchRequest) -> FetchResponse:
        """Internal fetch logic — runs inside semaphore + timeout guard."""
        ctx = await self._browser.new_context(
            locale=DEFAULT_LOCALE,
            timezone_id=DEFAULT_TZ,
        )
        try:
            page = await ctx.new_page()

            # Block trackers/heavy resources via route
            async def block_resources(route):
                request = route.request
                resource_type = request.resource_type
                # Block fonts and media always
                if resource_type in ("font", "media"):
                    await route.abort()
                    return
                # Block images by default; allow when screenshot requested
                if resource_type == "image" and not req.screenshot:
                    await route.abort()
                    return
                # Block known tracker domains
                try:
                    host = urlparse(request.url).hostname or ""
                    for domain in BLOCKED_DOMAINS:
                        if host == domain or host.endswith(f".{domain}"):
                            await route.abort()
                            return
                except Exception:
                    pass
                await route.continue_()

            await page.route("**/*", block_resources)

            try:
                resp = await page.goto(
                    req.url, wait_until="domcontentloaded", timeout=FETCH_TIMEOUT_MS
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"navigation failed: {e}")

            status = resp.status if resp else 0

            if req.wait_for:
                try:
                    await page.wait_for_selector(
                        req.wait_for, timeout=min(FETCH_TIMEOUT_MS, 10000)
                    )
                except Exception:
                    pass

            if req.wait_ms:
                await asyncio.sleep(req.wait_ms / 1000)

            title = await page.title()
            html = await page.content()
            try:
                text = await page.evaluate(
                    "() => document.body ? document.body.innerText : ''"
                )
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
            try:
                await asyncio.wait_for(ctx.close(), timeout=5)
            except (asyncio.TimeoutError, Exception) as e:
                log.warning(
                    "context close failed (%s), scheduling browser recycle", e
                )
                self._request_count = self.MAX_REQUESTS

    async def fetch(self, req: FetchRequest) -> FetchResponse:
        """Fetch with serialized access and hard timeout."""
        if self._browser is None:
            await self.start()
        await self._recycle_if_needed()
        self._request_count += 1

        async with self._semaphore:
            # Hard timeout: browser timeout + 5s buffer
            hard_timeout = (FETCH_TIMEOUT_MS / 1000) + 5
            try:
                return await asyncio.wait_for(
                    self._do_fetch(req), timeout=hard_timeout
                )
            except asyncio.TimeoutError:
                log.error("hard timeout reached for %s", req.url)
                # Force recycle — browser is likely stuck
                self._request_count = self.MAX_REQUESTS
                raise HTTPException(
                    status_code=504, detail=f"fetch timeout for {req.url}"
                )


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
