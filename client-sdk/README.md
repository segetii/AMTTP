# @amttp/client-sdk

A comprehensive TypeScript SDK for the AMTTP (Advanced Money Transfer Transaction Protocol) platform. This SDK provides full access to all AMTTP backend services including risk assessment, KYC verification, transaction processing, dispute resolution, and regulatory compliance features.

## Features

- 🔐 **Risk Assessment** - DQN-based ML risk scoring with real-time address analysis
- 📋 **KYC Verification** - Multi-tier KYC with document management
- 💸 **Transaction Management** - Full transaction lifecycle with policy enforcement
- ⚖️ **Dispute Resolution** - Kleros-integrated arbitration system
- 🏆 **Reputation System** - 5-tier reputation (Bronze → Diamond)
- 📦 **Bulk Operations** - Batch scoring up to 10,000 transactions
- 🔔 **Webhooks** - Real-time event notifications with HMAC-SHA256 signing
- 👤 **PEP Screening** - Multi-provider Politically Exposed Person checks
- 📝 **EDD Workflow** - Enhanced Due Diligence case management
- 👁️ **Ongoing Monitoring** - Continuous compliance monitoring
- 🏷️ **Address Labels** - Comprehensive address categorization
- 🛡️ **MEV Protection** - Flashbots integration for transaction privacy

## Installation

```bash
npm install @amttp/client-sdk
# or
yarn add @amttp/client-sdk
# or
pnpm add @amttp/client-sdk
```

## Quick Start

```typescript
import { AMTTPClient } from '@amttp/client-sdk';

// Initialize the client
const client = new AMTTPClient({
  baseUrl: 'https://api.amttp.io',
  apiKey: 'your-api-key',
  timeout: 30000,
  debug: true,
});

// Assess risk for an address
const risk = await client.risk.assess({
  address: '0x1234567890abcdef...',
  amount: '1000000000000000000', // 1 ETH in wei
});

console.log(`Risk Score: ${risk.riskScore}, Level: ${risk.riskLevel}`);
```

## Services

### Risk Service

Assess transaction and address risk using DQN-based ML models.

```typescript
// Single address assessment
const risk = await client.risk.assess({
  address: '0x...',
  transactionHash: '0x...',
  amount: '1000000000000000000',
  counterparty: '0x...',
});

// Batch assessment
const batch = await client.risk.batchAssess({
  addresses: ['0x...', '0x...', '0x...'],
  includeLabels: true,
  includeFactors: true,
});

// Get risk history
const history = await client.risk.getHistory('0x...', {
  limit: 100,
  startDate: new Date('2025-01-01'),
});

// Check threshold
const threshold = await client.risk.checkThreshold('0x...', 'medium');
if (!threshold.passed) {
  console.log(`Blocked: ${threshold.action}`);
}
```

### KYC Service

Manage Know Your Customer verification workflows.

```typescript
// Submit KYC
const kyc = await client.kyc.submit({
  address: '0x...',
  documentType: 'passport',
  documentNumber: 'AB123456',
  firstName: 'John',
  lastName: 'Doe',
  dateOfBirth: '1990-01-15',
  nationality: 'GB',
});

// Check KYC status
const status = await client.kyc.getStatus('0x...');
console.log(`KYC Level: ${status.level}, Status: ${status.status}`);

// Upload document
const doc = await client.kyc.uploadDocument('0x...', {
  type: 'document_front',
  contentHash: 'QmXxx...',
  mimeType: 'image/jpeg',
});

// Check expiry
const expiry = await client.kyc.checkExpiry('0x...');
if (expiry.isExpiring) {
  console.log(`KYC expires in ${expiry.daysRemaining} days`);
}
```

### Transaction Service

Process and manage transactions with policy enforcement.

```typescript
// Validate transaction before submission
const validation = await client.transactions.validate({
  from: '0x...',
  to: '0x...',
  amount: '1000000000000000000',
  chainId: 1,
});

if (!validation.valid) {
  console.log(`Transaction blocked: ${validation.policyResult.reason}`);
  return;
}

// Submit transaction
const tx = await client.transactions.submit({
  from: '0x...',
  to: '0x...',
  amount: '1000000000000000000',
  chainId: 1,
  memo: 'Payment for services',
});

// Get transaction history
const history = await client.transactions.getHistory({
  address: '0x...',
  status: 'completed',
  limit: 50,
  sortBy: 'createdAt',
  sortOrder: 'desc',
});

// Estimate cost
const estimate = await client.transactions.estimateCost({
  from: '0x...',
  to: '0x...',
  amount: '1000000000000000000',
  chainId: 1,
});
console.log(`Estimated cost: ${estimate.totalCostEth} ETH`);
```

