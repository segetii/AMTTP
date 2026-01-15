/**
 * AMTTP Risk Explainability Module
 * 
 * Converts raw ML scores into human-readable explanations for risk decisions.
 * This module provides regulatory-compliant audit trails with clear reasoning.
 */

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export enum ImpactLevel {
  CRITICAL = 'CRITICAL',
  HIGH = 'HIGH',
  MEDIUM = 'MEDIUM',
  LOW = 'LOW',
  NEUTRAL = 'NEUTRAL'
}

export enum TypologyType {
  STRUCTURING = 'structuring',
  LAYERING = 'layering',
  ROUND_TRIP = 'round_trip',
  SMURFING = 'smurfing',
  FAN_OUT = 'fan_out',
  FAN_IN = 'fan_in',
  DORMANT_ACTIVATION = 'dormant_activation',
  MIXER_INTERACTION = 'mixer_interaction',
  SANCTIONS_PROXIMITY = 'sanctions_proximity',
  HIGH_RISK_GEOGRAPHY = 'high_risk_geography',
  RAPID_MOVEMENT = 'rapid_movement'
}

export interface ExplanationFactor {
  factorId: string;
  impact: ImpactLevel;
  humanReadable: string;
  technicalDetail: string;
  value: any;
  threshold?: any;
  contribution: number;
}

export interface TypologyMatch {
  typology: TypologyType;
  confidence: number;
  description: string;
  indicators: string[];
  evidence: Record<string, any>;
}

export interface RiskExplanation {
  riskScore: number;
  action: 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK';
  summary: string;
  topReasons: string[];
  factors: ExplanationFactor[];
  typologyMatches: TypologyMatch[];
  graphExplanation: string | null;
  recommendations: string[];
  confidence: number;
  degradedMode: boolean;
}

export interface RiskFeatures {
  // Amount features
  amountEth?: number;
  amountVsAverage?: number;
  avgAmount30d?: number;
  
  // Velocity features
  txCount1h?: number;
  txCount24h?: number;
  uniqueRecipients24h?: number;
  uniqueSenders24h?: number;
  
  // Timing features
  dormancyDays?: number;
  unusualHour?: number;
  
  // Model scores (internal)
  xgbProb?: number;
  lgbProb?: number;
  vaeReconError?: number;
  sageProb?: number;
  metaProb?: number;
  
  // Compliance features
  sanctionsMatch?: boolean;
  sanctionsList?: string;
  pepMatch?: boolean;
  pepCategory?: string;
  fatfCountryRisk?: string;
  countryCode?: string;
}

export interface GraphContext {
  pagerank?: number;
  inDegree?: number;
  outDegree?: number;
  clusteringCoefficient?: number;
  hopsToSanctioned?: number;
  hopsToMixer?: number;
  mixerInteraction?: boolean;
  degradedMode?: boolean;
}

