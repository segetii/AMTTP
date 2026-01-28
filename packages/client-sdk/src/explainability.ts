// src/explainability.ts
/**
 * AMTTP Explainability Service
 * Converts raw ML scores into human-readable explanations for risk decisions.
 * 
 * Features:
 * - Feature-level explanations (why each feature contributed)
 * - Typology matching (what fraud pattern was detected)
 * - Graph-based explanations (network proximity to bad actors)
 * - Regulatory-ready audit trails
 */

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type ImpactLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NEUTRAL';

export type TypologyType = 
  | 'structuring'
  | 'layering'
  | 'round_trip'
  | 'smurfing'
  | 'fan_out'
  | 'fan_in'
  | 'dormant_activation'
  | 'mixer_interaction'
  | 'sanctions_proximity'
  | 'high_risk_geography'
  | 'unusual_timing'
  | 'rapid_movement'
  | 'peeling';

export interface ExplanationFactor {
  /** Unique identifier for this factor */
  factorId: string;
  /** Impact level of this factor */
  impact: ImpactLevel;
  /** Human-readable explanation */
  reason: string;
  /** Technical detail for developers/compliance */
  detail: string;
  /** Raw value that triggered this */
  value: any;
  /** Threshold that was exceeded */
  threshold?: any;
  /** How much this factor contributed (0-1) */
  contribution: number;
}

export interface TypologyMatch {
  /** Type of fraud pattern detected */
  typology: TypologyType;
  /** Confidence score (0-1) */
  confidence: number;
  /** Human-readable description */
  description: string;
  /** Specific indicators that matched */
  indicators: string[];
  /** Supporting evidence */
  evidence: Record<string, any>;
}

export interface GraphExplanation {
  /** One-sentence summary of graph findings */
  summary: string;
  /** Hops to nearest known bad actor */
  hopsToRisk?: number;
  /** PageRank centrality score */
  pageRank?: number;
  /** Community/cluster label */
  community?: string;
  /** Direct connections to flagged addresses */
  flaggedConnections?: string[];
}

export interface RiskExplanation {
  /** Risk score (0-1) */
  riskScore: number;
  /** Recommended action: ALLOW, REVIEW, ESCROW, BLOCK */
  action: 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK';
  /** One-sentence summary for end users */
  summary: string;
  /** Top 3-5 human-readable reasons */
  topReasons: string[];
  /** All contributing factors with details */
  factors: ExplanationFactor[];
  /** Matched fraud typologies */
  typologyMatches: TypologyMatch[];
  /** Graph-based explanation (if available) */
  graphExplanation?: GraphExplanation;
  /** Suggested next steps */
  recommendations: string[];
  /** Confidence in this explanation */
  confidence: number;
  /** Whether running in degraded mode (some services unavailable) */
  degradedMode: boolean;
}

export interface ExplainRequest {
  /** Risk score to explain (0-1) */
  riskScore: number;
  /** Feature values used in scoring */
  features: Record<string, any>;
  /** Graph context (if available) */
  graphContext?: Record<string, any>;
  /** Rule check results (if available) */
  ruleResults?: Array<{ rule: string; triggered: boolean; value: any }>;
  /** Individual model contributions (if available) */
  modelContributions?: Record<string, number>;
}

export interface TransactionExplainRequest {
  /** Transaction hash */
  transactionHash: string;
  /** Risk score (0-1) */
  riskScore: number;
  /** Sender address */
  sender: string;
  /** Receiver address */
  receiver: string;
  /** Amount in ETH */
  amount: number;
  /** Additional features */
  features: Record<string, any>;
  /** Graph context (if available) */
  graphContext?: Record<string, any>;
}

