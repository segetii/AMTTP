# AMTTP User Profile Site Maps

> **⚠️ IMPLEMENTATION STATUS: This document reflects the ACTUAL implementation in `orchestrator.py`**

This document outlines the user journey and accessible features for each entity profile type in the AMTTP compliance system.

---

## 🔧 Current Implementation Reference

**Source:** `backend/compliance-service/orchestrator.py`  
**Port:** 8007  
**Endpoints:**
- `POST /evaluate` - Full compliance evaluation
- `GET /profiles/{address}` - Get entity profile
- `PUT /profiles/{address}` - Update profile
- `POST /profiles/{address}/set-type/{type}` - Set entity type with presets

---

## 🏠 Common Navigation Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AMTTP PLATFORM                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  🏠 Home  │  💼 Dashboard  │  🔄 Transfer  │  🛡️ Compliance  │  ⚙️ Settings  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 IMPLEMENTED Profile Presets (from `orchestrator.py`)

```python
PROFILE_PRESETS = {
    EntityType.RETAIL: {
        "daily_limit_eth": 10.0,
        "monthly_limit_eth": 100.0,
        "single_tx_limit_eth": 5.0,
        "risk_tolerance": RiskTolerance.CONSERVATIVE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.INSTITUTIONAL: {
        "daily_limit_eth": 1000.0,
        "monthly_limit_eth": 10000.0,
        "single_tx_limit_eth": 500.0,
        "risk_tolerance": RiskTolerance.MODERATE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.VASP: {
        "daily_limit_eth": 10000.0,
        "monthly_limit_eth": 100000.0,
        "single_tx_limit_eth": 5000.0,
        "risk_tolerance": RiskTolerance.PERMISSIVE,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.HIGH_NET_WORTH: {
        "daily_limit_eth": 500.0,
        "monthly_limit_eth": 5000.0,
        "single_tx_limit_eth": 250.0,
        "risk_tolerance": RiskTolerance.STRICT,
        "travel_rule_threshold_eth": 0.84,
    },
    EntityType.UNVERIFIED: {
        "daily_limit_eth": 1.0,
        "monthly_limit_eth": 5.0,
        "single_tx_limit_eth": 0.5,
        "risk_tolerance": RiskTolerance.STRICT,
        "travel_rule_threshold_eth": 0.0,  # Always require Travel Rule info
    },
}
```

---

## 👤 UNVERIFIED User (New/Anonymous)

**KYC Level:** NONE  
**Limits:** 0.5 ETH/tx, 1 ETH/day, 5 ETH/month  
**Risk Tolerance:** STRICT

```
                           ┌────────────────────┐
                           │    UNVERIFIED      │
                           │    Landing Page    │
                           └─────────┬──────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
   ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
   │  🔐 Sign Up   │          │  📊 View Only │          │  ℹ️ About    │
   │  (Required)  │          │  Dashboard    │          │  Platform   │
   └──────┬───────┘          └──────┬───────┘          └─────────────┘
          │                          │
          ▼                          ▼
   ┌──────────────┐          ┌──────────────┐
   │  📧 Email    │          │  💰 Balance   │
   │  Verification│          │  (Read Only) │
   └──────┬───────┘          └──────────────┘
          │
          ▼
   ┌──────────────┐
   │  🪪 Start KYC │
   │  Process     │
   └──────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ RESTRICTIONS:                                                            │
│ ❌ Cannot send transactions > 0.5 ETH                                   │
│ ❌ All transactions require Travel Rule info                            │
│ ❌ No access to advanced features                                       │
│ ❌ High-risk transactions BLOCKED                                       │
│ ⚠️  All suspicious activity triggers BLOCK                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🛒 RETAIL User (Individual)

**KYC Level:** BASIC → STANDARD  
**Limits:** 5 ETH/tx, 10 ETH/day, 100 ETH/month  
**Risk Tolerance:** CONSERVATIVE

```
                           ┌────────────────────┐
                           │      RETAIL        │
                           │    Dashboard       │
                           └─────────┬──────────┘
                                     │
     ┌───────────────┬───────────────┼───────────────┬───────────────┐
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
┌─────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌─────────┐
│ 💰 Wallet│   │ 🔄 Transfer│   │ 📜 History │   │ 🛡️ Safety │   │ ⚙️ Acct  │
│         │   │           │   │           │   │           │   │ Settings│
└────┬────┘   └─────┬─────┘   └─────┬─────┘   └─────┬─────┘   └────┬────┘
     │              │               │               │              │
     ▼              ▼               ▼               ▼              ▼
