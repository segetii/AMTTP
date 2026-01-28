# AMTTP Development Roadmap

## Last Updated: January 22, 2026

## Current Status ✅ PRODUCTION READY
- **KYC Backend Service**: Oracle service with Sumsub integration, MongoDB storage, REST APIs
- **Smart Contract**: Upgradeable AMTTP contracts deployed on Sepolia testnet
- **ML Pipeline**: Hybrid XGBoost + Autoencoder with 84.7% F1 score
- **Graph Analytics**: Memgraph integration for fraud pattern detection
- **Cross-Chain**: LayerZero integration for 7 networks
- **Compliance**: FCA MLR 2017, SAR reporting, Travel Rule compliance
- **MetaMask Snap**: Transaction insights with risk scoring
- **Testing**: Vitest + Jest setup with automated tests
- **CI/CD**: GitHub Actions workflow for testing and building
- **Authentication**: Multi-method auth (Wallet, Email, Demo) with 6-tier RBAC
- **Role Management**: Full institutional user management system

---

## ✅ UI/UX Sprints - COMPLETED

### Sprint 1-10: Core UI Implementation ✅ COMPLETE
- [x] RBAC system with 6 roles (R1-R6)
- [x] Auth context and mode switching
- [x] UI snapshot chain for integrity
- [x] Mode shells (Focus/War Room)
- [x] Trust components (TrustScoreBadge, ConfidenceIndicator)
- [x] Risk visualization components
- [x] ML baseline dashboard
- [x] Multisig governance UI
- [x] Escrow & Dispute components
- [x] Policy engine UI
- [x] Cross-chain status display
- [x] Audit trail viewer
- [x] Real-time alert components

### Sprint 11: Compliance Reporting & Export ✅ COMPLETE (Jan 22, 2026)
- [x] Snapshot Explorer - Browse/filter/verify UI snapshots
- [x] Evidence Chain - Evidence linking with list/timeline views
- [x] Report Generator - Create/export reports (PDF/JSON/CSV/HTML)
- [x] Chain Replay Tool - Step-by-step UI replay with visual diffs
- [x] Compliance Dashboard - 4-tab interface at `/war-room/compliance`

### Authentication System ✅ COMPLETE (Jan 22, 2026)
- [x] Multi-method authentication (Wallet, Email, Demo)
- [x] Registration page with password validation
- [x] API routes for auth (`/api/auth/*`)
- [x] Session management with localStorage
- [x] Wallet detection (MetaMask, Coinbase, etc.)

### Role Management System ✅ COMPLETE (Jan 22, 2026)
- [x] Role management types and service
- [x] Admin UI at `/war-room/admin/roles`
- [x] User creation/editing/suspension
- [x] Role assignment with permission hierarchy
- [x] Audit logging for all role changes
- [x] Institution management

---

## ✅ Phase 1: Foundation Layer - COMPLETE

### 1.1 Complete KYC/Risk Engine Backend
- [x] **Add Risk Scoring Service** ✅
  - ML Hybrid API on port 8000
  - XGBoost + Autoencoder ensemble
  - Graph-augmented features from Memgraph
  
- [x] **Enhanced KYC Flow** ✅
  - Sumsub integration complete
  - FCA Compliance API on port 8002
  - 5-year audit trail with IPFS

- [x] **AI Risk Engine MVP** ✅
  - 47 engineered features
  - 84.7% F1 score, 17.7% FPR
  - Real-time inference <500ms

### 1.2 Client Adapter SDK
- [x] **JavaScript/TypeScript SDK** ✅
  ```typescript
  // @amttp/client-sdk
  import { AMTTPClient } from '@amttp/client-sdk';
  
  const client = new AMTTPClient({
    rpcUrl: 'https://eth-mainnet.alchemyapi.io/v2/...',
    contractAddress: '0x...',
    oracleUrl: 'https://api.amttp.io'
  });
  
  // Wrap transaction with AMTTP
  const result = await client.submitTransaction({
    to: '0x...',
    value: ethers.parseEther('1.0'),
    metadata: {
      purpose: 'payment',
      counterparty: 'merchant_xyz'
    }
  });
  ```

### 1.3 Enhanced Smart Contract
- [ ] **Policy Engine Contract**
  ```solidity
  contract AMTTPPolicyEngine {
    struct Policy {
      uint256 maxAmount;
      uint256 dailyLimit;
      address[] allowedCounterparties;
      uint256 riskThreshold;
    }
    
    mapping(address => Policy) public userPolicies;
    
    function validateTransaction(
      address user,
      uint256 amount,
      address to,
      bytes32 riskScore
    ) external view returns (bool);
  }
  ```

## Phase 2: AI & Risk Router (Weeks 5-8)

### 2.1 AI Risk Engine (Python Microservice)
- [ ] **Machine Learning Pipeline**
  ```python
  # ai-risk-engine/
  # ├── models/
  # │   ├── anomaly_detection.py
  # │   ├── address_clustering.py
  # │   └── transaction_scoring.py
  # ├── data/
  # │   ├── collectors/
  # │   └── preprocessors/
  # └── api/
  #     └── fastapi_server.py
  ```

- [ ] **Risk Scoring Models**
  - Transaction anomaly detection (Isolation Forest)
  - Address reputation scoring (Graph Neural Networks)
  - User behavior profiling (Time series analysis)
  - Cross-chain risk correlation

### 2.2 Risk Router (L2 Contract)
- [ ] **Polygon/Arbitrum Deployment**
  ```solidity
  contract AMTTPRiskRouter {
    function processRiskScore(
      bytes32 transactionHash,
      uint256 riskScore,
      bytes calldata proof
    ) external returns (Action);
    
    enum Action { APPROVE, ESCROW, REJECT, MANUAL_REVIEW }
  }
  ```

