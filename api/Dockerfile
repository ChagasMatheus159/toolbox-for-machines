FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy everything (source + pyproject.toml)
COPY pyproject.toml .
COPY src/ src/

# Install Python deps (non-editable for production)
RUN pip install --no-cache-dir .

# Create data dir for cache
RUN mkdir -p /data

EXPOSE 9600

CMD ["uvicorn", "toolbox.main:app", "--host", "0.0.0.0", "--port", "9600", "--log-level", "info"]
