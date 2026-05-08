# Toolbox Deployment Guide

## Prerequisites

- Docker Engine 24+ with Compose V2
- Network access to the GPU host (192.168.3.118:8080) running Qwen3-VL-8B
- At least 4GB free RAM for containers (SearXNG + Camoufox + Whisper + API)

## Quick Start

```bash
cd toolbox
cp .env.example .env
# Edit .env if your LLM host is different from 192.168.3.118
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

# LLM host (your GPU machine on LAN)
LLM_URL=http://192.168.3.118:8080/v1
LLM_API_KEY=dontfuckup!
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
                    │   │ /v1/summarize        │──┼──┼──► Qwen3-VL-8B (LAN :8080)
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

Total RAM: ~4GB. No GPU required on this host.

## GPU Host (Separate Machine)

The LLM runs on a separate machine with an AMD RX 6600 (8GB VRAM):

- **Model:** Qwen3-VL-8B-Instruct Q4_K_M
- **Server:** llama.cpp with `--ctx-size 2048 --parallel 1`
- **Port:** 8080 (OpenAI-compatible API)
- **Setup guide:** [SETUP_LLM_HOST.md](../SETUP_LLM_HOST.md)

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
- Verify GPU host: `curl http://192.168.3.118:8080/v1/models`
- Check firewall: port 8080 must be open between hosts
- Check `LLM_URL` and `LLM_API_KEY` in `.env`

### Whisper shows "unhealthy"  
- The medium model takes ~20s to load on startup
- Verify: `docker compose exec whisper python3 -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8200/').status)"`

### Cache issues
- Clear cache: `docker compose exec api python3 -c "import os; os.remove('/data/cache.db')"`
- Disable: set `CACHE_ENABLED=false` in `.env`

## Stopping

```bash
docker compose down           # Stop all containers
docker compose down -v        # Stop and remove volumes (deletes cache)
```
