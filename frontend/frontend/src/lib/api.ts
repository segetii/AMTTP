// API client for SIEM Dashboard
// Orchestrator Service (master coordinator) - Port 8007
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';
// Risk Engine Service (ML scoring) - Port 8002
const RISK_ENGINE_URL = process.env.NEXT_PUBLIC_RISK_ENGINE_URL || 'http://127.0.0.1:8002';

import type { Alert, EntityProfile, DashboardStats, TimelineDataPoint } from '@/types/siem';

// ============================================================================
// Risk Engine API (ML-based scoring)
// ============================================================================

export interface RiskScoreResponse {
  risk_score: number;
  risk_level: 'minimal' | 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  factors: Record<string, unknown>;
  model_version: string;
  timestamp: string;
}

export interface RiskEngineHealth {
  status: string;
  model_loaded: boolean;
  version: string;
  uptime_seconds: number;
}

// Check risk engine health
export async function checkRiskEngineHealth(): Promise<RiskEngineHealth> {
  const response = await fetch(`${RISK_ENGINE_URL}/health`);
  if (!response.ok) throw new Error('Risk engine unavailable');
  return response.json();
}

// Score a transaction using ML model
export async function scoreTransaction(tx: {
  from_address: string;
  to_address: string;
  value_eth: number;
  gas_price_gwei?: number;
  nonce?: number;
  data?: string;
}): Promise<RiskScoreResponse> {
  const response = await fetch(`${RISK_ENGINE_URL}/score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tx)
  });
  if (!response.ok) throw new Error('Failed to score transaction');
  return response.json();
}

// Batch score multiple transactions
export async function scoreTransactionBatch(transactions: Array<{
  from_address: string;
  to_address: string;
  value_eth: number;
  gas_price_gwei?: number;
  nonce?: number;
}>): Promise<{ results: RiskScoreResponse[]; processing_time_ms: number }> {
  const response = await fetch(`${RISK_ENGINE_URL}/score/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transactions })
  });
  if (!response.ok) throw new Error('Failed to batch score');
  return response.json();
}

// Get model info
export async function getRiskModelInfo(): Promise<{
  model_version: string;
  models_available: string[];
  last_updated: string;
}> {
  try {
    const response = await fetch(`${RISK_ENGINE_URL}/model/info`);
    if (!response.ok) throw new Error('Failed to get model info');
    return response.json();
  } catch {
    return {
      model_version: 'unknown',
      models_available: [],
      last_updated: 'unknown'
    };
  }
}

// ============================================================================
// Dashboard API (alerts, stats, entities)
// ============================================================================

// Fetch dashboard statistics
export async function fetchDashboardStats(): Promise<DashboardStats> {
  try {
    const response = await fetch(`${API_BASE}/dashboard/stats`);
    if (!response.ok) throw new Error('Failed to fetch stats');
    return response.json();
  } catch (error) {
    // Return mock data if API unavailable
    return {
      totalAlerts: 166,
      criticalAlerts: 8,
      highAlerts: 24,
      mediumAlerts: 89,
      lowAlerts: 45,
      alertsTrend: 12.5,
      resolvedToday: 15,
      pendingInvestigation: 23,
      blockedAddresses: 8,
      flaggedTransactions: 1152
    };
  }
}

// Fetch alerts with filters
export async function fetchAlerts(filters?: {
  riskLevel?: string[];
  status?: string[];
  limit?: number;
  offset?: number;
}): Promise<Alert[]> {
  try {
    const params = new URLSearchParams();
    if (filters?.riskLevel) params.set('risk_level', filters.riskLevel.join(','));
    if (filters?.status) params.set('status', filters.status.join(','));
    if (filters?.limit) params.set('limit', filters.limit.toString());
    if (filters?.offset) params.set('offset', filters.offset.toString());
    
    const response = await fetch(`${API_BASE}/alerts?${params}`);
    if (!response.ok) throw new Error('Failed to fetch alerts');
    return response.json();
  } catch (error) {
    // Return mock alerts
    return generateMockAlerts(20);
  }
}

// Fetch entity profile for drill-down
export async function fetchEntityProfile(address: string): Promise<EntityProfile> {
  try {
    const response = await fetch(`${API_BASE}/profiles/${address}`);
    if (!response.ok) throw new Error('Failed to fetch entity');
    return response.json();
  } catch (error) {
    console.error('Failed to fetch entity profile:', error);
    // Return mock entity as fallback
    return generateMockEntity(address);
  }
}

// Score an address
export async function scoreAddress(address: string): Promise<{
  address: string;
  hybrid_score: number;
  risk_level: string;
  action: string;
  ml_score: number;
  graph_score: number;
  patterns: string;
  signal_count: number;
}> {
  const response = await fetch(`${API_BASE}/score/address`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ address })
  });
  if (!response.ok) throw new Error('Failed to score address');
  return response.json();
}

