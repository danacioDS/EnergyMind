#!/usr/bin/env python3
"""
Script de ingesta para EnergyMind.
Ejemplo: python scripts/ingest.py BO-L-1604 BO-DS-24711
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ingestion.pipeline import ingest_documents
from loguru import logger


async def main():
    if len(sys.argv) > 1:
        document_ids = sys.argv[1:]
    else:
        document_ids = [
            "BO-L-1604",
            "BO-L-1600",
            "BO-DS-24711",
        ]
    
    logger.info(f"📋 Documentos a ingestar: {document_ids}")
    
    stats = await ingest_documents(document_ids)
    
    logger.info(f"✅ Ingesta completada:")
    logger.info(f"   - Procesados: {stats['processed']}")
    logger.info(f"   - Fallidos: {stats['failed']}")
    logger.info(f"   - Unidades: {stats['units']}")


if __name__ == "__main__":
    asyncio.run(main())
