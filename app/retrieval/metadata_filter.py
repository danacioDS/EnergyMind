from typing import Optional, Dict, Any
from loguru import logger


class MetadataFilter:
    QUERY_TO_METADATA_MAP = {
        "solar": {"subsector": "Solar"},
        "fotovoltaico": {"subsector": "Solar"},
        "photovoltaic": {"subsector": "Solar"},
        "eólico": {"subsector": "Eolica"},
        "eolica": {"subsector": "Eolica"},
        "wind": {"subsector": "Eolica"},
        "biomasa": {"subsector": "Biomasa"},
        "biomass": {"subsector": "Biomasa"},
        "hidroeléctrica": {"subsector": "Hidroelectrica"},
        "hidroelectrica": {"subsector": "Hidroelectrica"},
        "hydroelectric": {"subsector": "Hidroelectrica"},
        "generación distribuida": {"enfoque": "Generacion"},
        "distributed generation": {"enfoque": "Generacion"},
        "autoproducción": {"enfoque": "Generacion"},
        "self-production": {"enfoque": "Generacion"},
        "interconexión": {"enfoque": "Interconexion"},
        "interconnection": {"enfoque": "Interconexion"},
        "inversión": {"enfoque": "Inversion"},
        "investment": {"enfoque": "Inversion"},
        "incentivo": {"renewable_incentive": True},
        "incentive": {"renewable_incentive": True},
        "tributo": {"enfoque": "Tributario"},
        "tax": {"enfoque": "Tributario"},
        "impuesto": {"enfoque": "Tributario"},
        "constitucional": {"tipo_norma": "Constitucion"},
        "constitutional": {"tipo_norma": "Constitucion"},
        "ley 1604": {"norma_id": "1604"},
        "ley de electricidad": {"norma_id": "1604"},
        "ds 5503": {"norma_id": "5503"},
        "decreto 5503": {"norma_id": "5503"},
    }

    @staticmethod
    def infer_from_query(query: str, explicit_filter: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata_filter: Dict[str, Any] = {}
        query_lower = query.lower()

        metadata_filter["vigente"] = True

        for keyword, mapping in MetadataFilter.QUERY_TO_METADATA_MAP.items():
            if keyword in query_lower:
                metadata_filter.update(mapping)

        if explicit_filter:
            metadata_filter.update(explicit_filter)

        logger.debug(f"Inferred metadata filter: {metadata_filter}")
        return metadata_filter

    @staticmethod
    def build_qdrant_filter(metadata_filter: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in metadata_filter.items() if v is not None}
