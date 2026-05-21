import re
from typing import List, Optional, Dict, Any


RISK_FLAG_MAPPINGS: Dict[str, List[str]] = {
    "constitutional_conflict": {
        "keywords": ["conflicto constitucional", "inconstitucional", "tribunal constitucional",
                      "control de constitucionalidad", "artículo 410", "jerarquía constitucional",
                      "prevalencia constitucional", "conflicto de competencias"],
        "entities": ["CPE", "Constitución Política del Estado", "Artículo 410"],
    },
    "nationalization_risk": {
        "keywords": ["nacionalización", "expropiación", "estatización", "reserva del estado",
                      "sector estratégico", "control estatal", "propiedad del estado",
                      "reversión", "dominio originario"],
    },
    "regulatory_instability": {
        "keywords": ["modificación", "derogación", "abrogación", "sustitución", "cambio normativo",
                      "inestabilidad jurídica", "inseguridad jurídica", "nueva regulación",
                      "modificatoria", "transitorio", "disposición final"],
    },
    "legal_ambiguity": {
        "keywords": ["interpretación", "ambigüedad", "vacío legal", "laguna jurídica",
                      "discrecionalidad", "reglamentación pendiente", "falta de reglamentación",
                      "pendiente de reglamentación"],
    },
    "renewable_incentive": {
        "keywords": ["incentivo", "beneficio tributario", "exención", "subvención",
                      "tarifa preferencial", "crédito fiscal", "depreciación acelerada",
                      "arancel cero", "exención arancelaria", "fomento", "promoción",
                      "energía renovable", "energía limpia", "generación distribuida",
                      "autoproducción", "biomasa", "solar", "eólica", "hidroeléctrica",
                      "fuente renovable", "energía alternativa"],
    },
    "arbitration_protection": {
        "keywords": ["arbitraje", "arbitraje internacional", "CIADI", "tribunal arbitral",
                      "protección de inversiones", "garantía de inversión", "tratado bilateral",
                      "API", "promoción de inversiones", "cláusula arbitral", "solución de controversias",
                      "inversión extranjera", "protección al inversor"],
    },
    "private_investment": {
        "keywords": ["inversión privada", "iniciativa privada", "concesión", "licencia",
                      "permiso", "autorización", "contrato de riesgo compartido",
                      "asociación público-privada", "APP", "capital privado",
                      "inversionista", "inversión extranjera", "libre competencia"],
    },
}


SUBSECTOR_KEYWORDS: Dict[str, List[str]] = {
    "Solar": ["solar", "fotovoltaico", "radiación solar", "panel solar", "planta solar",
              "energía solar", "parque solar", "generación solar fotovoltaica"],
    "Eolica": ["eólica", "eólico", "viento", "aerogenerador", "parque eólico", "energía eólica"],
    "Biomasa": ["biomasa", "biogás", "biocombustible", "residuos orgánicos", "biomasa forestal"],
    "Hidroelectrica": ["hidroeléctrica", "hidroeléctrico", "hidráulica", "central hidroeléctrica",
                       "represa", "embalse", "mini hidroeléctrica", "pch", "pequeña central hidroeléctrica"],
    "General": ["generación", "electricidad", "energía", "energético", "fuente de energía",
                "distribución eléctrica", "transmisión", "interconexión"],
}


ENFOQUE_KEYWORDS: Dict[str, List[str]] = {
    "Inversion": ["inversión", "inversionista", "capital", "inversión extranjera", "inversión privada",
                   "proyecto de inversión", "financiamiento", "presupuesto", "recursos económicos"],
    "Generacion": ["generación", "generador", "planta de generación", "capacidad instalada",
                    "producción de energía", "generación eléctrica", "autoproductor"],
    "Interconexion": ["interconexión", "conexión", "red eléctrica", "sistema interconectado",
                       "punto de conexión", "acceso a red", "transmisión eléctrica",
                       "línea de transmisión"],
    "Regulacion": ["regulación", "reglamento", "norma técnica", "procedimiento", "autorización",
                    "licencia", "permiso", "registro", "habilitación"],
    "Tributario": ["tributo", "impuesto", "tasa", "contribución", "exención tributaria",
                    "beneficio fiscal", "IVA", "IT", "IUE", "ICE", "gravamen"],
}


NORM_TYPE_MAPPING = {
    "Ley": ["Ley", "Ley de", "Ley N°", "Ley Nro"],
    "Decreto Supremo": ["DS", "Decreto Supremo", "D.S."],
    "Constitucion": ["Constitución", "CPE", "Constitución Política del Estado"],
    "Resolucion": ["Resolución", "Resolución Administrativa", "RA", "R.A."],
    "Decreto": ["Decreto", "Decreto Presidencial", "Decreto Reglamentario"],
}


def extract_risk_flags(text: str) -> List[str]:
    flags: List[str] = []
    text_lower = text.lower()
    for flag_name, config in RISK_FLAG_MAPPINGS.items():
        keywords = config.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in text_lower:
                display_name = " ".join(w.capitalize() for w in flag_name.split("_"))
                if display_name not in flags:
                    flags.append(display_name)
                break
    return flags


def extract_subsector(text: str) -> str:
    text_lower = text.lower()
    for subsector, keywords in SUBSECTOR_KEYWORDS.items():
        if subsector == "General":
            continue
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return subsector
    return "General"


def extract_enfoque(text: str) -> str:
    text_lower = text.lower()
    scores: Dict[str, int] = {}
    for enfoque, keywords in ENFOQUE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            scores[enfoque] = score
    if not scores:
        return "General"
    return max(scores, key=scores.get)


def extract_norm_type(text: str) -> str:
    for norm_type, patterns in NORM_TYPE_MAPPING.items():
        for pattern in patterns:
            if pattern.lower() in text.lower():
                return norm_type
    return "Unknown"


def extract_norm_id(text: str) -> Optional[str]:
    patterns = [
        r"(?:Ley\s*(?:N°|Nro|Número|)\s*)(\d{3,4})",
        r"(?:DS|D\.S\.|Decreto Supremo)\s*(?:N°|Nro|Número|)\s*(\d{3,4})",
        r"(?:Resolución|RA|R\.A\.)\s*(?:N°|Nro|Número|)\s*(\d{3,4})",
        r"(?:Artículo|Articulo)\s*(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def extract_articles(text: str) -> List[str]:
    article_refs = re.findall(r"Artículo\s*(\d+[°º]?(?:\s*bis|\s*ter|\s*quater)?)", text, re.IGNORECASE)
    return list(set(a.strip() for a in article_refs))


def detect_renewable_incentive(text: str) -> bool:
    text_lower = text.lower()
    incentive_kw = RISK_FLAG_MAPPINGS.get("renewable_incentive", {}).get("keywords", [])
    return any(kw.lower() in text_lower for kw in incentive_kw)


def extract_all_metadata(text: str, tipo_norma: Optional[str] = None) -> Dict[str, Any]:
    return {
        "tipo_norma": tipo_norma or extract_norm_type(text),
        "norma_id": extract_norm_id(text) or "",
        "articulo": "",
        "tema": "",
        "vigente": True,
        "sector": "Energia",
        "subsector": extract_subsector(text),
        "enfoque": extract_enfoque(text),
        "risk_flags": extract_risk_flags(text),
        "renewable_incentive": detect_renewable_incentive(text),
    }
