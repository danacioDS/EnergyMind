"""
Adaptador base para fuentes de documentos legales.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from loguru import logger


class LegalSourceAdapter(ABC):
    """Interfaz base para adaptadores de fuentes legales."""
    
    @abstractmethod
    async def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        """Buscar documentos en la fuente."""
        pass
    
    @abstractmethod
    async def fetch(self, document_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Obtener un documento específico."""
        pass
    
    @abstractmethod
    async def list_documents(self, **kwargs) -> List[Dict[str, Any]]:
        """Listar documentos disponibles."""
        pass
    
    @abstractmethod
    async def get_metadata(self, document_id: str) -> Dict[str, Any]:
        """Obtener metadatos de un documento."""
        pass
    
    def normalize_text(self, text: str) -> str:
        """Normalizar texto."""
        if not text:
            return ""
        # Eliminar espacios múltiples
        import re
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
