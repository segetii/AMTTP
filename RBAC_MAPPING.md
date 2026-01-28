# RBAC Mapping, Wireframes, and TODOs

This document captures the final mapping of Flutter/Next.js pages to RBAC roles (R1–R6), the high‑level wireframes per role, and concrete TODOs to align navigation and implementation.

---

## 1. Roles Overview

From `lib/core/rbac/roles.dart`:

- **R1 – End User** (`Role.r1EndUser`)
- **R2 – Power User / PEP** (`Role.r2EndUserPep`)
- **R3 – Institution Ops** (`Role.r3InstitutionOps`)
- **R4 – Institution Compliance** (`Role.r4InstitutionCompliance`)
- **R5 – Platform Admin** (`Role.r5PlatformAdmin`)
- **R6 – Super Admin / Auditor** (`Role.r6SuperAdmin`)

App modes:

- **Focus Mode** – R1/R2 (no sidebar, bottom nav only).
- **War Room Mode** – R3–R6 (sidebar shell, institutional views).

---

## 2. Route → Role Matrix (Flutter Routes)

Legend:

- `full` – normal use (read/write).
- `ro` – read‑only (view only).
- `n/a` – not visible / not intended for that role.

### 2.1 Auth & System

| Route                 | Page                       | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|-----------------------|----------------------------|-----|-----|-----|-----|-----|-----|-------|
| `/sign-in`           | `SignInPage`               | full| full| full| full| full| full| All roles can authenticate here. |
| `/register`          | `RegisterPage`             | opt | opt | n/a | n/a | n/a | n/a | Optional; mainly for R1/R2 if used. |
| `/unauthorized`      | `UnauthorizedPage`         | ro  | ro  | ro  | ro  | ro  | ro  | Shown on RBAC/route violations. |
| `/select-profile`    | `ProfileSelectorPage`      | demo| demo| demo| demo| demo| demo| Demo/onboarding only (non‑prod). |

Legacy visual variants (not routed in production): `LightSignInPage`.

---

### 2.2 Core End‑User Flows

| Route        | Page            | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|--------------|-----------------|-----|-----|-----|-----|-----|-----|-------|
| `/`          | `HomePage`      | full| full| ro  | ro  | ro  | ro  | Primary home for R1/R2. Others may see a minimal landing. |
| `/wallet`    | `WalletPage`    | full| full| ro  | ro  | ro  | ro  | Wallet balances; R3+ may view in case context. |
| `/transfer`  | `TransferPage`  | full| full| n/a | n/a | n/a | n/a | Only end users initiate transfers. |
| `/history`   | `HistoryPage`   | full| full| ro  | ro  | ro  | ro  | Transaction history, used as context for investigations. |
| `/trust-check` | `TrustCheckPage` | full| full| full| full| ro  | ro  | Quick risk check; R3/R4 use heavily. |

Legacy visual variants (not primary): `FocusHomePage`, `LightHomePage`.

---

### 2.3 Advanced / Pro User Features

| Route           | Page                 | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|-----------------|----------------------|-----|-----|-----|-----|-----|-----|-------|
| `/nft-swap`     | `NFTSwapPage`        | n/a | full| ro  | ro  | ro  | ro  | R2 swaps; R3+ view in investigations. |
| `/zknaf`        | `ZkNAFPage`          | n/a | full| ro  | ro  | ro  | ro  | Privacy attestations; R3+ view attestations read‑only. |
| `/safe`         | `SafeManagementPage` | n/a | full| ro  | ro  | full| ro  | R2 manages personal safes; R5 manages system safes. |
| `/session-keys` | `SessionKeyPage`     | n/a | full| ro  | ro  | full| ro  | R2 creates keys; R5 supervises/revokes. |
| `/cross-chain`  | `CrossChainPage`     | n/a | full| ro  | ro  | ro  | ro  | R2 uses cross‑chain; R3+ see flows for context. |

---

### 2.4 Disputes

| Route            | Page                   | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|------------------|------------------------|-----|-----|-----|-----|-----|-----|-------|
| `/disputes`      | `DisputeCenterPage`    | full| full| full| full| ro  | ro  | R1/R2 open/view disputes; R3/R4 adjudicate; R5/R6 view. |
| `/dispute/:id`   | `DisputeDetailPage`    | full| full| full| full| ro  | ro  | Role‑specific actions based on RBAC. |

