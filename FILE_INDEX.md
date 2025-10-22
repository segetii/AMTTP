# AMTTP Complete File Index & Directory Structure

## 📁 Project Root Structure

```
c:\amttp/
├── 📋 Configuration Files
│   ├── package.json                    # Node.js dependencies and scripts
│   ├── package-lock.json               # Locked dependency versions
│   ├── hardhat.config.cjs             # Hardhat blockchain development config
│   ├── docker-compose.yml             # Multi-service container orchestration
│   ├── Makefile                       # Build automation shortcuts
│   ├── .env                           # Environment variables (API keys, DB)
│   ├── .gitignore                     # Git exclusion rules
│   └── .dockerignore                  # Docker build exclusions
│
├── 📚 Documentation
│   ├── AMTTP_ROADMAP.md               # Project roadmap and milestones
│   ├── ML_ARCHITECTURE_DIAGRAM.md     # Machine learning architecture docs
│   ├── PROJECT_DOCUMENTATION.md       # Complete project documentation
│   ├── ARCHITECTURE_DIAGRAM.md        # Visual system architecture
│   └── DEVELOPER_GUIDE.md             # Developer quick reference
│
├── ⛓️ Smart Contracts (/contracts/)
├── 🔙 Backend Services (/backend/)
├── 🤖 Machine Learning (/cloud-training/)
├── 📦 Client SDK (/packages/)
├── 🧪 Testing Suite (/test/)
├── 🚀 Deployment Scripts (/scripts/)
├── 📊 Data Storage (/data/)
├── 🎨 Frontend (/frontend/)
├── 📁 Build Artifacts (/artifacts/, /cache/, /node_modules/)
└── 🔧 Development Tools (/hardhat/, /.github/)
```

---

## ⛓️ Smart Contracts Directory (`/contracts/`)

```
contracts/
├── 🎯 Core Production Contracts
│   ├── AMTTPStreamlined.sol           # Main AMTTP token with fraud protection
│   │   ├── Size: 9% of 24,576 byte limit ✅
│   │   ├── Features: ERC20 + fraud detection + policy integration
│   │   ├── Key Functions:
│   │   │   ├── secureTransfer()       # Protected token transfers
│   │   │   ├── submitRiskScore()      # Oracle risk score submission
│   │   │   ├── validateTransaction()  # Policy-based validation
│   │   │   ├── releaseEscrow()       # Manual review resolution
│   │   │   └── canTransfer()         # Pre-transfer validation
│   │   └── Logic: Transaction lifecycle with risk-based routing
│   │
│   ├── AMTTPPolicyManager.sol         # Policy coordination layer
│   │   ├── Size: 4% of byte limit ✅
│   │   ├── Features: User policies + risk validation + engine interface
│   │   ├── Key Functions:
│   │   │   ├── setUserPolicy()       # Configure user limits/thresholds
│   │   │   ├── validateTransaction() # Core validation logic
│   │   │   ├── setTrustedUser()      # Trusted user management
│   │   │   └── setPolicyEngine()     # Connect advanced policies
│   │   └── Logic: Risk-based decision engine (approve/escrow/reject)
│   │
│   └── AMTTPPolicyEngine.sol          # Advanced policy engine
│       ├── Size: 10.4% of byte limit ✅
│       ├── Features: Complex policies + compliance + workflows
│       ├── Key Functions:
│       │   ├── createTransactionPolicy()  # Amount/frequency limits
│       │   ├── createRiskPolicy()         # Dynamic risk thresholds
│       │   ├── createVelocityLimit()      # Time-based controls
│       │   ├── createComplianceRule()     # Regulatory automation
│       │   └── createApprovalWorkflow()   # Multi-sig approvals
│       └── Logic: Enterprise-grade policy management
│
├── 📚 Mock Contracts (/mocks/)
│   └── (Testing contracts for development)
│
└── 🗄️ Legacy/Archive
    ├── withnft.sol                    # ❌ Original monolithic (size exceeded)
    ├── firstcontract.doc             # Initial contract documentation
    └── allingnedversion5.doc          # Contract alignment notes
```

---

## 🔙 Backend Services Directory (`/backend/`)

