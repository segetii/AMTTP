#!/bin/bash
# Test all AMTTP endpoints on VPS
endpoints=(
  "/ Landing"
  "/health Health"
  "/risk/health Risk-Engine"
  "/api/health API"
  "/app/ Flutter-App"
  "/zknaf/health ZK-NAF"
  "/oracle/health Oracle"
  "/compliance/health Compliance"
  "/war-room War-Room"
  "/dashboard Dashboard"
  "/api/data/stats Data-Stats"
  "/sanctions/health Sanctions"
  "/monitoring/health Monitoring"
  "/policy/health Policy"
  "/integrity/health Integrity"
  "/explain/health Explainability"
  "/geo/health GeoRisk"
  "/graph/health Graph"
)

echo "=== AMTTP Endpoint Test ==="
echo "Time: $(date -u)"
echo ""

for entry in "${endpoints[@]}"; do
  path=$(echo "$entry" | awk '{print $1}')
  name=$(echo "$entry" | awk '{print $2}')
  code=$(curl -so /dev/null -w "%{http_code}" "http://127.0.0.1:8888${path}" --max-time 5 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo "✅ $name ($path): $code"
  elif [ "$code" = "301" ] || [ "$code" = "302" ]; then
    echo "↪️  $name ($path): $code (redirect)"
  else
    echo "❌ $name ($path): $code"
  fi
done
echo ""
echo "=== Done ==="
