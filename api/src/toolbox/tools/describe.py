"""POST /v1/describe — Image/screenshot description via vision model."""

import base64
import hashlib
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.config import settings
from toolbox.llm import chat
from toolbox.prompts import DESCRIBE
from toolbox.validation import validate_url

log = logging.getLogger("toolbox.describe")
router = APIRouter()


class DescribeRequest(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    page_url: Optional[str] = None
    prompt: str = "Describe this image concisely."
    wait_for: Optional[str] = None
    wait_ms: int = Field(default=0, ge=0, le=20000)


class DescribeResponse(BaseModel):
    description: str


@router.post("/describe", response_model=DescribeResponse)
async def describe(req: DescribeRequest, request: Request):
    """Describe an image using the vision model."""
    if not req.image_url and not req.image_b64 and not req.page_url:
        raise HTTPException(
            status_code=400,
            detail="One of image_url, image_b64, or page_url is required.",
        )

    # Validate any user-provided URLs
    if req.page_url:
        await validate_url(req.page_url)
    if req.image_url:
        await validate_url(req.image_url)

    http = request.app.state.http
    image_data_url: str

    if req.page_url:
        # Screenshot a page via Camoufox, then describe
        use_cache = not req.wait_for and req.wait_ms == 0
        cache_key = cache.make_key("describe", {"page_url": req.page_url, "prompt": req.prompt})
        if use_cache:
            cached = cache.get(cache_key)
            if cached:
                return cached

        try:
            payload = {
                "url": req.page_url,
                "screenshot": True,
                "wait_for": req.wait_for,
                "wait_ms": req.wait_ms,
            }
            r = await http.post(
                f"{settings.camoufox_url}/fetch",
                json=payload,
                timeout=settings.fetch_timeout_seconds,
            )
            r.raise_for_status()
            data = r.json()
            screenshot_b64 = data.get("screenshot_b64")
            if not screenshot_b64:
                raise HTTPException(status_code=502, detail="Camoufox returned no screenshot.")
            image_data_url = f"data:image/png;base64,{screenshot_b64}"
        except HTTPException:
            raise
        except Exception as e:
            log.error("Camoufox screenshot failed for %s: %s", req.page_url, e)
            raise HTTPException(status_code=502, detail="Failed to screenshot page.")

    elif req.image_url:
        cache_key = cache.make_key("describe", {"url": req.image_url, "prompt": req.prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            r = await http.get(req.image_url, timeout=15)
            r.raise_for_status()
            # Check Content-Length header before reading body
            cl_header = r.headers.get("content-length")
            if cl_header and int(cl_header) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Image too large (max 10MB).")
            raw = r.content
            if len(raw) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Image too large (max 10MB).")
            content_type = r.headers.get("content-type", "image/png").split(";")[0]
            b64 = base64.b64encode(raw).decode("ascii")
            image_data_url = f"data:{content_type};base64,{b64}"
        except HTTPException:
            raise
        except Exception as e:
            log.error("Failed to download image %s: %s", req.image_url, e)
            raise HTTPException(status_code=502, detail="Failed to download image.")
    else:
        b64_hash = hashlib.sha256(req.image_b64.encode()).hexdigest()
        cache_key = cache.make_key("describe", {"b64_hash": b64_hash, "prompt": req.prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached
        if req.image_b64.startswith("data:"):
            image_data_url = req.image_b64
        else:
            image_data_url = f"data:image/png;base64,{req.image_b64}"

    # Call LLM with vision
    messages = [
        {"role": "system", "content": DESCRIBE},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": req.prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        },
    ]

    try:
        description = await chat(messages, max_tokens=300)
    except Exception as e:
        log.error("LLM vision request failed: %s", e)
        raise HTTPException(status_code=502, detail="Vision model error.")

    response = DescribeResponse(description=description)
    # Only cache when use_cache is not explicitly disabled (page_url with wait params)
    if not req.page_url or (not req.wait_for and req.wait_ms == 0):
        cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
    return response
