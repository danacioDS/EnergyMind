"""
Dense retriever using sentence transformers.
"""
from typing import List, Dict, Any, Optional
import numpy as np
from loguru import logger
from app.config import settings
from core.embeddings import get_embedder
from vectorstore.qdrant_client import QdrantStore


class DenseRetriever:
    """Retriever vectorial usando embeddings dense."""
    
    def __init__(self):
        self.embedder = get_embedder()
        self.qdrant = QdrantStore()
        self.top_k: int = settings.DENSE_TOP_K
        self.collection = settings.QDRANT_COLLECTION
        
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Recupera documentos usando búsqueda vectorial.
        
        Args:
            query: Texto de la consulta
            top_k: Número de resultados a retornar
            filters: Filtros para la búsqueda
            
        Returns:
            Lista de documentos con sus scores
        """
        if top_k is None:
            top_k = self.top_k
            
        logger.info(f"Dense retrieval: query='{query[:50]}...', top_k={top_k}")
        
        # Generar embedding para la consulta
        query_embedding = self.embedder.encode(query)
        
        # Buscar en Qdrant
        results = self.qdrant.search(
            collection_name=self.collection,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            query_filter=filters
        )
        
        # Formatear resultados
        documents = []
        for hit in results:
            doc = {
                "id": hit.id,
                "text": hit.payload.get("texto", ""),
                "score": hit.score,
                "metadata": {
                    k: v for k, v in hit.payload.items() 
                    if k != "texto"
                }
            }
            documents.append(doc)
            
        logger.info(f"Dense retrieval: found {len(documents)} documents")
        return documents