export interface TypologyInfo {
  id: TypologyType;
  name: string;
  description: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TYPOLOGY DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

export const TYPOLOGIES: TypologyInfo[] = [
  {
    id: 'structuring',
    name: 'Structuring',
    description: 'Breaking large transactions into smaller ones to avoid reporting thresholds'
  },
  {
    id: 'layering',
    name: 'Layering',
    description: 'Complex chains of transactions to obscure the source of funds'
  },
  {
    id: 'round_trip',
    name: 'Round Trip',
    description: 'Funds returning to origin through intermediaries'
  },
  {
    id: 'smurfing',
    name: 'Smurfing',
    description: 'Using multiple accounts/people to move funds'
  },
  {
    id: 'fan_out',
    name: 'Fan Out',
    description: 'Single source distributing to many destinations'
  },
  {
    id: 'fan_in',
    name: 'Fan In',
    description: 'Many sources consolidating to single destination'
  },
  {
    id: 'dormant_activation',
    name: 'Dormant Account Activation',
    description: 'Previously inactive account suddenly active with large amounts'
  },
  {
    id: 'mixer_interaction',
    name: 'Mixer Interaction',
    description: 'Funds passing through known mixing services'
  },
  {
    id: 'sanctions_proximity',
    name: 'Sanctions Proximity',
    description: 'Close network connection to sanctioned entities'
  },
  {
    id: 'high_risk_geography',
    name: 'High Risk Geography',
    description: 'Transaction involving FATF high-risk jurisdictions'
  },
  {
    id: 'unusual_timing',
    name: 'Unusual Timing',
    description: 'Transactions at atypical hours or rapid succession'
  },
  {
    id: 'rapid_movement',
    name: 'Rapid Movement',
    description: 'Funds moved through multiple hops in short time'
  },
  {
    id: 'peeling',
    name: 'Peeling Chain',
    description: 'Sequential transactions that progressively reduce amounts'
  }
];

// ═══════════════════════════════════════════════════════════════════════════════
// EXPLAINABILITY SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export class ExplainabilityService {
  private baseUrl: string;
  private timeout: number;

