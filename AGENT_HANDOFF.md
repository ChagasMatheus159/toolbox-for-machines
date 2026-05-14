# Toolbox — Post-Sweep Context for Agents

You are working on the Toolbox project at `/home/humano/Projects/toolbox`. Two code sweeps were just completed. This document tells you what changed so you don't duplicate work or make assumptions based on stale code.

**Project root:** `/home/humano/Projects/toolbox`  
**Full changelog:** `/home/humano/Projects/toolbox/CHANGELOG.md`  
**Service:** REST API at `:9600` serving 6 tools to AI agents (search, fetch, describe, transcribe, summarize, extract)

---

## What Was Done

### Sweep 1 — Bug Fixes + Security

5 confirmed bugs fixed:
1. `/v1/describe` now accepts `page_url` (screenshots via Camoufox then describes with VLM)
2. Cache keys use `hashlib.sha256` instead of Python's `hash()` — survives restarts
3. `/v1/search` no longer caches zero-result responses
4. `/v1/fetch` cache key includes `wait_for` and `wait_ms` — different wait params get separate cache entries
5. `/v1/extract` handles array-type root schemas — wraps in object for LLM, unwraps after. `ExtractResponse.data` is now `Union[dict, list]`

Security:
- New file `api/src/toolbox/validation.py` — async URL validator on all URL-accepting endpoints
- Blocks: `file://`, non-HTTP schemes, loopback (127.x, ::1), link-local (169.254.x), unspecified (0.0.0.0), IPv4-mapped IPv6 loopback
- Allows: LAN private ranges (192.168.x, 10.x) — intentional, agents need LAN access
- Error messages sanitized — no more internal Docker hostnames or raw exceptions in responses

Code removal:
- Dead Crawl4AI code path removed from `fetch.py` (always failed silently)
- `crawl4ai` removed from `pyproject.toml` — trafilatura is the sole content extractor

### Sweep 2 — Validation Hardening + Cleanup

6 more bugs fixed:
1. `0.0.0.0` now blocked (`is_unspecified`)
2. IPv4-mapped IPv6 (`::ffff:127.0.0.1`) now blocked
3. `validate_url` is now `async` — DNS resolution uses `run_in_executor` to avoid blocking the event loop
4. `describe` with `page_url` + `wait_for`/`wait_ms` no longer writes to cache (prevents stale dynamic content)
5. `image_b64` cache key hashes the full string (was only first 200 chars — collision risk)
6. Image download errors sanitized (no more exception details in response)

Cleanup:
- `import re` moved to module level in `fetch.py`
- Unused `import tempfile` removed from `transcribe.py`
- Stale "fallback for Crawl4AI" docstring updated
- `/healthz` runs 4 backend checks in parallel via `asyncio.gather` (5s worst-case vs 16s)
- `categories` field in search validates against `general|news|images|science|it`

Improvements:
- Image downloads capped at 10MB, audio at 100MB (returns 400 if exceeded)
- Summarize prompt uses word count (`~{words} words`) instead of misleading token count

---

## Current File State

```
api/src/toolbox/
  main.py           — FastAPI app, parallel healthz, router mounting
  config.py         — Pydantic Settings (unchanged)
  cache.py          — SQLite TTL cache, SHA-256 keys (unchanged)
  llm.py            — Async OpenAI client, Semaphore(1) (unchanged)
  prompts.py        — System prompts (summarize now uses {words})
  skills.py         — /v1/skills with updated describe + extract cards
  validation.py     — NEW: async URL validator (SSRF protection)
  tools/
    search.py       — SearXNG, categories validated, no zero-result caching
    fetch.py        — Camoufox + trafilatura, URL validated, cache key includes wait params
    describe.py     — page_url support, URL validated, full b64 hash, size limit, guarded cache write
    transcribe.py   — URL validated, size limit, sanitized errors
    summarize.py    — hashlib cache key, word-count prompt
    extract.py      — hashlib cache key, array schema support
```

---

## What Still Needs Doing

The service is **not yet rebuilt**. The running container is stale. To deploy:

```bash
cd ~/Projects/toolbox
docker compose build api && docker compose up -d api
```

After deploy, verify with:
```bash
# Health
curl http://localhost:9600/healthz

# page_url (new feature)
curl -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"page_url": "https://example.com", "prompt": "What text is on this page?"}'

# SSRF blocked
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "file:///etc/passwd"}'

# Array extract (new behavior)
curl -X POST http://localhost:9600/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Alice (eng), Bob (design), Carol (PM)", "schema": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}}}}}'
```

---

## Known Remaining Issues (Not Fixed)

- `audio_url` downloads fail when the API container can't resolve external DNS — agents should prefer `audio_b64`
- SQLite cache uses `check_same_thread=False` without a write lock — could hit `database is locked` under heavy concurrent writes. Consider `aiosqlite` if this becomes a problem.
- Camoufox `_request_count` is incremented before the semaphore — counter is imprecise under burst traffic (cosmetic, doesn't cause failures)
- No cache at all for `/v1/transcribe` — identical audio re-transcribes every time

---

## Key Design Decisions to Respect

- **No auth** — LAN-only service, intentional
- **LLM semaphore = 1** — single GPU (RX 6600, 8GB VRAM), cannot parallelize
- **Trafilatura is the sole content extractor** — Crawl4AI was removed
- **URL validation allows LAN** — agents legitimately fetch from 192.168.x hosts
- **`validate_url` is async** — always `await` it
- **Cache keys must use `hashlib.sha256`** — never Python's `hash()`
- **Error messages must not expose internals** — no exception strings, no Docker hostnames
