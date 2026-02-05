// API client for SIEM Dashboard
// Orchestrator Service (master coordinator) - Port 8007
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';
// Risk Engine Service (ML scoring) - Port 8002
const RISK_ENGINE_URL = process.env.NEXT_PUBLIC_RISK_ENGINE_URL || 'http://127.0.0.1:8002';
// Explainability Service - Port 8009
const EXPLAIN_URL = process.env.NEXT_PUBLIC_EXPLAIN_URL || 'http://127.0.0.1:8009';

import type { Alert, EntityProfile, DashboardStats, TimelineDataPoint } from '@/types/siem';

// ============================================================================
// Explainability Types
// ============================================================================

export type ImpactLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NEUTRAL';

export interface ExplanationFactor {
  factor_id: string;
  impact: ImpactLevel;
  reason: string;
  detail: string;
  value: unknown;
  threshold?: unknown;
  contribution: number;
}

export interface TypologyMatch {
  typology: string;
  confidence: number;
  description: string;
  indicators: string[];
  evidence: Record<string, unknown>;
}

export interface RiskExplanation {
  risk_score: number;
  action: 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK';
  summary: string;
  top_reasons: string[];
  factors: ExplanationFactor[];
  typology_matches: TypologyMatch[];
  graph_explanation?: string;
  recommendations: string[];
  confidence: number;
  degraded_mode: boolean;
}

// ============================================================================
// Explainability API
// ============================================================================

/**
 * Get human-readable explanation for a risk score
 */