```
backend/
├── 🌐 Oracle Service (/oracle-service/)
│   ├── 📁 Source Code (/src/)
│   │   ├── 🛣️ API Routes (/routes/)
│   │   │   ├── risk.ts               # 🎯 DQN risk scoring endpoints
│   │   │   │   ├── POST /api/risk/dqn-score    # DQN-enhanced detection
│   │   │   │   ├── POST /api/risk/score        # Original heuristic scoring
│   │   │   │   ├── GET /api/risk/score/:txId   # Risk score retrieval
│   │   │   │   └── POST /api/risk/bulk-score   # Batch processing
│   │   │   │
│   │   │   ├── kyc.ts                # 🔍 KYC verification endpoints
│   │   │   │   ├── POST /api/kyc/verify        # Document verification
│   │   │   │   ├── GET /api/kyc/status/:addr   # Verification status
│   │   │   │   └── POST /api/kyc/update        # Update information
│   │   │   │
│   │   │   └── transaction.ts        # 💸 Transaction management
│   │   │       ├── POST /api/transaction/validate  # Pre-validation
│   │   │       ├── GET /api/transaction/:id        # Transaction details
│   │   │       └── POST /api/transaction/dispute   # Dispute handling
│   │   │
│   │   ├── 🔧 Business Services (/services/)
│   │   │   ├── risk.service.ts       # 🧠 Core risk assessment logic
│   │   │   │   ├── scoreDQNTransaction()     # DQN model integration
│   │   │   │   ├── calculateOriginalRisk()   # Heuristic scoring
│   │   │   │   ├── extractDQNFeatures()      # Feature engineering
│   │   │   │   └── applyBusinessRules()      # Business logic layer
│   │   │   │
│   │   │   ├── kyc.service.ts        # 📋 Identity verification
│   │   │   │   ├── verifyDocuments()         # Document processing
│   │   │   │   ├── checkComplianceStatus()   # Regulatory compliance
│   │   │   │   └── updateVerificationStatus() # Status management
│   │   │   │
│   │   │   └── blockchain.service.ts # ⛓️ Smart contract interaction
│   │   │       ├── submitRiskScore()         # Oracle score submission
│   │   │       ├── getTransactionStatus()    # Contract state queries
│   │   │       └── monitorContractEvents()   # Event listening
│   │   │
│   │   ├── 🗄️ Database Layer (/db/)
│   │   │   ├── models.ts             # 📊 MongoDB schemas & models
│   │   │   │   ├── UserModel              # User profiles and KYC
│   │   │   │   ├── TransactionModel       # Transaction records
│   │   │   │   ├── RiskScoreModel         # Risk assessment history
│   │   │   │   └── PolicyModel           # Policy configurations
│   │   │   │
│   │   │   └── connection.ts         # 🔌 Database connection management
│   │   │       ├── MongoDB connection setup
│   │   │       ├── Connection pooling
│   │   │       └── Error handling
│   │   │
│   │   ├── 🛡️ Middleware (/middleware/)
│   │   │   ├── auth.ts               # 🔐 Authentication middleware
│   │   │   │   ├── JWT token validation
│   │   │   │   ├── API key verification
│   │   │   │   └── Role-based access control
│   │   │   │
│   │   │   └── validation.ts         # ✅ Request validation
│   │   │       ├── Input sanitization
│   │   │       ├── Schema validation
│   │   │       └── Rate limiting
│   │   │
│   │   ├── app.ts                    # 🚀 Express application setup
│   │   │   ├── Middleware configuration
│   │   │   ├── Route registration
│   │   │   ├── Error handling
│   │   │   └── CORS configuration
│   │   │
│   │   └── server.ts                 # 🌐 Server entry point
│   │       ├── HTTP server startup
│   │       ├── Database initialization
│   │       ├── Environment configuration
│   │       └── Graceful shutdown handling
│   │
│   ├── 📋 Configuration
│   │   ├── package.json              # Backend dependencies
│   │   ├── Dockerfile               # Container configuration
│   │   └── .env.example             # Environment template
│   │
│   └── 📚 Documentation
│       ├── API.md                   # API documentation
│       └── DEPLOYMENT.md            # Deployment instructions
│
└── 🔧 Configuration (/config/)
    └── database.json                # Database connection settings
```

