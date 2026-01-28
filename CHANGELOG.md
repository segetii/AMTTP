# AMTTP Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] - 2026-01-22

### Added

#### Authentication System
- **Multi-method authentication** - Support for wallet, email/password, and demo mode login
- **Registration page** (`/register`) - New user registration with wallet or email
- **Password validation** - Enforced complexity requirements (8+ chars, uppercase, lowercase, number, special char)
- **Password strength indicator** - Real-time visual feedback during registration
- **API routes for auth** - `/api/auth/register`, `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- **Wallet detection** - Automatic detection of MetaMask, Coinbase Wallet, and other providers
- **Session management** - localStorage-based session persistence

#### Role Management System
- **Role management page** (`/war-room/admin/roles`) - Admin interface for managing users
- **User creation** - Create new users with assigned roles and institutions
- **Role editing** - Change user roles with audit logging
- **User suspension/reactivation** - Temporarily disable user access
- **Audit logging** - Complete trail of all role changes
- **Permission hierarchy** - Super Admin > Platform Admin > Compliance > Ops
- **Institution filtering** - Filter users by institution

#### New Types & Services
- `src/types/auth.ts` - Authentication type definitions
- `src/types/role-management.ts` - Role management types, institutions, permissions
- `src/lib/auth-service.ts` - Authentication operations and wallet integration
- `src/lib/role-management-service.ts` - Role management service with CRUD operations

#### Login Page Enhancements
- Added Platform Admin (R5) and Super Admin (R6) to demo mode options
- Tabbed interface for wallet/email/demo login methods
- Link to registration page

#### Navigation Updates
- Added "Role Management" link to War Room sidebar (System section)
- New UserCog icon for role management

### Changed

- Updated `README.md` with authentication section and new documentation links
- Updated `QUICK_START_GUIDE.md` with login instructions and demo credentials
- Updated `DEVELOPER_GUIDE.md` with authentication and authorization code examples
- Updated `FILE_INDEX.md` with new frontend file structure
- Updated `AMTTP_ROADMAP.md` with completed Sprint 11 and auth system status
- Updated `PROJECT_DOCUMENTATION.md` version to 2.1.0
- Updated `frontend/frontend/README.md` with comprehensive dashboard documentation

### Documentation

- Created `docs/AUTH_GUIDE.md` - Comprehensive authentication and authorization guide
- Added role hierarchy diagrams
- Added capability matrix
- Added API reference for auth endpoints
- Added security considerations

---

## [2.0.0] - 2026-01-19

### Added

#### Sprint 11: Compliance Reporting & Export
- **Snapshot Explorer** - Browse, filter, and verify UI snapshots
- **Evidence Chain** - Evidence linking with list and timeline views
- **Report Generator** - Create and export reports (PDF, JSON, CSV, HTML)
- **Chain Replay Tool** - Step-by-step UI replay with visual diffs
- **Compliance Dashboard** - 4-tab interface at `/war-room/compliance`

#### Compliance Report Types
- `src/types/compliance-report.ts` - Report type definitions
- `src/lib/compliance-report-service.ts` - Report generation service
- Export formats: PDF, JSON, CSV, HTML

### Changed

- Enhanced WarRoomShell with compliance navigation
- Added compliance reports to role capabilities

---

## [1.9.0] - 2026-01-15

### Added

#### UI Snapshot Chain
- `src/lib/ui-snapshot-chain.ts` - UI integrity verification system
- Cryptographic hashing of UI state
- Snapshot history tracking
- Verification against expected states

#### Trust Components
- `TrustScoreBadge` - Visual trust score indicator
- `ConfidenceIndicator` - ML confidence display
- Risk visualization components

---

## [1.8.0] - 2026-01-10

### Added

#### RBAC System
- 6-tier role hierarchy (R1-R6)
- `src/types/rbac.ts` - Role definitions and capabilities
- `src/lib/auth-context.tsx` - Authentication state provider
- Mode switching (Focus/War Room)
- Route protection based on roles

#### Mode Shells
- `FocusShell` - Simplified end-user interface
- `WarRoomShell` - Full institutional dashboard

---

## [1.7.0] - 2025-12-20

### Added

- Cross-chain status display
- Policy engine UI
- Escrow & Dispute components
- Multisig governance UI

---

## [1.6.0] - 2025-12-01

### Added

- ML baseline dashboard
- Risk scoring visualization
- Explainability service integration

---

## [1.5.0] - 2025-11-15

### Added

- LayerZero cross-chain integration
- MetaMask Snap for transaction insights
- Kleros dispute resolution

---

## [1.0.0] - 2025-09-22

### Added

- Initial release
- Smart contract deployment (AMTTPStreamlined, PolicyManager, PolicyEngine)
- ML pipeline with XGBoost + Graph ML
- Compliance services (Sanctions, Monitoring, GeoRisk)
- Orchestrator API
- Flutter web app
- Next.js dashboard

---

## File Changes Summary (v2.1.0)

### New Files Created
```
frontend/frontend/src/types/auth.ts
frontend/frontend/src/types/role-management.ts
frontend/frontend/src/lib/auth-service.ts
frontend/frontend/src/lib/role-management-service.ts
frontend/frontend/src/app/register/page.tsx
frontend/frontend/src/app/war-room/admin/roles/page.tsx
frontend/frontend/src/app/api/auth/register/route.ts
frontend/frontend/src/app/api/auth/login/route.ts
frontend/frontend/src/app/api/auth/logout/route.ts
frontend/frontend/src/app/api/auth/me/route.ts
docs/AUTH_GUIDE.md
CHANGELOG.md
```

### Modified Files
```
frontend/frontend/src/app/login/page.tsx
frontend/frontend/src/components/shells/WarRoomShell.tsx
README.md
QUICK_START_GUIDE.md
DEVELOPER_GUIDE.md
FILE_INDEX.md
AMTTP_ROADMAP.md
PROJECT_DOCUMENTATION.md
frontend/frontend/README.md
```
