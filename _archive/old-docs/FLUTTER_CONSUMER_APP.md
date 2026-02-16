# Flutter Consumer App - Streamlined Architecture

## Overview

The Flutter app is now **consumer-focused only**. Institutional users (exchanges, fintechs, compliance teams) use the **Next.js War Room** instead.

## Architecture Separation

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AMTTP Platform Architecture                     │
├─────────────────────────────────┬───────────────────────────────────┤
│     Flutter Consumer App        │       Next.js War Room            │
│         (End Users)             │       (Institutions)              │
├─────────────────────────────────┼───────────────────────────────────┤
│ ✅ Home Dashboard               │ ✅ War Room Dashboard             │
│ ✅ Wallet (Tokens, NFTs)        │ ✅ Detection Studio               │
│ ✅ Transfer (Send with Trust)   │ ✅ Graph Explorer                 │
│ ✅ Trust Check                  │ ✅ Policy Engine                  │
│ ✅ History                      │ ✅ Compliance Tools               │
│ ✅ Disputes (View/Raise)        │ ✅ Enforcement Actions            │
│ ✅ Wallet Connect               │ ✅ User Management                │
│ ✅ Profile/Settings             │ ✅ Reports & Audit                │
│                                 │ ✅ ML Models                      │
│                                 │ ✅ Multisig Queue                 │
└─────────────────────────────────┴───────────────────────────────────┘
```

## Consumer App Features (Flutter)

### Core Pages

| Page | Route | Description |
|------|-------|-------------|
| Home | `/` | Main dashboard with balance, quick actions |
| Wallet | `/wallet` | Token balances, NFTs, receive address |
| Transfer | `/transfer` | Send tokens with pre-transfer trust check |
| Trust Check | `/trust-check` | Verify recipient before sending |
| History | `/history` | Transaction history and status |
| Disputes | `/disputes` | View and raise disputes |
| Wallet Connect | `/wallet-connect` | Connect external wallets |
| Profile | `/profile` | User settings and preferences |

### Removed from Consumer App

These pages are **NOT** in the consumer app - they're in Next.js War Room:

- ❌ War Room / Detection Studio
- ❌ Policy Engine / Compliance Tools  
- ❌ ML Models / Graph Explorer
- ❌ User Management / Admin
- ❌ Audit Chain Replay
- ❌ Enforcement Actions
- ❌ Multisig Queue

## Running the Apps

### Consumer Flutter App

```bash
# Development
cd frontend/amttp_app
flutter run -t lib/main_consumer.dart

# Build for web
flutter build web -t lib/main_consumer.dart

# Serve
cd build/web && npx serve -s -l 8889
```

### Next.js War Room (Institutions)

```bash
cd frontend/frontend
npm run dev -- -p 3006

# Access at http://localhost:3006/war-room
```

## File Structure

```
frontend/
├── amttp_app/                    # Flutter Consumer App
│   ├── lib/
│   │   ├── main_consumer.dart    # ← Consumer entry point
│   │   ├── main.dart             # Full app (includes institutional)
│   │   ├── core/
│   │   │   └── router/
│   │   │       ├── consumer_app_router.dart  # ← Clean consumer routes
│   │   │       └── app_router.dart           # Full routes (all roles)
│   │   └── features/
│   │       ├── home/             # ✅ Consumer
│   │       ├── wallet/           # ✅ Consumer
│   │       ├── transfer/         # ✅ Consumer
│   │       ├── trust_check/      # ✅ Consumer
│   │       ├── history/          # ✅ Consumer
│   │       ├── disputes/         # ✅ Consumer
│   │       ├── settings/         # ✅ Consumer
│   │       ├── wallet_connect/   # ✅ Consumer
│   │       ├── auth/             # ✅ Consumer
│   │       ├── war_room/         # ❌ Institutional (Next.js)
│   │       ├── detection_studio/ # ❌ Institutional (Next.js)
│   │       ├── compliance/       # ❌ Institutional (Next.js)
│   │       ├── ml_models/        # ❌ Institutional (Next.js)
│   │       └── admin/            # ❌ Institutional (Next.js)
│
└── frontend/                     # Next.js War Room
    └── src/app/war-room/         # All institutional pages
```

## Consumer App Entry Points

| Entry Point | Use Case |
|-------------|----------|
| `lib/main_consumer.dart` | Production consumer app |
| `lib/main.dart` | Full app with all roles (dev/testing) |

## Benefits of Separation

1. **Smaller Bundle**: Consumer app doesn't include institutional code
2. **Cleaner UX**: End users see only what they need
3. **Security**: Institutional tools not exposed to consumers
4. **Maintainability**: Clear separation of concerns
5. **Performance**: Faster load times for consumer app
