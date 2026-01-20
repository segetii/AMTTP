# Explainability & ML Transparency

## Overview

AMTTP provides full explainability for all ML risk decisions, both in the UI and via SDKs.

- Drill-down on any alert or decision to see:
  - Key risk factors and their impact
  - Detected fraud typologies
  - Graph/network context
  - Action recommendations
- Dedicated FastAPI microservice (port 8009)
- SDK support: Python & TypeScript
- Fallback logic: local explanation if service is down

## UI Integration
- **Next.js Dashboard**: Click any alert/decision for explainability modal
- **Compliance Page**: Click any monitoring alert for explainability
- **Fallback**: Local explanation if service is unavailable

## SDK Usage

### TypeScript
```ts
import { ExplainabilityService } from '@amttp/client-sdk';
const svc = new ExplainabilityService('http://localhost:8009');
const explanation = await svc.explain({ risk_score: 0.85, features: { amount_eth: 10 } });
console.log(explanation.summary);
```

### Python
```python
from amttp.explainability import ExplainabilityService
svc = ExplainabilityService('http://localhost:8009')
explanation = svc.explain(risk_score=0.85, features={'amount_eth': 10})
print(explanation.summary)
```
