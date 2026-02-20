/**
 * Services index - re-exports all service classes
 */

export { BaseService } from './base';
export { RiskService } from './risk';
export { KYCService } from './kyc';
export { TransactionService } from './transaction';
export { PolicyService } from './policy';
export { DisputeService } from './dispute';
export { ReputationService } from './reputation';
export { BulkService } from './bulk';
export { WebhookService } from './webhook';
export { PEPService } from './pep';
export { EDDService } from './edd';
export { MonitoringService } from './monitoring';
export { LabelService } from './label';

// New services
export { ComplianceService } from './compliance';
export { ExplainabilityService } from './explainability';
export { SanctionsService } from './sanctions';
export { GeographicRiskService } from './geographic';
export { IntegrityService } from './integrity';
export { GovernanceService } from './governance';
export { DashboardService } from './dashboard';

// Re-export types from each service
export type {
  RiskAssessmentRequest,
  RiskAssessmentResponse,
  RiskFactor,
  BatchRiskRequest,
  BatchRiskResponse,
  RiskThreshold,
  RiskLevel,
  RiskScore,
  LabelInfo,
} from './risk';

export type {
  KYCSubmission,
  KYCVerificationResult,
  KYCDocument,
  KYCRequirements,
  KYCStatus,
  KYCLevel,
} from './kyc';

export type {
  TransactionRequest,
  TransactionRecord,
  TransactionValidation,
  TransactionHistoryOptions,
  TransactionStatus,
} from './transaction';

export type {
  Policy,
  PolicyCondition,
  PolicyAction,
  PolicyEvaluationRequest,
  PolicyEvaluationResult,
  PolicyCreateRequest,
  PolicyDecision,
} from './policy';

export type {
  Dispute,
  Evidence,
  TimelineEvent,
  DisputeCreateRequest,
  DisputeListOptions,
  DisputeStatus,
  DisputeRuling,
} from './dispute';

export type {
  ReputationProfile,
  Badge,
  ReputationEvent,
  TierRequirements,
  LeaderboardEntry,
  ReputationTier,
  ReputationScore,
} from './reputation';

export type {
  BulkScoringRequest,
  BulkTransaction,
  BulkScoringResult,
  TransactionScoreResult,
  BulkJobStatus,
} from './bulk';

export type {
  Webhook,
  WebhookDelivery,
  WebhookCreateRequest,
  WebhookEventType,
} from './webhook';

export type {
  PEPScreeningRequest,
  PEPMatch,
  PEPScreeningResult,
  PEPHistoryEntry,
} from './pep';

export type {
  EDDCase,
  EDDDocument,
  EDDNote,
  EDDTimelineEvent,
  EDDCreateRequest,
  EDDListOptions,
  EDDStatus,
  EDDTrigger,
} from './edd';

export type {
  MonitoringAlert,
  MonitoringRule,
  RuleCondition,
  MonitoredAddress,
  MonitoringConfig,
  AlertSeverity,
  AlertStatus,
  AlertType,
} from './monitoring';

export type {
  AddressLabel,
  LabelSearchResult,
  LabelStatistics,
  LabelCategory,
  LabelSeverity,
} from './label';

// Compliance service types
export type {
  EntityProfile,
  EvaluateRequest,
  EvaluateResponse,
  ComplianceAction,
  ComplianceCheck,
  EntityType,
  KYCLevel as ComplianceKYCLevel,
  RiskTolerance,
  DashboardStats as ComplianceDashboardStats,
  DashboardAlert,
  TimelineDataPoint,
  DecisionRecord,
  DecisionListOptions,
} from './compliance';

// Explainability service types
export type {
  ExplainRequest,
  RiskExplanation,
  ExplanationFactor,
  TypologyMatch,
  TransactionExplainRequest,
  TransactionExplanation,
  Typology,
  ImpactLevel,
  RecommendedAction,
} from './explainability';

// Sanctions service types
export type {
  SanctionsCheckRequest,
  SanctionsCheckResponse,
  SanctionsMatch,
  BatchCheckRequest,
  BatchCheckResult,
  BatchCheckResponse,
  SanctionsStats,
  SanctionsList,
  SanctionedEntity,
  MatchType,
} from './sanctions';

// Geographic risk service types
export type {
  CountryRiskRequest,
  CountryRiskResponse,
  IPRiskRequest,
  IPRiskResponse,
  TransactionGeoRiskRequest,
  TransactionGeoRiskResponse,
  FATFListCountry,
  CountryInfo,
  RiskLevel as GeoRiskLevel,
  TransactionPolicy,
} from './geographic';

// Integrity service types
export type {
  SnapshotData,
  RegisterHashRequest,
  RegisterHashResponse,
  VerifyIntegrityRequest,
  VerifyIntegrityResponse,
  PaymentSubmission,
  PaymentSubmissionResponse,
  IntegrityViolation,
  ViolationListOptions,
} from './integrity';

// Governance service types
export type {
  GovernanceAction,
  ActionType,
  ActionStatus,
  ActionScope,
  RiskContext,
  Signature,
  CreateActionRequest,
  SignActionRequest,
  SigningResult,
  ExecutionResult,
  WYASummary,
  ActionListOptions,
} from './governance';

// Dashboard service types
export type {
  DashboardStats,
  Alert,
  RiskDistribution,
  ActivityMetric,
  SankeyNode,
  SankeyLink,
  SankeyData,
  TopRiskEntity,
  GeographicRiskMap,
  DashboardFilters,
  TimeRange,
} from './dashboard';
