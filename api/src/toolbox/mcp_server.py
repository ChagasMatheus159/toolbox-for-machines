"""MCP server — exposes all 6 Toolbox tools via Streamable HTTP.

Thin wrapper over services.py. Converts ToolboxError → ToolError for MCP protocol.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import TransportSecuritySettings
from mcp.server.fastmcp.exceptions import ToolError

from toolbox.services import (
    ToolboxError,
    search as search_service,
    fetch as fetch_service,
    describe as describe_service,
    transcribe as transcribe_service,
    summarize as summarize_service,
    extract as extract_service,
)

mcp = FastMCP(
    "toolbox",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _convert_error(e: ToolboxError) -> ToolError:
    return ToolError(e.detail)


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
    try:
        return await search_service(query=query, limit=limit, categories=categories)
    except ToolboxError as e:
        raise _convert_error(e)


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
    try:
        return await fetch_service(url=url, format=format, screenshot=screenshot, wait_for=wait_for, wait_ms=wait_ms)
    except ToolboxError as e:
        raise _convert_error(e)


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
    try:
        return await describe_service(
            image_url=image_url, image_b64=image_b64, page_url=page_url,
            prompt=prompt, wait_for=wait_for, wait_ms=wait_ms,
        )
    except ToolboxError as e:
        raise _convert_error(e)


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
    try:
        return await transcribe_service(audio_url=audio_url, audio_b64=audio_b64, mime_type=mime_type, language=language)
    except ToolboxError as e:
        raise _convert_error(e)


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
    try:
        return await summarize_service(text=text, max_tokens=max_tokens, style=style)
    except ToolboxError as e:
        raise _convert_error(e)


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
    try:
        return await extract_service(text=text, schema=schema)
    except ToolboxError as e:
        raise _convert_error(e)