// Perform action on alert
export async function performAction(
  alertId: string,
  action: 'FLAG' | 'BLOCK' | 'ESCALATE' | 'RESOLVE' | 'FALSE_POSITIVE' | 'WATCHLIST'
): Promise<{ success: boolean; message: string }> {
  try {
    const response = await fetch(`${API_BASE}/alerts/${alertId}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    if (!response.ok) throw new Error('Action failed');
    return response.json();
  } catch (error) {
    return { success: true, message: `Action ${action} performed (mock)` };
  }
}

// Fetch timeline data for charts
export async function fetchTimelineData(timeRange: string): Promise<TimelineDataPoint[]> {
  try {
    const response = await fetch(`${API_BASE}/dashboard/timeline?range=${timeRange}`);
    if (!response.ok) throw new Error('Failed to fetch timeline');
    return response.json();
  } catch (error) {
    return generateMockTimeline(timeRange);
  }
}

// Mock data generators
function generateMockAlerts(count: number): Alert[] {
  const riskLevels: Alert['riskLevel'][] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
  const patterns = ['SMURFING', 'LAYERING', 'FAN_OUT', 'FAN_IN', 'ROUND_TRIP', 'RAPID_MOVEMENT'];
  const statuses: Alert['status'][] = ['NEW', 'INVESTIGATING', 'RESOLVED', 'FALSE_POSITIVE'];
  const actions: Alert['action'][] = ['BLOCK', 'ESCROW', 'FLAG', 'MONITOR', 'APPROVE'];
  
  // Known high-risk addresses from our analysis
  const knownAddresses = [
    '0xeae7380dd4cef6fbd1144f49e4d1e6964258a4f4',
    '0xa1abfa21f80ecf401b5fab3f4cf88223dc7ed5a6',
    '0x28c6c06298d514db089934071355e5743bf21d60',
    '0x21a31ee1afc51d94c2efccaa2092ad1028285549',
    '0x56eddb7aa87536c09ccc2793473599fd21a8b17f',
    '0x3cc936b795a188f0e246cbb2d74c5bd190aecf18',
    '0x9696f59e4d72e237be84ffd425dcad154bf96976',
    '0xd793281d0d58993d2c99cd238a03f51c54b7001c'
  ];
  
  return Array.from({ length: count }, (_, i) => {
    const riskLevel = riskLevels[Math.floor(Math.random() * riskLevels.length)];
    const numPatterns = Math.floor(Math.random() * 3) + 1;
    const selectedPatterns = patterns.sort(() => 0.5 - Math.random()).slice(0, numPatterns);
    
    return {
      id: `alert-${Date.now()}-${i}`,
      timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
      address: i < knownAddresses.length ? knownAddresses[i] : `0x${Math.random().toString(16).slice(2, 42)}`,
      riskLevel,
      riskScore: riskLevel === 'CRITICAL' ? 85 + Math.random() * 15 :
                 riskLevel === 'HIGH' ? 65 + Math.random() * 20 :
                 riskLevel === 'MEDIUM' ? 40 + Math.random() * 25 :
                 Math.random() * 40,
      signals: selectedPatterns,
      signalCount: numPatterns,
      patterns: selectedPatterns,
      action: actions[riskLevels.indexOf(riskLevel)] || 'MONITOR',
      status: statuses[Math.floor(Math.random() * statuses.length)],
      valueEth: Math.random() * 100,
      transactionHash: `0x${Math.random().toString(16).slice(2, 66)}`
    };
  }).sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

function generateMockEntity(address: string): EntityProfile {
  return {
    address,
    firstSeen: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
    lastSeen: new Date().toISOString(),
    totalTransactions: Math.floor(Math.random() * 500) + 50,
    totalValueEth: Math.random() * 1000,
    riskScore: Math.random() * 100,
    riskLevel: 'HIGH',
    patterns: ['LAYERING', 'FAN_OUT'],
    graphConnections: Math.floor(Math.random() * 50) + 5,
    mlScore: Math.random(),
    graphScore: Math.random() * 50,
    alerts: generateMockAlerts(5),
    transactions: Array.from({ length: 10 }, (_, i) => ({
      hash: `0x${Math.random().toString(16).slice(2, 66)}`,
      timestamp: new Date(Date.now() - i * 3600000).toISOString(),
      from: i % 2 === 0 ? address : `0x${Math.random().toString(16).slice(2, 42)}`,
      to: i % 2 === 1 ? address : `0x${Math.random().toString(16).slice(2, 42)}`,
      valueEth: Math.random() * 10,
      gasUsed: Math.floor(Math.random() * 100000) + 21000,
      riskScore: Math.random() * 100,
      flagged: Math.random() > 0.7
    })),
    connectedAddresses: Array.from({ length: 8 }, () => ({
      address: `0x${Math.random().toString(16).slice(2, 42)}`,
      relationship: ['SENT_TO', 'RECEIVED_FROM', 'BOTH'][Math.floor(Math.random() * 3)] as 'SENT_TO' | 'RECEIVED_FROM' | 'BOTH',
      transactionCount: Math.floor(Math.random() * 20) + 1,
      totalValue: Math.random() * 50,
      riskLevel: ['LOW', 'MEDIUM', 'HIGH'][Math.floor(Math.random() * 3)]
    }))
  };
}

function generateMockTimeline(timeRange: string): TimelineDataPoint[] {
  const points = timeRange === '1h' ? 12 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;
  const interval = timeRange === '1h' ? 5 * 60 * 1000 : 
                   timeRange === '24h' ? 60 * 60 * 1000 :
                   24 * 60 * 60 * 1000;
  
  return Array.from({ length: points }, (_, i) => ({
    timestamp: new Date(Date.now() - (points - i) * interval).toISOString(),
    critical: Math.floor(Math.random() * 3),
    high: Math.floor(Math.random() * 8),
    medium: Math.floor(Math.random() * 15),
    low: Math.floor(Math.random() * 10)
  }));
}

// ============================================================================
// Policy Management API
// ============================================================================

import type { Policy, PolicyFormData } from '@/types/policy';

const POLICY_API = process.env.NEXT_PUBLIC_POLICY_API_URL || 'http://127.0.0.1:8003';

// Fetch all policies
export async function fetchPolicies(): Promise<Policy[]> {
  try {
    const response = await fetch(`${POLICY_API}/policies`);
    if (!response.ok) throw new Error('Failed to fetch policies');
    return response.json();
  } catch (error) {
    console.error('API error, using mock data:', error);
    return generateMockPolicies();
  }
}

// Fetch single policy by ID
export async function fetchPolicy(id: string): Promise<Policy | null> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${id}`);
    if (!response.ok) return null;
    return response.json();
  } catch {
    const policies = generateMockPolicies();
    return policies.find(p => p.id === id) || null;
  }
}

