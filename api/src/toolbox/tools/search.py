"""POST /v1/search — Web search via SearXNG."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from toolbox.cache import cache
from toolbox.config import settings

log = logging.getLogger("toolbox.search")
router = APIRouter()

# Categories that use slower engines and need more time
SLOW_CATEGORIES = {"it", "science", "files", "social media"}
SLOW_TIMEOUT = 20  # seconds
DEFAULT_TIMEOUT = 10  # seconds


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

    # Use longer timeout for slow engine categories
    timeout = SLOW_TIMEOUT if req.categories.lower() in SLOW_CATEGORIES else DEFAULT_TIMEOUT

    try:
        r = await http.get(f"{settings.searxng_url}/search", params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.error("SearXNG request failed (category=%s, timeout=%ds): %s", req.categories, timeout, e)
        # For slow categories, retry with "general" as fallback
        if req.categories.lower() in SLOW_CATEGORIES:
            log.info("Retrying with 'general' category as fallback for query: %s", req.query)
            params["categories"] = "general"
            try:
                r = await http.get(f"{settings.searxng_url}/search", params=params, timeout=DEFAULT_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            except Exception as e2:
                log.error("SearXNG fallback also failed: %s", e2)
                return SearchResponse(results=[], query=req.query, count=0)
        else:
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
