# Toolbox — Implementation Plan

Build order is designed so each phase is independently testable.

---

## Phase 1: Project Skeleton & Infrastructure

- [ ] Create `toolbox/docker-compose.yml` with all 4 services (api, searxng, camoufox, whisper) stubbed
- [ ] Create `toolbox/.env.example` with all config vars documented
- [ ] Create `toolbox/api/Dockerfile` (Python 3.12 slim)
- [ ] Create `toolbox/api/pyproject.toml` (dependencies: fastapi, uvicorn, httpx, crawl4ai, openai, pydantic)
- [ ] Create `toolbox/api/src/toolbox/__init__.py`
- [ ] Create `toolbox/api/src/toolbox/main.py` — FastAPI app with lifespan, CORS, health endpoint
- [ ] Create `toolbox/api/src/toolbox/config.py` — Pydantic Settings from env vars

**Test:** `docker compose up api` starts and `/healthz` returns 200.

---

## Phase 2: SearXNG + Search Endpoint

- [ ] Create `toolbox/config/searxng/settings.yml` — JSON-only, no UI, tuned for API use
- [ ] Wire up searxng service in docker-compose (internal-only, no host port)
- [ ] Create `toolbox/api/src/toolbox/tools/search.py` — POST /v1/search implementation
- [ ] Implement SearXNG client (httpx GET with `?format=json&q=...`)
- [ ] Response model: results array with title, url, snippet, engine

**Test:** `POST /v1/search {"query": "test"}` returns SearXNG JSON results.

---

## Phase 3: Camoufox + Fetch Endpoint

- [ ] Create `toolbox/camoufox/Dockerfile` (reuse from hermes-agent stack)
- [ ] Create `toolbox/camoufox/server.py` (copy from hermes-agent, adjust if needed)
- [ ] Create `toolbox/camoufox/requirements.txt`
- [ ] Wire up camoufox service in docker-compose (internal-only)
- [ ] Create `toolbox/api/src/toolbox/tools/fetch.py` — POST /v1/fetch implementation
- [ ] Integrate Crawl4AI for content extraction (markdown output from raw HTML)
- [ ] Fallback to trafilatura if Crawl4AI fails

**Test:** `POST /v1/fetch {"url": "https://example.com"}` returns markdown content.

---

## Phase 4: Cache Layer

- [ ] Create `toolbox/api/src/toolbox/cache.py` — SQLite cache with TTL
- [ ] Implement `get(key)` and `set(key, value, ttl)` methods
- [ ] Add background task for stale entry cleanup
- [ ] Wire cache into search and fetch endpoints
- [ ] Add `cache-data` volume in docker-compose

**Test:** Second identical request returns cached result (check response time).

---

## Phase 5: LLM Client + Summarize Endpoint

- [ ] Create `toolbox/api/src/toolbox/llm.py` — OpenAI-compatible client with semaphore
- [ ] Create `toolbox/api/src/toolbox/prompts.py` — All system prompts
- [ ] Implement async semaphore (`LLM_MAX_CONCURRENT`)
- [ ] Implement timeout handling
- [ ] Create `toolbox/api/src/toolbox/tools/summarize.py` — POST /v1/summarize
- [ ] Add LLM health check in `/healthz`

**Test:** `POST /v1/summarize {"text": "...", "max_tokens": 100}` returns summary from Qwen3-VL.

---

## Phase 6: Describe Endpoint (Vision)

- [ ] Create `toolbox/api/src/toolbox/tools/describe.py` — POST /v1/describe
- [ ] Handle image_url input (download image, encode b64, send to LLM)
- [ ] Handle image_b64 input (send directly)
- [ ] Vision system prompt enforcement

**Test:** `POST /v1/describe {"image_url": "https://..."}` returns description.

---

## Phase 7: Extract Endpoint (Structured Output)

- [ ] Create `toolbox/api/src/toolbox/tools/extract.py` — POST /v1/extract
- [ ] Implement JSON Schema → GBNF grammar converter (or use llama.cpp's `response_format` if supported)
- [ ] System prompt with schema injection
- [ ] JSON validation of LLM output before returning

**Test:** `POST /v1/extract {"text": "...", "schema": {...}}` returns valid JSON matching schema.

---

## Phase 8: Whisper + Transcribe Endpoint

- [ ] Create `toolbox/whisper/Dockerfile` — whisper.cpp server with medium model
- [ ] Wire up whisper service in docker-compose (internal-only)
- [ ] Create `toolbox/api/src/toolbox/tools/transcribe.py` — POST /v1/transcribe
- [ ] Handle audio_url (download → forward to whisper)
- [ ] Handle audio_b64 (decode → forward to whisper)
- [ ] Add whisper health check

**Test:** `POST /v1/transcribe {"audio_url": "..."}` returns transcript.

---

## Phase 9: Skill Cards & Discovery

- [ ] Create `toolbox/api/src/toolbox/skills.py` — skill card definitions for all 6 tools
- [ ] Implement `GET /v1/skills` endpoint
- [ ] Include input_schema, output_schema, when_to_use, examples for each
- [ ] Validate skill cards match actual endpoint schemas (Pydantic models)

**Test:** `GET /v1/skills` returns complete, valid skill definitions.

---

## Phase 10: Polish & Documentation

- [ ] Create `toolbox/README.md` — setup instructions, quick start, usage examples
- [ ] Add health checks to all services in docker-compose
- [ ] Add restart policies
- [ ] Add resource limits (mem_limit for camoufox)
- [ ] Test full stack with `docker compose up`
- [ ] Verify all 6 endpoints work end-to-end

---

## Build Order Rationale

```
Phase 1 (skeleton)     → Can run the container
Phase 2 (search)       → First useful endpoint, no LLM needed
Phase 3 (fetch)        → Second endpoint, no LLM needed
Phase 4 (cache)        → Improves 2+3, still no LLM
Phase 5 (summarize)    → First LLM endpoint, validates connectivity
Phase 6 (describe)     → Adds vision, reuses LLM client
Phase 7 (extract)      → Most complex LLM task, builds on 5+6
Phase 8 (transcribe)   → Independent, can be built in parallel
Phase 9 (skills)       → Discovery layer, needs all endpoints done
Phase 10 (polish)      → Final integration testing
```

Non-LLM endpoints first (phases 2-4) means the toolbox is partially useful even before the GPU host is set up with Qwen3-VL.