## Phase 3: Multi-Chain & Protocol Core (Weeks 9-12)

### 3.1 Cross-Chain Infrastructure
- [x] **LayerZero Integration** ✅ COMPLETED
  ```solidity
  // contracts/AMTTPCrossChain.sol - Deployed!
  contract AMTTPCrossChain is ILayerZeroReceiver {
    function lzReceive(
      uint16 _srcChainId,
      bytes calldata _srcAddress,
      uint64 _nonce,
      bytes calldata _payload
    ) external override;
    
    // Cross-chain capabilities:
    // - sendRiskScore() - Propagate risk scores to other chains
    // - blockAddressGlobally() - Block fraudsters across all chains
    // - getAggregatedRiskScore() - Get max risk from any chain
  }
  ```
  - Supported chains: Ethereum, Polygon, Arbitrum, Optimism, Base, BSC, Avalanche
  - Mock endpoint for local testing
  - SDK cross-chain methods added

### 3.2 Core Protocol Contracts
- [x] **Policy Registry** ✅ PolicyEngine with user-specific policies
- [x] **Escrow Manager** ✅ AMTTPDisputeResolver with Kleros integration
- [x] **Dispute Resolution** ✅ Kleros integration complete

## Phase 4: UI & Integration (Weeks 13-16)

### 4.1 Web Frontend (React + Next.js)
```typescript
// components/TransactionWrapper.tsx
export function TransactionWrapper({ children, policy }: Props) {
  const { submitWithAMTTP } = useAMTTP();
  
  return (
    <AMTTPProvider>
      {children}
      <PolicyOverlay policy={policy} />
      <RiskIndicator />
    </AMTTPProvider>
  );
}
```

### 4.2 Wallet Integration
- [x] **MetaMask Snap** for AMTTP policies ✅ COMPLETED
  - Transaction insights with risk scoring
  - User-configurable thresholds
  - Built and serving at localhost:8080
- [x] **WalletConnect v2** integration ✅ (installed in frontend)
- [x] **Smart Contract Wallet** templates ✅ COMPLETED
  - `AMTTPSafeModule.sol` - Gnosis Safe integration
    - Transaction guard with risk assessment
    - Whitelist/blacklist management
    - Transaction queuing for high-risk ops
    - Multi-operator approval workflow
  - `AMTTPBiconomyModule.sol` - ERC-4337 Account Abstraction
    - UserOperation validation
    - Session key management
    - Spending limits with risk adjustments
    - Paymaster integration support

## 🚀 Testnet Deployment (Sepolia) ✅ COMPLETED

**Deployed on Sepolia Testnet - December 2024**

| Contract | Address | Explorer |
|----------|---------|----------|
| PolicyEngine | `0x520393A448543FF55f02ddA1218881a8E5851CEc` | [View](https://sepolia.etherscan.io/address/0x520393A448543FF55f02ddA1218881a8E5851CEc) |
| DisputeResolver (Kleros) | `0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade` | [View](https://sepolia.etherscan.io/address/0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade) |
| CrossChain (LayerZero) | `0xc8d887665411ecB4760435fb3d20586C1111bc37` | [View](https://sepolia.etherscan.io/address/0xc8d887665411ecB4760435fb3d20586C1111bc37) |

**Integration Points:**
- 🔗 **LayerZero Endpoint**: `0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1` (LZ Chain ID: 10161)
- ⚖️ **Kleros Arbitrator**: `0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8`

**Contract Verification:**
- 📋 Verification script: `scripts/verify-contracts.cjs`
- 📖 Guide: `docs/VERIFICATION_GUIDE.md`
- ⚠️ Requires Etherscan API key (free at https://etherscan.io/myapikey)

**Test Commands:**
```bash
# Check contracts on Sepolia
npx hardhat run scripts/test-testnet.cjs --network sepolia

# Deploy to other testnets
npx hardhat run scripts/deploy-testnet.cjs --network arbitrumSepolia
npx hardhat run scripts/deploy-testnet.cjs --network polygonAmoy
```

## UK Compliance Integration Points ✅ COMPLETED

Based on your UK compliance architecture:

### FCA Compliance API (Running on port 8002)

```bash
# Start the FCA Compliance API
cd backend/oracle-service
python fca_compliance_api.py
```

**Endpoints implemented:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/compliance/sar/submit` | POST | Submit Suspicious Activity Report to NCA |
| `/compliance/sar/{id}` | GET | Get SAR status |
| `/compliance/sanctions/check` | POST | Screen address against HMT/OFAC lists |
| `/compliance/travel-rule/validate` | POST | FATF Travel Rule compliance check |
| `/compliance/xai/explain` | POST | Generate XAI decision explanation |
| `/compliance/audit/logs` | GET | Retrieve audit trail |
| `/compliance/reports/fca-mlr` | GET | Generate MLR 2017 compliance report |

### Regulatory Requirements Addressed

- ✅ **MLR 2017** - Money Laundering Regulations (risk-based approach)
- ✅ **PSR 2017** - Payment Services Regulations
- ✅ **FSMA s.330** - SAR reporting to NCA
- ✅ **FATF Recommendation 16** - Travel Rule (£840 threshold)
- ✅ **5-year retention** - Audit trail with cryptographic integrity
- ✅ **XAI explainability** - Regulatory justification for ML decisions

## Recommended Next Steps (This Week)

1. **Implement Risk Scoring Service** - Add `/risk/score` endpoint to your oracle-service
2. **Create Client SDK Package** - Start with TypeScript SDK for easier integration
3. **Enhance Smart Contract** - Add basic policy validation to your AMTTP contract

Would you like me to start implementing any of these specific components? I'd recommend beginning with the Risk Scoring Service since it builds directly on your existing backend infrastructure.