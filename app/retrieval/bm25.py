import pickle
from pathlib import Path
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

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "index": self.index,
                "documents": self.documents,
                "tokenized_corpus": self.tokenized_corpus,
            }, f)
        logger.info(f"BM25 index saved to {path}")

    def load(self, path: Path) -> bool:
        if not path.exists():
            logger.info(f"No persisted BM25 index at {path}")
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.index = data["index"]
        self.documents = data["documents"]
        self.tokenized_corpus = data["tokenized_corpus"]
        logger.info(f"BM25 index loaded from {path} ({len(self.documents)} docs)")
        return True

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