export interface RuleResult {
  ruleType: string;
  triggered: boolean;
  severity?: string;
  confidence?: number;
  description?: string;
  evidence?: Record<string, any>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// FEATURE TEMPLATES
// ═══════════════════════════════════════════════════════════════════════════════

interface FeatureTemplate {
  name: string;
  templates: Partial<Record<ImpactLevel, string>>;
  thresholds: Partial<Record<ImpactLevel, number | string>>;
  internalOnly?: boolean;
}

const FEATURE_TEMPLATES: Record<string, FeatureTemplate> = {
  amountEth: {
    name: 'Transaction Amount',
    templates: {
      [ImpactLevel.CRITICAL]: 'Transaction amount ({value} ETH, ~${usdValue}) exceeds critical threshold',
      [ImpactLevel.HIGH]: 'Large transaction ({value} ETH, ~${usdValue}) is {ratio}x larger than sender\'s average',
      [ImpactLevel.MEDIUM]: 'Transaction amount ({value} ETH) is above typical for this address'
    },
    thresholds: {
      [ImpactLevel.CRITICAL]: 1000,
      [ImpactLevel.HIGH]: 100,
      [ImpactLevel.MEDIUM]: 10
    }
  },
  
  amountVsAverage: {
    name: 'Amount vs Historical Average',
    templates: {
      [ImpactLevel.HIGH]: 'Transaction is {value}x larger than sender\'s 30-day average (${avg})',
      [ImpactLevel.MEDIUM]: 'Transaction is {value}x larger than typical'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 10,
      [ImpactLevel.MEDIUM]: 3
    }
  },
  
  txCount1h: {
    name: 'Transaction Velocity (1 hour)',
    templates: {
      [ImpactLevel.HIGH]: 'Unusually high activity: {value} transactions in the last hour',
      [ImpactLevel.MEDIUM]: 'Elevated activity: {value} transactions in the last hour'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 10,
      [ImpactLevel.MEDIUM]: 5
    }
  },
  
  dormancyDays: {
    name: 'Account Dormancy',
    templates: {
      [ImpactLevel.HIGH]: 'Account was dormant for {value} days before this activity',
      [ImpactLevel.MEDIUM]: 'Account was inactive for {value} days'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 180,
      [ImpactLevel.MEDIUM]: 90
    }
  },
  
  hopsToSanctioned: {
    name: 'Proximity to Sanctioned Addresses',
    templates: {
      [ImpactLevel.CRITICAL]: 'Recipient IS a sanctioned address (OFAC/HMT/EU/UN match)',
      [ImpactLevel.HIGH]: 'Recipient has received funds from sanctioned addresses ({value} hop away)',
      [ImpactLevel.MEDIUM]: 'Transaction chain connects to sanctioned address ({value} hops away)'
    },
    thresholds: {
      [ImpactLevel.CRITICAL]: 0,
      [ImpactLevel.HIGH]: 1,
      [ImpactLevel.MEDIUM]: 2
    }
  },
  
  inDegree: {
    name: 'Incoming Connections',
    templates: {
      [ImpactLevel.HIGH]: 'Recipient has received from {value} unique addresses (possible aggregation point)',
      [ImpactLevel.MEDIUM]: 'Recipient has above-average incoming connections ({value})'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 1000,
      [ImpactLevel.MEDIUM]: 100
    }
  },
  
  outDegree: {
    name: 'Outgoing Connections',
    templates: {
      [ImpactLevel.HIGH]: 'Sender has sent to {value} unique addresses (possible distribution point)',
      [ImpactLevel.MEDIUM]: 'Sender has above-average outgoing connections ({value})'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 500,
      [ImpactLevel.MEDIUM]: 50
    }
  },
  
  pagerank: {
    name: 'Network Importance',
    templates: {
      [ImpactLevel.HIGH]: 'Address has unusually high network influence (PageRank: {value})',
      [ImpactLevel.MEDIUM]: 'Address has elevated network centrality'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 0.001,
      [ImpactLevel.MEDIUM]: 0.0001
    }
  },
  
  clusteringCoefficient: {
    name: 'Network Clustering',
    templates: {
      [ImpactLevel.HIGH]: 'Address is part of a tightly connected cluster (coef: {value})',
      [ImpactLevel.MEDIUM]: 'Address shows elevated clustering with related addresses'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 0.8,
      [ImpactLevel.MEDIUM]: 0.5
    }
  },
  
  sanctionsMatch: {
    name: 'Sanctions Match',
    templates: {
      [ImpactLevel.CRITICAL]: 'Direct match on {listName} sanctions list'
    },
    thresholds: {}
  },
  
  fatfCountryRisk: {
    name: 'Geographic Risk',
    templates: {
      [ImpactLevel.CRITICAL]: 'Transaction involves FATF blacklisted jurisdiction ({country})',
      [ImpactLevel.HIGH]: 'Transaction involves FATF grey-listed jurisdiction ({country})',
      [ImpactLevel.MEDIUM]: 'Transaction involves higher-risk jurisdiction ({country})'
    },
    thresholds: {
      [ImpactLevel.CRITICAL]: 'blacklist',
      [ImpactLevel.HIGH]: 'greylist'
    }
  },
  
  // Internal model scores - don't expose raw values
  xgbProb: {
    name: 'ML Risk Score',
    templates: {
      [ImpactLevel.HIGH]: 'Machine learning model detected high-risk patterns',
      [ImpactLevel.MEDIUM]: 'Machine learning model detected moderate risk signals'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 0.7,
      [ImpactLevel.MEDIUM]: 0.4
    },
    internalOnly: true
  },
  
  vaeReconError: {
    name: 'Anomaly Score',
    templates: {
      [ImpactLevel.HIGH]: 'Transaction pattern is highly unusual compared to normal behavior',
      [ImpactLevel.MEDIUM]: 'Transaction shows some unusual characteristics'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 2.0,
      [ImpactLevel.MEDIUM]: 1.5
    },
    internalOnly: true
  },
  
  sageProb: {
    name: 'Network Risk Score',
    templates: {
      [ImpactLevel.HIGH]: 'Network analysis indicates high-risk transaction pattern',
      [ImpactLevel.MEDIUM]: 'Network analysis shows elevated risk signals'
    },
    thresholds: {
      [ImpactLevel.HIGH]: 0.7,
      [ImpactLevel.MEDIUM]: 0.4
    },
    internalOnly: true
  }
};

// ═══════════════════════════════════════════════════════════════════════════════
// EXPLAINER CLASS
// ═══════════════════════════════════════════════════════════════════════════════

export class RiskExplainer {
  private ethPriceUsd: number;
  
