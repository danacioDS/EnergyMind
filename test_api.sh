#!/bin/bash
echo "🔍 EnergyMind — Validación API"
echo "================================"
echo ""

echo -n "📊 Health: "
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health
echo ""

echo -n "📊 Readiness: "
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/health/ready
echo ""

echo ""
echo "📊 Query: "
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "¿Qué dice la Ley 1604?"}' \
  | jq -r '"question: " + .question, "sources: " + (.sources | length | tostring), "time: " + (.processing_time_ms | tostring) + "ms"'
