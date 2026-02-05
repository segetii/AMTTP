# UI Architecture Map

**Last Updated:** February 1, 2026

## Overview

AMTTP uses a hybrid architecture with two frontend applications:

1. **Flutter Consumer App** - End-user wallet interface
2. **Next.js War Room** - Institutional compliance console

---

## Flutter Consumer App (Port 8889)

Entry point: `lib/main_consumer.dart`

### Routes

| Route | Page | Description |
|-------|------|-------------|
| `/` | Home | Wallet overview, balance, quick actions |
| `/transfer` | Transfer | Send funds with risk assessment |
| `/transactions` | Transactions | Transaction history |
| `/settings` | Settings | App preferences |

### Architecture

```
lib/
├── core/                   # Core infrastructure
│   ├── theme/              # Design tokens, typography, spacing
│   ├── router/             # Route definitions
│   ├── constants/          # API endpoints, feature flags
│   ├── services/           # API client, result types
│   ├── web3/               # Wallet integration
│   └── rbac/               # Role-based access
│
├── shared/                 # Reusable components
│   ├── models/             # Data models
│   ├── widgets/            # Standard UI components
│   ├── layout/             # Layout components
│   └── shells/             # App shells/wrappers
│
└── features/               # Feature modules
    ├── home/
    ├── transfer/
    ├── transactions/
    └── settings/
```

### Wallet Integration

- **MetaMask** via `dart:js_util` and `dart:html`
- **Network**: Sepolia Testnet (chainId: 0xaa36a7)
- **Real Data**: Live ETH balance and address from connected wallet

---

## Next.js War Room (Port 3006)

Entry point: `src/app/page.tsx` → Redirects to `/login`

### Routes

| Route | Page | Description |
|-------|------|-------------|
| `/login` | Login | Multi-method authentication |
| `/register` | Register | New user registration |
| `/war-room` | Dashboard | Main War Room dashboard |
| `/war-room/landing` | Landing | War Room section overview |
| `/war-room/alerts` | Alerts | Active alerts |
| `/war-room/transactions` | Transactions | Transaction monitoring |
| `/war-room/flagged-queue` | Flagged Queue | Review flagged transactions |
| `/war-room/compliance` | Compliance | Compliance dashboard |
| `/war-room/policy-engine` | Policy Engine | Policy configuration |
| `/war-room/disputes` | Disputes | Dispute management |
| `/war-room/enforcement` | Enforcement | Account freeze/unfreeze |
| `/war-room/detection-studio` | Detection Studio | ML model configuration |
| `/war-room/detection/graph` | Graph Explorer | Transaction graph analysis |
| `/war-room/detection/models` | ML Models | Model performance |
| `/war-room/detection/risk` | Risk Scoring | Risk score configuration |
| `/war-room/audit` | Audit Trail | Complete audit log |
| `/war-room/reports` | Reports | Generate reports |
| `/war-room/user-management` | Users | Manage team members |
| `/war-room/admin/roles` | Roles | Role permissions |
| `/war-room/settings` | Settings | War Room settings |
| `/war-room/system-settings` | System | Platform configuration |

### Authentication

The War Room supports three authentication methods:

1. **Wallet Login**: MetaMask/WalletConnect
2. **Email/Password**: Traditional authentication
3. **Demo Mode**: Select role (R3-R6) for testing

### Role Access

| Role | Access Level |
|------|--------------|
| R3 - Institution Ops | War Room (View) |
| R4 - Compliance | War Room (Full) |
| R5 - Platform Admin | War Room (Admin) |
| R6 - Super Admin | War Room (Super) |

---

## Removed Components

The following components have been removed from the platform:

- `SIEMDashboard.tsx` - Removed
- `SIEMDashboardImproved.tsx` - Removed
- `src/types/siem.ts` - Removed
- Related chart components (`AlertsTable.tsx`, `TimelineChart.tsx`, `RiskDistributionChart.tsx` in components folder)

**Note**: The Detection Studio still uses its own `RiskDistributionChart` from `src/components/detection/`.

---

## Explainability Integration

All alert and decision views support explainability modals:

- Click any alert to view ML explanation
- Key risk factors with impact scores
- Detected fraud typologies
- Graph/network context
- Recommended actions

The Explainability Service runs on port 8009.
