"""POST /v1/extract — Schema-guided structured data extraction via LLM."""

import hashlib
import json
import logging
from typing import Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.llm import chat
from toolbox.prompts import EXTRACT

log = logging.getLogger("toolbox.extract")
router = APIRouter()


class ExtractRequest(BaseModel):
    text: str
    json_schema: dict = Field(alias="schema", description="JSON Schema the output must match")

    model_config = {"populate_by_name": True}


class ExtractResponse(BaseModel):
    data: Union[dict, list]


@router.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest):
    """Extract structured JSON data from text using a provided schema."""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty.")
    if not req.json_schema:
        raise HTTPException(status_code=400, detail="Schema cannot be empty.")

    # Check cache
    text_hash = hashlib.sha256(req.text.encode()).hexdigest()
    cache_key = cache.make_key("extract", {"text_hash": text_hash, "schema": req.json_schema})
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Truncate input to stay within 2048 context limit
    # Schema takes some tokens, so be conservative: ~1200 tokens for input (~4800 chars)
    max_input_chars = 4800
    input_text = req.text[:max_input_chars]

    # Handle array-type root schemas by wrapping in an object
    is_array_schema = req.json_schema.get("type") == "array"
    if is_array_schema:
        effective_schema = {
            "type": "object",
            "properties": {"items": req.json_schema},
            "required": ["items"],
        }
    else:
        effective_schema = req.json_schema

    # Build prompt
    schema_str = json.dumps(effective_schema, indent=2)
    system_prompt = EXTRACT.format(schema=schema_str)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": input_text},
    ]

    try:
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
        cleaned = result.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        log.warning("LLM returned invalid JSON: %s\nRaw: %s", e, result[:200])
        try:
            start = result.index("{")
            end = result.rindex("}") + 1
            data = json.loads(result[start:end])
        except (ValueError, json.JSONDecodeError):
            raise HTTPException(
                status_code=502,
                detail=f"LLM returned invalid JSON. Raw output: {result[:300]}",
            )

    # Unwrap array results
    if is_array_schema and isinstance(data, dict) and "items" in data:
        data = data["items"]

    response = ExtractResponse(data=data)
    cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
    return response
