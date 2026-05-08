# Toolbox — Specification

> A self-contained, containerized tool service for AI agents.  
> Dumb muscle. No thinking. Fire a request, get a result.

---

## Overview

Toolbox is a unified REST API that gives AI agents/harnesses access to:

- **Web search** (SearXNG, JSON output)
- **Web fetch** (Camoufox stealth browser + content extraction via Crawl4AI)
- **Image/screenshot description** (Qwen3-VL-8B via llama.cpp)
- **Audio transcription** (whisper.cpp, CPU-only)
- **Text summarization** (Qwen3-VL-8B)
- **Schema-guided data extraction** (Qwen3-VL-8B + GBNF grammar constraints)

Agents call **one endpoint** (`host:9600`) and get back structured JSON.  
They never interact with SearXNG, Camoufox, or the LLM directly.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Consumers (any agent on LAN)                           │
│  • Roo (VSCode)                                         │
│  • Hermes Agent                                         │
│  • OpenHands / any future harness                       │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP :9600
                    ▼
┌─────────────────────────────────────────────────────────┐
│  Toolbox Docker Stack                                   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  toolbox-api (FastAPI)            :9600 exposed  │   │
│  │  • Routes requests to backends                   │   │
│  │  • Crawl4AI library (content extraction)         │   │
│  │  • System prompts for LLM calls                  │   │
│  │  • SQLite cache with TTL                         │   │
│  │  • Asyncio semaphore for LLM concurrency         │   │
│  └──────┬──────────┬──────────┬─────────────────────┘   │
│         │          │          │                          │
│  ┌──────┴───┐ ┌────┴─────┐ ┌─┴──────────┐              │
│  │ searxng   │ │ camoufox │ │ whisper    │              │
│  │ :8888     │ │ :8790    │ │ :8200      │              │
│  │ (internal)│ │(internal)│ │ (internal) │              │
│  └──────────┘ └──────────┘ └────────────┘              │
│                                                         │
└─────────────────────────────────────────────────────────┘
                    │ LAN
                    ▼
