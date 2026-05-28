FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# SOLO requirements
COPY requirements.txt .

# 🔥 cache pip (MUY importante en WSL)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt


# =========================
# RUNTIME
# =========================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

COPY . .

RUN mkdir -p \
    /app/corpus/raw \
    /app/corpus/processed \
    /app/corpus/normalized \
    /app/logs

EXPOSE 8000

# ❌ QUITAR reload en docker
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
