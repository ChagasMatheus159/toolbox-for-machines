FROM python:3.12-slim

WORKDIR /app

# System deps for Camoufox (headless Firefox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    xvfb \
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8790

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8790", "--log-level", "info"]
