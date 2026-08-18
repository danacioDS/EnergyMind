from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.models.schemas import QueryRequest, QueryResponse
from app.services.query_service import QueryService
from app.services.sse_manager import SSEStreamManager


router = APIRouter(prefix="/api/v1", tags=["Legal RAG"])


def get_query_service(request: Request) -> QueryService:
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service warming up — retry in a few seconds")
    svc = getattr(request.app.state, "query_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return svc


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the Legal RAG system",
    description="Ask a legal question about renewable energy investments in Bolivia",
)
async def query_legal(request: QueryRequest, fastapi_request: Request, service: QueryService = Depends(get_query_service)):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
        try:
            response = await service.process_query(request)
            return response
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/query/stream",
    summary="Stream query results via SSE",
    description="Ask a legal question and receive progressive updates: retrieval → analysis → risk → incentives → complete",
)
async def query_legal_stream(request: QueryRequest, fastapi_request: Request, service: QueryService = Depends(get_query_service)):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
        try:
            # Obtener el generador asíncrono del pipeline
            stream_gen = service.process_query_streaming(request)
            
            # Crear el SSE stream manager
            sse_manager = SSEStreamManager(correlation_id=cid or "--------")
            
            # ✅ CORREGIDO: Pasar el generador y el manager al streaming response
            return StreamingResponse(
                sse_manager.stream_generator(stream_gen),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        except Exception as e:
            logger.error(f"Stream query failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    summary="Liveness check",
)
async def health():
    return {"status": "alive"}


@router.get(
    "/health/ready",
    summary="Readiness check",
)
async def readiness(request: Request):
    if not getattr(request.app.state, "ready", False):
        raise HTTPException(status_code=503, detail="Service warming up")
    return {"status": "ready"}


@router.post(
    "/ingest",
    summary="Trigger document ingestion",
    description="Run the ingestion pipeline to process and index legal documents",
)
async def trigger_ingestion(fastapi_request: Request):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
        try:
            from ingestion.pipeline import run_ingestion, CORPUS_DEFINITIONS
            count = await run_ingestion()
            return {"status": "success", "documents_indexed": count}
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/corpus/stats",
    summary="Corpus statistics",
    description="Returns document counts, norm type distribution, and coverage info",
)
async def corpus_stats(fastapi_request: Request):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
        try:
            from app.config import settings
            import json
            
            corpus_path = settings.corpus_normalized_path / "all_units.json"
            if not corpus_path.exists():
                return {
                    "total_units": 0,
                    "documents": {},
                    "error": "Corpus file not found"
                }
            
            with open(corpus_path) as f:
                units = json.load(f)
            
            return {
                "total_units": len(units),
                "documents": {}
            }
        except Exception as e:
            logger.error(f"Corpus stats failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
