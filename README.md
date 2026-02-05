# AMTTP - Anti-Money Laundering Transaction Transfer Protocol

## Last Updated: February 1, 2026

A comprehensive DeFi compliance platform with ML-powered fraud detection, regulatory compliance (FATF, FCA), real-time transaction monitoring, and enterprise role management.

> **Recent Updates (Feb 2026):**
> - Flutter app fully standardized with design tokens, components, and services layer
> - Real MetaMask wallet integration (Sepolia testnet)
> - War Room landing page as entry point (SIEM removed)
> - Unified RBAC system across Flutter and Next.js

---

## 🚀 Quick Start

```powershell
# Option 1: Start all services with script
.\START_SERVICES.ps1

# Option 2: Manual start (see QUICK_START_GUIDE.md)
```

### Login & Authentication
The platform supports multiple authentication methods:
- **Wallet Login**: Connect MetaMask or other Web3 wallets
- **Email/Password**: Traditional authentication
- **Demo Mode**: Test different roles without authentication

**Demo Credentials:**
- Email: `demo@amttp.io`
- Password: `Demo123!`

---

## 📊 Architecture Overview

### Hybrid Flutter + Next.js Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FLUTTER APP (Main Shell)                              │
│                    iOS, Android, Web, Windows, macOS, Linux                  │
│                              Port: 3010                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────┐   ┌──────────────────────────────────────┐│
│  │     NATIVE FLUTTER VIEWS     │   │      EMBEDDED NEXT.JS (WebView)      ││
│  │  • Login / Registration      │   │  • Detection Studio (Charts)         ││
│  │  • Wallet Connection         │   │  • Graph Explorer (Memgraph)         ││
│  │  • Transfer / Send           │◄─►│  • Velocity Heatmap                  ││
│  │  • Transaction History       │   │  • Compliance Dashboard              ││
│  │  • Trust Check Interstitial  │   │  • "Open Full Screen" → Browser      ││
│  └──────────────────────────────┘   └──────────────────────────────────────┘│
│                            BRIDGE (Bidirectional Sync)                       │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (8007)                          │
│  Central API Gateway - Coordinates all compliance checks        │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   ML Engine   │    │  Compliance   │    │   Security    │
│    (8000)     │    │   Services    │    │   Services    │
├───────────────┤    ├───────────────┤    ├───────────────┤
│ - XGBoost     │    │ - Sanctions   │    │ - Integrity   │
│ - Graph ML    │    │   (8004)      │    │   (8008)      │
│ - Heuristics  │    │ - Monitoring  │    │ - Audit logs  │
│               │    │   (8005)      │    │               │
│ Graph Service │    │ - GeoRisk     │    │               │
│    (8001)     │    │   (8006)      │    │               │
└───────────────┘    │ - Policy      │    └───────────────┘
                     │   (8003)      │
                     └───────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE                               │
