# Toolbox API Reference

Complete reference for all endpoints exposed at `http://<host>:9600`.

---

## Discovery

### `GET /v1/skills`

Returns machine-readable skill cards for all tools. Use this at agent startup to discover available capabilities.

**Response:** JSON object with `version` and `skills` array containing full input/output schemas, descriptions, and usage guidance for each tool.

---

## Tools

### `POST /v1/search`

Search the web via SearXNG meta-search engine.

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | — | Search query |
| `limit` | integer | — | 10 | Max results (1-50) |
| `categories` | string | — | "general" | Category: general, news, images, science, it |

**Example:**
```bash
curl -X POST http://localhost:9600/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "kubernetes autoscaling 2025", "limit": 5}'
```

**Response:**
```json
{
  "results": [
    {
      "title": "Page Title",
      "url": "https://...",
      "snippet": "Brief description from search engine",
      "engine": "google"
    }
  ],
  "query": "kubernetes autoscaling 2025",
  "count": 5
}
```

**Cache:** 5 minutes TTL.

---

### `POST /v1/fetch`

Fetch a URL using a stealth browser (Camoufox) and extract clean content.

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | ✅ | — | URL to fetch |
| `format` | string | — | "markdown" | Output: "markdown" or "text" |
| `screenshot` | boolean | — | false | Include base64 PNG screenshot |
| `wait_for` | string | — | null | CSS selector to wait for before extracting |
| `wait_ms` | integer | — | 0 | Additional wait time in ms (max 20000) |

**Example:**
```bash
curl -X POST http://localhost:9600/v1/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://blog.rust-lang.org/", "format": "markdown"}'
```

**Response:**
```json
{
  "url": "https://blog.rust-lang.org/",
  "final_url": "https://blog.rust-lang.org/",
  "title": "Rust Blog",
  "content": "# Rust Blog\n\n...",
  "format": "markdown",
  "word_count": 1523,
  "screenshot_b64": null
}
```

**Cache:** 30 minutes TTL. Screenshots bypass cache.

---

### `POST /v1/describe`

Describe an image using the vision model.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image_url` | string | One of these | URL of image to describe |
| `image_b64` | string | required | Base64-encoded image |
| `prompt` | string | — | Custom prompt (default: "Describe this image concisely.") |

**Example (URL):**
```bash
curl -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/screenshot.png", "prompt": "What UI elements are visible?"}'
```

**Example (Base64):**
```bash
curl -X POST http://localhost:9600/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"image_b64": "/9j/4AAQ...", "prompt": "What text is shown?"}'
```

**Response:**
```json
{
  "description": "The image shows a dashboard with three bar charts displaying monthly revenue..."
}
```

**Cache:** 1 hour TTL. Timeout: 60 seconds.

---

### `POST /v1/transcribe`

Transcribe audio to text using whisper.cpp (CPU, medium model).

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio_url` | string | One of these | URL of audio file |
| `audio_b64` | string | required | Base64-encoded audio |
| `mime_type` | string | — | MIME type (default: "audio/wav") |
| `language` | string | — | Language hint, ISO 639-1 (default: "en") |

**Supported formats:** wav, mp3, ogg, webm, m4a, flac

**Example:**
```bash
curl -X POST http://localhost:9600/v1/transcribe \
  -H "Content-Type: application/json" \
  -d '{"audio_url": "https://example.com/clip.mp3", "language": "en"}'
```

**Response:**
```json
{
  "transcript": "Hello and welcome to the show. Today we're discussing...",
  "language": "en"
}
```

**Cache:** None (audio files are unique). Timeout: 120 seconds.

---

### `POST /v1/summarize`

Summarize text using the LLM.

**Request Body:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `text` | string | ✅ | — | Text to summarize |
| `max_tokens` | integer | — | 200 | Max output tokens (20-500) |
| `style` | string | — | "brief" | Style: "brief", "detailed", or "bullets" |

**Example:**
```bash
curl -X POST http://localhost:9600/v1/summarize \
  -H "Content-Type: application/json" \
  -d '{"text": "Long article text here...", "max_tokens": 100, "style": "bullets"}'
```

**Response:**
```json
{
  "summary": "• Key point one\n• Key point two\n• Key point three"
}
```

**Note:** Input is truncated to ~6800 characters (~1700 tokens) to fit within the 2048 context limit. Cache: 1 hour TTL.

---

### `POST /v1/extract`

Extract structured JSON from text using a schema. The LLM is constrained to output valid JSON matching your schema.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | ✅ | Text to extract data from |
| `schema` | object | ✅ | JSON Schema the output must match |

**Example:**
```bash
curl -X POST http://localhost:9600/v1/extract \
  -H "Content-Type: application/json" \
  -d '{
    "text": "John Smith, Senior Engineer at Google, earns $180k. Skills: Go, Python, K8s.",
    "schema": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "company": {"type": "string"},
        "role": {"type": "string"},
        "salary": {"type": "number"},
        "skills": {"type": "array", "items": {"type": "string"}}
      },
      "required": ["name", "company"]
    }
  }'
```

**Response:**
```json
{
  "data": {
    "name": "John Smith",
    "company": "Google",
    "role": "Senior Engineer",
    "salary": 180000,
    "skills": ["Go", "Python", "K8s"]
  }
}
```

**Note:** Input is truncated to ~4800 characters to fit schema + prompt within context. Fields not found in text return `null`. Cache: 1 hour TTL.

---

## Health

### `GET /healthz`

Check the health of the API and all backends.

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

Status is `"ok"` when all backends are healthy, `"degraded"` otherwise.

---

## Error Handling

All endpoints return standard HTTP error codes:

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (missing/invalid fields) |
| 502 | Backend error (LLM timeout, Camoufox failure, etc.) |
| 422 | Validation error (Pydantic) |

Error responses include a `detail` field:
```json
{
  "detail": "Either image_url or image_b64 is required."
}
```

---

## Rate Limits & Timeouts

| Endpoint | Timeout | Concurrency |
|----------|---------|-------------|
| `/v1/search` | 10s | Unlimited |
| `/v1/fetch` | 30s | Unlimited |
| `/v1/describe` | 60s | 1 (LLM semaphore) |
| `/v1/transcribe` | 120s | Unlimited (CPU) |
| `/v1/summarize` | 60s | 1 (LLM semaphore) |
| `/v1/extract` | 60s | 1 (LLM semaphore) |

LLM-backed endpoints (`describe`, `summarize`, `extract`) share a single concurrency slot. If one is running, others queue.
