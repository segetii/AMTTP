# AMTTP UI Sitemaps by User Profile

This document provides visual sitemaps for each user profile in the AMTTP (Advanced Money Transfer Protocol) application.

---

## 📊 Application Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AMTTP PLATFORM                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐                   │
│   │   END USER    │    │    ADMIN      │    │  COMPLIANCE   │                   │
│   │   (Wallet)    │    │  (Dashboard)  │    │   (Officer)   │                   │
│   └───────┬───────┘    └───────┬───────┘    └───────┬───────┘                   │
│           │                    │                    │                            │
│           ▼                    ▼                    ▼                            │
│   ┌───────────────────────────────────────────────────────────────┐             │
│   │                    SHARED INFRASTRUCTURE                       │             │
│   │  • Web3 Wallet Connection  • AI Risk Assessment               │             │
│   │  • Blockchain Integration  • Real-time Monitoring             │             │
│   └───────────────────────────────────────────────────────────────┘             │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 👤 Profile 1: END USER (Standard User)

The standard user profile for conducting secure transfers and managing their wallet.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           END USER SITEMAP                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   HOME PAGE     │
                              │   (Welcome)     │
                              │   Route: /      │
                              └────────┬────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
   ┌────────────────┐        ┌────────────────┐        ┌────────────────┐
   │  NOT CONNECTED │        │   CONNECTED    │        │  QUICK LINKS   │
   │                │        │                │        │                │
   │ • Welcome View │        │ • Main Content │        │ • Transfer     │
   │ • Feature Cards│        │ • Bottom Nav   │        │ • History      │
   │ • Connect CTA  │        │ • Tab Views    │        │ • Wallet       │
   │ • Trust Badges │        │                │        │ • Admin        │
   └────────────────┘        └───────┬────────┘        └────────────────┘
                                     │
       ┌─────────────────────────────┼─────────────────────────────┐
       │                             │                             │
       ▼                             ▼                             ▼
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│     SEND     │           │   HISTORY    │           │  ANALYTICS   │
│   (Tab 0)    │           │   (Tab 1)    │           │   (Tab 2)    │
├──────────────┤           ├──────────────┤           ├──────────────┤
│              │           │              │           │              │
│ SecureTransfer           │ • TX List    │           │ • Risk Vis   │
│ Widget:      │           │ • Risk Scores│           │ • DQN Metrics│
│              │           │ • Filters    │           │ • Charts     │
│ • Recipient  │           │ • TX Details │           │ • Score Hist │
│ • Amount     │           │              │           │              │
│ • Risk Check │           └──────────────┘           └──────────────┘
│ • MEV Protect│                  │
│ • Confirm    │                  ▼
│              │           ┌──────────────┐
└──────────────┘           │  TX DETAIL   │
       │                   │   (Modal)    │
       ▼                   ├──────────────┤
┌──────────────┐           │ • TX ID      │
│ TX RESULT    │           │ • Addresses  │
│   (Modal)    │           │ • Amount     │
├──────────────┤           │ • Risk Score │
│ • Success/   │           │ • Status     │
│   Failure    │           │ • Timestamp  │
│ • TX Hash    │           └──────────────┘
│ • Details    │
└──────────────┘

       │
       ▼
┌──────────────┐
│  SECURITY    │
│   (Tab 3)    │
├──────────────┤
│              │
│ • Wallet Info│
│ • Security   │
│   Settings   │
│ • Risk Prefs │
│              │
└──────────────┘
```

### End User Navigation Flow

```
HOME (/)
├── 📱 Bottom Navigation Bar (when connected)
│   ├── Send (Tab 0)      → SecureTransferWidget
│   ├── History (Tab 1)   → Transaction History List
│   ├── Analytics (Tab 2) → Risk Visualizer + DQN Metrics  
│   └── Security (Tab 3)  → Security & Wallet Settings
│
├── 🔗 Quick Links (sidebar)
│   ├── /transfer → Dedicated Transfer Page
│   ├── /history  → Full History Page
│   ├── /wallet   → Wallet Management Page
│   └── /admin    → Admin Dashboard (if authorized)
│
└── ⚙️ Header Actions
    └── /settings → Settings Page