  constructor(ethPriceUsd: number = 2500) {
    this.ethPriceUsd = ethPriceUsd;
  }
  
  /**
   * Generate a complete explanation for a risk decision
   */
  explain(
    riskScore: number,
    features: RiskFeatures,
    graphContext: GraphContext = {},
    ruleResults: RuleResult[] = []
  ): RiskExplanation {
    // Determine action
    const action = this.determineAction(riskScore);
    
    // Explain individual features
    const factors = this.explainFeatures(features, graphContext);
    
    // Sort by contribution
    factors.sort((a, b) => b.contribution - a.contribution);
    
    // Match typologies
    const typologyMatches = this.matchTypologies(features, graphContext, ruleResults);
    
    // Generate top reasons
    const topReasons = this.generateTopReasons(factors, typologyMatches, ruleResults);
    
    // Generate summary
    const summary = this.generateSummary(riskScore, action, topReasons, typologyMatches);
    
    // Generate graph explanation
    const graphExplanation = this.generateGraphExplanation(graphContext);
    
    // Generate recommendations
    const recommendations = this.generateRecommendations(action, factors, typologyMatches);
    
    // Estimate confidence
    const confidence = this.estimateConfidence(factors, graphContext);
    
    return {
      riskScore,
      action,
      summary,
      topReasons: topReasons.slice(0, 5),
      factors,
      typologyMatches,
      graphExplanation,
      recommendations,
      confidence,
      degradedMode: graphContext.degradedMode ?? false
    };
  }
  
  private determineAction(riskScore: number): 'ALLOW' | 'REVIEW' | 'ESCROW' | 'BLOCK' {
    if (riskScore < 0.4) return 'ALLOW';
    if (riskScore < 0.7) return 'REVIEW';
    if (riskScore < 0.8) return 'ESCROW';
    return 'BLOCK';
  }
  
  private explainFeatures(features: RiskFeatures, graphContext: GraphContext): ExplanationFactor[] {
    const factors: ExplanationFactor[] = [];
    const allFeatures = { ...features, ...graphContext };
    
    for (const [key, value] of Object.entries(allFeatures)) {
      if (value === undefined || value === null) continue;
      
      // Convert camelCase to match template keys
      const templateKey = key;
      const template = FEATURE_TEMPLATES[templateKey];
      
      if (!template) continue;
      
      const impact = this.determineImpact(templateKey, value, template.thresholds);
      if (impact === ImpactLevel.NEUTRAL) continue;
      
      const humanReadable = this.formatTemplate(template.templates[impact], {
        value,
        usdValue: typeof value === 'number' ? this.formatCurrency(value * this.ethPriceUsd) : '0',
        ratio: features.amountVsAverage ?? 1,
        avg: this.formatCurrency(features.avgAmount30d ?? 0),
        listName: features.sanctionsList ?? 'OFAC',
        country: features.countryCode ?? 'Unknown'
      });
      
      if (!humanReadable) continue;
      
      factors.push({
        factorId: key,
        impact,
        humanReadable,
        technicalDetail: `${template.name}: ${value}`,
        value,
        threshold: template.thresholds[impact],
        contribution: this.estimateContribution(impact)
      });
    }
    
    return factors;
  }
  
