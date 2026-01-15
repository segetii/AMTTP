/**
 * AMTTP Client SDK
 *
 * A comprehensive SDK for interacting with the AMTTP (Advanced Money Transfer Transaction Protocol)
 * backend services. Provides regulatory-compliant transaction processing with DQN-based risk scoring.
 *
 * @packageDocumentation
 */
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
export { AMTTPClient, type AMTTPClientConfig } from './client';
export { RiskService, type RiskAssessmentRequest, type RiskAssessmentResponse, type BatchRiskRequest, type BatchRiskResponse, type RiskFactor, type RiskThreshold } from './services/risk';
export { KYCService, type KYCSubmission, type KYCVerificationResult, type KYCDocument, type KYCRequirements } from './services/kyc';
export { TransactionService, type TransactionRequest, type TransactionRecord, type TransactionValidation, type TransactionHistoryOptions } from './services/transaction';
export { PolicyService, type Policy, type PolicyCondition, type PolicyAction, type PolicyEvaluationRequest, type PolicyEvaluationResult, type PolicyCreateRequest } from './services/policy';
export { DisputeService, type Dispute, type Evidence, type TimelineEvent, type DisputeCreateRequest, type DisputeListOptions } from './services/dispute';
export { ReputationService, type ReputationProfile, type Badge, type ReputationEvent, type TierRequirements, type LeaderboardEntry } from './services/reputation';
export { BulkService, type BulkScoringRequest, type BulkScoringResult, type BulkJobStatus, type BulkTransaction, type TransactionScoreResult } from './services/bulk';
export { WebhookService, type Webhook, type WebhookDelivery, type WebhookCreateRequest, type WebhookEventType } from './services/webhook';
export { PEPService, type PEPScreeningRequest, type PEPScreeningResult, type PEPMatch, type PEPHistoryEntry } from './services/pep';
export { EDDService, type EDDCase, type EDDDocument, type EDDNote, type EDDTimelineEvent, type EDDCreateRequest, type EDDListOptions, type EDDStatus, type EDDTrigger } from './services/edd';
export { MonitoringService, type MonitoringAlert, type MonitoringRule, type RuleCondition, type MonitoredAddress, type MonitoringConfig, type AlertSeverity, type AlertStatus, type AlertType } from './services/monitoring';
export { LabelService, type AddressLabel, type LabelSearchResult, type LabelStatistics, type LabelCategory, type LabelSeverity } from './services/label';
export { MEVProtection, type MEVConfig, type MEVProtectedTransaction, type FlashbotsBundle, type MEVAnalysis, type MEVProtectionLevel } from './mev/protection';
export { AMTTPError, AMTTPErrorCode } from './errors';
export { EventEmitter, type AMTTPEvents } from './events';
//# sourceMappingURL=index.d.ts.map