┌─────────┐   ┌───────────┐   ┌───────────┐   ┌───────────┐   ┌─────────┐
│ Balance │   │ Send ETH  │   │ All Txs   │   │ Risk Score│   │ Profile │
│ Portfolio│   │ (≤5 ETH)  │   │ Pending   │   │ Overview  │   │ KYC     │
│ Assets  │   │           │   │ Completed │   │           │   │ Security│
└─────────┘   └─────┬─────┘   └───────────┘   └───────────┘   └─────────┘
                    │
                    ▼
           ┌───────────────┐
           │ 📝 Recipient   │
           │ • Address     │
           │ • Amount      │
           │ • Memo        │
           └───────┬───────┘
                   │
                   ▼
           ┌───────────────┐
           │ ✅ Compliance  │
           │ Pre-Check     │
           │ • Sanctions   │
           │ • Geo Risk    │
           │ • Limits      │
           └───────┬───────┘
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐
   │✓ APPROVE│ │⏳ ESCROW│ │✗ BLOCK │
   │ Send   │ │ 24-48h │ │ Denied │
   └────────┘ └────────┘ └────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ CAPABILITIES:                                                            │
│ ✅ Standard transfers up to 5 ETH                                       │
│ ✅ View transaction history                                             │
│ ✅ Basic portfolio view                                                 │
│ ⚠️  High-value tx (>5 ETH) → ESCROW 24h                                 │
│ ⚠️  Travel Rule applies at 0.84 ETH                                     │
│ ❌ No batch transactions                                                │
│ ❌ No API access                                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🏢 INSTITUTIONAL User (Corporate)

**KYC Level:** STANDARD → ENHANCED  
**Limits:** 500 ETH/tx, 1,000 ETH/day, 10,000 ETH/month  
**Risk Tolerance:** MODERATE

```
                           ┌────────────────────┐
                           │   INSTITUTIONAL    │
                           │    Dashboard       │
                           └─────────┬──────────┘
                                     │
  ┌──────────┬──────────┬────────────┼────────────┬──────────┬──────────┐
  │          │          │            │            │          │          │
  ▼          ▼          ▼            ▼            ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ ┌──────┐
│💰 Treas│ │🔄 Ops │ │📊 Reports│ │👥 Team   │ │🛡️ Compli-│ │📡 API │ │⚙️ Admin│
│ury    │ │      │ │          │ │ Mgmt    │ │ance     │ │      │ │      │
└───┬───┘ └───┬──┘ └────┬─────┘ └────┬────┘ └────┬────┘ └───┬──┘ └───┬──┘
    │         │          │            │           │          │        │
    ▼         ▼          ▼            ▼           ▼          ▼        ▼
┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────┐ ┌──────┐
│Multi-│ │Single TX │ │Daily     │ │Add Users │ │Risk Dash │ │API   │ │Corp  │
│Wallet│ │(≤500 ETH)│ │Summary   │ │Roles     │ │Sanctions │ │Keys  │ │KYC   │
│Mgmt  │ │Batch TX  │ │Monthly   │ │Approvers │ │Geo Status│ │Docs  │ │Docs  │
│      │ │Scheduled │ │Quarterly │ │Audit Log │ │Alerts    │ │      │ │      │
└──────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────┘ └──────┘

                    ┌─────────────────────────────┐
                    │      APPROVAL WORKFLOW      │
                    └─────────────┬───────────────┘
                                  │
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
   ┌───────────┐           ┌───────────┐           ┌───────────┐
   │ < 100 ETH │           │100-500 ETH│           │ > 500 ETH │
   │ Auto-OK   │           │ 1 Approver│           │ 2 Approvers│
   │ if clean  │           │ Required  │           │ + Compliance│
   └───────────┘           └───────────┘           └───────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ CAPABILITIES:                                                            │
│ ✅ Multi-wallet treasury management                                     │
│ ✅ Batch transaction processing                                         │
│ ✅ Scheduled/recurring transfers                                        │
│ ✅ Team roles & approval workflows                                      │
│ ✅ API access for integrations                                          │
│ ✅ Compliance reporting dashboard                                       │
│ ⚠️  Transactions >500 ETH → REVIEW                                      │
│ ⚠️  High-risk jurisdictions → Escrow 48h                                │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🏦 VASP User (Virtual Asset Service Provider)

**KYC Level:** INSTITUTIONAL  
**Limits:** 5,000 ETH/tx, 10,000 ETH/day, 100,000 ETH/month  
**Risk Tolerance:** PERMISSIVE

```
                           ┌────────────────────┐
                           │       VASP         │
                           │  Control Center    │
                           └─────────┬──────────┘
                                     │