```

---

## 👨‍💼 Profile 2: ADMIN USER

The administrator profile with full system oversight and management capabilities.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           ADMIN SITEMAP                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │   ADMIN PAGE    │
                              │   Route: /admin │
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────┐      ┌─────────┐     ┌─────────┐    ┌─────────┐      ┌─────────┐
│OVERVIEW │      │   DQN   │     │  TRANS  │    │POLICIES │      │ WEBHOOKS│
│ (Tab 0) │      │ANALYTICS│     │ (Tab 2) │    │ (Tab 3) │      │(Tab 3.2)│
│         │      │ (Tab 1) │     │         │    │         │      │         │
└────┬────┘      └────┬────┘     └────┬────┘    └────┬────┘      └─────────┘
     │                │               │               │
     ▼                ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           OVERVIEW TAB                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │System Status │  │  DQN Model   │  │ Transactions │  │Fraud Blocked │ │
│  │  (Health)    │  │   Status     │  │    Today     │  │    Count     │ │
│  │ • Uptime %   │  │ • Version    │  │ • Count      │  │ • Fraud Rate │ │
│  │ • Operational│  │ • Active     │  │ • Change %   │  │ • Blocked #  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐                                     │
│  │ Pending EDD  │  │   Alerts     │                                     │
│  │   Cases      │  │ Unresolved   │                                     │
│  │ • Count      │  │ • Count      │                                     │
│  └──────────────┘  └──────────────┘                                     │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │              REAL-TIME TRANSACTION FEED                            │ │
│  │  • Live TX Stream  • Risk Indicators  • Status Updates             │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │              RISK DISTRIBUTION CHART (Pie)                         │ │
│  │  • Low Risk %  • Medium Risk %  • High Risk %  • Blocked %         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        DQN ANALYTICS TAB                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    MODEL PERFORMANCE METRICS                       │  │
│  │   ┌──────────┐    ┌──────────┐    ┌──────────┐                    │  │
│  │   │ F1 Score │    │Precision │    │  Recall  │                    │  │
│  │   │  0.669   │    │  0.723   │    │  0.625   │                    │  │
│  │   │  66.9%   │    │  72.3%   │    │  62.5%   │                    │  │
│  │   └──────────┘    └──────────┘    └──────────┘                    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                 FEATURE IMPORTANCE (Bar Chart)                     │  │
│  │   Amount ████████████████████ 0.85                                │  │
│  │   Frequency ██████████████ 0.72                                   │  │
│  │   Geographic █████████████ 0.68                                   │  │
│  │   Time ██████████ 0.54                                            │  │
│  │   Account Age █████████ 0.49                                      │  │
│  │   Velocity ████████ 0.43                                          │  │
│  │   Cross-border ███████ 0.38                                       │  │
│  │   Deviation ██████ 0.31                                           │  │
│  │   Reputation █████ 0.27                                           │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                 TRAINING DATASET ANALYSIS                          │  │
│  │   • Total Transactions: 28,457                                    │  │
│  │   • Fraud Cases: 1,842 (6.5%)                                     │  │
│  │   • Training Time: 2.3 hours                                      │  │
│  │   • Model Size: 15.2 MB                                           │  │
│  │   • Inference Time: <100ms                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              LIVE PERFORMANCE MONITORING (Line Chart)              │  │
│  │              Accuracy over last 24 hours                           │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        TRANSACTIONS TAB                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Filter: [All] [High Risk] [Blocked]    Showing X transactions  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    TRANSACTION LIST                              │    │
│  │  ┌───────────────────────────────────────────────────────────┐  │    │
│  │  │ 🟢 0.15 ETH  From: 0x742d...  To: 0x8ba1...  APPROVED     │  │    │
│  │  │ 🟡 0.25 ETH  From: 0x8ba1...  To: 0x742d...  ESCROW       │  │    │
│  │  │ 🔴 1.50 ETH  From: 0x742d...  To: 0xAb58...  BLOCKED      │  │    │
│  │  │ 🟢 0.50 ETH  From: 0xC02a...  To: 0x742d...  APPROVED     │  │    │
│  │  └───────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              TRANSACTION DETAIL MODAL (on tap)                   │    │
│  │  • Transaction ID    • Amount       • Risk Score                 │    │
│  │  • From Address      • To Address   • Status                     │    │
│  │  • Timestamp         • Actions: [APPROVE] [REJECT]               │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                        POLICIES TAB                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                     ACTIVE POLICIES                                │  │
│  │  ✓ AML Screening      | Anti-money laundering rules    | AML     │  │
│  │  ✓ Sanctions Check    | OFAC/SDN list verification     | OFAC    │  │
│  │  ✓ Velocity Limits    | Transaction frequency caps     | LIMITS  │  │
│  │  ✓ Geographic Rules   | Country-based restrictions     | GEO     │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                    RISK THRESHOLDS                                 │  │
│  │  Low Risk Threshold:    ▓▓▓▓▓░░░░░░░░░░░░░░░  25%                │  │
│  │  Medium Risk Threshold: ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  50%                │  │
│  │  High Risk Threshold:   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░  75%                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                   TRANSACTION LIMITS                               │  │
│  │  Daily Limit:        $50,000                                      │  │
│  │  Transaction Limit:  $10,000                                      │  │
│  │  EDD Threshold:      $15,000                                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                   REGISTERED WEBHOOKS                              │  │
│  │  • High Risk Alert    → https://api.example.com/alerts           │  │
│  │  • Blocked TX         → https://api.example.com/blocked          │  │
│  │  • Dispute Created    → https://api.example.com/disputes         │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Admin Navigation Flow

```
ADMIN (/admin)
├── 📊 Tab Navigation
│   ├── Overview (Tab 0)
│   │   ├── System Health Cards
│   │   ├── Compliance Status (EDD, Alerts)
│   │   ├── Real-time TX Feed
│   │   └── Risk Distribution Chart
│   │
│   ├── DQN Analytics (Tab 1)
│   │   ├── Performance Metrics (F1, Precision, Recall)
│   │   ├── Feature Importance Chart
│   │   ├── Training Dataset Stats
│   │   └── Live Performance Graph
│   │
│   ├── Transactions (Tab 2)
│   │   ├── Filter Controls
│   │   ├── Transaction List
│   │   └── Detail Modal → Approve/Reject Actions
│   │
│   └── Policies (Tab 3)
│       ├── Active Policies List
│       ├── Risk Threshold Sliders
│       ├── Transaction Limits
│       └── Webhook Configuration
│
└── 🔙 Back to Home (/)
```

---

## 🔍 Profile 3: COMPLIANCE OFFICER

The compliance officer profile focuses on regulatory oversight, EDD reviews, and audit trails.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       COMPLIANCE OFFICER SITEMAP                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  ADMIN PAGE     │
                              │  (Compliance    │
                              │   Focus)        │
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┴───────────────┬─────────────────┐
     │                 │                               │                 │
     ▼                 ▼                               ▼                 ▼
┌─────────────┐  ┌─────────────┐              ┌─────────────┐  ┌─────────────┐
│  OVERVIEW   │  │TRANSACTIONS │              │   POLICIES  │  │   REPORTS   │
│ (Compliance)│  │  (Review)   │              │(Management) │  │  (Audit)    │
└──────┬──────┘  └──────┬──────┘              └──────┬──────┘  └──────┬──────┘
       │                │                            │                │
       ▼                ▼                            ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          COMPLIANCE DASHBOARD                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        EDD CASE MANAGEMENT                                  │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  📋 PENDING EDD CASES                                                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ Case #001  | 0x742d...  | $25,000  | High Risk | Awaiting Review   │   │ │
│  │  │ Case #002  | 0x8ba1...  | $18,500  | Medium    | Documents Pending │   │ │
│  │  │ Case #003  | 0xAb58...  | $50,000  | Critical  | Urgent Review     │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │  [Review Case] [Request Docs] [Approve] [Escalate] [Reject]                │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        SANCTIONS SCREENING                                  │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  🚫 BLOCKED ADDRESSES (Sanctions List Matches)                             │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ 0xdead... | OFAC SDN List    | Blocked Since: 2026-01-01          │   │ │
│  │  │ 0xbeef... | OFAC SDN List    | Blocked Since: 2025-12-15          │   │ │
│  │  │ 0xcafe... | EU Sanctions     | Blocked Since: 2025-11-20          │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │  [Add Address] [Remove] [Update Lists] [Export Report]                     │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        SUSPICIOUS ACTIVITY REPORTS                          │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  📊 SAR QUEUE                                                              │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ SAR-2026-001 | Structuring Detected  | Priority: High   | Draft    │   │ │
│  │  │ SAR-2026-002 | Unusual Pattern       | Priority: Medium | Review   │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │  [Create SAR] [Submit to FCA] [Archive]                                    │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        AUDIT TRAIL                                          │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  📝 RECENT COMPLIANCE ACTIONS                                              │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ 2026-01-04 21:30 | EDD Approved    | Case #001 | Officer: J.Smith │   │ │
│  │  │ 2026-01-04 20:15 | SAR Submitted   | SAR-001   | Officer: M.Jones │   │ │
│  │  │ 2026-01-04 19:45 | Address Blocked | 0xdead... | System: Auto     │   │ │
│  │  │ 2026-01-04 18:30 | Policy Updated  | AML v2.1  | Officer: J.Smith │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │  [Export Audit Log] [Filter by Date] [Filter by Officer]                   │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Compliance Officer Navigation Flow

```
ADMIN (/admin) - Compliance Focus
├── 📊 Overview Tab (Compliance Metrics)
│   ├── Pending EDD Cases Counter
│   ├── Unresolved Alerts Counter
│   ├── Fraud Blocked Statistics
│   └── Compliance Status Dashboard
│
├── 📋 Transactions Tab (High-Risk Review)
│   ├── Filter: High Risk / Blocked
│   ├── EDD Case Queue
│   ├── Transaction Review Modal
│   │   ├── Full Transaction Details
│   │   ├── Risk Assessment Breakdown
│   │   ├── Customer Information
│   │   └── Actions: Approve / Reject / Escalate
│   └── Bulk Actions
│
├── 📜 Policies Tab (Regulatory Management)
│   ├── Active Policy Management
│   ├── Risk Threshold Configuration
│   ├── Transaction Limit Settings
│   ├── EDD Threshold Configuration
│   └── Webhook Notifications Setup
│
└── 📈 Reports (via API/Export)
    ├── SAR Generation
    ├── Audit Trail Export
    ├── Compliance Reports
    └── Regulatory Filing
