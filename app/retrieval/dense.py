from typing import List, Optional, Dict, Any
from loguru import logger
from sentence_transformers import SentenceTransformer

from app.config import settings


class DenseRetriever:
    def __init__(self, model_name: str = settings.embeddings_model,
                 device: str = settings.embeddings_device):
        self.model = SentenceTransformer(model_name, device=device)
        logger.info(f"Initialized DenseRetriever with {model_name} on {device}")

    def encode(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts).tolist()

    def encode_query(self, query: str) -> List[float]:
        return self.model.encode(query).tolist()

    async def search(self, query: str, documents: List[Dict[str, Any]],
                     top_k: int = settings.dense_top_k) -> List[Dict[str, Any]]:
        if not documents:
            return []

        query_vec = self.encode_query(query)
        doc_texts = [d.get("texto", "") for d in documents]
        doc_vecs = self.encode(doc_texts)

        import numpy as np
        query_np = np.array(query_vec)
        doc_np = np.array(doc_vecs)
        scores = np.dot(doc_np, query_np) / (
            np.linalg.norm(doc_np, axis=1) * np.linalg.norm(query_np) + 1e-10
        )

        scored = list(zip(documents, scores.tolist()))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[:top_k]:
            results.append({**doc, "dense_score": float(score)})

        return results
