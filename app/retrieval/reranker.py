from typing import List, Dict, Any
from loguru import logger
import os

class Reranker:
    def __init__(self):
        self.model = None
        self.initialized = False
        self.disabled = True  # ✅ Desactivado para Render Free
        logger.info("Reranker disabled (memory optimization for Render)")

    def initialize(self):
        """No hace nada - reranker desactivado"""
        pass

    def rerank(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Retorna los documentos sin reranking"""
        return documents
