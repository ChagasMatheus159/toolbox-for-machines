# Toolbox Integration Prompt

> Give this to the agent building your harness/assistant.

---

## Context

You have access to a **Toolbox** service at `http://<TOOLBOX_HOST>:9600`. It provides tools as simple REST endpoints. No auth required.

## Available Tools

Discover all tools programmatically:
```
GET http://<TOOLBOX_HOST>:9600/v1/skills
```

This returns JSON with full input/output schemas for each tool.

## Quick Reference

| Tool | Method | Endpoint | What it does |
|------|--------|----------|--------------|
| Search | POST | `/v1/search` | Web search → JSON results (title, url, snippet) |
| Fetch | POST | `/v1/fetch` | URL → clean markdown content (stealth browser) |
| Describe | POST | `/v1/describe` | Image (URL or b64) → text description |
| Transcribe | POST | `/v1/transcribe` | Audio (URL or b64) → transcript text |
| Summarize | POST | `/v1/summarize` | Long text → short summary |
| Extract | POST | `/v1/extract` | Text + JSON schema → structured data matching schema |

## How to Use

All endpoints accept JSON, return JSON. Example:

```bash
# Search
curl -X POST http://toolbox:9600/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "kubernetes best practices 2025", "limit": 5}'

# Fetch a page
curl -X POST http://toolbox:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article", "format": "markdown"}'

# Extract structured data
curl -X POST http://toolbox:9600/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "schema": {"type":"object","properties":{"name":{"type":"string"},"price":{"type":"number"}},"required":["name"]}}'
```

## Integration Rules

1. **Call `/v1/skills` at startup** to get current tool definitions. Use them as your function/tool schemas.
2. **Each call is stateless** — no sessions, no context carried between requests.
3. **LLM-backed tools (describe, summarize, extract) may queue** — expect up to 60s timeout for these.
4. **Non-LLM tools (search, fetch, transcribe) are fast** — typically <5s.
5. **Fetch returns markdown by default** — optimized for LLM consumption.
6. **Extract uses schema constraints** — your schema MUST be valid JSON Schema. Fields not found return null.
7. **Don't send raw HTML to your own model** — use fetch to get clean content, or extract to get structured data. Save your tokens.