### Policy Service

Manage and evaluate compliance policies.

```typescript
// Evaluate policies for a transaction
const result = await client.policy.evaluate({
  from: '0x...',
  to: '0x...',
  amount: '50000000000000000000000', // 50,000 ETH
  chainId: 1,
});

console.log(`Decision: ${result.decision}`);
console.log(`Applied policies: ${result.appliedPolicies.map(p => p.name).join(', ')}`);

// Create a new policy
const policy = await client.policy.create({
  name: 'High Value Transaction Review',
  description: 'Require approval for transactions over 10,000 USD',
  type: 'require_approval',
  conditions: [
    { field: 'amountUsd', operator: 'gt', value: 10000 },
  ],
  actions: [
    { type: 'require_approval', params: { approvers: 2 } },
  ],
  priority: 100,
});

// Test policy
const test = await client.policy.test(policy.id, {
  from: '0x...',
  to: '0x...',
  amount: '100000000000000000000000',
  chainId: 1,
});
console.log(`Would apply: ${test.wouldApply}`);
```

### Dispute Service

Handle disputes with Kleros arbitration integration.

```typescript
// Create a dispute
const dispute = await client.disputes.create({
  transactionId: 'tx-123',
  reason: 'Product not delivered',
  category: 'non_delivery',
  description: 'Paid for goods but never received them',
  evidence: [
    {
      type: 'communication',
      title: 'Chat logs',
      contentHash: 'QmXxx...',
    },
  ],
});

// Submit additional evidence
await client.disputes.submitEvidence(dispute.id, {
  type: 'screenshot',
  title: 'Order confirmation',
  contentHash: 'QmYyy...',
});

// Escalate to Kleros
const escalation = await client.disputes.escalateToKleros(dispute.id);
console.log(`Kleros Dispute ID: ${escalation.klerosDisputeId}`);
console.log(`Arbitration cost: ${escalation.arbitrationCost}`);

// Get dispute statistics
const stats = await client.disputes.getStatistics('0x...');
console.log(`Win rate: ${stats.winRate}%`);
```

### Reputation Service

Access the 5-tier reputation system (Bronze → Silver → Gold → Platinum → Diamond).

```typescript
// Get reputation profile
const profile = await client.reputation.getProfile('0x...');
console.log(`Tier: ${profile.tier}, Score: ${profile.score}`);

// Get progress to next tier
const progress = await client.reputation.getProgress('0x...');
console.log(`Progress to ${progress.nextTier}: ${progress.progress}%`);
console.log(`Missing: ${progress.missingRequirements.join(', ')}`);

// Get badges
const badges = await client.reputation.getBadges('0x...');
badges.forEach(b => console.log(`🏅 ${b.name}: ${b.description}`));

// Get leaderboard
const leaderboard = await client.reputation.getLeaderboard({
  tier: 'diamond',
  limit: 10,
});

// Calculate impact of potential transaction
const impact = await client.reputation.calculateImpact('0x...', {
  amount: '10000000000000000000',
  successful: true,
  counterpartyTier: 'gold',
});
console.log(`Score change: ${impact.scoreChange}`);
```

### Bulk Service

Process large batches of transactions efficiently.

```typescript
// Submit bulk scoring job
const job = await client.bulk.submit({
  transactions: [
    { id: '1', from: '0x...', to: '0x...', amount: '1000000000000000000' },
    { id: '2', from: '0x...', to: '0x...', amount: '2000000000000000000' },
    // ... up to 10,000 transactions
  ],
  options: {
    includeLabels: true,
    parallelism: 10,
  },
});

// Poll for status
let status = await client.bulk.getStatus(job.jobId);
while (status.status === 'processing') {
  console.log(`Progress: ${status.progress}%`);
  await new Promise(r => setTimeout(r, 5000));
  status = await client.bulk.getStatus(job.jobId);
}

// Get results
const results = await client.bulk.getResults(job.jobId);
console.log(`Processed: ${results.total}, High risk: ${
  results.results.filter(r => r.riskLevel === 'high').length
}`);

// Retry failed transactions
const retry = await client.bulk.retryFailed(job.jobId);
console.log(`Retrying ${retry.transactionsToRetry} failed transactions`);
```

### Webhook Service

Set up real-time event notifications.

