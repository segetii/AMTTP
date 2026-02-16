# AMTTP Port Configuration Guide# AMTTP Port Configuration Guide



## Last Updated: January 19, 2026## ⚠️ OFFICIAL PORT ASSIGNMENTS - DO NOT CHANGE WITHOUT UPDATING ALL REFERENCES



⚠️ **OFFICIAL PORT ASSIGNMENTS** - This is the single source of truth for all port assignments.This document is the **single source of truth** for all port assignments in the AMTTP system.



------



## Frontend Services## Frontend Services



| Service | Port | URL | Start Command || Service | Port | URL | Description |

|---------|------|-----|---------------||---------|------|-----|-------------|

| **Next.js Dashboard** | **3006** | http://localhost:3006 | `cd frontend/frontend; npm run dev -- -p 3006` || **Next.js Frontend** | **3006** | http://localhost:3006 | Main web dashboard (compliance, policies, SIEM) |

| **Flutter Web App** | **3010** | http://localhost:3010 | `py -3 frontend/amttp_app/flutter_server.py` || **Flutter Web** | **3010** | http://localhost:3010 | Mobile-optimized web app |



------



## Backend Microservices (Python FastAPI)## Backend Services (Python)



| Service | Port | File | Start Command || Service | Port | Health Endpoint | Description |

|---------|------|------|---------------||---------|------|-----------------|-------------|

| **ML Risk API** | **8000** | `ml/Automation/ml_pipeline/inference/hybrid_api.py` | `py -3 hybrid_api.py` || **ML Risk Engine** | **8000** | http://localhost:8000/health | XGBoost risk scoring, transaction analysis |

| **Graph Service** | **8001** | `ml/Automation/ml_pipeline/inference/run_graph_server.py` | `py -3 run_graph_server.py` || **Graph Server** | **8001** | http://localhost:8001/health | Graph-based analytics, Memgraph integration |

| **FCA Compliance** | **8002** | `backend/oracle-service/fca-compliance-service.ts` | TypeScript service || **FCA Compliance** | **8002** | http://localhost:8002/health | FCA regulatory compliance |

| **Policy Service** | **8003** | `backend/policy-service/policy_api.py` | `py -3 policy_api.py` || **Policy Service** | **8003** | http://localhost:8003/health | Policy CRUD, whitelist/blacklist management |

| **Sanctions Service** | **8004** | `backend/compliance-service/sanctions_service.py` | `py -3 sanctions_service.py` || **Sanctions Service** | **8004** | http://localhost:8004/health | OFAC/EU/UN sanctions screening |

| **Monitoring Engine** | **8005** | `backend/compliance-service/monitoring_rules.py` | `py -3 monitoring_rules.py` || **Monitoring Service** | **8005** | http://localhost:8005/health | AML transaction monitoring, alerts |

| **Geographic Risk** | **8006** | `backend/compliance-service/geographic_risk.py` | `py -3 geographic_risk.py` || **Geographic Risk** | **8006** | http://localhost:8006/health | FATF lists, country risk scoring |

| **Orchestrator** | **8007** | `backend/compliance-service/orchestrator.py` | `py -3 orchestrator.py` || **Orchestrator** | **8007** | http://localhost:8007/health | Main API gateway, unified compliance checks |

| **Integrity Service** | **8008** | `backend/compliance-service/integrity_service.py` | `py -3 integrity_service.py` || **Integrity Service** | **8008** | http://localhost:8008/health | Audit trails, data integrity |

| **Explainability** | **8009** | `backend/compliance-service/explainability_service.py` | `py -3 explainability_service.py` || **Explainability** | **8009** | http://localhost:8009/health | ML decision explanations |



------



## Infrastructure (Docker Compose)## Storage Services (Docker)



| Service | Port | Credentials | Description || Service | Port | Credentials | Description |

|---------|------|-------------|-------------||---------|------|-------------|-------------|

