FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 🔥 1. SOLO requirements primero (cache layer importante)
COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# =========================
# RUNTIME IMAGE
# =========================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 🔥 2. copiar dependencias instaladas
COPY --from=builder /install /usr/local

# 🔥 3. copiar código AL FINAL (esto es clave)
COPY . .

RUN mkdir -p \
    /app/corpus/raw \
    /app/corpus/processed \
    /app/corpus/normalized \
    /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
