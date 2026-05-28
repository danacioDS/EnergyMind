import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

from app.config import settings
from app.retrieval.hybrid import HybridRetriever
from vectorstore.qdrant_client import QdrantStore


BM25_INDEX_PATH = Path(settings.base_dir) / "cache" / "bm25_index.pkl"


class RetrievalEngine:
    def __init__(self):
        self.qdrant = QdrantStore()
        self.hybrid = HybridRetriever()

    async def initialize(self):
        await self._log_qdrant_collection_info()
        if not self.hybrid.bm25.load(BM25_INDEX_PATH):
            logger.info("Building BM25 index from full Qdrant corpus...")
            all_docs = await self.qdrant.scroll_all()
            if all_docs:
                await asyncio.to_thread(self.hybrid.bm25.build_index, all_docs)
                self.hybrid.bm25.save(BM25_INDEX_PATH)
                logger.info(f"BM25 index built from {len(all_docs)} documents")
            else:
                logger.warning("No documents found in Qdrant — BM25 index empty")
        else:
            logger.info("RetrievalEngine initialized (BM25 from cache)")

    async def _log_qdrant_collection_info(self):
        try:
            collection_info = self.qdrant.client.get_collection(
                collection_name=self.qdrant.collection_name,
            )
            points_count = collection_info.points_count
            logger.info(f"Qdrant collection '{self.qdrant.collection_name}': {points_count} indexed documents")
        except Exception as e:
            logger.warning(f"Could not retrieve Qdrant collection info: {e}")

    async def retrieve(self, query: str,
                       metadata_filter: Optional[Dict[str, Any]] = None,
                       top_k: int = settings.top_k) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

        qdrant_filter = self.hybrid.metadata_filter.infer_from_query(query, metadata_filter)
        logger.info(f"Qdrant metadata filter: {qdrant_filter}")

        bm25_task = self.hybrid.bm25.search(query, top_k=settings.bm25_top_k)
        qdrant_task = self.qdrant.search(
            query=query,
            metadata_filter=qdrant_filter,
            top_k=top_k * 2,
        )
        bm25_results, qdrant_results = await asyncio.gather(bm25_task, qdrant_task)
        logger.info(f"BM25 returned {len(bm25_results)} results, Qdrant returned {len(qdrant_results)} results")

        if not qdrant_results:
            logger.warning("No results from Qdrant with filter — retrying without metadata filter")
            qdrant_results = await self.qdrant.search(
                query=query,
                metadata_filter=None,
                top_k=top_k * 2,
            )
            logger.info(f"Qdrant search (no filter) returned {len(qdrant_results)} results")

        if not qdrant_results:
            logger.warning("Qdrant collection appears empty — no documents indexed")
            return [], qdrant_filter

        for r in qdrant_results:
            r["dense_score"] = r.pop("score", 0.0)

        results_reranked, filter_used = await self.hybrid.retrieve_with_results(
            query, bm25_results, qdrant_results, metadata_filter, top_k=top_k,
        )

        if not results_reranked:
            logger.warning("Hybrid retrieval returned empty — using raw Qdrant results as fallback")
            results_reranked = qdrant_results[:settings.final_top_k]
            filter_used = qdrant_filter

        return results_reranked, filter_used

    async def close(self):
        await self.qdrant.close()
