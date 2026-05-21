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
        self.retrieval = RetrievalEngine()
        self.chain = LegalChain()
        self.context_builder = ContextBuilder()

    async def initialize(self):
        await self.retrieval.initialize()
        logger.info("RAGPipeline initialized")

    async def query(self, question: str,
                    subsector: Optional[str] = None,
                    tipo_norma: Optional[str] = None,
                    vigente: Optional[bool] = None,
                    top_k: int = 5) -> QueryResponse:

        start_time = time.time()
        metadata_filter: Dict[str, Any] = {}
        if subsector:
            metadata_filter["subsector"] = subsector
        if tipo_norma:
            metadata_filter["tipo_norma"] = tipo_norma
        if vigente is not None:
            metadata_filter["vigente"] = vigente

        documents, filter_used = await self.retrieval.retrieve(
            query=question,
            metadata_filter=metadata_filter,
            top_k=top_k,
        )

        if not documents:
            logger.warning("No documents retrieved for query")
            processing_time = int((time.time() - start_time) * 1000)
            return QueryResponse(
                question=question,
                answer=RegulatoryAnalysis(
                    direct_conclusion="Insufficient information in the specialized renewable energy legal corpus.",
                    regulatory_analysis="No relevant legal documents were found in the corpus.",
                    risk_matrix=RiskMatrix(),
                    incentives_detected=IncentiveInfo(detected=False),
                    insufficient_context=True,
                ),
                processing_time_ms=processing_time,
            )

        context = self.context_builder.build_context(documents)
        citations = self.context_builder.extract_citations(documents)

        llm_response = await self.chain.answer(question, context)

        risk_matrix = self._extract_risk_matrix(llm_response)
        incentives = self._extract_incentives(llm_response, documents)

        analysis = RegulatoryAnalysis(
            direct_conclusion=self._extract_section(llm_response, "DIRECT CONCLUSION"),
            regulatory_analysis=self._extract_section(llm_response, "REGULATORY ANALYSIS"),
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
            risk_matrix=risk_matrix,
            incentives_detected=incentives,
            insufficient_context=False,
        )

        processing_time = int((time.time() - start_time) * 1000)

        return QueryResponse(
            question=question,
            answer=analysis,
            sources=[d.get("id", "") for d in documents],
            processing_time_ms=processing_time,
        )

    @staticmethod
    def _extract_section(text: str, section_name: str) -> str:
        import re
        pattern = rf"##\s*{section_name}\s*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text[:500]

    @staticmethod
    def _extract_risk_matrix(text: str) -> RiskMatrix:
        import re
        matrix = RiskMatrix()
        patterns = {
            "ideological_framework": r"Ideological Framework:\s*(\w+-?\w*)",
            "constitutional_conflict_risk": r"Constitutional Conflict Risk:\s*(\w+-?\w*)",
            "nationalization_risk": r"Nationalization Risk:\s*(\w+-?\w*)",
            "regulatory_instability": r"Regulatory Instability:\s*(\w+-?\w*)",
            "legal_ambiguity": r"Legal Ambiguity:\s*(\w+-?\w*)",
            "arbitration_protection": r"Arbitration Protection:\s*(\w+-?\w*)",
        }
        for field, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                setattr(matrix, field, match.group(1))
        return matrix

    @staticmethod
    def _extract_incentives(text: str, documents: List[Dict[str, Any]]) -> IncentiveInfo:
        import re
        has_incentive = re.search(r"Status:\s*(Active|Pending)", text, re.IGNORECASE)

        if has_incentive:
            type_match = re.search(r"Type:\s*([^\n]+)", text)
            basis_match = re.search(r"Legal Basis:\s*([^\n]+)", text)
            return IncentiveInfo(
                detected=True,
                type=type_match.group(1).strip() if type_match else None,
                description=basis_match.group(1).strip() if basis_match else None,
                articles=[],
            )

        for doc in documents:
            payload = doc.get("payload", doc)
            if payload.get("renewable_incentive", False):
                return IncentiveInfo(
                    detected=True,
                    type="Renewable Energy Incentive",
                    description=f"Found in {payload.get('tipo_norma', '')} {payload.get('norma_id', '')}",
                    articles=[payload.get("articulo", "")],
                )

        return IncentiveInfo(detected=False)

    async def close(self):
        await self.retrieval.close()