| **MongoDB** | **27017** | admin:changeme | Primary database || **MongoDB** | **27017** | admin:changeme | Primary database |

| **Redis** | **6379** | (none) | Caching, session storage || **Redis** | **6379** | (none) | Caching, session storage |

| **MinIO** | **9000** | localtest:localtest123 | Object storage || **MinIO** | **9000** | localtest:localtest123 | Object storage (S3-compatible) |

| **MinIO Console** | **9001** | localtest:localtest123 | MinIO web UI || **MinIO Console** | **9001** | localtest:localtest123 | MinIO web UI |

| **Memgraph** | **7687** | (none) | Graph database || **IPFS** | **5001** | (none) | Decentralized storage |

| **IPFS** | **5001** | (none) | Decentralized storage || **Memgraph** | **7687** | (none) | Graph database |



------



## Service Dependencies## Quick Reference



```### Starting All Services

┌─────────────────────────────────────────────────────────────────┐

│                    FRONTEND LAYER                                │```powershell

├─────────────────────────────────────────────────────────────────┤# Backend Services (run from c:\amttp\backend\compliance-service)

│  Flutter Web (3010)          Next.js Dashboard (3006)           │py sanctions_service.py      # Port 8004

│       │                              │                          │py monitoring_rules.py       # Port 8005

│       └──────────┬───────────────────┘                          │py geographic_risk.py        # Port 8006

│                  ▼                                               │py orchestrator.py           # Port 8007

├─────────────────────────────────────────────────────────────────┤py integrity_service.py      # Port 8008

│                    API GATEWAY                                   │py explainability_service.py # Port 8009

├─────────────────────────────────────────────────────────────────┤

│              Orchestrator (8007)                                │# ML Services (run from c:\amttp\ml\Automation)

│                  │                                               │py -m ml_pipeline.run_server       # Port 8000

│     ┌───────────┼───────────┬───────────┬───────────┐           │py -m ml_pipeline.run_graph_server # Port 8001

│     ▼           ▼           ▼           ▼           ▼           │

├─────────────────────────────────────────────────────────────────┤# Policy Service (run from c:\amttp\backend\policy-service)

│                 COMPLIANCE SERVICES                              │py policy_api.py             # Port 8003

├─────────────────────────────────────────────────────────────────┤

│  ML Risk    Sanctions   Monitoring   GeoRisk    Policy         │# FCA Compliance (run from c:\amttp\backend\oracle-service)

│  (8000)     (8004)      (8005)       (8006)     (8003)         │py fca_compliance_api.py     # Port 8002

│     │                                                           │```

│     ▼                                                           │

├─────────────────────────────────────────────────────────────────┤### VS Code Tasks

│                    ML LAYER                                      │

├─────────────────────────────────────────────────────────────────┤Use `Ctrl+Shift+P` → "Tasks: Run Task" to start:

│  Graph Service (8001)    Integrity (8008)    Explain (8009)    │- `Start Next.js Dev Server` - Starts Next.js on port 3006

│       │                                                         │- `Start Flutter Web Server` - Serves Flutter on port 3010

│       ▼                                                         │

├─────────────────────────────────────────────────────────────────┤---

│                 INFRASTRUCTURE                                   │

├─────────────────────────────────────────────────────────────────┤## Next.js Proxy Rewrites

│  Memgraph     MongoDB      Redis       MinIO                    │

│  (7687)       (27017)      (6379)      (9000)                  │The Next.js frontend proxies API calls to backend services:

└─────────────────────────────────────────────────────────────────┘

```| Frontend Path | Backend Target | Service |

|---------------|----------------|---------|

---| `/api/*` | http://localhost:8007 | Orchestrator |

| `/sanctions/*` | http://localhost:8004 | Sanctions |

## API Routing| `/monitoring/*` | http://localhost:8005 | Monitoring |

| `/geo/*` | http://localhost:8006 | Geographic Risk |

### Next.js Proxy Rewrites (next.config.js)| `/explain/*` | http://localhost:8009 | Explainability |

