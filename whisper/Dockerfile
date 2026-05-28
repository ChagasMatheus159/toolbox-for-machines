FROM ghcr.io/ggerganov/whisper.cpp:main

# Download the small model — best speed/accuracy tradeoff for CPU
RUN bash /app/models/download-ggml-model.sh small

EXPOSE 8200

# Override the base image's ENTRYPOINT which is ["bash", "-c"]
ENTRYPOINT []

# Default to nproc/2 threads (sweet spot per benchmarks, minimum 2). Override with WHISPER_THREADS env.
CMD ["sh", "-c", "THREADS=${WHISPER_THREADS:-$(( $(nproc) / 2 ))}; [ $THREADS -lt 2 ] && THREADS=2; exec /app/build/bin/whisper-server --model /app/models/ggml-small.bin --host 0.0.0.0 --port 8200 --threads $THREADS"]