```

---

## 🔧 Shared Pages (All Profiles)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SHARED PAGES                                           │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    WALLET       │     │    SETTINGS     │     │    HISTORY      │
│  Route: /wallet │     │ Route: /settings│     │ Route: /history │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│                 │     │                 │     │                 │
│ • Balance Card  │     │ GENERAL         │     │ • TX List       │
│   - ETH Balance │     │ • Language      │     │ • Risk Scores   │
│   - USD Value   │     │ • Theme         │     │ • Status Filter │
│   - Connected   │     │ • Notifications │     │ • Date Filter   │
│                 │     │                 │     │                 │
│ • Address       │     │ SECURITY        │     │ • TX Detail     │
│   - Copy        │     │ • Biometrics    │     │   Modal         │
│   - QR Code     │     │ • Auto-lock     │     │                 │
│                 │     │ • TX Limit      │     │                 │
│ • Tokens        │     │                 │     │                 │
│   - ETH         │     │ NETWORK         │     │                 │
│   - ERC-20s     │     │ • RPC Endpoint  │     │                 │
│                 │     │ • Gas Price     │     │                 │
│ • Quick Actions │     │                 │     │                 │
│   - Send        │     │ COMPLIANCE      │     │                 │
│   - Receive     │     │ • Risk Warnings │     │                 │
│   - Swap        │     │ • Confirmation  │     │                 │
│                 │     │ • Slippage      │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘

┌─────────────────┐
│    TRANSFER     │
│Route: /transfer │
├─────────────────┤
│                 │
│SecureTransfer   │
│Widget:          │
│                 │
│ • Recipient     │
│   Address       │
│                 │
│ • Amount        │
│   (ETH/USD)     │
│                 │
│ • Risk Preview  │
│   - Score       │
│   - Warning     │
│                 │
│ • MEV Protection│
│   Toggle        │
│                 │
│ • Review &      │
│   Confirm       │
│                 │
│ • Status        │
│   Updates       │
│                 │
└─────────────────┘
```

