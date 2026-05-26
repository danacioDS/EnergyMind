from typing import List, Dict, Any, Optional
from loguru import logger
import torch

from app.config import settings


class Reranker:
    def __init__(self, model_name: str = settings.reranker_model,
                 device: str = settings.reranker_device):
        self.model_name = model_name
        self.device = device
        self.model = None
        self._initialize()

    def _initialize(self):
        try:
            from FlagEmbedding import FlagReranker
            self.model = FlagReranker(
                self.model_name,
                use_fp16=(self.device == "cuda"),
                device=self.device,
            )
            logger.info(f"Initialized Reranker with {self.model_name} on {self.device}")
        except ImportError:
            logger.warning("FlagEmbedding not available, using cross-encoder fallback")
            try:
                from sentence_transformers import CrossEncoder
                self.model = CrossEncoder(self.model_name, device=self.device)
                logger.info(f"Initialized CrossEncoder reranker with {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize reranker: {e}")
                self.model = None

    async def rerank(self, query: str, documents: List[Dict[str, Any]],
                     top_k: int = settings.reranker_top_k) -> List[Dict[str, Any]]:
        if not self.model:
            logger.warning("Reranker model not available — skipping rerank")
            return documents[:top_k]

        if not documents:
            logger.warning("Reranker received empty documents — skipping rerank")
            return []

        pairs = [(query, d.get("texto", "")) for d in documents]

        # FlagReranker uses .compute_score(), CrossEncoder uses .predict()
        if hasattr(self.model, "compute_score"):
            scores = self.model.compute_score(pairs)
        else:
            scores = self.model.predict(pairs)

        if isinstance(scores, list) and len(scores) > 0 and isinstance(scores[0], list):
            scores = [s[0] for s in scores]

        scores_list = scores.tolist() if hasattr(scores, "tolist") else scores

        if not scores_list or len(scores_list) == 0:
            logger.warning("Reranker produced no scores — returning documents as-is")
            return documents[:top_k]

        scored = list(zip(documents, scores_list))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[:top_k]:
            results.append({**doc, "rerank_score": float(score)})

        return results
