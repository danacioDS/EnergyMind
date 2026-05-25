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
        await self.qdrant.initialize()
        if self.hybrid.bm25.load(BM25_INDEX_PATH):
            logger.info("RetrievalEngine initialized (BM25 from cache)")
        else:
            logger.info("RetrievalEngine initialized (no BM25 cache)")

    async def retrieve(self, query: str,
                       metadata_filter: Optional[Dict[str, Any]] = None,
                       top_k: int = settings.top_k) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

        qdrant_filter = self.hybrid.metadata_filter.infer_from_query(query, metadata_filter)

        qdrant_results = await self.qdrant.search(
            query=query,
            metadata_filter=qdrant_filter,
            top_k=top_k * 2,
        )

        if not qdrant_results:
            logger.warning("No results from Qdrant, using pure semantic search")
            qdrant_results = await self.qdrant.search(
                query=query,
                metadata_filter=None,
                top_k=top_k * 2,
            )

        # Build BM25 index from Qdrant results if not cached
        if qdrant_results and not self.hybrid.bm25.index:
            self.hybrid.bm25.build_index(qdrant_results)
            self.hybrid.bm25.save(BM25_INDEX_PATH)

        results_reranked, filter_used = await self.hybrid.retrieve(query, metadata_filter)

        if not results_reranked:
            results_reranked = qdrant_results[:settings.final_top_k]
            filter_used = qdrant_filter

        return results_reranked, filter_used

    async def close(self):
        await self.qdrant.close()
