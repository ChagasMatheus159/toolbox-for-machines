"""Skill cards — machine-readable tool definitions for agent discovery."""

from fastapi import APIRouter

router = APIRouter()

SKILLS = {
    "version": "1.0.0",
    "skills": [
        {
            "id": "search",
            "endpoint": "POST /v1/search",
            "description": "Search the web via SearXNG. Returns structured results as JSON.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 10, "description": "Max results to return"},
                    "categories": {"type": "string", "default": "general", "description": "Search category: general, news, images, science, it"},
                },
                "required": ["query"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "results": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "url": {"type": "string"}, "snippet": {"type": "string"}, "engine": {"type": "string"}}}},
                    "query": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
            "when_to_use": "When you need to find information, URLs, or recent content about a topic.",
            "when_not_to_use": "When you already have the URL and just need its content (use fetch instead).",
        },
        {
            "id": "fetch",
            "endpoint": "POST /v1/fetch",
            "description": "Fetch a URL using a stealth browser. Returns clean extracted content as markdown or plain text.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "format": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
                    "screenshot": {"type": "boolean", "default": False, "description": "Include base64 screenshot"},
                    "wait_for": {"type": "string", "description": "CSS selector to wait for before extracting"},
                    "wait_ms": {"type": "integer", "default": 0, "maximum": 20000},
                },
                "required": ["url"],
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "final_url": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "format": {"type": "string"},
                    "word_count": {"type": "integer"},
                    "screenshot_b64": {"type": "string"},
                },
            },
            "when_to_use": "When you need the content of a specific URL. Works with JS-heavy sites and bot-protected pages.",
            "when_not_to_use": "When you need to find URLs first (use search). When you only need structured data (use fetch + extract).",
        },
        {
            "id": "describe",
            "endpoint": "POST /v1/describe",
            "description": "Describe an image, screenshot, or webpage using vision model. Accepts image_url, image_b64, or page_url (screenshots the page first).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL of the image to describe"},
                    "image_b64": {"type": "string", "description": "Base64-encoded image data"},
                    "page_url": {"type": "string", "description": "URL of a webpage to screenshot and describe"},
                    "prompt": {"type": "string", "default": "Describe this image concisely.", "description": "Custom prompt for the vision model"},
                    "wait_for": {"type": "string", "description": "CSS selector to wait for before screenshotting (page_url only)"},
                    "wait_ms": {"type": "integer", "default": 0, "maximum": 20000, "description": "Milliseconds to wait after page load before screenshotting (page_url only)"},
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {"description": {"type": "string"}},
            },
            "when_to_use": "When you need to understand what's in an image, screenshot, diagram, or photo. Use page_url to screenshot and describe a webpage in one call.",
            "when_not_to_use": "When you already have the text content (use summarize instead).",
        },
        {
            "id": "transcribe",
            "endpoint": "POST /v1/transcribe",
            "description": "Transcribe audio to text using whisper.cpp.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "audio_url": {"type": "string", "description": "URL of the audio file"},
                    "audio_b64": {"type": "string", "description": "Base64-encoded audio data"},
                    "mime_type": {"type": "string", "default": "audio/wav", "description": "MIME type of audio"},
                    "language": {"type": "string", "default": "en", "description": "Language hint (ISO 639-1)"},
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "transcript": {"type": "string"},
                    "language": {"type": "string"},
                },
            },
            "when_to_use": "When you have an audio file or URL and need the spoken content as text.",
            "when_not_to_use": "When you have text already.",
        },
        {
            "id": "summarize",
            "endpoint": "POST /v1/summarize",
            "description": "Summarize long text into a concise version using the LLM.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to summarize"},
                    "max_tokens": {"type": "integer", "default": 200, "description": "Maximum tokens in the summary"},
                    "style": {"type": "string", "enum": ["brief", "detailed", "bullets"], "default": "brief"},
                },
                "required": ["text"],
            },
            "output_schema": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
            "when_to_use": "When you have a long text and need a shorter version preserving key information.",
            "when_not_to_use": "When you need structured data from text (use extract instead).",
        },
        {
            "id": "extract",
            "endpoint": "POST /v1/extract",
            "description": "Extract structured JSON data from text using a provided schema. LLM enforces the schema via grammar constraints.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to extract data from"},
                    "schema": {"type": "object", "description": "JSON Schema that the output must match"},
                },
                "required": ["text", "schema"],
            },
            "output_schema": {
                "type": "object",
                "properties": {"data": {"description": "Extracted data matching the provided schema (object or array)"}},
            },
            "when_to_use": "When you need specific structured fields from unstructured text (job listings, articles, profiles, etc.). Supports both object and array root schemas.",
            "when_not_to_use": "When you need a general summary (use summarize). When the data is already structured.",
        },
    ],
}


@router.get("/skills")
async def get_skills():
    """Return machine-readable skill cards for all available tools."""
    return SKILLS
