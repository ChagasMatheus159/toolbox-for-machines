"""POST /v1/fetch — Stealth web fetch via Camoufox + content extraction."""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.config import settings

log = logging.getLogger("toolbox.fetch")
router = APIRouter()


class FetchRequest(BaseModel):
    url: str
    format: str = Field(default="markdown", pattern="^(markdown|text)$")
    screenshot: bool = False
    wait_for: Optional[str] = None
    wait_ms: int = Field(default=0, ge=0, le=20000)


class FetchResponse(BaseModel):
    url: str
    final_url: str
    title: str
    content: str
    format: str
    word_count: int
    screenshot_b64: Optional[str] = None


def extract_content(html: str, output_format: str) -> str:
    """Extract main content from HTML using trafilatura (fallback for Crawl4AI)."""
    try:
        import trafilatura

        result = trafilatura.extract(
            html,
            include_links=True,
            include_formatting=(output_format == "markdown"),
            output_format="txt" if output_format == "text" else "markdown",
        )
        return result or ""
    except Exception as e:
        log.warning("trafilatura extraction failed: %s", e)
        return ""


@router.post("/fetch", response_model=FetchResponse)
async def fetch(req: FetchRequest, request: Request):
    """Fetch a URL via stealth browser, return clean extracted content."""
    # Check cache (skip if screenshot requested)
    if not req.screenshot:
        cache_key = cache.make_key("fetch", {"url": req.url, "format": req.format})
        cached = cache.get(cache_key)
        if cached:
            return cached

    # Call Camoufox
    http = request.app.state.http
    payload = {
        "url": req.url,
        "screenshot": req.screenshot,
        "wait_for": req.wait_for,
        "wait_ms": req.wait_ms,
    }

    try:
        r = await http.post(
            f"{settings.camoufox_url}/fetch",
            json=payload,
            timeout=settings.fetch_timeout_seconds,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Camoufox fetch failed for %s: %s — trying lightweight fallback", req.url, e)
        # Fallback: simple HTTP GET without JS rendering
        try:
            fallback_r = await http.get(
                req.url,
                timeout=15,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            fallback_r.raise_for_status()
            html = fallback_r.text
            import re
            title_search = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_search.group(1).strip() if title_search else ""
            final_url = str(fallback_r.url)
            content = extract_content(html, req.format)
            if content and len(content) > 50:
                log.info("Lightweight fallback succeeded for %s (%d words)", req.url, len(content.split()))
                word_count = len(content.split())
                response = FetchResponse(
                    url=req.url,
                    final_url=final_url,
                    title=title,
                    content=content,
                    format=req.format,
                    word_count=word_count,
                )
                if not req.screenshot:
                    cache.set(cache_key, response.model_dump(), ttl_seconds=1800)
                return response
        except Exception as fallback_err:
            log.debug("Lightweight fallback also failed for %s: %s", req.url, fallback_err)

        # Both methods failed
        return FetchResponse(
            url=req.url,
            final_url=req.url,
            title="",
            content=f"Error fetching URL: {e}",
            format=req.format,
            word_count=0,
        )

    # Extract content from HTML
    html = data.get("html", "")
    title = data.get("title", "")
    final_url = data.get("final_url", req.url)
    screenshot_b64 = data.get("screenshot_b64")

    # Try Crawl4AI first, fall back to trafilatura
    content = ""
    try:
        from crawl4ai import extract_content as crawl4ai_extract

        content = crawl4ai_extract(html, output_format=req.format)
    except (ImportError, Exception) as e:
        log.debug("Crawl4AI not available or failed, using trafilatura: %s", e)
        content = extract_content(html, req.format)

    # If extraction failed, use the plain text from Camoufox
    if not content:
        content = data.get("text", "")

    word_count = len(content.split())

    response = FetchResponse(
        url=req.url,
        final_url=final_url,
        title=title,
        content=content,
        format=req.format,
        word_count=word_count,
        screenshot_b64=screenshot_b64 if req.screenshot else None,
    )

    # Cache for 30 minutes (skip if screenshot)
    if not req.screenshot:
        cache.set(cache_key, response.model_dump(), ttl_seconds=1800)

    return response