  private determineImpact(
    featureName: string,
    value: any,
    thresholds: Partial<Record<ImpactLevel, number | string>>
  ): ImpactLevel {
    if (!thresholds || Object.keys(thresholds).length === 0) {
      return ImpactLevel.NEUTRAL;
    }
    
    // For numeric values
    if (typeof value === 'number') {
      for (const level of [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]) {
        const threshold = thresholds[level];
        if (typeof threshold === 'number' && value >= threshold) {
          return level;
        }
      }
      return value > 0 ? ImpactLevel.LOW : ImpactLevel.NEUTRAL;
    }
    
    // For boolean values
    if (typeof value === 'boolean') {
      return value ? ImpactLevel.HIGH : ImpactLevel.NEUTRAL;
    }
    
    // For string values (like country risk)
    if (typeof value === 'string') {
      for (const level of [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]) {
        if (thresholds[level] === value) {
          return level;
        }
      }
    }
    
    return ImpactLevel.NEUTRAL;
  }
  
  private estimateContribution(impact: ImpactLevel): number {
    const contributions: Record<ImpactLevel, number> = {
      [ImpactLevel.CRITICAL]: 0.5,
      [ImpactLevel.HIGH]: 0.25,
      [ImpactLevel.MEDIUM]: 0.15,
      [ImpactLevel.LOW]: 0.05,
      [ImpactLevel.NEUTRAL]: 0
    };
    return contributions[impact] ?? 0;
  }
  
  private formatTemplate(template: string | undefined, context: Record<string, any>): string {
    if (!template) return '';
    
    return template.replace(/\{(\w+)\}/g, (match, key) => {
      const value = context[key];
      if (value === undefined) return match;
      if (typeof value === 'number') {
        return value.toFixed(value < 1 ? 4 : 2);
      }
      return String(value);
    });
  }
  
  private formatCurrency(value: number): string {
    return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
  }
  
