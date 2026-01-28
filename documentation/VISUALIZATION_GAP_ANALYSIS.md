# AMTTP Visualization Architecture - Gap Analysis & Implementation Plan

## 📊 Current State vs. Required Architecture

### Comparison Matrix

| Cognitive Job | Required Library | Required Surface | Current Status | Gap |
|--------------|------------------|------------------|----------------|-----|
| **Relationship Discovery** | Reagraph (WebGL) | Next.js | ❌ Missing | Need to install & implement |
| **Flow of Value** | @unovis/react (Sankey) | Next.js | ❌ Missing | Need to install & implement |
| **Velocity & Time Anomalies** | Apache ECharts | Next.js | ❌ Missing (using Recharts) | **Need to replace Recharts with ECharts** |
| **Statistical Context** | Apache ECharts | Next.js | ❌ Missing (using Recharts) | Same as above |
| **Trust Summaries** | fl_chart | Flutter | ✅ Installed | Partially implemented |
| **Governance Actions** | Flutter M3 + web3dart | Flutter | ⚠️ Partial | web3dart installed, M3 in use |
| **Integrity Verification** | Web Crypto + EIP-712 | Both | ⚠️ Partial | Web Crypto started, EIP-712 stub |

---

## 🔴 Critical Gaps

### 1. **Missing: Reagraph for Graph Intelligence**
- **Status:** Not installed, not implemented
- **Required for:** Wallet relationships, hop expansion, cluster discovery
- **Impact:** Cannot visualize network topology for investigations

### 2. **Missing: @unovis/react for Sankey Flows**
- **Status:** Not installed, not implemented
- **Required for:** Value flow auditor, smurfing detection
- **Impact:** Cannot show money conservation/splitting patterns

### 3. **Wrong Library: Recharts instead of ECharts**
- **Status:** Recharts v3.6.0 installed
- **Issue:** Recharts is NOT industrial-grade for:
  - Dense heatmaps
  - Time-series with dataZoom
  - Velocity detection matrices
- **Required:** Apache ECharts for time/statistical views

### 4. **Missing: Secure Bridge (Critical)**
- **Status:** No postMessage bridge, no dart:js_interop
- **Required for:** Cryptographic binding between Next.js ↔ Flutter
- **Impact:** **REGULATOR FAILURE RISK** - Cannot prove "what user saw = what they signed"

---

## ✅ What's Already Correct

| Component | Status | Notes |
|-----------|--------|-------|
| fl_chart (Flutter) | ✅ Installed | v1.1.1 in pubspec.yaml |
| web3dart (Flutter) | ✅ Installed | v3.0.1 in pubspec.yaml |
| Flutter Material 3 | ✅ In use | Standard Flutter UI |
| Web Crypto API | ⚠️ Started | UI Integrity Service exists |
| UI Snapshot Hashing | ✅ Implemented | New ui-snapshot-chain.ts |
| RBAC System | ✅ Implemented | New rbac.ts types |
| Focus/War Room Shells | ✅ Implemented | Phase 1 complete |

---

## 📦 Required Package Changes

### Next.js (frontend/frontend/package.json)

**ADD:**
```json
{
  "dependencies": {
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
    "reagraph": "^4.18.0",
    "@unovis/ts": "^1.4.0",
    "@unovis/react": "^1.4.0"
  }
}
```

**REMOVE:**
```json
{
  "dependencies": {
    "recharts": "^3.6.0"  // REMOVE - replace with ECharts
  }
}
```

### Flutter (frontend/amttp_app/pubspec.yaml)

**Current is mostly correct. May need:**
```yaml
dependencies:
  # Already have fl_chart, web3dart, crypto
  # May need to add:
  pointycastle: ^3.7.3  # For advanced crypto if needed
```

---

## 🏗️ Implementation Priority

### Phase 3: War Room Visualization Stack (URGENT)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| 🔴 P0 | Install & configure ECharts | 2 hours | Replace Recharts |
| 🔴 P0 | Install Reagraph | 1 hour | Graph engine |
| 🔴 P0 | Install Unovis | 1 hour | Sankey engine |
| 🔴 P1 | Create VelocityHeatmap (ECharts) | 4 hours | Time anomaly detection |
| 🔴 P1 | Create GraphExplorer (Reagraph) | 6 hours | Wallet relationships |
| 🔴 P1 | Create SankeyAuditor (Unovis) | 4 hours | Value flow |
| 🟡 P2 | Migrate existing charts to ECharts | 3 hours | Consistency |

