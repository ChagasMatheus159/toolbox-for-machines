# Toolbox

A self-contained, containerized tool service for AI agents.  
Dumb muscle. No thinking. Fire a request, get a result.

## What It Does

Provides 6 tools as REST endpoints at `:9600`:

| Tool | Endpoint | Backend |
|------|----------|---------|
| Web Search | `POST /v1/search` | SearXNG |
| Web Fetch | `POST /v1/fetch` | Camoufox + Crawl4AI |
| Image Description | `POST /v1/describe` | Qwen3-VL-8B |
| Audio Transcription | `POST /v1/transcribe` | whisper.cpp |
| Text Summarization | `POST /v1/summarize` | Qwen3-VL-8B |
| Data Extraction | `POST /v1/extract` | Qwen3-VL-8B + GBNF |

## Quick Start

```bash
cp .env.example .env
# Edit .env with your LLM host IP
docker compose up -d
```

## Discovery

Agents discover available tools at:
```
GET http://<host>:9600/v1/skills
```

## Architecture

See [SPEC.md](SPEC.md) for full details.

```
Agents → toolbox-api:9600 → { searxng, camoufox, whisper (internal) }
                           → Qwen3-VL-8B (remote GPU host, LAN)
```

## Docs

- [SPEC.md](SPEC.md) — Architecture & API specification
- [PLAN.md](PLAN.md) — Implementation phases
- [HARNESS_PROMPT.md](HARNESS_PROMPT.md) — Integration guide for consuming agents
- [SETUP_LLM_HOST.md](SETUP_LLM_HOST.md) — GPU host setup instructions
