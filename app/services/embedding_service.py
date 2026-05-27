from sentence_transformers import SentenceTransformer
from app.config import settings

_embedder = None


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(
            settings.embeddings_model,
            device=settings.embeddings_device,
            trust_remote_code=True,
        )
    return _embedder