┌────────┬────────┬────────┬─────────┼─────────┬────────┬────────┬────────┐
│        │        │        │         │         │        │        │        │
▼        ▼        ▼        ▼         ▼         ▼        ▼        ▼        ▼
┌────┐ ┌────┐ ┌────────┐ ┌────┐ ┌────────┐ ┌────────┐ ┌────┐ ┌────┐ ┌────┐
│💰  │ │🔄  │ │📊 Real │ │🌐  │ │🛡️ Full │ │📡 Full │ │📋  │ │🔗  │ │⚙️  │
│Omni│ │High│ │Time    │ │Travel│ │Compliance│ │API    │ │Audit│ │Inter│ │Admin│
│bus │ │Vol │ │Monitor │ │Rule │ │Suite    │ │Suite  │ │Trail│ │ops  │ │     │
└──┬─┘ └──┬─┘ └───┬────┘ └──┬─┘ └───┬────┘ └───┬────┘ └──┬──┘ └──┬─┘ └──┬─┘
   │      │       │         │       │          │         │       │      │
   ▼      ▼       ▼         ▼       ▼          ▼         ▼       ▼      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        VASP FEATURE DETAILS                              │
├──────────────┬────────────────────────────────────────────────────────────┤
│ Omnibus      │ • Multi-chain wallet management                          │
│ Wallets      │ • Hot/Cold wallet separation                             │
│              │ • Automated rebalancing                                   │
├──────────────┼────────────────────────────────────────────────────────────┤
│ High Volume  │ • Up to 5,000 ETH per transaction                        │
│ Operations   │ • Batch processing (1000+ tx/batch)                      │
│              │ • Priority queue processing                              │
├──────────────┼────────────────────────────────────────────────────────────┤
│ Real-Time    │ • Live transaction monitoring                            │
│ Monitoring   │ • Anomaly detection alerts                               │
│              │ • Custom rule configuration                              │
├──────────────┼────────────────────────────────────────────────────────────┤
│ Travel Rule  │ • TRISA network integration                              │
│ Compliance   │ • Automated originator/beneficiary data                  │
│              │ • Cross-VASP messaging                                   │
├──────────────┼────────────────────────────────────────────────────────────┤
│ Compliance   │ • Full sanctions screening                               │
│ Suite        │ • PEP/Adverse media checks                               │
│              │ • Jurisdiction risk management                           │
│              │ • SAR auto-filing integration                            │
├──────────────┼────────────────────────────────────────────────────────────┤
│ API Suite    │ • REST & WebSocket APIs                                  │
│              │ • Webhook notifications                                  │
│              │ • Rate limit: 10,000 req/min                             │
├──────────────┼────────────────────────────────────────────────────────────┤
│ Audit Trail  │ • Complete transaction logs                              │
│              │ • Compliance decision history                            │
│              │ • FCA-ready reports                                      │
├──────────────┼────────────────────────────────────────────────────────────┤
│ Interops     │ • LayerZero cross-chain                                  │
│              │ • DEX integrations                                       │
│              │ • Custodian connections                                  │
└──────────────┴────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ CAPABILITIES:                                                            │
│ ✅ Highest transaction limits (5,000 ETH single, 100K/month)            │
│ ✅ Full Travel Rule automation                                          │
│ ✅ Cross-chain bridging (LayerZero)                                     │
│ ✅ Real-time compliance monitoring                                      │
│ ✅ SAR auto-filing capability                                           │
│ ✅ Full API suite with WebSockets                                       │
│ ✅ Priority support & SLA                                               │
│ ⚠️  Only BLOCK on confirmed sanctions                                   │
│ ⚠️  20% risk score reduction for institutional KYC                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 💎 HIGH_NET_WORTH User (HNW Individual)