---

## 📱 Route Summary

| Route | Page | Access | Description |
|-------|------|--------|-------------|
| `/` | HomePage | All | Landing page, wallet connection, main dashboard |
| `/wallet` | WalletPage | All | Wallet management, balances, addresses |
| `/transfer` | TransferPage | All | Dedicated transfer page with SecureTransferWidget |
| `/history` | HistoryPage | All | Transaction history with filters |
| `/admin` | AdminPage | Admin/Compliance | Full admin dashboard with 4 tabs |
| `/settings` | SettingsPage | All | User preferences and configuration |

---

## 🎨 UI Component Library

```
SHARED WIDGETS
├── SecureTransferWidget    - Complete transfer flow with risk assessment
├── RiskVisualizerWidget    - Risk score visualization and breakdown
├── RiskLevelIndicator      - Color-coded risk badge
├── InteractiveWalletWidget - Wallet connection and management
├── FeaturesCarousel        - Feature showcase on landing page
└── TransactionCard         - Individual transaction display
```

---

## 🆕 NEW PAGES REQUIRED FOR COMPLETE COVERAGE

The following pages are required to cover all smart contract functionality:

---

## 🔄 Profile: NFT TRADER

Complete NFT swap functionality for NFT ↔ ETH and NFT ↔ NFT swaps.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           NFT SWAP SITEMAP                                       │
│                           Route: /nft-swap                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  NFT SWAP PAGE  │
                              │ Route: /nft-swap│
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  NFT → ETH  │  │  NFT → NFT  │  │   ACTIVE    │  │  COMPLETED  │  │   REFUNDS   │
│   SWAP      │  │    SWAP     │  │   SWAPS     │  │    SWAPS    │  │             │
│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │   (Tab 3)   │  │   (Tab 4)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘
       │                │               │
       ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          NFT → ETH SWAP TAB                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        SELECT YOUR NFT                                      │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │ │
│  │  │  [NFT 1] │  │  [NFT 2] │  │  [NFT 3] │  │  [NFT 4] │  ...              │ │
│  │  │  BAYC    │  │  Azuki   │  │  Doodles │  │  Moonbird│                   │ │
│  │  │  #1234   │  │  #5678   │  │  #9012   │  │  #3456   │                   │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        SWAP CONFIGURATION                                   │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Selected NFT: BAYC #1234                                                  │ │
│  │  ┌──────────────────────────────────┐                                      │ │
│  │  │ ETH Amount Requested:  [____] ETH │                                     │ │
│  │  │ Recipient Address:     [________] │                                     │ │
│  │  │ Hash Lock (optional):  [________] │                                     │ │
│  │  │ Time Lock:             [24 hours] │                                     │ │
│  │  └──────────────────────────────────┘                                      │ │
│  │                                                                             │ │
│  │  Risk Assessment: 🟢 Low Risk (Score: 0.23)                                │ │
│  │                                                                             │ │
│  │                    [Initiate NFT → ETH Swap]                               │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                          ACTIVE SWAPS TAB                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    PENDING SWAPS (Waiting for Counterparty)             │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │ Swap #abc123  │ BAYC #1234 → 10 ETH │ Waiting for ETH │ ⏰ 23:45:00     │    │
│  │ Swap #def456  │ Azuki #567 → NFT    │ Waiting for NFT │ ⏰ 12:30:00     │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    READY TO COMPLETE                                    │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │ Swap #ghi789  │ BAYC #1234 → 10 ETH │ ETH Deposited   │ [COMPLETE SWAP] │    │
│  │               │ Enter Preimage: [_____________________]                 │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    AWAITING APPROVAL (High Risk)                        │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │ Swap #jkl012  │ Rare NFT → 50 ETH   │ Pending Approval │ 🟡 High Risk   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `initiateNFTtoETHSwap()` - Start NFT ↔ ETH swap
- `depositETHForNFT()` - Deposit ETH to complete swap
- `completeNFTSwap()` - Complete swap with preimage
- `initiateNFTtoNFTSwap()` - Start NFT ↔ NFT swap
- `depositNFTForSwap()` - Deposit second NFT
- `completeNFTtoNFTSwap()` - Complete NFT-to-NFT swap
- `refundNFTSwap()` - Refund expired swap
- `approveSwap()` - (Approver) Approve high-risk swap

---

## ⚖️ Profile: DISPUTE PARTICIPANT

Complete dispute resolution with Kleros arbitration integration.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DISPUTE CENTER SITEMAP                                   │
│                         Route: /disputes                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │ DISPUTE CENTER  │
                              │Route: /disputes │
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   CREATE    │  │   ACTIVE    │  │   SUBMIT    │  │   RESOLVED  │  │   APPEALS   │
│  DISPUTE    │  │  DISPUTES   │  │  EVIDENCE   │  │   HISTORY   │  │             │
│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │   (Tab 3)   │  │   (Tab 4)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘
       │                │               │
       ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       CREATE DISPUTE TAB                                         │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    STEP 1: SELECT TRANSACTION                              │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Your Recent Transactions (Disputeable):                                  │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │
│  │  │ ⚪ TX 0xabc... │ 1.5 ETH to 0x742d... │ Jan 4, 2026 │ [Select]      │   │ │
│  │  │ ⚪ TX 0xdef... │ 0.8 ETH to 0x8ba1... │ Jan 3, 2026 │ [Select]      │   │ │
│  │  │ ⚪ TX 0xghi... │ 2.0 ETH to 0xAb58... │ Jan 2, 2026 │ [Select]      │   │ │
│  │  └─────────────────────────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    STEP 2: DISPUTE DETAILS                                 │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Reason for Dispute:                                                       │ │
│  │  ○ Goods/Services Not Received                                            │ │
│  │  ○ Goods/Services Not As Described                                        │ │
│  │  ○ Unauthorized Transaction                                               │ │
│  │  ○ Other: [____________________]                                          │ │
│  │                                                                             │ │
│  │  Evidence Description:                                                     │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ Describe the issue and provide initial evidence...                   │  │ │
│  │  │ ________________________________________________________________     │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    STEP 3: ARBITRATION FEE                                 │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  ⚠️  Arbitration Fee Required: 0.1 ETH                                    │ │
│  │      (Refunded if you win the dispute)                                    │ │
│  │                                                                             │ │
│  │      Kleros Arbitration Court: General Court                              │ │
│  │      Expected Resolution Time: 3-7 days                                   │ │
│  │                                                                             │ │
│  │                     [⚖️ Challenge Transaction]                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       ACTIVE DISPUTES TAB                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                    MY ACTIVE DISPUTES                                   │    │
│  ├─────────────────────────────────────────────────────────────────────────┤    │
│  │                                                                          │    │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │    │
│  │  │ Dispute #001 - TX 0xabc...                                         │ │    │
│  │  │                                                                     │ │    │
│  │  │ Status: 🟡 EVIDENCE PHASE                                          │ │    │
│  │  │ ━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━             │ │    │
│  │  │ Created → Evidence → Voting → Ruling → Appeal → Final              │ │    │
│  │  │                                                                     │ │    │
│  │  │ Deadline: 2 days 14 hours remaining                                │ │    │
│  │  │                                                                     │ │    │
│  │  │ [View Details] [Submit Evidence] [View Respondent Evidence]        │ │    │
│  │  └────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                          │    │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │    │
│  │  │ Dispute #002 - TX 0xdef...                                         │ │    │
│  │  │                                                                     │ │    │
│  │  │ Status: 🟢 RULING ISSUED                                           │ │    │
│  │  │ Ruling: In Your Favor ✓                                            │ │    │
│  │  │                                                                     │ │    │
│  │  │ Appeal Window: 5 days remaining                                    │ │    │
│  │  │                                                                     │ │    │
│  │  │ [View Details] [Request Appeal] (if eligible)                      │ │    │
│  │  └────────────────────────────────────────────────────────────────────┘ │    │
│  │                                                                          │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

                              DISPUTE DETAIL PAGE
                              Route: /dispute/:id
                              
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       DISPUTE DETAIL VIEW                                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Dispute ID: #001                     Status: Evidence Phase                    │
│  Transaction: 0xabc123...def456                                                 │
│  Amount: 1.5 ETH                      Created: Jan 4, 2026                      │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                         DISPUTE TIMELINE                                    │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  ✓ Jan 4, 10:00 - Dispute Created by 0x742d...                            │ │
│  │  ✓ Jan 4, 10:00 - Initial Evidence Submitted                              │ │
│  │  ✓ Jan 4, 12:30 - Respondent Notified                                     │ │
│  │  ● Jan 4, 14:00 - Respondent Evidence Submitted                           │ │
│  │  ○ Jan 6, 10:00 - Evidence Period Ends                                    │ │
│  │  ○ Jan 7, 10:00 - Voting Begins                                           │ │
│  │  ○ Jan 9, 10:00 - Ruling Issued                                           │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────────┐ │
│  │      YOUR EVIDENCE               │  │    RESPONDENT EVIDENCE              │ │
│  ├──────────────────────────────────┤  ├──────────────────────────────────────┤ │
│  │ • Screenshot of agreement       │  │ • Delivery confirmation             │ │
│  │ • Communication logs            │  │ • Tracking information              │ │
│  │ • Payment confirmation          │  │ • Terms of service                  │ │
│  │                                  │  │                                      │ │
│  │ [+ Add More Evidence]           │  │                                      │ │
│  └──────────────────────────────────┘  └──────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                         SUBMIT NEW EVIDENCE                                 │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Evidence Type: [Dropdown: Text / File / IPFS Link]                       │ │
│  │  Content/URI: [_________________________________________________]         │ │
│  │  Description: [_________________________________________________]         │ │
│  │                                                                             │ │
│  │                          [Submit Evidence]                                  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `challengeTransaction()` - Initiate dispute with arbitration fee
- `submitEvidence()` - Submit evidence for ongoing dispute
- `requestAppeal()` - Request appeal on ruling
- `raiseDispute()` - (from AMTTPCore) Initial dispute raise

---

## 🌐 Profile: CROSS-CHAIN USER

Cross-chain transfers and risk score propagation via LayerZero.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        CROSS-CHAIN SITEMAP                                       │
│                        Route: /cross-chain                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  CROSS-CHAIN    │
                              │    TRANSFER     │
                              │Route:/cross-chain│
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   TRANSFER  │  │   CHAIN     │  │   PENDING   │  │   HISTORY   │  │   ADMIN     │
│   (Tab 0)   │  │   STATUS    │  │ TRANSFERS   │  │   (Tab 3)   │  │  (Admin)    │
│             │  │   (Tab 1)   │  │   (Tab 2)   │  │             │  │   (Tab 4)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘
       │                │               │
       ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       CROSS-CHAIN TRANSFER TAB                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    SELECT DESTINATION CHAIN                                │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  Source: Ethereum Mainnet ──────────────────────▶ Destination: [▼]        │ │
