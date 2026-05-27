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
from app.services.embedding_service import get_embedder


class QdrantStore:
    def __init__(self):
        self.client: Optional[QdrantClient] = None
        self.embedder = get_embedder()
        self.collection_name = settings.qdrant_collection

    async def initialize(self):
        """
        Initialize Qdrant client and embedding model.
        """

        # FIX SSL ERROR:
        # Use URL instead of host/port to force HTTP protocol
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=False,
            https=False,
            timeout=60,
        )

        logger.info(f"Connecting to Qdrant at {settings.qdrant_url}")

        await self._ensure_collection()

    async def _ensure_collection(self):
        """
        Create collection if it does not exist.
        """

        collections = self.client.get_collections().collections
        existing = [c.name for c in collections]

        if self.collection_name not in existing:
            logger.info(f"Creating collection: {self.collection_name}")

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=settings.embeddings_dimensions,
                    distance=qmodels.Distance.COSINE,
                ),
            )

            self._create_payload_indexes()

            logger.success(f"Collection created: {self.collection_name}")

        else:
            logger.info(f"Collection already exists: {self.collection_name}")

    def _create_payload_indexes(self):
        """
        Create payload indexes for filtering.
        """

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

                logger.info(f"Created keyword index: {field}")

            except Exception as e:
                logger.warning(f"Index already exists or failed for {field}: {e}")

        for field in bool_fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.BOOL,
                )

                logger.info(f"Created bool index: {field}")

            except Exception as e:
                logger.warning(f"Index already exists or failed for {field}: {e}")

    def _unit_to_point(self, unit: LegalUnit, embedding: Optional[List[float]] = None) -> PointStruct:
        """
        Convert LegalUnit to Qdrant PointStruct.

        Accepts an optional pre-computed embedding to support batched encoding.
        """

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

    async def upsert_units(self, units: List[LegalUnit]) -> int:
        """
        Insert or update legal units in Qdrant.

        Encodes all texts in a single batched call (~5-10x faster than one-at-a-time).
        """

        if not self.client or not self.embedder:
            raise RuntimeError("QdrantStore not initialized")

        total_units = len(units)
        logger.info(f"Ingestion: preparing {total_units} points for Qdrant")

        texts = [unit.texto for unit in units]
        embeddings = self.embedder.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).tolist()

        points = [
            self._unit_to_point(unit, embedding)
            for unit, embedding in zip(units, embeddings)
        ]

        # Validate all point IDs are str or int
        for pt in points:
            if not isinstance(pt.id, (str, int)):
                raise TypeError(f"Point id must be str or int, got {type(pt.id).__name__}: {pt.id}")

        logger.info(f"Ingestion: encoded {len(points)} points, starting batch upsert")

        batch_size = 32
        total_inserted = 0

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]

            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                    wait=True,
                )
                total_inserted += len(batch)
                logger.info(
                    f"Ingestion: batch {i // batch_size + 1}/{(len(points) - 1) // batch_size + 1} "
                    f"({len(batch)} points, {total_inserted}/{total_units} total)"
                )
            except Exception as e:
                logger.error(f"Ingestion: batch {i // batch_size + 1} FAILED: {e}")
                raise

        logger.success(f"Ingestion complete: {total_inserted}/{total_units} points inserted into '{self.collection_name}'")

        return total_inserted

    def build_filter(
        self,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> Optional[Filter]:
        """
        Build Qdrant metadata filter.
        """

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
            value = metadata_filter.get(key)

            if value is not None:
                conditions.append(
                    FieldCondition(
                        key=field,
                        match=MatchValue(value=value),
                    )
                )

        # risk flags
        if metadata_filter.get("risk_flags"):
            for flag in metadata_filter["risk_flags"]:
                conditions.append(
                    FieldCondition(
                        key="risk_flags",
                        match=MatchValue(value=flag),
                    )
                )

        return Filter(must=conditions) if conditions else None

    async def search(
        self,
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search in Qdrant.
        """

        if not self.client or not self.embedder:
            raise RuntimeError("QdrantStore not initialized")

        query_vector = self.embedder.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

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

    async def scroll_all(self, batch_size: int = 100) -> List[Dict[str, Any]]:
        if not self.client:
            raise RuntimeError("QdrantStore not initialized")

        all_points: list = []
        next_offset = None

        while True:
            points, next_offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points)
            if next_offset is None or len(points) == 0:
                break

        logger.info(f"Scrolled {len(all_points)} points from Qdrant")
        return [
            {
                "id": p.payload.get("id", ""),
                "texto": p.payload.get("texto", ""),
                "score": 0.0,
                "payload": p.payload,
            }
            for p in all_points
        ]

    async def close(self):
        """
        Close Qdrant connection.
        """

        if self.client:
            self.client.close()
            logger.info("Qdrant client closed")