---

## 🤖 Machine Learning Directory (`/cloud-training/`)

```
cloud-training/
├── 📓 Training Notebooks
│   ├── AMTTP_DQN_Colab_Training.ipynb    # 🧠 Main DQN training notebook
│   │   ├── Data preprocessing pipeline
│   │   ├── Feature engineering (15 features)
│   │   ├── DQN model architecture definition
│   │   ├── Training loop with experience replay
│   │   ├── Performance evaluation (F1=0.669)
│   │   └── Model export and optimization
│   │
│   └── notebooks/                        # 📁 Additional research notebooks
│       ├── data_exploration.ipynb        # Dataset analysis
│       ├── feature_analysis.ipynb        # Feature importance studies
│       └── model_comparison.ipynb        # Algorithm comparison
│
├── 🏗️ Training Infrastructure
│   ├── dqn_training_environment.py       # 🏋️ Training environment setup
│   │   ├── Reinforcement learning environment
│   │   ├── Reward function definition
│   │   ├── State space configuration
│   │   └── Action space definition
│   │
│   ├── rl_implementation.py             # 🎯 Core RL algorithms
│   │   ├── DQN agent implementation
│   │   ├── Experience replay buffer
│   │   ├── Target network updates
│   │   └── Epsilon-greedy exploration
│   │
│   └── sota_risk_engine.py              # 🏆 State-of-the-art engine
│       ├── Advanced feature engineering
│       ├── Ensemble model integration
│       ├── Real-time inference optimization
│       └── Production deployment utilities
│
├── 🎯 Trained Models (/models/)
│   ├── dqn_fraud_detection.h5           # 🧠 Main DQN model (F1=0.669)
│   ├── scaler.pkl                       # 📊 Feature normalization scaler
│   ├── feature_columns.json             # 📋 Feature configuration
│   ├── model_metadata.json              # 📄 Model versioning info
│   └── backup_models/                   # 🔄 Previous model versions
│       ├── dqn_v1.h5                    # Earlier training iterations
│       └── baseline_model.h5            # Baseline comparison model
│
├── 📊 Training Data (/data/)
│   ├── prepared_fraud_features.npy      # 🔢 Training features (28,457)
│   ├── prepared_fraud_labels.npy        # 🎯 Training labels
│   ├── validation_set.npy               # ✅ Validation data (20%)
│   ├── test_set.npy                     # 🧪 Test data (20%)
│   ├── raw_data/                        # 📄 Original datasets
│   │   ├── credit_card_fraud.csv        # Source fraud data
│   │   └── synthetic_transactions.csv   # Generated samples
│   └── processed_data/                  # 🔄 Intermediate processing
│       ├── feature_engineered.npy       # Post-engineering features
│       └── normalized_data.npy          # Normalized datasets
│
├── ⚙️ Configuration (/config/)
│   ├── remote_training_config.json      # 🏭 Training hyperparameters
│   │   ├── Learning rate schedules
│   │   ├── Batch size configurations
│   │   ├── Network architecture params
│   │   └── Training iteration settings
│   │
│   ├── model_architecture.json          # 🏗️ DQN architecture
│   │   ├── Layer definitions
│   │   ├── Activation functions
│   │   ├── Regularization parameters
│   │   └── Output configurations
│   │
│   └── production_config.json           # 🚀 Production settings
│       ├── Inference optimization
│       ├── Batch processing configs
│       ├── Memory management
│       └── Performance thresholds
│
├── 🚀 Deployment Scripts (/deployment/)
│   ├── deploy_dqn.py                    # 🌐 Model deployment automation
│   │   ├── Model validation and testing
│   │   ├── Production environment setup
│   │   ├── API endpoint configuration
│   │   └── Health check implementation
│   │
│   ├── integration_service.py           # 🔗 Backend integration
│   │   ├── API endpoint creation
│   │   ├── Request/response handling
│   │   ├── Error handling and logging
│   │   └── Performance monitoring
│   │
│   └── production_integration.py        # 🏭 Production integration
│       ├── Load balancing configuration
│       ├── Scaling policies
│       ├── Monitoring setup
│       └── Backup procedures
│
├── 📊 Monitoring & Logging (/monitoring/)
│   ├── training_logs/                   # 📈 Training progress logs
│   │   ├── loss_curves.json             # Training/validation loss
│   │   ├── accuracy_metrics.json        # Performance metrics
│   │   └── hyperparameter_tuning.json   # Parameter optimization
│   │
│   ├── performance_metrics.json         # 📊 Model performance tracking
│   │   ├── F1 scores over time
│   │   ├── Precision/recall curves
│   │   ├── ROC curves and AUC
│   │   └── Confusion matrices
│   │
│   └── validation_results.json          # ✅ Validation outcomes
│       ├── Cross-validation results
│       ├── A/B testing comparisons
│       ├── Production performance
│       └── Drift detection metrics
│
├── 🔄 Data Processing Scripts
│   ├── prepare_colab_upload.py          # 📤 Colab data preparation
│   ├── real_data_integration.py         # 🔗 Real data integration
│   ├── check_results.py                 # ✅ Result validation
│   └── data_pipeline.py                 # 🔄 Data processing automation
│
├── 🛠️ Utility Scripts
│   ├── quick_setup.py                   # ⚡ Quick environment setup
│   ├── setup_remote_environment.py      # 🌐 Remote training setup
│   ├── resume_dqn_training.py           # 🔄 Training resumption
│   └── test_dqn_environment.py          # 🧪 Environment testing
│
├── 📋 Documentation & Guides
│   ├── DQN_README.md                    # 🧠 DQN-specific documentation
│   ├── SOTA_DEPLOYMENT_GUIDE.md         # 🏆 Production deployment guide
│   ├── TECHNICAL_ARCHITECTURE.py        # 🏗️ Architecture documentation
│   ├── colab_quick_start.md             # ⚡ Google Colab quick start
│   └── colab_upload_instructions.md     # 📤 Colab data upload guide
│
└── 🔧 Build & Setup Files
    ├── requirements_dqn.txt              # 📋 Python dependencies
    ├── quick_setup_dqn.ps1              # 🪟 Windows setup script
    ├── setup_complete_environment.ps1    # 🔧 Complete environment setup
    ├── start_dqn.bat                     # 🚀 Windows batch startup
    └── start_dqn.ps1                     # 🪟 PowerShell startup script
```

