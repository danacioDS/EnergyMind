"""
Pipeline de ingesta para EnergyMind.
Conecta LexiVox → Qdrant → BM25.
"""

import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger
from pathlib import Path

from app.ingestion.sources.lexivox import LexiVoxAdapter
from app.ingestion.models import LegalDocument, LegalUnit, Provenance
from vectorstore.qdrant_client import QdrantStore
from core.embeddings import get_embedder
from app.config import settings


class IngestionPipeline:
    """Pipeline de ingesta para EnergyMind."""
    
    def __init__(self):
        self.adapter = LexiVoxAdapter()
        self.qdrant = QdrantStore()
        self.embedder = get_embedder()
        self.processed_count = 0
        self.errors = []
    
    async def ingest(self, document_ids: List[str]) -> Dict[str, Any]:
        """Ingesta de documentos desde LexiVox."""
        logger.info(f"🚀 Iniciando ingesta de {len(document_ids)} documentos")
        
        stats = {
            "total": len(document_ids),
            "processed": 0,
            "failed": 0,
            "units": 0,
            "errors": []
        }
        
        self.qdrant.initialize()
        self.qdrant._ensure_collection()
        
        for doc_id in document_ids:
            try:
                result = await self._ingest_document(doc_id)
                if result:
                    stats["processed"] += 1
                    stats["units"] += result.get("units", 0)
                else:
                    stats["failed"] += 1
            except Exception as e:
                logger.error(f"❌ Error en {doc_id}: {e}")
                stats["failed"] += 1
                stats["errors"].append(str(e))
        
        if stats["processed"] > 0:
            await self._rebuild_bm25()
        
        await self.adapter.close()
        
        logger.info(f"✅ Ingesta completada: {stats}")
        return stats
    
    async def _ingest_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Ingesta de un documento individual."""
        logger.info(f"📄 Procesando: {document_id}")
        
        doc_data = await self.adapter.fetch(document_id)
        if not doc_data:
            logger.warning(f"❌ No se pudo obtener {document_id}")
            return None
        
        legal_doc = self._to_legal_document(doc_data, document_id)
        
        units = await self._generate_embeddings(legal_doc.unidades)
        
        if units:
            success = self.qdrant.upsert_units(units)
            if success:
                logger.info(f"✅ Indexados {len(units)} artículos de {document_id}")
                return {"units": len(units)}
        
        return None
    
    def _to_legal_document(self, doc_data: Dict[str, Any], document_id: str) -> LegalDocument:
        """Convertir datos de LexiVox a LegalDocument."""
        metadata = doc_data.get("metadata", {})
        
        norma_id = document_id.split("-")[1] if "-" in document_id else document_id
        
        tipo = metadata.get("tipo", "Ley")
        if "Decreto" in doc_data.get("title", ""):
            tipo = "Decreto Supremo"
        
        units = []
        for article in doc_data.get("articles", []):
            unit = LegalUnit(
                id=f"{document_id}_art_{article.get('numero', '1')}",
                documento_id=document_id,
                tipo="articulo",
                numero=str(article.get("numero", "1")),
                texto=article.get("texto", ""),
                metadata={
                    "norma_id": norma_id,
                    "tipo_norma": tipo,
                    "source": "lexivox",
                    "url": doc_data.get("url", ""),
                }
            )
            units.append(unit)
        
        provenance = Provenance(
            source_primary="gaceta_oficial",
            source_discovery="lexivox",
            discovery_url=doc_data.get("url", ""),
            document_hash=hashlib.sha256(doc_data.get("text", "").encode()).hexdigest(),
            retrieved_at=datetime.now()
        )
        
        return LegalDocument(
            id=document_id,
            norma_id=norma_id,
            tipo=tipo,
            titulo=doc_data.get("title", ""),
            texto=doc_data.get("text", ""),
            unidades=units,
            metadata=metadata,
            provenance=provenance
        )
    
    async def _generate_embeddings(self, units: List[LegalUnit]) -> List[LegalUnit]:
        """Generar embeddings para las unidades legales."""
        if not units:
            return []
        
        texts = [u.texto for u in units]
        embeddings = self.embedder.encode(texts, show_progress_bar=True)
        
        for i, unit in enumerate(units):
            unit.metadata["embedding"] = embeddings[i].tolist()
        
        return units
    
    async def _rebuild_bm25(self):
        """Reconstruir el índice BM25."""
        logger.info("🔄 Reconstruyendo índice BM25...")
        
        all_docs = self.qdrant.scroll_all()
        
        if not all_docs:
            logger.warning("No hay documentos para reconstruir BM25")
            return
        
        from app.retrieval.bm25 import BM25Retriever
        bm25 = BM25Retriever()
        bm25.build_index(all_docs)
        
        cache_path = Path(settings.BM25_INDEX_PATH)
        bm25.save(cache_path)
        
        logger.info(f"✅ BM25 reconstruido con {len(all_docs)} documentos")
    
    async def close(self):
        """Cerrar conexiones."""
        await self.adapter.close()


async def ingest_documents(document_ids: List[str]) -> Dict[str, Any]:
    """Ingestar documentos desde LexiVox."""
    pipeline = IngestionPipeline()
    try:
        return await pipeline.ingest(document_ids)
    finally:
        await pipeline.close()
