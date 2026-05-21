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
        if not self.model or not documents:
            return documents[:top_k]

        pairs = [(query, d.get("texto", "")) for d in documents]
        scores = self.model.compute_score(pairs)

        if isinstance(scores, list) and len(scores) > 0 and isinstance(scores[0], list):
            scores = [s[0] for s in scores]

        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[:top_k]:
            results.append({**doc, "rerank_score": float(score)})

        return results
