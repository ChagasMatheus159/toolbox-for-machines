"""POST /v1/describe — Image/screenshot description via vision model."""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.services import describe as describe_service, ToolboxError

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
async def describe(req: DescribeRequest):
    """Describe an image using the vision model."""
    try:
        return await describe_service(
            image_url=req.image_url,
            image_b64=req.image_b64,
            page_url=req.page_url,
            prompt=req.prompt,
            wait_for=req.wait_for,
            wait_ms=req.wait_ms,
        )
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