  private matchTypologies(
    features: RiskFeatures,
    graphContext: GraphContext,
    ruleResults: RuleResult[]
  ): TypologyMatch[] {
    const matches: TypologyMatch[] = [];
    
    // Check rule-based typologies
    for (const rule of ruleResults) {
      if (!rule.triggered) continue;
      
      switch (rule.ruleType) {
        case 'STRUCTURING':
          matches.push({
            typology: TypologyType.STRUCTURING,
            confidence: rule.confidence ?? 0.8,
            description: 'Multiple transactions just below reporting threshold, potentially to avoid detection',
            indicators: [
              `Total volume: ${rule.evidence?.totalValueEth ?? 0} ETH`,
              `Transaction count: ${rule.evidence?.transactionCount ?? 0}`,
              'Each transaction < threshold'
            ],
            evidence: rule.evidence ?? {}
          });
          break;
          
        case 'LAYERING':
          matches.push({
            typology: TypologyType.LAYERING,
            confidence: rule.confidence ?? 0.85,
            description: 'Complex transaction chain detected, potentially to obscure fund origin',
            indicators: [
              `Chain length: ${rule.evidence?.chainLength ?? 0} hops`,
              'Rapid movement between addresses',
              'Value approximately preserved through chain'
            ],
            evidence: rule.evidence ?? {}
          });
          break;
          
        case 'ROUND_TRIP':
          matches.push({
            typology: TypologyType.ROUND_TRIP,
            confidence: rule.confidence ?? 0.9,
            description: 'Funds sent and returned to origin, potentially for artificial volume',
            indicators: [
              `Sent: ${rule.evidence?.sentValueEth ?? 0} ETH`,
              `Returned: ${rule.evidence?.returnedValueEth ?? 0} ETH`,
              `Via ${rule.evidence?.hopCount ?? 0} intermediary(ies)`
            ],
            evidence: rule.evidence ?? {}
          });
          break;
      }
    }
    
    // Check graph-based typologies
    if (features.sanctionsMatch) {
      matches.push({
        typology: TypologyType.SANCTIONS_PROXIMITY,
        confidence: 1.0,
        description: 'Direct sanctions list match',
        indicators: [
          'Address appears on OFAC/HMT/EU/UN sanctions list',
          'Transaction MUST be blocked'
        ],
        evidence: { directMatch: true, hops: 0 }
      });
    } else if (graphContext.hopsToSanctioned !== undefined && graphContext.hopsToSanctioned <= 3) {
      matches.push({
        typology: TypologyType.SANCTIONS_PROXIMITY,
        confidence: 0.9 - (graphContext.hopsToSanctioned * 0.2),
        description: `Transaction chain ${graphContext.hopsToSanctioned} hop(s) from sanctioned address`,
        indicators: [
          `Counterparty is ${graphContext.hopsToSanctioned} hop(s) from sanctioned entity`,
          'Elevated risk due to sanctions proximity'
        ],
        evidence: { hops: graphContext.hopsToSanctioned }
      });
    }
    
    if (graphContext.mixerInteraction || (graphContext.hopsToMixer !== undefined && graphContext.hopsToMixer <= 2)) {
      matches.push({
        typology: TypologyType.MIXER_INTERACTION,
        confidence: graphContext.hopsToMixer === 0 ? 0.95 : 0.7,
        description: 'Transaction chain involves known mixing/tumbling service',
        indicators: [
          graphContext.hopsToMixer !== undefined 
            ? `Distance to mixer: ${graphContext.hopsToMixer} hop(s)` 
            : 'Direct mixer interaction',
          'Mixing services obscure transaction origin'
        ],
        evidence: { mixerInteraction: true, hopsToMixer: graphContext.hopsToMixer }
      });
    }
    
    // Check dormancy
    if (features.dormancyDays && features.dormancyDays >= 180) {
      matches.push({
        typology: TypologyType.DORMANT_ACTIVATION,
        confidence: Math.min(0.85, 0.5 + features.dormancyDays / 365),
        description: 'Account reactivated after extended dormancy',
        indicators: [
          `Account was inactive for ${features.dormancyDays} days`,
          'Sudden activity after long dormancy is a risk indicator'
        ],
        evidence: { dormancyDays: features.dormancyDays }
      });
    }
    
    // Sort by confidence
    matches.sort((a, b) => b.confidence - a.confidence);
    return matches;
  }
  
  private generateTopReasons(
    factors: ExplanationFactor[],
    typologyMatches: TypologyMatch[],
    ruleResults: RuleResult[]
  ): string[] {
    const reasons: string[] = [];
    const seen = new Set<string>();
    
    // Add typology-based reasons first
    for (const typology of typologyMatches.slice(0, 2)) {
      if (!seen.has(typology.description)) {
        reasons.push(typology.description);
        seen.add(typology.description);
      }
    }
    
    // Add rule-based reasons
    for (const rule of ruleResults) {
      if (rule.triggered && rule.description && !seen.has(rule.description)) {
        reasons.push(rule.description);
        seen.add(rule.description);
      }
    }
    
    // Add factor-based reasons
    for (const factor of factors) {
      if (
        (factor.impact === ImpactLevel.CRITICAL || factor.impact === ImpactLevel.HIGH) &&
        !FEATURE_TEMPLATES[factor.factorId]?.internalOnly &&
        !seen.has(factor.humanReadable)
      ) {
        reasons.push(factor.humanReadable);
        seen.add(factor.humanReadable);
      }
    }
    
    return reasons;
  }
  
