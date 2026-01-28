# AMTTP Developer Quick Reference

## 🚀 Quick Start Commands

### Development Setup
```bash
# Clone and setup
cd c:\amttp
npm install

# Start development environment
docker-compose up -d                    # Start MongoDB, MinIO, IPFS
npm run dev                             # Start backend development server
npx hardhat node                        # Start local blockchain

# Run tests
npx hardhat test                        # All smart contract tests
npx hardhat test test/AMTTPModular.test.cjs  # Modular architecture tests
npm run test:backend                    # Backend API tests
```

### Deployment Commands
```bash
# Deploy to local network
npx hardhat run scripts/deploy-modular.cjs --network localhost

# Deploy to testnet
npx hardhat run scripts/deploy-modular.cjs --network goerli

# Verify contracts
npx hardhat verify --network goerli CONTRACT_ADDRESS
```

## 📋 Key File Locations

### Smart Contracts
```
contracts/AMTTPStreamlined.sol     # Main AMTTP token (9% size limit)
contracts/AMTTPPolicyManager.sol   # Policy coordination (4% size limit)  
contracts/AMTTPPolicyEngine.sol    # Advanced policies (10.4% size limit)
```

### Backend API
```
backend/oracle-service/src/routes/risk.ts        # DQN risk scoring endpoints
backend/oracle-service/src/services/risk.service.ts  # Risk assessment logic
backend/oracle-service/src/db/models.ts         # Database schemas
```

### Machine Learning
```
ml/Automation/risk_engine/integration_service.py  # FastAPI risk engine (/health, /score)
ml/Automation/risk_engine/train_baseline.py       # Baseline sklearn trainer (joblib + meta)
ml/Automation/models/cloud/                       # Persisted models (baseline_model.joblib, *_meta.json)
```

### Client SDK
```
packages/client-sdk/src/AMTTPClient.ts           # Main SDK class
packages/client-sdk/src/services/RiskService.ts # Risk assessment integration
packages/client-sdk/dist/                       # Compiled SDK (257KB)
```

## 🔧 API Endpoints

### Risk Scoring
```typescript
// DQN-enhanced fraud detection
POST /api/risk/dqn-score
{
  "transaction": {
    "amount": 1000,
    "from": "0x123...",
    "to": "0x456...",
    "timestamp": 1695398400
  }
}
// Response: { "riskScore": 0.342, "confidence": 0.89, "recommendation": "approve" }

// Original heuristic scoring  
POST /api/risk/score
// Retrieve risk score
GET /api/risk/score/:txId
```

### KYC Verification
```typescript
// Submit KYC documents
POST /api/kyc/verify
// Check verification status
GET /api/kyc/status/:address
```

### Transaction Management
```typescript
// Pre-transaction validation
POST /api/transaction/validate
// Transaction details
GET /api/transaction/:id
```

## 📦 SDK Usage Examples

### Basic Transfer
```typescript
import { AMTTPClient } from '@amttp/client-sdk';

const client = new AMTTPClient({
  rpcUrl: 'https://ethereum-rpc.com',
  contractAddress: '0x123...',
  apiBaseUrl: 'https://api.amttp.com'
});

// Secure transfer with fraud protection
const result = await client.secureTransfer({
  to: '0x456...',
  amount: ethers.parseEther('100'),
  metadata: { purpose: 'payment' }
});

console.log(`Transaction ${result.txId} - Risk: ${result.riskScore}`);
```

### Risk Assessment
```typescript
// Check transaction risk before sending
const riskAssessment = await client.checkTransactionRisk({
  from: '0x123...',
  to: '0x456...',
  amount: ethers.parseEther('1000')
});

if (riskAssessment.riskLevel === 'high') {
  console.log('High risk transaction - manual review required');
}
```

### Policy Management
```typescript
// Set user policy
await client.setUserPolicy({
  maxAmount: ethers.parseEther('5000'),
  riskThreshold: 700, // 70%
  dailyLimit: ethers.parseEther('10000')
});

// Check if transfer is allowed
const canTransfer = await client.canTransfer({
  from: '0x123...',
  to: '0x456...',
  amount: ethers.parseEther('500')
});
```

## 🧪 Testing Scenarios

### Contract Size Validation
```javascript
// Verify all contracts are under Ethereum 24,576 byte limit
it('Should have correct contract sizes', async function () {
  const amttpCode = await ethers.provider.getCode(amttp.address);
  const policyManagerCode = await ethers.provider.getCode(policyManager.address);
  
  expect(amttpCode.length / 2 - 1).to.be.lessThan(24576);  // 9% actual
  expect(policyManagerCode.length / 2 - 1).to.be.lessThan(24576);  // 4% actual
});
```

### Risk Level Testing
```javascript
// Test different risk scenarios
const scenarios = [
  { risk: 200, expected: 'approve' },    // Low risk (20%)
  { risk: 500, expected: 'monitor' },    // Medium risk (50%)  
  { risk: 750, expected: 'escrow' },     // High risk (75%)
  { risk: 850, expected: 'reject' }      // Very high risk (85%)
];
```

### Policy Enforcement Testing  
```javascript
// Test user limit enforcement
await policyManager.setUserPolicy(user.address, parseEther('100'), 500);
// This should fail due to amount limit
await expect(
  amttp.connect(user).secureTransfer(recipient.address, parseEther('200'), dataHash)
).to.be.revertedWith('Exceeds user limit');
```

## 🔍 Debugging & Monitoring

