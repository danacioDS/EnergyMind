import time
from typing import Optional, AsyncGenerator
from loguru import logger

from app.rag.pipeline import RAGPipeline
from app.agents.graph import LegalAgentGraph
from app.models.schemas import (
    QueryResponse, QueryRequest, RegulatoryAnalysis, LegalCitation, RiskMatrix, IncentiveInfo,
)
from app.services.sse_manager import SSEStreamManager
from app.services.cache import init_redis, close_redis, get_cached, set_cached
from app.config import settings


class QueryService:
    def __init__(self):
        self.pipeline: Optional[RAGPipeline] = None
        self.agent: Optional[LegalAgentGraph] = None

    async def initialize(self):
        self.pipeline = RAGPipeline()
        await self.pipeline.initialize()
        self.agent = LegalAgentGraph()
        await self.agent.initialize()
        try:
            await init_redis(host=settings.redis_host, port=settings.redis_port)
            logger.info("Redis cache initialized")
        except Exception as e:
            logger.warning(f"Redis not available, cache disabled: {e}")
        logger.info("QueryService initialized (pipeline + agent)")

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        if not self.pipeline or not self.agent:
            raise RuntimeError("QueryService not initialized")

        cached = await get_cached(request.question, request.subsector)
        if cached is not None:
            logger.info(f"Cache HIT for: {request.question[:60]}...")
            response = QueryResponse(**cached)
            response.cached = True
            return response

        if request.use_agent:
            response = await self._process_with_agent(request)
        else:
            response = await self._process_with_pipeline(request)

        try:
            await set_cached(
                request.question, request.subsector,
                response.model_dump(),
            )
        except Exception as e:
            logger.debug(f"Cache set failed: {e}")

        return response

    async def process_query_streaming(
        self, request: QueryRequest, stream: SSEStreamManager,
    ) -> AsyncGenerator[str, None]:
        if not self.pipeline or not self.agent:
            raise RuntimeError("QueryService not initialized")

        try:
            cached = await get_cached(request.question, request.subsector)
            if cached is not None:
                resp = QueryResponse(**cached)
                yield stream.emit("analysis", {"direct_conclusion": resp.answer.direct_conclusion[:500]})
                yield stream.emit("risk", {"matrix": resp.answer.risk_matrix.model_dump()})
                yield stream.emit("incentives", {"detected": resp.answer.incentives_detected.model_dump()})
                yield stream.emit("complete", {"processing_time_ms": 0, "sources": resp.sources, "cached": True})
                return

            metadata_filter = {}
            if request.subsector:
                metadata_filter["subsector"] = request.subsector
            if request.tipo_norma:
                metadata_filter["tipo_norma"] = request.tipo_norma
            if request.vigente is not None:
                metadata_filter["vigente"] = request.vigente

            documents, _ = await self.pipeline.retrieval.retrieve(
                query=request.question,
                metadata_filter=metadata_filter,
                top_k=request.top_k or 5,
            )
            yield stream.emit("retrieval_complete", {"source_count": len(documents)})

            if not documents:
                yield stream.emit("insufficient_context", {})
                yield stream.emit("complete", {"sources": []})
                return

            context = self.pipeline.context_builder.build_context(documents)
            citations = self.pipeline.context_builder.extract_citations(documents)

            structured = await self.pipeline.chain.structured_answer(request.question, context)

            yield stream.emit("analysis", {"direct_conclusion": structured.direct_conclusion[:500]})
            yield stream.emit("risk", {"matrix": structured.risk_matrix.model_dump()})
            yield stream.emit("incentives", {"detected": structured.incentives.model_dump()})

            citation_data = [
                {
                    "norma": c["norma"],
                    "articulo": c["articulo"],
                    "texto": c["texto"][:500],
                    "tipo_norma": c["tipo_norma"],
                    "risk_flags": c.get("risk_flags", []),
                }
                for c in citations
            ]
            yield stream.emit("citations", {"citations": citation_data})
            yield stream.emit("complete", {"sources": [d.get("id", "") for d in documents]})

        except Exception as e:
            logger.error(f"Streaming query failed: {e}")
            yield stream.emit("error", {"detail": str(e)})

    async def _process_with_pipeline(self, request: QueryRequest) -> QueryResponse:
        response = await self.pipeline.query(
            question=request.question,
            subsector=request.subsector,
            tipo_norma=request.tipo_norma,
            vigente=request.vigente,
            top_k=request.top_k or 5,
        )
        logger.info(f"Pipeline query: {request.question[:60]}... -> {response.processing_time_ms}ms")
        return response

    async def _process_with_agent(self, request: QueryRequest) -> QueryResponse:
        start_time = time.time()

        result = await self.agent.run(
            question=request.question,
            subsector=request.subsector,
            tipo_norma=request.tipo_norma,
        )

        processing_time = int((time.time() - start_time) * 1000)
        logger.info(f"Agent query (iter {result.get('iteration', 0)}): {request.question[:60]}... -> {processing_time}ms")

        citations = result.get("citations", [])
        sr = result.get("structured_response")

        if sr:
            analysis = RegulatoryAnalysis(
                direct_conclusion=sr.direct_conclusion,
                regulatory_analysis=sr.regulatory_analysis,
                legal_citations=[
                    LegalCitation(
                        norma=c.get("norma", ""),
                        articulo=c.get("articulo", ""),
                        texto=c.get("texto", "")[:500],
                        tipo_norma=c.get("tipo_norma", ""),
                        risk_flags=c.get("risk_flags", []),
                    )
                    for c in citations
                ],
                risk_matrix=sr.risk_matrix or RiskMatrix(),
                incentives_detected=sr.incentives or IncentiveInfo(),
                insufficient_context=sr.insufficient_context,
            )
        else:
            final_text = result.get("final_answer", "")
            analysis = RegulatoryAnalysis(
                direct_conclusion=final_text[:500],
                regulatory_analysis="",
                legal_citations=[
                    LegalCitation(
                        norma=c.get("norma", ""),
                        articulo=c.get("articulo", ""),
                        texto=c.get("texto", "")[:500],
                        tipo_norma=c.get("tipo_norma", ""),
                        risk_flags=c.get("risk_flags", []),
                    )
                    for c in citations
                ],
                risk_matrix=RiskMatrix(),
                incentives_detected=IncentiveInfo(),
                insufficient_context=not bool(result.get("documents")),
            )

        return QueryResponse(
            question=request.question,
            answer=analysis,
            sources=[d.get("id", "") for d in result.get("documents", [])],
            processing_time_ms=processing_time,
        )

    async def close(self):
        if self.pipeline:
            await self.pipeline.close()
        if self.agent:
            await self.agent.close()
        await close_redis()
