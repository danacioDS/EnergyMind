# LexEnergy Bolivia — Run Transcript

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (recommended) OR Qdrant installed natively
- Ollama (for local LLM) OR an OpenAI API key

---

## 1. Setup environment

```bash
cd lexenergy
cp .env.example .env
```

Edit `.env` if needed (defaults work with local Ollama + Qdrant).

---

## 2. Start infrastructure (Qdrant vector DB)

### Option A: Docker (recommended)

```bash
docker compose -f docker/docker-compose.yml up -d qdrant
```

### Option B: Native Qdrant

```bash
# Install Qdrant: https://qdrant.tech/documentation/quick-start/
qdrant
```

---

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Set up the LLM

### Option A: Ollama (local, free)

```bash
# Install Ollama: https://ollama.com
ollama pull llama3.1
```

This matches `LLM_MODEL=llama3.1` and `LLM_PROVIDER=ollama` in `.env`.

### Option B: OpenAI (cloud)

Edit `.env`:
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o
```

---

## 5. Ingest the legal corpus

This parses all files in `corpus/raw/`, creates legal units (one per article), generates embeddings with BAAI/bge-m3, and indexes them into Qdrant.

```bash
python3 -c "
import asyncio
from ingestion.pipeline import run_ingestion
asyncio.run(run_ingestion())
"
```

Expected output:
```
INFO  | Starting ingestion pipeline
INFO  | Parsing file: corpus/raw/constitucion_bolivia_articulos_seleccionados.txt
INFO  | Parsing file: corpus/raw/ley_1604_1994.txt
INFO  | Parsing file: corpus/raw/ley_943_modificaciones.txt
INFO  | Parsing file: corpus/raw/ds_5503_2025.txt
INFO  | Parsing file: corpus/raw/aetn_resoluciones_muestra.txt
INFO  | Created collection: lexenergy_bolivia
INFO  | Upserted N points to Qdrant
INFO  | Ingestion pipeline complete: N units indexed
```

---

## 6. Start the API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or for production:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Open http://localhost:8000/docs for interactive Swagger docs.

---

## 7. Query the system

### Via curl

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Can a foreign company build a solar plant in Bolivia?",
    "subsector": "Solar"
  }'
```

### Via Python

```python
import httpx

response = httpx.post(
    "http://localhost:8000/api/v1/query",
    json={
        "question": "What incentives exist for distributed solar generation?",
        "subsector": "Solar"
    }
)
print(response.json())
```

### Example queries to try

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What incentives exist for biomass energy projects?"}'

curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Is arbitration available for foreign investors in the electricity sector?"}'

curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the constitution say about energy as a strategic sector?"}'

curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Can I self-produce solar energy and sell excess to the grid?"}'
```

---

## 8. Health check

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "LexEnergy Bolivia",
  "version": "1.0.0"
}
```

---

## 9. Re-ingest (after modifying corpus)

```bash
curl -X POST http://localhost:8000/api/v1/ingest
```

---

## 10. Full Docker stack (everything in containers)

Skip steps 2-6. Just run:

```bash
docker compose -f docker/docker-compose.yml up -d --build
# Then pull the model inside the container:
docker exec -it lexenergy-ollama-1 ollama pull llama3.1
# Then ingest:
docker exec -it lexenergy-lexenergy-api-1 python3 -c "
import asyncio
from ingestion.pipeline import run_ingestion
asyncio.run(run_ingestion())
"
```

---

## 11. Run tests

```bash
pytest tests/ -v
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Connection refused` on Qdrant | Ensure Qdrant is running: `docker ps` or `systemctl status qdrant` |
| Ollama model not found | Run `ollama pull llama3.1` |
| Ingestion finds no files | Check `corpus/raw/` exists and contains `.txt` files |
| Slow first query | BAAI/bge-m3 model downloads on first use (~2.4GB) |
| API won't start | Check port 8000 is free: `lsof -i :8000` |
