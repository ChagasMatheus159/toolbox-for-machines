# Toolbox

A self-contained, containerized tool service for AI agents.  
Dumb muscle. No thinking. Fire a request, get a result.

## What It Does

Provides 6 tools as REST endpoints at `:9600`:

| Tool | Endpoint | Backend |
|------|----------|---------|
| Web Search | `POST /v1/search` | SearXNG |
| Web Fetch | `POST /v1/fetch` | Camoufox + trafilatura |
| Image Description | `POST /v1/describe` | Qwen3-VL-8B |
| Audio Transcription | `POST /v1/transcribe` | whisper.cpp |
| Text Summarization | `POST /v1/summarize` | Qwen3-VL-8B |
| Data Extraction | `POST /v1/extract` | Qwen3-VL-8B |

## Quick Start

```bash
cp .env.example .env
# Edit .env — set LLM_URL to your GPU host running Qwen3-VL-8B
docker compose up -d
```

Verify:
```bash
curl http://localhost:9600/healthz
# {"status": "ok", "backends": {"searxng": "healthy", "camoufox": "healthy", "whisper": "healthy", "llm": "healthy"}}
```

## Discovery

Agents discover available tools at startup:
```bash
curl http://localhost:9600/v1/skills
```

Returns machine-readable skill cards with full schemas, descriptions, and usage guidance.

## Example Usage

```bash
# Search
curl -X POST http://localhost:9600/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "rust async runtimes 2025", "limit": 5}'

# Fetch a page
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://blog.rust-lang.org/"}'

# Extract structured data
curl -X POST http://localhost:9600/v1/extract \
  -H "Content-Type: application/json" \
  -d '{"text": "...", "schema": {"type": "object", "properties": {"name": {"type": "string"}}}}'
```

## Stack

```
Agents → toolbox-api:9600 → { searxng, camoufox, whisper } (internal containers)
                           → Qwen3-VL-8B (remote GPU host, LAN)
```

| Container | Role | Resources |
|-----------|------|-----------|
| toolbox-api | FastAPI service | ~200MB RAM |
| toolbox-searxng | Meta-search engine | ~300MB RAM |
| toolbox-camoufox | Stealth headless browser | ~1.5GB RAM |
| toolbox-whisper | Audio transcription (CPU) | ~2GB RAM |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/API.md](docs/API.md) | Complete API reference with examples |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, caching |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Setup, configuration, troubleshooting |
| [SPEC.md](SPEC.md) | Original design specification |
| [HARNESS_PROMPT.md](HARNESS_PROMPT.md) | Prompt for agents consuming the toolbox |
| [SETUP_LLM_HOST.md](SETUP_LLM_HOST.md) | GPU host setup (Qwen3-VL-8B on RX 6600) |

## Requirements

- Docker Engine 24+ with Compose V2
- ~4GB free RAM for containers
- Network access to GPU host running llama.cpp with Qwen3-VL-8B
- No GPU required on the toolbox host