┌─────────────────────────────────────────────────────────┐
│  GPU Host (192.168.3.118)                               │
│  llama.cpp :8080 — Qwen3-VL-8B (Q4_K_M)               │
│  RX 6600 / 8GB VRAM / Vulkan                           │
│  Handles: vision, summarize, extract                    │
└─────────────────────────────────────────────────────────┘
```

---

## Design Principles

1. **Dumb muscle** — The toolbox does NOT think, plan, or orchestrate. The calling agent decides what tool to use and calls the specific endpoint.

2. **Token-efficient responses** — Every response is the minimum useful result. Raw HTML is never returned. Content is extracted, cleaned, and optionally summarized before returning.

3. **Stateless** — No sessions, no conversation memory. Each request is independent.

4. **Self-contained** — One `docker compose up` brings up everything the toolbox needs. Only external dependency is the LLM on the GPU host.

5. **Model-agnostic** — The LLM is accessed via OpenAI-compatible API. Swap Qwen3-VL for any model by changing `LLM_URL` and `LLM_MODEL`.

6. **No authentication** — Runs on LAN only. Not exposed to the internet.

---

## API Endpoints

### `GET /v1/skills`

Returns machine-readable skill cards describing all available tools. Agents fetch this at startup to know what's available.

**Response:**
```json
{
  "version": "1.0.0",
  "base_url": "http://toolbox:9600",
  "skills": [
    {
      "id": "search",
      "endpoint": "POST /v1/search",
      "description": "Search the web via SearXNG. Returns structured results as JSON.",
      "input_schema": { ... },
      "output_schema": { ... },
      "when_to_use": "When you need to find information, URLs, or recent content.",
      "when_not_to_use": "When you already have the URL (use fetch instead)."
    }
  ]
}
```

---

### `POST /v1/search`

Search the web. Returns structured JSON results from SearXNG.

**Request:**
```json
{
  "query": "rust async runtime comparison 2025",
  "limit": 10,
  "categories": "general"
}
```

**Response:**
```json
{
  "results": [
    {
      "title": "Comparing Tokio, async-std, and smol in 2025",
      "url": "https://example.com/article",
      "snippet": "A deep dive into the current state of...",
      "engine": "google"
    }
  ],
  "query": "rust async runtime comparison 2025",
  "count": 10
}
```

**Backend:** SearXNG with `?format=json`  
**LLM:** Not used  
**Cache TTL:** 5 minutes

---

### `POST /v1/fetch`

Fetch a URL using stealth browser, return clean extracted content.

**Request:**
```json
{
  "url": "https://example.com/article",
  "format": "markdown",
  "screenshot": false,
  "wait_for": null,
  "wait_ms": 0
}
```

**Response:**
```json
{
  "url": "https://example.com/article",
  "final_url": "https://example.com/article?ref=...",
  "title": "Article Title",
  "content": "# Article Title\n\nThe extracted content in markdown...",
  "format": "markdown",
  "word_count": 1523,
  "screenshot_b64": null
}
```

**Backend:** Camoufox (stealth fetch) → Crawl4AI (content extraction)  
**LLM:** Not used  
**Cache TTL:** 30 minutes

---

### `POST /v1/describe`

Describe an image or screenshot using vision model.

**Request (URL):**
```json
{
  "image_url": "https://example.com/photo.jpg",
  "prompt": "What text is visible in this image?"
}
```

**Request (base64):**
```json
{
  "image_b64": "/9j/4AAQ...",
  "prompt": "Describe the UI layout and any data shown."
}
```

**Response:**
```json
{
  "description": "The image shows a dashboard with three charts..."
}
```

**Backend:** Qwen3-VL-8B via llama.cpp  
**System prompt:** "You are an image describer. Describe what you see concisely. Focus on text, UI elements, data, and actionable information. Do not speculate. Return plain text only."  
**Cache TTL:** 1 hour (keyed on image hash + prompt)

---

### `POST /v1/transcribe`

Transcribe audio to text.

**Request:**
```json
{
  "audio_url": "https://example.com/podcast-clip.mp3"
}
```

**Request (base64):**
```json
{
  "audio_b64": "UklGRi...",
  "mime_type": "audio/wav",
  "language": "en"
}
```

**Response:**
```json
{
  "transcript": "Hello and welcome to the show. Today we're discussing...",
  "language": "en",
  "duration_seconds": 127.4
}
```

**Backend:** whisper.cpp (CPU, medium model)  
**LLM:** Not used  
**Cache TTL:** None (unique audio files)

---

### `POST /v1/summarize`

Summarize long text into a concise version.

**Request:**
```json
{
  "text": "... long article text ...",
  "max_tokens": 200,
  "style": "brief"
}
```

**Response:**
```json
{
  "summary": "The article discusses three main points: first...",
  "input_tokens": 3500,
  "output_tokens": 180
}
```

**Backend:** Qwen3-VL-8B via llama.cpp  
**System prompt:** "You are a summarizer. Condense the following text to {max_tokens} tokens maximum. Preserve key facts, names, numbers, and conclusions. Return the summary only, no preamble."  
**Cache TTL:** 1 hour (keyed on text hash + params)

---

### `POST /v1/extract`

Extract structured data from text using a provided JSON schema.

**Request:**
```json
{
  "text": "<html>... job listing page content ...</html>",
  "schema": {
    "type": "object",
    "properties": {
      "title": { "type": "string" },
      "company": { "type": "string" },
      "salary_min": { "type": "number" },
      "salary_max": { "type": "number" },
      "remote": { "type": "boolean" },
      "requirements": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["title", "company"]
  }
}
```

**Response:**
```json
{
  "data": {
    "title": "Senior Backend Engineer",
    "company": "Acme Corp",
    "salary_min": 120000,
    "salary_max": 180000,
    "remote": true,
    "requirements": ["Python", "PostgreSQL", "5+ years experience"]
  },
  "confidence": "high"
}
```

**Backend:** Qwen3-VL-8B via llama.cpp with GBNF grammar constraints  
**System prompt:** "You are a data extractor. Extract data from the text below and return ONLY valid JSON matching this schema: {schema}. If a field cannot be found, use null. No explanation, no markdown, just the JSON object."  
**Cache TTL:** 1 hour (keyed on text hash + schema hash)

---

### `GET /healthz`

Health check for the toolbox API itself.

**Response:**
```json
{
  "status": "ok",
  "backends": {
    "searxng": "healthy",
    "camoufox": "healthy",
    "whisper": "healthy",
    "llm": "healthy"
  }
}
```

---

## Internal Architecture

### Request Flow

```
Agent request → FastAPI router → check cache → if miss:
  → call backend (searxng / camoufox / llm / whisper)
  → format response
  → store in cache
  → return JSON
```

### LLM Concurrency Control

The LLM processes one request at a time (llama.cpp limitation with VRAM constraints). The toolbox uses an asyncio semaphore:

```python
llm_semaphore = asyncio.Semaphore(int(os.getenv("LLM_MAX_CONCURRENT", "1")))

async def call_llm(messages, grammar=None):
    async with llm_semaphore:
        return await httpx_client.post(LLM_URL + "/chat/completions", ...)
```

Non-LLM endpoints (search, fetch, transcribe) run fully parallel with no limits.

### System Prompts

Each LLM-backed endpoint uses a rigid system prompt stored in `prompts.py`. These enforce:
- Output format (plain text or JSON only)
- No preamble, no explanation
- Strict adherence to the task

### GBNF Grammar Constraints

For the `/v1/extract` endpoint, the toolbox converts the caller's JSON schema into a GBNF grammar passed to llama.cpp. This guarantees structurally valid JSON output at the sampling level — the model physically cannot generate invalid tokens.

### Caching (SQLite)

```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,      -- hash of (endpoint + request params)
    response TEXT NOT NULL,    -- JSON response body
    created_at INTEGER,        -- unix timestamp
    ttl_seconds INTEGER        -- per-endpoint TTL
);
```

Cache is stored in a Docker volume. Stale entries are cleaned up on a background timer.

---

## Configuration

All via environment variables:

```env
# Toolbox API
TOOLBOX_PORT=9600