├─────────────────────────────────────────────────────────────────┤
│  MongoDB (27017)  │  Redis (6379)  │  Memgraph (7687)  │  MinIO │
└─────────────────────────────────────────────────────────────────┘
```

### Why Hybrid?
| Component | Technology | Reason |
|-----------|------------|--------|
| **Main App** | Flutter | 6 platforms from 1 codebase |
| **Analytics** | Next.js | Rich charting (Recharts, D3) |
| **Bridge** | JS Channel | Session sync, data updates |

See [FLUTTER_NEXTJS_BRIDGE.md](docs/FLUTTER_NEXTJS_BRIDGE.md) for implementation details.

---

## 🔑 Key Features

### ML-Powered Fraud Detection
- **Stacked Ensemble**: GraphSAGE + LightGBM + XGBoost with Linear Meta-Learner
- **Validated Performance**: ROC-AUC ~0.94, PR-AUC ~0.87, F1 ~0.87 (time-based test split)
- **Multi-Signal Analysis**: Combines ML predictions, graph topology, 6 AML rules
- **Real-time Scoring**: Sub-second risk assessment via parallel async calls

### Explainability & ML Transparency
- **Drill-down Explainability**: Click any alert or decision in the dashboard to view a full ML explanation, including:
        - Key risk factors and their impact
        - Detected fraud typologies (patterns)
        - Graph/network context
        - Action recommendations
- **Explainability Service**: Dedicated FastAPI microservice (port 8009) providing human-readable explanations for all ML risk decisions
- **SDK Support**: Both Python and TypeScript SDKs include `ExplainabilityService` for programmatic access
- **Fallback Logic**: If the explainability service is unavailable, the UI and SDKs generate a local explanation
- **UI Integration**: Explainability is available in:
        - Compliance Alerts (Next.js)
        - Dashboard Recent Decisions (Next.js)
        - Compliance Monitoring Alerts (Next.js)
        - (Optional) Flutter app via API


### Regulatory Compliance
- **FATF Travel Rule**: Full compliance with FATF recommendations
- **Sanctions Screening**: OFAC, EU, UN sanctions list integration
- **Geographic Risk**: Country-level risk scoring based on FATF grey/black lists
- **AML Monitoring**: Real-time transaction monitoring with configurable rules

### Security
- **UI Integrity Service**: Prevents Bybit-style UI manipulation attacks
- **Audit Trails**: Complete transaction and decision logging
- **Policy Engine**: Configurable whitelist/blacklist and transaction limits

### Authentication & Role Management
- **Multi-Method Auth**: Wallet-based (MetaMask), Email/Password, OAuth support
- **RBAC System**: 6-tier role hierarchy with granular permissions
- **Institutional Management**: Create and manage institutional users
- **Audit Logging**: Complete trail of role assignments and changes

---

## 📁 Project Structure

```
c:\amttp\
├── frontend/
│   ├── amttp_app/           # Flutter web application
│   │   ├── lib/             # Dart source code
│   │   ├── build/web/       # Built web app
│   │   └── flutter_server.py # Development server with CSP
│   └── frontend/            # Next.js dashboard
│       ├── src/
│       │   ├── app/         # Next.js pages
│       │   │   ├── login/   # Authentication pages
│       │   │   ├── register/ # User registration
│       │   │   ├── focus/   # End-user mode
│       │   │   ├── war-room/ # Institutional mode
│       │   │   │   ├── admin/roles/ # Role management
│       │   │   │   ├── compliance/  # Compliance reports
│       │   │   │   └── ...
│       │   │   └── api/auth/ # Auth API routes
│       │   ├── lib/         # Services & utilities
│       │   │   ├── auth-context.tsx    # Auth state
│       │   │   ├── auth-service.ts     # Auth operations
│       │   │   └── role-management-service.ts
│       │   ├── types/       # TypeScript definitions
│       │   │   ├── rbac.ts  # Role definitions
│       │   │   ├── auth.ts  # Auth types
│       │   │   └── role-management.ts
│       │   └── components/  # React components
│       └── next.config.js   # Proxy configuration
├── backend/
│   ├── compliance-service/  # Python microservices
│   │   ├── orchestrator.py  # Main API gateway
│   │   ├── sanctions_service.py
│   │   ├── monitoring_rules.py
│   │   ├── geographic_risk.py
│   │   └── integrity_service.py
│   └── policy-service/
│       └── policy_api.py
├── ml/
│   └── Automation/
│       └── ml_pipeline/
│           └── inference/
│               ├── hybrid_api.py    # ML risk scoring
│               └── run_graph_server.py
├── START_SERVICES.ps1       # Service startup script
├── QUICK_START_GUIDE.md     # Getting started guide
├── PORT_USAGE.md            # Port assignments
└── docker-compose.yml       # Infrastructure services
```

---

## 🌐 Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Flutter Consumer App | http://localhost:8889 | End-user wallet & transfer interface |
| Next.js War Room | http://localhost:3006 | Institutional compliance dashboard |
| Orchestrator API | http://localhost:8007 | Main API gateway |
| ML Risk API | http://localhost:8000 | Fraud detection service |

> **Note:** The War Room now opens directly to the login page. SIEM dashboard has been removed.

---

## 📖 Documentation

### Quick Reference

| Document | Description |
|----------|-------------|
| [QUICK_START_GUIDE.md](documentation/QUICK_START_GUIDE.md) | How to start all services |
| [PORT_USAGE.md](documentation/PORT_USAGE.md) | Complete port reference |
| [FINAL_STATUS.md](documentation/FINAL_STATUS.md) | Current implementation status |
| [UI_ARCHITECTURE_MAP.md](documentation/UI_ARCHITECTURE_MAP.md) | UI/UX structure |

### Architecture & Design

| Document | Description |
|----------|-------------|
| [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | Full system architecture |
| [AUTH_GUIDE.md](docs/AUTH_GUIDE.md) | Authentication & role management |
| [ML_ARCHITECTURE.md](docs/ML_ARCHITECTURE.md) | ML pipeline details |

### Compliance & Regulatory

| Document | Description |
|----------|-------------|
| [FCA_COMPLIANCE.md](documentation/FCA_COMPLIANCE.md) | FCA regulatory compliance |
| [FATF_COMPLIANCE.md](documentation/FATF_COMPLIANCE.md) | FATF Travel Rule implementation |

### Flutter App

| Document | Description |
|----------|-------------|
| [STANDARDIZATION_GUIDE.md](frontend/amttp_app/STANDARDIZATION_GUIDE.md) | Flutter design system & patterns |

---

## 🧠 Explainability Usage

### In the UI
- **Next.js Dashboard**: Click any alert or decision to open a modal with full ML explainability (factors, typologies, recommendations)
- **Compliance Page**: Click any monitoring alert for instant explainability
- **Fallback**: If the explainability service is down, a local explanation is generated

### In the SDKs
- **TypeScript**: Use `ExplainabilityService` from `packages/client-sdk/src/explainability.ts`
- **Python**: Use `ExplainabilityService` from `packages/python-sdk/amttp/explainability.py`

#### Example (TypeScript)
```ts
import { ExplainabilityService } from '@amttp/client-sdk';
const svc = new ExplainabilityService('http://localhost:8009');
const explanation = await svc.explain({ risk_score: 0.85, features: { amount_eth: 10 } });
console.log(explanation.summary);
```

#### Example (Python)
```python
from amttp.explainability import ExplainabilityService
svc = ExplainabilityService('http://localhost:8009')
explanation = svc.explain(risk_score=0.85, features={'amount_eth': 10})
print(explanation.summary)
```

---

---

## 🛠️ Development

### Prerequisites
- Python 3.10+
- Node.js 18+
- Flutter 3.x
- Docker & Docker Compose

### Environment Setup
```powershell
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies
cd frontend/frontend && npm install

# Install Flutter dependencies
cd frontend/amttp_app && flutter pub get

# Start Docker infrastructure
docker-compose up -d
```

### Running Tests
```powershell
# Backend tests
pytest backend/

# Frontend tests
cd frontend/frontend && npm test
cd frontend/amttp_app && flutter test
```

---

## 📄 License

Proprietary - All rights reserved.

---

## 👥 Contact

For questions or support, contact the development team.