---

## 📦 Client SDK Directory (`/packages/client-sdk/`)

```
packages/client-sdk/
├── 📁 Source Code (/src/)
│   ├── AMTTPClient.ts                   # 🎯 Main SDK client class
│   │   ├── Core transaction methods (secureTransfer, etc.)
│   │   ├── Risk assessment integration
│   │   ├── Policy management functions
│   │   ├── Atomic swap capabilities
│   │   └── Event monitoring and callbacks
│   │
│   ├── 📋 Type Definitions (/types/)
│   │   ├── index.ts                     # 📄 Main type exports
│   │   ├── contracts.ts                 # 🔗 Smart contract interfaces
│   │   ├── api.ts                       # 🌐 API response types
│   │   ├── transactions.ts              # 💸 Transaction types
│   │   └── policies.ts                  # 🎛️ Policy configuration types
│   │
│   ├── 🔧 Utilities (/utils/)
│   │   ├── validation.ts                # ✅ Input validation functions
│   │   ├── formatting.ts                # 🎨 Data formatting helpers
│   │   ├── encryption.ts                # 🔐 Encryption/decryption utilities
│   │   ├── constants.ts                 # 📋 SDK constants and configs
│   │   └── helpers.ts                   # 🛠️ General helper functions
│   │
│   ├── 🔧 Services (/services/)
│   │   ├── RiskService.ts               # 🎯 Risk assessment integration
│   │   │   ├── DQN risk scoring interface
│   │   │   ├── Heuristic risk calculation
│   │   │   ├── Risk threshold management
│   │   │   └── Real-time risk monitoring
│   │   │
│   │   ├── PolicyService.ts             # 🎛️ Policy management service
│   │   │   ├── User policy configuration
│   │   │   ├── Policy validation logic
│   │   │   ├── Compliance rule management
│   │   │   └── Policy engine integration
│   │   │
│   │   ├── TransactionService.ts        # 💸 Transaction handling service
│   │   │   ├── Transaction lifecycle management
│   │   │   ├── Status monitoring
│   │   │   ├── Escrow handling
│   │   │   └── Transaction history
│   │   │
│   │   └── ContractService.ts           # ⛓️ Smart contract interface
│   │       ├── Contract interaction methods
│   │       ├── Event listening and parsing
│   │       ├── Gas estimation utilities
│   │       └── Transaction confirmation
│   │
│   └── index.ts                         # 📦 Public API exports
│
├── 🏗️ Built Distribution (/dist/)
│   ├── index.js                         # 📦 Compiled main entry (257KB)
│   ├── index.d.ts                       # 📋 TypeScript declarations
│   ├── AMTTPClient.js                   # 🎯 Compiled client class
│   ├── services/                        # 🔧 Compiled services
│   ├── types/                           # 📋 Compiled type definitions
│   └── utils/                           # 🔧 Compiled utilities
│
├── 📚 Documentation (/docs/)
│   ├── API.md                           # 📖 Complete API reference
│   ├── EXAMPLES.md                      # 💡 Usage examples
│   ├── INTEGRATION.md                   # 🔗 Integration guide
│   ├── MIGRATION.md                     # 🔄 Migration guide
│   └── TROUBLESHOOTING.md               # 🔧 Common issues and solutions
│
├── 🧪 Tests (/tests/)
│   ├── AMTTPClient.test.ts              # 🧪 Main client tests
│   ├── services/                        # 🔧 Service-specific tests
│   ├── utils/                           # 🛠️ Utility function tests
│   └── integration/                     # 🔗 End-to-end integration tests
│
├── 📋 Configuration
│   ├── package.json                     # 📦 SDK dependencies and metadata
│   ├── tsconfig.json                    # 🔧 TypeScript configuration
│   ├── rollup.config.js                 # 📦 Bundle configuration
│   ├── jest.config.js                   # 🧪 Testing configuration
│   └── .npmignore                       # 📦 NPM publish exclusions
│
└── README.md                            # 📖 SDK usage documentation
```

