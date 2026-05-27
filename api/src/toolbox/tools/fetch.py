"""POST /v1/fetch — Stealth web fetch via Camoufox + content extraction."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.services import fetch as fetch_service, ToolboxError

router = APIRouter()


class FetchRequest(BaseModel):
    url: str
    format: str = Field(default="markdown", pattern="^(markdown|text)$")
    screenshot: bool = False
    wait_for: Optional[str] = None
    wait_ms: int = Field(default=0, ge=0, le=20000)


class FetchResponse(BaseModel):
    url: str
    final_url: str
    title: str
    content: str
    format: str
    word_count: int
    screenshot_b64: Optional[str] = None


@router.post("/fetch", response_model=FetchResponse)
async def fetch(req: FetchRequest):
    """Fetch a URL via stealth browser, return clean extracted content."""
    try:
        return await fetch_service(
            url=req.url,
            format=req.format,
            screenshot=req.screenshot,
            wait_for=req.wait_for,
            wait_ms=req.wait_ms,
        )
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
