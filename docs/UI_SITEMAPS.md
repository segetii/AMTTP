# AMTTP UI Sitemaps by User Profile# AMTTP UI Sitemaps by User Profile



This document provides visual sitemaps for each user profile in the AMTTP (Advanced Money Transfer Trust Protocol) application.This document provides visual sitemaps for each user profile in the AMTTP (Advanced Money Transfer Protocol) application.



**Last Updated:** January 2026  ---

**Version:** 2.0

## 📊 Application Overview

---

```

## 📊 Application Architecture Overview┌─────────────────────────────────────────────────────────────────────────────────┐

│                              AMTTP PLATFORM                                      │

```├─────────────────────────────────────────────────────────────────────────────────┤

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐│                                                                                  │

│                                    AMTTP PLATFORM                                                ││   ┌───────────────┐    ┌───────────────┐    ┌───────────────┐                   │

├─────────────────────────────────────────────────────────────────────────────────────────────────┤│   │   END USER    │    │    ADMIN      │    │  COMPLIANCE   │                   │

│                                                                                                  ││   │   (Wallet)    │    │  (Dashboard)  │    │   (Officer)   │                   │

│   ┌────────────────┐     ┌────────────────┐     ┌────────────────┐     ┌────────────────┐       ││   └───────┬───────┘    └───────┬───────┘    └───────┬───────┘                   │

│   │   END USER     │     │     ADMIN      │     │  COMPLIANCE    │     │   APPROVER     │       ││           │                    │                    │                            │

│   │   (Wallet)     │     │  (Dashboard)   │     │   (Officer)    │     │   (Arbiter)    │       ││           ▼                    ▼                    ▼                            │

│   └───────┬────────┘     └───────┬────────┘     └───────┬────────┘     └───────┬────────┘       ││   ┌───────────────────────────────────────────────────────────────┐             │

│           │                      │                      │                      │                ││   │                    SHARED INFRASTRUCTURE                       │             │

│           ▼                      ▼                      ▼                      ▼                ││   │  • Web3 Wallet Connection  • AI Risk Assessment               │             │

│   ┌─────────────────────────────────────────────────────────────────────────────────────┐       ││   │  • Blockchain Integration  • Real-time Monitoring             │             │

│   │                           SHARED INFRASTRUCTURE                                      │       ││   └───────────────────────────────────────────────────────────────┘             │

│   │                                                                                      │       ││                                                                                  │

│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │       │└─────────────────────────────────────────────────────────────────────────────────┘

│   │  │   Web3      │  │   ML Risk   │  │  Compliance │  │   Smart     │               │       │```

│   │  │   Wallet    │  │   Engine    │  │   Services  │  │  Contracts  │               │       │

│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘               │       │---

│   │                                                                                      │       │

│   │  • MetaMask/WalletConnect       • Stacked Ensemble (ROC-AUC ~0.94)                 │       │## 👤 Profile 1: END USER (Standard User)

│   │  • Session Keys (ERC-4337)      • GraphSAGE + LGBM + XGBoost                       │       │

│   │  • Gnosis Safe Module           • Real-time Risk Scoring                           │       │The standard user profile for conducting secure transfers and managing their wallet.

│   │  • zkNAF Privacy Proofs         • 7 AML Pattern Detection                          │       │

│   │                                                                                      │       │```

│   └─────────────────────────────────────────────────────────────────────────────────────┘       │┌─────────────────────────────────────────────────────────────────────────────────┐

│                                                                                                  ││                           END USER SITEMAP                                       │

└─────────────────────────────────────────────────────────────────────────────────────────────────┘└─────────────────────────────────────────────────────────────────────────────────┘

```

                              ┌─────────────────┐

---                              │   HOME PAGE     │

                              │   (Welcome)     │

## 🔐 Authentication Flow                              │   Route: /      │

                              └────────┬────────┘

```                                       │

┌─────────────────────────────────────────────────────────────────────────────────┐            ┌──────────────────────────┼──────────────────────────┐

│                           AUTHENTICATION ROUTES                                  │            │                          │                          │

└─────────────────────────────────────────────────────────────────────────────────┘            ▼                          ▼                          ▼

   ┌────────────────┐        ┌────────────────┐        ┌────────────────┐

                              ┌─────────────────┐   │  NOT CONNECTED │        │   CONNECTED    │        │  QUICK LINKS   │

                              │    SIGN IN      │   │                │        │                │        │                │

                              │  Route: /sign-in│   │ • Welcome View │        │ • Main Content │        │ • Transfer     │

                              └────────┬────────┘   │ • Feature Cards│        │ • Bottom Nav   │        │ • History      │

                                       │   │ • Connect CTA  │        │ • Tab Views    │        │ • Wallet       │

            ┌──────────────────────────┼──────────────────────────┐   │ • Trust Badges │        │                │        │ • Admin        │

            │                          │                          │   └────────────────┘        └───────┬────────┘        └────────────────┘

            ▼                          ▼                          ▼                                     │

   ┌────────────────┐        ┌────────────────┐        ┌────────────────┐       ┌─────────────────────────────┼─────────────────────────────┐

   │    REGISTER    │        │ SELECT PROFILE │        │  WALLET AUTH   │       │                             │                             │

   │ Route: /register│       │Route: /select- │        │                │       ▼                             ▼                             ▼

   │                │        │      profile   │        │ • MetaMask     │┌──────────────┐           ┌──────────────┐           ┌──────────────┐

   │ • Email/Pass   │        │                │        │ • WalletConnect││     SEND     │           │   HISTORY    │           │  ANALYTICS   │

   │ • Wallet Link  │        │ • End User     │        │ • Coinbase     ││   (Tab 0)    │           │   (Tab 1)    │           │   (Tab 2)    │

   │ • KYC Upload   │        │ • Admin        │        │                │├──────────────┤           ├──────────────┤           ├──────────────┤

   └────────────────┘        │ • Compliance   │        └────────────────┘│              │           │              │           │              │

                             └────────┬────────┘│ SecureTransfer           │ • TX List    │           │ • Risk Vis   │

                                      ││ Widget:      │           │ • Risk Scores│           │ • DQN Metrics│

            ┌─────────────────────────┼─────────────────────────┐│              │           │ • Filters    │           │ • Charts     │

            │                         │                         ││ • Recipient  │           │ • TX Details │           │ • Score Hist │

            ▼                         ▼                         ▼│ • Amount     │           │              │           │              │

     ┌────────────┐           ┌────────────┐           ┌────────────┐│ • Risk Check │           └──────────────┘           └──────────────┘

     │    HOME    │           │   ADMIN    │           │ COMPLIANCE ││ • MEV Protect│                  │

     │  Route: /  │           │Route: /admin│          │Route: /    ││ • Confirm    │                  ▼

     │  (End User)│           │            │           │ compliance ││              │           ┌──────────────┐

     └────────────┘           └────────────┘           └────────────┘└──────────────┘           │  TX DETAIL   │

```       │                   │   (Modal)    │

       ▼                   ├──────────────┤

---┌──────────────┐           │ • TX ID      │

│ TX RESULT    │           │ • Addresses  │

## 👤 Profile 1: END USER (Standard User)│   (Modal)    │           │ • Amount     │

├──────────────┤           │ • Risk Score │

The standard user profile for conducting secure transfers and managing their wallet.│ • Success/   │           │ • Status     │

│   Failure    │           │ • Timestamp  │

```│ • TX Hash    │           └──────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐│ • Details    │

│                           END USER SITEMAP                                       │└──────────────┘

