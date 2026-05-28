FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the small model — best speed/accuracy tradeoff for CPU
# (medium is ~2.5x realtime on Ryzen 5 3600; small is ~0.5x realtime)
RUN bash /app/models/download-ggml-model.sh small

EXPOSE 8200

# Override the base image's ENTRYPOINT which is ["bash", "-c"]
ENTRYPOINT []
CMD ["/app/build/bin/whisper-server", "--model", "/app/models/ggml-small.bin", "--host", "0.0.0.0", "--port", "8200", "--threads", "4"]
