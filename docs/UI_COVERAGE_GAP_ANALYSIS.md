# AMTTP UI Coverage Gap Analysis

## Executive Summary

This document identifies all smart contract functions that require UI coverage and highlights gaps between current UI implementation and complete feature coverage. The goal is to ensure every use case supported by the smart contracts is accessible through the UI.

---

## 📊 Current State Analysis

### Current Routes (from `app_router.dart`)
| Route | Page | Current Features |
|-------|------|------------------|
| `/` | HomePage | Welcome, wallet connect, basic tabs |
| `/wallet` | WalletPage | Wallet management |
| `/transfer` | TransferPage | ETH/ERC20 transfers with SecureTransferWidget |
| `/history` | HistoryPage | Transaction history list |
| `/admin` | AdminPage | Overview, DQN Analytics, Transactions, Policies |
| `/settings` | SettingsPage | User preferences |

### Current Features Directory
- `admin/` - Admin dashboard (4 tabs)
- `history/` - Transaction history
- `home/` - Home/dashboard
- `settings/` - Settings page
- `transfer/` - Secure transfer
- `wallet/` - Wallet management

---

## 🔴 CRITICAL MISSING UI PAGES

### 1. NFT Swap Page (`/nft-swap`) - NEW PAGE REQUIRED
**Contract:** `AMTTPNFT.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `initiateNFTtoETHSwap()` | End User | Start NFT ↔ ETH swap |
| `depositETHForNFT()` | End User | Deposit ETH to complete NFT swap |
| `completeNFTSwap()` | End User | Complete NFT swap with preimage |
| `initiateNFTtoNFTSwap()` | End User | Start NFT ↔ NFT swap |
| `depositNFTForSwap()` | End User | Deposit second NFT for swap |
| `completeNFTtoNFTSwap()` | End User | Complete NFT-to-NFT swap |
| `refundNFTSwap()` | End User | Refund expired NFT swap |
| `approveSwap()` | Approver | Approve high-risk NFT swap |

**Required UI Components:**
- NFT collection browser/selector
- NFT preview with metadata
- Swap type selector (NFT→ETH, NFT→NFT)
- ETH amount input for NFT→ETH swaps
- Risk score display before confirmation
- Swap progress stepper
- Active swaps list with completion actions

---

### 2. Dispute Resolution Center (`/disputes`) - NEW PAGE REQUIRED
**Contract:** `AMTTPDisputeResolver.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `challengeTransaction()` | End User | Initiate dispute (requires arbitration fee) |
| `submitEvidence()` | End User | Submit evidence for ongoing dispute |
| `requestAppeal()` | End User | Request appeal on dispute ruling |

**Required UI Components:**
- Active disputes list with status
- Dispute creation wizard (select TX → reason → evidence → pay fee)
- Evidence submission form (text, files, IPFS links)
- Dispute timeline showing phases
- Appeal request button (when eligible)
- Ruling display with fund distribution
- Kleros integration status

---

### 3. Cross-Chain Transfer Page (`/cross-chain`) - NEW PAGE REQUIRED
**Contract:** `AMTTPCrossChain.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `sendRiskScore()` | Admin | Propagate risk score to other chains |
| `propagateDisputeResult()` | Admin | Share dispute result cross-chain |

**Required UI Components:**
- Destination chain selector (Ethereum, Polygon, Arbitrum, etc.)
- Cross-chain swap initiation form
- LayerZero fee estimator
- Chain status indicators (paused/active)
- Cross-chain transaction tracking
- Risk score propagation dashboard (Admin)

---

### 4. MultiSig / Safe Management (`/safe`) - NEW PAGE REQUIRED
**Contract:** `AMTTPSafeModule.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `registerSafe()` | End User | Register Gnosis Safe with AMTTP |
| `updateSafeConfig()` | End User | Update Safe configuration |
| `approveQueuedTransaction()` | End User | Approve queued high-risk TX |
| `rejectQueuedTransaction()` | End User | Reject queued TX |
| `executeQueuedTransaction()` | End User | Execute after threshold approvals |
| `addToWhitelist()` | End User | Add address to Safe whitelist |
| `removeFromWhitelist()` | End User | Remove from whitelist |
| `addToBlacklist()` | End User | Block address for Safe |
| `removeFromBlacklist()` | End User | Unblock address |

