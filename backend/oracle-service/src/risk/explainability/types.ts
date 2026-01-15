/**
 * Type Definitions for Production Explainability System
 * 
 * All interfaces are designed for:
 * - Regulatory compliance (audit trails)
 * - API stability (versioned contracts)
 * - Type safety (strict mode compatible)
 */

// ═══════════════════════════════════════════════════════════════════════════════
// ENUMS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Impact level for risk factors - determines weight and display priority
 */
export enum ImpactLevel {
  CRITICAL = 'CRITICAL',  // Single factor that triggers BLOCK (weight: 0.5)
  HIGH = 'HIGH',          // Strong contributor to risk (weight: 0.25)
  MEDIUM = 'MEDIUM',      // Moderate contributor (weight: 0.15)
  LOW = 'LOW',            // Minor contributor (weight: 0.05)
  NEUTRAL = 'NEUTRAL'     // No significant impact (weight: 0)
}

/**
 * Known fraud/AML typology patterns
 */
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
  RAPID_MOVEMENT = 'rapid_movement',
  UNUSUAL_TIMING = 'unusual_timing',
  PEP_INVOLVEMENT = 'pep_involvement',
  SHELL_COMPANY = 'shell_company'
}

/**
 * Actions taken on transactions
 */
export enum RiskAction {
  ALLOW = 'ALLOW',
  REVIEW = 'REVIEW',
  ESCROW = 'ESCROW',
  BLOCK = 'BLOCK'
}

/**
 * Severity levels for logging and alerts
 */
export enum Severity {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
  CRITICAL = 'CRITICAL'
}

// ═══════════════════════════════════════════════════════════════════════════════
// CORE TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * A single contributing factor to the risk decision
 */
export interface ExplanationFactor {
  /** Unique identifier for the factor (e.g., 'amountEth', 'dormancyDays') */
  factorId: string;
  
  /** Impact level determines display priority */
  impact: ImpactLevel;
  
  /** Human-readable explanation (for compliance officers) */
  humanReadable: string;
  
  /** Technical detail (for engineers/auditors) */
  technicalDetail: string;
  
  /** Raw value that triggered this factor */
  value: unknown;
  
  /** Threshold that was exceeded (if applicable) */
  threshold?: unknown;
  
  /** Estimated contribution to overall risk (0-1) */
  contribution: number;
  
  /** Category for grouping in UI */
  category: FactorCategory;
  
  /** Regulatory reference (e.g., 'FATF R.10', 'FCA SYSC 3.2') */
  regulatoryRef?: string;
}

export type FactorCategory = 
  | 'TRANSACTION'
  | 'BEHAVIOR'
  | 'NETWORK'
  | 'COMPLIANCE'
  | 'GEOGRAPHIC'
  | 'MODEL';

/**
 * A matched fraud/AML typology pattern
 */
export interface TypologyMatch {
  /** Type of pattern detected */
  typology: TypologyType;
  
  /** Confidence in the match (0-1) */
  confidence: number;
  
  /** Human-readable description */
  description: string;
  
  /** List of indicators that triggered this match */
  indicators: string[];
  
  /** Raw evidence (for audit trail) */
  evidence: Record<string, unknown>;
  
  /** Regulatory guidance for this typology */
  regulatoryGuidance?: string;
  
  /** Typical SAR narrative for this pattern */
  sarNarrative?: string;
}

/**
 * Complete explanation for a risk decision
 */
export interface RiskExplanation {
  /** The risk score (0-1) */
  riskScore: number;
  
  /** Action taken (ALLOW/REVIEW/ESCROW/BLOCK) */
  action: RiskAction;
  
  /** One-sentence summary for UI display */
  summary: string;
  
  /** Top 5 human-readable reasons */
  topReasons: string[];
  
  /** All contributing factors sorted by impact */
  factors: ExplanationFactor[];
  
  /** Matched fraud/AML patterns */
  typologyMatches: TypologyMatch[];
  
  /** Network analysis explanation (if available) */
  graphExplanation: string | null;
  
  /** Recommended actions for compliance team */
  recommendations: string[];
  
  /** Confidence in the explanation (0-1) */
  confidence: number;
  
  /** Whether running in degraded mode (missing data) */
  degradedMode: boolean;
  
  /** Components that were unavailable */
  degradedComponents?: string[];
  
  /** Explanation metadata */
  metadata: ExplanationMetadata;
}

export interface ExplanationMetadata {
  /** Version of explainer that generated this */
  explainerVersion: string;
  
  /** Timestamp of generation */
  generatedAt: string;
  
  /** Processing time in milliseconds */
  processingTimeMs: number;
  
  /** Request ID for correlation */
  requestId: string;
  
  /** Model versions used */
  modelVersions: Record<string, string>;
  
  /** Configuration hash for reproducibility */
  configHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// INPUT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Transaction features for risk explanation
 */
export interface RiskFeatures {
  // ─── Amount Features ────────────────────────────────────────────────────────
  amountEth?: number;
  amountUsd?: number;
  amountVsAverage?: number;
  avgAmount30d?: number;
  maxAmount30d?: number;
  
  // ─── Velocity Features ──────────────────────────────────────────────────────
  txCount1h?: number;
  txCount24h?: number;
  txCount7d?: number;
  uniqueRecipients24h?: number;
  uniqueSenders24h?: number;
  volumeLast24h?: number;
  
  // ─── Timing Features ────────────────────────────────────────────────────────
  dormancyDays?: number;
  unusualHour?: boolean;
  weekendTransaction?: boolean;
  hourOfDay?: number;
  
