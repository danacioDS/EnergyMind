import time
from typing import List, Dict, Any, Optional

from loguru import logger

from app.config import settings
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
        await self.retrieval.initialize()
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

        logger.info(f"PIPELINE QUERY - metadata filter: {metadata_filter}")

        documents, filter_used = await self.retrieval.retrieve(
            query=question,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

        logger.info(f"Retrieved {len(documents)} documents")

        if not documents:
            logger.warning("No documents retrieved for query")

            processing_time = int(
                (time.time() - start_time) * 1000
            )

            return QueryResponse(
                question=question,
                answer=RegulatoryAnalysis(
                    direct_conclusion=(
                        "Insufficient information in the "
                        "specialized renewable energy legal corpus."
                    ),
                    regulatory_analysis=(
                        "No relevant legal documents were found "
                        "in the corpus."
                    ),
                    risk_matrix=RiskMatrix(),
                    incentives_detected=IncentiveInfo(),
                    insufficient_context=True,
                ),
                processing_time_ms=processing_time,
            )

        context = self.context_builder.build_context(documents)

        citations = self.context_builder.extract_citations(documents)

        structured = await self.chain.structured_answer(
            question,
            context,
        )

        if structured.insufficient_context:

            analysis = RegulatoryAnalysis(
                direct_conclusion=str(
                    structured.direct_conclusion
                    or (
                        "Insufficient information in the "
                        "specialized renewable energy legal corpus."
                    )
                ),
                regulatory_analysis=str(
                    structured.regulatory_analysis
                    or (
                        "The corpus does not contain sufficient "
                        "legal context."
                    )
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
                risk_matrix=(
                    structured.risk_matrix
                    or RiskMatrix()
                ),
                incentives_detected=(
                    structured.incentives_detected
                    or IncentiveInfo()
                ),
                insufficient_context=True,
            )

        else:

            analysis = RegulatoryAnalysis(
                direct_conclusion=str(
                    structured.direct_conclusion or ""
                ),
                regulatory_analysis=str(
                    structured.regulatory_analysis or ""
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
                risk_matrix=(
                    structured.risk_matrix
                    or RiskMatrix()
                ),
                incentives_detected=(
                    structured.incentives_detected
                    or IncentiveInfo()
                ),
                insufficient_context=False,
            )

        processing_time = int(
            (time.time() - start_time) * 1000
        )

        logger.info(f"Query complete ({processing_time}ms)")

        return QueryResponse(
            question=question,
            answer=analysis,
            sources=[
                d.get("id", "")
                for d in documents
            ],
            processing_time_ms=processing_time,
        )

    async def close(self):
        logger.info("Closing RAGPipeline")
        await self.retrieval.close()
