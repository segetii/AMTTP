# AMTTP — Copilot Instructions

## Project Overview

AMTTP (Anti-Money Laundering Transaction Transfer Protocol) is a DeFi compliance platform with ML-powered fraud detection, regulatory compliance, and enterprise role management. It runs as a **hybrid Flutter + Next.js** frontend backed by Python microservices, a TypeScript API gateway, and Solidity smart contracts.

## Architecture

```
Flutter App (port 3010)  ←→  Next.js Dashboard (port 3006)
         ↓ shared RBAC (frontend/shared/rbac_config.json)
Orchestrator (8007) — fan-out via aiohttp to:
  ML Risk API (8000)  |  Graph Service (8001)  |  Policy (8003)
  Sanctions (8004)    |  Monitoring (8005)     |  GeoRisk (8006)
  Integrity (8008)    |  Explainability (8009) |  ZK-NAF (8010)
Oracle Service (3001) — Express.js TypeScript gateway
Infrastructure: MongoDB (27017) | Redis (6379) | Memgraph (7687) | MinIO | Vault
```

- **Flutter** handles wallet/DeFi interactions (all 6 platforms); **Next.js** handles analytics/War Room dashboards with rich charting.
- They share design tokens: colors in `frontend/amttp_app/lib/core/theme/design_tokens.dart` must stay in sync with `frontend/frontend/tailwind.config.ts`.
- Python services all use **FastAPI + Uvicorn + Pydantic** with CORS middleware and optional API key auth.

## Key Directories

| Path | Purpose |
|------|---------|
| `contracts/` | Solidity ^0.8.24, UUPS upgradeable (OpenZeppelin), Hardhat + Foundry |
| `backend/oracle-service/src/` | Express.js TypeScript API — modular: `risk/`, `kyc/`, `compliance/`, `dispute/` |
| `backend/compliance-service/` | Python FastAPI microservices (orchestrator, sanctions, monitoring, geo-risk, integrity) |
| `ml/Automation/risk_engine/` | FastAPI model-serving endpoint (CPU-only, distilled student model) |
| `ml/Automation/ml_pipeline/` | Training, graph ML, inference pipelines |
| `frontend/frontend/src/` | Next.js App Router — `app/` pages, `components/` UI, `lib/` utilities |
| `frontend/amttp_app/lib/` | Flutter — Riverpod state, go_router routing, `features/`, `services/`, `core/` |
| `packages/client-sdk/` | TypeScript SDK (ABI, cross-chain, explainability, risk routing) |
| `packages/python-sdk/` | Python SDK (mirrors TS SDK capabilities) |
| `research/` | Academic work (SIAM paper, adaptive-friction research) |

## Development Workflow

### Starting services

```powershell
.\START_SERVICES.ps1                    # Full stack (Docker + all services)
.\START_SERVICES.ps1 -BackendOnly       # Backend services only
.\START_SERVICES.ps1 -FrontendOnly      # Frontends only
.\START_SERVICES.ps1 -SkipDocker        # Skip Docker containers
```

Or use VS Code tasks: "Start Next.js Dev Server" (port 3006), "Start Flutter Web Server" (port 3010).

### Smart contracts

```bash
npx hardhat compile                                 # Compile
npx hardhat test                                    # Hardhat tests (Chai + ethers v6)
npx hardhat test test/AMTTPModular.test.cjs          # Specific test
forge test                                          # Foundry tests (in test/foundry/)
npx hardhat run scripts/deploy-modular.cjs --network localhost
```

Optimizer: 50 runs with `viaIR: true` (minimizes bytecode size, not runtime gas). Config: `hardhat.config.cjs`.

### ML pipeline

Python services force `CUDA_VISIBLE_DEVICES=""` for CPU-only container portability. Models in `ml/Automation/models/cloud/` (joblib + `*_meta.json`). ML test scripts are standalone Python files at the repo root (`test_mode*.py`, `test_no_leakage*.py`).

## Conventions

- **Next.js**: `'use client'` directive explicit on client components; server components by default. TanStack React Query for data fetching. Dark theme (`bg-gray-950`). Shared UI in `components/shared/`.
- **Flutter**: Riverpod exclusively (no Provider/Bloc). `ConsumerWidget` pattern. Design tokens in `core/theme/`. Web3 via raw `dart:js_util` interop (not a high-level package).
- **Python services**: FastAPI with Pydantic models, `Field(...)` descriptions. Each service runs on a fixed port (env-configurable). `asynccontextmanager` lifespan for startup/shutdown.
- **Solidity**: UUPS proxy pattern, `Initializable` (no constructors). Interface-based cross-contract calls (`IAMTTPPolicyManager`). Rich event emission. `onlyOracle` modifier for access control.
- **TypeScript backend**: Express Router, service functions imported from `*.service.js`, modular folder-per-domain structure.
- **RBAC**: Six roles R1–R6 (End User → Super Admin). Config shared at `frontend/shared/rbac_config.json`. R1–R2 = Focus Mode (Flutter), R3–R6 = War Room (Next.js).

## Testing

- **Smart contracts**: Hardhat (`.test.cjs` / `.test.mjs`, Chai `expect`, ethers v6) AND Foundry (Solidity tests) — both maintained in parallel.
- **ML pipeline**: Standalone Python scripts, NumPy/Polars/scikit-learn/XGBoost. Run from repo root: `py -3 test_mode4.py`.
- **Integration/API**: Tests in `tests/api-integration/`.
- **Other**: `tests/security/`, `tests/external-validation/`, `tests/ui/`.

## Port Map

| Port | Service |
|------|---------|
| 3006 | Next.js Dashboard |
| 3010 | Flutter Web App |
| 3001 | Oracle Service (TS) |
| 8000 | ML Risk API |
| 8001 | Graph Service |
| 8003–8006 | Policy, Sanctions, Monitoring, GeoRisk |
| 8007 | Compliance Orchestrator |
| 8008 | Integrity Service |
| 8009 | Explainability Service |
| 27017 | MongoDB |
| 6379 | Redis |
| 7687 | Memgraph |

## Common Pitfalls

- When editing design tokens (colors, spacing, typography), update **both** `design_tokens.dart` and `tailwind.config.ts` to keep Flutter and Next.js visually consistent.
- Smart contracts use UUPS proxies — use `upgrades.deployProxy(..., { kind: "uups" })` in tests, not direct deployment.
- The root `package.json` is for Hardhat/contracts only; frontend packages have their own `package.json` in `frontend/frontend/`.
- ML artifacts use Windows-absolute paths in some test scripts — use relative paths when possible.
- Hardhat config is CJS (`hardhat.config.cjs`) while contract tests may be ESM (`.mjs`) — be aware of module format.