  // ─── Account Features ───────────────────────────────────────────────────────
  accountAgeDays?: number;
  totalTransactions?: number;
  
  // ─── Compliance Features ────────────────────────────────────────────────────
  sanctionsMatch?: boolean;
  sanctionsList?: string;
  sanctionsMatchScore?: number;
  pepMatch?: boolean;
  pepCategory?: string;
  pepRiskLevel?: number;
  adverseMedia?: boolean;
  adverseMediaCount?: number;
  
  // ─── Geographic Features ────────────────────────────────────────────────────
  fatfCountryRisk?: 'blacklist' | 'greylist' | 'monitored' | 'standard';
  countryCode?: string;
  countryRiskScore?: number;
  crossBorder?: boolean;
  
  // ─── Model Scores (internal - not exposed in reasons) ──────────────────────
  xgbProb?: number;
  lgbProb?: number;
  vaeReconError?: number;
  sageProb?: number;
  metaProb?: number;
  dqnAction?: number;
  ensembleScore?: number;
}

/**
 * Graph/network context
 */
export interface GraphContext {
  // ─── Centrality Metrics ─────────────────────────────────────────────────────
  pagerank?: number;
  betweenness?: number;
  eigenvector?: number;
  
  // ─── Degree Metrics ─────────────────────────────────────────────────────────
  inDegree?: number;
  outDegree?: number;
  totalDegree?: number;
  
  // ─── Clustering ─────────────────────────────────────────────────────────────
  clusteringCoefficient?: number;
  communityId?: string;
  communitySize?: number;
  
  // ─── Distance to Bad Actors ─────────────────────────────────────────────────
  hopsToSanctioned?: number;
  hopsToMixer?: number;
  hopsToExchange?: number;
  hopsToDarknet?: number;
  
  // ─── Behavioral Patterns ────────────────────────────────────────────────────
  mixerInteraction?: boolean;
  exchangeInteraction?: boolean;
  contractInteraction?: boolean;
  
  // ─── Status Flags ───────────────────────────────────────────────────────────
  degradedMode?: boolean;
  lastUpdated?: string;
  dataFreshness?: 'realtime' | 'near-realtime' | 'stale';
}

/**
 * Rule engine results
 */
export interface RuleResult {
  /** Rule type identifier */
  ruleType: string;
  
  /** Whether rule was triggered */
  triggered: boolean;
  
  /** Severity if triggered */
  severity?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  
  /** Confidence in the match (0-1) */
  confidence?: number;
  
  /** Human-readable description */
  description?: string;
  
  /** Evidence that triggered the rule */
  evidence?: Record<string, unknown>;
  
  /** Rule version for audit */
  ruleVersion?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Request to generate an explanation
 */
export interface ExplanationRequest {
  /** Transaction identifier for correlation */
  transactionId: string;
  
  /** Request ID for tracing */
  requestId?: string;
  
  /** Risk score from model */
  riskScore: number;
  
  /** Transaction features */
  features: RiskFeatures;
  
  /** Graph context (optional) */
  graphContext?: GraphContext;
  
  /** Rule engine results (optional) */
  ruleResults?: RuleResult[];
  
  /** Override action (for manual review) */
  overrideAction?: RiskAction;
  
  /** Include full details (for audit) */
  includeFullDetails?: boolean;
}

/**
 * Response from explanation service
 */
export interface ExplanationResponse {
  success: boolean;
  explanation?: RiskExplanation;
  error?: ExplanationError;
  cached: boolean;
  requestId: string;
}

export interface ExplanationError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  retryable: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ExplainabilityConfig {
  /** Version of configuration */
  version: string;
  
  /** Action thresholds */
  actionThresholds: ActionThresholds;
  
  /** Feature configuration */
  features: FeatureConfig[];
  
  /** Typology configuration */
  typologies: TypologyConfig[];
  
  /** Cache settings */
  cache: CacheConfig;
  
  /** Metrics settings */
  metrics: MetricsConfig;
  
  /** Logging settings */
  logging: LoggingConfig;
}

export interface ActionThresholds {
  allow: { max: number };
  review: { min: number; max: number };
  escrow: { min: number; max: number };
  block: { min: number };
}

export interface FeatureConfig {
  id: string;
  name: string;
  category: FactorCategory;
  thresholds: Partial<Record<ImpactLevel, number | string>>;
  templates: Partial<Record<ImpactLevel, string>>;
  enabled: boolean;
  internalOnly?: boolean;
  regulatoryRef?: string;
}

export interface TypologyConfig {
  type: TypologyType;
  enabled: boolean;
  minConfidence: number;
  regulatoryGuidance: string;
  sarNarrative: string;
}

export interface CacheConfig {
  enabled: boolean;
  ttlSeconds: number;
  maxSize: number;
  keyPrefix: string;
}

export interface MetricsConfig {
  enabled: boolean;
  prefix: string;
  labels: string[];
}

export interface LoggingConfig {
  level: Severity;
  includeFeatures: boolean;
  redactPII: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// METRICS TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ExplainabilityMetrics {
  /** Total explanations generated */
  explanationsTotal: number;
  
  /** Explanations by action */
  explanationsByAction: Record<RiskAction, number>;
  
  /** Explanations by typology */
  explanationsByTypology: Record<string, number>;
  
  /** Processing time histogram */
  processingTimeMs: {
    p50: number;
    p90: number;
    p99: number;
    avg: number;
  };
  
  /** Cache metrics */
  cacheHits: number;
  cacheMisses: number;
  
  /** Error counts */
  errorsTotal: number;
  errorsByType: Record<string, number>;
  
  /** Degraded mode count */
  degradedModeCount: number;
}
