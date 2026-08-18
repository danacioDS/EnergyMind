import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.ingestion.models import LegalUnit
from ingestion.metadata.extractor import extract_all_metadata
from ingestion.normalization.normalizer import LegalTextNormalizer


# =========================================================
# PATTERNS
# =========================================================

NORM_STRUCTURE_PATTERNS = {
    "Constitucion": {
        "article_pattern": r"(Artículo\s+\d+)",
    },
    "Ley": {
        "article_pattern": r"(Artículo\s+\d+[°º]?(?:\s*(?:bis|ter|quater))?)",
    },
    "Decreto Supremo": {
        "article_pattern": r"(Artículo\s+\d+)",
    },
    "Resolucion": {
        "article_pattern": r"(Artículo\s+(?:Primero|Segundo|Tercero|Cuarto|Quinto|\d+))",
    },
}


# =========================================================
# PARSER
# =========================================================

class LegalDocumentParser:

    def __init__(self, normalizer: Optional[LegalTextNormalizer] = None):
        self.normalizer = normalizer or LegalTextNormalizer()

    # -----------------------------------------------------
    # MAIN
    # -----------------------------------------------------

    def parse_text(
        self,
        text: str,
        tipo_norma: Optional[str] = None,
        norma_id: Optional[str] = None,
        metadata_override: Optional[Dict[str, Any]] = None,
    ) -> List[LegalUnit]:

        normalized = self.normalizer.normalize(text)

        tipo = tipo_norma or self._detect_norm_type(normalized)

        articles = self._split_legal_units(normalized, tipo)

        if not articles:
            logger.warning("No legal units detected → fallback full document")
            articles = [normalized]

        logger.info(f"Detected {len(articles)} legal articles")

        units: List[LegalUnit] = []

        for idx, article_text in enumerate(articles):

            meta = (
                metadata_override.copy()
                if metadata_override
                else extract_all_metadata(article_text, tipo)
            )

            articulo = self._extract_article_number(article_text, idx)

            unit_id = f"{tipo}_{meta.get('norma_id', norma_id or 'unknown')}_art_{articulo}"
            unit_id = re.sub(r"\s+", "_", unit_id).replace("°", "").replace("º", "")

            risk_flags = meta.get("risk_flags", []) or []

            unit = LegalUnit(
                id=unit_id,
                tipo_norma=meta.get("tipo_norma", tipo),
                norma_id=meta.get("norma_id", norma_id or "unknown"),
                articulo=articulo,
                tema=meta.get("tema", ""),
                vigente=meta.get("vigente", True),
                sector=meta.get("sector", "Energia"),
                subsector=meta.get("subsector", "General"),
                enfoque=meta.get("enfoque", "General"),
                risk_flags=risk_flags,
                renewable_incentive=meta.get("renewable_incentive", False),
                texto=article_text.strip(),
            )

            units.append(unit)

        logger.info(f"Generated {len(units)} legal units")

        return units

    # -----------------------------------------------------
    # FILE
    # -----------------------------------------------------

    def parse_file(
        self,
        filepath: Path,
        tipo_norma: Optional[str] = None,
        norma_id: Optional[str] = None,
    ) -> List[LegalUnit]:

        logger.info(f"Parsing file: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        return self.parse_text(text, tipo_norma, norma_id)

    # -----------------------------------------------------
    # SPLIT ARTICLES (FIX REAL)
    # -----------------------------------------------------

    def _split_legal_units(self, text: str, tipo_norma: str) -> List[str]:

        pattern = NORM_STRUCTURE_PATTERNS.get(tipo_norma, {}).get(
            "article_pattern",
            r"(Artículo\s+\d+)",
        )

        matches = list(re.finditer(pattern, text, flags=re.IGNORECASE))

        if not matches:
            return []

        chunks = []

        for i, match in enumerate(matches):

            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)

            chunk = text[start:end].strip()

            if len(chunk) > 20:
                chunks.append(chunk)

        return chunks

    # -----------------------------------------------------
    # ARTICLE NUMBER
    # -----------------------------------------------------

    def _extract_article_number(self, text: str, idx: int) -> str:

        match = re.search(
            r"Artículo\s+(\d+[°º]?(?:\s*(?:bis|ter|quater))?)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(1).replace("°", "").replace("º", "").strip()

        return str(idx + 1)

    # -----------------------------------------------------
    # TYPE DETECTION
    # -----------------------------------------------------

    def _detect_norm_type(self, text: str) -> str:

        t = text.lower()

        if "constitución" in t or "constitucion" in t:
            return "Constitucion"

        if "decreto supremo" in t:
            return "Decreto Supremo"

        if "resolución" in t or "resolucion" in t:
            return "Resolucion"

        return "Ley"

    # -----------------------------------------------------
    # JSON EXPORT (FIX IMPORTANT)
    # -----------------------------------------------------

    def to_json(self, units: List[LegalUnit], output_path: Path) -> None:

        # 🔥 FIX CLAVE: evitar datetime crash
        data = [u.model_dump(mode="json") for u in units]

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved {len(units)} legal units to {output_path}")