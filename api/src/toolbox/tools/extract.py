"""POST /v1/extract — Schema-guided structured data extraction via LLM."""

from typing import Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.services import extract as extract_service, ToolboxError

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
    try:
        return await extract_service(text=req.text, schema=req.json_schema)
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