### Phase 4: Secure Bridge (CRITICAL FOR COMPLIANCE)

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| 🔴 P0 | Create Bridge Transport (postMessage) | 4 hours | Communication |
| 🔴 P0 | Implement dart:js_interop in Flutter | 4 hours | Message receiving |
| 🔴 P0 | Create TransactionIntent schema | 2 hours | Data contract |
| 🔴 P1 | Implement EIP-712 signing | 6 hours | Cryptographic proof |
| 🔴 P1 | Create Flutter verification UI | 4 hours | Trusted surface |
| 🟡 P2 | Backend intent verification | 4 hours | Server validation |

---

## 📐 Correct Architecture (What We Need)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AMTTP VISUALIZATION STACK                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              NEXT.JS - DETECTION STUDIO                      │    │
│  │                                                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │  REAGRAPH   │  │   UNOVIS    │  │  ECHARTS    │         │    │
│  │  │  (WebGL)    │  │  (Sankey)   │  │  (Time/Stat)│         │    │
│  │  │             │  │             │  │             │         │    │
│  │  │ • Topology  │  │ • Value flow│  │ • Heatmaps  │         │    │
│  │  │ • Clusters  │  │ • Splits    │  │ • Time zoom │         │    │
│  │  │ • Hops      │  │ • Smurfing  │  │ • Anomalies │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  │                                                               │    │
│  │  ┌─────────────────────────────────────────────────┐         │    │
│  │  │         WEB CRYPTO API + UI SNAPSHOT            │         │    │
│  │  │  • SHA-256 hashing  • Intent creation           │         │    │
│  │  └─────────────────────────────────────────────────┘         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                        │
│                              │ postMessage                            │
│                              │ (TransactionIntent)                    │
│                              ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    SECURE BRIDGE                             │    │
│  │                                                               │    │
│  │  • Verify hash consistency                                    │    │
│  │  • Validate intent structure                                  │    │
│  │  • Check timestamp freshness                                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              │                                        │
│                              │ dart:js_interop                        │
│                              ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │              FLUTTER - TRUST & AUTHORITY                     │    │
│  │                                                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │  FL_CHART   │  │ FLUTTER M3  │  │  WEB3DART   │         │    │
│  │  │             │  │             │  │             │         │    │
│  │  │ • Trust viz │  │ • UI shell  │  │ • EIP-712   │         │    │
│  │  │ • Summaries │  │ • Multisig  │  │ • Signing   │         │    │
│  │  │ • Pillars   │  │ • Governance│  │ • Submit    │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  │                                                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Summary: What We Have vs What We Need

| Aspect | Current | Required | Action |
|--------|---------|----------|--------|
| Graph Viz | ❌ None | Reagraph | Install + Implement |
| Sankey | ❌ None | Unovis | Install + Implement |
| Time/Stats | Recharts | ECharts | **Replace** |
| Flutter Charts | fl_chart ✅ | fl_chart | Keep |
| Web3 (Flutter) | web3dart ✅ | web3dart | Keep |
| Bridge | ❌ None | postMessage + js_interop | **Critical: Implement** |
| UI Integrity | ⚠️ Started | Full chain | Complete |
| RBAC | ✅ Done | Done | Keep |

---

## 🚨 Immediate Action Items

1. **Install missing packages** (Next.js):
   ```bash
   npm install echarts echarts-for-react reagraph @unovis/ts @unovis/react
   npm uninstall recharts
   ```

2. **Create Bridge Infrastructure**:
   - Next.js: `src/lib/bridge/transport.ts`
   - Next.js: `src/lib/bridge/intent.ts`
   - Flutter: `lib/core/bridge/js_bridge.dart`
   - Flutter: `lib/core/bridge/intent_verifier.dart`

3. **Migrate Charts**:
   - Replace `RiskDistributionChart.tsx` (Recharts → ECharts)
   - Replace `TimelineChart.tsx` (Recharts → ECharts)
   - Create `VelocityHeatmap.tsx` (new, ECharts)
   - Create `GraphExplorer.tsx` (new, Reagraph)
   - Create `SankeyAuditor.tsx` (new, Unovis)

---

## 📋 Conclusion

**Current implementation uses WRONG visualization libraries.**

- Recharts is good for simple dashboards, NOT for forensic investigation tools
- Missing graph engine entirely (Reagraph)
- Missing Sankey flow visualization (Unovis)
- Missing secure bridge (compliance risk)

**Recommendation:** Prioritize Phase 3 (visualization stack) and Phase 4 (secure bridge) before any other feature work. The bridge is **mandatory for FCA compliance**.
