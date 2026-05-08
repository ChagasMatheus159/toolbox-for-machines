"""POST /v1/summarize — Text summarization via LLM."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.llm import chat
from toolbox.prompts import SUMMARIZE

log = logging.getLogger("toolbox.summarize")
router = APIRouter()


class SummarizeRequest(BaseModel):
    text: str
    max_tokens: int = Field(default=200, ge=20, le=500)
    style: str = Field(default="brief", pattern="^(brief|detailed|bullets)$")


class SummarizeResponse(BaseModel):
    summary: str


@router.post("/summarize", response_model=SummarizeResponse)
async def summarize(req: SummarizeRequest):
    """Summarize text using the LLM."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    # Check cache
    cache_key = cache.make_key("summarize", {"text_hash": hash(req.text), "max_tokens": req.max_tokens, "style": req.style})
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Truncate input to stay within 2048 context limit
    # Reserve ~300 tokens for system prompt + output → ~1700 tokens for input (~6800 chars)
    max_input_chars = 6800
    input_text = req.text[:max_input_chars]
    if len(req.text) > max_input_chars:
        input_text += "\n\n[... text truncated ...]"

    # Build prompt with style hint
    style_hint = ""
    if req.style == "bullets":
        style_hint = " Use bullet points."
    elif req.style == "detailed":
        style_hint = " Include supporting details."

    system_prompt = SUMMARIZE.format(max_tokens=req.max_tokens) + style_hint

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    try:
        summary = await chat(messages, max_tokens=req.max_tokens)
    except Exception as e:
        log.error("LLM summarize failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Summarization error: {e}")

    response = SummarizeResponse(summary=summary)
    cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
    return response
