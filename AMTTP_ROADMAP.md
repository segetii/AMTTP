# AMTTP Development Roadmap

## Current Status ✅
- **KYC Backend Service**: Oracle service with Sumsub integration, MongoDB storage, REST APIs
- **Smart Contract**: Upgradeable AMTTP ERC721 contract deployed on local Hardhat
- **Testing**: Vitest setup with automated tests for KYC endpoints
- **CI/CD**: GitHub Actions workflow for testing and building

## Phase 1: Foundation Layer (Current → 4 weeks)

### 1.1 Complete KYC/Risk Engine Backend
- [ ] **Add Risk Scoring Service** 
  - Create `/risk/score` endpoint with ML model stub
  - Integrate with Chainalysis/TRM Labs APIs for address screening
  - Store risk scores in MongoDB with audit trail
  
- [ ] **Enhanced KYC Flow**
  - Add webhook support for Sumsub status updates
  - Implement KYC document verification pipeline
  - Add compliance reporting endpoints

- [ ] **AI Risk Engine MVP**
  ```typescript
  // Simple risk scoring based on:
  // - Transaction amount vs historical patterns
  // - Address reputation (Chainalysis)
  // - Velocity checks
  // - Geographic risk indicators
  ```

### 1.2 Client Adapter SDK
- [ ] **JavaScript/TypeScript SDK**
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
- [ ] **LayerZero Integration**
  ```solidity
  contract AMTTPCrossChain is ILayerZeroReceiver {
    function _lzReceive(
      uint16 _srcChainId,
      bytes memory _srcAddress,
      uint64 _nonce,
      bytes memory _payload
    ) internal override;
  }
  ```

### 3.2 Core Protocol Contracts
- [ ] **Policy Registry** (IPFS + On-chain pointers)
- [ ] **Escrow Manager** (Multi-signature + Timelock)
- [ ] **Dispute Resolution** (Initial integration with Kleros)

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
- [ ] **MetaMask Snap** for AMTTP policies
- [ ] **WalletConnect v2** integration
- [ ] **Smart Contract Wallet** templates (Safe, Biconomy)

## UK Compliance Integration Points

Based on your UK compliance architecture:

### FCA KYC Gateway
```typescript
// Integrate with your existing KYC service
interface FCACompliantKYC {
  performKYC(userId: string): Promise<KYCResult>;
  checkSanctions(address: string): Promise<SanctionsResult>;
  recordTravelRule(transaction: Transaction): Promise<void>;
}
```

### Regulatory Reporting
```typescript
// Add to your oracle-service
app.post('/compliance/report', async (req, res) => {
  // Generate FCA-compliant transaction reports
  // Include XAI explanations for AI decisions
  // Maintain audit trail for 5+ years
});
```

## Recommended Next Steps (This Week)

1. **Implement Risk Scoring Service** - Add `/risk/score` endpoint to your oracle-service
2. **Create Client SDK Package** - Start with TypeScript SDK for easier integration
3. **Enhance Smart Contract** - Add basic policy validation to your AMTTP contract

Would you like me to start implementing any of these specific components? I'd recommend beginning with the Risk Scoring Service since it builds directly on your existing backend infrastructure.