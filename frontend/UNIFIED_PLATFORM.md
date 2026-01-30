# AMTTP Unified Platform Architecture

## Overview

The AMTTP platform consists of two frontend applications that share authentication and design tokens:

| App | Technology | Port (Dev) | Path (Prod) | Purpose |
|-----|------------|------------|-------------|---------|
| **Wallet App** | Flutter Web | 3010 | `/` | End-user interface for transfers, trust checks, wallet management |
| **War Room** | Next.js | 3006 | `/war-room` | Institutional dashboard for compliance, monitoring, administration |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AMTTP Platform                                     │
│                        (app.amttp.io or localhost)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│    ┌─────────────────────────────┐    ┌─────────────────────────────┐       │
│    │      Platform Header        │    │      Platform Header        │       │
│    │  [AMTTP] [Wallet ▼]        │    │  [AMTTP] [War Room ▼]       │       │
│    │   ↓ App Switcher Dropdown   │    │   ↓ App Switcher Dropdown   │       │
│    │   • Wallet App (Active)     │    │   • Wallet App              │       │
│    │   • War Room                │    │   • War Room (Active)       │       │
│    ├─────────────────────────────┤    ├─────────────────────────────┤       │
│    │                             │    │                              │       │
│    │     Flutter Wallet App      │    │     Next.js War Room         │       │
│    │                             │    │                              │       │
│    │  • Home / Balance           │    │  • Risk Dashboards           │       │
│    │  • Transfer / Send          │    │  • Alert Queue               │       │
│    │  • Trust Check              │    │  • Entity Investigation      │       │
│    │  • Wallet Connect           │    │  • Compliance Reports        │       │
│    │  • Disputes (User Side)     │    │  • Policy Management         │       │
│    │  • Profile & Settings       │    │  • Team & Roles              │       │
│    │                             │    │                              │       │
│    └─────────────────────────────┘    └─────────────────────────────┘       │
│              │                                    │                          │
│              └──────────────┬─────────────────────┘                          │
│                             │                                                │
│    ┌────────────────────────┴────────────────────────┐                       │
│    │              Shared Resources                    │                       │
│    │                                                  │                       │
│    │  • design-tokens.json (colors, radii, spacing)  │                       │
│    │  • SharedSession (localStorage)                  │                       │
│    │  • Backend APIs (orchestrator:8007)              │                       │
│    │  • RBAC Role System (R1-R6)                      │                       │
│    └──────────────────────────────────────────────────┘                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Shared Components

### 1. Platform App Switcher

Both apps include a header with an app switcher dropdown:

**Flutter** (`lib/shared/widgets/platform_app_switcher.dart`):
```dart
CompactPlatformHeader(currentApp: 'wallet')
```

**Next.js** (`src/components/shared/PlatformAppSwitcher.tsx`):
```tsx
<PlatformAppSwitcher currentApp="war-room" />
```

### 2. Shared Authentication

Session data is stored in `localStorage` with shared keys:

| Key | Description |
|-----|-------------|
| `amttp_session` | JSON object with address, role, mode, expiresAt |
| `amttp_auth_token` | JWT token (if using real auth) |

**Flutter** (`lib/core/auth/shared_auth_service.dart`):
```dart
final auth = SharedAuthService();
await auth.loginDemo(address: '0x...', role: 'R1');
```

**Next.js** (`src/lib/shared-auth.ts`):
```typescript
import { getSharedSession, saveSharedSession } from '@/lib/shared-auth';
const session = getSharedSession();
```

### 3. Design Tokens

Shared color and spacing values in `frontend/design-tokens.json`:

```json
{
  "colors": {
    "primary": "#3B82F6",
    "background": "#0A0A0F",
    "surface": "#0F0F14",
    "text": "#F1F5F9",
    "mutedText": "#94A3B8"
  }
}
```

## Development Setup

### Start Both Apps

```powershell
# Terminal 1: Flutter Wallet App
cd frontend/amttp_app
flutter run -d chrome --web-port=3010

# Terminal 2: Next.js War Room
cd frontend/frontend
npm run dev -- -p 3006
```

Or use VS Code tasks:
- `Start Flutter Web Server`
- `Start Next.js Dev Server`

### URLs

| Environment | Wallet App | War Room |
|-------------|------------|----------|
| Development | http://localhost:3010 | http://localhost:3006 |
| Production | https://app.amttp.io | https://app.amttp.io/war-room |

## Production Deployment

### Nginx Configuration

Use `docker/nginx/amttp-platform.conf`:

```nginx
# Wallet App (default)
location / {
    proxy_pass http://flutter_app:3010;
}

# War Room
location /war-room {
    proxy_pass http://nextjs_app:3006;
}

# API
location /api/ {
    proxy_pass http://orchestrator:8007/;
}
```

### Docker Compose

```yaml
services:
  flutter-app:
    build: ./frontend/amttp_app
    ports:
      - "3010:3010"
  
  nextjs-app:
    build: ./frontend/frontend
    ports:
      - "3006:3006"
  
  nginx:
    image: nginx:alpine
    volumes:
      - ./docker/nginx/amttp-platform.conf:/etc/nginx/conf.d/default.conf
    ports:
      - "80:80"
    depends_on:
      - flutter-app
      - nextjs-app
```

## Role-Based Routing

| Role | Default App | Description |
|------|-------------|-------------|
| R1 (End User) | Wallet | Individual users making transfers |
| R2 (Power User) | Wallet | Users with advanced features |
| R3 (Analyst) | War Room | Risk analysts reviewing alerts |
| R4 (Compliance) | War Room | Compliance officers |
| R5 (Admin) | War Room | Platform administrators |
| R6 (Super Admin) | War Room | Full system access |

The app switcher allows any authenticated user to switch between apps, but certain features are role-gated within each app.

## Files Reference

| File | Purpose |
|------|---------|
| `frontend/amttp_app/lib/shared/widgets/platform_app_switcher.dart` | Flutter app switcher |
| `frontend/amttp_app/lib/core/auth/shared_auth_service.dart` | Flutter shared auth |
| `frontend/frontend/src/components/shared/PlatformAppSwitcher.tsx` | Next.js app switcher |
| `frontend/frontend/src/lib/shared-auth.ts` | Next.js shared auth utilities |
| `frontend/design-tokens.json` | Shared design tokens |
| `docker/nginx/amttp-platform.conf` | Production nginx config |
