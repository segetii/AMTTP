# AMTTP System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                🌐 USER INTERFACES                                    │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  📱 Mobile dApp    │  🖥️ Web Dashboard    │  🔗 DeFi Integration  │  📊 Admin Panel │
│  - Wallet connect │  - Policy management │  - SDK integration   │  - Monitoring   │
│  - Secure transfer │  - Transaction view  │  - API endpoints     │  - Analytics    │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              📦 CLIENT SDK LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  📚 AMTTP TypeScript SDK (257KB)                                                    │
│  ├── 🎯 AMTTPClient.ts           # Core client with fraud protection                │
│  ├── 🛡️ RiskService.ts          # Risk assessment integration                      │
│  ├── 🎛️ PolicyService.ts        # Policy management                               │
│  ├── 💸 TransactionService.ts    # Secure transaction handling                     │
│  └── ⚡ AtomicSwapService.ts     # Cross-chain atomic swaps                        │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                🔙 BACKEND SERVICES                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🌐 Oracle Service API (Express.js + MongoDB)                                      │
│  ├── 🎯 Risk Scoring Endpoints                                                     │
│  │   ├── POST /api/risk/dqn-score      # DQN-enhanced fraud detection             │
│  │   ├── POST /api/risk/score          # Original heuristic scoring               │
│  │   └── GET  /api/risk/score/:txId    # Risk score retrieval                     │
│  ├── 🔍 KYC Verification Endpoints                                                 │
│  │   ├── POST /api/kyc/verify          # Document verification                     │
│  │   └── GET  /api/kyc/status/:address # Verification status                      │
│  ├── 💸 Transaction Endpoints                                                      │
│  │   ├── POST /api/transaction/validate # Pre-transaction validation              │
│  │   └── GET  /api/transaction/:id     # Transaction details                      │
│  └── 🗄️ Data Services                                                             │
│      ├── 📊 MongoDB Collections        # Users, transactions, risk_scores         │
│      ├── 📁 MinIO Object Storage       # Documents, models, backups               │
│      └── 🌐 IPFS (Helia)              # Immutable transaction logs                │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               🧠 MACHINE LEARNING LAYER                             │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🤖 DQN Fraud Detection Engine (F1=0.669)                                          │
│  ├── 📊 Feature Engineering Pipeline                                               │
│  │   ├── transaction_amount          # Normalized transaction value                │
│  │   ├── user_frequency             # User's transaction frequency                 │
│  │   ├── geographic_risk            # Location-based risk assessment              │
│  │   ├── time_of_day               # Temporal pattern analysis                     │
│  │   ├── account_age_days          # Account maturity factor                       │
│  │   ├── velocity_last_hour        # Recent activity velocity                      │
│  │   ├── cross_border_indicator    # International transfer flag                  │
│  │   ├── amount_deviation          # Deviation from typical amounts               │
│  │   ├── recipient_reputation      # Recipient trust score                        │
│  │   ├── payment_method_risk       # Payment method risk level                    │
│  │   ├── device_fingerprint        # Device-based risk assessment                 │
│  │   ├── behavioral_anomaly        # Behavioral pattern analysis                  │
│  │   ├── network_analysis          # Social network risk                          │
│  │   ├── compliance_score          # Regulatory compliance score                  │
│  │   └── historical_disputes       # Historical dispute rate                      │
│  ├── 🧠 DQN Neural Network                                                         │
│  │   ├── Input Layer: 15 features  # Normalized feature vector                    │
│  │   ├── Hidden Layers: 3x128       # Deep Q-Network architecture                 │
│  │   ├── Output Layer: Q-values     # Action-value predictions                    │
│  │   └── Experience Replay Buffer   # Training data management                    │
│  ├── 🎯 Training Results                                                           │
│  │   ├── Dataset: 28,457 transactions # Real-world fraud data                     │
│  │   ├── F1 Score: 0.669           # Balanced accuracy metric                     │
│  │   ├── Precision: 0.723          # True positive rate                           │
│  │   ├── Recall: 0.625             # Fraud detection rate                         │
│  │   └── Training Time: 2.3h       # Full training duration                       │
│  └── ⚡ Real-time Inference                                                        │
│      ├── Response Time: <100ms     # Per transaction processing                    │
│      ├── Batch Processing: 1000/s  # Concurrent transaction scoring                │
│      └── Model Size: 15.2MB        # Optimized for production                     │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                               ⛓️ BLOCKCHAIN LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  🏗️ Modular Smart Contract Architecture (All under 24,576 byte limit)            │
│                                                                                     │
│  🎯 AMTTPStreamlined.sol (9% of limit) - Core Token Contract                      │
│  ├── 💰 ERC20 Token Functionality                                                  │
│  │   ├── secureTransfer()          # Fraud-protected transfers                     │
│  │   ├── balanceOf()               # Account balance queries                       │
│  │   └── approve()                 # Token allowance management                    │
│  ├── 🛡️ Fraud Protection Integration                                              │
│  │   ├── submitRiskScore()         # Oracle risk score submission                  │
│  │   ├── validateTransaction()     # Policy-based validation                      │
│  │   ├── releaseEscrow()          # Manual review resolution                       │
│  │   └── getTransaction()         # Transaction status queries                     │
│  ├── 📊 User Profile Management                                                    │
│  │   ├── updateUserProfile()      # Reputation scoring                            │
│  │   ├── getUserProfile()         # Profile information                           │
│  │   └── updateKYCStatus()        # KYC verification status                       │
│  └── 🎛️ Policy Manager Integration                                                │
│      ├── setPolicyManager()       # Connect policy management                     │
│      ├── canTransfer()            # Pre-transfer validation                       │
│      └── policyValidationEnabled  # Policy enforcement toggle                     │
│                                                                                     │
│  🎛️ AMTTPPolicyManager.sol (4% of limit) - Policy Coordination                   │
│  ├── 📋 User Policy Management                                                     │
│  │   ├── setUserPolicy()          # Amount limits, risk thresholds               │
│  │   ├── getUserPolicy()          # Policy retrieval                              │
│  │   └── setTrustedUser()         # Trusted user designation                      │
│  ├── 🔍 Transaction Validation                                                     │
│  │   ├── validateTransaction()    # Core validation logic                         │
│  │   ├── isTransactionAllowed()   # Pre-check capability                          │
│  │   └── Risk Processing Logic:                                                   │
│  │       ├── 0-39%: Auto-approve  # Low risk transactions                         │
│  │       ├── 40-69%: Monitor      # Medium risk with tracking                     │
│  │       ├── 70-79%: Escrow       # High risk manual review                       │
│  │       └── 80%+: Reject         # Very high risk blocking                       │
│  └── 🔗 Policy Engine Integration                                                  │
│      ├── setPolicyEngine()        # Connect advanced policies                     │
│      ├── policyEngineEnabled      # Advanced features toggle                      │
│      └── globalRiskThreshold      # System-wide risk limits                       │
│                                                                                     │
│  🧠 AMTTPPolicyEngine.sol (10.4% of limit) - Advanced Policy Engine              │
│  ├── 📊 Advanced Policy Types                                                      │
│  │   ├── TransactionPolicy        # Amount limits, frequency controls             │
│  │   ├── RiskPolicy               # Dynamic risk thresholds                       │
│  │   ├── VelocityLimit            # Time-based transaction limits                 │
│  │   ├── ComplianceRule           # Regulatory compliance automation              │
│  │   └── ApprovalWorkflow         # Multi-signature approvals                     │
│  ├── 🔄 Complex Validation Logic                                                   │
│  │   ├── Multi-dimensional Risk   # Geographic + temporal + behavioral            │
│  │   ├── Machine Learning Integration # DQN model result processing               │
│  │   ├── Regulatory Compliance    # AML/KYC rule enforcement                      │
│  │   └── Dynamic Policy Updates   # Real-time policy adjustments                 │
│  ├── 📋 Enterprise Features                                                        │
│  │   ├── Multi-signature Approvals # Institutional control                        │
│  │   ├── Compliance Reporting     # Automated regulatory reports                  │
│  │   ├── Audit Trail Management   # Immutable decision logging                    │
│  │   └── Emergency Controls       # Circuit breakers and freezes                 │
│  └── 🚀 Upgradeability & Security                                                 │
│      ├── UUPS Proxy Pattern       # Secure upgrade mechanism                      │
│      ├── Access Control (Ownable) # Permission management                         │
│      ├── Pausable Operations      # Emergency pause capability                    │
│      └── Reentrancy Protection    # MEV and attack prevention                     │
└─────────────────┬───────────────────────┬─────────────────────┬───────────────────┘
                  │                       │                     │
                  ▼                       ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              🌐 BLOCKCHAIN NETWORKS                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│  Production Networks:                                                               │
