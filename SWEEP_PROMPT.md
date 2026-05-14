# Toolbox — Full Code Sweep

You are doing a full code sweep of the Toolbox project. The goal is twofold: fix known bugs and find anything else worth fixing or improving.

**Project root:** `/home/humano/Projects/toolbox`  
**What it is:** A self-hosted REST API (FastAPI) that gives AI agents 6 tools — web search, web fetch, image description, audio transcription, text summarization, and structured data extraction. All tools are thin wrappers around SearXNG, Camoufox, whisper.cpp, and a remote Qwen3-VL-8B LLM.

---

## Known Bugs — Fix These First

A recent audit found 5 confirmed bugs. Fix all of them.

### BUG-1: `page_url` not implemented in `/v1/describe`

The Pi agent extension that consumes this API sends `page_url` as a parameter to `POST /v1/describe` for webpage screenshot-and-describe in one call. The server ignores it — `DescribeRequest` has no such field — and returns `400: Either image_url or image_b64 is required`.

**What needs to happen:** Add `page_url: Optional[str]` to `DescribeRequest` in `api/src/toolbox/tools/describe.py`. When `page_url` is provided, call the camoufox server at `settings.camoufox_url/fetch` with `{"url": page_url, "screenshot": true, "wait_for": wait_for, "wait_ms": wait_ms}`, extract `screenshot_b64` from the response, and use it as the image input to the VLM. Also add `wait_for: Optional[str]` and `wait_ms: int = 0` to the request model so callers can wait for JS to render before screenshotting.

Cache key for `page_url` mode should include `url + prompt` (like the `image_url` path). Do not cache `page_url` requests when `wait_for` or `wait_ms > 0` — dynamic content.

Also update `api/src/toolbox/skills.py` to add `page_url`, `wait_for`, `wait_ms` to the `describe` skill's input schema.

### BUG-2: `hash()` used for cache keys — breaks across restarts

Three files use Python's built-in `hash()` to pre-hash input before building cache keys:

```
api/src/toolbox/tools/extract.py:35   — hash(req.text)
api/src/toolbox/tools/summarize.py:33 — hash(req.text)
api/src/toolbox/tools/describe.py:54  — hash(req.image_b64[:100])
```

Python's `hash()` is randomized at startup (`PYTHONHASHSEED`). Cache entries written in one process are unreachable in the next — the cache fills with permanently orphaned rows and never gets hits for these three tools after a restart.

**Fix:** Replace all `hash(...)` calls with `hashlib.sha256(...encode()).hexdigest()`. Add `import hashlib` where missing. The `cache.py` `make_key` function already uses SHA-256 correctly — the bug is at the call sites.

### BUG-3: Zero search results are cached

In `api/src/toolbox/tools/search.py`, when SearXNG returns 0 results (transient engine failure), that empty response is cached for 5 minutes. The next call for the same query gets a cached empty result even after SearXNG recovers.

**Fix:** Only write to cache when `len(results) > 0`.

### BUG-4: Fetch cache key ignores `wait_for` and `wait_ms`

In `api/src/toolbox/tools/fetch.py`, the cache key is built from only `url` and `format`. A request with `wait_for=".loaded"` or `wait_ms=3000` will be served the cached version from a previous call that had no wait — silently delivering pre-JS-render content.

**Fix:** Include `wait_for` and `wait_ms` in the cache key. Change:
```python
cache_key = cache.make_key("fetch", {"url": req.url, "format": req.format})
```
to:
```python
cache_key = cache.make_key("fetch", {"url": req.url, "format": req.format, "wait_for": req.wait_for, "wait_ms": req.wait_ms})
```
Apply this same change to the second cache write inside the fallback path.

### BUG-5: Array-type schema in `/v1/extract` silently returns only first item

`extract.py` passes `response_format={"type": "json_object"}` to the LLM for all requests. This forces the LLM to output a JSON object, which means it cannot comply with an array root schema — it returns the first item only, with no error.

**Fix:** Detect when `req.schema.get("type") == "array"`. In that case, wrap the schema in `{"type": "object", "properties": {"items": <original_schema>}, "required": ["items"]}` before building the prompt, and after parsing the LLM response, return `data["items"]` as the `data` field. Also update `ExtractResponse` to accept `data: dict | list`.

---

## Sweep — Look for These Too

After the bugs, do a full sweep for anything else. Specifically:

**Security / correctness:**
- SSRF risk: `/v1/fetch`, `/v1/describe`, `/v1/transcribe` all accept arbitrary URLs. Should internal addresses (localhost, 127.x, 192.168.x, 10.x, 169.254.x) be blocked? The service is LAN-only but worth at least noting if this is intentional.
- Input sanitization: is `req.url` validated as a proper URL before being sent to Camoufox? An invalid URL (e.g. `"not-a-url"`) currently results in a 502 from Camoufox rather than a clean 400 from the API.
- Schema injection: `extract.py` embeds `json.dumps(req.schema)` directly into an LLM system prompt. Could a crafted schema override the prompt? Consider truncating the schema string.

**Robustness:**
- The SQLite cache uses `check_same_thread=False` but writes happen from async coroutines. Is there a risk of concurrent write contention? Should writes use a lock or be moved to a thread pool executor?
- `camoufox/server.py` has `_request_count` incremented without a lock. Concurrent requests could race on this counter. The semaphore prevents concurrent `_do_fetch` calls but the counter is incremented *before* the semaphore is acquired.
- Whisper transcription has no cache at all. A content-hash of the audio bytes would allow identical audio to skip re-transcription.
- `describe.py` downloads images synchronously with the main app's shared HTTP client (with a 30s timeout inherited from `fetch_timeout_seconds`). A very large image could block the event loop during download. Should use streaming.

**Code quality:**
- `fetch.py` has a dead import comment: `"extract_content as crawl4ai_extract"` — Crawl4AI is attempted first and always falls through to trafilatura. If it's not available, the try/except silently continues. Either add Crawl4AI to dependencies and commit to it, or remove the dead branch.
- `fetch.py` has duplicated fallback logic where `cache_key` might be referenced before assignment when `req.screenshot=True`. The fallback path does `cache.set(cache_key, ...)` — but `cache_key` was conditionally set only when `not req.screenshot`. Trace the control flow and verify there's no `NameError` waiting.
- `prompts.py` uses `{max_tokens}` in the SUMMARIZE prompt string as a count-guide for the LLM ("Condense the following text to {max_tokens} tokens maximum"). This is misleading — the model doesn't know how many tokens a sentence is. Consider switching to a word count estimate or removing the number and relying on `max_tokens` in the API call.
- Error messages from Camoufox failures embed the full httpx exception string. These can be verbose and include internal URLs (e.g. `http://toolbox-camoufox:8790/fetch`). Consider sanitizing before returning to callers.

**Missing features worth adding now (small lift):**
- `GET /v1/cache/stats` endpoint: return current cache row count, total size, and per-endpoint hit counts. Useful for debugging.
- `DELETE /v1/cache` endpoint: flush the cache. Useful when stale results are stuck.
- Health check should include cache DB reachability — currently it only checks the four backends.

---

## Constraints

- Do not add new dependencies unless necessary for a bug fix. The stack is intentionally minimal.
- Do not change the public API contract (request/response shapes) except where adding new optional fields (`page_url`, `wait_for`, `wait_ms` in describe is additive and backward-compatible).
- Do not touch `docker-compose.yml`, `.env`, or any config files — infrastructure is out of scope.
- Keep prompts in `prompts.py` short. The LLM runs with `-c 2048`.
- All tests should be verifiable with `curl` against the live service on `localhost:9600`.

---

## Reference

Full benchmark report with live test results and bug details:  
`/home/humano/Projects/pie/data/research/toolbox-benchmark-2026-05-14.md`

Source structure:
```
api/src/toolbox/
  main.py          — FastAPI app, lifespan, health check
  config.py        — pydantic-settings config
  cache.py         — SQLite TTL cache (SHA-256 keys — use this, not hash())
  llm.py           — async OpenAI client with Semaphore(1)
  prompts.py       — system prompts for LLM tools
  skills.py        — /v1/skills discovery endpoint
  tools/
    search.py      — POST /v1/search → SearXNG
    fetch.py       — POST /v1/fetch → Camoufox + trafilatura
    describe.py    — POST /v1/describe → download image → Qwen3-VL
    transcribe.py  — POST /v1/transcribe → whisper.cpp
    summarize.py   — POST /v1/summarize → LLM
    extract.py     — POST /v1/extract → LLM (json_object mode)
camoufox/server.py — Camoufox Playwright browser server
```

Report back: list everything you found and changed, with file:line references.
