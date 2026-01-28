# AMTTP UI/UX Ground Truth Alignment Plan

**Version:** 1.0  
**Date:** January 21, 2026  
**Status:** Planning Phase  
**Reference Document:** `AMTTP_UI_UX_Ground_Truth.md`

---

## Executive Summary

This document outlines the work required to align the current AMTTP codebase with the UI/UX Ground Truth specification v2.3. The plan is organized into 8 epics with prioritized tasks, gap analysis, and estimated effort.

---

## 📊 Current State Analysis

### What Exists

| Component | Status | Notes |
|-----------|--------|-------|
| **Flutter App** | ✅ Partial | Has `UserProfile` enum with 3 roles (endUser, admin, complianceOfficer) |
| **Next.js Dashboard** | ✅ Partial | SIEM dashboard exists, embedded in Flutter |
| **RBAC Backend** | ✅ Partial | `label-safeguards.ts` has roles: ANALYST, SENIOR_ANALYST, COMPLIANCE_OFFICER, MLRO, SYSTEM_ADMIN, AUDITOR |
| **Detection Studio** | ✅ Exists | Basic iframe wrapper to Next.js |
| **Smart Contracts** | ✅ Exists | AMTTPCore, PolicyEngine, DisputeResolver, etc. |
| **Multisig** | ⚠️ Basic | Contract-level exists, no UI governance flow |
| **UI Integrity** | ❌ Missing | No snapshot/hash chain implementation |

### Critical Gaps

1. **RBAC Mismatch:** Current roles don't match R1-R6 specification
2. **No UI Integrity System:** Missing snapshot hashing, tamper detection
3. **No Multisig UI Flow:** Missing WYA screens, integrity acknowledgement
4. **No Focus vs War Room Mode:** Missing role-locked mode separation
5. **Detection Studio Incomplete:** Missing Graph Explorer, Velocity Heatmap, Sankey
6. **No Pre-Transaction Trust Check:** R1/R2 flow not implemented

---

## 🏗️ EPIC BREAKDOWN

### EPIC 1: RBAC Foundation Alignment
**Priority:** P0 (Blocking)  
**Effort:** 2-3 sprints

#### Tasks

| ID | Task | Frontend | Backend | Contracts |
|----|------|----------|---------|-----------|
| 1.1 | Define canonical Role enum (R1-R6) | ✅ | ✅ | ✅ |
| 1.2 | Create shared RBAC types package | ✅ | ✅ | - |
| 1.3 | Update Flutter `UserProfile` to R1-R6 | ✅ | - | - |
| 1.4 | Update Next.js auth context | ✅ | - | - |
| 1.5 | Update `label-safeguards.ts` roles | - | ✅ | - |
| 1.6 | Update `fca-compliance-service.ts` | - | ✅ | - |
| 1.7 | Add RBAC middleware to all API routes | - | ✅ | - |
| 1.8 | Update smart contract access control | - | - | ✅ |

#### Implementation Details

**1.1 Canonical Role Enum (create in shared package)**

```typescript
// packages/shared/src/rbac/roles.ts
export enum Role {
  R1_END_USER = 'R1_END_USER',
  R2_END_USER_PEP = 'R2_END_USER_PEP',
  R3_INSTITUTION_OPS = 'R3_INSTITUTION_OPS',
  R4_INSTITUTION_COMPLIANCE = 'R4_INSTITUTION_COMPLIANCE',
  R5_PLATFORM_ADMIN = 'R5_PLATFORM_ADMIN',
  R6_SUPER_ADMIN = 'R6_SUPER_ADMIN'
}

export const ROLE_CAPABILITIES = {
  [Role.R1_END_USER]: {
    canInitiateOwnTx: true,
    canAccessDetectionStudio: false,
    canEditPolicies: false,
    canEnforceActions: false,
    canSignMultisig: false,
    canViewUISnapshots: 'view',
    canEmergencyOverride: false,
  },
  // ... R2-R6
};
```