│  │                                                                             │ │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐            │ │
│  │  │  Polygon   │  │  Arbitrum  │  │  Optimism  │  │    BSC     │            │ │
│  │  │   🟢 Live   │  │   🟢 Live   │  │   🟢 Live   │  │   🟡 Busy   │            │ │
│  │  │  ChainId:  │  │  ChainId:  │  │  ChainId:  │  │  ChainId:  │            │ │
│  │  │    137     │  │   42161    │  │     10     │  │     56     │            │ │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘            │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    TRANSFER DETAILS                                        │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Recipient Address: [________________________________________]             │ │
│  │  Amount:            [________] ETH                                         │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  FEE ESTIMATION (LayerZero)                                          │  │ │
│  │  │  • Native Fee:       0.0025 ETH                                      │  │ │
│  │  │  • LayerZero Fee:    0.0010 ETH                                      │  │ │
│  │  │  • Total Fees:       0.0035 ETH (~$8.50)                             │  │ │
│  │  │  • Estimated Time:   ~2-5 minutes                                    │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  Risk Assessment: 🟢 Low Risk (Cross-chain verified)                       │ │
│  │                                                                             │ │
│  │                    [🌐 Initiate Cross-Chain Transfer]                      │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       CHAIN STATUS TAB                                           │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    SUPPORTED CHAINS                                        │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │ Chain          │ Status │ Rate Limit │ Tx Today │ Avg Time │ Actions      │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │ Polygon (137)  │ 🟢 Live │ 100/block  │ 2,453    │ 2 min    │ [Transfer]   │ │
│  │ Arbitrum(42161)│ 🟢 Live │ 100/block  │ 1,832    │ 3 min    │ [Transfer]   │ │
│  │ Optimism (10)  │ 🟢 Live │ 100/block  │ 1,245    │ 3 min    │ [Transfer]   │ │
│  │ BSC (56)       │ 🟡 Busy │ 50/block   │ 3,891    │ 5 min    │ [Transfer]   │ │
│  │ Avalanche(43114│ 🔴 Pause│ 0/block    │ 0        │ N/A      │ [Disabled]   │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ADMIN CONTROLS (if authorized):                                                │
│  [Pause Chain] [Unpause Chain] [Set Rate Limit] [Configure Trusted Remote]     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `sendRiskScore()` - Propagate risk score to other chains
- `propagateDisputeResult()` - Share dispute result cross-chain
- `pauseChain()` - (Admin) Pause specific chain
- `unpauseChain()` - (Admin) Resume chain
- `setChainRateLimit()` - (Admin) Set rate limits
- `setTrustedRemote()` - (Admin) Configure trusted remotes

---

## 🔐 Profile: MULTISIG / SAFE USER

Gnosis Safe integration with AMTTP risk assessment.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        SAFE MANAGEMENT SITEMAP                                   │
│                        Route: /safe                                              │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │ SAFE MANAGEMENT │
                              │   Route: /safe  │
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  REGISTER   │  │   QUEUED    │  │  WHITELIST  │  │   AUDIT     │  │  SETTINGS   │
│    SAFE     │  │    TXS      │  │  /BLACKLIST │  │    LOG      │  │             │
│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │   (Tab 3)   │  │   (Tab 4)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘
       │                │               │
       ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       REGISTER SAFE TAB                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    REGISTER YOUR GNOSIS SAFE                               │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Safe Address: [________________________________________]                  │ │
│  │                                                                             │ │
│  │  Risk Threshold (0-100):  [____]  (Transactions above trigger queue)      │ │
│  │                                                                             │ │
│  │  Initial Operators:                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ + Operator 1: [0x742d...] (You - Auto-added)                        │  │ │
│  │  │ + Operator 2: [________________________________________] [Add]       │  │ │
│  │  │ + Operator 3: [________________________________________] [Add]       │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  ⚠️ Note: AMTTP will act as a Guard for your Safe, requiring             │ │
│  │     >50% operator approval for high-risk transactions.                    │ │
│  │                                                                             │ │
│  │                    [🔐 Register Safe with AMTTP]                           │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    YOUR REGISTERED SAFES                                   │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │ Safe 0x8ba1... │ 3 Operators │ Threshold: 70 │ Active │ [Manage] [Config] │ │
│  │ Safe 0xAb58... │ 5 Operators │ Threshold: 85 │ Active │ [Manage] [Config] │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       QUEUED TRANSACTIONS TAB                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    PENDING APPROVALS                                       │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ TX Hash: 0xabc123...                                                 │  │ │
│  │  │ To: 0x742d35Cc6634C0532925a3b844Bc454e4438f44e                       │  │ │
│  │  │ Value: 5.0 ETH                  Data: 0x (Transfer)                  │  │ │
│  │  │ Risk Score: 🔴 78/100                                                 │  │ │
│  │  │                                                                       │  │ │
│  │  │ Approval Progress: ████████░░░░░░░░░░░░  2/4 (50%)                   │  │ │
│  │  │ Approvers: ✓ You, ✓ 0x8ba1..., ○ 0xAb58..., ○ 0xC02a...             │  │ │
│  │  │                                                                       │  │ │
│  │  │ [✓ Approve] [✗ Reject] [View Details]                                │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ TX Hash: 0xdef456...                                                 │  │ │
│  │  │ To: 0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B                       │  │ │
│  │  │ Value: 10.0 ETH                 Risk Score: 🟡 65/100                 │  │ │
│  │  │                                                                       │  │ │
│  │  │ Approval Progress: ██████████████████░░  3/4 (75%) - READY           │  │ │
│  │  │                                                                       │  │ │
│  │  │ [🚀 Execute Transaction] [View Details]                              │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       WHITELIST / BLACKLIST TAB                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  Select Safe: [Safe 0x8ba1... ▼]                                                │
│                                                                                  │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────────┐ │
│  │      ✅ WHITELIST (Trusted)      │  │      🚫 BLACKLIST (Blocked)          │ │
│  ├──────────────────────────────────┤  ├──────────────────────────────────────┤ │
│  │ 0x742d... (Exchange)    [Remove] │  │ 0xdead... (Sanctioned)    [Remove]  │ │
│  │ 0x8ba1... (Partner)     [Remove] │  │ 0xbeef... (Scammer)       [Remove]  │ │
│  │ 0xAb58... (Treasury)    [Remove] │  │                                      │ │
│  │                                  │  │                                      │ │
│  │ [+ Add to Whitelist]             │  │ [+ Add to Blacklist]                │ │
│  └──────────────────────────────────┘  └──────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `registerSafe()` - Register Safe with AMTTP
- `updateSafeConfig()` - Update Safe configuration
- `approveQueuedTransaction()` - Approve high-risk TX
- `rejectQueuedTransaction()` - Reject TX
- `executeQueuedTransaction()` - Execute after approvals
- `addToWhitelist()` - Add trusted address
- `removeFromWhitelist()` - Remove from whitelist
- `addToBlacklist()` - Block address
- `removeFromBlacklist()` - Unblock address

---

## 🔑 Profile: SESSION KEY USER

ERC-4337 Account Abstraction with session keys for gasless transactions.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      SESSION KEY MANAGEMENT SITEMAP                              │
│                      Route: /session-keys                                        │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  SESSION KEYS   │
                              │Route:/session-keys│
                              └────────┬────────┘
                                       │
     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
     │                 │               │               │                 │
     ▼                 ▼               ▼               ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  REGISTER   │  │   CREATE    │  │   ACTIVE    │  │   HISTORY   │  │  SETTINGS   │
│  ACCOUNT    │  │   SESSION   │  │   KEYS      │  │   (Tab 3)   │  │   (Tab 4)   │
│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │             │  │             │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘
       │                │               │
       ▼                ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       REGISTER ACCOUNT TAB                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    REGISTER SMART ACCOUNT                                  │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Smart Account Address: [________________________________________]         │ │
│  │  (Biconomy/Safe/Other ERC-4337 compatible account)                        │ │
│  │                                                                             │ │
│  │  Daily Spending Limit: [________] ETH                                      │ │
│  │  Risk Threshold:       [________] (0-100)                                  │ │
│  │                                                                             │ │
│  │  ✅ Enable Gasless Transactions (via Paymaster)                           │ │
│  │  ✅ Enable Session Keys                                                    │ │
│  │                                                                             │ │
│  │                    [🔐 Register Account with AMTTP]                        │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       CREATE SESSION KEY TAB                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    CREATE NEW SESSION KEY                                  │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │  Session Key Address: [________________________________________]           │ │
│  │  (The address that will be authorized to act on your behalf)              │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  VALIDITY PERIOD                                                     │  │ │
│  │  │  ○ 1 Hour   ○ 24 Hours   ○ 7 Days   ○ Custom: [____] days           │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  SPENDING LIMIT                                                      │  │ │
│  │  │  Maximum per transaction: [____] ETH                                 │  │ │
│  │  │  Maximum total spend:     [____] ETH                                 │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │  ALLOWED CONTRACTS (Optional - leave empty for all)                  │  │ │
│  │  │  + [0x742d...] AMTTPCore                                  [Remove]   │  │ │
│  │  │  + [________________________________________]              [Add]      │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │                    [🔑 Create Session Key]                                 │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                       ACTIVE SESSION KEYS TAB                                    │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    YOUR ACTIVE SESSION KEYS                                │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ 🔑 Session Key: 0x742d...                                            │  │ │
│  │  │                                                                       │  │ │
│  │  │ Created: Jan 4, 2026 10:00        Expires: Jan 5, 2026 10:00         │  │ │
│  │  │ Spending Limit: 1.0 ETH           Used: 0.25 ETH (25%)               │  │ │
│  │  │ ████████░░░░░░░░░░░░░░░░░░░░░░░░                                     │  │ │
│  │  │                                                                       │  │ │
│  │  │ Status: 🟢 Active                                                     │  │ │
│  │  │                                                                       │  │ │
│  │  │ [🔍 View Usage] [🔴 Revoke Key]                                       │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐  │ │
│  │  │ 🔑 Session Key: 0x8ba1...                                            │  │ │
│  │  │                                                                       │  │ │
│  │  │ Created: Jan 1, 2026              Expires: Jan 8, 2026               │  │ │
│  │  │ Spending Limit: 5.0 ETH           Used: 4.8 ETH (96%) ⚠️            │  │ │
│  │  │ ██████████████████████████████░░                                     │  │ │
│  │  │                                                                       │  │ │
│  │  │ Status: 🟡 Near Limit                                                 │  │ │
│  │  │                                                                       │  │ │
│  │  │ [🔍 View Usage] [🔴 Revoke Key]                                       │  │ │
│  │  └──────────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `registerAccount()` - Register smart account with AMTTP
- `updateAccountConfig()` - Update account settings
- `createSessionKey()` - Create session key with permissions
- `revokeSessionKey()` - Revoke active session key

---

## ✅ Profile: APPROVER

Dedicated portal for approving high-risk transactions.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        APPROVER PORTAL SITEMAP                                   │
│                        Route: /approver                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │ APPROVER PORTAL │
                              │ Route:/approver │
                              └────────┬────────┘
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────┐
     │                                 │                                 │
     ▼                                 ▼                                 ▼
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│    PENDING      │         │    APPROVED     │         │    REJECTED     │
│   APPROVALS     │         │     HISTORY     │         │     HISTORY     │
│    (Tab 0)      │         │     (Tab 1)     │         │     (Tab 2)     │
└────────┬────────┘         └─────────────────┘         └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       PENDING APPROVALS                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  🔔 You have 5 pending approvals                                                │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ SWAP #abc123                                       Priority: 🔴 HIGH       │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │                                                                             │ │
│  │ Type: ETH → ETH Swap                              Risk Score: 82/100       │ │
│  │ From: 0x742d35Cc6634C0532925a3b844Bc454e4438f44e                           │ │
│  │ To:   0x8ba1f109551bD432803012645Ac136ddd64DBA72                           │ │
│  │ Amount: 15.5 ETH (~$37,200)                                                │ │
│  │                                                                             │ │
│  │ ┌──────────────────────────────────────────────────────────────────────┐   │ │
│  │ │ RISK BREAKDOWN                                                       │   │ │
│  │ │ ⚠️ High-value transaction                              +25 points    │   │ │
│  │ │ ⚠️ Recipient has low reputation                        +20 points    │   │ │
│  │ │ ⚠️ First transaction with this address                 +15 points    │   │ │
│  │ │ ⚠️ Amount exceeds user's typical pattern               +12 points    │   │ │
│  │ │ ✅ Sender is KYC verified                               -10 points    │   │ │
│  │ └──────────────────────────────────────────────────────────────────────┘   │ │
│  │                                                                             │ │
│  │ Created: Jan 4, 2026 15:30          Timeout: 23 hours remaining            │ │
│  │                                                                             │ │
│  │ ┌──────────────────────────────┐  ┌──────────────────────────────────────┐ │ │
│  │ │     [✓ APPROVE SWAP]        │  │ [✗ REJECT SWAP]                      │ │ │
│  │ │                              │  │                                      │ │ │
│  │ │ Requires: 1 of 3 approvers  │  │ Reason: [_________________________] │ │ │
│  │ └──────────────────────────────┘  └──────────────────────────────────────┘ │ │
│  │                                                                             │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │ SWAP #def456                                       Priority: 🟡 MEDIUM     │ │
│  ├────────────────────────────────────────────────────────────────────────────┤ │
│  │ Type: NFT → ETH Swap                              Risk Score: 65/100       │ │
│  │ From: 0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B                           │ │
│  │ NFT: BAYC #1234                                   ETH: 50.0                │ │
│  │                                                                             │ │
│  │ [✓ APPROVE] [✗ REJECT] [View Full Details]                                │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Smart Contract Functions Covered:**
- `approveSwap()` - (AMTTPCore) Approve high-risk swap
- `rejectSwap()` - (AMTTPCore) Reject swap with reason
- `approveSwap()` - (AMTTPNFT) Approve high-risk NFT swap

---

## 📋 Updated Route Summary

| Route | Page | Access | Description | Status |
|-------|------|--------|-------------|--------|
| `/` | HomePage | All | Landing, wallet connection, dashboard | ✅ EXISTS |
| `/wallet` | WalletPage | All | Wallet management, balances | ✅ EXISTS |
| `/transfer` | TransferPage | All | ETH/ERC20 transfers | ✅ EXISTS |
| `/history` | HistoryPage | All | Transaction history | ✅ EXISTS |
| `/admin` | AdminPage | Admin | Dashboard, Analytics, Policies | ✅ EXISTS |
| `/settings` | SettingsPage | All | User preferences | ✅ EXISTS |
| `/nft-swap` | NFTSwapPage | All | NFT swap functionality | 🆕 NEW |
| `/disputes` | DisputeCenterPage | All | Dispute resolution | 🆕 NEW |
| `/dispute/:id` | DisputeDetailPage | All | Dispute details | 🆕 NEW |
| `/cross-chain` | CrossChainPage | All | Cross-chain transfers | 🆕 NEW |
| `/safe` | SafeManagementPage | All | Gnosis Safe integration | 🆕 NEW |
| `/session-keys` | SessionKeyPage | All | Session key management | 🆕 NEW |
| `/approver` | ApproverPortalPage | Approver | High-risk TX approval | 🆕 NEW |
| `/compliance` | CompliancePage | Compliance | Account freeze, trusted users | 🆕 NEW |

---

## 📊 Coverage Summary

| Contract | Functions | Current Coverage | With New Pages |
|----------|-----------|------------------|----------------|
| AMTTPCore.sol | 10 | 40% | 100% |
| AMTTPNFT.sol | 12 | 0% | 100% |
| AMTTPDisputeResolver.sol | 5 | 0% | 100% |
| AMTTPCrossChain.sol | 8 | 0% | 100% |
| AMTTPSafeModule.sol | 11 | 0% | 100% |
| AMTTPBiconomyModule.sol | 6 | 0% | 100% |
| AMTTPPolicyEngine.sol | 14 | 30% | 100% |
| **TOTAL** | **66** | **~15%** | **100%** |

---

*Generated: January 5, 2026*
*AMTTP Flutter App v2.0 - Complete UI Coverage*