│  ├── 🔷 Ethereum Mainnet         # Primary deployment target                       │
│  ├── 🟣 Polygon                  # L2 scaling solution                             │
│  ├── 🔵 Arbitrum                 # Optimistic rollup                              │
│  ├── 🔴 Optimism                 # Optimistic rollup                              │
│  └── 🟡 BSC                      # Binance Smart Chain                            │
│                                                                                     │
│  Development Networks:                                                              │
│  ├── 🧪 Goerli Testnet          # Ethereum testing                                │
│  ├── 🧪 Sepolia Testnet         # Ethereum testing                                │
│  ├── 🏠 Hardhat Local           # Local development                               │
│  └── 🌐 Ganache                  # GUI testing environment                        │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    📊 SYSTEM METRICS
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  Performance Metrics:                                                              │
│  ├── 🎯 DQN F1 Score: 0.669 (66.9% balanced accuracy)                            │
│  ├── ⚡ API Response: <200ms average                                               │
│  ├── 🔗 Contract Gas: ~150k per secure transfer                                   │
│  ├── 🧠 ML Inference: <100ms per transaction                                      │
│  ├── 👥 Concurrent Users: 1,000+ tested                                          │
│  └── 📦 SDK Bundle Size: 257KB optimized                                         │
│                                                                                     │
│  Security & Compliance:                                                            │
│  ├── 🛡️ OpenZeppelin Security Standards                                          │
│  ├── 🔐 Multi-signature Oracle Validation                                         │
│  ├── 📋 GDPR-compliant Data Handling                                              │
│  ├── 🔍 Immutable Audit Trails                                                    │
│  ├── ⚡ Emergency Pause Mechanisms                                                │
│  └── 📊 Real-time Monitoring & Alerting                                          │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                🔄 DATA FLOW DIAGRAM
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  Transaction Lifecycle:                                                            │
│                                                                                     │
│  1. 👤 User → 📱 dApp/SDK → 🔍 Pre-validation → 🎯 Risk Check                    │
│                                                ↓                                   │
│  2. ⛓️ Smart Contract → 📊 Transaction Created → 🔔 Event Emitted                 │
│                                                ↓                                   │
│  3. 🌐 Oracle Service → 📊 Data Fetch → 🧠 DQN Processing → 🎯 Risk Score        │
│                                                ↓                                   │
│  4. 🎛️ Policy Validation → 📋 Business Rules → ⚖️ Decision Engine                │
│                                                ↓                                   │
│  5. 💸 Execute Transfer | 🏦 Escrow | ❌ Reject → 📊 Audit Log → 🔔 Notification │
└─────────────────────────────────────────────────────────────────────────────────────┘
```