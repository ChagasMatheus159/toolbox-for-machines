# Toolbox Architecture

## Overview

Toolbox is a **dumb-muscle tool service** for AI agents. It does not think, plan, or orchestrate. An agent calls a specific endpoint, the toolbox executes the task using the appropriate backend, and returns a clean result.

## Design Principles

1. **Stateless** — No sessions, no conversation memory. Each request is independent.
2. **Explicit routing** — The calling agent decides which tool to use. No AI-based request routing.
3. **Token-efficient** — Responses are always the minimum useful result. Raw HTML is never returned.
4. **Self-contained** — One `docker compose up` brings everything needed (except the remote LLM).
5. **Model-agnostic** — The LLM is accessed via OpenAI-compatible API. Swap models by changing env vars.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  Toolbox Docker Stack                                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  toolbox-api (FastAPI)                                    │   │
│  │                                                           │   │
│  │  ┌─────────┐  ┌─────────┐  ┌───────────┐  ┌──────────┐ │   │
│  │  │ search  │  │  fetch  │  │ describe  │  │summarize │ │   │
│  │  │ router  │  │ router  │  │  router   │  │ router   │ │   │
│  │  └────┬────┘  └────┬────┘  └─────┬─────┘  └────┬─────┘ │   │
│  │       │             │             │              │        │   │
│  │  ┌────┴────┐  ┌────┴────┐  ┌─────┴─────┐  ┌────┴─────┐ │   │
│  │  │ extract │  │transcr. │  │   cache    │  │   llm    │ │   │
│  │  │ router  │  │ router  │  │  (sqlite)  │  │ (client) │ │   │
│  │  └─────────┘  └─────────┘  └────────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│       │              │              │                │            │
│  ┌────┴────┐   ┌────┴────┐   ┌────┴────┐          │            │
│  │ searxng │   │camoufox │   │ whisper │          │            │
│  │  :8080  │   │  :8790  │   │  :8200  │          │            │
│  └─────────┘   └─────────┘   └─────────┘          │            │
└────────────────────────────────────────────────────┼────────────┘
                                                     │ LAN
                                               ┌──────┴──────┐
                                               │  Vision LLM │
                                               │ (external)  │
                                               │    :8080    │
                                               └─────────────┘
```

## Request Flow

```
Agent → HTTP POST → FastAPI Router → Check Cache
                                         │
                                    ┌────┴────┐
                                    │  HIT    │  MISS
                                    │         │
                                    ▼         ▼
                              Return      Call Backend
                              cached      (SearXNG/Camoufox/LLM/Whisper)
                              result           │
                                              ▼
                                        Format Response
                                              │
                                              ▼
                                        Store in Cache
                                              │
                                              ▼
                                        Return JSON
```

## Backend Responsibilities

| Backend | What it does | Why it exists |
|---------|-------------|---------------|
| **SearXNG** | Meta-search across Google, Bing, DuckDuckGo, etc. | Privacy-respecting, self-hosted, JSON API |
| **Camoufox** | Stealth headless Firefox with anti-detection | Bypasses bot protection, renders JS pages |
| **whisper.cpp** | Audio transcription (CPU, medium model) | Purpose-built speech-to-text, no GPU needed |
| **Vision LLM** | Vision, summarization, structured extraction | Any OpenAI-compatible endpoint (Qwen3-VL recommended for self-hosted) |

## LLM Integration

The LLM is accessed via the OpenAI-compatible chat completions API:

```python
POST {LLM_URL}/chat/completions
Authorization: Bearer {LLM_API_KEY}
{
  "model": "qwen3-vl-8b",
  "messages": [...],
  "max_tokens": 512,
  "temperature": 0.1
}
```

### Concurrency Control

Only one LLM request runs at a time (asyncio Semaphore). This prevents overloading the LLM backend and avoids rate limit errors. Non-LLM endpoints (search, fetch, transcribe) run fully parallel.

### System Prompts

Each LLM endpoint uses a rigid system prompt stored in `prompts.py`:
- **describe**: Focus on text, UI elements, data. Plain text output.
- **summarize**: Condense to N tokens. No preamble.
- **extract**: Output ONLY valid JSON matching the schema. No explanation.

### Context Usage

Toolbox truncates inputs to keep requests small. Each request uses ~1500-2500 tokens:
- System prompt: ~150 tokens
- Input content: ~500-1500 tokens (truncated by the API if larger)
- Output: ~200-500 tokens

## Caching

SQLite database at `/data/cache.db` (Docker volume):

```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,        -- SHA-256 of endpoint + params
    response TEXT NOT NULL,      -- JSON response
    created_at INTEGER NOT NULL, -- Unix timestamp
    ttl_seconds INTEGER NOT NULL -- Per-endpoint TTL
);
```

| Endpoint | TTL | Rationale |
|----------|-----|-----------|
| search | 5 min | Search results change frequently |
| fetch | 30 min | Page content is relatively stable |
| describe | 1 hour | Same image → same description |
| summarize | 1 hour | Same text → same summary |
| extract | 1 hour | Same text + schema → same result |
| transcribe | None | Audio files are unique |

## Content Extraction Pipeline

For `/v1/fetch`:

```
URL → Camoufox (stealth fetch, renders JS)
    → Raw HTML
    → trafilatura (algorithmic content extraction)
    → Clean markdown/text
    → Response
```

The extraction pipeline is entirely algorithmic (no LLM involved), making it fast and free.

## Security Model

- **No authentication** — designed for trusted LAN only
- **No port exposure** except 9600 — backends are internal-only
- **No internet egress** from the API container — only backend containers access the internet
- **No persistent state** except the cache (can be wiped anytime)