  private generateSummary(
    riskScore: number,
    action: string,
    topReasons: string[],
    typologyMatches: TypologyMatch[]
  ): string {
    const actionContext: Record<string, string> = {
      ALLOW: 'Transaction approved with low risk',
      REVIEW: 'Transaction flagged for manual review',
      ESCROW: 'Transaction held in escrow pending investigation',
      BLOCK: 'Transaction blocked due to high risk'
    };
    
    let summary = actionContext[action] ?? 'Transaction evaluated';
    
    if (typologyMatches.length > 0) {
      summary += ` - ${typologyMatches[0].typology} pattern detected`;
    } else if (topReasons.length > 0) {
      const reason = topReasons[0].length > 80 
        ? topReasons[0].substring(0, 77) + '...'
        : topReasons[0];
      summary += ` - ${reason}`;
    }
    
    return summary;
  }
  
  private generateGraphExplanation(graphContext: GraphContext): string | null {
    if (!graphContext || Object.keys(graphContext).length === 0) {
      return null;
    }
    
    const parts: string[] = [];
    
    if (graphContext.hopsToSanctioned !== undefined) {
      if (graphContext.hopsToSanctioned === 0) {
        parts.push('directly matches sanctioned address');
      } else {
        parts.push(`is ${graphContext.hopsToSanctioned} hop(s) from sanctioned entities`);
      }
    }
    
    if (graphContext.mixerInteraction) {
      parts.push('interacts with known mixing services');
    }
    
    if (graphContext.pagerank && graphContext.pagerank > 0.0001) {
      parts.push(`has elevated network influence (PageRank: ${graphContext.pagerank.toFixed(4)})`);
    }
    
    if (graphContext.clusteringCoefficient && graphContext.clusteringCoefficient > 0.5) {
      parts.push('is part of a tightly connected group');
    }
    
    if (parts.length > 0) {
      return 'Network analysis: Address ' + parts.join(', ') + '.';
    }
    
    return null;
  }
  
  private generateRecommendations(
    action: string,
    factors: ExplanationFactor[],
    typologyMatches: TypologyMatch[]
  ): string[] {
    const recommendations: string[] = [];
    
    if (action === 'BLOCK') {
      recommendations.push('File SAR within 24 hours');
      recommendations.push('Preserve all evidence for potential law enforcement request');
    }
    
    if (action === 'ESCROW' || action === 'REVIEW') {
      recommendations.push('Request additional KYC documentation');
      recommendations.push('Review counterparty transaction history');
    }
    
    // Typology-specific recommendations
    for (const typology of typologyMatches) {
      switch (typology.typology) {
        case TypologyType.STRUCTURING:
          recommendations.push('Check for additional structured transactions');
          break;
        case TypologyType.LAYERING:
          recommendations.push('Trace full transaction chain origin');
          break;
        case TypologyType.MIXER_INTERACTION:
          recommendations.push('Flag all related addresses for enhanced monitoring');
          break;
        case TypologyType.SANCTIONS_PROXIMITY:
          recommendations.push('Verify sanctions list match is current');
          break;
      }
    }
    
    return recommendations.slice(0, 5);
  }
  
  private estimateConfidence(factors: ExplanationFactor[], graphContext: GraphContext): number {
    let confidence = 0.7;
    
    // Higher confidence if we have graph data
    if (graphContext && !graphContext.degradedMode) {
      confidence += 0.1;
    }
    
    // Higher confidence with more high-impact factors
    const highImpactCount = factors.filter(
      f => f.impact === ImpactLevel.CRITICAL || f.impact === ImpactLevel.HIGH
    ).length;
    confidence += Math.min(0.15, highImpactCount * 0.05);
    
    return Math.min(0.95, confidence);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONVENIENCE FUNCTION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Generate a risk explanation
 * 
 * @example
 * const explanation = explainRiskDecision(0.73, {
 *   amountEth: 847.5,
 *   amountVsAverage: 12.3,
 *   dormancyDays: 190
 * }, {
 *   hopsToSanctioned: 2,
 *   pagerank: 0.0003
 * });
 */
export function explainRiskDecision(
  riskScore: number,
  features: RiskFeatures,
  graphContext: GraphContext = {},
  ruleResults: RuleResult[] = [],
  ethPriceUsd: number = 2500
): RiskExplanation {
  const explainer = new RiskExplainer(ethPriceUsd);
  return explainer.explain(riskScore, features, graphContext, ruleResults);
}
