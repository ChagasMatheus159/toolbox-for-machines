"""POST /v1/search — Web search via SearXNG."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from toolbox.services import search as search_service, ToolboxError

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)
    categories: str = Field(default="general", pattern="^(general|news|images|science|it)$")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    engine: str


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str
    count: int


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    """Search the web via SearXNG. Returns structured JSON results."""
    try:
        return await search_service(query=req.query, limit=req.limit, categories=req.categories)
    except ToolboxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
