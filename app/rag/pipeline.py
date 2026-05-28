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
    def __init__(self):

        logger.info("PIPELINE STEP 1 - creating RetrievalEngine")

        self.retrieval = RetrievalEngine()

        logger.info("PIPELINE STEP 2 - RetrievalEngine created")

        logger.info("PIPELINE STEP 3 - creating LegalChain")

        self.chain = LegalChain()

        logger.info("PIPELINE STEP 4 - LegalChain created")

        logger.info("PIPELINE STEP 5 - creating ContextBuilder")

        self.context_builder = ContextBuilder()

        logger.info("PIPELINE STEP 6 - ContextBuilder created")

    async def initialize(self):

        logger.info(
            "PIPELINE INIT STEP 1 - initializing RetrievalEngine"
        )

        await self.retrieval.initialize()

        logger.info(
            "PIPELINE INIT STEP 2 - RetrievalEngine initialized"
        )

        logger.info("RAGPipeline initialized")

    async def query(
        self,
        question: str,
        subsector: Optional[str] = None,
        tipo_norma: Optional[str] = None,
        vigente: Optional[bool] = None,
        top_k: int = 5,
    ) -> QueryResponse:

        logger.info(
            f"PIPELINE QUERY START - {question[:80]}"
        )

        start_time = time.time()

        metadata_filter: Dict[str, Any] = {}

        if subsector:
            metadata_filter["subsector"] = subsector

        if tipo_norma:
            metadata_filter["tipo_norma"] = tipo_norma

        if vigente is not None:
            metadata_filter["vigente"] = vigente

        logger.info(
            f"PIPELINE QUERY - metadata filter: {metadata_filter}"
        )

        #
        # RETRIEVAL
        #
        logger.info("PIPELINE QUERY STEP 1 - retrieval start")

        documents, filter_used = await self.retrieval.retrieve(
            query=question,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

        logger.info(
            f"PIPELINE QUERY STEP 2 - retrieval done "
            f"(docs={len(documents)})"
        )

        if not documents:

            logger.warning(
                "No documents retrieved for query"
            )

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

        #
        # CONTEXT BUILDING
        #
        logger.info(
            "PIPELINE QUERY STEP 3 - building context"
        )

        context = self.context_builder.build_context(
            documents
        )

        logger.info(
            "PIPELINE QUERY STEP 4 - extracting citations"
        )

        citations = self.context_builder.extract_citations(
            documents
        )

        #
        # LLM CHAIN
        #
        logger.info(
            "PIPELINE QUERY STEP 5 - structured_answer start"
        )

        structured = await self.chain.structured_answer(
            question,
            context,
        )

        logger.info(
            "PIPELINE QUERY STEP 6 - structured_answer done"
        )

        #
        # RESPONSE BUILDING
        #
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

        logger.info(
            f"PIPELINE QUERY COMPLETE "
            f"({processing_time}ms)"
        )

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

        logger.info(
            "PIPELINE CLOSE - closing RetrievalEngine"
        )

        await self.retrieval.close()

        logger.info(
            "PIPELINE CLOSE - RetrievalEngine closed"
        )
