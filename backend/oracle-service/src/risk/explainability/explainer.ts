/**
 * Core Risk Explainer Engine
 * 
 * The main class that generates human-readable explanations
 * for risk decisions. Production-ready with:
 * - Configurable thresholds
 * - Graceful degradation
 * - Full audit trails
 */

import {
  RiskExplanation,
  RiskFeatures,
  GraphContext,
  RuleResult,
  ExplanationFactor,
  TypologyMatch,
  RiskAction,
  ImpactLevel,
  FactorCategory,
  ExplanationMetadata,
  ExplainabilityConfig
} from './types.js';
import { loadConfig, getConfigHash } from './config.js';
import { 
  formatTemplate, 
  formatCurrency,
  determineImpact,
  getContributionWeight,
  buildFeatureMap,
  buildTemplateContext,
  extractAllFeatures
} from './templates.js';
import { TypologyMatcher, getTypologyDisplayName } from './typologies.js';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const EXPLAINER_VERSION = '2.0.0';

// ═══════════════════════════════════════════════════════════════════════════════
// RISK EXPLAINER CLASS
// ═══════════════════════════════════════════════════════════════════════════════

export class RiskExplainer {
  private config: ExplainabilityConfig;
  private featureMap: Map<string, any>;
  private typologyMatcher: TypologyMatcher;
  private ethPriceUsd: number;
  
  constructor(options: {
    config?: ExplainabilityConfig;
    ethPriceUsd?: number;
  } = {}) {
    this.config = options.config ?? loadConfig();
    this.featureMap = buildFeatureMap(this.config.features);
    this.typologyMatcher = new TypologyMatcher(this.config.typologies);
    this.ethPriceUsd = options.ethPriceUsd ?? 2500;
  }
  
  /**
   * Update ETH price (call periodically)
   */
  setEthPrice(priceUsd: number): void {
    this.ethPriceUsd = priceUsd;
  }
  
