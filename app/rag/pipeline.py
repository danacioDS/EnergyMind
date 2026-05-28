import time
from typing import Dict, Any, Optional

from loguru import logger

from app.rag.chain import LegalChain
from app.rag.context_builder import ContextBuilder
from app.retrieval.engine import RetrievalEngine
from app.models.schemas import (
    QueryResponse,
    RegulatoryAnalysis,
    RiskMatrix,
    IncentiveInfo,
    LegalCitation,
)


class RAGPipeline:
    def __init__(self, qdrant=None):
        self.retrieval = RetrievalEngine(qdrant=qdrant)
        self.chain = LegalChain()
        self.context_builder = ContextBuilder()

    async def initialize(self):
        # safe if retrieval has async init, otherwise harmless
        init_fn = getattr(self.retrieval, "initialize", None)
        if init_fn:
            result = init_fn()
            if hasattr(result, "__await__"):
                await result

        logger.info("RAGPipeline initialized")

    async def query(
        self,
        question: str,
        subsector: Optional[str] = None,
        tipo_norma: Optional[str] = None,
        vigente: Optional[bool] = None,
        top_k: int = 5,
    ) -> QueryResponse:

        start_time = time.time()

        metadata_filter: Dict[str, Any] = {}

        if subsector:
            metadata_filter["subsector"] = subsector

        if tipo_norma:
            metadata_filter["tipo_norma"] = tipo_norma

        if vigente is not None:
            metadata_filter["vigente"] = vigente

        logger.info(f"PIPELINE QUERY - filter: {metadata_filter}")

        # -------------------------
        # 🔥 FIX: retrieval is SYNC
        # -------------------------
        documents, filter_used = self.retrieval.retrieve(
            query=question,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

        logger.info(f"Retrieved {len(documents)} documents")

        if not documents:
            processing_time = int((time.time() - start_time) * 1000)

            return QueryResponse(
                question=question,
                answer=RegulatoryAnalysis(
                    direct_conclusion=(
                        "Insufficient information in the specialized renewable energy legal corpus."
                    ),
                    regulatory_analysis=(
                        "No relevant legal documents were found in the corpus."
                    ),
                    risk_matrix=RiskMatrix(),
                    incentives_detected=IncentiveInfo(),
                    insufficient_context=True,
                ),
                sources=[],
                processing_time_ms=processing_time,
            )

        # -------------------------
        # Context building
        # -------------------------
        context = self.context_builder.build_context(documents)
        citations = self.context_builder.extract_citations(documents)

        # -------------------------
        # LLM call (ASYNC OK)
        # -------------------------
        structured = await self.chain.structured_answer(
            question,
            context,
        )

        # -------------------------
        # Build response
        # -------------------------
        analysis = RegulatoryAnalysis(
            direct_conclusion=str(
                structured.direct_conclusion
                or "Insufficient information in corpus."
            ),
            regulatory_analysis=str(
                structured.regulatory_analysis
                or "The corpus does not contain sufficient legal context."
            ),
            legal_citations=[
                LegalCitation(
                    norma=c["norma"],
                    articulo=c["articulo"],
                    texto=c["texto"][:500],
                    tipo_norma=c["tipo_norma"],
                    risk_flags=c.get("risk_flags", []),
                )
                for c in citations
            ],
            risk_matrix=structured.risk_matrix or RiskMatrix(),
            incentives_detected=structured.incentives_detected or IncentiveInfo(),
            insufficient_context=structured.insufficient_context,
        )

        processing_time = int((time.time() - start_time) * 1000)

        logger.info(f"Query complete ({processing_time}ms)")

        return QueryResponse(
            question=question,
            answer=analysis,
            sources=[d.get("id", "") for d in documents],
            processing_time_ms=processing_time,
        )

    async def close(self):
        logger.info("Closing RAGPipeline")

        close_fn = getattr(self.retrieval, "close", None)
        if close_fn:
            result = close_fn()
            if hasattr(result, "__await__"):
                await result
