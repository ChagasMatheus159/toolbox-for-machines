"""POST /v1/describe — Image/screenshot description via vision model."""

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from toolbox.cache import cache
from toolbox.llm import chat
from toolbox.prompts import DESCRIBE

log = logging.getLogger("toolbox.describe")
router = APIRouter()


class DescribeRequest(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    prompt: str = "Describe this image concisely."


class DescribeResponse(BaseModel):
    description: str


@router.post("/describe", response_model=DescribeResponse)
async def describe(req: DescribeRequest, request: Request):
    """Describe an image using the vision model."""
    if not req.image_url and not req.image_b64:
        raise HTTPException(status_code=400, detail="Either image_url or image_b64 is required.")

    # If URL provided, download and convert to b64
    image_data_url: str
    if req.image_url:
        # Check cache
        cache_key = cache.make_key("describe", {"url": req.image_url, "prompt": req.prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            http = request.app.state.http
            r = await http.get(req.image_url, timeout=15)
            r.raise_for_status()
            content_type = r.headers.get("content-type", "image/png").split(";")[0]
            b64 = base64.b64encode(r.content).decode("ascii")
            image_data_url = f"data:{content_type};base64,{b64}"
        except Exception as e:
            log.error("Failed to download image %s: %s", req.image_url, e)
            raise HTTPException(status_code=502, detail=f"Failed to download image: {e}")
    else:
        cache_key = cache.make_key("describe", {"b64_hash": hash(req.image_b64[:100]), "prompt": req.prompt})
        cached = cache.get(cache_key)
        if cached:
            return cached
        # Assume it's already a proper base64 string, detect format or default to png
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
        raise HTTPException(status_code=502, detail=f"Vision model error: {e}")

    response = DescribeResponse(description=description)
    cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
    return response
