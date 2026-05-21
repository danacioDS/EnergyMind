from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger

from app.models.schemas import QueryRequest, QueryResponse
from app.services.query_service import QueryService


router = APIRouter(prefix="/api/v1", tags=["Legal RAG"])


async def get_query_service() -> QueryService:
    from app.main import query_service
    if not query_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return query_service


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the Legal RAG system",
    description="Ask a legal question about renewable energy investments in Bolivia",
)
async def query_legal(request: QueryRequest, service: QueryService = Depends(get_query_service)):
    try:
        response = await service.process_query(request)
        return response
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/health",
    summary="Health check endpoint",
)
async def health():
    return {
        "status": "healthy",
        "service": "LexEnergy Bolivia",
        "version": "1.0.0",
    }


@router.post(
    "/ingest",
    summary="Trigger document ingestion",
    description="Run the ingestion pipeline to process and index legal documents",
)
async def trigger_ingestion():
    try:
        from ingestion.pipeline import run_ingestion
        count = await run_ingestion()
        return {"status": "success", "documents_indexed": count}
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
