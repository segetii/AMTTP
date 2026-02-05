# Start Here

**Last Updated:** February 1, 2026

Welcome to AMTTP! This guide will help you get started quickly.

---

## Quick Start

1. **Read the Documentation Index**: [documentation/README.md](README.md)
2. **Start Services**: [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)
3. **Understand Ports**: [PORT_USAGE.md](PORT_USAGE.md)

---

## Platform Overview

AMTTP is a DeFi compliance platform with two main applications:

### For End Users (Flutter Consumer App)
- Connect MetaMask wallet
- Send/receive funds with risk assessment
- View transaction history
- **URL**: http://localhost:8889

### For Institutions (Next.js War Room)
- Monitor transactions
- Review flagged activity
- Manage compliance policies
- **URL**: http://localhost:3006

---

## Key Documentation

| Topic | Document |
|-------|----------|
| Setup | [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) |
| Architecture | [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) |
| ML System | [ML_ARCHITECTURE_DIAGRAM.md](ML_ARCHITECTURE_DIAGRAM.md) |
| Explainability | [EXPLAINABILITY.md](EXPLAINABILITY.md) |
| UI Structure | [UI_ARCHITECTURE_MAP.md](UI_ARCHITECTURE_MAP.md) |
| Flutter Guide | `frontend/amttp_app/STANDARDIZATION_GUIDE.md` |

---

## Development

### Flutter Consumer App
```powershell
cd frontend\amttp_app
flutter build web -t lib/main_consumer.dart
npx serve -s build/web -l 8889
```

### Next.js War Room
```powershell
cd frontend\frontend
npm run dev -- -p 3006
```

---

## Authentication

The platform supports:
- **Wallet Login**: MetaMask (Sepolia testnet)
- **Email/Password**: Traditional auth
- **Demo Mode**: Test different roles

**Test Credentials**: `demo@amttp.io` / `Demo123!`
