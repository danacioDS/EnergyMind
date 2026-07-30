import re
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
from loguru import logger
from rank_bm25 import BM25Okapi
from app.config import settings


class BM25Retriever:
    def __init__(self):
        self.index: Optional[BM25Okapi] = None
        self.documents: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []

    def _tokenize_spanish(self, text: str) -> List[str]:
        """
        Tokenización específica para español legal.
        Incluye stopwords legales y términos jurídicos.
        """
        if not text:
            return []
        
        # 1. Limpiar y normalizar
        text = text.lower()
        # Eliminar caracteres especiales pero mantener letras, números y guiones
        text = re.sub(r'[^\w\sáéíóúñü.-]', ' ', text)
        # Normalizar espacios
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 2. Tokenizar por espacios
        tokens = text.split()
        
        # 3. Eliminar stopwords (incluyendo términos legales comunes)
        stopwords = {
            # Artículos
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
            # Preposiciones
            'de', 'del', 'en', 'por', 'para', 'con', 'sin', 'sobre', 'entre', 
            'hasta', 'desde', 'durante', 'según', 'mediante', 'contra',
            # Conjunciones
            'y', 'o', 'u', 'ni', 'que', 'quien', 'cual', 'cuyo', 'donde',
            'cuando', 'como', 'porque', 'pues', 'aunque', 'si', 'sino',
            # Adverbios
            'más', 'menos', 'muy', 'tan', 'tanto', 'bien', 'mal', 'así',
            'también', 'tampoco', 'sí', 'no', 'ya', 'aún', 'todavía',
            # Verbos comunes
            'ser', 'estar', 'haber', 'tener', 'hacer', 'decir', 'ver', 'dar',
            'saber', 'poder', 'querer', 'deber', 'ir', 'venir', 'llevar',
            'dejar', 'seguir', 'encontrar', 'llamar', 'pasar', 'quedar',
            # Términos legales comunes (stopwords)
            'artículo', 'art', 'num', 'número', 'inciso', 'párrafo', 'literal',
            'título', 'capítulo', 'sección', 'norma', 'reglamento', 'decreto',
            'ley', 'código', 'constitución', 'sentencia', 'resolución',
            'reglamentación', 'disposición', 'establece', 'determina',
            'considerando', 'visto', 'teniendo', 'presente', 'acuerdo',
            'declara', 'modifica', 'deroga', 'abroga', 'sustituye',
            'adicional', 'transitorio', 'final', 'vigencia', 'publicación',
            'consecuencia', 'efecto', 'regula', 'aplica', 'deberá', 'será',
            'podrá', 'tendrá', 'facultad', 'competencia', 'atribución',
        }
        
        tokens = [t for t in tokens if t not in stopwords and len(t) > 2]
        
        # 4. Opcional: stemmming básico para términos legales
        # Conservamos términos con números (artículos, leyes)
        tokens = [t for t in tokens if not re.match(r'^\d+$', t)]
        
        return tokens

    def build_index(self, documents: List[Dict[str, Any]]) -> None:
        """Construye el índice BM25 a partir de documentos"""
        self.documents = documents
        self.tokenized_corpus = []
        
        for doc in documents:
            text = doc.get("texto", doc.get("payload", {}).get("texto", ""))
            tokens = self._tokenize_spanish(text)
            self.tokenized_corpus.append(tokens)
        
        if self.tokenized_corpus:
            self.index = BM25Okapi(self.tokenized_corpus)
            logger.info(f"Built BM25 index with {len(documents)} documents (Spanish tokenizer)")
        else:
            logger.warning("No documents to build BM25 index")

    def search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Busca documentos relevantes usando BM25"""
        if not self.index or not self.documents:
            logger.warning("BM25 index not built or empty")
            return []
        
        tokenized_query = self._tokenize_spanish(query)
        if not tokenized_query:
            logger.warning("Query tokenized to empty")
            return []
        
        # Obtener scores
        scores = self.index.get_scores(tokenized_query)
        
        # Obtener índices de los mejores resultados
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]
        
        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                result = self.documents[idx].copy()
                result["bm25_score"] = float(scores[idx])
                results.append(result)
        
        logger.info(f"BM25 found {len(results)} results for query: {query[:50]}...")
        return results

    def save(self, path: Path) -> None:
        """Guarda el índice BM25 en disco"""
        if self.index is None:
            logger.warning("Cannot save: index not built")
            return
        
        data = {
            "documents": self.documents,
            "tokenized_corpus": self.tokenized_corpus,
            "index": self.index,
        }
        
        with open(path, "wb") as f:
            pickle.dump(data, f)
        
        logger.info(f"BM25 index saved to {path}")

    def load(self, path: Path) -> bool:
        """Carga el índice BM25 desde disco"""
        if not path.exists():
            logger.info(f"No persisted BM25 index at {path}")
            return False
        
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
            
            self.documents = data["documents"]
            self.tokenized_corpus = data["tokenized_corpus"]
            self.index = data["index"]
            
            logger.info(f"BM25 index loaded from {path} ({len(self.documents)} docs)")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load BM25 index: {e}")
            return False
