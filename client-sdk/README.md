# @amttp/client-sdk

A comprehensive TypeScript SDK for the AMTTP (Advanced Money Transfer Transaction Protocol) platform. This SDK provides full access to all AMTTP backend services including risk assessment, KYC verification, transaction processing, dispute resolution, and regulatory compliance features.

## Features

- 🔐 **Risk Assessment** - Stacked Ensemble ML risk scoring with real-time address analysis
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
- ✅ **Unified Compliance** - Complete compliance evaluation with ML integration
- 🔍 **ML Explainability** - Human-readable explanations for risk decisions
- 🚫 **Sanctions Screening** - OFAC, EU, UN sanctions list screening
- 🌍 **Geographic Risk** - Country and IP risk using FATF lists
- 🔒 **UI Integrity** - WYSIWYS verification for payment confirmations
- 🗳️ **Governance** - Multi-signature enforcement actions
- 📊 **Dashboard Analytics** - Real-time monitoring and visualization

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

Assess transaction and address risk using AMTTP's hybrid scoring API (ML + graph-derived signals + rule/pattern checks).

For reproducible evaluation artifacts in this repo, see:
- `../reports/publishing/address_level_metrics.md` (includes a proxy-label circularity caveat)
- `../reports/publishing/etherscan_validation_metrics.md` (small external sanity check)

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

### Compliance Service (NEW)

Unified compliance evaluation with ML-powered risk assessment.

```typescript
// Evaluate a transaction for compliance
const result = await client.compliance.evaluate({
  from_address: '0x...',
  to_address: '0x...',
  amount: 1.5,
  currency: 'ETH',
  chain: 'ethereum'
});

console.log(`Action: ${result.action}`); // ALLOW, REQUIRE_INFO, BLOCK, etc.
console.log(`Risk Score: ${result.risk_score}`);
console.log(`Checks:`, result.checks);

// Get entity profile
const profile = await client.compliance.getProfile('0x...');
console.log(`Entity Type: ${profile.entity_type}`);
console.log(`KYC Level: ${profile.kyc_level}`);
console.log(`Risk Tolerance: ${profile.risk_tolerance}`);

// Update entity profile
await client.compliance.updateProfile('0x...', {
  entity_type: 'INSTITUTIONAL',
  kyc_level: 'ENHANCED',
  risk_tolerance: 'STRICT'
});

// Get dashboard stats
const stats = await client.compliance.getDashboardStats();
console.log(`Active Policies: ${stats.totalPolicies}`);
console.log(`Pending Reviews: ${stats.pendingReviews}`);

// Get decision history
const decisions = await client.compliance.getDecisions({ limit: 50, status: 'BLOCKED' });
```

### Explainability Service (NEW)

Get human-readable explanations for ML risk decisions.

```typescript
// Explain a risk score
const explanation = await client.explainability.explain({
  address: '0x...',
  includeTypologies: true
});

console.log(`Risk Score: ${explanation.risk_score}`);
console.log(`Risk Level: ${explanation.risk_level}`);
console.log(`Summary: ${explanation.summary}`);

// Display risk factors
explanation.factors.forEach(f => {
  console.log(`${f.name}: ${f.contribution}% (${f.impact})`);
  console.log(`  → ${f.explanation}`);
});

// Show matched typologies
explanation.typology_matches.forEach(t => {
  console.log(`🔍 ${t.name} (Confidence: ${t.confidence})`);
  console.log(`   ${t.description}`);
});

// Explain a specific transaction
const txExplanation = await client.explainability.explainTransaction({
  tx_hash: '0x...',
  include_graph: true
});

// Get available typologies
const typologies = await client.explainability.getTypologies();
```

### Sanctions Service (NEW)

OFAC, EU, and UN sanctions screening.

```typescript
// Check a single address
const result = await client.sanctions.check({
  address: '0x...',
  lists: ['OFAC', 'EU', 'UN'],
  includeRelated: true
});

if (result.isMatch) {
  console.log(`⛔ SANCTIONS MATCH!`);
  result.matches.forEach(m => {
    console.log(`  List: ${m.list_name}`);
    console.log(`  Entity: ${m.entity.name}`);
    console.log(`  Match Type: ${m.match_type}`);
    console.log(`  Confidence: ${m.confidence}%`);
  });
}

// Batch check multiple addresses
const batchResult = await client.sanctions.batchCheck({
  addresses: ['0x...', '0x...', '0x...'],
  lists: ['OFAC', 'EU']
});

// Get sanctions statistics
const stats = await client.sanctions.getStats();
console.log(`Total entities: ${stats.totalEntities}`);
console.log(`Last updated: ${stats.lastUpdate}`);

// Get available lists
const lists = await client.sanctions.getLists();
```

### Geographic Risk Service (NEW)

Country and IP-based risk assessment using FATF lists.

