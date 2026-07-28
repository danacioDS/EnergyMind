#!/usr/bin/env python3
"""Prueba de conexión a Qdrant Cloud"""

import os
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

load_dotenv()

# Configuración desde .env
url = os.getenv("QDRANT_URL")
api_key = os.getenv("QDRANT_API_KEY")
collection = os.getenv("QDRANT_COLLECTION", "energymind")

print(f"🔗 Conectando a: {url}")
print(f"📚 Colección: {collection}")

try:
    # Conectar a Qdrant Cloud
    client = QdrantClient(
        url=url,
        api_key=api_key,
        timeout=30
    )
    
    # Verificar conexión
    collections = client.get_collections()
    print(f"✅ Conexión exitosa!")
    print(f"📚 Colecciones existentes: {[c.name for c in collections.collections]}")
    
    # Crear colección si no existe
    try:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(
                size=1024,  # BGE-M3 dimensión
                distance=Distance.COSINE
            )
        )
        print(f"✅ Colección '{collection}' creada correctamente")
    except Exception as e:
        if "already exists" in str(e).lower():
            print(f"ℹ️ La colección '{collection}' ya existe")
        else:
            print(f"⚠️ Error al crear colección: {e}")
    
    print(f"\n📊 Información del cluster:")
    print(f"   - URL: {url}")
    print(f"   - Colección: {collection}")
    print(f"   - Estado: OK")
    
except Exception as e:
    print(f"❌ Error: {e}")
    print("\n🔧 Verifica:")
    print("  1. URL correcta")
    print("  2. API Key correcta")
    print("  3. Cluster está 'Ready' en Qdrant Cloud")
