"""POST /v1/extract — Schema-guided structured data extraction via LLM."""

import json
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from toolbox.cache import cache
from toolbox.llm import chat
from toolbox.prompts import EXTRACT

log = logging.getLogger("toolbox.extract")
router = APIRouter()


class ExtractRequest(BaseModel):
    text: str
    schema: dict  # JSON Schema the output must match


class ExtractResponse(BaseModel):
    data: dict


@router.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest):
    """Extract structured JSON data from text using a provided schema."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    if not req.schema:
        raise HTTPException(status_code=400, detail="Schema cannot be empty.")

    # Check cache
    cache_key = cache.make_key("extract", {"text_hash": hash(req.text), "schema": req.schema})
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Truncate input to stay within 2048 context limit
    # Schema takes some tokens, so be conservative: ~1200 tokens for input (~4800 chars)
    max_input_chars = 4800
    input_text = req.text[:max_input_chars]

    # Build prompt
    schema_str = json.dumps(req.schema, indent=2)
    system_prompt = EXTRACT.format(schema=schema_str)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    try:
        # Request JSON output
        result = await chat(
            messages,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        log.error("LLM extract failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Extraction error: {e}")

    # Parse the JSON response
    try:
        # Strip markdown fences if the model added them despite instructions
        cleaned = result.strip()
        if cleaned.startswith("```"):
            # Remove first and last lines
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning("LLM returned invalid JSON: %s\nRaw: %s", e, result[:200])
        # Attempt a more aggressive parse
        try:
            # Find first { and last }
            start = result.index("{")
            end = result.rindex("}") + 1
            data = json.loads(result[start:end])
        except (ValueError, json.JSONDecodeError):
            raise HTTPException(
                status_code=502,
                detail=f"LLM returned invalid JSON. Raw output: {result[:300]}",
            )

    response = ExtractResponse(data=data)
    cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
    return response
