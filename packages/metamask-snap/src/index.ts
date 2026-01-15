/**
 * AMTTP MetaMask Snap - Transaction Risk Assessment
 * 
 * Provides real-time risk scoring and policy enforcement
 * directly in MetaMask before transaction confirmation.
 */

import type {
  OnTransactionHandler,
  OnRpcRequestHandler,
  OnInstallHandler,
  OnHomePageHandler,
} from '@metamask/snaps-sdk';
import {
  panel,
  text,
  heading,
  divider,
  row,
  address,
  copyable,
  image,
  bold,
  UserInputEventType,
} from '@metamask/snaps-sdk';

// ============================================================
// TYPES
// ============================================================

interface RiskScore {
  score: number;
  level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  factors: string[];
  recommendation: 'APPROVE' | 'REVIEW' | 'BLOCK';
}

interface TransactionData {
  from: string;
  to: string;
  value: string;
  data?: string;
  chainId: string;
}

interface UserPolicy {
  maxRiskThreshold: number;
  blockHighRisk: boolean;
  requireConfirmation: boolean;
  allowedAddresses: string[];
  blockedAddresses: string[];
  dailyLimit: string;
  notifyOnMediumRisk: boolean;
}

interface SnapState {
  policy: UserPolicy;
  transactionHistory: Array<{
    hash: string;
    to: string;
    riskScore: number;
    timestamp: number;
  }>;
  blockedCount: number;
  approvedCount: number;
}

// ============================================================
// CONSTANTS
// ============================================================

const DEFAULT_POLICY: UserPolicy = {
  maxRiskThreshold: 70,
  blockHighRisk: true,
  requireConfirmation: true,
  allowedAddresses: [],
  blockedAddresses: [],
  dailyLimit: '10', // ETH
  notifyOnMediumRisk: true,
};

const AMTTP_API_URL = 'http://localhost:8000';
const FCA_API_URL = 'http://localhost:8002';

const RISK_COLORS = {
  LOW: '🟢',
  MEDIUM: '🟡',
  HIGH: '🔴',
  CRITICAL: '⛔',
};

// ============================================================
// HELPERS
// ============================================================

/**
 * Get the current state from Snap storage
 */
async function getState(): Promise<SnapState> {
  const state = await snap.request({
    method: 'snap_manageState',
    params: { operation: 'get' },
  });
  
  return (state as SnapState) || {
    policy: DEFAULT_POLICY,
    transactionHistory: [],
    blockedCount: 0,
    approvedCount: 0,
  };
}

/**
 * Save state to Snap storage
 */
async function setState(state: SnapState): Promise<void> {
  await snap.request({
    method: 'snap_manageState',
    params: { operation: 'update', newState: state },
  });
}

/**
 * Fetch risk score from AMTTP API
 */
async function fetchRiskScore(transaction: TransactionData): Promise<RiskScore> {
  try {
    const response = await fetch(`${AMTTP_API_URL}/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        from_address: transaction.from,
        to_address: transaction.to,
        value_eth: parseFloat(transaction.value) / 1e18,
        input_data: transaction.data || '0x',
      }),
    });

    if (!response.ok) {
      throw new Error('API request failed');
    }

    const data = await response.json();
    
    // Convert API response to our format
    const score = data.hybrid_score * 100 || data.risk_score || 0;
    
    return {
      score,
      level: getRiskLevel(score),
      factors: data.risk_factors || extractRiskFactors(data),
      recommendation: getRecommendation(score),
    };
  } catch (error) {
    // Fallback to basic risk assessment if API is unavailable
    return performLocalRiskAssessment(transaction);
  }
}

/**
 * Check sanctions status via FCA API
 */
async function checkSanctions(address: string): Promise<boolean> {
  try {
    const response = await fetch(`${FCA_API_URL}/compliance/sanctions/check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address }),
    });

    if (!response.ok) return false;
    
    const data = await response.json();
    return data.is_sanctioned || false;
  } catch {
    return false;
  }
}

/**
 * Determine risk level from score
 */
