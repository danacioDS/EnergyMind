import json
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.config import settings
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
async def query_legal(request: QueryRequest, fastapi_request: Request, service: QueryService = Depends(get_query_service)):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
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
async def health(fastapi_request: Request):
    cid = getattr(fastapi_request.state, "correlation_id", None)
    with logger.contextualize(correlation_id=cid or "--------"):
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
            from ingestion.pipeline import CORPUS_DEFINITIONS
            import json
            corpus_path = settings.corpus_normalized_path / "all_units.json"
            if not corpus_path.exists():
                return {"status": "no_corpus", "detail": "Run ingestion first"}

            with open(corpus_path) as f:
                units = json.load(f)

            from collections import Counter
            type_counts = Counter(u["tipo_norma"] for u in units)
            subsector_counts = Counter(u.get("subsector", "Unknown") for u in units)
            incentive_count = sum(1 for u in units if u.get("renewable_incentive", False))
            flags = Counter()
            for u in units:
                for flag in u.get("risk_flags", []):
                    flags[flag] += 1

            return {
                "status": "ok",
                "total_documents": len(units),
                "by_norm_type": dict(type_counts),
                "by_subsector": dict(subsector_counts),
                "renewable_incentive_docs": incentive_count,
                "risk_flags": dict(flags.most_common()),
                "sources_configured": len(CORPUS_DEFINITIONS),
            }
        except Exception as e:
            logger.error(f"Corpus stats failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/query/stream",
    summary="Stream query results via SSE",
    description="Ask a legal question and receive progressive updates: retrieval status → analysis tokens → final result",
)
async def query_legal_stream(request: QueryRequest, fastapi_request: Request, service: QueryService = Depends(get_query_service)):
    cid = getattr(fastapi_request.state, "correlation_id", None)

    async def event_stream():
        with logger.contextualize(correlation_id=cid or "--------"):
            yield f"data: {json.dumps({'event': 'start', 'correlation_id': cid})}\n\n"
            try:
                yield f"data: {json.dumps({'event': 'retrieval', 'status': 'querying'})}\n\n"
                response = await service.process_query(request)
                yield f"data: {json.dumps({'event': 'analysis', 'direct_conclusion': response.answer.direct_conclusion[:500]})}\n\n"
                yield f"data: {json.dumps({'event': 'risk', 'matrix': response.answer.risk_matrix.model_dump()})}\n\n"
                yield f"data: {json.dumps({'event': 'incentives', 'detected': response.answer.incentives_detected.model_dump()})}\n\n"
                yield f"data: {json.dumps({'event': 'complete', 'processing_time_ms': response.processing_time_ms, 'sources': response.sources})}\n\n"
            except ValueError as e:
                logger.error(f"Streaming query failed (retrieval stage): {e}")
                error_detail = str(e)
                stage_hint = "retrieval" if any(kw in error_detail.lower() for kw in ["bm25", "dense", "rerank", "qdrant", "retrieval", "no documents", "empty"]) else "processing"
                yield f"data: {json.dumps({'event': 'error', 'detail': error_detail, 'stage': stage_hint})}\n\n"
            except Exception as e:
                logger.error(f"Streaming query failed: {e}")
                yield f"data: {json.dumps({'event': 'error', 'detail': str(e), 'stage': 'unknown'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "X-Correlation-ID": cid or "",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
