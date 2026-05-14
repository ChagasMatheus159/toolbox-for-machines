# Toolbox — Second Sweep

Round 2. The first sweep fixed 5 bugs and added SSRF validation. This sweep found that the validation has gaps, describe has a new caching bug introduced with the `page_url` implementation, and there's a cluster of smaller cleanup items. Fix everything below.

**Project root:** `/home/humano/Projects/toolbox`  
**Previous work log:** `/home/humano/Projects/toolbox/CHANGELOG.md`

> **Before anything else:** the current running process is stale — it predates the CHANGELOG fixes. After your changes, the service needs a rebuild:
> ```bash
> docker compose build api && docker compose up -d api
> ```

---

## Bugs to Fix

### BUG-1: `0.0.0.0` bypasses SSRF validation
**File:** `api/src/toolbox/validation.py`

`IPv4Address('0.0.0.0').is_loopback` is `False` and `is_link_local` is `False` in Python's `ipaddress` module, so `http://0.0.0.0/` passes the check. On Linux, connecting to `0.0.0.0` typically routes to the local host.

**Fix:** Add `addr.is_unspecified` to the block condition:
```python
if addr.is_loopback or addr.is_link_local or addr.is_unspecified:
```

---

### BUG-2: IPv4-mapped IPv6 addresses bypass SSRF validation
**File:** `api/src/toolbox/validation.py`

`IPv6Address('::ffff:127.0.0.1').is_loopback` is `False` in Python — IPv4-mapped addresses are not considered loopback even though they resolve to 127.0.0.1. `http://[::ffff:127.0.0.1]/` passes validation today.

**Fix:** After the loopback/link-local/unspecified check, add an IPv4-mapped check:
```python
if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
    mapped = addr.ipv4_mapped
    if mapped.is_loopback or mapped.is_link_local or mapped.is_unspecified:
        raise HTTPException(
            status_code=400,
            detail="Access to loopback/link-local addresses is not allowed.",
        )
```

---

### BUG-3: `socket.getaddrinfo()` blocks the async event loop
**File:** `api/src/toolbox/validation.py`

`socket.getaddrinfo()` is a synchronous blocking call sitting inside an async FastAPI handler. Slow or unresponsive DNS servers will block the entire uvicorn event loop. Since `validate_url` is called from three endpoints (`/v1/fetch`, `/v1/describe`, `/v1/transcribe`), a DNS stall blocks all concurrent requests.

**Fix:** `validate_url` needs to become an async function that uses `asyncio.get_event_loop().run_in_executor` for the DNS resolution. Update the signature and all three call sites.

```python
# validation.py
import asyncio

async def validate_url(url: str) -> None:
    ...
    # Instead of socket.getaddrinfo(...):
    loop = asyncio.get_event_loop()
    try:
        resolved = await loop.run_in_executor(
            None, socket.getaddrinfo, hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
    except socket.gaierror:
        return
    ...
```

Update call sites:
```python
# fetch.py, describe.py, transcribe.py
await validate_url(req.url)
```

---

### BUG-4: `describe` `page_url` writes to cache even when caching is disabled for that request
**File:** `api/src/toolbox/tools/describe.py`, line 130

When `page_url` is used with `wait_for` or `wait_ms > 0`, `use_cache` is set to `False` — the intent is to always fetch fresh content for dynamic pages. The cache *read* is correctly skipped. But `cache.set()` at line 130 is unconditional, so the result is always written.

Consequence: a request with `wait_for=".dynamic-content"` writes to cache (key = `page_url + prompt`, no wait params). A subsequent request *without* `wait_for` hits this cache entry, which may contain content that only appeared after the selector loaded. The cached entry also gets overwritten each time a wait-parameterized request runs. Inconsistent and unpredictable.

**Fix:** Guard the write:
```python
if use_cache:
    cache.set(cache_key, response.model_dump(), ttl_seconds=3600)
```

While you're here: the `page_url` cache key is `{"page_url": ..., "prompt": ...}` — it doesn't include `wait_for` or `wait_ms`. This is inconsistent with `fetch.py` which correctly includes them. Since `use_cache=False` when they're set, reads are already handled, but a future refactor could confuse this. Add a comment explaining the logic, or include `wait_for`/`wait_ms` in the key unconditionally (matching fetch.py's approach).

---

### BUG-5: `image_b64` hashes only first 200 bytes
**File:** `api/src/toolbox/tools/describe.py`, line 101

```python
b64_hash = hashlib.sha256(req.image_b64[:200].encode()).hexdigest()
```

Two different images that share the same first 200 base64 characters (same format, similar header, different content) collide in the cache. Screenshots of the same site taken seconds apart will share the same JPEG/PNG header bytes but differ in content — they'd get the same cache key and the second would be served the first's description.

**Fix:** Hash the full string:
```python
b64_hash = hashlib.sha256(req.image_b64.encode()).hexdigest()
```

The SHA-256 of a 40KB base64 string is negligible compared to the LLM call that follows.

---

### BUG-6: Image download error leaks exception details
**File:** `api/src/toolbox/tools/describe.py`, line 99

```python
raise HTTPException(status_code=502, detail=f"Failed to download image: {e}")
```

This exposes raw exception strings to callers — which can include internal network paths, IP addresses, or TLS handshake details. The LLM error in the same file was already sanitized to `"Vision model error."` in the last round. The image download error wasn't.

