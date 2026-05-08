FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the medium model
RUN mkdir -p /models && \
    /app/models/download-ggml-model.sh medium /models

EXPOSE 8200

CMD ["/app/server", \
     "--model", "/models/ggml-medium.bin", \
     "--host", "0.0.0.0", \
     "--port", "8200", \
     "--print-realtime", "false"]
