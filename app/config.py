from pydantic_settings import BaseSettings
from typing import List, Optional, Union, Any


class _Settings(BaseSettings):
    """Configuración interna de la aplicación."""
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"
    
    # API
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_ORIGINS: Union[str, List[str]] = ["*"]
    
    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "energymind"
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_USE_CLOUD: bool = False
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_TTL: int = 3600
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # LLM
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama3-70b-8192"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:1b"
    
    # Cloudflare Workers AI
    CLOUDFLARE_ACCOUNT_ID: Optional[str] = None
    CLOUDFLARE_API_TOKEN: Optional[str] = None
    CLOUDFLARE_MODEL: str = "@cf/meta/llama-3.1-8b-instruct"
    
    # Embeddings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDINGS_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDINGS_DIMENSIONS: int = 384
    EMBEDDINGS_DEVICE: str = "cpu"
    
    # Retrieval
    BM25_INDEX_PATH: str = "cache/bm25_index.pkl"
    DEFAULT_TOP_K: int = 10
    TOP_K: int = 10
    BM25_TOP_K: int = 50
    DENSE_TOP_K: int = 50
    FINAL_TOP_K: int = 5
    HYBRID_ALPHA: float = 0.5
    
    # Corpus
    CORPUS_RAW_PATH: str = "corpus/raw"
    CORPUS_PROCESSED_PATH: str = "corpus/processed"
    CORPUS_NORMALIZED_PATH: str = "corpus/normalized"
    
    # Logging
    LOG_LEVEL: str = "INFO"


class Settings:
    """Wrapper que permite acceso tanto en mayúsculas como minúsculas."""
    
    def __init__(self):
        self._settings = _Settings()
    
    def __getattr__(self, name: str) -> Any:
        if hasattr(self._settings, name):
            return getattr(self._settings, name)
        upper_name = name.upper()
        if hasattr(self._settings, upper_name):
            return getattr(self._settings, upper_name)
        lower_name = name.lower()
        if hasattr(self._settings, lower_name):
            return getattr(self._settings, lower_name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise AttributeError(f"Cannot set attribute '{name}'")
    
    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key, default)
        except AttributeError:
            return default
    
    # Propiedades
    @property
    def top_k(self): return self._settings.TOP_K
    @property
    def bm25_top_k(self): return self._settings.BM25_TOP_K
    @property
    def dense_top_k(self): return self._settings.DENSE_TOP_K
    @property
    def final_top_k(self): return self._settings.FINAL_TOP_K
    @property
    def hybrid_alpha(self): return self._settings.HYBRID_ALPHA
    @property
    def qdrant_collection(self): return self._settings.QDRANT_COLLECTION
    @property
    def qdrant_url(self): return self._settings.QDRANT_URL
    @property
    def qdrant_api_key(self): return self._settings.QDRANT_API_KEY
    @property
    def qdrant_use_cloud(self): return self._settings.QDRANT_USE_CLOUD
    @property
    def groq_api_key(self): return self._settings.GROQ_API_KEY
    @property
    def groq_model(self): return self._settings.GROQ_MODEL
    @property
    def gemini_api_key(self): return self._settings.GEMINI_API_KEY
    @property
    def gemini_model(self): return self._settings.GEMINI_MODEL
    @property
    def embeddings_dimensions(self): return self._settings.EMBEDDINGS_DIMENSIONS
    @property
    def embeddings_device(self): return self._settings.EMBEDDINGS_DEVICE
    @property
    def embeddings_model(self): return self._settings.EMBEDDINGS_MODEL
    @property
    def corpus_raw_path(self): return self._settings.CORPUS_RAW_PATH
    @property
    def corpus_processed_path(self): return self._settings.CORPUS_PROCESSED_PATH
    @property
    def corpus_normalized_path(self): return self._settings.CORPUS_NORMALIZED_PATH
    @property
    def redis_host(self): return self._settings.REDIS_HOST
    @property
    def redis_port(self): return self._settings.REDIS_PORT
    @property
    def cloudflare_account_id(self): return self._settings.CLOUDFLARE_ACCOUNT_ID
    @property
    def cloudflare_api_token(self): return self._settings.CLOUDFLARE_API_TOKEN
    @property
    def cloudflare_model(self): return self._settings.CLOUDFLARE_MODEL


settings = Settings()

print(f"✅ Config loaded: TOP_K={settings.top_k}, DENSE_TOP_K={settings.dense_top_k}")