**Fix:**
```python
raise HTTPException(status_code=502, detail="Failed to download image.")
```

---

## Code Quality Fixes

### CLEAN-1: `import re` inside exception handler body
**File:** `api/src/toolbox/tools/fetch.py`, line 102

```python
except Exception as e:
    ...
    try:
        ...
        import re   # ← should be at module level
        title_search = re.search(...)
```

Move `import re` to the top of the file with the other imports.

---

### CLEAN-2: Unused `import tempfile`
**File:** `api/src/toolbox/tools/transcribe.py`, line 5

`tempfile` is imported but never used. It's a leftover from an earlier implementation that wrote audio to disk before sending to whisper. Remove it.

---

### CLEAN-3: Stale docstring in `extract_content`
**File:** `api/src/toolbox/tools/fetch.py`, line 36

```python
def extract_content(html: str, output_format: str) -> str:
    """Extract main content from HTML using trafilatura (fallback for Crawl4AI)."""
```

Crawl4AI was removed in the last round. Update to:
```python
    """Extract main content from HTML using trafilatura."""
```

---

### CLEAN-4: `healthz` runs four backend checks sequentially
**File:** `api/src/toolbox/main.py`

The four backend health checks (`searxng`, `camoufox`, `whisper`, `llm`) are sequential `await` calls. Worst-case latency is the sum of all four timeouts (3+5+3+5 = 16 seconds). They're independent — run them in parallel with `asyncio.gather`.

Replace the four separate try/except blocks with:
```python
import asyncio

async def check_searxng(http):
    try:
        r = await http.get(f"{settings.searxng_url}/", timeout=3)
        return "healthy" if r.status_code == 200 else "unhealthy"
    except Exception:
        return "unreachable"

# ... similar helpers for camoufox, whisper, llm ...

results = await asyncio.gather(
    check_searxng(app.state.http),
    check_camoufox(app.state.http),
    check_whisper(app.state.http),
    check_llm(app.state.http),
)
backends = dict(zip(["searxng", "camoufox", "whisper", "llm"], results))
```

Keep the helpers as local async functions inside `healthz`, or module-level — your call.

---

### CLEAN-5: `categories` field accepts any string
**File:** `api/src/toolbox/tools/search.py`, line 23

```python
categories: str = "general"
```

No validation. An agent could send `"categories": "garbage"` and it silently passes to SearXNG. The valid values are `general`, `news`, `images`, `science`, `it` (documented in the skills card and the code).

**Fix:** Add a pattern validator:
```python
categories: str = Field(default="general", pattern="^(general|news|images|science|it)$")
```

Note: `SLOW_CATEGORIES` in the same file includes `"files"` and `"social media"` which are valid SearXNG categories but not documented anywhere user-facing. Either add them to the pattern (and the skills card) or remove them from `SLOW_CATEGORIES`. Pick one.

---

## Lower Priority (Do If Time Allows)

**No size limit on image/audio downloads.**  
`describe.py` calls `r.content` on the image response and `transcribe.py` calls `r.content` on the audio response — both load the full body into memory. A 200MB audio URL would OOM the process. Add a streaming size check or a hard `Content-Length` pre-check:
```python
content_length = int(r.headers.get("content-length", 0))
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB
if content_length > MAX_IMAGE_BYTES:
    raise HTTPException(status_code=400, detail="Image too large (max 10MB).")
```
Do the same for `transcribe.py` with a higher limit (e.g. 100MB for audio).

**SUMMARIZE prompt uses `{max_tokens}` as a word-count hint.**  
`prompts.py`: `"Condense the following text to {max_tokens} tokens maximum."` — models don't know token counts intuitively. Consider `"Condense to approximately {words} words."` where `words = max_tokens * 3 // 4`. Not critical, but produces more consistent output lengths.

---

## Verification After Deploy

```bash
# BUG-1: 0.0.0.0 blocked
curl -s -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "http://0.0.0.0/test"}' | grep -c '"detail"'
# → 1 (400 returned)

# BUG-2: IPv4-mapped IPv6 blocked
curl -s -w "%{http_code}" -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "http://[::ffff:127.0.0.1]/test"}' -o /dev/null
# → 400

# BUG-4: page_url with wait_for does NOT write to cache
# Call 1 with wait_for (should take >1s — live LLM call)
time curl -s -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"page_url": "https://example.com", "prompt": "What text?", "wait_ms": 100}'
# Call 2 without wait_for (should also take >1s — NOT a cache hit)
time curl -s -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"page_url": "https://example.com", "prompt": "What text?"}'

# CLEAN-4: healthz parallel (should complete in ~max(backend latency), not sum)
time curl -s http://localhost:9600/healthz
```

---

## Files to Change

```
api/src/toolbox/validation.py        — BUG-1, BUG-2, BUG-3
api/src/toolbox/tools/describe.py    — BUG-4, BUG-5, BUG-6
api/src/toolbox/tools/fetch.py       — CLEAN-1, CLEAN-3
api/src/toolbox/tools/transcribe.py  — CLEAN-2
api/src/toolbox/main.py              — CLEAN-4
api/src/toolbox/tools/search.py      — CLEAN-5
```

Update `CHANGELOG.md` with everything you change.