```typescript
// Create a webhook
const webhook = await client.webhooks.create({
  url: 'https://your-server.com/webhooks/amttp',
  events: [
    'transaction.completed',
    'risk.high_score',
    'kyc.verified',
    'dispute.created',
    'pep.match',
  ],
  description: 'Production webhook',
});

// Store the secret securely
console.log(`Webhook secret: ${webhook.secret}`);

// Test the webhook
const test = await client.webhooks.test(webhook.id, 'transaction.completed');
console.log(`Test result: ${test.success ? 'OK' : test.error}`);

// Verify webhook signature (in your webhook handler)
app.post('/webhooks/amttp', (req, res) => {
  const signature = req.headers['x-amttp-signature'];
  const isValid = client.webhooks.verifySignature(
    JSON.stringify(req.body),
    signature,
    webhookSecret
  );
  
  if (!isValid) {
    return res.status(401).send('Invalid signature');
  }
  
  // Process webhook event
  const { event, data } = req.body;
  console.log(`Received ${event}:`, data);
  
  res.status(200).send('OK');
});
```

### PEP Screening Service

Screen addresses for Politically Exposed Persons.

```typescript
// Screen an address
const result = await client.pep.screen({
  address: '0x...',
  fullName: 'John Smith',
  dateOfBirth: '1970-05-15',
  nationality: 'US',
  includeRelatives: true,
  includeAssociates: true,
});

console.log(`Risk Level: ${result.riskLevel}`);
console.log(`Requires EDD: ${result.requiresEDD}`);

if (result.matches.length > 0) {
  result.matches.forEach(match => {
    console.log(`Match: ${match.name} (${match.matchScore}%)`);
    console.log(`Position: ${match.position}`);
    console.log(`Source: ${match.source}`);
  });
}

// Batch screen
const batch = await client.pep.batchScreen(['0x...', '0x...', '0x...']);
console.log(`Found ${batch.results.filter(r => r.matches.length > 0).length} with matches`);

// Acknowledge match after review
await client.pep.acknowledgeMatch('0x...', 'match-123', {
  approved: true,
  reason: 'False positive - different person',
  reviewedBy: 'compliance-officer@company.com',
});
```

### EDD Service

Manage Enhanced Due Diligence cases.

```typescript
// Create EDD case
const eddCase = await client.edd.create({
  address: '0x...',
  trigger: 'pep_match',
  triggerDetails: { matchId: 'match-123' },
  priority: 'high',
});

// Assign to reviewer
await client.edd.assign(eddCase.id, 'reviewer@company.com');

// Upload required documents
await client.edd.uploadDocument(eddCase.id, {
  type: 'source_of_funds',
  name: 'Bank statement Q4 2025',
  contentHash: 'QmXxx...',
  mimeType: 'application/pdf',
});

// Add internal note
await client.edd.addNote(eddCase.id, {
  content: 'Customer provided additional documentation via email',
  visibility: 'internal',
});

// Resolve case
await client.edd.resolve(eddCase.id, {
  decision: 'approved',
  reason: 'All documentation verified, source of funds legitimate',
  resolvedBy: 'compliance-manager@company.com',
});

// Get EDD statistics
const stats = await client.edd.getStatistics();
console.log(`Approval rate: ${stats.approvalRate}%`);
console.log(`Average resolution time: ${stats.averageResolutionTime} hours`);
```

### Monitoring Service

Set up continuous compliance monitoring.

```typescript
// Add address to monitoring
const monitored = await client.monitoring.addAddress('0x...', {
  tags: ['high-value', 'vip'],
  priority: 'high',
});

// Create custom monitoring rule
await client.monitoring.createRule({
  name: 'Large Transaction Alert',
  description: 'Alert when transaction exceeds $100k',
  type: 'threshold_breach',
  conditions: [
    { field: 'amountUsd', operator: 'gt', value: 100000 },
  ],
  severity: 'high',
  enabled: true,
});

// Get open alerts
const alerts = await client.monitoring.getAlerts({
  status: 'open',
  severity: 'high',
  limit: 50,
});

alerts.alerts.forEach(alert => {
  console.log(`⚠️ ${alert.title}`);
  console.log(`   Address: ${alert.address}`);
  console.log(`   Type: ${alert.type}`);
});

// Acknowledge and resolve alert
await client.monitoring.acknowledgeAlert(alertId, 'analyst@company.com');
await client.monitoring.resolveAlert(alertId, {
  resolvedBy: 'analyst@company.com',
  resolution: 'Confirmed legitimate transaction, customer notified',
  actionsTaken: ['Customer verification call', 'Documentation collected'],
});

// Get risk trend
const trend = await client.monitoring.getRiskTrend('0x...', { days: 30 });
console.log(`Trend: ${trend.trend}, Average score: ${trend.averageScore}`);
```

### Label Service

Manage address labels and categorizations.