---

### 2.5 Compliance & Policy

| Route           | Page                     | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|-----------------|--------------------------|-----|-----|-----|-----|-----|-----|-------|
| `/compliance`   | `ComplianceToolsPage`    | n/a | n/a | full| full| ro  | ro  | Main compliance cockpit (freeze, PEP, EDD, etc.). |
| `/fatf-rules` * | `FatfRulesPage`          | n/a | n/a | full| full| ro  | full| FATF rule reference & mapping. May be a tab under `/compliance`. |

\* Check actual routing: may be accessed via query/tab in `/compliance` rather than a standalone route.

---

### 2.6 War Room & Detection (Embedded Next.js)

Flutter routes that host Next.js content via `HtmlElementView`:

| Route               | Page                   | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|---------------------|------------------------|-----|-----|-----|-----|-----|-----|-------|
| `/war-room`         | `WarRoomNextJSPage`    | n/a | n/a | full| full| ro  | ro  | Main war room (flagged queue, dashboards). `isEmbedded: true`. |
| `/detection-studio` | `DetectionStudioPage`  | n/a | n/a | full| full| ro  | ro  | Detection/ML dashboard. `isEmbedded: true`. |
| `/graph-explorer`   | `GraphExplorerPage`    | n/a | n/a | full| full| ro  | full| Graph view for investigations and audits. `isEmbedded: true`. |

Legacy/internally duplicated Flutter war room pages (superseded by Next.js): `WarRoomLandingPage`, `FlaggedQueuePage`, `AnalyticsHubPage`.

---

### 2.7 Admin, Approvals, Audit

| Route                 | Page                     | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|-----------------------|--------------------------|-----|-----|-----|-----|-----|-----|-------|
| `/approver`           | `ApproverPortalPage`     | n/a | opt | full| full| ro  | ro  | R2 only if approver; R3/R4 primary approvers. |
| `/admin`              | `AdminPage`              | n/a | n/a | n/a | ro  | full| ro  | Admin platform controls; R4 has limited policy view. |
| `/audit`              | `AuditChainReplayPage`   | n/a | n/a | ro  | full| ro  | full| Primary audit view for R4/R6; R3 view‑only. |

---

### 2.8 Settings & Misc

| Route         | Page             | R1  | R2  | R3  | R4  | R5  | R6  | Notes |
|---------------|------------------|-----|-----|-----|-----|-----|-----|-------|
| `/settings`   | `SettingsPage`   | full| full| full| full| full| full| All roles manage their own prefs. |


---

## 3. Per‑Role Wireframe Summaries

### 3.1 R1 – End User (Focus Mode)

- **Shell**: Focus mode, no sidebar, bottom nav only.
- **Bottom nav**: Home (`/`), Wallet (`/wallet`), Send (`/transfer`), History (`/history`), Profile/More.
- **Key screens**:
  - `HomePage`: balance, recent activity, quick actions (Send, Trust Check, Disputes).
  - `WalletPage`: token list, receive addresses.
  - `TransferPage`: simple send with AI safety hints.
  - `HistoryPage`: list of transactions, link to disputes.
  - `TrustCheckPage`: input address/tx; risk score & recommendations.
  - `DisputeCenterPage` / `DisputeDetailPage`: file and track disputes.
  - `SettingsPage`: notifications, security, profile.

### 3.2 R2 – Power User / PEP (Focus Mode + Pro Tools)

- **Shell**: Focus mode.
- **Bottom nav**: Home, Wallet, Pro, History, More.
- **Key screens**:
  - All R1 surfaces.
  - **Pro section** (via Pro tab or More):
    - `NFTSwapPage`: NFT swaps with risk overlays.
    - `SafeManagementPage`: safe/multisig treasury.
    - `SessionKeyPage`: manage ERC‑4337 session keys.
    - `CrossChainPage`: cross‑chain transfers.
    - `ZkNAFPage`: create/manage privacy attestations.
  - `ApproverPortalPage` (if flagged as approver): approval queue for high‑risk actions.

### 3.3 R3 – Institution Ops (War Room Mode)

