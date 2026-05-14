# Toolbox Changelog

## 2026-05-14 — Sweep 2: Validation Hardening, Caching Fixes, Cleanup

### Bug Fixes (6)

**BUG-1: `0.0.0.0` bypasses SSRF validation**
- File: `api/src/toolbox/validation.py`
- Added `addr.is_unspecified` to the block condition
- `http://0.0.0.0/` now returns 400

**BUG-2: IPv4-mapped IPv6 addresses bypass SSRF validation**
- File: `api/src/toolbox/validation.py`
- Added check for `::ffff:127.0.0.1` style addresses
- After main check, extracts `.ipv4_mapped` and re-checks loopback/link-local

**BUG-3: `socket.getaddrinfo()` blocks the async event loop**
- File: `api/src/toolbox/validation.py`
- `validate_url` is now `async` — DNS resolution runs via `run_in_executor`
- Updated all three call sites (`fetch.py`, `describe.py`, `transcribe.py`) to `await`

**BUG-4: `describe` `page_url` writes to cache even when caching is disabled**
- File: `api/src/toolbox/tools/describe.py`
- Cache write is now guarded: only writes when `page_url` has no `wait_for`/`wait_ms`
- Prevents stale dynamic-content screenshots from polluting the cache

**BUG-5: `image_b64` hashes only first 200 bytes — cache collisions**
- File: `api/src/toolbox/tools/describe.py`
- Now hashes the full base64 string: `hashlib.sha256(req.image_b64.encode())`

**BUG-6: Image download error leaks exception details**
- File: `api/src/toolbox/tools/describe.py`
- Sanitized to generic `"Failed to download image."` (matching vision error style)

### Code Quality (5)

**CLEAN-1:** Moved `import re` from inside exception handler to module-level (`fetch.py`)

**CLEAN-2:** Removed unused `import tempfile` (`transcribe.py`)

**CLEAN-3:** Updated stale docstring referencing Crawl4AI (`fetch.py`)

**CLEAN-4:** Health check now runs all 4 backend checks in parallel via `asyncio.gather` (`main.py`)
- Worst-case latency: max(timeouts) instead of sum(timeouts) — 5s vs 16s

**CLEAN-5:** Added pattern validation to `categories` field (`search.py`)
- Only accepts: `general`, `news`, `images`, `science`, `it`
- Removed undocumented `files` and `social media` from `SLOW_CATEGORIES`

### Additional Improvements

**Size limits on downloads**
- Images: 10MB max (`describe.py`) — returns 400 if exceeded
- Audio: 100MB max (`transcribe.py`) — returns 400 if exceeded
- Prevents OOM from oversized URL downloads

**Summarize prompt uses word count**
- `prompts.py`: Changed from `{max_tokens} tokens` to `{words} words`
- Models understand word counts better than token counts

**Error sanitization in transcribe**
- `transcribe.py`: Audio download and decode errors no longer leak exception details

### Files Changed

```
api/src/toolbox/validation.py        — BUG-1, BUG-2, BUG-3 (async, 0.0.0.0, IPv6-mapped)
api/src/toolbox/tools/describe.py    — BUG-4, BUG-5, BUG-6, size limit
api/src/toolbox/tools/fetch.py       — CLEAN-1, CLEAN-3
api/src/toolbox/tools/transcribe.py  — CLEAN-2, size limit, error sanitization
api/src/toolbox/main.py              — CLEAN-4 (parallel healthz)
api/src/toolbox/tools/search.py      — CLEAN-5 (categories validation)
api/src/toolbox/tools/summarize.py   — word count prompt
api/src/toolbox/prompts.py           — word count instead of token count
```

---

## 2026-05-14 — Sweep 1: Bug Fixes, Security Hardening, Dead Code Removal

### Bug Fixes (5)

**BUG-1: `page_url` not implemented in `/v1/describe`**
- File: `api/src/toolbox/tools/describe.py`
- Added `page_url`, `wait_for`, `wait_ms` fields to `DescribeRequest`
- When `page_url` is provided, screenshots the page via Camoufox then sends the screenshot to the vision model
- Cache behavior: `page_url` results are cached unless `wait_for` or `wait_ms > 0` (dynamic content)
- Updated `api/src/toolbox/skills.py` describe skill card with new fields

**BUG-2: `hash()` used for cache keys — non-deterministic across restarts**
- Files: `api/src/toolbox/tools/summarize.py`, `extract.py`, `describe.py`
- Replaced all `hash(...)` calls with `hashlib.sha256(...).hexdigest()`
- Cache entries now survive container restarts

