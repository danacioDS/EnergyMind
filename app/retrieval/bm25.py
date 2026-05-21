from typing import List, Optional, Dict, Any
from loguru import logger
import jieba
from rank_bm25 import BM25Okapi

from app.config import settings


class BM25Retriever:
    def __init__(self):
        self.index: Optional[BM25Okapi] = None
        self.documents: List[Dict[str, Any]] = []
        self.tokenized_corpus: List[List[str]] = []

    def _tokenize(self, text: str) -> List[str]:
        try:
            return list(jieba.cut(text))
        except ImportError:
            return text.lower().split()

    def build_index(self, documents: List[Dict[str, Any]]):
        self.documents = documents
        self.tokenized_corpus = [
            self._tokenize(d.get("texto", "")) for d in documents
        ]
        self.index = BM25Okapi(self.tokenized_corpus)
        logger.info(f"Built BM25 index with {len(documents)} documents")

    async def search(self, query: str, top_k: int = settings.bm25_top_k) -> List[Dict[str, Any]]:
        if not self.index:
            logger.warning("BM25 index not built")
            return []

        tokenized_query = self._tokenize(query)
        scores = self.index.get_scores(tokenized_query)

        scored = list(zip(self.documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored[:top_k]:
            results.append({**doc, "bm25_score": float(score)})

        return results