---

## 🧪 Testing Directory (`/test/`)

```
test/
├── 🏗️ Modular Architecture Tests
│   ├── AMTTPModular.test.cjs            # 🧪 Main modular architecture tests
│   │   ├── Contract deployment validation (8/8 passing ✅)
│   │   ├── Contract size verification (under 24,576 bytes)
│   │   ├── Transaction lifecycle testing
│   │   ├── Risk-based processing validation
│   │   ├── Policy management testing
│   │   └── Integration flow verification
│   │
│   └── AMTTPModular.test.mjs            # 📄 ES Module version (legacy)
│
├── 🎛️ Policy Engine Tests
│   ├── AMTTPPolicyEngine.test.mjs       # 🔧 Comprehensive policy testing
│   │   ├── Advanced policy creation
│   │   ├── Complex validation scenarios
│   │   ├── Compliance rule testing
│   │   ├── Multi-signature workflows
│   │   └── Enterprise feature validation
│   │
│   └── policy-scenarios/                # 📁 Policy testing scenarios
│       ├── risk_thresholds.json         # Risk-based test cases
│       ├── user_limits.json             # User limit scenarios
│       └── compliance_rules.json        # Regulatory testing
│
├── 🎯 Core Functionality Tests
│   ├── AMTTP1.test.mjs                  # 🧪 Core AMTTP functionality
│   │   ├── ERC20 token functionality
│   │   ├── Secure transfer mechanisms
│   │   ├── Oracle integration
│   │   ├── Risk score processing
│   │   └── Event emission validation
│   │
│   └── AMTTP.test.doc                   # 📄 Legacy test documentation
│
├── 📊 Test Data & Fixtures (/fixtures/)
│   ├── sample_transactions.json         # 💸 Test transaction data
│   │   ├── Low risk scenarios
│   │   ├── Medium risk scenarios
│   │   ├── High risk scenarios
│   │   └── Edge cases
│   │
│   ├── policy_configurations.json       # 🎛️ Test policy setups
│   │   ├── Basic user policies
│   │   ├── Enterprise policies
│   │   ├── Compliance configurations
│   │   └── Edge case policies
│   │
│   ├── risk_scenarios.json              # 🎯 Risk testing scenarios
│   │   ├── DQN model test cases
│   │   ├── Heuristic test cases
│   │   ├── Hybrid scoring tests
│   │   └── Performance benchmarks
│   │
│   └── user_profiles.json               # 👤 Test user configurations
│       ├── Verified users
│       ├── Unverified users
│       ├── Trusted users
│       └── Blocked users
│
├── 🔧 Utility Test Files
│   ├── test-helpers.js                  # 🛠️ Common testing utilities
│   ├── mock-data.js                     # 📊 Mock data generators
│   ├── contract-helpers.js              # ⛓️ Smart contract test utilities
│   └── api-helpers.js                   # 🌐 API testing utilities
│
└── 📋 Test Configuration
    ├── mocha.opts                       # ⚙️ Mocha test configuration
    ├── coverage.json                    # 📊 Code coverage settings
    └── test-results/                    # 📈 Test execution results
        ├── coverage-reports/            # 📊 Coverage analysis
        ├── performance-results/         # ⚡ Performance benchmarks
        └── integration-logs/            # 🔗 Integration test logs
```

