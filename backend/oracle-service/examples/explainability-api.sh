#!/bin/bash
# Example API calls to the Explainability API
# Run with: bash examples/explainability-api.sh

BASE_URL="${BASE_URL:-http://localhost:3000}"

echo "========================================"
echo "AMTTP Explainability API Examples"
echo "========================================"
echo ""

echo "1. Get API Documentation"
echo "------------------------"
curl -s "$BASE_URL/explainability" | jq '.endpoints'
echo ""

echo "2. Score Low-Risk Transaction (ALLOW)"
echo "--------------------------------------"
curl -s -X POST "$BASE_URL/explainability/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "transactionId": "tx-low-risk-001",
    "riskScore": 0.15,
    "features": {
      "amountEth": 0.5,
      "txCount24h": 2
    }
  }' | jq '{action: .explanation.action, summary: .explanation.summary, topReasons: .explanation.topReasons}'
echo ""

echo "3. Score Medium-Risk Transaction (REVIEW)"
echo "------------------------------------------"
curl -s -X POST "$BASE_URL/explainability/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "transactionId": "tx-medium-risk-001",
    "riskScore": 0.45,
    "features": {
      "amountEth": 5.0,
      "amountVsAverage": 3.5,
      "txCount24h": 15
    }
  }' | jq '{action: .explanation.action, summary: .explanation.summary, topReasons: .explanation.topReasons}'
echo ""

echo "4. Score High-Risk Transaction (ESCROW)"
echo "----------------------------------------"
curl -s -X POST "$BASE_URL/explainability/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "transactionId": "tx-high-risk-001",
    "riskScore": 0.73,
    "features": {
      "amountEth": 50.0,
      "avgAmount30d": 2.0,
      "dormancyDays": 180,
      "txCount24h": 45,
      "uniqueRecipients24h": 12
    }
  }' | jq '{action: .explanation.action, summary: .explanation.summary, topReasons: .explanation.topReasons, typologies: [.explanation.typologyMatches[].typology]}'
echo ""

echo "5. Score Critical-Risk Transaction (BLOCK)"
echo "-------------------------------------------"
curl -s -X POST "$BASE_URL/explainability/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "transactionId": "tx-critical-risk-001",
    "riskScore": 0.92,
    "features": {
      "amountEth": 100.0,
      "sanctionsMatch": true,
      "countryCode": "KP"
    },
    "graphContext": {
      "hopsToSanctioned": 1
    }
  }' | jq '{action: .explanation.action, summary: .explanation.summary, topReasons: .explanation.topReasons, recommendations: .explanation.recommendations}'
echo ""

echo "6. Full Transaction Score + Explanation"
echo "----------------------------------------"
curl -s -X POST "$BASE_URL/explainability/explain/transaction" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 15500000000000000000,
    "from": "0x742d35Cc6634C0532925a3b844Bc9e7595f1e1234",
    "to": "0x8ba1f109551bD432803012645Hac136e8e2b1234",
    "avgAmount30d": 2.5,
    "dormancyDays": 90,
    "velocity_24h": 20
  }' | jq '{riskScore, action, summary, topReasons}'
echo ""

echo "7. Health Check"
echo "----------------"
curl -s "$BASE_URL/explainability/health" | jq '.'
echo ""

echo "8. Prometheus Metrics (first 10 lines)"
echo "---------------------------------------"
curl -s "$BASE_URL/explainability/metrics" | head -10
echo ""

echo "9. Get All Typologies"
echo "----------------------"
curl -s "$BASE_URL/explainability/typologies" | jq '.typologies | .[:3] | .[] | {id, name, severity}'
echo ""

echo "Done!"
