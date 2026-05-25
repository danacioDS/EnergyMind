from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class LegalUnit(BaseModel):
    id: str = Field(description="Unique legal unit identifier")
    tipo_norma: str = Field(description="Type of legal norm (Ley, Decreto, Resolucion, Constitucion)")
    norma_id: str = Field(description="Norm identifier (e.g., 1604, 5503)")
    articulo: str = Field(description="Article or section number")
    tema: str = Field(description="Main topic/subject")
    vigente: bool = Field(default=True, description="Whether the norm is currently in force")
    sector: str = Field(default="Energia", description="Economic sector")
    subsector: str = Field(description="Energy subsector (Solar, Eolica, Biomasa, General)")
    enfoque: str = Field(description="Regulatory focus (Inversion, Generacion, Interconexion)")
    risk_flags: List[str] = Field(default_factory=list, description="Legal risk flags detected")
    renewable_incentive: bool = Field(default=False, description="Whether this unit contains renewable incentives")
    texto: str = Field(description="Full legal text content")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LegalUnitCreate(BaseModel):
    tipo_norma: str
    norma_id: str
    articulo: str
    tema: str
    vigente: bool = True
    sector: str = "Energia"
    subsector: str
    enfoque: str
    risk_flags: List[str] = []
    renewable_incentive: bool = False
    texto: str


class LegalUnitResponse(LegalUnit):
    class Config:
        from_attributes = True
