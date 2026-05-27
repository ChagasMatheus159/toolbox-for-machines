# LLM Setup Guide

Toolbox requires an OpenAI-compatible LLM endpoint for three tools: **describe**, **summarize**, and **extract**. The other three tools (search, fetch, transcribe) work without an LLM.

## Requirements

Your LLM must support:
1. **OpenAI-compatible chat completions API** (`POST /v1/chat/completions`)
2. **Vision/multimodal input** — images as base64 in message content (for `/v1/describe`)
3. **JSON response format** — `response_format: {"type": "json_object"}` (for `/v1/extract`)

## Critical Parameters

These settings matter for toolbox to work correctly:

| Parameter | Value | Why |
|-----------|-------|-----|
| Vision projector | Required (mmproj) | `/v1/describe` sends images as base64 data URLs. Without the vision projector loaded, the model cannot process images. |
| Context size | ≥2048 tokens | Toolbox truncates all inputs to fit within 2048. Larger contexts work but waste memory. |
| Chat template | `chatml` (for Qwen) | Must match the model's expected format. Wrong template = garbage output. |
| JSON mode | Supported | `/v1/extract` sends `response_format: {"type": "json_object"}`. The server must support this or extraction will fail. llama.cpp, vLLM, and OpenAI all support it. Ollama supports it for some models. |
| Temperature | Controlled by toolbox | Toolbox sends `temperature: 0.1` on every request. Don't set a server-side override higher than this. |
| Parallel slots | 1 recommended | Toolbox serializes LLM requests with a semaphore (`LLM_MAX_CONCURRENT=1`). Multiple slots waste VRAM. If you have excess VRAM, increase both `--parallel` on the server AND `LLM_MAX_CONCURRENT` in toolbox .env. |

> **No thinking mode.** Toolbox prompts are rigid one-shot instructions ("describe this image", "extract this JSON"). Do NOT enable chain-of-thought, reasoning tokens, or thinking modes — they waste tokens and break output parsing.

## Recommended Models

Any vision-capable model works. Tested options:

| Model | Size | Vision | Notes |
|-------|------|--------|-------|
| **Qwen3-VL-8B-Instruct** | ~5GB (Q4_K_M) | ✅ | Primary tested model. Best balance of quality/speed for self-hosted |
| Qwen2.5-VL-7B-Instruct | ~5GB (Q4) | ✅ | Older but stable |
| GPT-4o-mini | Cloud | ✅ | Easiest setup, pay-per-token |
| GPT-4o | Cloud | ✅ | Highest quality |

> **Vision is required** for `/v1/describe`. If you only need summarize and extract (no image/screenshot description), any text-only model works — but you'll get 502 errors on describe calls.

## Tested Setup (Reference)

This is the exact configuration toolbox was developed and tested against:

```
Model:           Qwen3-VL-8B-Instruct-Q4_K_M.gguf
Vision module:   mmproj-qwen3-vl-8b-f16.gguf
Server:          llama.cpp (built with Vulkan)
Context size:    2048 tokens
Parallel slots:  1
Chat template:   chatml
GPU offload:     full (auto)
Flash attention: auto
Temperature:     0.1 (set by toolbox, not the server)
```

The toolbox sends requests with `temperature: 0.1` for deterministic output. No thinking/reasoning mode is used — the prompts are rigid and expect direct answers.

Context window of 2048 is enough because toolbox truncates inputs:
- summarize: ~6800 chars (~1700 tokens) + system prompt + output
- extract: ~4800 chars (~1200 tokens) + schema + system prompt + output
- describe: image + short prompt + output

### systemd service (for reference)

```ini
[Unit]
Description=llama.cpp Server
After=network.target

[Service]
Type=simple
ExecStart=/path/to/llama-server \
    -m /path/to/Qwen3-VL-8B-Instruct-Q4_K_M.gguf \
    --mmproj /path/to/mmproj-qwen3-vl-8b-f16.gguf \
    -ngl auto \
    -c 2048 \
    -fa auto \
    --host 0.0.0.0 \
    --port 8080 \
    --parallel 1 \
    --chat-template chatml \
    --api-key "your-secret-key"
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

## Option A: llama.cpp (Self-Hosted, GPU)

Best for: dedicated GPU machine (6GB+ VRAM).

```bash
# 1. Download the model GGUFs
mkdir -p ~/models && cd ~/models
# Qwen3-VL-8B Q4_K_M (~5GB)
huggingface-cli download Qwen/Qwen3-VL-8B-Instruct-GGUF \
  --include "*Q4_K_M*" --local-dir .
# Vision projector (required for multimodal)
huggingface-cli download Qwen/Qwen3-VL-8B-Instruct-GGUF \
  --include "*mmproj*f16*" --local-dir .

