"""MCP server — exposes all 6 Toolbox tools via Streamable HTTP."""

import base64
import hashlib
import json
import logging
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from mcp.server.fastmcp.exceptions import ToolError

from toolbox.cache import cache
from toolbox.config import settings
from toolbox.http_client import get_http_client
from toolbox.llm import chat
from toolbox.prompts import DESCRIBE, SUMMARIZE, EXTRACT
from toolbox.validation import validate_url_raw, URLValidationError

log = logging.getLogger("toolbox.mcp")


async def _validate_url(url: str) -> None:
    """Validate URL, converting URLValidationError to ToolError."""
    try:
        await validate_url_raw(url)
    except URLValidationError as e:
        raise ToolError(e.detail)


mcp = FastMCP(
    "toolbox",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

SLOW_CATEGORIES = {"it", "science"}
SLOW_TIMEOUT = 20
DEFAULT_TIMEOUT = 10


@mcp.tool()
async def search(
    query: str,
    limit: int = 10,
    categories: str = "general",
) -> dict[str, Any]:
    """Search the web. Returns results with title, URL, and snippet.

    Use when you need to find information, URLs, or recent content about a topic.
    Do NOT use when you already have the URL (use fetch instead).

    Args:
        query: Search query
        limit: Max results to return (1-50, default 10)
        categories: Search category — general, news, images, science, or it
    """
    if not query.strip():
        raise ToolError("query cannot be empty")
    if categories not in ("general", "news", "images", "science", "it"):
        raise ToolError("categories must be one of: general, news, images, science, it")
    limit = max(1, min(50, limit))

    cache_key = cache.make_key("search", {"query": query, "limit": limit, "categories": categories})
    cached = cache.get(cache_key)
    if cached:
        return cached

    http = get_http_client()
    params = {"q": query, "format": "json", "categories": categories}
    timeout = SLOW_TIMEOUT if categories in SLOW_CATEGORIES else DEFAULT_TIMEOUT

    try:
        r = await http.get(f"{settings.searxng_url}/search", params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        if categories in SLOW_CATEGORIES:
            params["categories"] = "general"
            try:
                r = await http.get(f"{settings.searxng_url}/search", params=params, timeout=DEFAULT_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            except Exception:
                return {"results": [], "query": query, "count": 0}
        else:
            return {"results": [], "query": query, "count": 0}

    raw_results = data.get("results", [])[:limit]
    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
            "engine": item.get("engine", "unknown"),
        }
        for item in raw_results
    ]

    response = {"results": results, "query": query, "count": len(results)}
    if results:
        cache.set(cache_key, response, ttl_seconds=300)
    return response


def _extract_content(html: str, output_format: str) -> str:
    """Extract main content from HTML using trafilatura."""
    try:
        import trafilatura

        result = trafilatura.extract(
            html,
            include_links=True,
            include_formatting=(output_format == "markdown"),
            output_format="txt" if output_format == "text" else "markdown",
        )
        return result or ""
    except Exception:
        return ""


@mcp.tool()
async def fetch(
    url: str,
    format: str = "markdown",
    screenshot: bool = False,
    wait_for: str | None = None,
    wait_ms: int = 0,
) -> dict[str, Any]:
    """Fetch a URL using a stealth browser. Returns clean extracted content.

    Handles JavaScript-rendered pages and bot-protected sites.
    Use when you need the content of a specific URL.
    Do NOT use when you need to find URLs first (use search).

    Args:
        url: URL to fetch
        format: Output format — markdown or text (default markdown)
        screenshot: Include base64 screenshot of the page (default false)
        wait_for: CSS selector to wait for before extracting content
        wait_ms: Milliseconds to wait after page load (0-20000)
    """
    if format not in ("markdown", "text"):
        raise ToolError("format must be 'markdown' or 'text'")
    wait_ms = max(0, min(20000, wait_ms))

    await _validate_url(url)

    if not screenshot:
        cache_key = cache.make_key("fetch", {"url": url, "format": format, "wait_for": wait_for, "wait_ms": wait_ms})
        cached = cache.get(cache_key)
        if cached:
            return cached

    http = get_http_client()
    payload = {"url": url, "screenshot": screenshot, "wait_for": wait_for, "wait_ms": wait_ms}

    try:
        r = await http.post(f"{settings.camoufox_url}/fetch", json=payload, timeout=settings.fetch_timeout_seconds)
        r.raise_for_status()
        data = r.json()
    except Exception:
        # Lightweight fallback without JS rendering
        try:
            fallback_r = await http.get(
                url, timeout=15, follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            fallback_r.raise_for_status()
            html = fallback_r.text
            title_search = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            title = title_search.group(1).strip() if title_search else ""
            content = _extract_content(html, format)
            if content and len(content) > 50:
                response = {
                    "url": url, "final_url": str(fallback_r.url), "title": title,
                    "content": content, "format": format, "word_count": len(content.split()),
                }
                if not screenshot:
                    cache.set(cache_key, response, ttl_seconds=1800)
                return response
        except Exception:
            pass
        return {"url": url, "final_url": url, "title": "", "content": "Error: unable to fetch this URL.", "format": format, "word_count": 0}

    html = data.get("html", "")
    title = data.get("title", "")
    final_url = data.get("final_url", url)
    screenshot_b64 = data.get("screenshot_b64")
    content = _extract_content(html, format)
    if not content:
        content = data.get("text", "")

    word_count = len(content.split())
    response = {
        "url": url, "final_url": final_url, "title": title,
        "content": content, "format": format, "word_count": word_count,
    }
    if screenshot and screenshot_b64:
        response["screenshot_b64"] = screenshot_b64
    if not screenshot:
        cache.set(cache_key, response, ttl_seconds=1800)
    return response


@mcp.tool()
async def describe(
    image_url: str | None = None,
    image_b64: str | None = None,
    page_url: str | None = None,
    prompt: str = "Describe this image concisely.",
    wait_for: str | None = None,
    wait_ms: int = 0,
) -> dict[str, str]:
    """Describe an image or webpage screenshot using a vision model.

    Three input modes (provide exactly one):
    - page_url: Screenshots a live webpage, then describes it. Best for visual verification.
    - image_url: Downloads and describes a public image.
    - image_b64: Describes a base64-encoded image.

    Shares LLM concurrency slot with summarize/extract — requests may queue.

    Args:
        image_url: URL of a public image to describe
        image_b64: Base64-encoded image data (with or without data: prefix)
        page_url: URL of a webpage to screenshot and describe
        prompt: Custom prompt for the vision model
        wait_for: CSS selector to wait for before screenshotting (page_url only)
        wait_ms: Milliseconds to wait after page load (page_url only, 0-20000)
    """
    if not image_url and not image_b64 and not page_url:
        raise ToolError("One of image_url, image_b64, or page_url is required.")

    wait_ms = max(0, min(20000, wait_ms))
    http = get_http_client()
    image_data_url: str

    if page_url:
        await _validate_url(page_url)
        use_cache = not wait_for and wait_ms == 0
        cache_key = cache.make_key("describe", {"page_url": page_url, "prompt": prompt})
        if use_cache:
            cached = cache.get(cache_key)
            if cached:
                return cached

        try:
            payload = {"url": page_url, "screenshot": True, "wait_for": wait_for, "wait_ms": wait_ms}
            r = await http.post(f"{settings.camoufox_url}/fetch", json=payload, timeout=settings.fetch_timeout_seconds)
            r.raise_for_status()
            data = r.json()
            screenshot_b64 = data.get("screenshot_b64")
            if not screenshot_b64:
                raise ToolError("Screenshot service returned no image.")
            image_data_url = f"data:image/png;base64,{screenshot_b64}"
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to screenshot page: {e}")

    elif image_url:
        await _validate_url(image_url)
        cache_key = cache.make_key("describe", {"url": image_url, "prompt": prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            r = await http.get(image_url, timeout=15)
            r.raise_for_status()
            raw = r.content
            if len(raw) > 10 * 1024 * 1024:
                raise ToolError("Image too large (max 10MB).")
            content_type = r.headers.get("content-type", "image/png").split(";")[0]
            b64 = base64.b64encode(raw).decode("ascii")
            image_data_url = f"data:{content_type};base64,{b64}"
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to download image: {e}")
    else:
        b64_hash = hashlib.sha256(image_b64.encode()).hexdigest()
        cache_key = cache.make_key("describe", {"b64_hash": b64_hash, "prompt": prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached
        if image_b64.startswith("data:"):
            image_data_url = image_b64
        else:
            image_data_url = f"data:image/png;base64,{image_b64}"

    messages = [
        {"role": "system", "content": DESCRIBE},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]

    try:
        description = await chat(messages, max_tokens=300)
    except Exception as e:
        raise ToolError(f"Vision model error: {e}")

    response = {"description": description}
    if not page_url or (not wait_for and wait_ms == 0):
        cache.set(cache_key, response, ttl_seconds=3600)
    return response


@mcp.tool()
async def transcribe(
    audio_url: str | None = None,
    audio_b64: str | None = None,
    mime_type: str = "audio/wav",
    language: str = "en",
) -> dict[str, str]:
    """Transcribe audio to text using whisper.cpp.

    Processing time is approximately 1x realtime.

    Args:
        audio_url: URL of the audio file to transcribe
        audio_b64: Base64-encoded audio data
        mime_type: MIME type of the audio (default audio/wav)
        language: Language hint as ISO 639-1 code (default en)
    """
    if not audio_url and not audio_b64:
        raise ToolError("Either audio_url or audio_b64 is required.")

    http = get_http_client()
    MAX_AUDIO_BYTES = 100 * 1024 * 1024

    if audio_url:
        await _validate_url(audio_url)
        try:
            r = await http.get(audio_url, timeout=30)
            r.raise_for_status()
            audio_bytes = r.content
            if len(audio_bytes) > MAX_AUDIO_BYTES:
                raise ToolError("Audio too large (max 100MB).")
        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Failed to download audio: {e}")
    else:
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            raise ToolError("Invalid base64 audio data.")

    try:
        files = {"file": ("audio.wav", audio_bytes, mime_type)}
        data = {"language": language, "response_format": "json"}
        r = await http.post(f"{settings.whisper_url}/inference", files=files, data=data, timeout=120)
        r.raise_for_status()
        result = r.json()
    except Exception as e:
        raise ToolError(f"Whisper transcription error: {e}")

    return {"transcript": result.get("text", "").strip(), "language": language}


@mcp.tool()
async def summarize(
    text: str,
    max_tokens: int = 200,
    style: str = "brief",
) -> dict[str, str]:
    """Summarize long text into a concise version.

    Input is truncated to ~6800 characters. For longer content, chunk before calling.
    Shares LLM concurrency slot with describe/extract — requests may queue.

    Args:
        text: Text to summarize
        max_tokens: Maximum tokens in the summary (20-500, default 200)
        style: Summary style — brief, detailed, or bullets
    """
    if not text.strip():
        raise ToolError("Text cannot be empty.")
    if style not in ("brief", "detailed", "bullets"):
        raise ToolError("style must be one of: brief, detailed, bullets")
    max_tokens = max(20, min(500, max_tokens))

    text_hash = hashlib.sha256(text.encode()).hexdigest()
    cache_key = cache.make_key("summarize", {"text_hash": text_hash, "max_tokens": max_tokens, "style": style})
    cached = cache.get(cache_key)
    if cached:
        return cached

    max_input_chars = 6800
    input_text = text[:max_input_chars]
    if len(text) > max_input_chars:
        input_text += "\n\n[... text truncated ...]"

    style_hint = ""
    if style == "bullets":
        style_hint = " Use bullet points."
    elif style == "detailed":
        style_hint = " Include supporting details."

    system_prompt = SUMMARIZE.format(words=max_tokens * 3 // 4) + style_hint
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    try:
        summary = await chat(messages, max_tokens=max_tokens)
    except Exception as e:
        raise ToolError(f"Summarization error: {e}")

    response = {"summary": summary}
    cache.set(cache_key, response, ttl_seconds=3600)
    return response


@mcp.tool()
async def extract(
    text: str,
    schema: dict,
) -> dict[str, Any]:
    """Extract structured JSON data from text using a provided schema.

    Output is guaranteed to match the schema. Input is truncated to ~4800 characters.
    Supports both object and array root schemas.
    Shares LLM concurrency slot with describe/summarize — requests may queue.

    Args:
        text: Text to extract data from
        schema: JSON Schema that the output must conform to
    """
    if not text.strip():
        raise ToolError("Text cannot be empty.")
    if not schema:
        raise ToolError("Schema cannot be empty.")

    text_hash = hashlib.sha256(text.encode()).hexdigest()
    cache_key = cache.make_key("extract", {"text_hash": text_hash, "schema": schema})
    cached = cache.get(cache_key)
    if cached:
        return cached

    max_input_chars = 4800
    input_text = text[:max_input_chars]

    is_array_schema = schema.get("type") == "array"
    if is_array_schema:
        effective_schema = {"type": "object", "properties": {"items": schema}, "required": ["items"]}
    else:
        effective_schema = schema

    schema_str = json.dumps(effective_schema, indent=2)
    system_prompt = EXTRACT.format(schema=schema_str)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    try:
        result = await chat(messages, max_tokens=400, response_format={"type": "json_object"})
    except Exception as e:
        raise ToolError(f"Extraction error: {e}")

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            start = result.index("{")
            end = result.rindex("}") + 1
            data = json.loads(result[start:end])
        except (ValueError, json.JSONDecodeError):
            raise ToolError(f"LLM returned invalid JSON. Raw: {result[:300]}")

    if is_array_schema and isinstance(data, dict) and "items" in data:
        data = data["items"]

    response = {"data": data}
    cache.set(cache_key, response, ttl_seconds=3600)
    return response