**KYC Level:** ENHANCED  
**Limits:** 250 ETH/tx, 500 ETH/day, 5,000 ETH/month  
**Risk Tolerance:** STRICT

```
                           ┌────────────────────┐
                           │  HIGH NET WORTH    │
                           │ Private Dashboard  │
                           └─────────┬──────────┘
                                     │
      ┌──────────────┬───────────────┼───────────────┬──────────────┐
      │              │               │               │              │
      ▼              ▼               ▼               ▼              ▼
┌───────────┐ ┌───────────┐   ┌───────────┐   ┌───────────┐ ┌───────────┐
│💰 Private │ │🔄 Curated │   │📊 Wealth  │   │🛡️ Enhanced│ │👤 Concierge│
│ Wealth    │ │ Transfers │   │ Reports   │   │ Protection│ │ Support   │
└─────┬─────┘ └─────┬─────┘   └─────┬─────┘   └─────┬─────┘ └─────┬─────┘
      │             │               │               │             │
      ▼             ▼               ▼               ▼             ▼
┌───────────┐ ┌───────────┐   ┌───────────┐   ┌───────────┐ ┌───────────┐
│• Multi-sig│ │• Trusted  │   │• Portfolio│   │• Extra    │ │• Dedicated│
│  Vaults   │ │  Address  │   │  Analysis │   │  Sanctions│ │  Manager  │
│• Cold     │ │  Book     │   │• Tax Rpts │   │  Checks   │ │• Priority │
│  Storage  │ │• Large TX │   │• Audit    │   │• PEP Check│ │  Queue    │
│• DeFi     │ │  Approval │   │  History  │   │• SOF Verify│ │• 24/7     │
│  Positions│ │  Workflow │   │           │   │           │ │  Support  │
└───────────┘ └─────┬─────┘   └───────────┘   └───────────┘ └───────────┘
                    │
                    ▼
           ┌───────────────┐
           │ STRICT CHECKS │
           └───────┬───────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
    ▼              ▼              ▼
┌────────┐   ┌──────────┐   ┌────────┐
│<50 ETH │   │ 50-250   │   │>250 ETH│
│Std Check│   │ Enhanced │   │ Manual │
│         │   │ + Verify │   │ Review │
└────────┘   └──────────┘   └────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ CAPABILITIES:                                                            │
│ ✅ Private wealth dashboard                                             │
│ ✅ Multi-signature vault management                                     │
│ ✅ Trusted address book (pre-verified recipients)                       │
│ ✅ Detailed wealth & tax reporting                                      │
│ ✅ Dedicated relationship manager                                       │
│ ✅ Priority processing queue                                            │
│ ⚠️  ALL transactions get enhanced screening                             │
│ ⚠️  Source of Funds verification required                               │
│ ⚠️  PEP screening on every transaction                                  │
│ ⚠️  Any suspicious activity → BLOCK (no escrow option)                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Comparison Matrix (ACTUAL IMPLEMENTATION)

| Feature | UNVERIFIED | RETAIL | INSTITUTIONAL | VASP | HIGH_NET_WORTH |
|---------|------------|--------|---------------|------|----------------|
| **Single TX Limit** | **0.5 ETH** | **5 ETH** | **500 ETH** | **5,000 ETH** | **250 ETH** |
| **Daily Limit** | **1 ETH** | **10 ETH** | **1,000 ETH** | **10,000 ETH** | **500 ETH** |
| **Monthly Limit** | **5 ETH** | **100 ETH** | **10,000 ETH** | **100,000 ETH** | **5,000 ETH** |
| **Risk Tolerance** | **STRICT** | **CONSERVATIVE** | **MODERATE** | **PERMISSIVE** | **STRICT** |
| **Travel Rule Threshold** | **0 ETH** (always) | **0.84 ETH** | **0.84 ETH** | **0.84 ETH** | **0.84 ETH** |

### Risk Tolerance Behaviors (Implemented)

| Risk Tolerance | Behavior on Suspicious Activity |
|----------------|--------------------------------|
| **STRICT** | Block anything suspicious - no escrow option |
| **CONSERVATIVE** | Escrow high-risk transactions for review |
| **MODERATE** | Flag for manual review, allow to proceed |
| **PERMISSIVE** | Only block confirmed sanctions matches |

### KYC Levels (Implemented)

| KYC Level | Description | Typical Profile |
|-----------|-------------|-----------------|
| **NONE** | No verification | UNVERIFIED |
| **BASIC** | Email + phone verified | RETAIL (initial) |
| **STANDARD** | ID verified | RETAIL (full) |
| **ENHANCED** | Full KYC + source of funds | HIGH_NET_WORTH |
| **INSTITUTIONAL** | Corporate KYC/KYB | VASP, INSTITUTIONAL |

### Compliance Actions (Implemented)

| Action | Description |
|--------|-------------|
| **APPROVE** | Transaction can proceed immediately |
| **ESCROW** | Hold funds for specified duration (24-48h) |
| **REVIEW** | Flag for manual compliance review |
| **BLOCK** | Transaction rejected + SAR may be required |
| **REQUIRE_INFO** | Additional KYC/Travel Rule data needed |

---

## 🔐 Decision Flow by Profile

```
                          INCOMING TRANSACTION
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │    SANCTIONS CHECK      │
                    │    (All Profiles)       │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │ SANCTIONED       │ CLEAN            │
              ▼                  ▼                  
         ┌────────┐        ┌──────────────────┐
         │ BLOCK  │        │   LOAD PROFILE   │
         │ + SAR  │        └────────┬─────────┘
         └────────┘                 │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
             ┌──────────┐    ┌──────────┐    ┌──────────┐
             │ Check    │    │ Check    │    │ Check    │
             │ Limits   │    │ Geo Risk │    │ KYC Level│
             └────┬─────┘    └────┬─────┘    └────┬─────┘
                  │               │               │
                  └───────────────┼───────────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │      PROFILE-BASED        │
                    │      RISK TOLERANCE       │
                    └─────────────┬─────────────┘
                                  │
    ┌─────────────────────────────┼─────────────────────────────┐
    │ STRICT                      │ CONSERVATIVE/MODERATE       │ PERMISSIVE
    │ (UNVERIFIED, HNW)           │ (RETAIL, INSTITUTIONAL)     │ (VASP)
    ▼                             ▼                             ▼
