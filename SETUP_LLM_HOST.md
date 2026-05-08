# Setup Qwen3-VL-8B on llama.cpp (RX 6600 Host)

## Context

- Host: `192.168.3.118`
- GPU: AMD RX 6600 (8GB VRAM)
- Backend: llama.cpp with Vulkan already installed and working
- Current model: Gemma 4 E4B (to be replaced)
- Server currently accessible at: `http://192.168.3.118:8080`
- API key: `dontfuckup!`

## Task

Download Qwen3-VL-8B (Q4_K_M quantization) and configure llama.cpp to serve it with vision support on this host.

## Steps

1. **Download the model GGUF from HuggingFace:**
   ```bash
   # Check if Qwen3-VL-8B GGUF exists. Try these repos in order:
   # - bartowski/Qwen3-VL-8B-Instruct-GGUF
   # - Qwen/Qwen3-VL-8B-Instruct-GGUF  
   # - unsloth/Qwen3-VL-8B-Instruct-GGUF
   #
   # Download the Q4_K_M quantization. File will be ~5GB.
   # If Qwen3-VL doesn't exist yet, fall back to Qwen2.5-VL-7B-Instruct:
   # - bartowski/Qwen2.5-VL-7B-Instruct-GGUF (Q4_K_M)
   
   mkdir -p ~/models
   cd ~/models
   
   # Use huggingface-cli or wget to download the Q4_K_M GGUF file
   # Example: huggingface-cli download bartowski/Qwen2.5-VL-7B-Instruct-GGUF --include "*Q4_K_M*" --local-dir .
   ```

2. **Verify the model fits in VRAM:**
   - Model weights (Q4_K_M): ~4.5-5.5GB
   - Must leave ~1GB free for KV cache + Vulkan scratch
   - Total VRAM usage must stay under 7GB

3. **Configure llama.cpp server for vision:**
   ```bash
   # Key flags for Qwen-VL models:
   llama-server \
     --model ~/models/<model-file>.gguf \
     --host 0.0.0.0 \
     --port 8080 \
     --n-gpu-layers 99 \
     --ctx-size 4096 \
     --api-key "dontfuckup!" \
     --parallel 1 \
     --chat-template chatml \
     --log-disable
   ```
   
   **Important flags:**
   - `--n-gpu-layers 99` — offload all layers to GPU
   - `--ctx-size 4096` — enough for toolbox (requests are ~3K tokens max)
   - `--parallel 1` — single concurrent request (VRAM limited)
   - Vision support should be automatic for VL models in recent llama.cpp

4. **Create a systemd service (or screen/tmux session) so it persists:**
   ```bash
   # Option A: systemd
   sudo tee /etc/systemd/system/llama-server.service << 'EOF'
   [Unit]
   Description=llama.cpp server (Qwen3-VL-8B)
   After=network.target
   
   [Service]
   Type=simple
   User=<your-user>
   WorkingDirectory=/home/<your-user>
   ExecStart=/usr/local/bin/llama-server --model /home/<your-user>/models/<model-file>.gguf --host 0.0.0.0 --port 8080 --n-gpu-layers 99 --ctx-size 4096 --api-key "dontfuckup!" --parallel 1
   Restart=on-failure
   RestartSec=5
   
   [Install]
   WantedBy=multi-user.target
   EOF
   
   sudo systemctl daemon-reload
   sudo systemctl enable --now llama-server
   ```

5. **Test the setup:**
   ```bash
   # Text completion
   curl http://192.168.3.118:8080/v1/chat/completions \
     -H "Authorization: Bearer dontfuckup!" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3-vl-8b",
       "messages": [{"role": "user", "content": "Say hello in one word."}],
       "max_tokens": 10
     }'
   
   # Vision test (base64 image)
   # Generate a small test image as base64, send with image_url content type
   curl http://192.168.3.118:8080/v1/chat/completions \
     -H "Authorization: Bearer dontfuckup!" \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen3-vl-8b",
       "messages": [{"role": "user", "content": [
         {"type": "text", "text": "What do you see?"},
         {"type": "image_url", "image_url": {"url": "data:image/png;base64,<small-test-image-b64>"}}
       ]}],
       "max_tokens": 100
     }'
   ```

6. **Verify VRAM usage:**
   ```bash
   # Check actual GPU memory usage
   # For AMD: 
   cat /sys/class/drm/card0/device/mem_info_vram_used
   # or
   radeontop -d -
   # Should show < 7GB used
   ```

## Success Criteria

- `curl http://192.168.3.118:8080/v1/models` returns model info
- Text chat completions work
- Vision (image input) chat completions work
- VRAM usage < 7GB (1GB free buffer)
- Server auto-restarts on crash (systemd)

## Fallback

If Qwen3-VL-8B GGUF is not yet available on HuggingFace, use **Qwen2.5-VL-7B-Instruct** (Q4_K_M) instead. Same setup, same flags. It's proven and widely available as GGUF.