  constructor(baseUrl: string = 'http://localhost:8009', timeout: number = 5000) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.timeout = timeout;
  }

  /**
   * Get human-readable explanation for a risk score.
   * 
   * @example
   * ```typescript
   * const explanation = await explainer.explain({
   *   riskScore: 0.73,
   *   features: {
   *     amount_eth: 50,
   *     tx_count_24h: 15,
   *     hops_to_sanctioned: 2
   *   }
   * });
   * 
   * console.log(explanation.summary);
   * // "High-risk transaction due to large amount and proximity to flagged addresses"
   * 
   * console.log(explanation.topReasons);
   * // ["Large transaction (50 ETH)", "2 hops from sanctioned address", "Above-average activity"]
   * ```
   */
  async explain(request: ExplainRequest): Promise<RiskExplanation> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}/explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          risk_score: request.riskScore,
          features: request.features,
          graph_context: request.graphContext,
          rule_results: request.ruleResults,
          model_contributions: request.modelContributions
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Explainability service error: ${response.status}`);
      }

      const data = await response.json();
      return this.transformResponse(data);
    } catch (error: any) {
      clearTimeout(timeoutId);
      
      // Fallback to local explanation if service unavailable
      if (error.name === 'AbortError' || error.message.includes('fetch')) {
        return this.generateLocalExplanation(request);
      }
      throw error;
    }
  }

  /**
   * Get explanation for a specific transaction.
   * 
   * @example
   * ```typescript
   * const explanation = await explainer.explainTransaction({
   *   transactionHash: '0xabc123...',
   *   riskScore: 0.85,
   *   sender: '0x1234...',
   *   receiver: '0xabcd...',
   *   amount: 100,
   *   features: { tx_count_24h: 25 }
   * });
   * ```
   */
  async explainTransaction(request: TransactionExplainRequest): Promise<RiskExplanation & { transaction: { hash: string; sender: string; receiver: string; amount: number } }> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(`${this.baseUrl}/explain/transaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          transaction_hash: request.transactionHash,
          risk_score: request.riskScore,
          sender: request.sender,
          receiver: request.receiver,
          amount: request.amount,
          features: request.features,
          graph_context: request.graphContext
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Explainability service error: ${response.status}`);
      }

      const data = await response.json();
      return {
        ...this.transformResponse(data),
        transaction: {
          hash: request.transactionHash,
          sender: request.sender,
          receiver: request.receiver,
          amount: request.amount
        }
      };
    } catch (error: any) {
      clearTimeout(timeoutId);
      
      // Fallback to local explanation
      const localExplanation = this.generateLocalExplanation({
        riskScore: request.riskScore,
        features: { ...request.features, amount_eth: request.amount }
      });
      
      return {
        ...localExplanation,
        transaction: {
          hash: request.transactionHash,
          sender: request.sender,
          receiver: request.receiver,
          amount: request.amount
        }
      };
    }
  }

  /**
   * List all known fraud typologies.
   */
  async getTypologies(): Promise<TypologyInfo[]> {
    try {
      const response = await fetch(`${this.baseUrl}/typologies`);
      if (!response.ok) throw new Error('Service unavailable');
      const data = await response.json();
      return data.typologies;
    } catch {
      return TYPOLOGIES;
    }
  }

  /**
   * Check if the explainability service is healthy.
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // PRIVATE METHODS
  // ─────────────────────────────────────────────────────────────────────────────

  private transformResponse(data: any): RiskExplanation {
    return {
      riskScore: data.risk_score,
      action: data.action,
      summary: data.summary,
      topReasons: data.top_reasons,
      factors: (data.factors || []).map((f: any) => ({
        factorId: f.factor_id,
        impact: f.impact,
        reason: f.reason,
        detail: f.detail,
        value: f.value,
        threshold: f.threshold,
        contribution: f.contribution
      })),
      typologyMatches: (data.typology_matches || []).map((t: any) => ({
        typology: t.typology,
        confidence: t.confidence,
        description: t.description,
        indicators: t.indicators,
        evidence: t.evidence
      })),
      graphExplanation: data.graph_explanation ? {
        summary: data.graph_explanation
      } : undefined,
      recommendations: data.recommendations || [],
      confidence: data.confidence,
      degradedMode: data.degraded_mode
    };
  }

  /**
   * Generate explanation locally when service is unavailable.
   * Uses simplified rule-based logic.
   */
  private generateLocalExplanation(request: ExplainRequest): RiskExplanation {
    const { riskScore, features } = request;
    const factors: ExplanationFactor[] = [];
    const topReasons: string[] = [];
    const typologyMatches: TypologyMatch[] = [];
    
    // Determine action based on score
    let action: 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK';
    if (riskScore >= 0.85) action = 'BLOCK';
    else if (riskScore >= 0.70) action = 'ESCROW';
    else if (riskScore >= 0.40) action = 'REVIEW';
    else action = 'ALLOW';

    // Amount analysis
    const amountEth = features.amount_eth || features.value_eth || 0;
    if (amountEth >= 100) {
      factors.push({
        factorId: 'large_amount',
        impact: 'HIGH',
        reason: `Large transaction amount (${amountEth} ETH)`,
        detail: 'Transaction amount exceeds typical threshold for enhanced monitoring',
        value: amountEth,
        threshold: 100,
        contribution: 0.25
      });
      topReasons.push(`Large transaction (${amountEth} ETH)`);
    } else if (amountEth >= 10) {
      factors.push({
        factorId: 'medium_amount',
        impact: 'MEDIUM',
        reason: `Above-average amount (${amountEth} ETH)`,
        detail: 'Transaction amount above typical range',
        value: amountEth,
        threshold: 10,
        contribution: 0.10
      });
    }

    // Velocity analysis
    const txCount24h = features.tx_count_24h || features.velocity_24h || 0;
    if (txCount24h >= 20) {
      factors.push({
        factorId: 'high_velocity',
        impact: 'HIGH',
        reason: `High transaction velocity (${txCount24h} in 24h)`,
        detail: 'Unusually high number of transactions in short period',
        value: txCount24h,
        threshold: 20,
        contribution: 0.20
      });
      topReasons.push(`${txCount24h} transactions in 24 hours`);
      
      // Potential structuring
      if (amountEth && amountEth < 10) {
        typologyMatches.push({
          typology: 'structuring',
          confidence: 0.6,
          description: 'Multiple small transactions may indicate structuring',
          indicators: ['High transaction count', 'Below-threshold amounts'],
          evidence: { txCount24h, averageAmount: amountEth }
        });
      }
    }

    // Sanctions proximity
    const hopsToSanctioned = features.hops_to_sanctioned;
    if (hopsToSanctioned !== undefined && hopsToSanctioned <= 2) {
      const impact: ImpactLevel = hopsToSanctioned === 0 ? 'CRITICAL' : hopsToSanctioned === 1 ? 'HIGH' : 'MEDIUM';
      factors.push({
        factorId: 'sanctions_proximity',
        impact,
        reason: hopsToSanctioned === 0 
          ? 'Direct sanctioned address match'
          : `${hopsToSanctioned} hop(s) from sanctioned address`,
        detail: 'Network proximity to known sanctioned entities',
        value: hopsToSanctioned,
        threshold: 2,
        contribution: hopsToSanctioned === 0 ? 0.5 : 0.3
      });
      topReasons.push(hopsToSanctioned === 0 
        ? 'Sanctioned address' 
        : `${hopsToSanctioned} hop(s) from sanctioned address`);
      
      typologyMatches.push({
        typology: 'sanctions_proximity',
        confidence: hopsToSanctioned === 0 ? 1.0 : 0.8,
        description: 'Connection to sanctioned entities detected',
        indicators: ['Network analysis', 'Graph traversal'],
        evidence: { hops: hopsToSanctioned }
      });
    }

    // Dormancy
    const dormancyDays = features.dormancy_days || features.account_age_days;
    if (dormancyDays && dormancyDays > 180 && amountEth > 10) {
      factors.push({
        factorId: 'dormant_activation',
        impact: 'HIGH',
        reason: `Dormant account (${dormancyDays} days) with large transaction`,
        detail: 'Previously inactive account suddenly moving significant funds',
        value: dormancyDays,
        threshold: 180,
        contribution: 0.15
      });
      topReasons.push(`Account inactive for ${dormancyDays} days`);
      
      typologyMatches.push({
        typology: 'dormant_activation',
        confidence: 0.7,
        description: 'Dormant account suddenly activated with large transfer',
        indicators: ['Long dormancy period', 'Large transaction amount'],
        evidence: { dormancyDays, amountEth }
      });
    }

    // Generate summary
    let summary: string;
    if (action === 'BLOCK') {
      summary = 'Transaction blocked due to critical risk factors';
    } else if (action === 'ESCROW') {
      summary = `High-risk transaction (score: ${(riskScore * 100).toFixed(0)}%) - requires escrow or manual approval`;
    } else if (action === 'REVIEW') {
      summary = 'Moderate risk detected - manual review recommended';
    } else {
      summary = 'Low risk transaction - approved';
    }

    // Generate recommendations
    const recommendations: string[] = [];
    if (action === 'BLOCK') {
      recommendations.push('Do not proceed with this transaction');
      recommendations.push('Report to compliance team');
    } else if (action === 'ESCROW') {
      recommendations.push('Request additional KYC documentation');
      recommendations.push('Consider using escrow mechanism');
      recommendations.push('Verify source of funds');
    } else if (action === 'REVIEW') {
      recommendations.push('Verify counterparty identity');
      recommendations.push('Document business purpose');
    }

    // Ensure we have at least one reason
    if (topReasons.length === 0) {
      if (riskScore >= 0.5) {
        topReasons.push('ML model detected elevated risk patterns');
      } else {
        topReasons.push('Transaction within normal parameters');
      }
    }

    return {
      riskScore,
      action,
      summary,
      topReasons: topReasons.slice(0, 5),
      factors,
      typologyMatches,
      recommendations,
      confidence: 0.7, // Lower confidence for local explanation
      degradedMode: true
    };
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONVENIENCE EXPORTS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Create a default explainability service instance.
 */
export function createExplainabilityService(baseUrl?: string): ExplainabilityService {
  return new ExplainabilityService(baseUrl);
}

/**
 * Format an explanation for display (HTML-safe).
 */
export function formatExplanationForDisplay(explanation: RiskExplanation): string {
  const lines: string[] = [];
  
  lines.push(`Risk Score: ${(explanation.riskScore * 100).toFixed(1)}%`);
  lines.push(`Action: ${explanation.action}`);
  lines.push('');
  lines.push(explanation.summary);
  lines.push('');
  lines.push('Key Factors:');
  explanation.topReasons.forEach((reason, i) => {
    lines.push(`  ${i + 1}. ${reason}`);
  });
  
  if (explanation.typologyMatches.length > 0) {
    lines.push('');
    lines.push('Detected Patterns:');
    explanation.typologyMatches.forEach(t => {
      lines.push(`  • ${t.description} (${(t.confidence * 100).toFixed(0)}% confidence)`);
    });
  }
  
  if (explanation.recommendations.length > 0) {
    lines.push('');
    lines.push('Recommendations:');
    explanation.recommendations.forEach(rec => {
      lines.push(`  • ${rec}`);
    });
  }
  
  return lines.join('\n');
}
