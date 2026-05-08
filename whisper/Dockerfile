FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the medium model (the script puts it in /app/models/)
RUN bash /app/models/download-ggml-model.sh medium

EXPOSE 8200

CMD ["/app/build/bin/whisper-server", \
     "--model", "/app/models/ggml-medium.bin", \
     "--host", "0.0.0.0", \
     "--port", "8200"]
