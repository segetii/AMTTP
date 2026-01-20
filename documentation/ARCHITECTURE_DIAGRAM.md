# System Architecture Diagram

```
[User]
   |
   |-- Flutter Web (3010)
   |-- Next.js Dashboard (3006)
        |
        |-- Orchestrator (8007)
                |-- ML Risk Engine (8000)
                |-- Graph Service (8001)
                |-- ML Service (8002)
                |-- FCA Sanctions (8003)
                |-- Policy Engine (8004)
                |-- Monitoring (8005)
                |-- GeoRisk (8006)
                |-- Integrity (8008)
                |-- Explainability (8009)
```
