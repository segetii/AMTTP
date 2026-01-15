/**
 * Feature Templates for Human-Readable Explanations
 * 
 * Each template converts raw feature values into sentences
 * that compliance officers can understand and act upon.
 */

import { ImpactLevel, FeatureConfig, RiskFeatures, GraphContext } from './types.js';
import { loadConfig } from './config.js';

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE CONTEXT
// ═══════════════════════════════════════════════════════════════════════════════

export interface TemplateContext {
  value: unknown;
  usd: string;
  ratio: number;
  avg: string;
  listName: string;
  country: string;
  pepCategory: string;
  threshold: unknown;
  ethPrice: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TEMPLATE ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Format a template string with context values
 */
export function formatTemplate(template: string, context: TemplateContext): string {
  if (!template) return '';
  
  return template.replace(/\{(\w+)\}/g, (match, key) => {
    const value = (context as unknown as Record<string, unknown>)[key];
    if (value === undefined) return match;
    
    if (typeof value === 'number') {
      // Format based on magnitude
      if (Math.abs(value) < 0.001) {
        return value.toExponential(2);
      } else if (Math.abs(value) < 1) {
        return value.toFixed(4);
      } else if (Math.abs(value) < 100) {
        return value.toFixed(2);
      } else {
        return Math.round(value).toLocaleString();
      }
    }
    
    return String(value);
  });
}

/**
 * Format currency value
 */
export function formatCurrency(value: number): string {
  if (value >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(2)}B`;
  } else if (value >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(2)}M`;
  } else if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}K`;
  }
  return `$${value.toFixed(0)}`;
}

/**
 * Format ETH value
 */
export function formatEth(value: number): string {
  if (value >= 1000) {
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} ETH`;
  } else if (value >= 1) {
    return `${value.toFixed(2)} ETH`;
  } else {
    return `${value.toFixed(4)} ETH`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// IMPACT DETERMINATION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Determine impact level based on value and thresholds
 */
export function determineImpact(
  value: unknown,
  thresholds: Partial<Record<ImpactLevel, number | string>>
): ImpactLevel {
  if (!thresholds || Object.keys(thresholds).length === 0) {
    return ImpactLevel.NEUTRAL;
  }
  
  // Numeric comparison
  if (typeof value === 'number') {
    for (const level of [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]) {
      const threshold = thresholds[level];
      if (typeof threshold === 'number' && value >= threshold) {
        return level;
      }
    }
    return value > 0 ? ImpactLevel.LOW : ImpactLevel.NEUTRAL;
  }
  
  // Boolean - true = HIGH
  if (typeof value === 'boolean') {
    return value ? ImpactLevel.HIGH : ImpactLevel.NEUTRAL;
  }
  
  // String matching
  if (typeof value === 'string') {
    for (const level of [ImpactLevel.CRITICAL, ImpactLevel.HIGH, ImpactLevel.MEDIUM]) {
      if (thresholds[level] === value) {
        return level;
      }
    }
  }
  
  return ImpactLevel.NEUTRAL;
}

/**
 * Get contribution weight for impact level
 */
export function getContributionWeight(impact: ImpactLevel): number {
  const weights: Record<ImpactLevel, number> = {
    [ImpactLevel.CRITICAL]: 0.50,
    [ImpactLevel.HIGH]: 0.25,
    [ImpactLevel.MEDIUM]: 0.15,
    [ImpactLevel.LOW]: 0.05,
    [ImpactLevel.NEUTRAL]: 0.00
  };
  return weights[impact] ?? 0;
}

// ═══════════════════════════════════════════════════════════════════════════════
// FEATURE PROCESSING
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Build feature map from config for fast lookup
 */
export function buildFeatureMap(
  configs: FeatureConfig[]
): Map<string, FeatureConfig> {
  return new Map(configs.filter(f => f.enabled).map(f => [f.id, f]));
}

/**
 * Extract all feature values from features and graph context
 */
export function extractAllFeatures(
  features: RiskFeatures,
  graphContext: GraphContext
): Record<string, unknown> {
  return {
    ...features,
    ...graphContext,
  };
}

/**
 * Build template context from feature values
 */
export function buildTemplateContext(
  value: unknown,
  features: RiskFeatures,
  ethPrice: number = 2500
): TemplateContext {
  const amountEth = features.amountEth ?? 0;
  const avgAmount = features.avgAmount30d ?? 0;
  
  return {
    value,
    usd: formatCurrency(typeof value === 'number' ? value * ethPrice : 0),
    ratio: features.amountVsAverage ?? (avgAmount > 0 ? amountEth / avgAmount : 1),
    avg: formatCurrency(avgAmount * ethPrice),
    listName: features.sanctionsList ?? 'OFAC',
    country: features.countryCode ?? 'Unknown',
    pepCategory: features.pepCategory ?? 'Unknown',
    threshold: null,
    ethPrice
  };
}
