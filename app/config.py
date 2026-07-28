from pathlib import Path
from typing import Optional

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application configuration.
    Loads values from .env automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================
    # QDRANT
    # =========================================================

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "energymind"

    # =========================================================
    # EMBEDDINGS
    # =========================================================

    embeddings_model: str = "BAAI/bge-m3"
    embeddings_dimensions: int = 1024
    embeddings_device: str = "cpu"

    # =========================================================
    # RERANKER
    # =========================================================

    reranker_model: str = "BAAI/bge-reranker-large"
    reranker_device: str = "cpu"
    reranker_top_k: int = 5

    # =========================================================
    # LLM
    # =========================================================

    llm_model: str = "llama3.1"
    llm_provider: str = "ollama"
    llm_fallback_provider: Optional[str] = None

    ollama_base_url: str = "http://localhost:11434"

    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"
    
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash"

    # =========================================================
    # GROQ
    # =========================================================
    
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.3-70b-versatile"

    # =========================================================
    # CEREBRAS - Fallback 1
    # =========================================================
    

    # =========================================================
    # LANGCHAIN
    # =========================================================

    langchain_tracing_v2: bool = False
    langchain_api_key: Optional[str] = None

    # =========================================================
    # OPTIONAL NEO4J
    # =========================================================

    neo4j_uri: Optional[str] = None
    neo4j_user: Optional[str] = None
    neo4j_password: Optional[str] = None

    # =========================================================
    # API
    # =========================================================

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 4
    api_debug: bool = False

    # =========================================================
    # LOGGING
    # =========================================================

    log_level: str = "INFO"
    log_format: str = "json"

    # =========================================================
    # PATHS
    # =========================================================

    base_dir: Path = Path(__file__).resolve().parent.parent

    corpus_raw_path: Path = base_dir / "corpus" / "raw"
    corpus_processed_path: Path = base_dir / "corpus" / "processed"
    corpus_normalized_path: Path = base_dir / "corpus" / "normalized"

    # =========================================================
    # REDIS
    # =========================================================

    redis_host: str = "localhost"
    redis_port: int = 6379

    # =========================================================
    # CORS
    # =========================================================

    frontend_origins: str = "http://localhost:3000"

    # =========================================================
    # RETRIEVAL
    # =========================================================

    top_k: int = 10
    bm25_top_k: int = 20
    dense_top_k: int = 20
    final_top_k: int = 5
    hybrid_alpha: float = 0.5

    # =========================================================
    # METHODS
    # =========================================================

    def get_llm_config(self) -> dict:
        """
        Returns provider-specific LLM configuration.
        """

        if self.llm_provider.lower() == "ollama":
            return {
                "model": self.llm_model,
                "base_url": self.ollama_base_url,
                "temperature": 0.1,
                "top_p": 0.9,
            }

        return {
            "model": self.openai_model,
            "api_key": self.openai_api_key,
            "temperature": 0.1,
        }


settings = Settings()
