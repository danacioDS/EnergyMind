import asyncio
import time
from typing import Optional

from loguru import logger

from core.embeddings import get_embedder
from app.config import settings


class ResourceManager:
    def __init__(self) -> None:
        self._ready = asyncio.Event()
        self._embedder = None
        self._qdrant = None
        self._warmup_error: Optional[Exception] = None
        self._warmup_start: Optional[float] = None

    async def warmup(self) -> None:
        self._warmup_start = time.perf_counter()
        logger.info("ResourceManager warmup starting...")
        try:
            await asyncio.gather(
                asyncio.to_thread(self._load_embedder),
                self._load_qdrant(),
            )
            elapsed = time.perf_counter() - self._warmup_start
            logger.info(f"ResourceManager ready in {elapsed:.2f}s")
            self._ready.set()
        except Exception as e:
            self._warmup_error = e
            self._ready.set()
            logger.exception("ResourceManager warmup failed")
            raise

    async def wait_ready(self, timeout: float = 120.0) -> None:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise RuntimeError("ResourceManager warmup timed out")
        if self._warmup_error:
            raise RuntimeError(f"ResourceManager warmup failed: {self._warmup_error}")

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._warmup_error is None

    def embedder(self):
        if self._embedder is None:
            raise RuntimeError("Embedder not loaded — call wait_ready() first")
        return self._embedder

    def qdrant(self):
        if self._qdrant is None:
            raise RuntimeError("Qdrant not connected — call wait_ready() first")
        return self._qdrant

    async def close(self) -> None:
        if self._qdrant:
            await self._qdrant.close()
            logger.info("Qdrant connection closed")

    def _load_embedder(self) -> None:
        t = time.perf_counter()
        self._embedder = get_embedder()
        logger.info(f"Embedder loaded in {time.perf_counter() - t:.2f}s")

    async def _load_qdrant(self) -> None:
        from vectorstore.qdrant_client import QdrantStore
        t = time.perf_counter()
        store = QdrantStore()
        await store.initialize()
        self._qdrant = store
        logger.info(f"Qdrant connected in {time.perf_counter() - t:.2f}s")
