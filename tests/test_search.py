import asyncio
from vectorstore.qdrant_client import QdrantStore

async def main():
    store = QdrantStore()

    results = await store.search("generación de electricidad", top_k=5)

    for r in results:
        print("\nARTICULO:", r["payload"]["articulo"])
        print("SCORE:", r["score"])
        print("TEXT:", r["texto"][:200])

asyncio.run(main())