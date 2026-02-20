/**
 * AMTTP Client SDK
 * 
 * A comprehensive SDK for interacting with the AMTTP (Advanced Money Transfer Transaction Protocol)
 * backend services. Provides regulatory-compliant transaction processing with Stacked Ensemble ML risk scoring.
 * 
 * @packageDocumentation
 */

// Core types used across the SDK
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type KYCStatus = 'none' | 'pending' | 'verified' | 'rejected' | 'expired';
export type KYCLevel = 'none' | 'basic' | 'standard' | 'enhanced';
export type TransactionStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
export type PolicyDecision = 'allow' | 'deny' | 'review' | 'escalate';
export type DisputeStatus = 'open' | 'in_review' | 'awaiting_evidence' | 'resolved' | 'appealed' | 'closed';
export type DisputeRuling = 'claimant_wins' | 'respondent_wins' | 'split' | 'dismissed';
export type ReputationTier = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';

export interface RiskScore {
  address: string;
  score: number;
  level: RiskLevel;
  timestamp: string;
  expiresAt: string;
}

export interface LabelInfo {
  label: string;
  category: string;
  severity: string;
  source: string;
}

export interface ReputationScore {
  address: string;
  tier: ReputationTier;
  score: number;
  totalTransactions: number;
}

// Main client export
export { AMTTPClient, type AMTTPClientConfig } from './client';

// Service exports with specific types
export { 
  RiskService, 
  type RiskAssessmentRequest, 
  type RiskAssessmentResponse,
  type BatchRiskRequest,
  type BatchRiskResponse,
  type RiskFactor,
  type RiskThreshold
} from './services/risk';

export { 
  KYCService, 
  type KYCSubmission, 
  type KYCVerificationResult,
  type KYCDocument,
  type KYCRequirements
} from './services/kyc';

export { 
  TransactionService, 
  type TransactionRequest, 
  type TransactionRecord,
  type TransactionValidation,
  type TransactionHistoryOptions
} from './services/transaction';

export { 
  PolicyService, 
  type Policy,
  type PolicyCondition,
  type PolicyAction,
  type PolicyEvaluationRequest, 
  type PolicyEvaluationResult,
  type PolicyCreateRequest
} from './services/policy';

export { 
  DisputeService, 
  type Dispute,
  type Evidence,
  type TimelineEvent,
  type DisputeCreateRequest,
  type DisputeListOptions
} from './services/dispute';

export { 
  ReputationService, 
  type ReputationProfile, 
  type Badge,
  type ReputationEvent,
  type TierRequirements,
  type LeaderboardEntry
} from './services/reputation';

export { 
  BulkService, 
  type BulkScoringRequest,
  type BulkScoringResult, 
  type BulkJobStatus,
  type BulkTransaction,
  type TransactionScoreResult
} from './services/bulk';

export { 
  WebhookService, 
  type Webhook, 
  type WebhookDelivery,
  type WebhookCreateRequest,
  type WebhookEventType
} from './services/webhook';

export { 
  PEPService, 
  type PEPScreeningRequest,
  type PEPScreeningResult, 
  type PEPMatch,
  type PEPHistoryEntry
} from './services/pep';

export { 
  EDDService, 
  type EDDCase, 
  type EDDDocument,
  type EDDNote,
  type EDDTimelineEvent,
  type EDDCreateRequest,
  type EDDListOptions,
  type EDDStatus,
  type EDDTrigger
} from './services/edd';

export { 
  MonitoringService, 
  type MonitoringAlert, 
  type MonitoringRule,
  type RuleCondition,
  type MonitoredAddress,
  type MonitoringConfig,
  type AlertSeverity,
  type AlertStatus,
  type AlertType
} from './services/monitoring';

export { 
  LabelService, 
  type AddressLabel,
  type LabelSearchResult,
  type LabelStatistics,
  type LabelCategory,
  type LabelSeverity
} from './services/label';

export { 
  MEVProtection, 
  type MEVConfig,
  type MEVProtectedTransaction,
  type FlashbotsBundle,
  type MEVAnalysis,
  type MEVProtectionLevel
} from './mev/protection';

// New service exports
export { 
  ComplianceService,
  type EntityProfile,
  type EvaluateRequest,
  type EvaluateResponse,
  type ComplianceAction,
  type ComplianceCheck,
  type EntityType,
  type RiskTolerance,
  type DashboardAlert,
  type TimelineDataPoint,
  type DecisionRecord,
  type DecisionListOptions
} from './services/compliance';

export { 
  ExplainabilityService,
  type ExplainRequest,
  type RiskExplanation,
  type ExplanationFactor,
  type TypologyMatch,
  type TransactionExplainRequest,
  type TransactionExplanation,
  type Typology,
  type ImpactLevel,
  type RecommendedAction
} from './services/explainability';

export { 
  SanctionsService,
  type SanctionsCheckRequest,
  type SanctionsCheckResponse,
  type SanctionsMatch,
  type BatchCheckRequest,
  type BatchCheckResult,
  type BatchCheckResponse,
  type SanctionsStats,
  type SanctionsList,
  type SanctionedEntity,
  type MatchType
} from './services/sanctions';

export { 
  GeographicRiskService,
  type CountryRiskRequest,
  type CountryRiskResponse,
  type IPRiskRequest,
  type IPRiskResponse,
  type TransactionGeoRiskRequest,
  type TransactionGeoRiskResponse,
  type FATFListCountry,
  type CountryInfo,
  type TransactionPolicy
} from './services/geographic';

export { 
  IntegrityService,
  type SnapshotData,
  type RegisterHashRequest,
  type RegisterHashResponse,
  type VerifyIntegrityRequest,
  type VerifyIntegrityResponse,
  type PaymentSubmission,
  type PaymentSubmissionResponse,
  type IntegrityViolation,
  type ViolationListOptions
} from './services/integrity';

export { 
  GovernanceService,
  type GovernanceAction,
  type ActionType,
  type ActionStatus,
  type ActionScope,
  type RiskContext,
  type Signature,
  type CreateActionRequest,
  type SignActionRequest,
  type SigningResult,
  type ExecutionResult,
  type WYASummary,
  type ActionListOptions
} from './services/governance';

export { 
  DashboardService,
  type DashboardStats,
  type Alert,
  type RiskDistribution,
  type ActivityMetric,
  type SankeyNode,
  type SankeyLink,
  type SankeyData,
  type TopRiskEntity,
  type GeographicRiskMap,
  type DashboardFilters,
  type TimeRange
} from './services/dashboard';

export { AMTTPError, AMTTPErrorCode } from './errors';
export { EventEmitter, type AMTTPEvents } from './events';
