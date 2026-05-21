import re
from typing import List, Tuple, Optional


class RegexLegalParser:
    BOLIVIAN_LAW_PATTERNS = {
        "law_number": r'(?:Ley\s+(?:N[°º]?\s*)?)(\d{3,4}(?:/\d{4})?)',
        "decree_number": r'(?:DS|D\.S\.|Decreto\s+Supremo\s+(?:N[°º]?\s*)?)(\d{3,4}(?:/\d{4})?)',
        "resolution_number": r'(?:Resolución\s+(?:Administrativa\s+)?(?:N[°º]?\s*)?)(\d{3,4})',
        "article_ref": r'(?:Artículo|Art\.?|Articulo)\s+(\d+[°º]?(?:\s*bis|\s*ter|\s*quater)?)',
        "paragraph_ref": r'(?:Parágrafo|Párrafo|Parrafo)\s+(\d+)',
        "section_ref": r'(?:Sección|Seccion)\s+(\w+)',
        "chapter_ref": r'(?:Capítulo|Capitulo)\s+(\w+)',
        "title_ref": r'(?:Título|Titulo)\s+(\w+)',
    }

    LEGAL_STRUCTURE_MARKERS = {
        "articulo": r'^Artículo\s+\d+',
        "capitulo": r'^CAPÍTULO\s+\w+',
        "titulo": r'^TÍTULO\s+\w+',
        "disposicion": r'^Disposición\s+(?:Transitoria|Final|Adicional|Derogatoria|Abrogatoria)',
        "considerando": r'^CONSIDERANDO',
        "vistos": r'^VISTOS',
        "resuelve": r'^RESUELVE',
    }

    @staticmethod
    def extract_norm_references(text: str) -> List[Tuple[str, str]]:
        references: List[Tuple[str, str]] = []
        for ref_type, pattern in RegexLegalParser.BOLIVIAN_LAW_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                references.append((ref_type, match.strip()))
        return references

    @staticmethod
    def find_ideological_markers(text: str) -> dict:
        markers = {
            "liberal_market": bool(re.search(
                r'(libre mercado|libre competencia|iniciativa privada|inversión privada|'
                r'concesión|licencia|permiso|desregulación|privatización)', text, re.IGNORECASE
            )),
            "state_control": bool(re.search(
                r'(sector estratégico|control estatal|reserva del estado|monopolio estatal|'
                r'nacionalización|soberanía|dominio originario|planificación central)', text, re.IGNORECASE
            )),
            "mixed": bool(re.search(
                r'(participación mixta|público-privada|cooperación|concertación|'
                r'concertación social|desarrollo conjunto)', text, re.IGNORECASE
            )),
        }
        return markers

    @staticmethod
    def classify_ideological_framework(text: str) -> str:
        markers = RegexLegalParser.find_ideological_markers(text)
        liberal_score = 1 if markers["liberal_market"] else 0
        state_score = 1 if markers["state_control"] else 0
        mixed_score = 1 if markers["mixed"] else 0

        if mixed_score:
            return "Mixed"
        if liberal_score and state_score:
            return "Mixed"
        if liberal_score:
            return "Market-Oriented"
        if state_score:
            return "State-Controlled"
        return "Undefined"

    @staticmethod
    def detect_constitutional_hierarchy_mentions(text: str) -> bool:
        return bool(re.search(
            r'(artículo\s+410|jerarquía\s+(?:constitucional|normativa)|'
            r'bloque\s+de\s+constitucionalidad|prevalencia\s+constitucional)', text, re.IGNORECASE
        ))

    @staticmethod
    def extract_normative_period(text: str) -> Optional[Tuple[str, str]]:
        date_patterns = [
            r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',
            r'(\d{4})[/-](\d{2})[/-](\d{2})',
            r'(\d{2})[/-](\d{2})[/-](\d{4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                return (match.group(0), "date")
        return None

    @staticmethod
    def segment_by_structure(text: str) -> List[Tuple[str, str]]:
        segments: List[Tuple[str, str]] = []
        lines = text.split('\n')
        current_section: Optional[str] = None
        current_content: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            matched = False
            for section_type, section_pattern in RegexLegalParser.LEGAL_STRUCTURE_MARKERS.items():
                if re.match(section_pattern, stripped, re.IGNORECASE):
                    if current_section and current_content:
                        segments.append((current_section, '\n'.join(current_content).strip()))
                    current_section = section_type
                    current_content = [stripped]
                    matched = True
                    break

            if not matched:
                current_content.append(stripped)

        if current_section and current_content:
            segments.append((current_section, '\n'.join(current_content).strip()))

        return segments
