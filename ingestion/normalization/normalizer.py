import re
from typing import List, Optional


class LegalTextNormalizer:

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        # No destruir estructura de párrafos
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n[ \t]+', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def normalize_articles(text: str) -> str:
        # FIX 1: evitar sobre-escritura agresiva de "Art"
        text = re.sub(r'\bART\.?\s*', 'Artículo ', text, flags=re.IGNORECASE)

        text = re.sub(
            r'\bArticulo\b',
            'Artículo',
            text,
            flags=re.IGNORECASE
        )

        # FIX CRÍTICO: arreglar corrupción "Artículo ículo"
        text = re.sub(
            r'Artículo\s+ículo',
            'Artículo',
            text,
            flags=re.IGNORECASE
        )

        return text

    @staticmethod
    def normalize_norm_ids(text: str) -> str:
        text = re.sub(r'Ley\s+N[°º]?\s*\.?\s*', 'Ley N° ', text, flags=re.IGNORECASE)
        text = re.sub(r'\bD\.?\s*S\.?\b', 'Decreto Supremo', text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def remove_headers_footers(text: str) -> str:
        lines = text.splitlines()
        cleaned = []

        for line in lines:
            s = line.strip()

            if not s:
                continue

            # páginas
            if re.fullmatch(r'\d+', s):
                continue

            # "- 3 -"
            if re.fullmatch(r'-\s*\d+\s*-', s):
                continue

            cleaned.append(s)

        return '\n'.join(cleaned)

    @staticmethod
    def normalize(text: str) -> str:
        text = LegalTextNormalizer.remove_headers_footers(text)

        # orden IMPORTANTE: primero IDs, luego artículos
        text = LegalTextNormalizer.normalize_norm_ids(text)
        text = LegalTextNormalizer.normalize_articles(text)

        text = LegalTextNormalizer.normalize_whitespace(text)

        return text

    @staticmethod
    def extract_title(text: str) -> Optional[str]:
        lines = text.splitlines()

        for line in lines[:10]:
            s = line.strip()
            if 10 < len(s) < 200:
                return s

        return None

    @staticmethod
    def split_into_articles(text: str) -> List[str]:

        # FIX IMPORTANTE: más tolerante a formatos reales legales bolivianos
        pattern = re.compile(
            r'(Artículo\s+(?:\d+|Primero|Segundo|Tercero|Cuarto|Quinto))',
            flags=re.IGNORECASE
        )

        matches = list(pattern.finditer(text))

        if not matches:
            return [text.strip()]

        articles = []

        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            chunk = text[start:end].strip()

            if len(chunk) > 30:  # evita basura
                articles.append(chunk)

        return articles