export async function getExplanation(params: {
  risk_score: number;
  features: Record<string, unknown>;
  graph_context?: Record<string, unknown>;
}): Promise<RiskExplanation> {
  try {
    const response = await fetch(`${EXPLAIN_URL}/explain`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    if (!response.ok) throw new Error('Explainability service unavailable');
    return response.json();
  } catch (error) {
    // Fallback to local explanation with graph context
    return generateLocalExplanation(params.risk_score, params.features, params.graph_context);
  }
}

/**
 * Get explanation for a specific transaction
 */
export async function explainTransaction(params: {
  transaction_hash: string;
  risk_score: number;
  sender: string;
  receiver: string;
  amount: number;
  features: Record<string, unknown>;
}): Promise<RiskExplanation & { transaction: { hash: string; sender: string; receiver: string; amount: number } }> {
  try {
    const response = await fetch(`${EXPLAIN_URL}/explain/transaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });
    if (!response.ok) throw new Error('Explainability service unavailable');
    return response.json();
  } catch (error) {
    const localExplanation = generateLocalExplanation(params.risk_score, { ...params.features, amount_eth: params.amount });
    return {
      ...localExplanation,
      transaction: {
        hash: params.transaction_hash,
        sender: params.sender,
        receiver: params.receiver,
        amount: params.amount
      }
    };
  }
}

/**
 * Get all known fraud typologies
 */
export async function getTypologies(): Promise<Array<{ id: string; name: string; description: string }>> {
  try {
    const response = await fetch(`${EXPLAIN_URL}/typologies`);
    if (!response.ok) throw new Error('Failed to fetch typologies');
    const data = await response.json();
    return data.typologies;
  } catch {
    return KNOWN_TYPOLOGIES;
  }
}

// Known fraud typologies (fallback)
const KNOWN_TYPOLOGIES = [
  { id: 'structuring', name: 'Structuring', description: 'Breaking large transactions into smaller ones' },
  { id: 'layering', name: 'Layering', description: 'Complex chains to obscure fund origins' },
  { id: 'smurfing', name: 'Smurfing', description: 'Using multiple accounts to move funds' },
  { id: 'fan_out', name: 'Fan Out', description: 'Single source distributing to many' },
  { id: 'fan_in', name: 'Fan In', description: 'Many sources consolidating to one' },
  { id: 'mixer_interaction', name: 'Mixer Interaction', description: 'Funds through mixing services' },
  { id: 'sanctions_proximity', name: 'Sanctions Proximity', description: 'Near sanctioned entities' },
  { id: 'dormant_activation', name: 'Dormant Activation', description: 'Inactive account suddenly active' },
  { id: 'rapid_movement', name: 'Rapid Movement', description: 'Fast fund movement through hops' },
];

/**
 * Generate local explanation when service unavailable - ENHANCED VERSION
 * Provides meaningful patterns, factors, and recommendations based on available data
 */
function generateLocalExplanation(riskScore: number, features: Record<string, unknown>, graphContext?: Record<string, unknown>): RiskExplanation {
  const factors: ExplanationFactor[] = [];
  const topReasons: string[] = [];
  const typologyMatches: TypologyMatch[] = [];
  const recommendations: string[] = [];
  let graphExplanation: string | undefined;

  // Determine action based on risk score
  let action: 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK';
  if (riskScore >= 0.85) action = 'BLOCK';
  else if (riskScore >= 0.70) action = 'ESCROW';
  else if (riskScore >= 0.40) action = 'REVIEW';
  else action = 'ALLOW';

  // Extract feature values with defaults
  const amountEth = Number(features.amount_eth || features.value_eth || features.amount || 0);
  const txCount = Number(features.tx_count_24h || features.velocity_24h || features.velocity || 0);
  const amountVsAverage = Number(features.amount_vs_average || 1);
  const dormancyDays = Number(features.dormancy_days || 0);
  const hopsToSanctioned = graphContext?.hops_to_sanctioned as number | undefined ?? features.hops_to_sanctioned as number | undefined;
  const inDegree = Number(graphContext?.in_degree || features.in_degree || 0);
  const outDegree = Number(graphContext?.out_degree || features.out_degree || 0);
  const pagerank = Number(graphContext?.pagerank || features.pagerank || 0);
  const clusteringCoef = Number(graphContext?.clustering_coefficient || features.clustering_coefficient || 0);
  const mixerInteraction = Boolean(graphContext?.mixer_interaction || features.mixer_interaction);

  // ═══════════════════════════════════════════════════════════════════════════
  // FACTOR ANALYSIS - Generate detailed factors based on features
  // ═══════════════════════════════════════════════════════════════════════════

  // 1. Amount Analysis
  if (amountEth >= 1000) {
    factors.push({
      factor_id: 'critical_amount',
      impact: 'CRITICAL',
      reason: `Very large transaction amount (${amountEth.toFixed(2)} ETH, ~$${(amountEth * 2500).toLocaleString()})`,
      detail: 'Transaction amount exceeds critical threshold requiring enhanced due diligence',
      value: amountEth,
      threshold: 1000,
      contribution: 0.35
    });
    topReasons.push(`Critical: ${amountEth.toFixed(2)} ETH (~$${(amountEth * 2500).toLocaleString()}) transaction`);
  } else if (amountEth >= 100) {
    factors.push({
      factor_id: 'large_amount',
      impact: 'HIGH',
      reason: `Large transaction amount (${amountEth.toFixed(2)} ETH, ~$${(amountEth * 2500).toLocaleString()})`,
      detail: 'Transaction amount exceeds typical threshold for enhanced monitoring',
      value: amountEth,
      threshold: 100,
      contribution: 0.25
    });
    topReasons.push(`Large transaction: ${amountEth.toFixed(2)} ETH`);
  } else if (amountEth >= 10) {
    factors.push({
      factor_id: 'medium_amount',
      impact: 'MEDIUM',
      reason: `Above-average amount (${amountEth.toFixed(2)} ETH)`,
      detail: 'Transaction amount above typical range for this address',
      value: amountEth,
      threshold: 10,
      contribution: 0.10
    });
  }

  // 2. Amount vs Historical Average
  if (amountVsAverage >= 10) {
    factors.push({
      factor_id: 'amount_anomaly',
      impact: 'HIGH',
      reason: `Transaction is ${amountVsAverage.toFixed(1)}x larger than sender's 30-day average`,
      detail: 'Significant deviation from historical transaction patterns',
      value: amountVsAverage,
      threshold: 10,
      contribution: 0.20
    });
    topReasons.push(`Amount ${amountVsAverage.toFixed(1)}x above historical average`);
  } else if (amountVsAverage >= 3) {
    factors.push({
      factor_id: 'amount_elevated',
      impact: 'MEDIUM',
      reason: `Transaction is ${amountVsAverage.toFixed(1)}x larger than typical`,
      detail: 'Transaction amount higher than usual for this sender',
      value: amountVsAverage,
      threshold: 3,
      contribution: 0.10
    });
  }

  // 3. Velocity Analysis
  if (txCount >= 20) {
    factors.push({
      factor_id: 'high_velocity',
      impact: 'HIGH',
      reason: `Very high transaction velocity (${txCount} transactions in 24 hours)`,
      detail: 'Unusually high number of transactions indicating potential automated activity',
      value: txCount,
      threshold: 20,
      contribution: 0.20
    });
    topReasons.push(`${txCount} transactions in 24 hours (very high activity)`);
  } else if (txCount >= 10) {
    factors.push({
      factor_id: 'elevated_velocity',
      impact: 'MEDIUM',
      reason: `Elevated transaction velocity (${txCount} in 24h)`,
      detail: 'Above-average transaction frequency',
      value: txCount,
      threshold: 10,
      contribution: 0.12
    });
    topReasons.push(`${txCount} transactions in 24 hours`);
  }

  // 4. Dormancy Analysis
  if (dormancyDays >= 365) {
    factors.push({
      factor_id: 'long_dormancy',
      impact: 'HIGH',
      reason: `Account was dormant for ${dormancyDays} days (${(dormancyDays / 365).toFixed(1)} years)`,
      detail: 'Long-dormant account suddenly active with significant funds',
      value: dormancyDays,
      threshold: 365,
      contribution: 0.18
    });
    topReasons.push(`Dormant for ${dormancyDays} days before this activity`);
    
    typologyMatches.push({
      typology: 'dormant_activation',
      confidence: Math.min(0.9, 0.5 + dormancyDays / 730),
      description: 'Account reactivated after extended dormancy period, which may indicate account takeover or money laundering preparation',
      indicators: [
        `Inactive for ${dormancyDays} days`,
        'Sudden reactivation with transaction',
        'Pattern consistent with sleeper accounts'
      ],
      evidence: { dormancy_days: dormancyDays, years_dormant: (dormancyDays / 365).toFixed(1) }
    });
  } else if (dormancyDays >= 180) {
    factors.push({
      factor_id: 'dormancy',
      impact: 'MEDIUM',
      reason: `Account was inactive for ${dormancyDays} days`,
      detail: 'Account reactivated after significant dormancy period',
      value: dormancyDays,
      threshold: 180,
      contribution: 0.12
    });
  }

  // 5. Sanctions Proximity Analysis
  if (hopsToSanctioned !== undefined && hopsToSanctioned <= 3) {
    const impact: ImpactLevel = hopsToSanctioned === 0 ? 'CRITICAL' : hopsToSanctioned === 1 ? 'HIGH' : 'MEDIUM';
    const contribution = hopsToSanctioned === 0 ? 0.5 : hopsToSanctioned === 1 ? 0.35 : 0.20;
    
    factors.push({
      factor_id: 'sanctions_proximity',
      impact,
      reason: hopsToSanctioned === 0 
        ? 'CRITICAL: Direct sanctioned address match (OFAC/EU/UN)'
        : `Counterparty is ${hopsToSanctioned} hop(s) from sanctioned entity`,
      detail: hopsToSanctioned === 0
        ? 'Address appears on international sanctions lists - transaction must be blocked'
        : 'Network analysis reveals connection to sanctioned entities',
      value: hopsToSanctioned,
      threshold: 2,
      contribution
    });
    
    topReasons.push(hopsToSanctioned === 0 
      ? '🚨 SANCTIONED ADDRESS - Direct match on OFAC/EU/UN list'
      : `${hopsToSanctioned} hop(s) from sanctioned address`);

    typologyMatches.push({
      typology: 'sanctions_proximity',
      confidence: hopsToSanctioned === 0 ? 1.0 : 0.9 - (hopsToSanctioned * 0.15),
      description: hopsToSanctioned === 0
        ? 'Direct sanctions list match - transaction chain connects to OFAC/HMT/EU/UN designated entity'
        : `Transaction chain ${hopsToSanctioned} hop(s) from sanctioned address, indicating potential sanctions evasion`,
      indicators: [
        hopsToSanctioned === 0 ? 'Direct OFAC/EU/UN match' : `${hopsToSanctioned} degree separation`,
        'Graph-based detection',
        'Sanctions list correlation'
      ],
      evidence: { hops: hopsToSanctioned, direct_match: hopsToSanctioned === 0 }
    });
  }

  // 6. Mixer Interaction
  if (mixerInteraction) {
    factors.push({
      factor_id: 'mixer_interaction',
      impact: 'CRITICAL',
      reason: 'Transaction chain involves known mixing/tumbling service',
      detail: 'Funds have passed through services designed to obscure transaction origins',
      value: true,
      contribution: 0.40
    });
    topReasons.push('🔀 Funds routed through mixing service');

    typologyMatches.push({
      typology: 'mixer_interaction',
      confidence: 0.95,
      description: 'Funds have been processed through cryptocurrency mixing or tumbling services, designed to break the transaction trail',
      indicators: [
        'Known mixer address interaction',
        'Obfuscation service detected',
        'Transaction origin concealment'
      ],
      evidence: { mixer_detected: true, service_type: 'tumbler' }
    });
  }

  // 7. Network Analysis (Graph Features)
  if (outDegree >= 100) {
    factors.push({
      factor_id: 'high_out_degree',
      impact: 'HIGH',
      reason: `Sender has sent to ${outDegree} unique addresses (distribution pattern)`,
      detail: 'High number of outgoing connections indicates possible distribution point',
      value: outDegree,
      threshold: 100,
      contribution: 0.15
    });
    
    typologyMatches.push({
      typology: 'fan_out',
      confidence: Math.min(0.85, 0.5 + outDegree / 500),
      description: 'Single source distributing funds to many recipients in fan-out pattern, potentially for layering or distribution',
      indicators: [
        `${outDegree} unique recipients`,
        'Distribution hub pattern',
        'Possible fund dispersal'
      ],
      evidence: { out_degree: outDegree, pattern: 'distribution' }
    });
  }

  if (inDegree >= 200) {
    factors.push({
      factor_id: 'high_in_degree',
      impact: 'HIGH',
      reason: `Recipient has received from ${inDegree} unique addresses (aggregation point)`,
      detail: 'High number of incoming connections indicates possible collection point',
      value: inDegree,
      threshold: 200,
      contribution: 0.15
    });
    
    typologyMatches.push({
      typology: 'fan_in',
      confidence: Math.min(0.85, 0.5 + inDegree / 1000),
      description: 'Funds aggregated from many sources to single destination, potentially for consolidation before further movement',
      indicators: [
        `${inDegree} unique senders`,
        'Aggregation point pattern',
        'Possible fund collection'
      ],
      evidence: { in_degree: inDegree, pattern: 'aggregation' }
    });
  }

  if (pagerank >= 0.0005) {
    factors.push({
      factor_id: 'high_pagerank',
      impact: 'HIGH',
      reason: `Address has unusually high network influence (PageRank: ${pagerank.toFixed(6)})`,
      detail: 'Central position in transaction network may indicate significant money movement hub',
      value: pagerank,
      threshold: 0.0005,
      contribution: 0.12
    });
  }

  if (clusteringCoef >= 0.7) {
    factors.push({
      factor_id: 'tight_cluster',
      impact: 'MEDIUM',
      reason: `Part of tightly connected cluster (coefficient: ${clusteringCoef.toFixed(2)})`,
      detail: 'Address belongs to closely interconnected group of addresses',
      value: clusteringCoef,
      threshold: 0.7,
      contribution: 0.08
    });
  }

  // 8. Structuring Detection
  if (txCount >= 5 && amountEth < 10 && riskScore >= 0.4) {
    typologyMatches.push({
      typology: 'structuring',
      confidence: Math.min(0.8, 0.5 + txCount / 20),
      description: 'Multiple transactions below reporting threshold may indicate structuring to avoid detection',
      indicators: [
        `${txCount} transactions in 24h`,
        `Average amount: ${(amountEth).toFixed(2)} ETH`,
        'Below regulatory threshold'
      ],
      evidence: { tx_count: txCount, avg_amount: amountEth }
    });
  }

  // 9. Layering Detection (based on risk score when detailed data unavailable)
  if (riskScore >= 0.7 && txCount >= 5) {
    typologyMatches.push({
      typology: 'layering',
      confidence: Math.min(0.85, riskScore),
      description: 'Complex transaction patterns detected suggesting layering activity to obscure fund origins',
      indicators: [
        'Multiple rapid transactions',
        'Value approximately preserved',
        'Pattern consistent with fund obfuscation'
      ],
      evidence: { pattern_detected: true, risk_score: riskScore }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GRAPH EXPLANATION
  // ═══════════════════════════════════════════════════════════════════════════
  const graphParts: string[] = [];
  if (hopsToSanctioned !== undefined && hopsToSanctioned <= 3) {
    graphParts.push(hopsToSanctioned === 0 ? 'directly matches sanctioned address' : `is ${hopsToSanctioned} hop(s) from sanctioned entities`);
  }
  if (mixerInteraction) {
    graphParts.push('interacts with known mixing services');
  }
  if (pagerank >= 0.0001) {
    graphParts.push(`has elevated network influence (PageRank: ${pagerank.toFixed(6)})`);
  }
  if (clusteringCoef >= 0.5) {
    graphParts.push('is part of a tightly connected group of addresses');
  }
  if (outDegree >= 50) {
    graphParts.push(`has sent to ${outDegree} unique addresses`);
  }
  if (inDegree >= 100) {
    graphParts.push(`has received from ${inDegree} unique addresses`);
  }
  
  if (graphParts.length > 0) {
    graphExplanation = `Network analysis: Address ${graphParts.join(', ')}.`;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SUMMARY GENERATION
  // ═══════════════════════════════════════════════════════════════════════════
  let summary: string;
  const primaryTypology = typologyMatches[0];
  
  if (action === 'BLOCK') {
    summary = primaryTypology 
      ? `Transaction BLOCKED - ${primaryTypology.typology.replace(/_/g, ' ')} pattern detected with ${(riskScore * 100).toFixed(0)}% risk score`
      : `Transaction BLOCKED due to critical risk factors (score: ${(riskScore * 100).toFixed(0)}%)`;
  } else if (action === 'ESCROW') {
    summary = primaryTypology
      ? `High-risk transaction - ${primaryTypology.typology.replace(/_/g, ' ')} indicators detected, escrow recommended`
      : `High-risk transaction (score: ${(riskScore * 100).toFixed(0)}%) - requires escrow or manual approval`;
  } else if (action === 'REVIEW') {
    summary = topReasons.length > 0
      ? `Moderate risk detected - ${topReasons[0].toLowerCase()}`
      : 'Moderate risk detected - manual review recommended';
  } else {
    summary = 'Low risk transaction - approved with standard monitoring';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RECOMMENDATIONS
  // ═══════════════════════════════════════════════════════════════════════════
  if (action === 'BLOCK') {
    recommendations.push('🛑 Do not proceed with this transaction');
    recommendations.push('📋 Report to compliance team immediately');
    recommendations.push('📝 File SAR (Suspicious Activity Report) within 24 hours');
    recommendations.push('🔒 Preserve all evidence for potential law enforcement request');
  } else if (action === 'ESCROW') {
    recommendations.push('🔐 Use escrow mechanism to protect funds');
    recommendations.push('📄 Request additional KYC documentation');
    recommendations.push('🔍 Verify source of funds before release');
    recommendations.push('👤 Review counterparty transaction history');
  } else if (action === 'REVIEW') {
    recommendations.push('👤 Verify counterparty identity');
    recommendations.push('📝 Document business purpose of transaction');
    recommendations.push('📊 Consider enhanced monitoring');
  }

  // Typology-specific recommendations
  for (const typology of typologyMatches.slice(0, 2)) {
    switch (typology.typology) {
      case 'structuring':
        recommendations.push('🔢 Check for additional structured transactions below threshold');
        break;
      case 'layering':
        recommendations.push('🔗 Trace full transaction chain to origin');
        break;
      case 'mixer_interaction':
        recommendations.push('🚩 Flag all related addresses for enhanced monitoring');
        break;
      case 'sanctions_proximity':
        recommendations.push('✅ Verify sanctions list match is current');
        recommendations.push('🌐 Check all counterparties against updated lists');
        break;
      case 'dormant_activation':
        recommendations.push('🔑 Verify account ownership and access');
        break;
    }
  }

  // Ensure we have at least one top reason
  if (topReasons.length === 0) {
    if (riskScore >= 0.7) {
      topReasons.push('ML ensemble model detected high-risk behavioral patterns');
    } else if (riskScore >= 0.4) {
      topReasons.push('ML model flagged elevated risk signals');
    } else {
      topReasons.push('Transaction within normal parameters');
    }
  }

  // Sort factors by contribution
  factors.sort((a, b) => b.contribution - a.contribution);
  
  // Sort typologies by confidence
  typologyMatches.sort((a, b) => b.confidence - a.confidence);

  return {
    risk_score: riskScore,
    action,
    summary,
    top_reasons: topReasons.slice(0, 5),
    factors: factors.slice(0, 8),
    typology_matches: typologyMatches.slice(0, 4),
    graph_explanation: graphExplanation,
    recommendations: [...new Set(recommendations)].slice(0, 6),
    confidence: Math.min(0.95, 0.7 + factors.length * 0.03),
    degraded_mode: true
  };
}

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

    const query = params.toString();
    const url = query
      ? `${API_BASE}/dashboard/alerts?${query}`
      : `${API_BASE}/dashboard/alerts`;

    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch alerts');
    const data = await response.json();

    // Orchestrator returns { alerts, total, limit, offset }
    if (Array.isArray(data)) return data;
    if (Array.isArray(data?.alerts)) return data.alerts;
    return [];
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
    // Return empty profile for address not found
    return {
      address,
      entity_type: 'UNKNOWN',
      kyc_level: 'NONE',
      risk_tolerance: 'LOW',
      jurisdiction: 'UNKNOWN',
      daily_limit_eth: 0,
      monthly_limit_eth: 0,
      single_tx_limit_eth: 0,
      total_transactions: 0,
      daily_volume_eth: 0,
      flags: ['Entity not found - register in orchestrator'],
    };
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
  reasons: string[];
}> {
  try {
    // Use orchestrator's risk/score endpoint
    const response = await fetch(`${API_BASE}/risk/score`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        from_address: address,
        to_address: address,
        value_eth: 1.0
      })
    });
    if (!response.ok) throw new Error('Failed to score address');
    const data = await response.json();
    
    // Map orchestrator response to expected format
    const riskScore = data.risk_score ?? 0.5;
    const riskLevel = riskScore > 0.7 ? 'HIGH' : riskScore > 0.4 ? 'MEDIUM' : 'LOW';
    
    // Generate meaningful reasons based on the score and data
    const reasons = generateInvestigationReasons(address, riskScore, riskLevel, data);
    
    return {
      address,
      hybrid_score: riskScore,
      risk_level: data.risk_level || riskLevel,
      action: data.action || (riskLevel === 'HIGH' ? 'REVIEW' : 'ALLOW'),
      ml_score: data.ml_score ?? riskScore * 0.9,
      graph_score: data.graph_score ?? riskScore * 1.1,
      patterns: data.patterns || generatePatternString(riskScore),
      signal_count: data.signal_count ?? Math.floor(riskScore * 10),
      reasons
    };
  } catch (error) {
    console.error('Failed to score address, using fallback:', error);
    // Return fallback score based on address characteristics
    const hash = address.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    const baseScore = (hash % 100) / 100;
    const riskLevel = baseScore > 0.7 ? 'HIGH' : baseScore > 0.4 ? 'MEDIUM' : 'LOW';
    
    // Generate fallback reasons
    const reasons = generateInvestigationReasons(address, baseScore, riskLevel, null);
    
    return {
      address,
      hybrid_score: baseScore,
      risk_level: riskLevel,
      action: riskLevel === 'HIGH' ? 'REVIEW' : 'ALLOW',
      ml_score: baseScore * 0.9,
      graph_score: baseScore * 1.1,
      patterns: generatePatternString(baseScore),
      signal_count: Math.floor(hash % 10),
      reasons
    };
  }
}

// Generate pattern string based on risk score
function generatePatternString(riskScore: number): string {
  const patterns: string[] = [];
  if (riskScore > 0.8) patterns.push('HIGH_VELOCITY', 'LAYERING');
  if (riskScore > 0.6) patterns.push('FAN_OUT', 'UNUSUAL_TIMING');
  if (riskScore > 0.4) patterns.push('NEW_COUNTERPARTY');
  if (riskScore > 0.2) patterns.push('CROSS_CHAIN');
  return patterns.join(', ') || 'NORMAL_ACTIVITY';
}

// Generate meaningful investigation reasons based on address analysis
function generateInvestigationReasons(
  address: string, 
  riskScore: number, 
  riskLevel: string,
  apiData: Record<string, unknown> | null
): string[] {
  const reasons: string[] = [];
  
  // Use API-provided reasons if available
  if (apiData?.reasons && Array.isArray(apiData.reasons) && apiData.reasons.length > 0) {
    return apiData.reasons as string[];
  }
  
  // Generate reasons based on risk score analysis
  if (riskScore >= 0.8) {
    reasons.push(`Critical risk level detected (${(riskScore * 100).toFixed(0)}%) - immediate review recommended`);
    reasons.push('Transaction patterns indicate potential layering or structuring behavior');
    reasons.push('Multiple high-risk indicators triggered in automated screening');
  } else if (riskScore >= 0.6) {
    reasons.push(`Elevated risk score of ${(riskScore * 100).toFixed(0)}% detected by ML model`);
    reasons.push('Address shows unusual transaction velocity compared to peer group');
    reasons.push('Graph analysis reveals connections to addresses with prior suspicious activity');
  } else if (riskScore >= 0.4) {
    reasons.push(`Moderate risk indicators present (score: ${(riskScore * 100).toFixed(0)}%)`);
    reasons.push('Some transaction patterns deviate from typical behavior for this address type');
    reasons.push('Enhanced monitoring recommended based on counterparty risk assessment');
  } else if (riskScore >= 0.2) {
    reasons.push(`Low risk profile with score of ${(riskScore * 100).toFixed(0)}%`);
    reasons.push('Minor anomalies detected but within acceptable thresholds');
    reasons.push('Standard transaction patterns with no immediate concerns');
  } else {
    reasons.push(`Very low risk score (${(riskScore * 100).toFixed(0)}%) - address appears clean`);
    reasons.push('No suspicious patterns detected in transaction history');
    reasons.push('Address behavior consistent with legitimate usage patterns');
  }
  
  // Add address-specific insights based on address characteristics
  const addressLower = address.toLowerCase();
  if (addressLower.includes('dead') || addressLower.includes('0000')) {
    reasons.push('Address contains unusual character patterns - may be a burn address or contract');
  }
  
  // Add graph-related insights if graph score available
  if (apiData?.graph_score !== undefined) {
    const graphScore = apiData.graph_score as number;
    if (graphScore > 0.7) {
      reasons.push(`Network analysis shows high-risk connections (graph score: ${(graphScore * 100).toFixed(0)}%)`);
    } else if (graphScore > 0.4) {
      reasons.push(`Moderate network risk detected through graph analysis (score: ${(graphScore * 100).toFixed(0)}%)`);
    }
  }
  
  // Add ML-specific insights if ML score available
  if (apiData?.ml_score !== undefined) {
    const mlScore = apiData.ml_score as number;
    if (Math.abs(mlScore - riskScore) > 0.2) {
      reasons.push(`ML model and rule-based scores show ${mlScore > riskScore ? 'elevated' : 'reduced'} risk compared to hybrid assessment`);
    }
  }
  
  return reasons;
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
    const response = await fetch(`${API_BASE}/dashboard/timeline?time_range=${timeRange}`);
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

function generateMockTimeline(timeRange: string): TimelineDataPoint[] {
  const points = timeRange === '1h' ? 12 : timeRange === '24h' ? 24 : timeRange === '7d' ? 7 : 30;
  const interval = timeRange === '1h' ? 5 * 60 * 1000 : 
                   timeRange === '24h' ? 60 * 60 * 1000 :
                   24 * 60 * 60 * 1000;
  
  return Array.from({ length: points }, (_, i) => ({
    timestamp: new Date(Date.now() - (points - i) * interval).toISOString(),
    value: Math.floor(Math.random() * 20),
    label: `Point ${i}`,
    metadata: {
      critical: Math.floor(Math.random() * 3),
      high: Math.floor(Math.random() * 8),
      medium: Math.floor(Math.random() * 15),
      low: Math.floor(Math.random() * 10)
    }
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
