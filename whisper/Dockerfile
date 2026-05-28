FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the small model — best speed/accuracy tradeoff for CPU
RUN bash /app/models/download-ggml-model.sh small

EXPOSE 8200

# Override the base image's ENTRYPOINT which is ["bash", "-c"]
ENTRYPOINT []

# Default to all available cores. Override with WHISPER_THREADS env.
CMD ["sh", "-c", "exec /app/build/bin/whisper-server --model /app/models/ggml-small.bin --host 0.0.0.0 --port 8200 --threads ${WHISPER_THREADS:-$(nproc)}"]
