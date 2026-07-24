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

# Expose the port Render provides via $PORT
EXPOSE 8000

# ── Startup ──────────────────────────────────────────────────────────────
# uvicorn serves the FastAPI app (single worker, enough for MVP).
# The background scheduler (APScheduler) runs in the same process via
# the FastAPI lifespan hook — no Celery needed.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
