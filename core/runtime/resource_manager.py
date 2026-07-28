import asyncio
import time
from typing import Optional

from loguru import logger

from core.embeddings import get_embedder
from vectorstore.qdrant_client import QdrantStore


class ResourceManager:
    def __init__(self) -> None:
        self._embedder = None
        self._qdrant = None
        self._warmed_up = False

    async def warmup(self) -> None:
        """Carga recursos en segundo plano"""
        logger.info("ResourceManager warmup starting...")
        start = time.perf_counter()

        try:
            # Cargar embedder y qdrant en paralelo
            await asyncio.gather(
                self._load_embedder(),
                self._load_qdrant(),
            )
            self._warmed_up = True
            logger.info(f"ResourceManager warmup completed in {time.perf_counter() - start:.2f}s")
        except Exception as e:
            logger.exception(f"ResourceManager warmup failed")
            raise

    async def _load_embedder(self) -> None:
        """Carga el modelo de embeddings"""
        start = time.perf_counter()
        # Ejecutar en threadpool porque es CPU-bound
        loop = asyncio.get_running_loop()
        self._embedder = await loop.run_in_executor(None, get_embedder)
        logger.info(f"Embedder loaded in {time.perf_counter() - start:.2f}s")

    async def _load_qdrant(self) -> None:
        """Conecta a Qdrant"""
        start = time.perf_counter()
        # QdrantStore.initialize() es sincrónico
        self._qdrant = QdrantStore()
        # ✅ CORREGIDO: llamar sin await (es sync)
        self._qdrant.initialize()
        logger.info(f"Qdrant connected in {time.perf_counter() - start:.2f}s")

    def embedder(self):
        """Retorna el embedder cargado"""
        if not self._warmed_up:
            raise RuntimeError("ResourceManager not warmed up")
        return self._embedder

    def qdrant(self):
        """Retorna el cliente Qdrant"""
        if not self._warmed_up:
            raise RuntimeError("ResourceManager not warmed up")
        return self._qdrant

    async def close(self) -> None:
        """Cierra recursos"""
        if self._qdrant:
            # QdrantStore.close() es sincrónico
            self._qdrant.close()
        logger.info("ResourceManager closed")
