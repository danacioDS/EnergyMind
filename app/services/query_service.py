from typing import Optional
from loguru import logger

from app.rag.pipeline import RAGPipeline
from app.agents.graph import LegalAgentGraph
from app.models.schemas import QueryResponse, QueryRequest, RegulatoryAnalysis, LegalCitation, RiskMatrix, IncentiveInfo


class QueryService:
    def __init__(self):
        self.pipeline: Optional[RAGPipeline] = None
        self.agent: Optional[LegalAgentGraph] = None

    async def initialize(self):
        self.pipeline = RAGPipeline()
        await self.pipeline.initialize()
        self.agent = LegalAgentGraph()
        await self.agent.initialize()
        logger.info("QueryService initialized (pipeline + agent)")

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        if not self.pipeline or not self.agent:
            raise RuntimeError("QueryService not initialized")

        if request.use_agent:
            return await self._process_with_agent(request)
        return await self._process_with_pipeline(request)

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
        import time
        start_time = time.time()

        result = await self.agent.run(
            question=request.question,
            subsector=request.subsector,
            tipo_norma=request.tipo_norma,
        )

        processing_time = int((time.time() - start_time) * 1000)
        logger.info(f"Agent query (iter {result.get('iteration', 0)}): {request.question[:60]}... -> {processing_time}ms")

        citations = result.get("citations", [])
        analysis = RegulatoryAnalysis(
            direct_conclusion=RAGPipeline._extract_section(result.get("final_answer", ""), "DIRECT CONCLUSION") if "##" in result.get("final_answer", "") else result.get("final_answer", "")[:500],
            regulatory_analysis=RAGPipeline._extract_section(result.get("final_answer", ""), "REGULATORY ANALYSIS") if "##" in result.get("final_answer", "") else "",
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
            risk_matrix=RAGPipeline._extract_risk_matrix(result.get("final_answer", "")),
            incentives_detected=RAGPipeline._extract_incentives(result.get("final_answer", ""), result.get("documents", [])),
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
