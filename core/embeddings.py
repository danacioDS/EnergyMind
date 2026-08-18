import os
import gc
import threading
from loguru import logger
from app.config import settings

_embedder = None
_embedder_lock = threading.Lock()

def get_embedder():
    global _embedder
    
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                logger.info("🔽 Loading embedding model...")
                
                hf_token = os.getenv("HF_TOKEN")
                if hf_token:
                    os.environ["HUGGINGFACE_HUB_TOKEN"] = hf_token
                    logger.info("✅ HF_TOKEN detected")
                
                try:
                    from sentence_transformers import SentenceTransformer
                    import torch
                    
                    model_name = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
                    
                    logger.info(f"📥 Loading model: {model_name}")
                    
                    # ✅ SOLUCIÓN: Cargar el modelo directamente sin usar meta tensors
                    # Usar el método de carga que evita el problema de meta tensors
                    _embedder = SentenceTransformer(
                        model_name,
                        device="cpu",
                        trust_remote_code=True,
                        use_auth_token=hf_token if hf_token else None
                    )
                    
                    # ✅ Forzar a CPU después de cargar
                    if hasattr(_embedder, "to"):
                        _embedder.to("cpu")
                    
                    # ✅ Probar que funciona
                    test_embedding = _embedder.encode("test", convert_to_numpy=True)
                    logger.info(f"✅ Model test successful: embedding shape {test_embedding.shape}")
                    
                    # ✅ Limpiar memoria
                    gc.collect()
                    
                    logger.info(f"✅ Embedder loaded successfully: {model_name}")
                    
                except Exception as e:
                    logger.error(f"❌ Failed to load embedder: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    raise
    
    return _embedder
