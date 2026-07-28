import asyncio
import time
from typing import Optional, AsyncGenerator, Dict, Any

from loguru import logger

from core.runtime.resource_manager import ResourceManager
from app.rag.pipeline import RAGPipeline
from app.agents.graph import LegalAgentGraph
from app.models.schemas import (
    QueryResponse,
    QueryRequest,
    RegulatoryAnalysis,
    LegalCitation,
    RiskMatrix,
    IncentiveInfo,
)
from app.services.sse_manager import SSEStreamManager
from app.services.cache import (
    init_redis,
    close_redis,
    get_cached,
    set_cached,
)
from app.config import settings


class QueryService:
    def __init__(self, rm: ResourceManager) -> None:
        self.rm = rm
        self.pipeline: Optional[RAGPipeline] = None
        self.agent: Optional[LegalAgentGraph] = None
        self.redis_enabled = False

    async def initialize(self) -> None:
        t = time.perf_counter()

        await asyncio.gather(
            self._init_pipeline(),
            self._init_agent(),
            self._init_redis(),
        )

        logger.info(f"QueryService initialized in {time.perf_counter() - t:.2f}s")

    async def _init_pipeline(self) -> None:
        t = time.perf_counter()
        self.pipeline = RAGPipeline(qdrant=self.rm.qdrant())
        await asyncio.wait_for(self.pipeline.initialize(), timeout=180)
        logger.info(f"RAGPipeline initialized in {time.perf_counter() - t:.2f}s")

    async def _init_agent(self) -> None:
        t = time.perf_counter()
        self.agent = LegalAgentGraph()
        await asyncio.wait_for(self.agent.initialize(), timeout=120)
        logger.info(f"LegalAgentGraph initialized in {time.perf_counter() - t:.2f}s")

    async def _init_redis(self) -> None:
        try:
            await asyncio.wait_for(
                init_redis(host=settings.redis_host, port=settings.redis_port),
                timeout=15,
            )
            self.redis_enabled = True
            logger.info("Redis connected")
        except Exception:
            logger.warning("Redis unavailable — cache disabled")

    async def close(self) -> None:
        if self.pipeline:
            try:
                await self.pipeline.close()
            except Exception:
                logger.exception("Error closing pipeline")
        if self.redis_enabled:
            try:
                await close_redis()
            except Exception:
                logger.exception("Error closing Redis")
        logger.info("QueryService closed")

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        import time
        start_time = time.perf_counter()
        
        cache_key = self._get_cache_key(request)
        
        if self.redis_enabled:
            try:
                cached = await get_cached(cache_key)
                if cached:
                    logger.info(f"✅ Cache hit para: {request.question[:50]}...")
                    return QueryResponse(**cached)
            except Exception as e:
                logger.warning(f"Error al leer caché: {e}")
        
        logger.info(f"📝 Procesando query: {request.question[:50]}...")
        
        try:
            if getattr(request, 'use_agent', False):
                response = await self.agent.run(request)
            else:
                response = await self.pipeline.query(request)
            
            if self.redis_enabled:
                try:
                    await set_cached(
                        cache_key,
                        response.dict() if hasattr(response, 'dict') else response,
                        ttl=3600
                    )
                except Exception as e:
                    logger.warning(f"Error al guardar en caché: {e}")
            
            processing_time = int((time.perf_counter() - start_time) * 1000)
            if hasattr(response, 'processing_time_ms'):
                response.processing_time_ms = processing_time
            
            logger.info(f"✅ Query completada en {processing_time}ms")
            return response
            
        except Exception as e:
            logger.exception(f"❌ Error procesando query: {e}")
            raise

    async def process_query_streaming(self, request: QueryRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """Procesa una consulta legal con streaming"""
        logger.info(f"📝 Streaming query: {request.question[:50]}...")
        
        # Usar el pipeline directamente
        async for event in self.pipeline.query_stream(request):
            yield event

    def _get_cache_key(self, request: QueryRequest) -> str:
        import hashlib
        import json
        
        content = request.question + json.dumps(getattr(request, 'metadata_filter', {}))
        return f"query:{hashlib.sha256(content.encode()).hexdigest()}"