**1.3 Update Flutter UserProfile**

```dart
// lib/core/auth/user_profile_provider.dart
enum UserProfile {
  r1EndUser,           // Was: endUser
  r2EndUserPEP,        // NEW
  r3InstitutionOps,    // NEW (was partially: admin)
  r4InstitutionCompliance, // Was: complianceOfficer
  r5PlatformAdmin,     // NEW
  r6SuperAdmin,        // NEW
}
```

---

### EPIC 2: Focus Mode vs War Room Mode
**Priority:** P0 (Blocking)  
**Effort:** 2 sprints

#### Tasks

| ID | Task | Flutter | Next.js |
|----|------|---------|---------|
| 2.1 | Create mode context provider | ✅ | ✅ |
| 2.2 | Implement Focus Mode shell (R1/R2) | ✅ | - |
| 2.3 | Implement War Room shell (R3/R4) | ✅ | ✅ |
| 2.4 | RBAC-lock mode switching | ✅ | ✅ |
| 2.5 | Update navigation based on mode | ✅ | ✅ |

#### Implementation Details

**Mode Provider Structure:**

```typescript
// frontend/frontend/src/lib/mode-context.tsx
export type AppMode = 'FOCUS_MODE' | 'WAR_ROOM_MODE';

export const MODE_BY_ROLE: Record<Role, AppMode> = {
  R1_END_USER: 'FOCUS_MODE',
  R2_END_USER_PEP: 'FOCUS_MODE',
  R3_INSTITUTION_OPS: 'WAR_ROOM_MODE',
  R4_INSTITUTION_COMPLIANCE: 'WAR_ROOM_MODE',
  R5_PLATFORM_ADMIN: 'WAR_ROOM_MODE',
  R6_SUPER_ADMIN: 'WAR_ROOM_MODE',
};
```

---

### EPIC 3: End User Pre-Transaction Trust Check (R1/R2)
**Priority:** P1  
**Effort:** 2 sprints

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 3.1 | Create Trust Check API | `/api/trust/check?address=0x...` |
| 3.2 | Design Trust Pillars component | Identity, History, Disputes, Network, Behavior |
| 3.3 | Build Interstitial Screen | Mandatory before tx if confidence < 100% |
| 3.4 | Implement decision flow | Continue / Use Escrow / Cancel |
| 3.5 | Add UI Integrity Indicator | Lock icon + tooltip |

#### UI Specification (from Ground Truth)

```
┌──────────────────────────────────────────────────────────────┐
│ Pre-Transaction Trust Check                                  │
├──────────────────────────────────────────────────────────────┤
│ Trust Pillars (Qualitative, Non-Numeric):                    │
│ • Identity Confidence: [Verified/Unverified/Unknown]         │
│ • Transaction History: [Established/Limited/None]            │
│ • Dispute Record: [Clean/Has Disputes/Unknown]               │
│ • Network Proximity: [Direct/Indirect/Unknown]               │
│ • Behavioral Signals: [Normal/Anomalous/Insufficient]        │
├──────────────────────────────────────────────────────────────┤
│ 🔒 UI Integrity Verified                                     │
├──────────────────────────────────────────────────────────────┤
│ [ Continue ]  [ Use Escrow Protection ]  [ Cancel ]          │
└──────────────────────────────────────────────────────────────┘
```

**❌ Explicitly Excluded:** No numeric risk scores, no charts, no enforcement controls

---

### EPIC 4: Detection Studio (R3 - War Room)
**Priority:** P1  
**Effort:** 3-4 sprints

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 4.1 | War Room Landing page | Flagged Queue + KPI Strip |
| 4.2 | Graph Explorer (Memgraph) | Progressive hop expansion, time-travel |
| 4.3 | Velocity Heatmap | Hourly grid, z-score deviation |
| 4.4 | Sankey Flow Auditor | Value conservation visualization |
| 4.5 | ML Explainability Overlay | Human-readable explanations |
| 4.6 | Evidence & Notes Panel | Case documentation |
| 4.7 | Graph Summary Strip | Hops, fan-out, re-convergence |