  /**
   * Generate a complete explanation for a risk decision
   */
  explain(
    riskScore: number,
    features: RiskFeatures,
    graphContext: GraphContext = {},
    ruleResults: RuleResult[] = [],
    requestId: string = crypto.randomUUID()
  ): RiskExplanation {
    const startTime = performance.now();
    
    // Track degraded components
    const degradedComponents: string[] = [];
    if (graphContext.degradedMode) {
      degradedComponents.push('graph-service');
    }
    
    // Determine action based on thresholds
    const action = this.determineAction(riskScore);
    
    // Explain individual features
    const factors = this.explainFeatures(features, graphContext);
    
    // Match typologies
    const typologyMatches = this.typologyMatcher.matchAll(features, graphContext, ruleResults);
    
    // Generate top reasons (most important for compliance)
    const topReasons = this.generateTopReasons(factors, typologyMatches, ruleResults);
    
    // Generate summary
    const summary = this.generateSummary(riskScore, action, typologyMatches);
    
    // Generate graph explanation
    const graphExplanation = this.generateGraphExplanation(graphContext);
    
    // Generate recommendations
    const recommendations = this.generateRecommendations(action, factors, typologyMatches);
    
    // Estimate confidence
    const confidence = this.estimateConfidence(factors, graphContext, ruleResults);
    
    // Build metadata
    const metadata: ExplanationMetadata = {
      explainerVersion: EXPLAINER_VERSION,
      generatedAt: new Date().toISOString(),
      processingTimeMs: Math.round(performance.now() - startTime),
      requestId,
      modelVersions: this.extractModelVersions(features),
      configHash: getConfigHash(this.config)
    };
    
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
      degradedMode: degradedComponents.length > 0,
      degradedComponents: degradedComponents.length > 0 ? degradedComponents : undefined,
      metadata
    };
  }
  
  // ─── Action Determination ───────────────────────────────────────────────────
  
  private determineAction(riskScore: number): RiskAction {
    const t = this.config.actionThresholds;
    
    if (riskScore < t.allow.max) return RiskAction.ALLOW;
    if (riskScore < t.review.max) return RiskAction.REVIEW;
    if (riskScore < t.escrow.max) return RiskAction.ESCROW;
    return RiskAction.BLOCK;
  }
  
  // ─── Feature Explanation ────────────────────────────────────────────────────
  
  private explainFeatures(
    features: RiskFeatures,
    graphContext: GraphContext
  ): ExplanationFactor[] {
    const factors: ExplanationFactor[] = [];
    const allFeatures = extractAllFeatures(features, graphContext);
    
    for (const [key, value] of Object.entries(allFeatures)) {
      if (value === undefined || value === null) continue;
      
      const config = this.featureMap.get(key);
      if (!config) continue;
      
      // Skip internal-only features from display
      // (but still use them for calculations)
      
      const impact = determineImpact(value, config.thresholds);
      if (impact === ImpactLevel.NEUTRAL) continue;
      
      const template = config.templates[impact];
      if (!template) continue;
      
      const context = buildTemplateContext(value, features, this.ethPriceUsd);
      context.threshold = config.thresholds[impact];
      
      const humanReadable = formatTemplate(template, context);
      if (!humanReadable) continue;
      
      factors.push({
        factorId: key,
        impact,
        humanReadable,
        technicalDetail: `${config.name}: ${this.formatValue(value)}`,
        value,
        threshold: config.thresholds[impact],
        contribution: getContributionWeight(impact),
        category: config.category,
        regulatoryRef: config.regulatoryRef
      });
    }
    
    // Sort by contribution (highest first)
    return factors.sort((a, b) => b.contribution - a.contribution);
  }
  
  private formatValue(value: unknown): string {
    if (typeof value === 'number') {
      if (value < 0.001 && value > 0) {
        return value.toExponential(2);
      } else if (value < 1) {
        return value.toFixed(4);
      } else if (value < 100) {
        return value.toFixed(2);
      }
      return Math.round(value).toLocaleString();
    }
    return String(value);
  }
  
  // ─── Summary Generation ─────────────────────────────────────────────────────
  
  private generateSummary(
    riskScore: number,
    action: RiskAction,
    typologyMatches: TypologyMatch[]
  ): string {
    const actionDescriptions: Record<RiskAction, string> = {
      [RiskAction.ALLOW]: 'Transaction approved with low risk',
      [RiskAction.REVIEW]: 'Transaction flagged for manual review',
      [RiskAction.ESCROW]: 'Transaction held in escrow pending investigation',
      [RiskAction.BLOCK]: 'Transaction blocked due to high risk'
    };
    
    let summary = actionDescriptions[action];
    
    // Add primary typology if detected
    if (typologyMatches.length > 0) {
      const primary = typologyMatches[0];
      const typeName = getTypologyDisplayName(primary.typology);
      summary += ` - ${typeName} pattern detected (${Math.round(primary.confidence * 100)}% confidence)`;
    }
    
    return summary;
  }
  
  // ─── Top Reasons ────────────────────────────────────────────────────────────
  
  private generateTopReasons(
    factors: ExplanationFactor[],
    typologyMatches: TypologyMatch[],
    ruleResults: RuleResult[]
  ): string[] {
    const reasons: string[] = [];
    const seen = new Set<string>();
    
    // Priority 1: Typology descriptions (they're most meaningful)
    for (const match of typologyMatches.slice(0, 2)) {
      if (!seen.has(match.description)) {
        reasons.push(match.description);
        seen.add(match.description);
      }
    }
    
    // Priority 2: Critical factors
    for (const factor of factors) {
      if (factor.impact === ImpactLevel.CRITICAL && !seen.has(factor.humanReadable)) {
        reasons.push(factor.humanReadable);
        seen.add(factor.humanReadable);
      }
    }
    
    // Priority 3: Rule descriptions
    for (const rule of ruleResults) {
      if (rule.triggered && rule.description && !seen.has(rule.description)) {
        reasons.push(rule.description);
        seen.add(rule.description);
      }
    }
    
    // Priority 4: High-impact factors
    for (const factor of factors) {
      if (factor.impact === ImpactLevel.HIGH && !seen.has(factor.humanReadable)) {
        reasons.push(factor.humanReadable);
        seen.add(factor.humanReadable);
      }
    }
    
    // Priority 5: Medium-impact factors (if we need more)
    for (const factor of factors) {
      if (factor.impact === ImpactLevel.MEDIUM && !seen.has(factor.humanReadable)) {
        reasons.push(factor.humanReadable);
        seen.add(factor.humanReadable);
      }
    }
    
    return reasons.slice(0, 5);
  }
  
  // ─── Graph Explanation ──────────────────────────────────────────────────────
  
  private generateGraphExplanation(graphContext: GraphContext): string | null {
    if (!graphContext || Object.keys(graphContext).length === 0) {
      return null;
    }
    
    if (graphContext.degradedMode) {
      return 'Network analysis unavailable - graph service degraded. Decision made with limited context.';
    }
    
    const parts: string[] = [];
    
    if (graphContext.hopsToSanctioned !== undefined) {
      if (graphContext.hopsToSanctioned === 0) {
        parts.push('directly matches sanctioned address');
      } else if (graphContext.hopsToSanctioned <= 3) {
        parts.push(`is ${graphContext.hopsToSanctioned} hop(s) from sanctioned entities`);
      }
    }
    
    if (graphContext.mixerInteraction) {
      parts.push('has direct mixer interaction');
    } else if (graphContext.hopsToMixer !== undefined && graphContext.hopsToMixer <= 2) {
      parts.push(`is ${graphContext.hopsToMixer} hop(s) from mixing services`);
    }
    
    if (graphContext.pagerank !== undefined && graphContext.pagerank > 0.0001) {
      parts.push(`has elevated network influence (PageRank: ${graphContext.pagerank.toFixed(4)})`);
    }
    
    if (graphContext.clusteringCoefficient !== undefined && graphContext.clusteringCoefficient > 0.5) {
      parts.push('is part of a tightly connected group');
    }
    
    if (graphContext.inDegree !== undefined && graphContext.inDegree > 100) {
      parts.push(`has high incoming volume (${graphContext.inDegree} unique senders)`);
    }
    
    if (graphContext.outDegree !== undefined && graphContext.outDegree > 100) {
      parts.push(`has high outgoing volume (${graphContext.outDegree} unique recipients)`);
    }
    
    if (parts.length === 0) {
      return 'Network analysis shows no significant risk indicators.';
    }
    
    return 'Network analysis: Address ' + parts.join(', ') + '.';
  }
  
  // ─── Recommendations ────────────────────────────────────────────────────────
  
  private generateRecommendations(
    action: RiskAction,
    factors: ExplanationFactor[],
    typologyMatches: TypologyMatch[]
  ): string[] {
    const recs: string[] = [];
    
    // Action-based recommendations
    switch (action) {
      case RiskAction.BLOCK:
        recs.push('File SAR (Suspicious Activity Report) within 24 hours');
        recs.push('Preserve all transaction evidence for potential law enforcement request');
        recs.push('Notify compliance officer and senior management immediately');
        recs.push('Consider account freeze pending investigation');
        break;
        
      case RiskAction.ESCROW:
        recs.push('Hold funds in escrow pending compliance review');
        recs.push('Request enhanced KYC documentation from customer');
        recs.push('Review counterparty transaction history');
        recs.push('Document escalation reasoning');
        break;
        
      case RiskAction.REVIEW:
        recs.push('Request additional KYC documentation from sender');
        recs.push('Review counterparty transaction history');
        recs.push('Verify source of funds documentation');
        recs.push('Consider transaction in context of customer profile');
        break;
        
      case RiskAction.ALLOW:
        recs.push('Continue standard monitoring');
        if (factors.some(f => f.impact === ImpactLevel.MEDIUM)) {
          recs.push('Flag for periodic review');
        }
        break;
    }
    
    // Typology-specific recommendations
    for (const match of typologyMatches) {
      switch (match.typology) {
        case 'layering':
          recs.push('Trace full transaction chain to identify ultimate origin');
          break;
        case 'sanctions_proximity':
          recs.push('Verify sanctions list match is current (lists update daily)');
          recs.push('Check for potential false positive through additional identifiers');
          break;
        case 'dormant_activation':
          recs.push('Verify account ownership has not changed');
          recs.push('Check for security compromise indicators');
          break;
        case 'mixer_interaction':
          recs.push('Review all associated transactions for mixer patterns');
          recs.push('Consider enhanced monitoring for related addresses');
          break;
        case 'pep_involvement':
          recs.push('Apply enhanced due diligence per FATF R.12');
          recs.push('Document source of wealth assessment');
          break;
      }
    }
    
    // Deduplicate and limit
    return Array.from(new Set(recs)).slice(0, 6);
  }
  
  // ─── Confidence Estimation ──────────────────────────────────────────────────
  
  private estimateConfidence(
    factors: ExplanationFactor[],
    graphContext: GraphContext,
    ruleResults: RuleResult[]
  ): number {
    let confidence = 0.6; // Base confidence
    
    // Graph context available
    if (graphContext && !graphContext.degradedMode) {
      confidence += 0.15;
    }
    
    // High-impact factors increase confidence
    const highImpactCount = factors.filter(
      f => f.impact === ImpactLevel.CRITICAL || f.impact === ImpactLevel.HIGH
    ).length;
    confidence += Math.min(0.15, highImpactCount * 0.03);
    
    // Rule confirmations increase confidence
    const triggeredRules = ruleResults.filter(r => r.triggered).length;
    confidence += Math.min(0.1, triggeredRules * 0.02);
    
    // Cap at 0.95 (never 100% certain)
    return Math.min(0.95, confidence);
  }
  
  // ─── Model Version Extraction ───────────────────────────────────────────────
  
  private extractModelVersions(features: RiskFeatures): Record<string, string> {
    const versions: Record<string, string> = {
      explainer: EXPLAINER_VERSION
    };
    
    // Add model versions if available (from external sources)
    if (features.xgbProb !== undefined) {
      versions.xgboost = 'v1.0';
    }
    if (features.vaeReconError !== undefined) {
      versions.vae = 'v1.0';
    }
    if (features.sageProb !== undefined) {
      versions.graphsage = 'v1.0';
    }
    
    return versions;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONVENIENCE FUNCTION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Convenience function for quick explanation generation
 */
export function explainRiskDecision(
  riskScore: number,
  features: RiskFeatures,
  graphContext: GraphContext = {},
  ruleResults: RuleResult[] = [],
  ethPriceUsd: number = 2500
): RiskExplanation {
  const explainer = new RiskExplainer({ ethPriceUsd });
  return explainer.explain(riskScore, features, graphContext, ruleResults);
}