---

## 🚀 Deployment Scripts Directory (`/scripts/`)

```
scripts/
├── 🏗️ Modular Deployment
│   ├── deploy-modular.cjs               # 🚀 Main modular deployment script
│   │   ├── Deploy AMTTPPolicyManager (4% size limit)
│   │   ├── Deploy AMTTPStreamlined (9% size limit)
│   │   ├── Deploy AMTTPPolicyEngine (10.4% size limit)
│   │   ├── Connect contract interfaces
│   │   ├── Verify deployments and test functionality
│   │   └── Save deployment configuration
│   │
│   └── deploy-modular.js                # 📄 ES Module version (legacy)
│
├── 🎛️ Component Deployment
│   ├── deploy-policy-engine.js          # 🔧 Policy engine specific deployment
│   │   ├── Advanced policy configuration
│   │   ├── Enterprise feature setup
│   │   ├── Compliance rule initialization
│   │   └── Integration testing
│   │
│   └── deploy-streamlined.js            # 🎯 Core AMTTP deployment
│       ├── Basic token functionality
│       ├── Oracle integration setup
│       ├── Risk scoring configuration
│       └── Basic policy integration
│
├── 🔧 Utility Scripts
│   ├── initiate.mjs                     # 🚀 Project initialization
│   │   ├── Environment setup validation
│   │   ├── Dependency installation
│   │   ├── Configuration file creation
│   │   └── Database initialization
│   │
│   ├── alligned.js                      # 🔄 Contract alignment utilities
│   │   ├── ABI alignment verification
│   │   ├── Interface compatibility checks
│   │   ├── Version synchronization
│   │   └── Integration validation
│   │
│   └── vault-init.sh                    # 🔐 Security vault initialization
│       ├── Key generation and storage
│       ├── Access control setup
│       ├── Encryption configuration
│       └── Security policy enforcement
│
├── 📊 Verification & Testing
│   ├── verify-contracts.js              # ✅ Contract verification automation
│   │   ├── Source code verification on Etherscan
│   │   ├── ABI validation
│   │   ├── Deployment confirmation
│   │   └── Integration testing
│   │
│   └── test-deployment.js               # 🧪 Deployment testing script
│       ├── End-to-end functionality testing
│       ├── Performance validation
│       ├── Security verification
│       └── Rollback procedures
│
├── 📋 Configuration & Documentation
│   ├── deployment-config.json           # ⚙️ Deployment configuration template
│   ├── network-configs.json             # 🌐 Network-specific settings
│   ├── gas-optimization.js              # ⛽ Gas optimization utilities
│   └── deployment-logs/                 # 📊 Deployment history
│       ├── mainnet-deployments.json     # 🌐 Mainnet deployment records
│       ├── testnet-deployments.json     # 🧪 Testnet deployment records
│       └── local-deployments.json       # 🏠 Local deployment records
│
└── 📄 Legacy Scripts
    ├── 1deploy.doc                      # 📄 Original deployment documentation
    ├── 1deploy1.doc                     # 📄 Updated deployment notes
    └── tempDeploy.doc                   # 📄 Temporary deployment notes
```