#### Current State vs Target

| Component | Current | Target |
|-----------|---------|--------|
| Detection Studio | Iframe to Next.js | Full implementation |
| Graph Explorer | ❌ Missing | Memgraph integration |
| Velocity Heatmap | ❌ Missing | Netflix-style grid |
| Sankey | ❌ Missing | Value flow auditor |
| ML Explanation | ❌ Missing | Human-readable panel |

#### Hard Constraints (from Ground Truth)

- R3 has **read-only policies**
- **No block / pause / enforce buttons** in Detection Studio
- Tabbed interface: **one active view at a time**

---

### EPIC 5: Compliance Studio (R4 - War Room)
**Priority:** P1  
**Effort:** 2 sprints

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 5.1 | Policy Rule Engine UI | Velocity, jurisdiction, threshold rules |
| 5.2 | Enforcement Action UI | Scoped pause, asset block, mandatory escrow |
| 5.3 | Action Attribution | All actions hashed and attributed |
| 5.4 | Multisig Trigger | High-impact actions require multisig |

#### API Endpoints Required

```
POST /api/compliance/policy         # Create/update policy
GET  /api/compliance/policy/:id     # Get policy
POST /api/compliance/enforce        # Trigger enforcement (requires multisig)
GET  /api/compliance/audit          # Get audit trail
```

---

### EPIC 6: Multisig Governance System
**Priority:** P0 (Core Differentiator)  
**Effort:** 3 sprints

#### Tasks

| ID | Task | Frontend | Backend | Contracts |
|----|------|----------|---------|-----------|
| 6.1 | Multisig Queue UI | ✅ | - | - |
| 6.2 | WYA (What-You-Approve) Screen | ✅ | - | - |
| 6.3 | UI Snapshot Acknowledgement | ✅ | ✅ | - |
| 6.4 | MFA/Biometric Integration | ✅ | ✅ | - |
| 6.5 | Parallel Signing Support | - | ✅ | ✅ |
| 6.6 | Threshold Quorum Logic | - | ✅ | ✅ |
| 6.7 | Snapshot-bound Signatures | - | ✅ | ✅ |

#### WYA Screen Specification

```
┌──────────────────────────────────────────────────────────────┐
│ MULTISIG APPROVAL — SIGNATURE 2 OF 3 REQUIRED               │
├──────────────────────────────────────────────────────────────┤
│ WHAT YOU ARE APPROVING (WYA)                                │
│ Action: Scoped Wallet Pause                                 │
│ Target: Wallet 0xA1                                         │
│ Scope: Outgoing Transfers                                   │
│ Duration: 24 hours                                          │
│                                                             │
│ Risk Context Summary                                        │
│ • Fan-Out Across 7 Wallets                                  │
│ • Velocity Spike (6σ above baseline)                        │
│ • Prior Dispute History: Yes                                │
├──────────────────────────────────────────────────────────────┤
│ UI INTEGRITY VERIFICATION 🔒                                │
│ Snapshot Hash: 7f3a9c…                                      │
│ [ ] I verify this view matches the integrity hash           │
├──────────────────────────────────────────────────────────────┤
│ SIGNING                                                     │
│ [ MFA / Biometric ]  [ SIGN APPROVAL ]                      │
└──────────────────────────────────────────────────────────────┘
```

#### Enforcement Rules

- ❌ "Sign" disabled until hash acknowledged
- ❌ Cannot sign without viewing investigation
- ✅ Signature bound to snapshot hash
- ✅ Parallel signing allowed

#### API Endpoints

