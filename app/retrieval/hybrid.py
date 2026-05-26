import re
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import numpy as np

from app.config import settings
from app.retrieval.metadata_filter import MetadataFilter
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.reranker import Reranker

# Patterns that suggest exact legal code lookup → bias towards BM25 (keyword match)
_CODE_PATTERNS = re.compile(
    r"(artículo|art\.?\s*\d+|ley\s*\d+|decreto\s*\d+|norma\s*\d+|l\s*\.?\s*n[°º]?\s*\d+)",
    re.IGNORECASE,
)

# Patterns that suggest conceptual/abstract query → bias towards dense (semantic match)
_CONCEPT_PATTERNS = re.compile(
    r"(riesgo|qué\s*es|definición|concepto|qué\s*significa|diferencia|comparación)",
    re.IGNORECASE,
)


class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Retriever()
        self.dense = DenseRetriever()
        self.reranker = Reranker()
        self.metadata_filter = MetadataFilter()

    def _infer_alpha(self, query: str) -> float:
        if _CODE_PATTERNS.search(query):
            return 0.7
        if _CONCEPT_PATTERNS.search(query):
            return 0.3
        return settings.hybrid_alpha

    def _normalize_scores(self, items: List[Dict[str, Any]], score_key: str) -> List[Dict[str, Any]]:
        if not items:
            return []
        scores = np.array([item.get(score_key, 0) for item in items])
        if scores.size == 0:
            return []
        if scores.max() == scores.min():
            for item in items:
                item[f"{score_key}_normalized"] = 0.0
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

        if not doc_map:
            return []

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
        stage_log: Dict[str, int] = {"bm25": 0, "dense": 0, "hybrid": 0, "reranked": 0}

        # Phase 1: BM25 retrieval
        logger.info(f"Retrieval stage [bm25] for: {query}")
        bm25_results = await self.bm25.search(query, top_k=settings.bm25_top_k)
        stage_log["bm25"] = len(bm25_results)
        logger.info(f"  BM25 returned {len(bm25_results)} results")

        if not bm25_results:
            logger.warning("BM25 stage returned empty results — no documents in index or metadata filter too restrictive")
            return [], filter_dict

        # Phase 2: Dense retrieval on BM25 results
        logger.info(f"Retrieval stage [dense] for: {query}")
        dense_results = await self.dense.search(query, bm25_results, top_k=settings.dense_top_k)
        stage_log["dense"] = len(dense_results)
        logger.info(f"  Dense returned {len(dense_results)} results")

        if not dense_results:
            logger.warning("Dense stage returned empty — falling back to BM25-only results")
            fallback = bm25_results[:settings.final_top_k]
            stage_log["hybrid"] = len(fallback)
            logger.info(f"Retrieved {len(fallback)} results (BM25 fallback)")
            return fallback, filter_dict

        # Phase 3: Hybrid fusion with adaptive alpha
        alpha = self._infer_alpha(query)
        logger.info(f"Retrieval stage [fusion] (alpha={alpha})")
        hybrid_results = self._fusion(bm25_results, dense_results, alpha=alpha)
        stage_log["hybrid"] = len(hybrid_results)
        logger.info(f"  Fusion returned {len(hybrid_results)} results")

        if not hybrid_results:
            logger.warning("Fusion stage returned empty — falling back to BM25-only results")
            fallback = bm25_results[:settings.final_top_k]
            return fallback, filter_dict

        hybrid_results = hybrid_results[:top_k]

        # Phase 4: Reranking
        logger.info(f"Retrieval stage [reranker] ({len(hybrid_results)} inputs)")
        reranked = await self.reranker.rerank(query, hybrid_results, top_k=settings.final_top_k)
        stage_log["reranked"] = len(reranked)
        logger.info(f"  Reranker returned {len(reranked)} results")

        logger.info(f"Retrieved {len(reranked)} final results | stages: {stage_log}")
        return reranked, filter_dict
