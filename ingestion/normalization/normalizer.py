import re
from typing import List, Optional
from app.models.legal_unit import LegalUnit


class LegalTextNormalizer:
    @staticmethod
    def normalize_whitespace(text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @staticmethod
    def normalize_articles(text: str) -> str:
        text = re.sub(r'Art[°º]?\s*\.?\s*', 'Artículo ', text, flags=re.IGNORECASE)
        text = re.sub(r'Articulo\s+', 'Artículo ', text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def normalize_norm_ids(text: str) -> str:
        text = re.sub(r'Ley\s+N[°º]?\s*\.?\s*', 'Ley N° ', text, flags=re.IGNORECASE)
        text = re.sub(r'D\.?S\.?\s*\.?\s*', 'Decreto Supremo ', text, flags=re.IGNORECASE)
        text = re.sub(r'Ley\s+de\s+', 'Ley de ', text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def remove_headers_footers(text: str) -> str:
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r'^\d+\s*$', stripped):
                continue
            if re.match(r'^-\s*\d+\s*-$', stripped):
                continue
            cleaned.append(stripped)
        return '\n'.join(cleaned)

    @staticmethod
    def normalize(text: str) -> str:
        text = LegalTextNormalizer.remove_headers_footers(text)
        text = LegalTextNormalizer.normalize_articles(text)
        text = LegalTextNormalizer.normalize_norm_ids(text)
        text = LegalTextNormalizer.normalize_whitespace(text)
        return text

    @staticmethod
    def extract_title(text: str) -> Optional[str]:
        lines = text.strip().split('\n')
        for line in lines[:5]:
            stripped = line.strip()
            if stripped and len(stripped) > 10 and len(stripped) < 200:
                return stripped
        return None

    @staticmethod
    def split_into_articles(text: str) -> List[str]:
        article_pattern = r'(Artículo\s+\d+[°º]?(?:\s*bis|\s*ter|\s*quater)?[\.\s])'
        parts = re.split(article_pattern, text, flags=re.IGNORECASE)
        if len(parts) <= 1:
            return [text.strip()]
        articles: List[str] = []
        for i in range(1, len(parts), 2):
            article_header = parts[i].strip()
            article_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            articles.append(f"{article_header} {article_body}".strip())
        return articles