### Contract Events
```typescript
// Listen for transaction events
amttp.on('TransactionInitiated', (txId, from, to, amount) => {
  console.log(`New transaction: ${txId} - ${amount} tokens from ${from} to ${to}`);
});

amttp.on('TransactionApproved', (txId, riskScore) => {
  console.log(`Transaction ${txId} approved with risk score ${riskScore}`);
});

amttp.on('TransactionEscrowed', (txId, riskScore) => {
  console.log(`Transaction ${txId} escrowed for manual review - risk: ${riskScore}`);
});
```

### Database Queries
```javascript
// MongoDB queries for analysis
db.transactions.find({ riskScore: { $gte: 700 } });  // High risk transactions
db.users.find({ kycStatus: 'verified' });            // Verified users
db.risk_scores.aggregate([                           // Average risk by day
  { $group: { _id: '$date', avgRisk: { $avg: '$score' } } }
]);
```

### Performance Monitoring
```bash
# API performance
curl -w "@curl-format.txt" -s -o /dev/null http://localhost:3000/api/risk/dqn-score

# Smart contract gas usage
npx hardhat test --gas-reporter

# Database performance
mongostat --host localhost:27017
```

## 🛡️ Security Best Practices

### Authentication & Authorization

The platform uses a multi-tier RBAC (Role-Based Access Control) system:

```typescript
// Role Hierarchy
enum Role {
  R1_END_USER = 'R1_END_USER',           // Basic user - Focus Mode
  R2_END_USER_PEP = 'R2_END_USER_PEP',   // Enhanced monitoring - Focus Mode
  R3_INSTITUTION_OPS = 'R3_INSTITUTION_OPS',       // Ops team - War Room (View)
  R4_INSTITUTION_COMPLIANCE = 'R4_INSTITUTION_COMPLIANCE', // Compliance - War Room (Full)
  R5_PLATFORM_ADMIN = 'R5_PLATFORM_ADMIN',         // Platform admin
  R6_SUPER_ADMIN = 'R6_SUPER_ADMIN',               // Super admin
}

// Using auth context in components
import { useAuth } from '@/lib/auth-context';

function MyComponent() {
  const { role, capabilities, canEnforce, isInstitutional } = useAuth();
  
  if (capabilities?.canTriggerEnforcement) {
    // Show enforcement options
  }
}
```

### Authentication Methods

```typescript
// 1. Wallet-based login
import { connectWallet, isWalletConnected } from '@/lib/auth-service';

const result = await connectWallet();
if (result) {
  await login(result.address);
}

// 2. Email/password login
const response = await fetch('/api/auth/login', {
  method: 'POST',
  body: JSON.stringify({ email, password, authMethod: 'email' })
});

// 3. API endpoints
POST /api/auth/register  - User registration
POST /api/auth/login     - User authentication
POST /api/auth/logout    - Session invalidation
GET  /api/auth/me        - Current session info
```

### Role Management (Admin)

```typescript
import { useRoleManagement } from '@/lib/role-management-service';
import { canAssignRole, getAssignableRoles } from '@/types/role-management';

const { assignRole, createUser, suspendUser } = useRoleManagement(currentUserRole);

// Check if current user can assign a role
if (canAssignRole(Role.R6_SUPER_ADMIN, Role.R4_INSTITUTION_COMPLIANCE)) {
  await assignRole(userId, Role.R4_INSTITUTION_COMPLIANCE, institutionId, 'Promoted');
}

// Get roles the current user can assign
const assignable = getAssignableRoles(currentUserRole);
```

### Smart Contract Security
```solidity
// Always use reentrancy protection
modifier nonReentrant() {
    require(!_reentrancyGuard, "Reentrant call");
    _reentrancyGuard = true;
    _;
    _reentrancyGuard = false;
}

// Validate inputs
require(amount > 0, "Invalid amount");
require(to != address(0), "Invalid recipient");

// Use pull over push for external calls
mapping(address => uint256) public pendingWithdrawals;
```

### API Security
```typescript
// Rate limiting
const rateLimit = require('express-rate-limit');
app.use('/api/', rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // limit each IP to 100 requests per windowMs
}));

// Input validation
const { body, validationResult } = require('express-validator');
app.post('/api/risk/score', [
  body('amount').isNumeric().withMessage('Amount must be numeric'),
  body('from').isEthereumAddress().withMessage('Invalid from address')
], (req, res) => {
  const errors = validationResult(req);
  if (!errors.isEmpty()) {
    return res.status(400).json({ errors: errors.array() });
  }
});
```

## 📊 Performance Benchmarks

### Target Metrics
```
🎯 DQN Model Performance:
- F1 Score: ≥ 0.65 (achieved: 0.669)
- Inference Time: < 100ms (achieved: ~80ms)
- False Positive Rate: < 30% (achieved: 27.7%)

⚡ System Performance:
- API Response Time: < 200ms (achieved: ~150ms)
- Contract Gas Usage: < 200k per transfer (achieved: ~150k)
- Concurrent Users: > 500 (tested: 1,000+)

📦 Bundle Sizes:
- SDK Size: < 300KB (achieved: 257KB)
- Contract Size: < 24KB each (achieved: 9%, 4%, 10.4% of limit)
```

## 🚀 Production Checklist

### Pre-deployment
- [ ] All tests passing (8/8 ✅)
- [ ] Security audit completed
- [ ] Gas optimization verified
- [ ] Contract size limits confirmed
- [ ] API load testing completed
- [ ] Documentation updated

### Deployment
- [ ] Deploy to testnet first
- [ ] Verify contract source code
- [ ] Configure oracle endpoints
- [ ] Test end-to-end flow
- [ ] Set up monitoring
- [ ] Deploy to mainnet

### Post-deployment
- [ ] Monitor contract events
- [ ] Track API performance
- [ ] Verify ML model accuracy
- [ ] Set up alerting
- [ ] Prepare incident response
- [ ] Schedule regular audits