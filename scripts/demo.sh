#!/bin/bash
echo "⚡ EnergyMind — Demo"
echo "====================="
echo ""

echo "📡 Verificando backend..."
curl -s http://localhost:8000/api/v1/health | jq .

echo ""
echo "🔍 Ejecutando queries de demo..."
echo ""

queries=(
  "¿Qué dice la Ley 1604 sobre energías renovables?"
  "¿Qué establece el artículo 3 de la Ley 1604?"
  "¿Qué diferencias existen entre la Ley 1600 y la Ley 1604?"
  "¿Qué riesgos regulatorios identifica EnergyMind para proyectos de generación eléctrica?"
  "¿Qué establece la normativa boliviana sobre hidrógeno verde en 2050?"
)

for query in "${queries[@]}"; do
  echo "📝 $query"
  echo "---"
  curl -s -X POST http://localhost:8000/api/v1/query \
    -H "Content-Type: application/json" \
    -d "{\"question\": \"$query\"}" | jq '{sources: .sources, time: .processing_time_ms}'
  echo ""
done
