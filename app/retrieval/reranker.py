from typing import List, Dict, Any, Optional
from loguru import logger
from app.config import settings


class Reranker:
    def __init__(self):
        self.model = None
        self.model_name = settings.reranker_model or "cross-encoder/ms-marco-MiniLM-L-6-v2"
        self.device = settings.reranker_device or "cpu"
        self.initialized = False
        logger.info(f"Reranker created (model={self.model_name}, device={self.device})")

    def initialize(self):
        """Carga el modelo de reranker"""
        if self.initialized:
            return
        
        try:
            from FlagEmbedding import FlagReranker
            self.model = FlagReranker(
                self.model_name,
                use_fp16=False,
                device=self.device
            )
            logger.info(f"Reranker loaded: {self.model_name}")
        except Exception as e:
            logger.warning(f"FlagReranker failed: {e}")
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(
                    self.model_name,
                    device=self.device
                )
                logger.info(f"Reranker loaded (CrossEncoder fallback): {self.model_name}")
            except Exception as e2:
                logger.warning(f"Reranker model unavailable — skipping rerank: {e2}")
                self.model = None
        
        self.initialized = True

    def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Re-rank documents using cross-encoder"""
        if not documents:
            return documents
        
        if not self.initialized:
            self.initialize()
        
        if self.model is None:
            logger.warning("Reranker model unavailable — skipping rerank")
            return documents
        
        try:
            pairs = [[query, doc.get("texto", doc.get("payload", {}).get("texto", ""))] for doc in documents]
            scores = self.model.compute_score(pairs)
            
            for i, doc in enumerate(documents):
                doc["rerank_score"] = float(scores[i])
            
            return sorted(documents, key=lambda x: x.get("rerank_score", 0), reverse=True)
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            return documents