- **Shell**: War room mode (sidebar + content). Single navigation bar controlled by Flutter.
- **Sidebar sections (example):**
  - **Monitoring**:
    - Dashboard → `/war-room` (embedded Next.js).
    - Detection Studio → `/detection-studio` (embedded Next.js).
    - Graph Explorer → `/graph-explorer` (embedded Next.js).
  - **Operations**:
    - Compliance Tools → `/compliance`.
    - Disputes → `/disputes`.
  - Audit Trail → `/audit` (ro).
  - **Approvals**:
    - Approver Portal → `/approver`.
- **Behavior**:
  - Embedded pages enter full‑screen mode: Flutter hides its own sidebar/top bar, shows only a back overlay; Next.js shell hides its UI in `embed=true` mode.

### 3.4 R4 – Institution Compliance (War Room + Governance)

- **Shell**: War room mode like R3, with extra governance surfaces.
- **Sidebar**:
  - Monitoring (Dashboard, Detection Studio, Graph Explorer).
  - Compliance (Compliance Tools, Disputes).
  - Governance:
    - FATF Rules → `/fatf-rules` or `/compliance?tab=fatf`.
    - Audit Chain Replay → `/audit`.
- **Behavior**:
  - Elevated actions in Compliance Tools (override/approve policies).
  - Can configure policy thresholds; R3 cannot.

### 3.5 R5 – Platform Admin

- **Shell**: Admin‑oriented; can reuse War room shell with an "Admin" focus section.
- **Sidebar**:
  - Admin → `/admin` (system config, deployments, logs).
  - Keys & Safes → `/session-keys` (ro/full where appropriate), `/safe`.
  - Optional read‑only links into War Room / Compliance for diagnostics.
- **Behavior**:
  - No case‑level decision making (that’s R3/R4); focuses on infra and configuration.

### 3.6 R6 – Super Admin / Auditor

- **Shell**: War room mode, **strict read‑only** on operational surfaces.
- **Sidebar**:
  - Audit:
    - Audit Chain Replay → `/audit`.
    - FATF Rules → `/fatf-rules` or `/compliance?tab=fatf`.
  - Views (read‑only):
    - War Room → `/war-room`.
    - Detection Studio → `/detection-studio`.
    - Graph Explorer → `/graph-explorer`.
    - Disputes → `/disputes`.
- **Behavior**:
  - Cannot change policies or act on cases; can observe and export evidence.

---

## 4. Navigation & RBAC Implementation Notes

### 4.1 Single Navigation Bar (No Double Nav)

- Flutter is the **only controlling shell**:
  - `RoleBasedShell` shows:
    - Focus mode (no sidebar) for R1/R2.
    - War room mode (sidebar) for R3–R6.
  - For embedded Next.js routes, `RoleBasedShell` uses `_buildFullScreenMode`:
    - No sidebar, no top bar.
    - Only a back button overlay.
- Next.js War Room/Focus shells (`WarRoomShell`, `FocusModeShell`):
  - Read `embed` query parameter.
  - In `embed=true`, they render only `{children}` with no sidebar/header/footer.

Result: there is **never a case** where both Flutter and Next.js nav are visible together.

### 4.2 RBAC Enforcement

- `RoleNavigationConfig` (in `role_navigation_config.dart`) is the **source of truth** for which routes each role can access.
- `RoleNavigationConfig.allRoutes` lists all allowed routes for that role.
- `canRoleAccessRoute(role, path)` uses that list to decide if a route is reachable.
- `app_router.dart` redirect logic:
  - Reads current `rbacState.role`.
  - If the route is not in `canRoleAccessRoute`, redirects to `/unauthorized?from=...`.
- Action‑level permissions (e.g., whether R3 vs R4 can approve a case) should be checked using `RoleCapabilities` from `roles.dart` inside each page widget.

---

## 5. TODOs

These are the concrete steps to fully align the codebase with this document.

### 5.1 Align `RoleNavigationConfig` with Final Mapping

1. **R1 & R2 configs** (`r1EndUserConfig`, `r2PowerUserConfig`):
   - Ensure `sections` remain empty (no sidebar).
   - Confirm `bottomNav` uses:
     - For R1: `/`, `/wallet`, `/transfer`, `/history`, `/profile`.
     - For R2: `/`, `/wallet`, `/transfer`, `/history`, `/more` (with Pro items accessible via More screen).
   - Add `quickActions` for R2 to point to `/nft-swap`, `/cross-chain`, `/disputes`, `/trust-check` as needed.

