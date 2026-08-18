from typing import List, Dict, Any, Optional
from loguru import logger
import asyncio

from app.retrieval.hybrid import HybridRetriever
from vectorstore.qdrant_client import QdrantStore
from app.config import settings
from pathlib import Path


class RetrievalEngine:
    def __init__(self, qdrant: Optional[QdrantStore] = None) -> None:
        self.qdrant = qdrant or QdrantStore()
        self.hybrid = HybridRetriever()
        self.initialized = False

    async def initialize(self) -> None:
        """Inicializa el motor de recuperación"""
        logger.info("Initializing RetrievalEngine...")
        
        # Inicializar Qdrant (es sincrónico)
        self.qdrant.initialize()
        
        # Inicializar el retriever híbrido
        await self._init_hybrid()
        
        self.initialized = True
        logger.info("RetrievalEngine initialized")

    async def _init_hybrid(self) -> None:
        """Inicializa el retriever híbrido con BM25 y Dense"""
        try:
            # Intentar cargar BM25 desde cache
            BM25_INDEX_PATH = Path(".") / "cache" / "bm25_index.pkl"
            
            loaded = self.hybrid.bm25.load(BM25_INDEX_PATH)
            if loaded:
                logger.info("BM25 loaded from cache")
                return
        except Exception as e:
            logger.warning(f"Could not load BM25 cache: {e}")
        
        # Si no hay cache, construir desde el corpus
        logger.info("BM25 cache miss — building from full corpus...")
        
        # scroll_all es sincrónico, ejecutar en threadpool
        loop = asyncio.get_running_loop()
        all_docs = await loop.run_in_executor(
            None,
            self.qdrant.scroll_all
        )
        
        if not all_docs:
            logger.warning("No documents found in Qdrant for BM25 indexing")
            return
        
        # Construir índice BM25
        self.hybrid.bm25.build_index(all_docs)
        
        # Guardar cache
        try:
            self.hybrid.bm25.save(BM25_INDEX_PATH)
        except Exception as e:
            logger.warning(f"Could not save BM25 cache: {e}")
        
        logger.info(f"BM25 index built with {len(all_docs)} documents")

    async def retrieve(
        self,
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Recupera documentos relevantes para la consulta"""
        if not self.initialized:
            await self.initialize()
        
        logger.info(f"Retrieving for query: {query[:50]}...")
        
        # 1. Obtener resultados BM25 (async)
        bm25_results = []
        try:
            if self.hybrid.bm25.index is not None:
                bm25_results = self.hybrid.bm25.search(query, settings.bm25_top_k)
            else:
                logger.warning("BM25 index not available, skipping")
        except Exception as e:
            logger.warning(f"BM25 search failed: {e}")
        
        # 2. Obtener resultados Dense (sync, con threadpool)
        dense_results = []
        try:
            loop = asyncio.get_running_loop()
            dense_results = await loop.run_in_executor(
                None,
                self.qdrant.search,
                query,
                metadata_filter,
                settings.dense_top_k
            )
        except Exception as e:
            logger.warning(f"Dense search failed: {e}")
        
        # 3. Si no hay resultados, retornar vacío
        if not bm25_results and not dense_results:
            logger.warning("No results from any retriever")
            return [], {"filter_used": metadata_filter}
        
        # 4. Determinar alpha para hybrid
        alpha = self.hybrid._infer_alpha(query)
        
        # 5. Hybrid fusion (sync)
        hybrid_results = self.hybrid._fusion(bm25_results, dense_results, alpha)
        
        # 6. Si no hay resultados híbridos, retornar vacío
        if not hybrid_results:
            return [], {"filter_used": metadata_filter}
        
        # 7. Reranking (async)
        try:
            reranked = await self.hybrid.reranker.rerank(
                query, 
                hybrid_results[:settings.top_k]
            )
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
            reranked = hybrid_results[:settings.top_k]
        
        # 8. Devolver top_k final
        final_results = reranked[:top_k] if reranked else hybrid_results[:top_k]
        
        logger.info(f"Retrieved {len(final_results)} documents")
        return final_results, {"alpha": alpha, "filter_used": metadata_filter}
