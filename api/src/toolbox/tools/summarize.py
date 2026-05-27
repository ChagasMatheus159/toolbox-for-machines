"""POST /v1/summarize — Text summarization via LLM."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.services import summarize as summarize_service, ToolboxError

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
    try:
        return await summarize_service(text=req.text, max_tokens=req.max_tokens, style=req.style)
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