**BUG-3: Zero search results cached**
- File: `api/src/toolbox/tools/search.py`
- Cache write now only happens when `len(results) > 0`
- Transient SearXNG failures no longer poison the cache for 5 minutes

**BUG-4: Fetch cache key ignores `wait_for` and `wait_ms`**
- File: `api/src/toolbox/tools/fetch.py`
- Cache key now includes `wait_for` and `wait_ms` parameters
- Requests with different wait settings get independent cache entries

**BUG-5: Array-type schema in `/v1/extract` returns only first item**
- File: `api/src/toolbox/tools/extract.py`
- When schema has `"type": "array"` at root, it's now wrapped in an object for the LLM prompt
- After LLM response, the array is unwrapped from `data["items"]`
- `ExtractResponse.data` type changed from `dict` to `Union[dict, list]`
- Updated skills.py output schema to document this

### Security

**SSRF Protection — new file: `api/src/toolbox/validation.py`**
- All URL-accepting endpoints (`/v1/fetch`, `/v1/describe`, `/v1/transcribe`) now validate URLs before processing
- Blocked: `file://`, `ftp://`, and all non-HTTP(S) schemes
- Blocked: loopback (127.x, ::1) and link-local (169.254.x) addresses
- Blocked: cloud metadata endpoint (169.254.169.254)
- Allowed: LAN private ranges (192.168.x, 10.x) — agents can fetch from LAN hosts
- Returns 400 with clear error message instead of passing through to backends
- Previously: `file:///etc/passwd` via `/v1/fetch` returned the Camoufox container's passwd file

**Error message sanitization**
- File: `api/src/toolbox/tools/fetch.py`
- Fetch errors no longer expose internal Docker hostnames (e.g., `http://toolbox-camoufox:8790/fetch`)
- Generic "Error: unable to fetch this URL." returned instead
- File: `api/src/toolbox/tools/describe.py`
- Vision model errors no longer include raw exception strings

### Code Cleanup

**Removed dead Crawl4AI code path**
- File: `api/src/toolbox/tools/fetch.py`
- The `from crawl4ai import extract_content` block always failed silently (wrong API signature)
- Removed the try/except and now calls trafilatura directly
- Removed `crawl4ai>=0.4.0` from `api/pyproject.toml` dependencies
- Net result: faster imports, smaller container image, no silent failures

### Files Changed

```
api/src/toolbox/validation.py       — NEW (URL validation)
api/src/toolbox/tools/describe.py   — BUG-1, BUG-2, security
api/src/toolbox/tools/extract.py    — BUG-2, BUG-5
api/src/toolbox/tools/summarize.py  — BUG-2
api/src/toolbox/tools/search.py     — BUG-3
api/src/toolbox/tools/fetch.py      — BUG-4, security, dead code removal
api/src/toolbox/skills.py           — describe + extract skill card updates
api/pyproject.toml                  — removed crawl4ai dependency
```

### API Changes (Backward-Compatible)

| Endpoint | Change |
|----------|--------|
| `POST /v1/describe` | Added optional fields: `page_url`, `wait_for`, `wait_ms` |
| `POST /v1/extract` | `data` field can now be a list (was always dict) |
| `POST /v1/fetch` | Invalid/internal URLs now return 400 instead of 502 |
| `POST /v1/describe` | Invalid URLs now return 400 instead of passing through |
| `POST /v1/transcribe` | Invalid URLs now return 400 instead of failing with DNS error |

### How to Deploy

```bash
cd ~/Projects/toolbox
docker compose build api
docker compose up -d api
```

### Verification

```bash
# BUG-1: page_url works
curl -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"page_url": "https://example.com", "prompt": "Describe this page"}'

# BUG-5: Array schema returns all items
curl -X POST http://localhost:9600/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "Alice (eng), Bob (design), Carol (PM)", "schema": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}}}}}'

# Security: file:// blocked
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "file:///etc/passwd"}'
# → 400: "URL scheme 'file' is not allowed. Use http or https."

# Security: loopback blocked
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "http://127.0.0.1:8790/healthz"}'
# → 400: "Access to loopback/link-local addresses is not allowed."

# LAN still allowed (agents can fetch from other LAN hosts)
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "http://192.168.3.50/some-page"}'
# → 200 (fetches normally)
```