---

## 📊 Data Management Directory (`/data/`)

```
data/
├── 🗄️ Database Storage (/mongo/)
│   ├── transactions/                    # 💸 Transaction records collection
│   │   ├── Raw transaction data
│   │   ├── Risk score associations
│   │   ├── Status tracking
│   │   └── Audit trail information
│   │
│   ├── users/                           # 👤 User profiles and KYC data
│   │   ├── Account information
│   │   ├── KYC verification status
│   │   ├── User policy configurations
│   │   └── Activity history
│   │
│   ├── risk_scores/                     # 🎯 Risk assessment history
│   │   ├── DQN model predictions
│   │   ├── Heuristic risk scores
│   │   ├── Hybrid scoring results
│   │   └── Performance metrics
│   │
│   └── policies/                        # 🎛️ Policy configurations
│       ├── User-specific policies
│       ├── Global policy settings
│       ├── Compliance rules
│       └── Policy change history
│
├── 📁 Object Storage (/minio/)
│   ├── documents/                       # 📄 KYC documents and files
│   │   ├── Identity documents
│   │   ├── Address verification
│   │   ├── Financial statements
│   │   └── Compliance documentation
│   │
│   ├── models/                          # 🧠 ML model artifacts
│   │   ├── Trained DQN models
│   │   ├── Feature scalers
│   │   ├── Model metadata
│   │   └── Version history
│   │
│   ├── reports/                         # 📊 Generated reports
│   │   ├── Risk assessment reports
│   │   ├── Compliance reports
│   │   ├── Performance analytics
│   │   └── Audit reports
│   │
│   └── backups/                         # 💾 Data backups
│       ├── Database snapshots
│       ├── Configuration backups
│       ├── Model checkpoints
│       └── Document archives
│
└── 🌐 Distributed Storage (/helia/)
    ├── transaction_logs/                # 📊 Immutable transaction logs
    │   ├── Blockchain transaction hashes
    │   ├── Off-chain transaction details
    │   ├── Risk scoring decisions
    │   └── Policy enforcement records
    │
    ├── compliance_records/              # 📋 Regulatory compliance data
    │   ├── AML compliance reports
    │   ├── KYC verification records
    │   ├── Regulatory submissions
    │   └── Audit trail documentation
    │
    ├── model_versions/                  # 🧠 ML model version control
    │   ├── Model training history
    │   ├── Performance benchmarks
    │   ├── A/B testing results
    │   └── Deployment records
    │
    └── system_logs/                     # 🔧 System operation logs
        ├── API access logs
        ├── Smart contract events
        ├── Error logs and debugging
        └── Performance monitoring data
```

---

## 🎨 Frontend Directory (`/frontend/`)

```
frontend/
├── 🌐 Main Application (/frontend/)
│   ├── 📁 Source Code (/src/)
│   │   ├── 📱 Components (/components/)
│   │   │   ├── Dashboard/               # 📊 Main dashboard components
│   │   │   ├── Transactions/            # 💸 Transaction management UI
│   │   │   ├── Risk/                    # 🎯 Risk assessment display
│   │   │   ├── Policies/                # 🎛️ Policy management interface
│   │   │   └── Common/                  # 🔧 Shared UI components
│   │   │
│   │   ├── 📄 Pages (/pages/)
│   │   │   ├── Home.tsx                 # 🏠 Landing page
│   │   │   ├── Dashboard.tsx            # 📊 Main user dashboard
│   │   │   ├── Transactions.tsx         # 💸 Transaction history
│   │   │   ├── Risk.tsx                 # 🎯 Risk management
│   │   │   └── Settings.tsx             # ⚙️ User settings
│   │   │
│   │   ├── 🔧 Services (/services/)
│   │   │   ├── api.ts                   # 🌐 API integration
│   │   │   ├── blockchain.ts            # ⛓️ Blockchain interactions
│   │   │   ├── risk.ts                  # 🎯 Risk assessment
│   │   │   └── auth.ts                  # 🔐 Authentication
│   │   │
│   │   ├── 🎨 Styles (/styles/)
│   │   │   ├── global.css               # 🌐 Global styles
│   │   │   ├── components.css           # 📱 Component styles
│   │   │   └── themes.css               # 🎨 Theme configurations
│   │   │
│   │   └── 🔧 Utils (/utils/)
│   │       ├── formatters.ts            # 🎨 Data formatting
│   │       ├── validation.ts            # ✅ Input validation
│   │       └── constants.ts             # 📋 Application constants
│   │
│   ├── 🏗️ Build Output (/dist/)
│   │   ├── Static assets
│   │   ├── Compiled JavaScript
│   │   ├── CSS bundles
│   │   └── HTML templates
│   │
│   ├── 🧪 Tests (/tests/)
│   │   ├── Component tests
│   │   ├── Integration tests
│   │   ├── E2E tests
│   │   └── Performance tests
│   │
│   └── 📋 Configuration
│       ├── package.json                 # Frontend dependencies
│       ├── tsconfig.json                # TypeScript configuration
│       ├── webpack.config.js            # Build configuration
│       └── .env.example                 # Environment template
│
└── 📚 Documentation
    ├── SETUP.md                         # Frontend setup guide
    ├── COMPONENTS.md                    # Component documentation
    └── DEPLOYMENT.md                    # Frontend deployment guide
```