```typescript
// Get labels for an address
const labels = await client.labels.getLabels('0x...');
console.log(`Risk implication: ${labels.riskImplication}`);
labels.labels.forEach(l => {
  console.log(`${l.category}: ${l.label} (${l.severity})`);
});

// Check for dangerous labels
const check = await client.labels.hasLabels('0x...', ['scam', 'sanctions', 'ransomware']);
if (check.hasLabels) {
  console.log(`⛔ Address has dangerous labels: ${check.matchedCategories.join(', ')}`);
}

// Batch check
const batch = await client.labels.batchCheck(
  ['0x...', '0x...', '0x...'],
  { minSeverity: 'high' }
);

// Add custom label
await client.labels.addLabel({
  address: '0x...',
  label: 'Known Customer',
  category: 'custodian',
  severity: 'info',
  confidence: 1.0,
  description: 'Verified business customer',
});
```

### MEV Protection Service

Protect transactions from MEV extraction.

```typescript
// Configure MEV protection
client.mev.setConfig({
  enabled: true,
  protectionLevel: 'enhanced',
  flashbotsEnabled: true,
  maxSlippage: 0.5,
});

// Analyze transaction for MEV vulnerabilities
const analysis = await client.mev.analyze({
  to: '0x...', // DEX router
  data: '0x...', // Swap data
  value: '1000000000000000000',
});

console.log(`Recommended protection: ${analysis.recommendedProtection}`);
analysis.vulnerabilities.forEach(v => {
  console.log(`⚠️ ${v.type}: ${v.description} (potential loss: ${v.estimatedLoss})`);
});

// Submit with MEV protection
const protectedTx = await client.mev.submitProtected({
  to: '0x...',
  data: '0x...',
  value: '1000000000000000000',
  gasLimit: '300000',
  signature: '0x...',
});

console.log(`Protected via: ${protectedTx.protectionType}`);
console.log(`Estimated savings: ${protectedTx.savings?.savedAmount}`);
```

## Events

The SDK emits events for key operations:

```typescript
// Subscribe to events
client.events.on('transaction:confirmed', (txHash, blockNumber) => {
  console.log(`Transaction ${txHash} confirmed in block ${blockNumber}`);
});

client.events.on('risk:alert', (address, alertType, severity) => {
  console.log(`Risk alert for ${address}: ${alertType} (${severity})`);
});

client.events.on('compliance:blocked', (address, reason) => {
  console.log(`Address ${address} blocked: ${reason}`);
});

client.events.on('error', (error) => {
  console.error('SDK Error:', error);
});

// Wait for specific event
const [txHash, block] = await client.events.waitFor('transaction:confirmed', 60000);
```

## Error Handling

```typescript
import { AMTTPError, AMTTPErrorCode } from '@amttp/client-sdk';

try {
  const risk = await client.risk.assess({ address: '0x...' });
} catch (error) {
  if (error instanceof AMTTPError) {
    switch (error.code) {
      case AMTTPErrorCode.UNAUTHORIZED:
        console.error('Invalid API key');
        break;
      case AMTTPErrorCode.RATE_LIMIT_EXCEEDED:
        console.error('Too many requests, retry after:', error.retryAfter);
        break;
      case AMTTPErrorCode.VALIDATION_ERROR:
        console.error('Invalid request:', error.details);
        break;
      case AMTTPErrorCode.NOT_FOUND:
        console.error('Resource not found');
        break;
      default:
        console.error('API error:', error.message);
    }
    
    // Check if retryable
    if (error.isRetryable()) {
      // SDK automatically retries based on config
    }
  }
}
```

## TypeScript Support

The SDK is written in TypeScript and provides full type definitions:

```typescript
import {
  AMTTPClient,
  RiskLevel,
  KYCStatus,
  KYCLevel,
  TransactionStatus,
  PolicyDecision,
  DisputeStatus,
  ReputationTier,
  RiskAssessmentResponse,
  TransactionRecord,
  Dispute,
  // ... all types exported
} from '@amttp/client-sdk';
```

## Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `baseUrl` | string | required | AMTTP API base URL |
| `apiKey` | string | undefined | API key for authentication |
| `timeout` | number | 30000 | Request timeout in ms |
| `retryAttempts` | number | 3 | Number of retry attempts |
| `mevConfig` | MEVConfig | undefined | MEV protection config |
| `debug` | boolean | false | Enable debug logging |

## Requirements

- Node.js 18.x or higher
- TypeScript 5.0+ (for TypeScript users)

## License

MIT

## Support

- Documentation: https://docs.amttp.io
- Issues: https://github.com/amttp/client-sdk/issues
- Email: support@amttp.io