// Create new policy
export async function createPolicy(data: PolicyFormData): Promise<Policy> {
  try {
    const response = await fetch(`${POLICY_API}/policies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error('Failed to create policy');
    return response.json();
  } catch (error) {
    console.error('Create policy error:', error);
    // Return mock created policy
    return {
      id: `policy-${Date.now()}`,
      ...data,
      isDefault: false,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      createdBy: '0x0000000000000000000000000000000000000000',
      stats: {
        totalTransactions: 0,
        approvedCount: 0,
        reviewedCount: 0,
        escrowedCount: 0,
        blockedCount: 0
      }
    };
  }
}

// Update existing policy
export async function updatePolicy(id: string, data: Partial<PolicyFormData>): Promise<Policy> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!response.ok) throw new Error('Failed to update policy');
    return response.json();
  } catch (error) {
    console.error('Update policy error:', error);
    throw error;
  }
}

// Delete policy
export async function deletePolicy(id: string): Promise<void> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${id}`, {
      method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to delete policy');
  } catch (error) {
    console.error('Delete policy error:', error);
    throw error;
  }
}

// Toggle policy active status
export async function togglePolicyStatus(id: string, isActive: boolean): Promise<Policy> {
  return updatePolicy(id, { isActive });
}

// Set policy as default
export async function setDefaultPolicy(id: string): Promise<Policy> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${id}/set-default`, {
      method: 'POST'
    });
    if (!response.ok) throw new Error('Failed to set default policy');
    return response.json();
  } catch (error) {
    console.error('Set default policy error:', error);
    throw error;
  }
}

// Add address to whitelist
export async function addToWhitelist(policyId: string, address: string): Promise<Policy> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${policyId}/whitelist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    if (!response.ok) throw new Error('Failed to add to whitelist');
    return response.json();
  } catch (error) {
    console.error('Add to whitelist error:', error);
    throw error;
  }
}

// Add address to blacklist
export async function addToBlacklist(policyId: string, address: string): Promise<Policy> {
  try {
    const response = await fetch(`${POLICY_API}/policies/${policyId}/blacklist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
    if (!response.ok) throw new Error('Failed to add to blacklist');
    return response.json();
  } catch (error) {
    console.error('Add to blacklist error:', error);
    throw error;
  }
}