# Backend URLs (internal Docker network)
SEARXNG_URL=http://searxng:8888
CAMOUFOX_URL=http://camoufox:8790
WHISPER_URL=http://whisper:8200

# LLM (remote GPU host)
LLM_URL=http://192.168.3.118:8080/v1
LLM_API_KEY=dontfuckup!
LLM_MODEL=qwen3-vl-8b
LLM_MAX_CONCURRENT=1
LLM_TIMEOUT_SECONDS=60

# Fetch settings
FETCH_TIMEOUT_SECONDS=30

# Cache
CACHE_ENABLED=true
CACHE_DB_PATH=/data/cache.db
```

---

## Docker Compose Stack

```yaml
services:
  api:
    build: ./api
    ports:
      - "0.0.0.0:9600:9600"
    environment:
      - SEARXNG_URL=http://searxng:8888
      - CAMOUFOX_URL=http://camoufox:8790
      - WHISPER_URL=http://whisper:8200
      - LLM_URL=http://192.168.3.118:8080/v1
      - LLM_API_KEY=dontfuckup!
      - LLM_MODEL=qwen3-vl-8b
    volumes:
      - cache-data:/data
    depends_on:
      searxng: { condition: service_healthy }
      camoufox: { condition: service_healthy }

  searxng:
    image: searxng/searxng:latest
    volumes:
      - ./config/searxng/settings.yml:/etc/searxng/settings.yml:ro
    # No port exposed to host — internal only

  camoufox:
    build: ./camoufox
    mem_limit: 1536m
    # No port exposed to host — internal only

  whisper:
    build: ./whisper
    # No port exposed to host — internal only
    # CPU only — no GPU passthrough

volumes:
  cache-data:
