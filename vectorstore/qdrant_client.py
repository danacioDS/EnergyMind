import uuid
from typing import List, Dict, Any, Optional, Union
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.models import PointStruct
from sentence_transformers import SentenceTransformer
from app.config import settings
from app.ingestion.models import LegalUnit

class QdrantStore:
    def __init__(self, url: Optional[str] = None, collection_name: Optional[str] = None):
        self.url = url or settings.QDRANT_URL
        self.collection_name = collection_name or settings.QDRANT_COLLECTION
        self.client: Optional[QdrantClient] = None
        self.embedder: Optional[SentenceTransformer] = None
        self.initialized = False

    def initialize(self):
        if self.initialized:
            return

        # Conectar a Qdrant
        self.client = QdrantClient(
            url=self.url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
        self.embedder = SentenceTransformer(settings.EMBEDDINGS_MODEL)
        self.initialized = True
        logger.info(f"Qdrant connected: {self.url}")

    def _ensure_collection(self):
        self.initialize()

        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
        except Exception:
            exists = False

        if not exists:
            logger.info(f"Creating collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=qmodels.VectorParams(
                    size=settings.EMBEDDINGS_DIMENSIONS,
                    distance=qmodels.Distance.COSINE,
                ),
            )
            logger.info(f"Collection created: {self.collection_name}")

        # Crear índices
        self._ensure_payload_indexes()

    def _ensure_payload_indexes(self):
        fields = [
            "tipo_norma", "norma_id", "subsector", "sector", "enfoque",
        ]
        for field in fields:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

        for field in ["vigente", "renewable_incentive"]:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=qmodels.PayloadSchemaType.BOOL,
                )
            except Exception:
                pass

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

        metadata = unit.metadata or {}

        return PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_DNS, unit.id)),
            vector=embedding,
            payload={
                "id": unit.id,
                "documento_id": unit.documento_id,
                "tipo_norma": metadata.get("tipo_norma", ""),
                "norma_id": metadata.get("norma_id", unit.norma_id or ""),
                "articulo": unit.numero,
                "tema": metadata.get("tema", ""),
                "vigente": metadata.get("vigente", unit.vigente),
                "sector": metadata.get("sector", "Energia"),
                "subsector": metadata.get("subsector", unit.subsector or "General"),
                "enfoque": metadata.get("enfoque", unit.enfoque or ""),
                "risk_flags": metadata.get("risk_flags", unit.risk_flags or []),
                "renewable_incentive": metadata.get("renewable_incentive", unit.renewable_incentive or False),
                "source": metadata.get("source", ""),
                "url": metadata.get("url", ""),
                "texto": unit.texto,
            },
        )

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
            batch = points[i:i+batch_size]
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                )
                total += len(batch)
                logger.info(f"Upsert batch: {total}/{len(points)}")
            except Exception as e:
                logger.error(f"Batch upsert failed: {e}")
                raise

        logger.info(f"Ingestion done: {total} points")
        return total

    def search(
        self,
        query: str,
        metadata_filter: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        self.initialize()

        # Generar embedding
        query_embedding = self.embedder.encode(query, normalize_embeddings=True).tolist()

        # Construir filtro
        qfilter = None
        if metadata_filter:
            conditions = []
            for key, value in metadata_filter.items():
                if value is None:
                    continue
                if isinstance(value, str):
                    conditions.append(qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchValue(value=value)
                    ))
                elif isinstance(value, bool):
                    conditions.append(qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchValue(value=value)
                    ))
            if conditions:
                qfilter = qmodels.Filter(must=conditions)

        # Buscar
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            limit=top_k,
            query_filter=qfilter,
        )

        # Formatear
        documents = []
        for hit in results:
            doc = {
                "id": hit.payload.get("id", ""),
                "texto": hit.payload.get("texto", ""),
                "score": hit.score,
                "payload": hit.payload,
            }
            documents.append(doc)

        return documents

    def scroll_all(self, limit: int = 1000) -> List[Dict[str, Any]]:
        self.initialize()

        documents = []
        offset = None

        while True:
            try:
                response = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                points, offset = response
                for point in points:
                    if point.payload:
                        documents.append(point.payload)
                if not offset:
                    break
            except Exception as e:
                logger.error(f"Scroll failed: {e}")
                break

        return documents

    def close(self):
        if self.client:
            self.client.close()
            logger.info("Qdrant closed")
