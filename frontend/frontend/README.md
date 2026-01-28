# AMTTP Next.js Dashboard

## Last Updated: January 22, 2026

The AMTTP Next.js dashboard provides a comprehensive compliance and monitoring interface for the Anti-Money Laundering Transaction Transfer Protocol.

## Features

### Authentication
- **Wallet Login**: Connect MetaMask or other Web3 wallets
- **Email/Password**: Traditional authentication
- **Demo Mode**: Test different roles without authentication

### Role-Based Access Control (RBAC)
Six-tier role hierarchy:
- **R1 End User**: Basic wallet user (Focus Mode)
- **R2 Enhanced User**: PEP-flagged user (Focus Mode)
- **R3 Institution Ops**: Operations team (War Room View)
- **R4 Compliance Officer**: Full War Room access
- **R5 Platform Admin**: Platform administration
- **R6 Super Admin**: Full system access

### Application Modes
- **Focus Mode** (`/focus`): Simplified interface for end users
- **War Room Mode** (`/war-room`): Full compliance dashboard for institutions

### Key Pages
| Route | Description | Required Role |
|-------|-------------|---------------|
| `/login` | Authentication page | Public |
| `/register` | User registration | Public |
| `/focus` | End user dashboard | R1, R2 |
| `/war-room` | Compliance dashboard | R3+ |
| `/war-room/compliance` | Compliance reports | R4+ |
| `/war-room/admin/roles` | Role management | R4+ |

## Getting Started

```bash
# Install dependencies
npm install

# Run development server (port 3006)
npm run dev -- -p 3006

# Or use the VS Code task
# Terminal > Run Task > Start Next.js Dev Server
```

Open [http://localhost:3006](http://localhost:3006) to view the dashboard.

### Demo Login
1. Go to `/login`
2. Click the **Demo** tab
3. Select a role (e.g., Super Admin)
4. Click **Enter Demo Mode**

### Test Credentials (Email Login)
- Email: `demo@amttp.io`
- Password: `Demo123!`

## Project Structure

```
src/
├── app/                    # Next.js app router pages
│   ├── login/              # Authentication
│   ├── register/           # Registration
│   ├── focus/              # End user mode
│   ├── war-room/           # Institutional mode
│   │   ├── admin/roles/    # Role management
│   │   ├── compliance/     # Compliance reports
│   │   └── ...
│   └── api/auth/           # Auth API routes
├── components/             # React components
│   ├── shells/             # Mode shells
│   ├── compliance/         # Compliance UI
│   └── ...
├── lib/                    # Services & utilities
│   ├── auth-context.tsx    # Auth state provider
│   ├── auth-service.ts     # Auth operations
│   ├── role-management-service.ts
│   └── ...
└── types/                  # TypeScript definitions
    ├── rbac.ts             # Role definitions
    ├── auth.ts             # Auth types
    └── role-management.ts  # Role management types
```

## Documentation

- [Authentication Guide](../../docs/AUTH_GUIDE.md)
- [Quick Start Guide](../../QUICK_START_GUIDE.md)
- [Developer Guide](../../DEVELOPER_GUIDE.md)

## Environment Variables

Create a `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8007
```

## Learn More

- [AMTTP Documentation](../../README.md)
- [Next.js Documentation](https://nextjs.org/docs)

