import time
from typing import List, Dict, Any

from loguru import logger

from app.config import settings


class Reranker:
    def __init__(
        self,
        model_name: str = settings.reranker_model,
        device: str = settings.reranker_device,
    ):
        self.model_name = model_name
        self.device = "cpu"
        self.model = None

        logger.info(f"Reranker created (model={self.model_name}, device={self.device})")

    async def initialize(self):
        try:
            from FlagEmbedding import FlagReranker

            t = time.perf_counter()

            self.model = FlagReranker(
                self.model_name,
                use_fp16=False,
                device=self.device,
            )

            logger.info(
                f"Reranker initialized with {self.model_name} "
                f"in {time.perf_counter() - t:.2f}s"
            )

            return

        except ImportError:
            logger.warning("FlagEmbedding not available, using CrossEncoder fallback")

        except Exception:
            logger.exception("FlagReranker initialization failed")

        try:
            from sentence_transformers import CrossEncoder

            fallback_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"

            t = time.perf_counter()

            self.model = CrossEncoder(
                fallback_model,
                device=self.device,
                max_length=512,
            )

            logger.info(
                f"Reranker initialized with {fallback_model} "
                f"in {time.perf_counter() - t:.2f}s"
            )

        except Exception:
            logger.exception("Failed to initialize CrossEncoder reranker")
            self.model = None

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = settings.reranker_top_k,
    ) -> List[Dict[str, Any]]:

        if not self.model:
            logger.warning("Reranker model unavailable — skipping rerank")
            return documents[:top_k]

        if not documents:
            logger.warning("Reranker received empty documents")
            return []

        logger.info(f"Reranking {len(documents)} documents")

        pairs = [
            (query, d.get("texto", ""))
            for d in documents
        ]

        try:
            if hasattr(self.model, "compute_score"):
                scores = self.model.compute_score(pairs)

            else:
                scores = self.model.predict(pairs)

            if (
                isinstance(scores, list)
                and len(scores) > 0
                and isinstance(scores[0], list)
            ):
                scores = [s[0] for s in scores]

            scores_list = (
                scores.tolist()
                if hasattr(scores, "tolist")
                else scores
            )

            if not scores_list:
                logger.warning("Reranker produced empty scores")
                return documents[:top_k]

            scored = list(zip(documents, scores_list))

            scored.sort(
                key=lambda x: x[1],
                reverse=True,
            )

            results = []

            for doc, score in scored[:top_k]:
                results.append({
                    **doc,
                    "rerank_score": float(score),
                })

            logger.info(f"Rerank completed (returned {len(results)} docs)")

            return results

        except Exception:
            logger.exception("Rerank failed")

            return documents[:top_k]