┌─────────┐                 ┌───────────┐                 ┌───────────┐
│ Any     │                 │ High Risk │                 │ Only      │
│ Issue   │                 │ → ESCROW  │                 │ Confirmed │
│ → BLOCK │                 │ Med Risk  │                 │ Sanctions │
└─────────┘                 │ → REVIEW  │                 │ → BLOCK   │
                            └───────────┘                 └───────────┘
```

---

## 📍 URL Routes by Profile (Planned)

> **Note:** These routes are planned UI features. Current implementation focuses on API-first compliance.

| Route | UNVERIFIED | RETAIL | INSTITUTIONAL | VASP | HIGH_NET_WORTH |
|-------|------------|--------|---------------|------|----------------|
| `/dashboard` | ⚠️ Limited | ✅ | ✅ | ✅ | ✅ |
| `/transfer` | ❌ | ✅ | ✅ | ✅ | ✅ |
| `/transfer/batch` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/history` | ⚠️ Limited | ✅ | ✅ | ✅ | ✅ |
| `/compliance` | ❌ | ⚠️ View | ✅ | ✅ Full | ⚠️ View |
| `/compliance/sanctions` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/compliance/alerts` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/reports` | ❌ | ❌ | ✅ | ✅ | ✅ |
| `/reports/tax` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `/team` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/api-keys` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `/settings` | ⚠️ Limited | ✅ | ✅ | ✅ | ✅ |
| `/settings/kyc` | ✅ Required | ✅ | ✅ | ✅ | ✅ |
| `/vault` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `/concierge` | ❌ | ❌ | ❌ | ❌ | ✅ |
| `/interops` | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## 🖥️ Currently Implemented API Endpoints

### Orchestrator Service (Port 8007)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health + connected services status |
| `/evaluate` | POST | Full compliance evaluation for a transaction |
| `/profiles/{address}` | GET | Get entity profile by address |
| `/profiles/{address}` | PUT | Update entity profile |
| `/profiles/{address}/set-type/{type}` | POST | Set entity type with preset limits |
| `/profiles` | GET | List all entity profiles |
| `/decisions` | GET | List compliance decision history |
| `/entity-types` | GET | List available entity types and presets |

### Supporting Services

| Service | Port | Key Endpoints |
|---------|------|---------------|
| **Sanctions** | 8004 | `POST /sanctions/check`, `GET /sanctions/stats` |
| **Monitoring** | 8005 | `POST /monitor/transaction`, `GET /alerts` |
| **Geo Risk** | 8006 | `POST /geo/country-risk`, `GET /geo/lists/*` |
| **Policy** | 8003 | `GET /policies`, `POST /policies` |

---

## 🧪 Test Examples

### Test UNVERIFIED User (will be blocked/require info)
```powershell
$body = @{from_address="0x0000000000000000000000000000000000000001"; to_address="0x0000000000000000000000000000000000000002"; value_eth=1.0} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8007/evaluate" -Method POST -Body $body -ContentType "application/json"
# Result: REQUIRE_INFO or BLOCK (exceeds 0.5 ETH limit)
```

### Test VASP Profile (high limits)
```powershell
# First, create VASP profile
Invoke-RestMethod -Uri "http://127.0.0.1:8007/profiles/0xABCD1234/set-type/VASP" -Method POST

# Then evaluate large transaction
$body = @{from_address="0xABCD1234"; to_address="0x9999"; value_eth=1000.0} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8007/evaluate" -Method POST -Body $body -ContentType "application/json"
# Result: APPROVE (within 5,000 ETH limit)
```

### Test Sanctioned Address (always blocked)
```powershell
$body = @{from_address="0x8589427373d6d84e98730d7795d8f6f8731fda16"; to_address="0x9999"; value_eth=0.1} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8007/evaluate" -Method POST -Body $body -ContentType "application/json"
# Result: BLOCK + requires_sar=true (Tornado Cash address)
```

---

*Last updated: January 8, 2026*  
*Document version: 1.1*  
*Source of truth: `backend/compliance-service/orchestrator.py`*