// Mock policy data generator
function generateMockPolicies(): Policy[] {
  return [
    {
      id: 'policy-default',
      name: 'Default Policy',
      description: 'Standard compliance policy for all transactions',
      isActive: true,
      isDefault: true,
      createdAt: '2025-01-01T00:00:00Z',
      updatedAt: '2025-01-05T00:00:00Z',
      createdBy: '0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F',
      thresholds: { lowRiskMax: 25, mediumRiskMax: 50, highRiskMax: 75 },
      limits: {
        maxTransactionAmount: '1000000000000000000000',
        dailyLimit: '10000000000000000000000',
        monthlyLimit: '100000000000000000000000',
        maxCounterparties: 100
      },
      rules: {
        blockSanctionedAddresses: true,
        requireKYCAboveThreshold: true,
        kycThresholdAmount: '10000000000000000000',
        autoEscrowHighRisk: true,
        escrowDurationHours: 24,
        allowedChainIds: [1, 137, 42161],
        blockedCountries: ['KP', 'IR', 'SY']
      },
      actions: {
        onLowRisk: 'APPROVE',
        onMediumRisk: 'REVIEW',
        onHighRisk: 'ESCROW',
        onCriticalRisk: 'BLOCK',
        onSanctionedAddress: 'BLOCK',
        onUnknownAddress: 'REVIEW'
      },
      whitelist: [],
      blacklist: [],
      stats: {
        totalTransactions: 15420,
        approvedCount: 12500,
        reviewedCount: 2100,
        escrowedCount: 720,
        blockedCount: 100,
        lastTriggered: '2025-01-05T10:30:00Z'
      }
    },
    {
      id: 'policy-high-value',
      name: 'High Value Transactions',
      description: 'Stricter policy for transactions over 100 ETH',
      isActive: true,
      isDefault: false,
      createdAt: '2025-01-02T00:00:00Z',
      updatedAt: '2025-01-04T00:00:00Z',
      createdBy: '0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F',
      thresholds: { lowRiskMax: 15, mediumRiskMax: 35, highRiskMax: 60 },
      limits: {
        maxTransactionAmount: '500000000000000000000',
        dailyLimit: '1000000000000000000000',
        monthlyLimit: '10000000000000000000000',
        maxCounterparties: 20
      },
      rules: {
        blockSanctionedAddresses: true,
        requireKYCAboveThreshold: true,
        kycThresholdAmount: '1000000000000000000',
        autoEscrowHighRisk: true,
        escrowDurationHours: 48,
        allowedChainIds: [1],
        blockedCountries: ['KP', 'IR', 'SY', 'CU', 'VE']
      },
      actions: {
        onLowRisk: 'REVIEW',
        onMediumRisk: 'ESCROW',
        onHighRisk: 'ESCROW',
        onCriticalRisk: 'BLOCK',
        onSanctionedAddress: 'BLOCK',
        onUnknownAddress: 'BLOCK'
      },
      whitelist: ['0x1234567890123456789012345678901234567890'],
      blacklist: [],
      stats: {
        totalTransactions: 342,
        approvedCount: 0,
        reviewedCount: 210,
        escrowedCount: 120,
        blockedCount: 12,
        lastTriggered: '2025-01-05T09:15:00Z'
      }
    },
    {
      id: 'policy-defi',
      name: 'DeFi Protocol Interactions',
      description: 'Optimized for DEX and lending protocol interactions',
      isActive: false,
      isDefault: false,
      createdAt: '2025-01-03T00:00:00Z',
      updatedAt: '2025-01-03T00:00:00Z',
      createdBy: '0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F',
      thresholds: { lowRiskMax: 30, mediumRiskMax: 55, highRiskMax: 80 },
      limits: {
        maxTransactionAmount: '10000000000000000000000',
        dailyLimit: '50000000000000000000000',
        monthlyLimit: '500000000000000000000000',
        maxCounterparties: 500
      },
      rules: {
        blockSanctionedAddresses: true,
        requireKYCAboveThreshold: false,
        kycThresholdAmount: '0',
        autoEscrowHighRisk: false,
        escrowDurationHours: 0,
        allowedChainIds: [1, 137, 42161, 10, 8453],
        blockedCountries: []
      },
      actions: {
        onLowRisk: 'APPROVE',
        onMediumRisk: 'APPROVE',
        onHighRisk: 'REVIEW',
        onCriticalRisk: 'ESCROW',
        onSanctionedAddress: 'BLOCK',
        onUnknownAddress: 'APPROVE'
      },
      whitelist: [],
      blacklist: [],
      stats: {
        totalTransactions: 0,
        approvedCount: 0,
        reviewedCount: 0,
        escrowedCount: 0,
        blockedCount: 0
      }
    }
  ];
}
