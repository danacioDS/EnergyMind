from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    question: str = Field(..., description="Legal question about renewable energy investments in Bolivia")
    subsector: Optional[str] = Field(default=None, description="Filter by subsector: Solar, Eolica, Biomasa, Hidroelectrica")
    tipo_norma: Optional[str] = Field(default=None, description="Filter by norm type")
    vigente: Optional[bool] = Field(default=None, description="Filter by validity")
    top_k: Optional[int] = Field(default=5, description="Number of results to return")
    use_agent: Optional[bool] = Field(default=False, description="Use LangGraph agent with refinement loop")


class RiskMatrix(BaseModel):
    ideological_framework: str = "Mixed"
    constitutional_conflict_risk: str = "Medium"
    nationalization_risk: str = "Medium"
    regulatory_instability: str = "Medium"
    legal_ambiguity: str = "Medium"
    arbitration_protection: str = "Limited"


class IncentiveInfo(BaseModel):
    detected: bool = False
    type: Optional[str] = None
    articles: List[str] = Field(default_factory=list)
    description: Optional[str] = None


class LegalCitation(BaseModel):
    norma: str = Field(description="Norm identifier")
    articulo: str = Field(description="Article number")
    texto: str = Field(description="Cited text")
    tipo_norma: str = Field(description="Type of norm")
    risk_flags: List[str] = Field(default_factory=list, description="Risk flags on this citation")


class RegulatoryAnalysis(BaseModel):
    direct_conclusion: str = Field(description="Direct answer to the question")
    regulatory_analysis: str = Field(description="Detailed regulatory analysis")
    legal_citations: List[LegalCitation] = Field(default_factory=list, description="Cited legal texts")
    risk_matrix: RiskMatrix = Field(default_factory=RiskMatrix, description="Risk assessment matrix")
    incentives_detected: IncentiveInfo = Field(default_factory=IncentiveInfo, description="Detected incentives")
    insufficient_context: bool = Field(default=False, description="Whether the corpus had insufficient information")


class StructuredLegalResponse(BaseModel):
    direct_conclusion: str = Field(description="Direct 2-3 sentence answer citing specific articles")
    regulatory_analysis: str = Field(description="Detailed 3-5 paragraph regulatory analysis with citations")
    risk_matrix: RiskMatrix = Field(description="Risk assessment matrix")
    incentives: IncentiveInfo = Field(description="Detected renewable energy incentives")
    insufficient_context: bool = False


class QueryResponse(BaseModel):
    question: str = Field(description="Original question")
    answer: RegulatoryAnalysis = Field(description="Structured regulatory analysis")
    sources: List[str] = Field(default_factory=list, description="Source document IDs used")
    processing_time_ms: Optional[int] = Field(default=None, description="Processing time in milliseconds")
    cached: bool = Field(default=False, description="Whether the response was served from cache")