2. **R3 config** (`r3InstitutionOpsConfig`):
   - Replace Next.js‑style routes (`/war-room/flagged`, `/war-room/alerts`, etc.) with Flutter routes:
     - Monitoring:
       - Dashboard → `/war-room` (`isEmbedded: true`).
       - Detection Studio → `/detection-studio` (`isEmbedded: true`).
       - Graph Explorer → `/graph-explorer` (`isEmbedded: true`).
     - Operations:
       - Compliance Tools → `/compliance`.
       - Disputes → `/disputes`.
  - Audit Trail → `/audit`.
     - Approvals:
       - Approver Portal → `/approver`.
   - Update `bottomNav` for R3 to reflect key sections (e.g., Dashboard, Detection, Disputes, Settings).

3. **R4 config** (`r4ComplianceConfig`):
   - Base on R3 with additional Governance section:
     - FATF Rules → `/fatf-rules` or `/compliance?tab=fatf`.
  - Audit Chain Replay → `/audit`.
   - Ensure R4 `sections` and `bottomNav` match this doc.

4. **R5 config** (`r5PlatformAdminConfig`):
   - Focus sections on:
     - Admin → `/admin`.
     - Keys & Safes → `/session-keys`, `/safe`.
   - Optionally add read‑only links to `/war-room` and `/compliance` for diagnostics.

5. **R6 config** (`r6SuperAdminConfig`):
   - Emphasize Audit/Governance:
     - Audit Chain Replay, FATF Rules, read‑only War Room, Detection Studio, Graph Explorer, Disputes.
   - Ensure no write‑permission routes (e.g., `/admin` write tabs) are included.

### 5.2 Verify Embedded Next.js URLs

1. In `WarRoomNextJSPage`, `DetectionStudioPage`, and `GraphExplorerPage`:
   - Ensure URLs always include `embed=true` and a role identifier, e.g.:
     - `/war-room?embed=true&role=R3`.
     - `/war-room/detection-studio?embed=true&role=R3`.
2. In Next.js (`WarRoomShell.tsx`, `FocusModeShell.tsx`):
   - Confirm `isEmbedMode` is computed via `searchParams.get('embed') === 'true'`.
   - In embed mode, render **only** children (no nav, status bar, etc.).
3. In internal Next.js links for embed mode, preserve `embed=true` when navigating.

### 5.3 Enforce RBAC Strictly

1. Confirm `canRoleAccessRoute` and `RoleNavigationConfig.allRoutes` use the updated routes only.
2. In `app_router.dart`:
   - Ensure redirect uses `canRoleAccessRoute` for all non‑system paths.
   - Keep `/settings`, `/profile`, `/more`, `/unauthorized` outside strict guard as intended.
3. In page widgets, use `RoleCapabilities` to differentiate:
   - R3 vs R4 vs R6 permissions inside the same route (e.g., who can click "Approve").

### 5.4 Clean Up Legacy / Duplicate Pages

1. Mark or move the following as **legacy/demo** (or remove if no longer needed):
   - `FocusHomePage`, `LightHomePage`.
   - `LightSignInPage`.
   - `WarRoomLandingPage`, `FlaggedQueuePage`, `AnalyticsHubPage`.
2. Optionally add a `legacy/README.md` pointing back to this mapping.

### 5.5 Validation

1. Run Flutter analyzer/tests to ensure no broken imports/routes:
   - Check all `RoleNavItem.route` values resolve to real routes in `app_router.dart`.
2. Manual QA per role (using demo accounts):
   - Verify visible navigation items match the per‑role wireframes.
   - Open embedded pages and confirm:
     - Flutter hides sidebar/top bar.
     - Next.js shows no sidebar/header.
   - Try accessing unauthorized routes directly in the URL and confirm redirect to `/unauthorized`.

---

This document is the authoritative reference for RBAC, navigation, and per‑role UX. Any changes to roles, routes, or shells should be reflected here and then applied in `role_navigation_config.dart`, `roles.dart`, `app_router.dart`, and the relevant Flutter/Next.js shells.