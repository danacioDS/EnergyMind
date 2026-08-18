"""
Modelos de datos para el pipeline de ingesta de EnergyMind.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class Provenance(BaseModel):
    """Información de procedencia del documento."""
    source_primary: str = Field(..., description="Fuente oficial (gaceta_oficial)")
    source_discovery: str = Field(..., description="Fuente de descubrimiento (lexivox)")
    official_url: Optional[str] = Field(None, description="URL en Gaceta Oficial")
    discovery_url: Optional[str] = Field(None, description="URL en LexiVox")
    document_hash: str = Field(..., description="SHA256 del documento")
    retrieved_at: datetime = Field(default_factory=datetime.now)
    version: str = Field(default="1.0")


class LegalUnit(BaseModel):
    """Unidad legal (artículo, disposición, etc.)."""
    id: str = Field(..., description="ID único")
    documento_id: str = Field(..., description="ID del documento padre")
    tipo: str = Field(..., description="articulo, disposicion, titulo, etc.")
    numero: str = Field(..., description="Número del artículo o disposición")
    texto: str = Field(..., description="Texto completo de la unidad")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadatos específicos
    norma_id: Optional[str] = None
    subsector: Optional[str] = None
    enfoque: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    renewable_incentive: bool = False
    vigente: bool = True


class LegalDocument(BaseModel):
    """Documento legal completo."""
    id: str = Field(..., description="ID único del documento")
    norma_id: str = Field(..., description="Número de la norma")
    tipo: str = Field(..., description="Ley, Decreto Supremo, Resolución, etc.")
    titulo: str = Field(..., description="Título completo")
    fecha: Optional[str] = Field(None, description="Fecha de promulgación")
    texto: str = Field(..., description="Texto completo del documento")
    unidades: List[LegalUnit] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(..., description="Procedencia del documento")


class IngestResult(BaseModel):
    """Resultado del proceso de ingesta."""
    documents_processed: int = 0
    units_processed: int = 0
    duplicates_skipped: int = 0
    errors: List[str] = Field(default_factory=list)
    elapsed_seconds: float = 0.0
