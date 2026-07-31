import gc
from loguru import logger
from app.config import settings

_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        logger.info("🔽 Loading embedding model on first request...")
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(
            settings.embeddings_model,
            device="cpu"
        )
        gc.collect()
        logger.info(f"✅ Embedder loaded: {settings.embeddings_model}")
    return _embedder