**Required UI Components:**
- Safe registration wizard
- Operator management (add/remove)
- Queued transactions list with approve/reject buttons
- Approval progress indicator
- Whitelist/Blacklist management
- Safe audit log viewer

---

### 5. Session Key Management (`/session-keys`) - NEW PAGE REQUIRED
**Contract:** `AMTTPBiconomyModule.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `registerAccount()` | End User | Register smart account with AMTTP |
| `updateAccountConfig()` | End User | Update account configuration |
| `createSessionKey()` | End User | Create session key with permissions |
| `revokeSessionKey()` | End User | Revoke active session key |

**Required UI Components:**
- Account registration flow
- Session key creation wizard
  - Validity period selector
  - Spending limit input
  - Allowed contract/function selector
- Active session keys list
- Revoke button with confirmation
- Gasless transaction toggle

---

### 6. Approver Portal (`/approver`) - NEW PAGE REQUIRED
**Contract:** `AMTTPCore.sol`, `AMTTPNFT.sol`

**Missing Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `approveSwap()` | Approver | Approve high-risk swap |
| `rejectSwap()` | Approver | Reject swap with reason |

**Required UI Components:**
- Pending approvals queue
- Swap details with risk analysis
- Risk score breakdown visualization
- One-click approve/reject buttons
- Rejection reason form
- Approval history log

---

### 7. Compliance Tools (`/compliance`) - ENHANCE ADMIN
**Contract:** `AMTTPPolicyEngine.sol`

**Missing Admin Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `freezeAccount()` | Admin/Compliance | Freeze user account |
| `unfreezeAccount()` | Admin/Compliance | Unfreeze user account |
| `addTrustedUser()` | Admin | Add to trusted users list |
| `removeTrustedUser()` | Admin | Remove from trusted list |
| `setTransactionPolicy()` | Admin | Configure TX policies |
| `setRiskPolicy()` | Admin | Configure risk thresholds |
| `addVelocityLimit()` | Admin | Set velocity limits |
| `setComplianceRules()` | Admin | Configure compliance rules |

**Required UI Components:**
- Frozen accounts list with freeze/unfreeze
- Trusted users management
- Policy configuration forms
- Velocity limit editor
- Compliance rules builder

---

### 8. User Self-Service Features - ADD TO SETTINGS
**Contract:** `AMTTPPolicyEngine.sol`

**Missing User Functions:**
| Function | User Type | Description |
|----------|-----------|-------------|
| `addTrustedCounterparty()` | End User | Add trusted contact |
| `removeTrustedCounterparty()` | End User | Remove trusted contact |

**Required UI Components:**
- Trusted contacts list
- Add contact by address
- Remove contact button
- Contact notes/labels

---

## 📊 Complete Smart Contract → UI Mapping

### AMTTPCore.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `initiateSwap()` | ✅ TransferPage | - |
| `initiateSwapERC20()` | ✅ TransferPage | - |
| `completeSwap()` | ❌ MISSING | Add to History/Transfer |
| `refundSwap()` | ❌ MISSING | Add to History |
| `approveSwap()` | ❌ MISSING | Create Approver Portal |
| `rejectSwap()` | ❌ MISSING | Create Approver Portal |
| `raiseDispute()` | ❌ MISSING | Create Dispute Center |

### AMTTPNFT.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `initiateNFTtoETHSwap()` | ❌ MISSING | Create NFT Swap Page |
| `depositETHForNFT()` | ❌ MISSING | Create NFT Swap Page |
| `completeNFTSwap()` | ❌ MISSING | Create NFT Swap Page |
| `initiateNFTtoNFTSwap()` | ❌ MISSING | Create NFT Swap Page |
| `depositNFTForSwap()` | ❌ MISSING | Create NFT Swap Page |
| `completeNFTtoNFTSwap()` | ❌ MISSING | Create NFT Swap Page |
| `refundNFTSwap()` | ❌ MISSING | Create NFT Swap Page |
| `approveSwap()` | ❌ MISSING | Create Approver Portal |
| `raiseDispute()` | ❌ MISSING | Create Dispute Center |

### AMTTPDisputeResolver.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `challengeTransaction()` | ❌ MISSING | Create Dispute Center |
| `submitEvidence()` | ❌ MISSING | Create Dispute Center |
| `requestAppeal()` | ❌ MISSING | Create Dispute Center |

### AMTTPCrossChain.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `sendRiskScore()` | ❌ MISSING | Create Cross-Chain Page |
| `propagateDisputeResult()` | ❌ MISSING | Create Cross-Chain Page |
| `pauseChain()` | ❌ MISSING | Add to Admin |
| `unpauseChain()` | ❌ MISSING | Add to Admin |
| `setChainRateLimit()` | ❌ MISSING | Add to Admin |

### AMTTPSafeModule.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `registerSafe()` | ❌ MISSING | Create Safe Management Page |
| `updateSafeConfig()` | ❌ MISSING | Create Safe Management Page |
| `approveQueuedTransaction()` | ❌ MISSING | Create Safe Management Page |
| `rejectQueuedTransaction()` | ❌ MISSING | Create Safe Management Page |
| `executeQueuedTransaction()` | ❌ MISSING | Create Safe Management Page |
| `addToWhitelist()` | ❌ MISSING | Create Safe Management Page |
| `removeFromWhitelist()` | ❌ MISSING | Create Safe Management Page |
| `addToBlacklist()` | ❌ MISSING | Create Safe Management Page |
| `removeFromBlacklist()` | ❌ MISSING | Create Safe Management Page |

### AMTTPBiconomyModule.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `registerAccount()` | ❌ MISSING | Create Session Key Page |
| `updateAccountConfig()` | ❌ MISSING | Create Session Key Page |
| `createSessionKey()` | ❌ MISSING | Create Session Key Page |
| `revokeSessionKey()` | ❌ MISSING | Create Session Key Page |

### AMTTPPolicyEngine.sol
| Function | Current UI | Gap |
|----------|-----------|-----|
| `setTransactionPolicy()` | ⚠️ Partial | Enhance Policies Tab |
| `setRiskPolicy()` | ⚠️ Partial | Enhance Policies Tab |
| `addVelocityLimit()` | ❌ MISSING | Add to Admin Policies |
| `setComplianceRules()` | ❌ MISSING | Add to Admin Policies |
| `freezeAccount()` | ❌ MISSING | Add Compliance Tools |
| `unfreezeAccount()` | ❌ MISSING | Add Compliance Tools |
| `addTrustedCounterparty()` | ❌ MISSING | Add to Settings |
| `removeTrustedCounterparty()` | ❌ MISSING | Add to Settings |
| `addTrustedUser()` | ❌ MISSING | Add to Admin |
| `removeTrustedUser()` | ❌ MISSING | Add to Admin |

---

## 🎯 Recommended New Routes

```dart
final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    routes: [
      // Existing Routes
      GoRoute(path: '/', name: 'home', builder: (_, __) => const HomePage()),
      GoRoute(path: '/wallet', name: 'wallet', builder: (_, __) => const WalletPage()),
      GoRoute(path: '/transfer', name: 'transfer', builder: (_, __) => const TransferPage()),
      GoRoute(path: '/history', name: 'history', builder: (_, __) => const HistoryPage()),
      GoRoute(path: '/admin', name: 'admin', builder: (_, __) => const AdminPage()),
      GoRoute(path: '/settings', name: 'settings', builder: (_, __) => const SettingsPage()),
      
      // NEW ROUTES REQUIRED
      GoRoute(path: '/nft-swap', name: 'nftSwap', builder: (_, __) => const NFTSwapPage()),
      GoRoute(path: '/disputes', name: 'disputes', builder: (_, __) => const DisputeCenterPage()),
      GoRoute(path: '/cross-chain', name: 'crossChain', builder: (_, __) => const CrossChainPage()),
      GoRoute(path: '/safe', name: 'safe', builder: (_, __) => const SafeManagementPage()),
      GoRoute(path: '/session-keys', name: 'sessionKeys', builder: (_, __) => const SessionKeyPage()),
      GoRoute(path: '/approver', name: 'approver', builder: (_, __) => const ApproverPortalPage()),
      GoRoute(path: '/compliance', name: 'compliance', builder: (_, __) => const CompliancePage()),
      
      // Nested/Detail Routes
      GoRoute(path: '/dispute/:id', name: 'disputeDetail', builder: (_, state) => DisputeDetailPage(id: state.pathParameters['id']!)),
      GoRoute(path: '/swap/:id', name: 'swapDetail', builder: (_, state) => SwapDetailPage(id: state.pathParameters['id']!)),
    ],
  );
});
```

---

## 📈 Implementation Priority

### Phase 1: Core User Features (High Priority)
1. **Dispute Resolution Center** - Essential for user trust
2. **Approver Portal** - Required for high-risk transactions
3. **Complete Swap UI** - Add complete/refund to existing transfer

### Phase 2: Advanced Features (Medium Priority)
4. **NFT Swap Page** - Full NFT swap functionality
5. **Session Key Management** - Gasless transaction support
6. **Safe Management** - MultiSig support

### Phase 3: Admin & Infrastructure (Lower Priority)
7. **Cross-Chain Dashboard** - LayerZero management
8. **Enhanced Compliance Tools** - Account freezing, trusted users
9. **Trusted Contacts** - User self-service feature

---

## 📁 New Feature Directory Structure

```
frontend/amttp_app/lib/features/
├── admin/                    # ✅ EXISTS - Enhance with compliance tools
├── disputes/                 # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   ├── dispute_center_page.dart
│       │   └── dispute_detail_page.dart
│       └── widgets/
│           ├── dispute_list_widget.dart
│           ├── evidence_form_widget.dart
│           └── dispute_timeline_widget.dart
├── nft_swap/                 # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   └── nft_swap_page.dart
│       └── widgets/
│           ├── nft_selector_widget.dart
│           ├── swap_progress_widget.dart
│           └── active_swaps_widget.dart
├── cross_chain/              # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   └── cross_chain_page.dart
│       └── widgets/
│           ├── chain_selector_widget.dart
│           └── cross_chain_tracker_widget.dart
├── safe/                     # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   └── safe_management_page.dart
│       └── widgets/
│           ├── queued_tx_widget.dart
│           ├── operator_list_widget.dart
│           └── whitelist_widget.dart
├── session_keys/             # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   └── session_key_page.dart
│       └── widgets/
│           ├── session_key_list_widget.dart
│           └── create_session_wizard.dart
├── approver/                 # 🆕 NEW
│   └── presentation/
│       ├── pages/
│       │   └── approver_portal_page.dart
│       └── widgets/
│           └── pending_approval_widget.dart
└── compliance/               # 🆕 NEW (or merge into admin)
    └── presentation/
        ├── pages/
        │   └── compliance_page.dart
        └── widgets/
            ├── frozen_accounts_widget.dart
            └── trusted_users_widget.dart
```

---

## ✅ Action Items Summary

| Priority | Action | New Pages | Functions Covered |
|----------|--------|-----------|-------------------|
| 🔴 HIGH | Create Dispute Center | 2 | 3 |
| 🔴 HIGH | Create Approver Portal | 1 | 2 |
| 🔴 HIGH | Enhance Transfer/History | 0 | 2 |
| 🟠 MEDIUM | Create NFT Swap Page | 1 | 8 |
| 🟠 MEDIUM | Create Session Key Page | 1 | 4 |
| 🟠 MEDIUM | Create Safe Management Page | 1 | 9 |
| 🟡 LOW | Create Cross-Chain Page | 1 | 5 |
| 🟡 LOW | Enhance Admin with Compliance | 0 | 8 |
| 🟡 LOW | Add Trusted Contacts to Settings | 0 | 2 |

**Total New Pages Required:** 8  
**Total Functions to Cover:** 43  
**Current Coverage:** ~15%  
**Target Coverage:** 100%

---

*Generated: 2025-01-05*
*Document Version: 1.0*
