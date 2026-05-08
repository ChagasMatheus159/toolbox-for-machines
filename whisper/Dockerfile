FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the medium model into /app/models/
RUN bash /app/models/download-ggml-model.sh medium

EXPOSE 8200

# Override the base image's ENTRYPOINT which is ["bash", "-c"]
ENTRYPOINT []
CMD ["/app/build/bin/whisper-server", "--model", "/app/models/ggml-medium.bin", "--host", "0.0.0.0", "--port", "8200"]
