from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import numpy as np

from app.config import settings
from app.retrieval.metadata_filter import MetadataFilter
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import Reranker


class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Retriever()
        self.dense = DenseRetriever()
        self.reranker = Reranker()
        self.metadata_filter = MetadataFilter()

    def _normalize_scores(self, items: List[Dict[str, Any]], score_key: str) -> List[Dict[str, Any]]:
        scores = np.array([item.get(score_key, 0) for item in items])
        if scores.max() == scores.min():
            return items
        normalized = (scores - scores.min()) / (scores.max() - scores.min() + 1e-10)
        for item, norm_score in zip(items, normalized):
            item[f"{score_key}_normalized"] = float(norm_score)
        return items

    def _fusion(self, bm25_results: List[Dict[str, Any]],
                dense_results: List[Dict[str, Any]],
                alpha: float = 0.5) -> List[Dict[str, Any]]:
        doc_map: Dict[str, Dict[str, Any]] = {}

        for doc in bm25_results:
            doc_id = doc.get("id", "")
            doc_map[doc_id] = {
                **doc,
                "bm25_score": doc.get("bm25_score", 0),
                "dense_score": 0,
                "hybrid_score": 0,
            }

        for doc in dense_results:
            doc_id = doc.get("id", "")
            if doc_id in doc_map:
                doc_map[doc_id]["dense_score"] = doc.get("dense_score", 0)
            else:
                doc_map[doc_id] = {
                    **doc,
                    "bm25_score": 0,
                    "dense_score": doc.get("dense_score", 0),
                    "hybrid_score": 0,
                }

        bm25_list = [d for d in doc_map.values() if d.get("bm25_score", 0) > 0]
        dense_list = [d for d in doc_map.values() if d.get("dense_score", 0) > 0]

        bm25_list = self._normalize_scores(bm25_list, "bm25_score")
        dense_list = self._normalize_scores(dense_list, "dense_score")

        norm_map: Dict[str, Dict[str, Any]] = {}
        for d in bm25_list:
            norm_map[d["id"]] = d
        for d in dense_list:
            if d["id"] in norm_map:
                norm_map[d["id"]]["dense_score_normalized"] = d.get("dense_score_normalized", 0)
            else:
                norm_map[d["id"]] = d

        for doc in norm_map.values():
            bm25_norm = doc.get("bm25_score_normalized", 0)
            dense_norm = doc.get("dense_score_normalized", 0)
            doc["hybrid_score"] = alpha * bm25_norm + (1 - alpha) * dense_norm

        fused = sorted(norm_map.values(), key=lambda x: x["hybrid_score"], reverse=True)
        return fused

    async def retrieve(self, query: str,
                       metadata_filter: Optional[Dict[str, Any]] = None,
                       top_k: int = settings.top_k) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        filter_dict = self.metadata_filter.infer_from_query(query, metadata_filter)

        # Phase 1: Metadata filtering (applied inside BM25/dense)
        # Phase 2: BM25 retrieval
        logger.info(f"Phase 1: BM25 retrieval for: {query}")
        bm25_results = await self.bm25.search(query, top_k=settings.bm25_top_k)

        # Phase 3: Dense retrieval on filtered results
        logger.info(f"Phase 2: Dense retrieval for: {query}")
        if bm25_results:
            dense_results = await self.dense.search(query, bm25_results, top_k=settings.dense_top_k)
        else:
            dense_results = []

        # Phase 4: Hybrid fusion
        logger.info("Phase 3: Hybrid fusion")
        hybrid_results = self._fusion(bm25_results, dense_results)
        hybrid_results = hybrid_results[:top_k]

        # Phase 5: Reranking
        logger.info(f"Phase 4: Reranking {len(hybrid_results)} results")
        reranked = await self.reranker.rerank(query, hybrid_results, top_k=settings.final_top_k)

        logger.info(f"Retrieved {len(reranked)} final results")
        return reranked, filter_dict