└─────────────────────────────────────────────────────────────────────────────────┘

       │

                              ┌─────────────────┐       ▼

                              │   HOME PAGE     │┌──────────────┐

                              │   Route: /      ││  SECURITY    │

                              └────────┬────────┘│   (Tab 3)    │

                                       │├──────────────┤

            ┌──────────────────────────┼──────────────────────────┐│              │

            │                          │                          ││ • Wallet Info│

            ▼                          ▼                          ▼│ • Security   │

   ┌────────────────┐        ┌────────────────┐        ┌────────────────┐│   Settings   │

   │  NOT CONNECTED │        │   CONNECTED    │        │  SIDEBAR NAV   ││ • Risk Prefs │

   │                │        │                │        │                ││              │

   │ • Welcome View │        │ • Main Content │        │ • Transfer     │└──────────────┘

   │ • Feature Cards│        │ • Bottom Nav   │        │ • History      │```

   │ • Connect CTA  │        │ • 4 Tab Views  │        │ • NFT Swap     │

   │ • Trust Badges │        │                │        │ • Cross-Chain  │### End User Navigation Flow

   │ • Features     │        │                │        │ • Disputes     │

   │   Carousel     │        │                │        │ • Safe         │```

   └────────────────┘        └───────┬────────┘        │ • Session Keys │HOME (/)

                                     │                 │ • zkNAF        │├── 📱 Bottom Navigation Bar (when connected)

                                     │                 │ • Settings     ││   ├── Send (Tab 0)      → SecureTransferWidget

       ┌─────────────────────────────┼─────────────────┘│   ├── History (Tab 1)   → Transaction History List

       │                             │                             │   ├── Analytics (Tab 2) → Risk Visualizer + DQN Metrics  

       ▼                             ▼                             │   └── Security (Tab 3)  → Security & Wallet Settings

┌──────────────┐           ┌──────────────┐           ┌──────────────┐│

│     SEND     │           │   HISTORY    │           │  ANALYTICS   │├── 🔗 Quick Links (sidebar)

│   (Tab 0)    │           │   (Tab 1)    │           │   (Tab 2)    ││   ├── /transfer → Dedicated Transfer Page

├──────────────┤           ├──────────────┤           ├──────────────┤│   ├── /history  → Full History Page

│              │           │              │           │              ││   ├── /wallet   → Wallet Management Page

│SecureTransfer│           │ • TX List    │           │ • Risk       ││   └── /admin    → Admin Dashboard (if authorized)

│Widget:       │           │ • Risk Scores│           │   Visualizer ││

│              │           │ • Filters    │           │ • ML Metrics │└── ⚙️ Header Actions