```
POST /api/multisig/request          # Create approval request
GET  /api/multisig/pending          # Get pending for user
POST /api/multisig/sign/:id         # Submit signature
GET  /api/multisig/status/:id       # Get quorum status
POST /api/multisig/verify-chain     # Verify snapshot chain
```

---

### EPIC 7: UI Integrity & Snapshot System
**Priority:** P0 (Core Differentiator)  
**Effort:** 2-3 sprints

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 7.1 | Snapshot Capture Service | JSON snapshot of displayed data |
| 7.2 | SHA-256 Hashing | Client + server verification |
| 7.3 | Hash Chain Storage | Immutable append-only log |
| 7.4 | Tamper Detection | Runtime integrity monitoring |
| 7.5 | Integrity Lock Component | Visual indicator + tooltip |
| 7.6 | Audit Verification Tool | Replay and verify chain |

#### Canonical UI Snapshot Schema

```json
{
  "snapshot_id": "uuid",
  "timestamp": "2026-01-21T12:44:09Z",
  "actor_role": "R4_INSTITUTION_COMPLIANCE",
  "actor_id": "user_8831",
  "action_context": "WALLET_PAUSE",
  "transaction_id": "0xA1",
  "displayed_data": {
    "risk_pillars": {
      "identity": "Verified",
      "behavior": "Anomalous",
      "network": "High Fan-Out"
    },
    "graph_summary": {
      "fan_out": 7,
      "layering": true
    },
    "active_policy": "POLICY_v3.2"
  },
  "ui_hash": "SHA256(displayed_data)",
  "prev_hash": "SHA256(previous_snapshot)"
}
```

#### API Endpoints

```
POST /api/ui-snapshot/create        # Create new snapshot
GET  /api/ui-snapshot/:id           # Get snapshot by ID
POST /api/ui-snapshot/verify-chain  # Verify integrity chain
GET  /api/ui-snapshot/audit         # Export for auditors
```

#### Guarantees (from Ground Truth)

- Any UI change → hash changes
- Any backend tampering → chain breaks
- Any signer denial → disproven cryptographically

---

### EPIC 8: Audit & Compliance Reporting
**Priority:** P2  
**Effort:** 1-2 sprints

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 8.1 | Snapshot Explorer | Browse historical snapshots |
| 8.2 | PDF/JSON Export | Regulator-ready reports |
| 8.3 | Evidence Linking | Connect snapshots to cases |
| 8.4 | Chain Replay Tool | Verify full audit trail |

---

## 📁 File Changes Required

### Flutter App (`frontend/amttp_app/lib/`)

| File | Change |
|------|--------|
| `core/auth/user_profile_provider.dart` | Refactor to R1-R6 roles |
| `core/auth/` | Add `rbac_provider.dart` |
| `core/` | Add `ui_integrity/` service |
| `features/transfer/` | Add Trust Check interstitial |
| `features/detection_studio/` | Complete War Room implementation |
| `features/compliance/` | Add Compliance Studio |
| `features/multisig/` | NEW - Multisig governance UI |
| `shared/widgets/` | Add `IntegrityLockBadge` |

### Next.js Frontend (`frontend/frontend/src/`)

| File | Change |
|------|--------|
| `lib/rbac/` | NEW - RBAC context and guards |
| `lib/ui-integrity/` | NEW - Snapshot service |
| `app/war-room/` | NEW - War Room landing |
| `app/detection/` | Refactor with new components |
| `app/compliance/` | Add Compliance Studio |
| `app/multisig/` | NEW - Multisig approval flows |
| `components/` | Add design system components |

### Backend Services

| Service | File | Change |
|---------|------|--------|
| `oracle-service` | `src/labels/label-safeguards.ts` | Update roles to R1-R6 |
| `oracle-service` | `src/rbac/` | NEW - Centralized RBAC |
| `compliance-service` | `orchestrator.py` | Add RBAC middleware |
| `policy-service` | `policy_api.py` | Add versioning, audit |
| NEW | `ui-snapshot-service/` | Snapshot storage & verification |
| NEW | `multisig-service/` | Governance workflow |