# 2. Start the server
llama-server \
  --model ~/models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf \
  --mmproj ~/models/mmproj-qwen3-vl-8b-f16.gguf \
  --host 0.0.0.0 --port 8080 \
  -ngl auto \
  -c 2048 \
  -fa auto \
  --parallel 1 \
  --chat-template chatml \
  --api-key "your-secret-key"

# 3. Configure Toolbox .env
# LLM_URL=http://<llm-host-ip>:8080/v1
# LLM_API_KEY=your-secret-key
# LLM_MODEL=qwen3-vl-8b
```

### Running as a systemd service

```bash
sudo tee /etc/systemd/system/llama-server.service << 'EOF'
[Unit]
Description=llama.cpp server
After=network.target

[Service]
Type=simple
ExecStart=/path/to/llama-server \
  --model /path/to/Qwen3-VL-8B-Instruct-Q4_K_M.gguf \
  --mmproj /path/to/mmproj-qwen3-vl-8b-f16.gguf \
  -ngl auto \
  -c 2048 \
  -fa auto \
  --host 0.0.0.0 --port 8080 \
  --parallel 1 \
  --chat-template chatml \
  --api-key "your-secret-key"
Restart=on-failure
RestartSec=10
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now llama-server
```

## Option B: Ollama (Self-Hosted, Easy)

Best for: quick local setup, less configuration.

```bash
# 1. Install Ollama (https://ollama.ai)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a vision model
ollama pull qwen2.5vl:7b

# 3. Ollama exposes an OpenAI-compatible API at :11434
# Configure Toolbox .env:
# LLM_URL=http://localhost:11434/v1
# LLM_API_KEY=ollama
# LLM_MODEL=qwen2.5vl:7b
```

> **Note:** Ollama must be accessible from inside Docker. If Toolbox runs on the same machine, use `http://host.docker.internal:11434/v1` as `LLM_URL`.

## Option C: OpenAI API (Cloud)

Best for: no GPU, minimal setup, willing to pay per token.

```bash
# Configure Toolbox .env:
# LLM_URL=https://api.openai.com/v1
# LLM_API_KEY=sk-your-openai-key
# LLM_MODEL=gpt-4o-mini
```

> **Note:** Works great but costs money per request. `gpt-4o-mini` is cheapest with vision support.

## Option D: Any OpenAI-Compatible Provider

Any service exposing `/v1/chat/completions` with vision support works:
- **vLLM** — `LLM_URL=http://host:8000/v1`
- **Together AI** — `LLM_URL=https://api.together.xyz/v1`
- **Groq** — `LLM_URL=https://api.groq.com/openai/v1`
- **Local AI** — `LLM_URL=http://localhost:8080/v1`

## Verify Your Setup

```bash
# Test text completion
curl $LLM_URL/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-model-name",
    "messages": [{"role": "user", "content": "Say hello in one word."}],
    "max_tokens": 10
  }'

# Test vision (must work for /v1/describe)
curl $LLM_URL/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "your-model-name",
    "messages": [{"role": "user", "content": [
      {"type": "text", "text": "What colors do you see?"},
      {"type": "image_url", "image_url": {"url": "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_272x92dp.png"}}
    ]}],
    "max_tokens": 50
  }'
```

Both should return valid JSON responses. Then start Toolbox and check:
```bash
curl http://localhost:9600/healthz
# backends.llm should be "healthy"
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_URL` | `http://host.docker.internal:8080/v1` | Base URL of OpenAI-compatible API |
| `LLM_API_KEY` | *(empty)* | API key (set to anything if not needed) |
| `LLM_MODEL` | `qwen3-vl-8b` | Model name to pass in requests |
| `LLM_MAX_CONCURRENT` | `1` | Max parallel LLM requests (keep at 1 for single-GPU) |
| `LLM_TIMEOUT_SECONDS` | `60` | Request timeout |
| `LLM_MAX_TOKENS` | `512` | Default max output tokens |

## Troubleshooting

- **`healthz` shows llm "unreachable"** — Check that `LLM_URL` is accessible from inside the Docker container. Use `host.docker.internal` instead of `localhost` if LLM runs on the same machine.
- **`/v1/describe` fails but summarize/extract work** — Your model doesn't support vision input. Switch to a VL/multimodal model.
- **`/v1/extract` returns malformed JSON** — Your model/server doesn't support `response_format`. Update llama.cpp or use a model that supports JSON mode.
- **Timeouts** — Increase `LLM_TIMEOUT_SECONDS` or use a faster model/GPU.
- **Qwen3 outputs `<think>` tags** — You're running the model in thinking/reasoning mode. Either use the non-thinking variant or pass `--override-kv tokenizer.chat_template.default=str:chatml` to suppress it. Toolbox does NOT handle think tokens in responses.
- **Describe works but output is poor quality** — Check that the mmproj (vision projector) file matches your model version. A Qwen2.5 mmproj won't work correctly with a Qwen3 model.