│ • Recipient  │           │ • TX Details │           │   (ROC-AUC,  │    └── /settings → Settings Page

│ • Amount     │           │ • Status     │           │    PR-AUC,   │```

│ • Analyze    │           │   Badges     │           │    F1)       │

│   Risk ⭐    │           │              │           │ • Charts     │---

│ • Policy     │           └──────────────┘           │ • History    │

│   Check      │                  │                   │              │## 👨‍💼 Profile 2: ADMIN USER

│ • Labels     │                  ▼                   └──────────────┘

│ • Confirm TX │           ┌──────────────┐                  │The administrator profile with full system oversight and management capabilities.

│              │           │  TX DETAIL   │                  │

└──────────────┘           │   (Modal)    │           ┌──────────────┐```

       │                   ├──────────────┤           │  SECURITY    │┌─────────────────────────────────────────────────────────────────────────────────┐

       ▼                   │ • TX ID      │           │   (Tab 3)    ││                           ADMIN SITEMAP                                          │

┌──────────────┐           │ • Addresses  │           ├──────────────┤└─────────────────────────────────────────────────────────────────────────────────┘

│ TX RESULT    │           │ • Amount     │           │              │

│   (Modal)    │           │ • Risk Score │           │ • Wallet     │                              ┌─────────────────┐

├──────────────┤           │ • Status     │           │   Info       │                              │   ADMIN PAGE    │

│ • Success/   │           │ • Labels     │           │ • Risk Prefs │                              │   Route: /admin │

│   Failure    │           │ • Timestamp  │           │ • 2FA Setup  │                              └────────┬────────┘

│ • TX Hash    │           └──────────────┘           │              │                                       │

│ • Explorer   │                                      └──────────────┘     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐

│   Link       │     │                 │               │               │                 │

└──────────────┘     ▼                 ▼               ▼               ▼                 ▼

```┌─────────┐      ┌─────────┐     ┌─────────┐    ┌─────────┐      ┌─────────┐

│OVERVIEW │      │   DQN   │     │  TRANS  │    │POLICIES │      │ WEBHOOKS│

### End User Additional Pages│ (Tab 0) │      │ANALYTICS│     │ (Tab 2) │    │ (Tab 3) │      │(Tab 3.2)│

│         │      │ (Tab 1) │     │         │    │         │      │         │

```└────┬────┘      └────┬────┘     └────┬────┘    └────┬────┘      └─────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐     │                │               │               │

│                       END USER - ADDITIONAL FEATURES                             │     ▼                ▼               ▼               ▼

└─────────────────────────────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────────────────────┐

│                           OVERVIEW TAB                                   │

┌────────────────┐      ┌────────────────┐      ┌────────────────┐├─────────────────────────────────────────────────────────────────────────┤

│   NFT SWAP     │      │  CROSS-CHAIN   │      │    DISPUTES    ││                                                                          │

│Route: /nft-swap│      │Route: /cross-  │      │Route: /disputes││  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │

├────────────────┤      │      chain     │      ├────────────────┤│  │System Status │  │  DQN Model   │  │ Transactions │  │Fraud Blocked │ │

│                │      ├────────────────┤      │                ││  │  (Health)    │  │   Status     │  │    Today     │  │    Count     │ │

│ AMTTPNFT.sol   │      │AMTTPCrossChain │      │AMTTPDispute    ││  │ • Uptime %   │  │ • Version    │  │ • Count      │  │ • Fraud Rate │ │

│                │      │     .sol       │      │ Resolver.sol   ││  │ • Operational│  │ • Active     │  │ • Change %   │  │ • Blocked #  │ │

│ • Create Swap  │      │                │      │                ││  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │

│ • List My NFTs │      │ • Bridge ETH   │      │ • Open Cases   ││                                                                          │

│ • Active Swaps │      │ • Chain Select │      │ • My Disputes  ││  ┌──────────────┐  ┌──────────────┐                                     │

│ • Claim NFT    │      │ • Fee Preview  │      │ • Submit Claim ││  │ Pending EDD  │  │   Alerts     │                                     │

│ • Escrow View  │      │ • History      │      │ • Evidence     ││  │   Cases      │  │ Unresolved   │                                     │

│                │      │                │      │                ││  │ • Count      │  │ • Count      │                                     │

└────────────────┘      └────────────────┘      └───────┬────────┘│  └──────────────┘  └──────────────┘                                     │

                                                        ││                                                                          │

                                                        ▼│  ┌────────────────────────────────────────────────────────────────────┐ │

                                                ┌────────────────┐│  │              REAL-TIME TRANSACTION FEED                            │ │

                                                │DISPUTE DETAIL  ││  │  • Live TX Stream  • Risk Indicators  • Status Updates             │ │

                                                │Route: /dispute ││  └────────────────────────────────────────────────────────────────────┘ │

                                                │       /:id     ││                                                                          │

                                                ├────────────────┤│  ┌────────────────────────────────────────────────────────────────────┐ │

                                                │ • Case Info    ││  │              RISK DISTRIBUTION CHART (Pie)                         │ │

                                                │ • Evidence     ││  │  • Low Risk %  • Medium Risk %  • High Risk %  • Blocked %         │ │

                                                │ • Timeline     ││  └────────────────────────────────────────────────────────────────────┘ │

                                                │ • Submit Appeal││                                                                          │

                                                │ • Kleros Vote  │└─────────────────────────────────────────────────────────────────────────┘

                                                └────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐

┌────────────────┐      ┌────────────────┐      ┌────────────────┐│                        DQN ANALYTICS TAB                                 │

│     SAFE       │      │  SESSION KEYS  │      │     zkNAF      │├─────────────────────────────────────────────────────────────────────────┤

│  Route: /safe  │      │Route: /session-│      │ Route: /zknaf  ││                                                                          │

├────────────────┤      │      keys      │      ├────────────────┤│  ┌───────────────────────────────────────────────────────────────────┐  │

│                │      ├────────────────┤      │                ││  │                    MODEL PERFORMANCE METRICS                       │  │

│AMTTPSafeModule │      │AMTTPBiconomy   │      │AMTTPCoreZkNAF  ││  │   ┌──────────┐    ┌──────────┐    ┌──────────┐                    │  │

│     .sol       │      │   Module.sol   │      │     .sol       ││  │   │ F1 Score │    │Precision │    │  Recall  │                    │  │

│                │      │                │      │                ││  │   │  0.669   │    │  0.723   │    │  0.625   │                    │  │

│ • Create Safe  │      │ • Create Key   │      │ • Generate     ││  │   │  66.9%   │    │  72.3%   │    │  62.5%   │                    │  │

│ • Add Owners   │      │ • Key Limits   │      │   Proof        ││  │   └──────────┘    └──────────┘    └──────────┘                    │  │

│ • Set Policy   │      │ • Expiration   │      │ • Verify KYC   ││  └───────────────────────────────────────────────────────────────────┘  │

│ • Queue TX     │      │ • Active Keys  │      │ • Privacy Mode ││                                                                          │

│ • Execute TX   │      │ • Revoke Key   │      │ • Attestations ││  ┌───────────────────────────────────────────────────────────────────┐  │

│                │      │                │      │                ││  │                 FEATURE IMPORTANCE (Bar Chart)                     │  │

└────────────────┘      └────────────────┘      └────────────────┘│  │   Amount ████████████████████ 0.85                                │  │

│  │   Frequency ██████████████ 0.72                                   │  │

┌────────────────┐      ┌────────────────┐│  │   Geographic █████████████ 0.68                                   │  │

│    WALLET      │      │   SETTINGS     ││  │   Time ██████████ 0.54                                            │  │

│Route: /wallet  │      │Route: /settings││  │   Account Age █████████ 0.49                                      │  │

├────────────────┤      ├────────────────┤│  │   Velocity ████████ 0.43                                          │  │

│                │      │                ││  │   Cross-border ███████ 0.38                                       │  │

│Interactive     │      │ • Theme        ││  │   Deviation ██████ 0.31                                           │  │

│Wallet Widget   │      │ • Notifications││  │   Reputation █████ 0.27                                           │  │

│                │      │ • Language     ││  └───────────────────────────────────────────────────────────────────┘  │

│ • Balance      │      │ • Risk Prefs   ││                                                                          │

│ • Addresses    │      │ • API Keys     ││  ┌───────────────────────────────────────────────────────────────────┐  │

│ • Token List   │      │ • Export Data  ││  │                 TRAINING DATASET ANALYSIS                          │  │

│ • TX History   │      │                ││  │   • Total Transactions: 28,457                                    │  │

│                │      │                ││  │   • Fraud Cases: 1,842 (6.5%)                                     │  │

└────────────────┘      └────────────────┘│  │   • Training Time: 2.3 hours                                      │  │

```│  │   • Model Size: 15.2 MB                                           │  │

│  │   • Inference Time: <100ms                                        │  │

### End User Navigation Flow│  └───────────────────────────────────────────────────────────────────┘  │

│                                                                          │

```│  ┌───────────────────────────────────────────────────────────────────┐  │

HOME (/)│  │              LIVE PERFORMANCE MONITORING (Line Chart)              │  │

├── 📱 Bottom Navigation Bar (when connected)│  │              Accuracy over last 24 hours                           │  │

│   ├── Send (Tab 0)      → SecureTransferWidget with ML Risk Analysis│  └───────────────────────────────────────────────────────────────────┘  │

│   ├── History (Tab 1)   → Transaction History with Risk Scores│                                                                          │

│   ├── Analytics (Tab 2) → Risk Visualizer + Model Metrics  └─────────────────────────────────────────────────────────────────────────┘

│   └── Security (Tab 3)  → Wallet & Security Settings

│┌─────────────────────────────────────────────────────────────────────────┐

├── 📂 Sidebar Navigation│                        TRANSACTIONS TAB                                  │

│   ├── /transfer     → Dedicated Transfer Page├─────────────────────────────────────────────────────────────────────────┤

│   ├── /history      → Full History Page│                                                                          │

│   ├── /wallet       → Wallet Management Page│  ┌─────────────────────────────────────────────────────────────────┐    │

│   ├── /nft-swap     → NFT Atomic Swaps (AMTTPNFT.sol)│  │  Filter: [All] [High Risk] [Blocked]    Showing X transactions  │    │

│   ├── /cross-chain  → Cross-Chain Bridge (LayerZero)│  └─────────────────────────────────────────────────────────────────┘    │

│   ├── /disputes     → Dispute Center (Kleros)│                                                                          │

│   ├── /safe         → Gnosis Safe Management│  ┌─────────────────────────────────────────────────────────────────┐    │

│   ├── /session-keys → ERC-4337 Session Keys│  │                    TRANSACTION LIST                              │    │

│   ├── /zknaf        → Zero-Knowledge Proofs│  │  ┌───────────────────────────────────────────────────────────┐  │    │

│   └── /settings     → Application Settings│  │  │ 🟢 0.15 ETH  From: 0x742d...  To: 0x8ba1...  APPROVED     │  │    │

││  │  │ 🟡 0.25 ETH  From: 0x8ba1...  To: 0x742d...  ESCROW       │  │    │

└── ⚙️ Header Actions│  │  │ 🔴 1.50 ETH  From: 0x742d...  To: 0xAb58...  BLOCKED      │  │    │

    └── /settings → Settings Page│  │  │ 🟢 0.50 ETH  From: 0xC02a...  To: 0x742d...  APPROVED     │  │    │

```│  │  └───────────────────────────────────────────────────────────┘  │    │

│  └─────────────────────────────────────────────────────────────────┘    │

---│                                                                          │

│  ┌─────────────────────────────────────────────────────────────────┐    │

## 👨‍💼 Profile 2: ADMIN USER│  │              TRANSACTION DETAIL MODAL (on tap)                   │    │

│  │  • Transaction ID    • Amount       • Risk Score                 │    │

The administrator profile with full system oversight and management capabilities.│  │  • From Address      • To Address   • Status                     │    │

│  │  • Timestamp         • Actions: [APPROVE] [REJECT]               │    │

```│  └─────────────────────────────────────────────────────────────────┘    │

┌─────────────────────────────────────────────────────────────────────────────────┐│                                                                          │

│                           ADMIN SITEMAP                                          │└─────────────────────────────────────────────────────────────────────────┘

└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐

                              ┌─────────────────┐│                        POLICIES TAB                                      │

                              │   ADMIN PAGE    │├─────────────────────────────────────────────────────────────────────────┤

                              │   Route: /admin ││                                                                          │

                              └────────┬────────┘│  ┌───────────────────────────────────────────────────────────────────┐  │

                                       ││  │                     ACTIVE POLICIES                                │  │

     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐│  │  ✓ AML Screening      | Anti-money laundering rules    | AML     │  │

     │                 │               │               │                 ││  │  ✓ Sanctions Check    | OFAC/SDN list verification     | OFAC    │  │

     ▼                 ▼               ▼               ▼                 ▼│  │  ✓ Velocity Limits    | Transaction frequency caps     | LIMITS  │  │

┌─────────┐      ┌─────────┐     ┌─────────┐    ┌─────────┐      ┌─────────┐│  │  ✓ Geographic Rules   | Country-based restrictions     | GEO     │  │

│OVERVIEW │      │   ML    │     │  TRANS  │    │POLICIES │      │DETECTION││  └───────────────────────────────────────────────────────────────────┘  │

│ (Tab 0) │      │ANALYTICS│     │ (Tab 2) │    │ (Tab 3) │      │ STUDIO  ││                                                                          │

│         │      │ (Tab 1) │     │         │    │         │      │ (Link)  ││  ┌───────────────────────────────────────────────────────────────────┐  │

└────┬────┘      └────┬────┘     └────┬────┘    └────┬────┘      └────┬────┘│  │                    RISK THRESHOLDS                                 │  │

     │                │               │               │                ││  │  Low Risk Threshold:    ▓▓▓▓▓░░░░░░░░░░░░░░░  25%                │  │

     ▼                ▼               ▼               ▼                ▼│  │  Medium Risk Threshold: ▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  50%                │  │

┌─────────────────────────────────────────────────────────────────────────────┐│  │  High Risk Threshold:   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░  75%                │  │

│                           OVERVIEW TAB                                       ││  └───────────────────────────────────────────────────────────────────┘  │

│                                                                              ││                                                                          │

│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             ││  ┌───────────────────────────────────────────────────────────────────┐  │

│  │  System Health  │  │   ML Model      │  │  Risk Dist.     │             ││  │                   TRANSACTION LIMITS                               │  │

│  │  • Uptime       │  │  • Version      │  │  • CRITICAL     │             ││  │  Daily Limit:        $50,000                                      │  │

│  │  • Services     │  │  • ROC-AUC 0.94 │  │  • HIGH         │             ││  │  Transaction Limit:  $10,000                                      │  │

│  │  • Alerts       │  │  • PR-AUC 0.87  │  │  • MEDIUM       │             ││  │  EDD Threshold:      $15,000                                      │  │

│  │                 │  │  • F1 0.87      │  │  • LOW          │             ││  └───────────────────────────────────────────────────────────────────┘  │

│  └─────────────────┘  └─────────────────┘  └─────────────────┘             ││                                                                          │

│                                                                              ││  ┌───────────────────────────────────────────────────────────────────┐  │

│  ┌─────────────────────────────────────────────────────────────────────────┐││  │                   REGISTERED WEBHOOKS                              │  │

│  │                    REAL-TIME TRANSACTION FEED                           │││  │  • High Risk Alert    → https://api.example.com/alerts           │  │

│  │  • Live TX stream with risk scores                                      │││  │  • Blocked TX         → https://api.example.com/blocked          │  │

│  │  • Flagged transactions highlighted                                     │││  │  • Dispute Created    → https://api.example.com/disputes         │  │

│  │  • Click to expand details                                              │││  └───────────────────────────────────────────────────────────────────┘  │

│  └─────────────────────────────────────────────────────────────────────────┘││                                                                          │

└─────────────────────────────────────────────────────────────────────────────┘└─────────────────────────────────────────────────────────────────────────┘

```

┌─────────────────────────────────────────────────────────────────────────────┐

│                           ML ANALYTICS TAB                                   │### Admin Navigation Flow

│                                                                              │

│  ┌──────────────────────────────────────────────────────────┐              │```

│  │                  MODEL PERFORMANCE                        │              │ADMIN (/admin)

│  │                                                           │              │├── 📊 Tab Navigation

│  │  Stacked Ensemble: GraphSAGE + LGBM + XGBoost            │              ││   ├── Overview (Tab 0)

│  │  + Linear Meta-Learner                                    │              ││   │   ├── System Health Cards

│  │                                                           │              ││   │   ├── Compliance Status (EDD, Alerts)

│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐      │              ││   │   ├── Real-time TX Feed

│  │  │  ROC-AUC    │  │   PR-AUC    │  │     F1      │      │              ││   │   └── Risk Distribution Chart

│  │  │    0.94     │  │    0.87     │  │    0.87     │      │              ││   │

│  │  └─────────────┘  └─────────────┘  └─────────────┘      │              ││   ├── DQN Analytics (Tab 1)

│  └──────────────────────────────────────────────────────────┘              ││   │   ├── Performance Metrics (F1, Precision, Recall)

│                                                                              ││   │   ├── Feature Importance Chart

│  ┌──────────────────────────────────────────────────────────┐              ││   │   ├── Training Dataset Stats

│  │                  PATTERN DETECTION                        │              ││   │   └── Live Performance Graph

│  │                                                           │              ││   │

│  │  7 AML Patterns Detected:                                │              ││   ├── Transactions (Tab 2)

│  │  • SMURFING    • LAYERING   • FAN-OUT   • FAN-IN        │              ││   │   ├── Filter Controls

│  │  • PEELING     • STRUCTURING • VELOCITY                  │              ││   │   ├── Transaction List

│  │                                                           │              ││   │   └── Detail Modal → Approve/Reject Actions

│  └──────────────────────────────────────────────────────────┘              ││   │

│                                                                              ││   └── Policies (Tab 3)

│  ┌──────────────────────────────────────────────────────────┐              ││       ├── Active Policies List

│  │                  RISK SCORE HISTOGRAM                     │              ││       ├── Risk Threshold Sliders

│  │                                                           │              ││       ├── Transaction Limits

│  │  [Chart: Distribution of risk scores across addresses]   │              ││       └── Webhook Configuration

│  └──────────────────────────────────────────────────────────┘              ││

└─────────────────────────────────────────────────────────────────────────────┘└── 🔙 Back to Home (/)

```

┌─────────────────────────────────────────────────────────────────────────────┐

│                        TRANSACTIONS TAB                                      │---

│                                                                              │

│  ┌─────────────────────────────────────────────────────────────────────────┐│## 🔍 Profile 3: COMPLIANCE OFFICER

│  │ Filters: [Status ▼] [Risk Level ▼] [Date Range] [Search Address]       ││

│  └─────────────────────────────────────────────────────────────────────────┘│The compliance officer profile focuses on regulatory oversight, EDD reviews, and audit trails.

│                                                                              │

│  ┌─────────────────────────────────────────────────────────────────────────┐│```

│  │ TX Hash    │ From        │ To          │ Amount  │ Risk │ Status       ││┌─────────────────────────────────────────────────────────────────────────────────┐

│  │───────────────────────────────────────────────────────────────────────││││                       COMPLIANCE OFFICER SITEMAP                                 │

│  │ 0xa1b2... │ 0x1234...   │ 0xabcd...   │ 1.5 ETH │ 0.85 │ ⚠️ REVIEW   ││└─────────────────────────────────────────────────────────────────────────────────┘

│  │ 0xc3d4... │ 0x5678...   │ 0xef01...   │ 0.1 ETH │ 0.12 │ ✅ APPROVED  ││

│  │ 0xe5f6... │ 0x9abc...   │ 0x2345...   │ 50 ETH  │ 0.92 │ 🛑 BLOCKED   ││                              ┌─────────────────┐

│  └─────────────────────────────────────────────────────────────────────────┘│                              │  ADMIN PAGE     │

└─────────────────────────────────────────────────────────────────────────────┘                              │  (Compliance    │

                              │   Focus)        │

┌─────────────────────────────────────────────────────────────────────────────┐                              └────────┬────────┘

│                          POLICIES TAB                                        │                                       │

│                                                                              │     ┌─────────────────┬───────────────┴───────────────┬─────────────────┐

│  ┌─────────────────────────────────────────────────────────────────────────┐│     │                 │                               │                 │

│  │ Risk Thresholds        │ Transaction Limits     │ Webhooks              ││     ▼                 ▼                               ▼                 ▼

│  │────────────────────────│────────────────────────│───────────────────────││┌─────────────┐  ┌─────────────┐              ┌─────────────┐  ┌─────────────┐

│  │ CRITICAL: ≥ 0.85       │ Max Single: 100 ETH    │ ✅ Slack #alerts      │││  OVERVIEW   │  │TRANSACTIONS │              │   POLICIES  │  │   REPORTS   │

│  │ HIGH:     ≥ 0.70       │ Daily:      500 ETH    │ ✅ Email ops@         │││ (Compliance)│  │  (Review)   │              │(Management) │  │  (Audit)    │

│  │ MEDIUM:   ≥ 0.50       │ Auto-approve: < 0.30   │ ❌ PagerDuty          ││└──────┬──────┘  └──────┬──────┘              └──────┬──────┘  └──────┬──────┘

│  │ LOW:      ≥ 0.25       │                        │                       ││       │                │                            │                │

│  └─────────────────────────────────────────────────────────────────────────┘│       ▼                ▼                            ▼                ▼

└─────────────────────────────────────────────────────────────────────────────┘┌─────────────────────────────────────────────────────────────────────────────────┐

```│                          COMPLIANCE DASHBOARD                                    │

├─────────────────────────────────────────────────────────────────────────────────┤

### Admin Additional Pages│                                                                                  │

│  ┌────────────────────────────────────────────────────────────────────────────┐ │

```│  │                        EDD CASE MANAGEMENT                                  │ │

┌─────────────────────────────────────────────────────────────────────────────┐│  ├────────────────────────────────────────────────────────────────────────────┤ │

│                       ADMIN - ADDITIONAL FEATURES                            ││  │                                                                             │ │

└─────────────────────────────────────────────────────────────────────────────┘│  │  📋 PENDING EDD CASES                                                       │ │

│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │

┌────────────────────────┐              ┌────────────────────────┐│  │  │ Case #001  | 0x742d...  | $25,000  | High Risk | Awaiting Review   │   │ │

│   DETECTION STUDIO     │              │   APPROVER PORTAL      ││  │  │ Case #002  | 0x8ba1...  | $18,500  | Medium    | Documents Pending │   │ │

│ Route: /detection-     │              │ Route: /approver       ││  │  │ Case #003  | 0xAb58...  | $50,000  | Critical  | Urgent Review     │   │ │

│        studio          │              ├────────────────────────┤│  │  └─────────────────────────────────────────────────────────────────────┘   │ │

├────────────────────────┤              │                        ││  │                                                                             │ │

│                        │              │ AMTTPCore.sol          ││  │  [Review Case] [Request Docs] [Approve] [Escalate] [Reject]                │ │

│ Embeds Next.js         │              │ • approveSwap()        ││  │                                                                             │ │

│ Dashboard (port 3006)  │              │ • rejectSwap()         ││  └────────────────────────────────────────────────────────────────────────────┘ │

│                        │              │                        ││                                                                                  │

│ • SIEM Dashboard       │              │ Features:              ││  ┌────────────────────────────────────────────────────────────────────────────┐ │

│ • FATF Compliance      │              │ • Pending Queue        ││  │                        SANCTIONS SCREENING                                  │ │

│ • Real-time Alerts     │              │ • Risk Details         ││  ├────────────────────────────────────────────────────────────────────────────┤ │

│ • Pattern Visualization│              │ • Approve/Reject       ││  │                                                                             │ │

│ • Custom Queries       │              │ • Add Comments         ││  │  🚫 BLOCKED ADDRESSES (Sanctions List Matches)                             │ │

│                        │              │ • Bulk Actions         ││  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │

└────────────────────────┘              └────────────────────────┘│  │  │ 0xdead... | OFAC SDN List    | Blocked Since: 2026-01-01          │   │ │

```│  │  │ 0xbeef... | OFAC SDN List    | Blocked Since: 2025-12-15          │   │ │

│  │  │ 0xcafe... | EU Sanctions     | Blocked Since: 2025-11-20          │   │ │

### Admin Navigation Flow│  │  └─────────────────────────────────────────────────────────────────────┘   │ │

│  │                                                                             │ │

```│  │  [Add Address] [Remove] [Update Lists] [Export Report]                     │ │

ADMIN (/admin)│  │                                                                             │ │

├── 📊 TabBar Navigation│  └────────────────────────────────────────────────────────────────────────────┘ │

│   ├── Overview (Tab 0)     → System Health + Real-time Feed│                                                                                  │

│   ├── ML Analytics (Tab 1) → Model Performance + Patterns│  ┌────────────────────────────────────────────────────────────────────────────┐ │

│   ├── Transactions (Tab 2) → Full TX List with Filters│  │                        SUSPICIOUS ACTIVITY REPORTS                          │ │

│   └── Policies (Tab 3)     → Risk Thresholds + Webhooks│  ├────────────────────────────────────────────────────────────────────────────┤ │

││  │                                                                             │ │

├── 📂 Sidebar Navigation│  │  📊 SAR QUEUE                                                              │ │

│   ├── /admin            → Admin Dashboard│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │

│   ├── /detection-studio → Next.js SIEM (iframe)│  │  │ SAR-2026-001 | Structuring Detected  | Priority: High   | Draft    │   │ │

│   ├── /approver         → Swap Approval Portal│  │  │ SAR-2026-002 | Unusual Pattern       | Priority: Medium | Review   │   │ │

│   ├── /compliance       → Compliance Tools│  │  └─────────────────────────────────────────────────────────────────────┘   │ │

│   └── /fatf-rules       → FATF Compliance Page│  │                                                                             │ │

││  │  [Create SAR] [Submit to FCA] [Archive]                                    │ │

└── 🔗 External Links│  │                                                                             │ │

    └── Next.js Dashboard → http://localhost:3006│  └────────────────────────────────────────────────────────────────────────────┘ │

```│                                                                                  │

│  ┌────────────────────────────────────────────────────────────────────────────┐ │

---│  │                        AUDIT TRAIL                                          │ │

│  ├────────────────────────────────────────────────────────────────────────────┤ │

## 👮 Profile 3: COMPLIANCE OFFICER│  │                                                                             │ │

│  │  📝 RECENT COMPLIANCE ACTIONS                                              │ │

The compliance officer profile for regulatory monitoring and enforcement.│  │  ┌─────────────────────────────────────────────────────────────────────┐   │ │

│  │  │ 2026-01-04 21:30 | EDD Approved    | Case #001 | Officer: J.Smith │   │ │

```│  │  │ 2026-01-04 20:15 | SAR Submitted   | SAR-001   | Officer: M.Jones │   │ │

┌─────────────────────────────────────────────────────────────────────────────┐│  │  │ 2026-01-04 19:45 | Address Blocked | 0xdead... | System: Auto     │   │ │

│                        COMPLIANCE OFFICER SITEMAP                            ││  │  │ 2026-01-04 18:30 | Policy Updated  | AML v2.1  | Officer: J.Smith │   │ │

└─────────────────────────────────────────────────────────────────────────────┘│  │  └─────────────────────────────────────────────────────────────────────┘   │ │

│  │                                                                             │ │

                              ┌─────────────────┐│  │  [Export Audit Log] [Filter by Date] [Filter by Officer]                   │ │

                              │  COMPLIANCE     ││  │                                                                             │ │

                              │    TOOLS        ││  └────────────────────────────────────────────────────────────────────────────┘ │

                              │Route: /compliance││                                                                                  │

                              └────────┬────────┘└─────────────────────────────────────────────────────────────────────────────────┘

                                       │```

     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐

     │                 │               │               │                 │### Compliance Officer Navigation Flow

     ▼                 ▼               ▼               ▼                 ▼

┌─────────┐      ┌─────────┐     ┌─────────┐    ┌─────────┐      ┌─────────┐```

│ FREEZE/ │      │ TRUSTED │     │   PEP/  │    │   EDD   │      │  FATF   │ADMIN (/admin) - Compliance Focus

│UNFREEZE │      │  USERS  │     │SANCTIONS│    │  QUEUE  │      │  RULES  │├── 📊 Overview Tab (Compliance Metrics)

│ (Tab 0) │      │ (Tab 1) │     │ (Tab 2) │    │ (Tab 3) │      │ (Link)  ││   ├── Pending EDD Cases Counter

└────┬────┘      └────┬────┘     └────┬────┘    └────┬────┘      └────┬────┘│   ├── Unresolved Alerts Counter

     │                │               │               │                ││   ├── Fraud Blocked Statistics

     ▼                ▼               ▼               ▼                ▼│   └── Compliance Status Dashboard

┌─────────────────────────────────────────────────────────────────────────────┐│

│                        FREEZE/UNFREEZE TAB                                   │├── 📋 Transactions Tab (High-Risk Review)

│                                                                              ││   ├── Filter: High Risk / Blocked

│  AMTTPPolicyEngine.sol: freezeAccount() / unfreezeAccount()                 ││   ├── EDD Case Queue

│                                                                              ││   ├── Transaction Review Modal

│  ┌─────────────────────────────────────────────────────────────────────────┐││   │   ├── Full Transaction Details

│  │ Address Input: [0x________________________________] [🔍 Check]          │││   │   ├── Risk Assessment Breakdown

│  └─────────────────────────────────────────────────────────────────────────┘││   │   ├── Customer Information

│                                                                              ││   │   └── Actions: Approve / Reject / Escalate

│  ┌─────────────────────────────────────────────────────────────────────────┐││   └── Bulk Actions

│  │ FROZEN ACCOUNTS                                               [Export] │││

│  │───────────────────────────────────────────────────────────────────────│││├── 📜 Policies Tab (Regulatory Management)

│  │ Address      │ Frozen At    │ Reason         │ By        │ Actions   │││   ├── Active Policy Management

│  │ 0xabcd...   │ Jan 1, 2026  │ OFAC match     │ Automated │ [Unfreeze]│││   ├── Risk Threshold Configuration

│  │ 0x1234...   │ Dec 15, 2025 │ High risk      │ Manual    │ [Unfreeze]│││   ├── Transaction Limit Settings

│  └─────────────────────────────────────────────────────────────────────────┘││   ├── EDD Threshold Configuration

└─────────────────────────────────────────────────────────────────────────────┘│   └── Webhook Notifications Setup

│

┌─────────────────────────────────────────────────────────────────────────────┐└── 📈 Reports (via API/Export)

│                        TRUSTED USERS TAB                                     │    ├── SAR Generation

│                                                                              │    ├── Audit Trail Export

│  AMTTPPolicyEngine.sol: addTrustedUser() / addTrustedCounterparty()         │    ├── Compliance Reports

│                                                                              │    └── Regulatory Filing

│  ┌─────────────────────────────────────────────────────────────────────────┐│```

│  │ Add Trusted:                                                            ││

│  │ [Address] [User ▼] [Reason________________] [+ Add]                    ││---

│  └─────────────────────────────────────────────────────────────────────────┘│

│                                                                              │## 🔧 Shared Pages (All Profiles)

│  ┌─────────────┐ ┌─────────────┐                                           │

│  │ TRUSTED     │ │ TRUSTED     │                                           │```

│  │ USERS       │ │COUNTERPARTY │                                           │┌─────────────────────────────────────────────────────────────────────────────────┐

│  │             │ │             │                                           ││                           SHARED PAGES                                           │

│  │ 12 entries  │ │ 8 entries   │                                           │└─────────────────────────────────────────────────────────────────────────────────┘

│  └─────────────┘ └─────────────┘                                           │

└─────────────────────────────────────────────────────────────────────────────┘┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐

│    WALLET       │     │    SETTINGS     │     │    HISTORY      │

┌─────────────────────────────────────────────────────────────────────────────┐│  Route: /wallet │     │ Route: /settings│     │ Route: /history │

│                        PEP/SANCTIONS TAB                                     │├─────────────────┤     ├─────────────────┤     ├─────────────────┤

│                                                                              ││                 │     │                 │     │                 │

│  Integrated Sanctions Lists: OFAC, EU, UN, HMT                              ││ • Balance Card  │     │ GENERAL         │     │ • TX List       │

│                                                                              ││   - ETH Balance │     │ • Language      │     │ • Risk Scores   │

│  ┌─────────────────────────────────────────────────────────────────────────┐││   - USD Value   │     │ • Theme         │     │ • Status Filter │

│  │ Screen Address: [0x________________________________] [🔍 Screen]       │││   - Connected   │     │ • Notifications │     │ • Date Filter   │

│  └─────────────────────────────────────────────────────────────────────────┘││                 │     │                 │     │                 │

│                                                                              ││ • Address       │     │ SECURITY        │     │ • TX Detail     │

│  ┌─────────────────────────────────────────────────────────────────────────┐││   - Copy        │     │ • Biometrics    │     │   Modal         │

│  │ SCREENING RESULTS                                                       │││   - QR Code     │     │ • Auto-lock     │     │                 │

│  │                                                                          │││                 │     │ • TX Limit      │     │                 │

│  │  ✅ OFAC: Clear                                                         │││ • Tokens        │     │                 │     │                 │

│  │  ✅ EU Sanctions: Clear                                                 │││   - ETH         │     │ NETWORK         │     │                 │

│  │  ✅ UN Sanctions: Clear                                                 │││   - ERC-20s     │     │ • RPC Endpoint  │     │                 │

│  │  ⚠️ HMT: Potential match - Review required                             │││                 │     │ • Gas Price     │     │                 │

│  │                                                                          │││ • Quick Actions │     │                 │     │                 │

│  │  PEP Status: Not a PEP                                                  │││   - Send        │     │ COMPLIANCE      │     │                 │

│  └─────────────────────────────────────────────────────────────────────────┘││   - Receive     │     │ • Risk Warnings │     │                 │

└─────────────────────────────────────────────────────────────────────────────┘│   - Swap        │     │ • Confirmation  │     │                 │

│                 │     │ • Slippage      │     │                 │

┌─────────────────────────────────────────────────────────────────────────────┐└─────────────────┘     └─────────────────┘     └─────────────────┘

│                        EDD QUEUE TAB                                         │

│                                                                              │┌─────────────────┐

│  Enhanced Due Diligence - High-risk cases requiring manual review           ││    TRANSFER     │

│                                                                              ││Route: /transfer │

│  ┌─────────────────────────────────────────────────────────────────────────┐│├─────────────────┤

│  │ PENDING REVIEW (5)                                                      │││                 │

│  │───────────────────────────────────────────────────────────────────────││││SecureTransfer   │

│  │ Case ID  │ Address     │ Risk Score │ Trigger        │ Assigned  │Act │││Widget:          │

│  │ EDD-001  │ 0x9abc...   │ 0.88       │ High volume    │ @sarah    │[▶] │││                 │

│  │ EDD-002  │ 0xdef0...   │ 0.91       │ Mixer contact  │ Unassigned│[▶] │││ • Recipient     │

│  │ EDD-003  │ 0x1234...   │ 0.85       │ FATF grey list │ @john     │[▶] │││   Address       │

│  └─────────────────────────────────────────────────────────────────────────┘││                 │

│                                                                              ││ • Amount        │

│  ┌─────────────────────────────────────────────────────────────────────────┐││   (ETH/USD)     │

│  │ CASE DETAIL (when expanded)                                             │││                 │

│  │                                                                          │││ • Risk Preview  │

│  │  • Full transaction history                                             │││   - Score       │

│  │  • Risk factor breakdown                                                │││   - Warning     │

│  │  • Connected addresses graph                                            │││                 │

│  │  • Document upload                                                      │││ • MEV Protection│

│  │  • Decision: [Approve] [Escalate] [Reject]                             │││   Toggle        │

│  └─────────────────────────────────────────────────────────────────────────┘││                 │

└─────────────────────────────────────────────────────────────────────────────┘│ • Review &      │

```│   Confirm       │

│                 │

### FATF Rules Page│ • Status        │

│   Updates       │

```│                 │

┌─────────────────────────────────────────────────────────────────────────────┐└─────────────────┘

│                           FATF RULES PAGE                                    │```

│                         Route: /fatf-rules                                   │

└─────────────────────────────────────────────────────────────────────────────┘---



┌─────────────────────────────────────────────────────────────────────────────┐## 📱 Route Summary

│                                                                              │

│  FATF Travel Rule Compliance                                                │| Route | Page | Access | Description |

│                                                                              │|-------|------|--------|-------------|

│  ┌──────────────────────────────────────────────────────────────────────┐  │| `/` | HomePage | All | Landing page, wallet connection, main dashboard |

│  │                   COMPLIANCE STATUS                                   │  │| `/wallet` | WalletPage | All | Wallet management, balances, addresses |

│  │                                                                       │  │| `/transfer` | TransferPage | All | Dedicated transfer page with SecureTransferWidget |

│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │  │| `/history` | HistoryPage | All | Transaction history with filters |

│  │  │  Travel     │  │  Threshold  │  │  Reporting  │                  │  │| `/admin` | AdminPage | Admin/Compliance | Full admin dashboard with 4 tabs |

│  │  │  Rule       │  │  Monitoring │  │  Status     │                  │  │| `/settings` | SettingsPage | All | User preferences and configuration |

│  │  │  ✅ Active  │  │  €1,000     │  │  Current    │                  │  │

│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │  │---

│  └──────────────────────────────────────────────────────────────────────┘  │

│                                                                              │## 🎨 UI Component Library

│  ┌──────────────────────────────────────────────────────────────────────┐  │

│  │                   COUNTRY RISK MATRIX                                 │  │```

│  │                                                                       │  │SHARED WIDGETS

│  │  FATF Grey List (19 countries):                                      │  │├── SecureTransferWidget    - Complete transfer flow with risk assessment

│  │  [Map visualization with risk coloring]                              │  │├── RiskVisualizerWidget    - Risk score visualization and breakdown

│  │                                                                       │  │├── RiskLevelIndicator      - Color-coded risk badge

│  │  FATF Black List (3 countries):                                      │  │├── InteractiveWalletWidget - Wallet connection and management

│  │  • DPRK (North Korea)                                                │  │├── FeaturesCarousel        - Feature showcase on landing page

│  │  • Iran                                                               │  │└── TransactionCard         - Individual transaction display

│  │  • Myanmar                                                            │  │```

│  └──────────────────────────────────────────────────────────────────────┘  │

│                                                                              │---

│  [Open Detection Studio →]  Links to Next.js Dashboard (port 3006)          │

│                                                                              │## 🆕 NEW PAGES REQUIRED FOR COMPLETE COVERAGE

└─────────────────────────────────────────────────────────────────────────────┘

```The following pages are required to cover all smart contract functionality:



### Compliance Navigation Flow---



```## 🔄 Profile: NFT TRADER

COMPLIANCE (/compliance)

├── 📊 TabBar NavigationComplete NFT swap functionality for NFT ↔ ETH and NFT ↔ NFT swaps.

│   ├── Freeze/Unfreeze (Tab 0) → Account freezing controls

│   ├── Trusted Users (Tab 1)   → Whitelist management```

│   ├── PEP/Sanctions (Tab 2)   → Screening tools┌─────────────────────────────────────────────────────────────────────────────────┐

│   └── EDD Queue (Tab 3)       → High-risk case review│                           NFT SWAP SITEMAP                                       │

││                           Route: /nft-swap                                       │

├── 📂 Sidebar Navigation└─────────────────────────────────────────────────────────────────────────────────┘

│   ├── /compliance    → Compliance Tools Dashboard

│   ├── /fatf-rules    → FATF Travel Rule Compliance                              ┌─────────────────┐

│   ├── /disputes      → Dispute Resolution Center                              │  NFT SWAP PAGE  │

│   └── /detection-studio → SIEM Dashboard (Next.js)                              │ Route: /nft-swap│

│                              └────────┬────────┘

└── 🔗 Query Parameters                                       │

    └── /compliance?tab=freeze  → Direct to specific tab     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐

    └── /compliance?tab=pep     → Direct to PEP/Sanctions     │                 │               │               │                 │

```     ▼                 ▼               ▼               ▼                 ▼

┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐

---│  NFT → ETH  │  │  NFT → NFT  │  │   ACTIVE    │  │  COMPLETED  │  │   REFUNDS   │

│   SWAP      │  │    SWAP     │  │   SWAPS     │  │    SWAPS    │  │             │

## 🌐 Complete Route Map│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │   (Tab 3)   │  │   (Tab 4)   │

└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘

```       │                │               │

┌─────────────────────────────────────────────────────────────────────────────┐       ▼                ▼               ▼

│                        COMPLETE ROUTE STRUCTURE                              │┌─────────────────────────────────────────────────────────────────────────────────┐

└─────────────────────────────────────────────────────────────────────────────┘│                          NFT → ETH SWAP TAB                                      │

├─────────────────────────────────────────────────────────────────────────────────┤

PUBLIC ROUTES (No Auth)│                                                                                  │

├── /sign-in         → Sign In Page│  ┌────────────────────────────────────────────────────────────────────────────┐ │

├── /register        → Registration Page│  │                        SELECT YOUR NFT                                      │ │

└── /select-profile  → Profile Selector (Demo)│  ├────────────────────────────────────────────────────────────────────────────┤ │

│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                   │ │

AUTHENTICATED ROUTES (Shell with ProfileNavigationShell)│  │  │  [NFT 1] │  │  [NFT 2] │  │  [NFT 3] │  │  [NFT 4] │  ...              │ │

││  │  │  BAYC    │  │  Azuki   │  │  Doodles │  │  Moonbird│                   │ │

├── END USER ROUTES│  │  │  #1234   │  │  #5678   │  │  #9012   │  │  #3456   │                   │ │

│   ├── /                → Home Page (4 tabs)│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘                   │ │

│   ├── /wallet          → Wallet Management│  └────────────────────────────────────────────────────────────────────────────┘ │

│   ├── /transfer        → Dedicated Transfer│                                                                                  │

│   ├── /history         → Transaction History│  ┌────────────────────────────────────────────────────────────────────────────┐ │

│   ├── /settings        → App Settings│  │                        SWAP CONFIGURATION                                   │ │

│   ├── /nft-swap        → NFT Atomic Swaps│  ├────────────────────────────────────────────────────────────────────────────┤ │

│   ├── /cross-chain     → Cross-Chain Bridge│  │  Selected NFT: BAYC #1234                                                  │ │

│   ├── /disputes        → Dispute Center│  │  ┌──────────────────────────────────┐                                      │ │

│   ├── /dispute/:id     → Dispute Detail│  │  │ ETH Amount Requested:  [____] ETH │                                     │ │

│   ├── /safe            → Gnosis Safe Management│  │  │ Recipient Address:     [________] │                                     │ │

│   ├── /session-keys    → ERC-4337 Session Keys│  │  │ Hash Lock (optional):  [________] │                                     │ │

│   └── /zknaf           → zkNAF Privacy Proofs│  │  │ Time Lock:             [24 hours] │                                     │ │

││  │  └──────────────────────────────────┘                                      │ │

├── ADMIN ROUTES│  │                                                                             │ │

│   ├── /admin           → Admin Dashboard (4 tabs)│  │  Risk Assessment: 🟢 Low Risk (Score: 0.23)                                │ │

│   ├── /detection-studio→ Next.js SIEM (iframe)│  │                                                                             │ │

│   └── /approver        → Swap Approver Portal│  │                    [Initiate NFT → ETH Swap]                               │ │

││  └────────────────────────────────────────────────────────────────────────────┘ │

└── COMPLIANCE ROUTES│                                                                                  │

    ├── /compliance      → Compliance Tools (4 tabs)└─────────────────────────────────────────────────────────────────────────────────┘

    ├── /compliance?tab=X→ Direct tab navigation

    └── /fatf-rules      → FATF Compliance Page┌─────────────────────────────────────────────────────────────────────────────────┐

```│                          ACTIVE SWAPS TAB                                        │

├─────────────────────────────────────────────────────────────────────────────────┤

---│                                                                                  │

│  ┌─────────────────────────────────────────────────────────────────────────┐    │

## 🔌 Backend Service Integration│  │                    PENDING SWAPS (Waiting for Counterparty)             │    │

│  ├─────────────────────────────────────────────────────────────────────────┤    │

```│  │ Swap #abc123  │ BAYC #1234 → 10 ETH │ Waiting for ETH │ ⏰ 23:45:00     │    │

┌─────────────────────────────────────────────────────────────────────────────┐│  │ Swap #def456  │ Azuki #567 → NFT    │ Waiting for NFT │ ⏰ 12:30:00     │    │

│                        SERVICE PORT MAPPING                                  ││  └─────────────────────────────────────────────────────────────────────────┘    │

└─────────────────────────────────────────────────────────────────────────────┘│                                                                                  │

│  ┌─────────────────────────────────────────────────────────────────────────┐    │

FRONTEND SERVICES│  │                    READY TO COMPLETE                                    │    │

├── Port 3006  → Next.js Dashboard (Detection Studio / FATF)│  ├─────────────────────────────────────────────────────────────────────────┤    │

└── Port 3010  → Flutter Web App (Main UI)│  │ Swap #ghi789  │ BAYC #1234 → 10 ETH │ ETH Deposited   │ [COMPLETE SWAP] │    │

│  │               │ Enter Preimage: [_____________________]                 │    │

ML & COMPLIANCE SERVICES│  └─────────────────────────────────────────────────────────────────────────┘    │

├── Port 8000  → ML Risk Scoring API (hybrid_api.py)│                                                                                  │

├── Port 8001  → Graph Analysis API (run_graph_server.py)│  ┌─────────────────────────────────────────────────────────────────────────┐    │

├── Port 8002  → Policy Service (policy_api.py)│  │                    AWAITING APPROVAL (High Risk)                        │    │

├── Port 8003  → Monitoring Rules (monitoring_rules.py)│  ├─────────────────────────────────────────────────────────────────────────┤    │

├── Port 8004  → Sanctions Screening (sanctions_service.py)│  │ Swap #jkl012  │ Rare NFT → 50 ETH   │ Pending Approval │ 🟡 High Risk   │    │

├── Port 8005  → Geographic Risk (geographic_risk.py)│  └─────────────────────────────────────────────────────────────────────────┘    │

├── Port 8006  → Labeling Service (labeling_service.py)│                                                                                  │

├── Port 8007  → Orchestrator (Main Gateway)└─────────────────────────────────────────────────────────────────────────────────┘

└── Port 8008  → Integrity Service (UI Security)```



INFRASTRUCTURE**Smart Contract Functions Covered:**

├── Port 27017 → MongoDB (Data Storage)- `initiateNFTtoETHSwap()` - Start NFT ↔ ETH swap

├── Port 6379  → Redis (Caching)- `depositETHForNFT()` - Deposit ETH to complete swap

├── Port 7687  → Memgraph (Graph Database)- `completeNFTSwap()` - Complete swap with preimage

└── Port 9000  → MinIO (Object Storage)- `initiateNFTtoNFTSwap()` - Start NFT ↔ NFT swap

```- `depositNFTForSwap()` - Deposit second NFT

- `completeNFTtoNFTSwap()` - Complete NFT-to-NFT swap

---- `refundNFTSwap()` - Refund expired swap

- `approveSwap()` - (Approver) Approve high-risk swap

## 📱 Smart Contract Coverage

---

| Contract | UI Coverage | Route |

|----------|-------------|-------|## ⚖️ Profile: DISPUTE PARTICIPANT

| `AMTTPCore.sol` | SecureTransferWidget, History | `/`, `/history` |

| `AMTTPPolicyEngine.sol` | Compliance Tools | `/compliance` |Complete dispute resolution with Kleros arbitration integration.

| `AMTTPDisputeResolver.sol` | Dispute Center | `/disputes`, `/dispute/:id` |

| `AMTTPNFT.sol` | NFT Swap Page | `/nft-swap` |```

| `AMTTPCrossChain.sol` | Cross-Chain Page | `/cross-chain` |┌─────────────────────────────────────────────────────────────────────────────────┐

| `AMTTPSafeModule.sol` | Safe Management | `/safe` |│                         DISPUTE CENTER SITEMAP                                   │

| `AMTTPBiconomyModule.sol` | Session Keys | `/session-keys` |│                         Route: /disputes                                         │

| `AMTTPCoreZkNAF.sol` | zkNAF Page | `/zknaf` |└─────────────────────────────────────────────────────────────────────────────────┘



---                              ┌─────────────────┐

                              │ DISPUTE CENTER  │

## 🎨 Design System                              │Route: /disputes │

                              └────────┬────────┘

| Component | Color | Usage |                                       │

|-----------|-------|-------|     ┌─────────────────┬───────────────┼───────────────┬─────────────────┐

| Primary Purple | `#6366F1` | CTAs, Active States |     │                 │               │               │                 │

| Primary Blue | `#3B82F6` | Links, Info |     ▼                 ▼               ▼               ▼                 ▼

| Success Green | `#10B981` | Approved, Success |┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐

| Warning Orange | `#F59E0B` | Review, Caution |│   CREATE    │  │   ACTIVE    │  │   SUBMIT    │  │   RESOLVED  │  │   APPEALS   │

| Danger Red | `#EF4444` | Blocked, Error |│  DISPUTE    │  │  DISPUTES   │  │  EVIDENCE   │  │   HISTORY   │  │             │

| Dark Background | `#0F172A` | Main BG |│   (Tab 0)   │  │   (Tab 1)   │  │   (Tab 2)   │  │   (Tab 3)   │  │   (Tab 4)   │

| Dark Card | `#1E293B` | Card Surfaces |└──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘

       │                │               │

---       ▼                ▼               ▼

┌─────────────────────────────────────────────────────────────────────────────────┐

*Generated: January 2026*  │                       CREATE DISPUTE TAB                                         │

*AMTTP v2.0 - Flutter Web + Next.js Dashboard*├─────────────────────────────────────────────────────────────────────────────────┤

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
