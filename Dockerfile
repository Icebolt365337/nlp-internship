FROM python:3.12-slim
 
WORKDIR /app
 
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
 

COPY requirements.txt .

# Install CPU-only torch first
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install the rest, telling pip to prioritize the CPU wheel index for torch dependencies
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu
 
RUN pip install --no-cache-dir -r requirements.txt
 
RUN python -c "import nltk; nltk.download('punkt_tab')" || true
 
COPY . .
 
EXPOSE 8000
 
ENV REDIS_URL=""


CMD ["streamlit", "run", "app.py", "--server.port", "8000", "--server.address", "0.0.0.0", "--server.headless", "true"]