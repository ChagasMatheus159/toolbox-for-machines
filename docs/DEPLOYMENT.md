# Toolbox Deployment Guide

## Prerequisites

- Docker Engine 24+ with Compose V2
- Network access to an OpenAI-compatible LLM endpoint (for describe/summarize/extract)
- At least 4GB free RAM for containers (SearXNG + Camoufox + Whisper + API)

## Quick Start

```bash
cd toolbox
cp .env.example .env
# Edit .env — point LLM_URL to your OpenAI-compatible vision model
docker compose up -d
```

Wait ~60 seconds for all services to become healthy, then verify:

```bash
curl http://localhost:9600/healthz
```

Expected: `{"status": "ok", "backends": {...all healthy...}}`

## Configuration

All settings via environment variables in `.env`:

```env
# API port (exposed to LAN)
TOOLBOX_PORT=9600

# Backend URLs (internal Docker network — don't change)
SEARXNG_URL=http://searxng:8080
CAMOUFOX_URL=http://camoufox:8790
WHISPER_URL=http://whisper:8200

# LLM endpoint (any OpenAI-compatible API with vision support)
LLM_URL=http://host.docker.internal:8080/v1
LLM_API_KEY=your-api-key
LLM_MODEL=qwen3-vl-8b
LLM_MAX_CONCURRENT=1        # Serialize LLM requests (limited VRAM)
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=512           # Max output per LLM call

# Fetch
FETCH_TIMEOUT_SECONDS=30

# Cache
CACHE_ENABLED=true
CACHE_DB_PATH=/data/cache.db
```

## Architecture

```
                         ┌─── LAN Consumers ──┐
                         │  Agents / Harnesses │
                         └────────┬────────────┘
                                  │ :9600
                    ┌─────────────┴──────────────┐
                    │   toolbox-api (FastAPI)      │
                    │   ┌──────────────────────┐  │
                    │   │ /v1/search           │──┼──► toolbox-searxng (internal)
                    │   │ /v1/fetch            │──┼──► toolbox-camoufox (internal)
                    │   │ /v1/transcribe       │──┼──► toolbox-whisper (internal)
                    │   │ /v1/describe         │──┼──┐
                    │   │ /v1/summarize        │──┼──┼──► Vision LLM (external)
                    │   │ /v1/extract          │──┼──┘
                    │   └──────────────────────┘  │
                    └─────────────────────────────┘
```

Only port **9600** is exposed. All backend services are on an internal Docker network.

## Containers

| Container | Image | Role | Resources |
|-----------|-------|------|-----------|
| toolbox-api | toolbox-api (custom) | FastAPI service, routes + cache | ~200MB RAM |
| toolbox-searxng | searxng/searxng:latest | Meta-search engine | ~300MB RAM |
| toolbox-camoufox | toolbox-camoufox (custom) | Stealth headless Firefox | ~1.5GB RAM (limited) |
| toolbox-whisper | toolbox-whisper (custom) | Audio transcription (CPU) | ~2GB RAM |

Total RAM: ~4GB. No GPU required on the toolbox host.

## LLM (Separate)

The LLM is **not** part of the Docker stack — it runs wherever you choose (local GPU, cloud API, remote server). See [SETUP_LLM_HOST.md](../SETUP_LLM_HOST.md) for setup options:

- **llama.cpp** — self-hosted with GPU (recommended: Qwen3-VL-8B)
- **Ollama** — easy local setup
- **OpenAI/cloud** — no GPU needed, pay-per-token
- **Any OpenAI-compatible provider** — vLLM, Together AI, Groq, etc.

## Updating

```bash
cd toolbox
docker compose pull searxng   # Update SearXNG image
docker compose build          # Rebuild custom images
docker compose up -d          # Restart with new images
```

## Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f camoufox
```

## Troubleshooting

### SearXNG shows "unhealthy"
- Check logs: `docker compose logs searxng`
- SearXNG listens on port **8080** inside the container (not 8888)
- Engine init errors (403) on startup are normal — they self-resolve

### Camoufox shows "unhealthy"
- Check memory: `docker stats toolbox-camoufox`
- Limited to 1.5GB — increase `mem_limit` in docker-compose.yml if needed
- Restart: `docker compose restart camoufox`

### LLM shows "unreachable"
- Verify your LLM endpoint: `curl $LLM_URL/models`
- Check firewall: LLM port must be accessible from the Docker host
- Check `LLM_URL` and `LLM_API_KEY` in `.env`
- If LLM is on the same machine, use `host.docker.internal` not `localhost`

### Whisper shows "unhealthy"  
- The model takes ~20s to load on startup
- Verify: `docker compose exec whisper python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8200/').status)"`

### Cache issues
- Clear cache: `docker compose exec api python3 -c "import os; os.remove('/data/cache.db')"`
- Disable: set `CACHE_ENABLED=false` in `.env`

## Stopping

```bash
docker compose down           # Stop all containers
docker compose down -v        # Stop and remove volumes (deletes cache)
```