| `/policy/*` | http://localhost:8003 | Policy Service |

| Frontend Path | Backend Target | Service |

|---------------|----------------|---------|---

| `/api/*` | http://localhost:8007 | Orchestrator |

| `/sanctions/*` | http://localhost:8004 | Sanctions Service |## Flutter Integration

| `/monitoring/*` | http://localhost:8005 | Monitoring Engine |

| `/geo/*` | http://localhost:8006 | Geographic Risk |Flutter embeds Next.js pages via iframes for:

| `/explain/*` | http://localhost:8009 | Explainability |- **Detection Studio / SIEM Dashboard** → http://localhost:3006

- **FATF Rules Page** → http://localhost:3006/compliance/fatf-rules

### Flutter Direct Calls (api_service.dart)

---

| Endpoint | Target | Description |

|----------|--------|-------------|## Health Check Script

| `/risk/score` | http://localhost:8007 | Risk scoring via orchestrator |

| `/verify-integrity` | http://localhost:8008 | UI integrity check |```powershell

| `/api/evaluate` | http://localhost:8007 | Full compliance evaluation |# Check all services

@(8000,8001,8002,8003,8004,8005,8006,8007,8008,8009,3006,3010) | ForEach-Object {

---    $port = $_

    $result = netstat -ano | findstr "LISTENING" | findstr ":$port "

## Health Check Commands    if ($result) { Write-Host "✅ Port $port - RUNNING" }

    else { Write-Host "❌ Port $port - DOWN" }

```powershell}

# Quick status check - all backend ports```

netstat -ano | findstr "LISTENING" | findstr ":800"

---

# Individual health checks

curl http://localhost:8000/health  # ML Risk API## Troubleshooting

curl http://localhost:8001/health  # Graph Service

curl http://localhost:8003/health  # Policy Service### Port Already in Use

curl http://localhost:8004/health  # Sanctions Service```powershell

curl http://localhost:8005/health  # Monitoring Engine# Find process using port

curl http://localhost:8006/health  # Geographic Risknetstat -ano | findstr ":PORT_NUMBER"

curl http://localhost:8007/health  # Orchestrator

curl http://localhost:8008/health  # Integrity Service# Kill process by PID

taskkill /F /PID <PID>

# Frontend checks```

curl -s -o nul -w "%{http_code}" http://localhost:3006  # Next.js

curl -s -o nul -w "%{http_code}" http://localhost:3010  # Flutter### Service Won't Start

```1. Check if port is already in use

2. Verify Python dependencies: `pip install -r requirements.txt`

---3. Check Docker containers: `docker ps`

4. Review logs for errors

## VS Code Tasks

---

Use `Ctrl+Shift+P` → "Tasks: Run Task":

## Version History

| Task Name | Action |

|-----------|--------|| Date | Change | Author |

| `Start Next.js Dev Server` | Starts Next.js on port 3006 ||------|--------|--------|

| `Start Flutter Web Server` | Serves Flutter on port 3010 || 2026-01-17 | Initial documentation, standardized ports | System |

| 2026-01-17 | Fixed SIEM dashboard port from 3004 → 3006 | System |

---

---

## Common Issues

**⚠️ REMINDER: Any port change requires updates to:**

### Port Already In Use1. This document

2. `next.config.js` (proxy rewrites)

```powershell3. Flutter files referencing the port

# Find process using port4. VS Code tasks.json

netstat -ano | findstr ":<PORT>"5. Docker compose files


# Kill process by PID
Stop-Process -Id <PID> -Force
```

### Service Won't Start

1. Check if port is already in use
2. Verify dependencies are installed: `pip install -r requirements.txt`
3. Check Docker containers are running: `docker ps`

### CORS/CSP Errors

The Flutter web server (`flutter_server.py`) handles CSP headers. If you see "content blocked":
1. Restart the Flutter server
2. Hard refresh browser (Ctrl+Shift+R)
