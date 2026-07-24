FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (psycopg2 needs libpq, yfinance may need ca-certificates)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency list first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port (defaults to 8000, overridden by $PORT on Render)
EXPOSE 8000

# ── Startup ──────────────────────────────────────────────────────────────
# Shell form so $PORT is expanded at runtime (Render injects this env var).
# Falls back to 8000 for local Docker runs where $PORT might not be set.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
