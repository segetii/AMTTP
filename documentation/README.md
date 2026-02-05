# Documentation Index

**Last Updated:** February 1, 2026

This folder contains all key documentation for the AMTTP platform.

## Quick Links

| Document | Description |
|----------|-------------|
| [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) | How to start all services |
| [PORT_USAGE.md](PORT_USAGE.md) | Complete port reference |
| [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) | System architecture |

## Architecture & Design

| Document | Description |
|----------|-------------|
| [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) | High-level system architecture |
| [ML_ARCHITECTURE_DIAGRAM.md](ML_ARCHITECTURE_DIAGRAM.md) | ML pipeline and model details |
| [UI_ARCHITECTURE_MAP.md](UI_ARCHITECTURE_MAP.md) | UI/UX structure and routing |
| [AMTTP_UI_UX_Ground_Truth.md](AMTTP_UI_UX_Ground_Truth.md) | UI/UX ground truth document |

## Compliance & Regulatory

| Document | Description |
|----------|-------------|
| [FCA_COMPLIANCE.md](FCA_COMPLIANCE.md) | FCA regulatory compliance |
| [FATF_COMPLIANCE.md](FATF_COMPLIANCE.md) | FATF Travel Rule implementation |

## Implementation Guides

| Document | Description |
|----------|-------------|
| [FLUTTER_ML_DASHBOARD_GUIDE.md](FLUTTER_ML_DASHBOARD_GUIDE.md) | Flutter dashboard integration |
| [LABEL_UNIFICATION_GUIDE.md](LABEL_UNIFICATION_GUIDE.md) | Consistent labeling across apps |
| [EXPLAINABILITY.md](EXPLAINABILITY.md) | ML explainability features |

## Status & Summaries

| Document | Description |
|----------|-------------|
| [FINAL_STATUS.md](FINAL_STATUS.md) | Current implementation status |
| [SYSTEM_INTEGRATION_COMPLETE.md](SYSTEM_INTEGRATION_COMPLETE.md) | Integration completion notes |
| [COMPLETE_UI_FIXES_SUMMARY.md](COMPLETE_UI_FIXES_SUMMARY.md) | UI fixes summary |

## Flutter App Documentation

See also: `frontend/amttp_app/STANDARDIZATION_GUIDE.md` for Flutter-specific patterns.

## Current Platform Status (February 2026)

### ✅ Completed Features

- **Flutter Consumer App**: Standardized with design tokens, real MetaMask wallet integration
- **Next.js War Room**: Login page as entry point, multi-method authentication
- **RBAC System**: 6-tier role hierarchy (R1-R6) with granular permissions
- **ML Risk Engine**: Stacked ensemble with GraphSAGE + LGBM + XGBoost
- **Compliance Services**: Sanctions, monitoring, geographic risk, policy engine

### 🔄 Recent Changes

- SIEM Dashboard removed from platform
- War Room opens directly to sign-in page
- Flutter app uses real wallet data (not mock data)
- Sepolia testnet as default network
