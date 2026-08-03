import os
import gc
from loguru import logger
from app.config import settings

_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        logger.info("🔽 Loading embedding model on first request...")
        
        # ✅ FORZAR EL USO DEL TOKEN DE HUGGING FACE
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
            logger.info("✅ HF_TOKEN detected, using it for authentication")
        else:
            logger.warning("⚠️ HF_TOKEN not set, trying unauthenticated download (may fail)")
        
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer(
            settings.embeddings_model,
            device="cpu",
            use_auth_token=hf_token  # ✅ Pasar el token explícitamente
        )
        gc.collect()
        logger.info(f"✅ Embedder loaded: {settings.embeddings_model}")
    return _embedder
