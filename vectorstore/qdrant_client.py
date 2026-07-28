import uuid
from typing import List, Optional, Dict, Any
from loguru import logger

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import (
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from app.models.legal_unit import LegalUnit
from app.config import settings
from core.embeddings import get_embedder


class QdrantStore:
    def __init__(self) -> None:
        self.client: Optional[QdrantClient] = None
        self.embedder = get_embedder()
        self.collection_name = settings.qdrant_collection

    # =========================
    # INIT (SYNC FIX)
    # =========================
    def initialize(self) -> None:
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False,
            timeout=60,
        )

        self._ensure_collection()

        logger.info(f"Qdrant connected: {settings.qdrant_url}")

    # =========================
    # COLLECTION
    # =========================
    def _ensure_collection(self) -> None:
        if self.client is None:
            raise RuntimeError("Qdrant client not initialized")

        collections = self.client.get_collections().collections
        existing = [c.name for c in collections]

        if self.collection_name in existing:
            logger.info(f"Collection exists: {self.collection_name}")
            return

        logger.info(f"Creating collection: {self.collection_name}")

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=settings.embeddings_dimensions,
                distance=qmodels.Distance.COSINE,
            ),
        )

        self._create_payload_indexes()

        logger.info(f"Collection created: {self.collection_name}")

    # =========================
    # INDEXES
    # =========================
    def _create_payload_indexes(self) -> None:
        keyword_fields = [
            "tipo_norma",
            "norma_id",
            "subsector",
            "enfoque",
            "sector",
        ]

        bool_fields = [
            "vigente",
            "renewable_incentive",
        ]

        for field in keyword_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception as e:
                logger.warning(f"Index issue {field}: {e}")

        for field in bool_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.BOOL,
                )
            except Exception as e:
                logger.warning(f"Index issue {field}: {e}")

    # =========================
    # CONVERT
    # =========================
    def _unit_to_point(
        self,
        unit: LegalUnit,
        embedding: Optional[List[float]] = None
    ) -> PointStruct:

        if embedding is None:
            embedding = self.embedder.encode(
                unit.texto,
                normalize_embeddings=True,
            ).tolist()

        return PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, unit.id)),
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

    # =========================
    # UPSERT
    # =========================
    def upsert_units(self, units: List[LegalUnit]) -> int:
        self._ensure_collection()

        logger.info(f"Ingestion: {len(units)} units")

        texts = [u.texto for u in units]
        embeddings = self.embedder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).tolist()

        points = [
            self._unit_to_point(unit, emb)
            for unit, emb in zip(units, embeddings)
        ]

        batch_size = 32
        total = 0

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]

            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True,
            )

            total += len(batch)
            logger.info(f"Upsert batch: {total}/{len(points)}")

        logger.info(f"Ingestion done: {total} points")
        return total

    # =========================
    # SEARCH
    # =========================
    def build_filter(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[Filter]:

        if not metadata_filter:
            return None

        conditions: List[FieldCondition] = []

        mapping = {
            "subsector": "subsector",
            "tipo_norma": "tipo_norma",
            "enfoque": "enfoque",
            "sector": "sector",
            "norma_id": "norma_id",
            "vigente": "vigente",
            "renewable_incentive": "renewable_incentive",
        }

        for k, field in mapping.items():
            if k in metadata_filter:
                conditions.append(
                    FieldCondition(
                        key=field,
                        match=MatchValue(value=metadata_filter[k]),
                    )
                )

        if metadata_filter.get("risk_flags"):
            for flag in metadata_filter["risk_flags"]:
                conditions.append(
                    FieldCondition(
                        key="risk_flags",
                        match=MatchValue(value=flag),
                    )
                )

        return Filter(must=conditions) if conditions else None

    def search(
        self,
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:

        self._ensure_collection()

        vector = self.embedder.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

        qfilter = self.build_filter(metadata_filter)

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            query_filter=qfilter,
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

    def scroll_all(self, batch_size: int = 100) -> List[Dict[str, Any]]:
        self._ensure_collection()

        all_points = []
        offset = None

        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            all_points.extend(points)

            if not offset or not points:
                break

        return [
            {
                "id": p.payload.get("id", ""),
                "texto": p.payload.get("texto", ""),
                "score": 0.0,
                "payload": p.payload,
            }
            for p in all_points
        ]

    def close(self) -> None:
        self.client = None
        logger.info("Qdrant closed")
