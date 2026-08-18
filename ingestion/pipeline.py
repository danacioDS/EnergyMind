from pathlib import Path
from typing import List
from loguru import logger

from app.ingestion.models import LegalUnit
from app.config import settings
from ingestion.parsing.legal_parser import LegalDocumentParser
from ingestion.normalization.normalizer import LegalTextNormalizer
from vectorstore.qdrant_client import QdrantStore


CORPUS_DEFINITIONS = [
    {
        "file": "constitucion_bolivia_articulos_seleccionados.txt",
        "tipo_norma": "Constitucion",
        "norma_id": "CPE",
        "metadata": {
            "subsector": "General",
            "enfoque": "Regulacion",
            "risk_flags": ["Constitutional Hierarchy"],
        },
    },
    {
        "file": "ley_1604_1994.txt",
        "tipo_norma": "Ley",
        "norma_id": "1604",
        "metadata": {
            "tema": "Ley de Electricidad",
            "subsector": "General",
            "enfoque": "Regulacion",
            "risk_flags": ["Market Framework"],
            "vigente": True,
        },
    },
    {
        "file": "ley_943_modificaciones.txt",
        "tipo_norma": "Ley",
        "norma_id": "943",
        "metadata": {
            "tema": "Modificaciones a Ley de Electricidad",
            "subsector": "General",
            "enfoque": "Regulacion",
        },
    },
    {
        "file": "ds_5503_2025.txt",
        "tipo_norma": "Decreto Supremo",
        "norma_id": "5503",
        "metadata": {
            "tema": "Regimen Extraordinario de Inversiones",
            "subsector": "General",
            "enfoque": "Inversion",
            "risk_flags": ["Regulatory Instability", "Nationalization Risk"],
        },
    },
]


class IngestionPipeline:
    def __init__(self):
        self.parser = LegalDocumentParser(
            normalizer=LegalTextNormalizer()
        )

        self.raw_path = Path(settings.corpus_raw_path)
        self.processed_path = Path(settings.corpus_processed_path)
        self.normalized_path = Path(settings.corpus_normalized_path)

        for p in [self.raw_path, self.processed_path, self.normalized_path]:
            p.mkdir(parents=True, exist_ok=True)

    def process_raw_files(self) -> List[LegalUnit]:
        all_units: List[LegalUnit] = []

        for definition in CORPUS_DEFINITIONS:
            filepath = self.raw_path / definition["file"]

            if not filepath.exists():
                logger.warning(f"Raw file not found: {filepath}")
                continue

            units = self.parser.parse_file(
                filepath=filepath,
                tipo_norma=definition["tipo_norma"],
                norma_id=definition["norma_id"],
            )

            metadata_override = definition.get("metadata", {})
            if metadata_override:
                for unit in units:
                    for key, value in metadata_override.items():
                        if hasattr(unit, key):
                            setattr(unit, key, value)

            all_units.extend(units)
            logger.info(f"Processed {filepath}: {len(units)} legal units")

        normalized_path = self.normalized_path / "all_units.json"
        self.parser.to_json(all_units, normalized_path)

        return all_units

    def index_to_qdrant(self, units: List[LegalUnit]) -> int:
        # ✅ FIX: fully synchronous usage
        store = QdrantStore()

        store.initialize()  # MUST be sync (no await anywhere)

        try:
            count = store.upsert_units(units)
        finally:
            store.close()

        logger.info(f"Indexed {count} units to Qdrant")

        return count

    def run(self) -> int:
        logger.info("Starting ingestion pipeline")

        units = self.process_raw_files()

        if not units:
            logger.error("No units to index")
            return 0

        count = self.index_to_qdrant(units)

        logger.info(f"Ingestion pipeline complete: {count} units indexed")

        return count


def run_ingestion():
    pipeline = IngestionPipeline()
    return pipeline.run()
