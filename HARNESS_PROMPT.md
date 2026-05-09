# Toolbox Integration Guide for Harness Developers

You are building an AI agent harness that consumes a **Toolbox** service. The toolbox provides web search, web fetch, vision, audio transcription, summarization, and structured data extraction as simple HTTP endpoints. Your harness should use these instead of implementing its own web access, vision, or content processing.

---

## Connection

```
Toolbox URL: http://192.168.3.118:9600
No authentication required.
Network: 192.168.3.0/24
```

**Health check:** `GET /healthz` — returns `{"status": "ok"}` when all backends are ready.

---

## Bootstrap: Discover Available Tools

At harness startup, fetch tool definitions:

```
GET http://<TOOLBOX_HOST>:9600/v1/skills
```

This returns a JSON object with full input/output schemas for every tool. Parse these and register them as available functions/tools for your agent. The response includes `when_to_use` and `when_not_to_use` guidance — include these in your agent's tool descriptions.

---

## Available Endpoints

### 1. `POST /v1/search` — Web Search
**When to use:** Find information, discover URLs, check recent content.  
**Input:** `{"query": "...", "limit": 10, "categories": "general"}`  
**Output:** `{"results": [{title, url, snippet, engine}], "count": N}`  
**Latency:** 2-5s. No LLM involved.

### 2. `POST /v1/fetch` — Stealth Web Fetch  
**When to use:** Get clean content from a known URL. Handles JS-rendered pages, bot protection.  
**Input:** `{"url": "...", "format": "markdown", "screenshot": false}`  
**Output:** `{"title": "...", "content": "# Markdown...", "word_count": N}`  
**Latency:** 3-15s. No LLM involved.  
**Tip:** Use `"format": "markdown"` for LLM consumption. Use `"screenshot": true` if you need to pass the page to `/v1/describe`.

### 3. `POST /v1/describe` — Image/Screenshot Description  
**When to use:** Understand images, screenshots, diagrams, charts.  
**Input:** `{"image_url": "https://..."} ` or `{"image_b64": "...", "prompt": "What data is shown?"}`  
**Output:** `{"description": "The image shows..."}`  
**Latency:** 5-30s (LLM inference). Queued if another LLM call is running.

### 4. `POST /v1/transcribe` — Audio to Text  
**When to use:** Convert audio files/recordings to text.  
**Input:** `{"audio_url": "https://..."} ` or `{"audio_b64": "...", "mime_type": "audio/mp3"}`  
**Output:** `{"transcript": "...", "language": "en"}`  
**Latency:** Roughly 1x realtime on CPU (5 min audio ≈ 5 min processing).

### 5. `POST /v1/summarize` — Text Compression  
**When to use:** Condense long content before feeding to your agent's context. Save tokens.  
**Input:** `{"text": "...", "max_tokens": 200, "style": "brief|detailed|bullets"}`  
**Output:** `{"summary": "..."}`  
**Latency:** 5-20s (LLM inference).  
**Tip:** Use this after `/v1/fetch` to compress large pages before your agent processes them.

### 6. `POST /v1/extract` — Structured Data Extraction  
**When to use:** Pull specific fields from unstructured text using a JSON schema.  
**Input:** `{"text": "...", "schema": {"type": "object", "properties": {...}, "required": [...]}}`  
**Output:** `{"data": {... matches your schema ...}}`  
**Latency:** 5-20s (LLM inference).  
**Tip:** The schema MUST be valid JSON Schema. Use `"type": "array"` for lists. Fields not found return `null`.

---

## Integration Patterns

### Pattern A: Register as function-calling tools
```python
TOOLBOX = "http://192.168.3.118:9600"

# At startup
skills = httpx.get(f"{TOOLBOX}/v1/skills").json()
for skill in skills["skills"]:
    register_tool(
        name=skill["id"],
        description=skill["description"],
        parameters=skill["input_schema"],
    )
```

### Pattern B: Wrapper functions
```python
TOOLBOX = "http://192.168.3.118:9600"

async def web_search(query: str, limit: int = 5) -> list[dict]:
    r = await httpx.post(f"{TOOLBOX}/v1/search", json={"query": query, "limit": limit})
    return r.json()["results"]

async def fetch_page(url: str) -> str:
    r = await httpx.post(f"{TOOLBOX}/v1/fetch", json={"url": url, "format": "markdown"})
    return r.json()["content"]

async def extract_data(text: str, schema: dict) -> dict:
    r = await httpx.post(f"{TOOLBOX}/v1/extract", json={"text": text, "schema": schema})
    return r.json()["data"]
```

### Pattern C: Chaining (search → fetch → summarize)
```python
# 1. Find relevant URLs
results = await web_search("topic of interest")
# 2. Fetch the best result
content = await fetch_page(results[0]["url"])
# 3. Summarize for context
summary = await summarize(content, max_tokens=150)
# Now 'summary' is a token-efficient context for your agent
```

---

## Important Constraints

1. **LLM endpoints queue** — describe, summarize, extract share ONE concurrency slot. If you fire all 3 at once, they execute serially (~15-30s each). Plan accordingly.

2. **Context limit** — The toolbox truncates inputs:
   - `/v1/summarize`: max ~6800 chars of input text
   - `/v1/extract`: max ~4800 chars of input text
   - For longer content, chunk it or summarize first.

3. **Timeouts** — LLM calls can take up to 60s. Transcription up to 120s. Set your HTTP client timeout accordingly.

4. **Cache** — Identical requests within the TTL return cached results instantly. Don't add randomness to queries if you want cache hits.

5. **No streaming** — All responses are complete JSON. No SSE, no WebSocket.

---

## Fixing Your Own Setup

If the toolbox is unreachable:
```bash
# Check if running
curl http://192.168.3.118:9600/healthz

# If not running, SSH to the host and start it
ssh 192.168.3.118
cd ~/Projects/toolbox && docker compose up -d

# Check individual backends
docker compose ps
docker compose logs api
```

If a backend is unhealthy:
```bash
# Restart specific service
docker compose restart camoufox  # or searxng, whisper

# Check LLM (runs on the same host)
curl http://192.168.3.118:8080/v1/models -H "Authorization: Bearer dontfuckup!"
```

---

## Don't Do This

- ❌ Don't send raw HTML to your own model — use `/v1/fetch` to get clean markdown
- ❌ Don't implement your own web scraping — the toolbox handles bot detection
- ❌ Don't call the LLM directly — use the toolbox endpoints that manage concurrency
- ❌ Don't cache results yourself — the toolbox caches with appropriate TTLs
- ❌ Don't parse `/v1/skills` response format manually — it's standard JSON Schema
