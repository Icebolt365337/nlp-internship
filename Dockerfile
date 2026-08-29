# Real Estate NLP API - Docker deployment
FROM python:3.12-slim

WORKDIR /app

# System deps some NLP packages need to build wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-fetch nltk's sentence tokenizer data at build time so it's not
# fetched on first request in production (falls back to a regex
# tokenizer automatically if this fails, e.g. no network at build time).
RUN python -c "import nltk; nltk.download('punkt_tab')" || true

COPY . .

EXPOSE 8000

# REDIS_URL can be set at runtime (e.g. `-e REDIS_URL=redis://redis:6379/0`
# in docker-compose) to use Redis for response caching instead of the
# in-memory fallback.
ENV REDIS_URL=""

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]