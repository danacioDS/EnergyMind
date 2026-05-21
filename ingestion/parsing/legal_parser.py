import re
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from loguru import logger

from app.models.legal_unit import LegalUnit
from ingestion.normalization.normalizer import LegalTextNormalizer
from ingestion.metadata.extractor import extract_all_metadata, extract_articles


NORM_STRUCTURE_PATTERNS = {
    "Constitucion": {
        "article_pattern": r'Artículo\s+(\d+)',
        "title_pattern": r'Título\s+\d+',
        "chapter_pattern": r'Capítulo\s+\w+',
    },
    "Ley": {
        "article_pattern": r'Artículo\s+(\d+[°º]?(?:\s*bis|\s*ter|\s*quater)?)',
        "title_pattern": r'TÍTULO\s+\w+',
        "chapter_pattern": r'CAPÍTULO\s+\w+',
    },
    "Decreto Supremo": {
        "article_pattern": r'Artículo\s+(\d+)',
        "section_pattern": r'Sección\s+\w+',
    },
    "Resolucion": {
        "article_pattern": r'Artículo\s+(?:Primero|Segundo|Tercero|Cuarto|Quinto|\d+)',
        "section_pattern": r'RESUELVE|CONSIDERANDO|VISTOS',
    },
}


class LegalDocumentParser:
    def __init__(self, normalizer: Optional[LegalTextNormalizer] = None):
        self.normalizer = normalizer or LegalTextNormalizer()

    def parse_text(self, text: str, tipo_norma: Optional[str] = None,
                   norma_id: Optional[str] = None, metadata_override: Optional[Dict[str, Any]] = None) -> List[LegalUnit]:
        normalized = self.normalizer.normalize(text)
        articles = self.normalizer.split_into_articles(normalized)
        if not articles:
            articles = [normalized]

        units: List[LegalUnit] = []
        for i, article_text in enumerate(articles):
            base_meta = metadata_override or extract_all_metadata(article_text, tipo_norma)
            article_refs = extract_articles(article_text)
            articulo = article_refs[0] if article_refs else str(i + 1)

            unit_id = f"{base_meta['tipo_norma']}_{base_meta.get('norma_id', 'unknown')}_art_{articulo}_{i}"
            unit_id = re.sub(r'\s+', '_', unit_id).replace('°', '').replace('º', '')

            if metadata_override:
                risk_flags = metadata_override.get("risk_flags", [])
                renewable_incentive = metadata_override.get("renewable_incentive", False)
            else:
                risk_flags = extract_all_metadata(article_text).get("risk_flags", [])
                renewable_incentive = "Renewable Incentive" in risk_flags

            unit = LegalUnit(
                id=unit_id,
                tipo_norma=base_meta["tipo_norma"],
                norma_id=base_meta.get("norma_id") or norma_id or str(i + 1),
                articulo=articulo,
                tema=base_meta.get("tema", ""),
                vigente=base_meta.get("vigente", True),
                sector=base_meta.get("sector", "Energia"),
                subsector=base_meta.get("subsector", "General"),
                enfoque=base_meta.get("enfoque", "General"),
                risk_flags=risk_flags,
                renewable_incentive=renewable_incentive,
                texto=article_text,
            )
            units.append(unit)

        return units

    def parse_file(self, filepath: Path, tipo_norma: Optional[str] = None,
                   norma_id: Optional[str] = None) -> List[LegalUnit]:
        logger.info(f"Parsing file: {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        return self.parse_text(text, tipo_norma, norma_id)

    def to_json(self, units: List[LegalUnit], output_path: Path) -> None:
        data = [unit.model_dump() for unit in units]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(units)} units to {output_path}")
