from typing import List, Optional, Dict, Any
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

from app.models.legal_unit import LegalUnit
from app.config import settings


class QdrantStore:
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.embedder: Optional[SentenceTransformer] = None
        self.collection_name = settings.qdrant_collection

    async def initialize(self):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        self.embedder = SentenceTransformer(
            settings.embeddings_model,
            device=settings.embeddings_device,
        )
        await self._ensure_collection()

    async def _ensure_collection(self):
        collections = self.client.get_collections().collections
        existing = [c.name for c in collections]

        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=settings.embeddings_dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            self._create_payload_indexes()
            logger.info(f"Created collection: {self.collection_name}")
        else:
            logger.info(f"Collection exists: {self.collection_name}")

    def _create_payload_indexes(self):
        for field in ["tipo_norma", "norma_id", "subsector", "enfoque", "vigente", "sector", "renewable_incentive"]:
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field,
                field_type=qmodels.PayloadSchemaType.KEYWORD,
            )

    def _unit_to_point(self, unit: LegalUnit) -> PointStruct:
        embedding = self.embedder.encode(unit.texto).tolist()
        return PointStruct(
            id=hash(unit.id),
            vector=embedding,
            payload={
                "id": unit.id,
                "tipo_norma": unit.tipo_norma,
                "norma_id": unit.norma_id,
                "articulo": unit.articulo,
                "tema": unit.tema,
                "vigente": unit.vigente,
                "sector": unit.sector,
                "subsector": unit.subsector,
                "enfoque": unit.enfoque,
                "risk_flags": unit.risk_flags,
                "renewable_incentive": unit.renewable_incentive,
                "texto": unit.texto,
            },
        )

    async def upsert_units(self, units: List[LegalUnit]) -> int:
        if not self.client or not self.embedder:
            raise RuntimeError("QdrantStore not initialized")

        points = [self._unit_to_point(u) for u in units]
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True,
            )
        logger.info(f"Upserted {len(points)} points to Qdrant")
        return len(points)

    def build_filter(self, metadata_filter: Optional[Dict[str, Any]] = None) -> Optional[Filter]:
        if not metadata_filter:
            return None

        conditions: List[FieldCondition] = []
        field_mapping = {
            "subsector": "subsector",
            "tipo_norma": "tipo_norma",
            "enfoque": "enfoque",
            "sector": "sector",
            "norma_id": "norma_id",
            "vigente": "vigente",
            "renewable_incentive": "renewable_incentive",
        }

        for key, field in field_mapping.items():
            if key in metadata_filter and metadata_filter[key] is not None:
                conditions.append(
                    FieldCondition(
                        key=field,
                        match=MatchValue(value=metadata_filter[key]),
                    )
                )

        if "risk_flags" in metadata_filter and metadata_filter["risk_flags"]:
            for flag in metadata_filter["risk_flags"]:
                conditions.append(
                    FieldCondition(
                        key="risk_flags",
                        match=MatchValue(value=flag),
                    )
                )

        return Filter(must=conditions) if conditions else None

    async def search(self, query: str, metadata_filter: Optional[Dict[str, Any]] = None,
                     top_k: int = 10) -> List[Dict[str, Any]]:
        if not self.client or not self.embedder:
            raise RuntimeError("QdrantStore not initialized")

        query_vector = self.embedder.encode(query).tolist()
        qdrant_filter = self.build_filter(metadata_filter)

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "id": r.payload.get("id", ""),
                "texto": r.payload.get("texto", ""),
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    async def close(self):
        if self.client:
            self.client.close()
            logger.info("Qdrant client closed")