function getRiskLevel(score: number): RiskScore['level'] {
  if (score >= 85) return 'CRITICAL';
  if (score >= 70) return 'HIGH';
  if (score >= 40) return 'MEDIUM';
  return 'LOW';
}

/**
 * Get recommendation based on score
 */
function getRecommendation(score: number): RiskScore['recommendation'] {
  if (score >= 70) return 'BLOCK';
  if (score >= 40) return 'REVIEW';
  return 'APPROVE';
}

/**
 * Extract risk factors from API response
 */
function extractRiskFactors(data: Record<string, unknown>): string[] {
  const factors: string[] = [];
  
  if (data.graph_risk && (data.graph_risk as number) > 0.5) {
    factors.push('Graph analysis detected suspicious patterns');
  }
  if (data.ml_risk && (data.ml_risk as number) > 0.5) {
    factors.push('ML model flagged anomalous behavior');
  }
  if (data.is_known_mixer) {
    factors.push('Recipient associated with mixing services');
  }
  if (data.is_new_address) {
    factors.push('New address with no transaction history');
  }
  if (data.high_value) {
    factors.push('High value transaction');
  }
  
  if (factors.length === 0) {
    factors.push('No specific risk factors identified');
  }
  
  return factors;
}

/**
 * Perform local risk assessment when API is unavailable
 */
function performLocalRiskAssessment(transaction: TransactionData): RiskScore {
  let score = 0;
  const factors: string[] = [];
  
  // Check value
  const valueEth = parseFloat(transaction.value) / 1e18;
  if (valueEth > 10) {
    score += 20;
    factors.push('Large transaction value (>10 ETH)');
  }
  if (valueEth > 100) {
    score += 30;
    factors.push('Very large transaction (>100 ETH)');
  }
  
  // Check for contract interaction
  if (transaction.data && transaction.data.length > 10) {
    score += 10;
    factors.push('Contract interaction detected');
  }
  
  // Check for known patterns in data
  if (transaction.data?.includes('0x095ea7b3')) {
    score += 15;
    factors.push('Token approval detected - verify spender');
  }
  
  if (factors.length === 0) {
    factors.push('Basic local assessment (API offline)');
  }
  
  return {
    score,
    level: getRiskLevel(score),
    factors,
    recommendation: getRecommendation(score),
  };
}

/**
 * Format ETH value for display
 */
function formatEth(weiValue: string): string {
  const eth = parseFloat(weiValue) / 1e18;
  return `${eth.toFixed(4)} ETH`;
}

// ============================================================
// SNAP HANDLERS
// ============================================================

/**
 * Called when the Snap is installed
 */
export const onInstall: OnInstallHandler = async () => {
  await snap.request({
    method: 'snap_dialog',
    params: {
      type: 'alert',
      content: panel([
        heading('🛡️ AMTTP Risk Guard Installed'),
        text('Your transactions are now protected with AI-powered risk assessment.'),
        divider(),
        text('**Features:**'),
        text('• Real-time risk scoring before every transaction'),
        text('• Sanctions screening (HMT/OFAC)'),
        text('• Customizable security policies'),
        text('• Transaction history tracking'),
        divider(),
        text('Configure your security settings from the Snap home page.'),
      ]),
    },
  });

  // Initialize default state
  await setState({
    policy: DEFAULT_POLICY,
    transactionHistory: [],
    blockedCount: 0,
    approvedCount: 0,
  });
};

/**
 * Transaction insight handler - called before every transaction
 */
