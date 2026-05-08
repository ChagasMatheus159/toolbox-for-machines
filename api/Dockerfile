FROM python:3.12-slim

WORKDIR /app

# System deps for crawl4ai and general use
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ src/

# Create data dir for cache
RUN mkdir -p /data

EXPOSE 9600

CMD ["uvicorn", "toolbox.main:app", "--host", "0.0.0.0", "--port", "9600", "--log-level", "info"]
