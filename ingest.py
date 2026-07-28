import sys
import os
sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
load_dotenv()

import asyncio

async def main():
    print("🔍 Iniciando ingesta...")
    
    # Configurar logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        from ingestion.pipeline import IngestionPipeline
        from vectorstore.qdrant_client import QdrantStore
        
        print("📄 Inicializando Qdrant...")
        qdrant = QdrantStore()
        qdrant.initialize()
        print("✅ Qdrant conectado")
        
        print("📂 Ejecutando pipeline de ingesta...")
        pipeline = IngestionPipeline()
        count = pipeline.run()
        
        print(f"✅ Ingesta completada: {count} documentos procesados")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
