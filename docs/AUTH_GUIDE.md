# AMTTP Authentication & Authorization Guide

## Last Updated: February 1, 2026

This document describes the authentication system, role-based access control (RBAC), and user management features in AMTTP.

---

## 📋 Table of Contents

1. [Authentication Methods](#authentication-methods)
2. [Role Hierarchy](#role-hierarchy)
3. [Application Modes](#application-modes)
4. [Role Capabilities](#role-capabilities)
5. [Role Management](#role-management)
6. [API Reference](#api-reference)
7. [Security Considerations](#security-considerations)

---

## 🏠 Entry Points

| Application | URL | Entry Point |
|-------------|-----|-------------|
| Flutter Consumer | http://localhost:8889 | Home (wallet connect) |
| Next.js War Room | http://localhost:3006 | Login page |

> **Note:** The War Room now opens directly to the login page. The SIEM dashboard has been removed.

---

## 🔐 Authentication Methods

### 1. Wallet-Based Authentication (Web3)

The recommended authentication method for DeFi users.

**Supported Wallets:**
- MetaMask (primary)
- Coinbase Wallet
- WalletConnect
- Other injected Web3 providers

**Flow:**
1. User clicks "Connect Wallet"
2. Wallet prompts for account access
3. User approves connection
4. System retrieves wallet address
5. Session is created with address as identifier

```typescript
import { connectWallet, signMessage } from '@/lib/auth-service';

// Connect wallet
const result = await connectWallet();
// result: { address: '0x123...', chainId: 1 }

// Optional: Sign-In with Ethereum (SIWE)
const signature = await signMessage(siweMessage);
```

### 2. Email/Password Authentication

Traditional authentication for users without crypto wallets.

**Password Requirements:**
- Minimum 8 characters
- At least one uppercase letter (A-Z)
- At least one lowercase letter (a-z)
- At least one number (0-9)
- At least one special character (!@#$%^&*)

**Flow:**
1. User registers with email, password, and display name
2. System creates account and session
3. User can login with email/password

```typescript
// Register
POST /api/auth/register
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "displayName": "John Doe",
  "authMethod": "email"
}

// Login
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "authMethod": "email"
}
```

### 3. Demo Mode

For testing and development purposes only.

**Flow:**
1. User selects desired role
2. System creates temporary session with selected role
3. Full access to features for that role (mock data)

---

## 👥 Role Hierarchy

AMTTP uses a 6-tier role hierarchy:

```
┌─────────────────────────────────────────────────────────────────┐
│  R6 - SUPER ADMIN                                               │
│  Full system access, emergency override, all role management    │
├─────────────────────────────────────────────────────────────────┤
│  R5 - PLATFORM ADMIN                                            │
│  Platform administration, user management (up to R4)            │
├─────────────────────────────────────────────────────────────────┤
│  R4 - INSTITUTION COMPLIANCE                                    │
│  Full War Room, enforcement, policy editing, user mgmt (R1-R3)  │
├─────────────────────────────────────────────────────────────────┤
│  R3 - INSTITUTION OPS                                           │
│  War Room (view-only), monitoring, audit logs                   │
├─────────────────────────────────────────────────────────────────┤
│  R2 - END USER (PEP)                                            │
│  Focus Mode, enhanced monitoring, PEP-flagged                   │
├─────────────────────────────────────────────────────────────────┤
│  R1 - END USER                                                  │
│  Focus Mode, basic transactions, personal wallet                │
└─────────────────────────────────────────────────────────────────┘
```

### Role Definitions

| Role | Code | Description |
|------|------|-------------|
| End User | `R1_END_USER` | Basic personal wallet user |
| Enhanced User | `R2_END_USER_PEP` | Politically Exposed Person - enhanced monitoring |
| Institution Ops | `R3_INSTITUTION_OPS` | Operations team member |
| Compliance Officer | `R4_INSTITUTION_COMPLIANCE` | Compliance and enforcement |
| Platform Admin | `R5_PLATFORM_ADMIN` | Platform-wide administration |
| Super Admin | `R6_SUPER_ADMIN` | Full system access |

---

## 🖥️ Application Modes

Roles determine which application mode users access:

### Focus Mode (R1, R2)
- Simplified, personal wallet interface
- Transaction initiation
- Personal risk analysis
- Account settings

**URL:** `/focus`

### War Room Mode (R3, R4, R5, R6)
- Full compliance dashboard
- Transaction monitoring
- Detection studio
- Policy management
- Multisig actions
- Role management (R4+)

**URL:** `/war-room`

---

## 🔑 Role Capabilities

### Capability Matrix

| Capability | R1 | R2 | R3 | R4 | R5 | R6 |
|------------|:--:|:--:|:--:|:--:|:--:|:--:|
| Initiate Own Transactions | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Access Detection Studio | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| Edit Policies | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Trigger Enforcement | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Sign Multisig | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Verify UI Snapshot | View | View | View | Full | Full | Full |
| Emergency Override | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Manage Users | ❌ | ❌ | ❌ | ✅* | ✅* | ✅ |

*Limited to roles below their own level

### Using Capabilities in Code

```typescript
import { useAuth } from '@/lib/auth-context';

function MyComponent() {
  const { capabilities, canEnforce, isInstitutional } = useAuth();
  
  return (
    <div>
      {capabilities?.canEditPolicies && (
        <button>Edit Policy</button>
      )}
      
      {capabilities?.canTriggerEnforcement && (
        <button>Freeze Account</button>
      )}
      
      {capabilities?.canEmergencyOverride && (
        <button className="danger">Emergency Override</button>
      )}
    </div>
  );
}
```

---

## 👨‍💼 Role Management

### Who Can Manage Roles

| Manager Role | Can Assign Roles |
|--------------|------------------|
| R6 Super Admin | R1, R2, R3, R4, R5, R6 |
| R5 Platform Admin | R1, R2, R3, R4 |
| R4 Compliance | R1, R2, R3 |
| R3 and below | Cannot assign roles |

### Accessing Role Management

1. Login with R4+ role
2. Navigate to **War Room** → **System** → **Role Management**
3. URL: `/war-room/admin/roles`

### Available Actions

- **View Users**: See all users (filtered by institution if applicable)
- **Create User**: Add new users with assigned roles
- **Edit Role**: Change a user's role (within your permission level)
- **Suspend User**: Temporarily disable access
- **Reactivate User**: Restore suspended user access
- **View Audit Log**: See history of all role changes

### Audit Logging

All role changes are logged with:
- Action type (assigned, changed, revoked, suspended, reactivated)
- Target user
- Performed by (admin)
- Timestamp
- Previous and new role
- Reason (required for changes)

---

## 📡 API Reference

### Authentication Endpoints

```typescript
// Register new user
POST /api/auth/register
Request: {
  email?: string;
  password?: string;
  walletAddress?: string;
  displayName: string;
  authMethod: 'email' | 'wallet';
}
Response: {
  success: boolean;
  user: { id, email, walletAddress, displayName, createdAt };
  sessionToken: string;
}

// Login
POST /api/auth/login
Request: {
  email?: string;
  password?: string;
  walletAddress?: string;
  signature?: string;
  authMethod: 'email' | 'wallet';
}
Response: {
  success: boolean;
  user: { id, email, walletAddress, displayName };
  sessionToken: string;
  refreshToken: string;
  expiresAt: string;
}

// Logout
POST /api/auth/logout
Headers: { Authorization: 'Bearer <token>' }
Response: { success: boolean; message: string; }

// Get current session
GET /api/auth/me
Headers: { Authorization: 'Bearer <token>' }
Response: {
  success: boolean;
  user: { ... };
  session: { token, expiresAt };
}
```

### Using the Auth Context

```typescript
import { useAuth, AuthProvider } from '@/lib/auth-context';

// Wrap your app
function App() {
  return (
    <AuthProvider>
      <MyComponent />
    </AuthProvider>
  );
}

// Use in components
function MyComponent() {
  const {
    // Auth state
    isAuthenticated,
    isLoading,
    session,
    
    // Role info
    role,
    mode,
    capabilities,
    
    // Helpers
    canAccess,
    isEndUser,
    isInstitutional,
    canEnforce,
    
    // Display
    roleLabel,
    roleColor,
    modeLabel,
    
    // Actions
    login,
    logout,
    switchRole, // Demo only
  } = useAuth();
  
  // Check route access
  if (!canAccess('/war-room/policies')) {
    return <AccessDenied />;
  }
  
  return <div>Welcome, {roleLabel}!</div>;
}
```

---

## 🔒 Security Considerations

### Session Storage
- Sessions stored in `localStorage` with key `amttp_session`
- Tokens should be short-lived (24 hours default)
- Refresh tokens for extended sessions

### Password Security
- Passwords are hashed (bcrypt in production)
- Never stored in plain text
- Minimum complexity requirements enforced

### Wallet Security
- Never request private keys
- Use personal_sign for authentication
- Verify signatures server-side

### Role Security
- Roles are RBAC-locked, not user-selectable
- Role changes require admin action
- All changes are audit-logged
- Principle of least privilege

### Best Practices
1. Always use HTTPS in production
2. Implement rate limiting on auth endpoints
3. Use secure, HTTP-only cookies for sensitive tokens
4. Implement 2FA for high-privilege roles
5. Regular audit log review
6. Session timeout for inactive users

---

## 📁 Related Files

| File | Description |
|------|-------------|
| `src/types/rbac.ts` | Role definitions and capabilities |
| `src/types/auth.ts` | Authentication type definitions |
| `src/types/role-management.ts` | Role management types |
| `src/lib/auth-context.tsx` | Auth state provider |
| `src/lib/auth-service.ts` | Auth operations and wallet integration |
| `src/lib/role-management-service.ts` | Role management service |
| `src/app/login/page.tsx` | Login page with all auth methods |
| `src/app/register/page.tsx` | Registration page |
| `src/app/war-room/admin/roles/page.tsx` | Role management UI |
| `src/app/api/auth/*` | Authentication API routes |

---

## 🔗 Quick Links

- [Login Page](/login)
- [Register Page](/register)
- [Role Management](/war-room/admin/roles) (R4+ required)
- [Focus Mode Dashboard](/focus)
- [War Room Dashboard](/war-room)
