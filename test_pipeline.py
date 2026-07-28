import asyncio
from dotenv import load_dotenv
load_dotenv()

async def test():
    print("1️⃣ Inicializando Qdrant...")
    from vectorstore.qdrant_client import QdrantStore
    qdrant = QdrantStore()
    qdrant.initialize()
    print("   ✅ Qdrant OK")
    
    print("2️⃣ Inicializando Pipeline...")
    from app.rag.pipeline import RAGPipeline
    from app.models.schemas import QueryRequest
    
    pipeline = RAGPipeline(qdrant=qdrant)
    await pipeline.initialize()
    print("   ✅ Pipeline OK")
    
    print("3️⃣ Probando query...")
    # ✅ USAR QueryRequest en lugar de dict
    request = QueryRequest(
        question="¿Qué dice la Ley 1604 sobre energías renovables?"
    )
    result = await pipeline.query(request)
    print("   ✅ Query OK")
    print("\n📋 RESULTADO:")
    print(result)

asyncio.run(test())
