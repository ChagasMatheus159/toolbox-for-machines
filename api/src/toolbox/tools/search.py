"""POST /v1/search — Web search via SearXNG."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.config import settings

log = logging.getLogger("toolbox.search")
router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=50)
    categories: str = "general"


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
async def search(req: SearchRequest, request: Request):
    """Search the web via SearXNG. Returns structured JSON results."""
    # Check cache
    cache_key = cache.make_key("search", req.model_dump())
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Query SearXNG
    http = request.app.state.http
    params = {
        "q": req.query,
        "format": "json",
        "categories": req.categories,
    }

    try:
        r = await http.get(f"{settings.searxng_url}/search", params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("SearXNG request failed: %s", e)
        return SearchResponse(results=[], query=req.query, count=0)

    # Parse results
    raw_results = data.get("results", [])[:req.limit]
    results = [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
            engine=item.get("engine", "unknown"),
        )
        for item in raw_results
    ]

    response = SearchResponse(results=results, query=req.query, count=len(results))

    # Cache for 5 minutes
    cache.set(cache_key, response.model_dump(), ttl_seconds=300)

    return response