### Smart Contracts (`contracts/`)

| Contract | Change |
|----------|--------|
| `AMTTPCore.sol` | Add R1-R6 role constants |
| `AMTTPPolicyManager.sol` | Add policy versioning |
| NEW | `AMTTPMultisigGovernance.sol` | Quorum + snapshot binding |
| NEW | `AMTTPUIIntegrity.sol` | On-chain hash anchoring |

---

## 🎨 Design System Components

### Required Components (from Ground Truth)

| Component | Token | Purpose |
|-----------|-------|---------|
| `KPI_HealthStrip` | `kpi.sparkline` | Read-only situational awareness |
| `FlaggedQueueTable` | `table.flagged` | Primary action surface |
| `GraphExplorerCanvas` | `graph.explorer` | Memgraph visualization |
| `TemporalHeatGrid` | `heatmap.velocity` | Velocity anomaly detection |
| `ValueFlowSankey` | `sankey.flow` | Value conservation |
| `EvidencePanel` | `panel.evidence` | Case documentation |
| `MultisigApprovalCard` | `card.multisig` | WYA approval |
| `IntegrityLockBadge` | `badge.integrity` | Tamper evidence |

### Color Tokens

```scss
// Design System Tokens
$background-dark-ops: #0B0E14;
$text-primary: #E6E8EB;
$text-secondary: #9AA1AC;
$risk-high: #E5484D;
$risk-medium: #F5A524;
$risk-low: #3FB950;
$integrity-lock: #4CC9F0;
```

### Typography

- Primary: Inter
- Numerical/Hashes: JetBrains Mono
- Scale: 12 / 14 / 16 / 20 / 24

---

## 📅 Recommended Sprint Sequence

### Phase 1: Foundation (Sprints 1-3)
1. EPIC 1: RBAC Foundation
2. EPIC 2: Focus/War Room Modes
3. EPIC 7: UI Integrity System (Core)

### Phase 2: User Flows (Sprints 4-6)
4. EPIC 3: End User Trust Check
5. EPIC 4: Detection Studio
6. EPIC 5: Compliance Studio

### Phase 3: Governance (Sprints 7-9)
7. EPIC 6: Multisig Governance
8. EPIC 8: Audit & Compliance

---

## ✅ Definition of Done (Per Feature)

A feature is **NOT DONE** unless:

- [ ] RBAC enforced server-side (not just UI)
- [ ] UI snapshot created for critical screens
- [ ] Hash stored immutably
- [ ] Audit replay works
- [ ] R3 cannot trigger enforcement
- [ ] R4 requires quorum for high-impact actions
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Accessibility verified

---

## ❌ Explicitly Excluded (By Design)

Per Ground Truth specification, do NOT implement:

- ❌ Radar / spider charts
- ❌ 3D globes
- ❌ Always-on dashboards
- ❌ Composite risk numbers (numeric scores)
- ❌ Simultaneous chart stacking
- ❌ Auto-execution without human approval
- ❌ Hidden enforcement actions

---

## 🔑 Success Criteria

| Dimension | Metric |
|-----------|--------|
| **Security** | All enforcement requires multisig |
| **Usability** | One cognitive task per screen |
| **Governance** | Complete separation of Ops (R3) vs Compliance (R4) |
| **Auditability** | 100% decision reconstruction from snapshots |
| **Cognitive Safety** | Zero chart stacking, progressive disclosure |

---

## Next Steps

1. **Immediate:** Review and approve this plan
2. **Week 1:** Create shared RBAC package, update all role definitions
3. **Week 2:** Implement UI Integrity service skeleton
4. **Week 3:** Begin Focus/War Room mode separation
5. **Ongoing:** Track progress against epic milestones

---

*This plan aligns with AMTTP UI/UX & Governance Master Plan v2.3*  
*Generated: January 21, 2026*
