# Flutter App Consolidation Plan

## Current State: 35+ Pages Across 23 Feature Folders

### Problem Summary
- **Duplicate pages** for same functionality (Premium vs Standard vs Light)
- **Contract-driven design** instead of user-journey design
- **Fragmented navigation** across 6 RBAC roles
- **4 pages that just embed Next.js** - unnecessary Flutter wrapper

---

## Consolidation Strategy

### Phase 1: Remove Duplicate Pages

| Keep | Remove | Reason |
|------|--------|--------|
| `PremiumSignInPage` | `SignInPage`, `LightSignInPage` | Single premium design |
| `PremiumTransferPage` | `TransferPage` | Premium has trust check integrated |
| `PremiumTrustCheckPage` | `TrustCheckPage` | Premium has better UX |
| `HomePage` | `LightHomePage`, `FocusHomePage` | Parameterize theme instead |
| `PremiumWalletConnectPage` | - | Already single implementation |

### Phase 2: Consolidate Contract-Coverage Pages

**Current fragmentation** (pages created per smart contract):
- `NFTSwapPage` → AMTTPNFT.sol
- `CrossChainPage` → AMTTPCrossChain.sol
- `SafeManagementPage` → AMTTPSafeModule.sol
- `SessionKeyPage` → AMTTPBiconomyModule.sol
- `DisputeCenterPage` → AMTTPDisputeResolver.sol
- `ComplianceToolsPage` → AMTTPPolicyEngine.sol
- `ApproverPortalPage` → AMTTPCore.sol approvals
- `ZkNAFPage` → zkNAF privacy proofs

**Consolidation:**
| New Page | Combines | User Journey |
|----------|----------|--------------|
| `AdvancedFeaturesPage` | NFT, CrossChain, Safe, SessionKeys | Power user tools (tabbed) |
| `DisputesPage` | DisputeCenter, DisputeDetail | Single dispute flow |
| `CompliancePage` | Compliance, FATF, Approver | Institutional compliance |

### Phase 3: Remove Next.js Embed Pages

These Flutter pages just wrap Next.js iframes - redirect to Next.js directly:

| Remove | Redirect To |
|--------|-------------|
| `WarRoomNextJsPage` | Direct link to Next.js `/war-room` |
| `FATFRulesPage` | Direct link to Next.js `/compliance/fatf-rules` |
| `DetectionStudioPage` | Direct link to Next.js `/detection` |
| `MLModelsPage` | Direct link to Next.js `/ml-models` |
| `GraphExplorerPage` | Direct link to Next.js `/detection/graph` |

---

## Final Simplified Structure

### Flutter App (End User Wallet) - 10 Core Pages

```
📱 FLUTTER APP (Port 3010)
├── /sign-in          → PremiumSignInPage (auth)
├── /register         → RegisterPage (auth)
├── /                 → HomePage (dashboard)
├── /wallet           → WalletPage (balances)
├── /connect          → PremiumWalletConnectPage (web3)
├── /transfer         → PremiumTransferPage (send + trust check)
├── /history          → HistoryPage (transactions)
├── /trust-check      → PremiumTrustCheckPage (address verification)
├── /settings         → SettingsPage (preferences)
├── /advanced         → AdvancedFeaturesPage (NFT, CrossChain, Safe, Sessions)
├── /disputes         → DisputeCenterPage (raise/view disputes)
└── /unauthorized     → UnauthorizedPage (403)
```

### Next.js War Room (Institutional) - Direct Access

```
🖥️ NEXT.JS WAR ROOM (Port 3006)
├── /war-room              → Dashboard
├── /war-room/flagged      → Flagged queue
├── /war-room/compliance   → Compliance tools + FATF
├── /war-room/detection    → Detection studio + Graph
├── /war-room/ml-models    → ML model management
├── /war-room/approvals    → Approval queue
├── /war-room/audit        → Audit trail
└── /war-room/admin        → Admin functions
```

---

## Files to Delete

```
features/auth/presentation/pages/sign_in_page.dart
features/auth/presentation/pages/light_sign_in_page.dart
features/home/presentation/pages/light_home_page.dart
features/home/presentation/pages/focus_home_page.dart
features/transfer/presentation/pages/transfer_page.dart
features/trust_check/presentation/pages/trust_check_page.dart
features/war_room/presentation/pages/war_room_nextjs_page.dart
features/war_room/presentation/pages/graph_explorer_page.dart
features/compliance/presentation/pages/fatf_rules_page.dart
features/detection_studio/presentation/pages/detection_studio_page.dart
features/ml_models/presentation/pages/ml_models_page.dart
features/profile/presentation/pages/profile_selector_page.dart
```

## Files to Consolidate

```
# Create new AdvancedFeaturesPage combining:
- features/nft_swap/presentation/pages/nft_swap_page.dart
- features/cross_chain/presentation/pages/cross_chain_page.dart
- features/safe/presentation/pages/safe_management_page.dart
- features/session_keys/presentation/pages/session_key_page.dart
- features/zknaf/presentation/pages/zknaf_page.dart

# Merge into single CompliancePage:
- features/compliance/presentation/pages/compliance_page.dart
- features/approver/presentation/pages/approver_portal_page.dart
```

---

## Router Simplification

### Before: 45+ routes
### After: 15 routes

```dart
// Simplified router structure
routes: [
  // Auth (public)
  GoRoute(path: '/sign-in', builder: PremiumSignInPage),
  GoRoute(path: '/register', builder: RegisterPage),
  GoRoute(path: '/unauthorized', builder: UnauthorizedPage),
  
  // Main app (Premium Fintech Shell)
  ShellRoute(
    builder: PremiumFintechShell,
    routes: [
      GoRoute(path: '/', builder: HomePage),
      GoRoute(path: '/wallet', builder: WalletPage),
      GoRoute(path: '/connect', builder: PremiumWalletConnectPage),
      GoRoute(path: '/transfer', builder: PremiumTransferPage),
      GoRoute(path: '/history', builder: HistoryPage),
      GoRoute(path: '/trust-check', builder: PremiumTrustCheckPage),
      GoRoute(path: '/settings', builder: SettingsPage),
      GoRoute(path: '/advanced', builder: AdvancedFeaturesPage),
      GoRoute(path: '/disputes', builder: DisputeCenterPage),
      GoRoute(path: '/dispute/:id', builder: DisputeDetailPage),
    ],
  ),
]
```

---

## Benefits

1. **Simpler codebase** - 10 pages instead of 35+
2. **Clearer user journey** - Wallet-focused Flutter, Analytics-focused Next.js
3. **No iframe wrapping** - Direct links to Next.js for institutional features
4. **Easier maintenance** - Single implementation per feature
5. **Better performance** - Less code to bundle
6. **Clear separation** - Flutter = end user, Next.js = institutional

---

## Implementation Order

1. ✅ Create `AdvancedFeaturesPage` (consolidate power user features)
2. ✅ Update router to simplified structure
3. ✅ Delete duplicate/unused pages
4. ✅ Update navigation components
5. ✅ Test all routes
6. ✅ Build and verify
