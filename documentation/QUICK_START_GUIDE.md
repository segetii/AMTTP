# Quick Start Guide

**Last Updated:** February 1, 2026

## Prerequisites

- Node.js 18+
- Flutter SDK (for consumer app development)
- Python 3.10+ (for backend services)
- MongoDB, Redis (or use Docker)

---

## Start All Services

```powershell
# Start everything with the script
.\START_SERVICES.ps1
```

---

## Manual Start

### 1. Next.js War Room (Institutional Dashboard)

```powershell
cd frontend\frontend
npm install
npm run dev -- -p 3006
```

Access: http://localhost:3006 → Opens to login page

### 2. Flutter Consumer App (End-User Wallet)

```powershell
cd frontend\amttp_app
flutter build web -t lib/main_consumer.dart
npx serve -s build/web -l 8889
```

Access: http://localhost:8889

### 3. Backend Orchestrator

```powershell
cd backend\compliance-service
python orchestrator.py
```

Access: http://localhost:8007/health

---

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Next.js War Room | http://localhost:3006 | Institutional compliance |
| Flutter Consumer | http://localhost:8889 | End-user wallet app |
| Orchestrator API | http://localhost:8007 | Main API gateway |
| ML Risk Engine | http://localhost:8000 | ML fraud detection |

---

## Authentication

The platform supports multiple authentication methods:

1. **Wallet Login**: Connect MetaMask (Sepolia testnet)
2. **Email/Password**: Traditional authentication  
3. **Demo Mode**: Test different roles (R3-R6)

**Demo Credentials:**
- Email: `demo@amttp.io`
- Password: `Demo123!`

---

## Role System

| Role | Access Level | Description |
|------|--------------|-------------|
| R1-R2 | Consumer | End-user (Flutter app) |
| R3 | Institution Ops | War Room view access |
| R4 | Compliance | War Room full access |
| R5 | Platform Admin | Platform administration |
| R6 | Super Admin | Full system access |

---

## Troubleshooting

- **Port in use**: Check `PORT_USAGE.md` for all port assignments
- **Wallet not connecting**: Ensure MetaMask is on Sepolia testnet
- **Build errors**: Run `flutter clean` or `npm run clean`