```

Only port `9600` is exposed. All other services are internal to the Docker network.

---

## Technology Stack

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| API framework | Python 3.12 + FastAPI + uvicorn | Async-native, fast, matches existing code |
| HTTP client | httpx (async) | Non-blocking backend calls |
| Content extraction | Crawl4AI (library) | Proven extraction, returns markdown |
| Vision/text LLM | Qwen3-VL-8B via llama.cpp (remote) | Best structured output + vision at 8B |
| Audio transcription | whisper.cpp (CPU, medium model) | Purpose-built, accurate, no GPU needed |
| Web search | SearXNG (JSON API) | Self-hosted meta-search |
| Stealth browser | Camoufox (headless Firefox) | Bot-detection bypass |
| Cache | SQLite | Zero dependencies, Docker volume |
| Structured output | GBNF grammar constraints | Guaranteed valid JSON from LLM |

---

## Project Structure

```
toolbox/
├── docker-compose.yml
├── .env.example
├── SPEC.md
├── README.md
│
├── api/                          # The main FastAPI service
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── src/
│   │   └── toolbox/
│   │       ├── __init__.py
│   │       ├── main.py           # FastAPI app, lifespan, router mounting
│   │       ├── config.py         # Settings from env vars
│   │       ├── cache.py          # SQLite cache layer
│   │       ├── prompts.py        # System prompts for LLM
│   │       ├── llm.py            # LLM client + semaphore + GBNF
│   │       ├── skills.py         # Skill card definitions
│   │       └── tools/
│   │           ├── __init__.py
│   │           ├── search.py     # /v1/search
│   │           ├── fetch.py      # /v1/fetch
│   │           ├── describe.py   # /v1/describe
│   │           ├── transcribe.py # /v1/transcribe
│   │           ├── summarize.py  # /v1/summarize
│   │           └── extract.py    # /v1/extract
│   └── tests/
│       └── ...
│
├── camoufox/                     # Camoufox container build
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py                 # (reuse from hermes-agent stack)
│
├── whisper/                      # whisper.cpp container build
│   └── Dockerfile
│
└── config/
    └── searxng/
        └── settings.yml          # SearXNG config (JSON-only, no HTML UI)
```

---

## Skill Cards Format

Skill cards are the primary documentation for agents. Each tool has:

```json
{
  "id": "fetch",
  "endpoint": "POST /v1/fetch",
  "description": "Fetch a URL using a stealth browser. Returns clean extracted content as markdown or plain text. Handles JavaScript-rendered pages.",
  "input_schema": {
    "type": "object",
    "properties": {
      "url": { "type": "string", "description": "URL to fetch" },
      "format": { "type": "string", "enum": ["markdown", "text"], "default": "markdown" },
      "screenshot": { "type": "boolean", "default": false },
      "wait_for": { "type": "string", "description": "CSS selector to wait for before extracting" },
      "wait_ms": { "type": "integer", "default": 0, "maximum": 20000 }
    },
    "required": ["url"]
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "url": { "type": "string" },
      "title": { "type": "string" },
      "content": { "type": "string" },
      "word_count": { "type": "integer" }
    }
  },
  "when_to_use": "When you need the content of a specific URL. Works with JavaScript-heavy sites, paywalls, and bot-protected pages.",
  "when_not_to_use": "When you need to find URLs first (use search). When you need structured data from a page (use fetch + extract).",
  "examples": [
    {
      "input": { "url": "https://blog.rust-lang.org/2025/01/01/new-release.html" },
      "output": { "title": "Rust 1.85 Release", "content": "# Rust 1.85...", "word_count": 2100 }
    }
  ]
}
```

---

## SearXNG Configuration

Tuned for toolbox use (JSON API only, no HTML UI needed):

```yaml
use_default_settings: true

server:
  port: 8888
  bind_address: "0.0.0.0"
  secret_key: "toolbox-internal"
  limiter: false
  public_instance: false

search:
  safe_search: 0
  formats:
    - json         # Only JSON — no HTML/CSV needed
  default_locale: "en"

ui:
  static_use_hash: false
  # UI is irrelevant — only JSON API is used
```

---

## What's NOT In Scope (v1)

- ❌ MCP server protocol (v2)
- ❌ Authentication (LAN-only deployment)
- ❌ Streaming responses
- ❌ Code execution sandbox
- ❌ Document parsing (PDF/DOCX — can add later)
- ❌ Embedding generation
- ❌ Orchestration / planning / agent behavior
- ❌ Chat interface
- ❌ Rate limiting

---

## Future (v2+)

- MCP server entrypoint (`python -m toolbox.mcp`)
- `/v1/parse_document` — PDF/DOCX → text + structured extraction
- `/v1/execute` — sandboxed code execution
- Optional auth (API keys) for multi-tenant deployment
- WebSocket support for long-running tasks
- Prometheus metrics endpoint
