from typing import List, Dict, Any, Optional
from loguru import logger


class ContextBuilder:
    MAX_CONTEXT_LENGTH = 32000

    @staticmethod
    def build_context(documents: List[Dict[str, Any]]) -> str:
        context_parts: List[str] = []

        for i, doc in enumerate(documents, 1):
            payload = doc.get("payload", doc)
            texto = doc.get("texto", "") or payload.get("texto", "")
            tipo_norma = payload.get("tipo_norma", "Unknown")
            norma_id = payload.get("norma_id", "")
            articulo = payload.get("articulo", "")
            subsector = payload.get("subsector", "")
            risk_flags = payload.get("risk_flags", [])
            enfoque = payload.get("enfoque", "")
            renewable = payload.get("renewable_incentive", False)

            header = f"[Document {i}]"
            meta = f"Norm: {tipo_norma} {norma_id} | Article: {articulo}"
            if subsector:
                meta += f" | Subsector: {subsector}"
            if enfoque:
                meta += f" | Approach: {enfoque}"
            if risk_flags:
                meta += f" | Risk Flags: {', '.join(risk_flags)}"
            if renewable:
                meta += " | RENEWABLE INCENTIVE"

            context_parts.append(f"{header}\n{meta}\n{texto}\n")

        context = "\n---\n".join(context_parts)

        if len(context) > ContextBuilder.MAX_CONTEXT_LENGTH:
            logger.warning(f"Context truncated from {len(context)} to {ContextBuilder.MAX_CONTEXT_LENGTH}")
            context = context[:ContextBuilder.MAX_CONTEXT_LENGTH]

        return context

    @staticmethod
    def extract_citations(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        seen: set = set()

        for doc in documents:
            payload = doc.get("payload", doc)
            citation_key = f"{payload.get('tipo_norma', '')}_{payload.get('norma_id', '')}_{payload.get('articulo', '')}"
            if citation_key in seen:
                continue
            seen.add(citation_key)

            citations.append({
                "norma": f"{payload.get('tipo_norma', '')} {payload.get('norma_id', '')}",
                "articulo": payload.get("articulo", ""),
                "texto": doc.get("texto", "") or payload.get("texto", ""),
                "tipo_norma": payload.get("tipo_norma", ""),
                "risk_flags": payload.get("risk_flags", []),
            })

        return citations