export const onTransaction: OnTransactionHandler = async ({ transaction, chainId }) => {
  const state = await getState();
  const txData: TransactionData = {
    from: transaction.from as string,
    to: transaction.to as string,
    value: transaction.value as string || '0',
    data: transaction.data as string,
    chainId,
  };

  // Check if address is in user's blocklist
  if (state.policy.blockedAddresses.includes(txData.to.toLowerCase())) {
    return {
      content: panel([
        heading('⛔ BLOCKED ADDRESS'),
        text('This address is on your personal blocklist.'),
        divider(),
        row('Recipient', address(txData.to as `0x${string}`)),
        text('**Action:** Transaction blocked by your policy.'),
      ]),
      severity: 'critical',
    };
  }

  // Check if address is in allowlist (skip risk check)
  if (state.policy.allowedAddresses.includes(txData.to.toLowerCase())) {
    return {
      content: panel([
        heading('✅ TRUSTED ADDRESS'),
        text('This address is on your allowlist.'),
        row('Recipient', address(txData.to as `0x${string}`)),
      ]),
    };
  }

  // Fetch risk score from AMTTP API
  const riskScore = await fetchRiskScore(txData);
  
  // Check sanctions
  const isSanctioned = await checkSanctions(txData.to);
  
  if (isSanctioned) {
    riskScore.score = 100;
    riskScore.level = 'CRITICAL';
    riskScore.factors.unshift('⚠️ ADDRESS ON SANCTIONS LIST');
    riskScore.recommendation = 'BLOCK';
  }

  // Build insight panel
  const insightContent = [
    heading(`${RISK_COLORS[riskScore.level]} AMTTP Risk Assessment`),
    divider(),
    row('Risk Score', text(`**${riskScore.score.toFixed(0)}/100**`)),
    row('Risk Level', text(`**${riskScore.level}**`)),
    row('Recommendation', text(`**${riskScore.recommendation}**`)),
    divider(),
    row('Recipient', address(txData.to as `0x${string}`)),
    row('Value', text(formatEth(txData.value))),
    divider(),
    heading('Risk Factors'),
  ];

  // Add risk factors
  riskScore.factors.forEach((factor) => {
    insightContent.push(text(`• ${factor}`));
  });

  // Add warning for high risk
  if (riskScore.level === 'HIGH' || riskScore.level === 'CRITICAL') {
    insightContent.push(divider());
    insightContent.push(
      text('⚠️ **Warning:** This transaction has been flagged as high risk. Proceed with caution.')
    );
  }

  // Determine severity
  let severity: 'critical' | undefined;
  if (riskScore.level === 'CRITICAL' || isSanctioned) {
    severity = 'critical';
  }

  // Check against user policy
  if (state.policy.blockHighRisk && riskScore.score >= state.policy.maxRiskThreshold) {
    insightContent.push(divider());
    insightContent.push(
      text(`🚫 **Policy Alert:** This transaction exceeds your risk threshold of ${state.policy.maxRiskThreshold}.`)
    );
    severity = 'critical';
  }

  return {
    content: panel(insightContent),
    severity,
  };
};

/**
 * Home page handler - shows Snap UI in MetaMask
 */
export const onHomePage: OnHomePageHandler = async () => {
  const state = await getState();
  
  return {
    content: panel([
      heading('🛡️ AMTTP Risk Guard'),
      text('AI-powered transaction protection'),
      divider(),
      
      heading('📊 Statistics'),
      row('Transactions Approved', text(`${state.approvedCount}`)),
      row('Transactions Blocked', text(`${state.blockedCount}`)),
      row('Risk Threshold', text(`${state.policy.maxRiskThreshold}/100`)),
      divider(),
      
      heading('⚙️ Current Policy'),
      row('Block High Risk', text(state.policy.blockHighRisk ? '✅ Yes' : '❌ No')),
      row('Require Confirmation', text(state.policy.requireConfirmation ? '✅ Yes' : '❌ No')),
      row('Notify Medium Risk', text(state.policy.notifyOnMediumRisk ? '✅ Yes' : '❌ No')),
      row('Daily Limit', text(`${state.policy.dailyLimit} ETH`)),
      divider(),
      
      heading('📋 Lists'),
      row('Allowed Addresses', text(`${state.policy.allowedAddresses.length}`)),
      row('Blocked Addresses', text(`${state.policy.blockedAddresses.length}`)),
      divider(),
      
      text('Use the RPC methods to configure your policy:'),
      copyable('amttp_setPolicy'),
      copyable('amttp_addToAllowlist'),
      copyable('amttp_addToBlocklist'),
    ]),
  };
};