```typescript
// Check country risk
const countryRisk = await client.geographic.getCountryRisk({ country_code: 'IR' });
console.log(`Risk Level: ${countryRisk.risk_level}`);
console.log(`FATF Black List: ${countryRisk.is_fatf_black_list}`);
console.log(`Policy: ${countryRisk.transaction_policy}`);

// Check IP risk
const ipRisk = await client.geographic.getIpRisk({ ip_address: '1.2.3.4' });
console.log(`Country: ${ipRisk.country_name}`);
console.log(`Is VPN: ${ipRisk.is_vpn}`);
console.log(`Is Tor: ${ipRisk.is_tor}`);
console.log(`Risk Score: ${ipRisk.risk_score}`);

// Check transaction geographic risk
const txGeoRisk = await client.geographic.getTransactionRisk({
  sender_country: 'US',
  receiver_country: 'RU',
  sender_ip: '1.2.3.4'
});

// Get FATF lists
const blackList = await client.geographic.getFatfBlackList();
const greyList = await client.geographic.getFatfGreyList();
const euHighRisk = await client.geographic.getEuHighRiskList();
const taxHavens = await client.geographic.getTaxHavens();
```

### Integrity Service (NEW)

WYSIWYS (What You See Is What You Sign) UI integrity verification.

```typescript
// Register a UI snapshot hash
const registration = await client.integrity.registerHash({
  action_type: 'TRANSFER',
  snapshot_hash: 'sha256:abc123...',
  ui_version: '1.0.0',
  component_id: 'PaymentConfirmation'
});

console.log(`Snapshot ID: ${registration.snapshot_id}`);
console.log(`Expires: ${registration.expires_at}`);

// Verify integrity before signing
const verification = await client.integrity.verifyIntegrity({
  snapshot_hash: 'sha256:abc123...',
  expected_snapshot_id: registration.snapshot_id
});

if (!verification.is_valid) {
  console.log(`⚠️ UI Tampering detected!`);
  console.log(`Discrepancies: ${verification.discrepancies.join(', ')}`);
}

// Submit verified payment
const payment = await client.integrity.submitPayment({
  from_address: '0x...',
  to_address: '0x...',
  amount: '1.5',
  currency: 'ETH',
  snapshot_hash: 'sha256:abc123...',
  user_signature: '0x...'
});

// Get integrity violations
const violations = await client.integrity.getViolations({ severity: 'HIGH', limit: 10 });
```

### Governance Service (NEW)

Multi-signature governance for enforcement actions.

```typescript
// Create a governance action
const action = await client.governance.createAction({
  type: 'WALLET_PAUSE',
  scope: 'SINGLE_WALLET',
  targetAddress: '0x...',
  durationHours: 24,
  riskContext: {
    summary: 'High risk ML score and fan-out pattern detected',
    fanOut: 15,
    velocityDeviation: 3.2,
    mlConfidence: 0.91
  },
  uiSnapshotHash: 'sha256:...',
  policyVersion: '2.1.0'
});

console.log(`Action ID: ${action.id}`);
console.log(`Status: ${action.status}`);
console.log(`Required Signatures: ${action.requiredSignatures}`);

// Get pending actions for user
const pending = await client.governance.getPendingActions('user123');

// Sign an action
const signResult = await client.governance.signAction({
  actionId: action.id,
  signature: '0x...',
  acknowledgedSnapshotHash: 'sha256:...',
  mfaToken: '123456'
});

if (signResult.quorumReached) {
  console.log(`✓ Quorum reached! Ready for execution.`);
  
  // Execute the action
  const execResult = await client.governance.executeAction(action.id);
  console.log(`Transaction: ${execResult.transactionHash}`);
}

// Get What-You-Approve summary
const summary = await client.governance.getWYASummary(action.id);

// Calculate quorum progress
const progress = GovernanceService.calculateQuorumProgress(action);
console.log(`${progress.current}/${progress.required} (${progress.percentage}%)`);
```

### Dashboard Service (NEW)

Real-time analytics and monitoring dashboard data.

```typescript
// Get dashboard statistics
const stats = await client.dashboard.getStats({ timeRange: '24h' });
console.log(`Total Transactions: ${stats.totalTransactions}`);
console.log(`Flagged: ${stats.flaggedTransactions}`);
console.log(`Compliance Score: ${stats.complianceScore}`);

// Get active alerts
const alerts = await client.dashboard.getAlerts({
  severity: 'high',
  unreadOnly: true,
  limit: 20
});

alerts.forEach(alert => {
  const formatted = DashboardService.formatAlert(alert);
  console.log(`${formatted.icon} ${formatted.title} [${formatted.color}]`);
  console.log(`   ${formatted.description}`);
});

// Mark alert as read
await client.dashboard.markAlertRead(alertId);

// Get risk distribution
const distribution = await client.dashboard.getRiskDistribution();
console.log(`Low: ${distribution.low}, Medium: ${distribution.medium}`);
console.log(`High: ${distribution.high}, Critical: ${distribution.critical}`);

// Get Sankey flow data for visualization
const sankey = await client.dashboard.getSankeyFlow({ limit: 100 });
// Use with ECharts or other Sankey visualization library

// Get top risk entities
const topRisk = await client.dashboard.getTopRiskEntities(10);

// Get geographic risk map
const geoMap = await client.dashboard.getGeographicRiskMap();

// Subscribe to real-time updates
const unsubscribe = client.dashboard.subscribeToUpdates((update) => {
  console.log(`Update: ${update.type}`, update.data);
});

// Later: cleanup
unsubscribe();

// Export dashboard data
const blob = await client.dashboard.exportData('csv', { timeRange: '7d' });
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
