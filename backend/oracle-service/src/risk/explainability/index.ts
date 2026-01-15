/**
 * AMTTP Production-Grade Explainability System
 * 
 * This module provides:
 * - Human-readable explanations for risk decisions
 * - Audit-compliant reasoning trails
 * - Configurable thresholds and templates
 * - Caching, metrics, and observability
 * - Graceful degradation under failure
 * 
 * @module explainability
 * @version 2.0.0
 */

// Export all types (use 'export type' for isolated modules)
export type {
  ExplanationFactor,
  FactorCategory,
  TypologyMatch,
  RiskExplanation,
  ExplanationMetadata,
  RiskFeatures,
  GraphContext,
  RuleResult,
  ExplanationRequest,
  ExplanationResponse,
  ExplanationError,
  ExplainabilityConfig,
  ActionThresholds,
  FeatureConfig,
  TypologyConfig,
  CacheConfig,
  MetricsConfig,
  LoggingConfig,
  ExplainabilityMetrics
} from './types.js';

// Export enums (these are values, not just types)
export {
  ImpactLevel,
  TypologyType,
  RiskAction,
  Severity
} from './types.js';

// Export configuration
export { loadConfig, getConfigHash, DEFAULTS } from './config.js';

// Export template utilities
export { 
  formatTemplate, 
  formatCurrency, 
  formatEth,
  determineImpact, 
  getContributionWeight,
  buildFeatureMap,
  buildTemplateContext,
  extractAllFeatures
} from './templates.js';

// Export typology matcher
export { TypologyMatcher, getTypologyDisplayName } from './typologies.js';

// Export core explainer
export { RiskExplainer, explainRiskDecision } from './explainer.js';

// Export service
export { 
  ExplainabilityService, 
  getExplainabilityService, 
  resetExplainabilityService 
} from './service.js';

// Export metrics
export { MetricsCollector, Logger, metrics, logger } from './metrics.js';