/**
 * RPC request handler for dApp interactions
 */
export const onRpcRequest: OnRpcRequestHandler = async ({ origin, request }) => {
  const state = await getState();

  switch (request.method) {
    // Get current policy
    case 'amttp_getPolicy': {
      return state.policy;
    }

    // Set policy
    case 'amttp_setPolicy': {
      const newPolicy = request.params as Partial<UserPolicy>;
      
      // Confirm with user
      const confirmed = await snap.request({
        method: 'snap_dialog',
        params: {
          type: 'confirmation',
          content: panel([
            heading('Update Security Policy'),
            text(`${origin} wants to update your AMTTP policy.`),
            divider(),
            text('New settings:'),
            row('Risk Threshold', text(`${newPolicy.maxRiskThreshold || state.policy.maxRiskThreshold}`)),
            row('Block High Risk', text(newPolicy.blockHighRisk !== undefined ? String(newPolicy.blockHighRisk) : String(state.policy.blockHighRisk))),
            divider(),
            text('Do you approve this change?'),
          ]),
        },
      });

      if (confirmed) {
        state.policy = { ...state.policy, ...newPolicy };
        await setState(state);
        return { success: true, policy: state.policy };
      }
      
      return { success: false, error: 'User rejected policy change' };
    }

    // Add address to allowlist
    case 'amttp_addToAllowlist': {
      const { address: addr } = request.params as { address: string };
      
      const confirmed = await snap.request({
        method: 'snap_dialog',
        params: {
          type: 'confirmation',
          content: panel([
            heading('Add to Allowlist'),
            text('Add this address to your trusted list?'),
            copyable(addr),
            text('Transactions to this address will skip risk checks.'),
          ]),
        },
      });

      if (confirmed) {
        if (!state.policy.allowedAddresses.includes(addr.toLowerCase())) {
          state.policy.allowedAddresses.push(addr.toLowerCase());
          await setState(state);
        }
        return { success: true };
      }
      
      return { success: false };
    }

    // Add address to blocklist
    case 'amttp_addToBlocklist': {
      const { address: addr } = request.params as { address: string };
      
      const confirmed = await snap.request({
        method: 'snap_dialog',
        params: {
          type: 'confirmation',
          content: panel([
            heading('Add to Blocklist'),
            text('Block all transactions to this address?'),
            copyable(addr),
            text('⚠️ You will not be able to send to this address.'),
          ]),
        },
      });

      if (confirmed) {
        if (!state.policy.blockedAddresses.includes(addr.toLowerCase())) {
          state.policy.blockedAddresses.push(addr.toLowerCase());
          await setState(state);
        }
        return { success: true };
      }
      
      return { success: false };
    }

    // Remove from allowlist
    case 'amttp_removeFromAllowlist': {
      const { address: addr } = request.params as { address: string };
      state.policy.allowedAddresses = state.policy.allowedAddresses.filter(
        (a) => a !== addr.toLowerCase()
      );
      await setState(state);
      return { success: true };
    }

    // Remove from blocklist
    case 'amttp_removeFromBlocklist': {
      const { address: addr } = request.params as { address: string };
      state.policy.blockedAddresses = state.policy.blockedAddresses.filter(
        (a) => a !== addr.toLowerCase()
      );
      await setState(state);
      return { success: true };
    }

    // Get transaction history
    case 'amttp_getHistory': {
      return state.transactionHistory;
    }

    // Get stats
    case 'amttp_getStats': {
      return {
        approved: state.approvedCount,
        blocked: state.blockedCount,
        historyCount: state.transactionHistory.length,
      };
    }

    // Check risk for an address
    case 'amttp_checkRisk': {
      const { to, value } = request.params as { to: string; value: string };
      const riskScore = await fetchRiskScore({
        from: '0x0000000000000000000000000000000000000000',
        to,
        value: value || '0',
        chainId: '0x1',
      });
      return riskScore;
    }

    default:
      throw new Error(`Method not found: ${request.method}`);
  }
};