---

## 📁 Build Artifacts & Development Tools

```
Build Artifacts:
├── 🏗️ /artifacts/                      # Hardhat compilation artifacts
│   ├── @openzeppelin/                  # OpenZeppelin contract artifacts
│   ├── contracts/                      # Compiled contract ABIs and bytecode
│   └── build-info/                     # Compilation metadata
│
├── 💾 /cache/                          # Development cache files
│   ├── solidity-files-cache.json       # Solidity compilation cache
│   ├── console-history.txt             # Hardhat console history
│   └── validations.json                # Validation cache
│
└── 📦 /node_modules/                   # NPM dependencies

Development Tools:
├── 🔧 /hardhat/                        # Hardhat development environment
│   └── Dockerfile                      # Hardhat container configuration
│
├── 🔄 /.github/                        # GitHub Actions CI/CD
│   ├── workflows/                      # Automated testing and deployment
│   ├── ISSUE_TEMPLATE.md               # Issue templates
│   └── PULL_REQUEST_TEMPLATE.md        # PR templates
│
└── 🌐 /.venv/                          # Python virtual environment
    ├── Python ML dependencies
    ├── Training environment packages
    └── Development utilities
```

---

## 🔗 File Relationships & Dependencies

### Smart Contract Dependencies
```
AMTTPStreamlined.sol
├── Depends on: AMTTPPolicyManager.sol (via interface)
├── Uses: OpenZeppelin upgradeable contracts
└── Integrates with: Oracle service for risk scores

AMTTPPolicyManager.sol  
├── Connects to: AMTTPPolicyEngine.sol (optional)
├── Used by: AMTTPStreamlined.sol
└── Manages: User policies and risk validation

AMTTPPolicyEngine.sol
├── Connected via: AMTTPPolicyManager.sol
├── Provides: Advanced policy features
└── Supports: Enterprise compliance requirements
```

### Backend Service Dependencies
```
Oracle Service
├── Integrates with: Smart contracts (risk score submission)
├── Uses: DQN model (cloud-training/models/)
├── Connects to: MongoDB (data/) and MinIO (data/)
└── Serves: Client SDK and frontend applications

DQN Model
├── Trained on: prepared_fraud_features.npy (28,457 samples)
├── Deployed via: deploy_dqn.py
├── Integrated in: risk.service.ts
└── Provides: Real-time fraud detection (F1=0.669)
```

### Client SDK Dependencies
```
AMTTP Client SDK
├── Connects to: Smart contracts (AMTTPStreamlined, PolicyManager)
├── Integrates with: Backend API (risk scoring, KYC)
├── Uses: ethers.js for blockchain interaction
└── Provides: Simplified dApp integration (257KB bundle)
```

---

This comprehensive file index documents the complete AMTTP project structure, showing how each component contributes to the overall fraud detection and prevention protocol. The modular architecture successfully solves the smart contract size limitations while maintaining full functionality across all layers of the system.