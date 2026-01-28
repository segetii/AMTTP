import EventEmitter3 from 'eventemitter3';
import { AxiosInstance } from 'axios';

/**
 * Simple Event Emitter for AMTTP SDK
 * Provides typed event handling
 */

interface AMTTPEvents {
    'connected': () => void;
    'disconnected': () => void;
    'reconnecting': (attempt: number) => void;
    'transaction:pending': (txHash: string) => void;
    'transaction:confirmed': (txHash: string, blockNumber: number) => void;
    'transaction:failed': (txHash: string, error: Error) => void;
    'transaction:escrowed': (txHash: string, escrowId: string) => void;
    'transaction:validated': (data: any) => void;
    'transaction:submitted': (data: any) => void;
    'transaction:cancelled': (data: any) => void;
    'transaction:retried': (data: any) => void;
    'risk:scored': (address: string, score: number, level: string) => void;
    'risk:alert': (address: string, alertType: string, severity: string) => void;
    'risk:assessed': (data: any) => void;
    'risk:batchCompleted': (data: any) => void;
    'risk:cacheInvalidated': (data: any) => void;
    'kyc:submitted': (data: any) => void;
    'kyc:documentUploaded': (data: any) => void;
    'kyc:upgradeRequested': (data: any) => void;
    'kyc:renewed': (data: any) => void;
    'policy:evaluated': (data: any) => void;
    'policy:created': (data: any) => void;
    'policy:updated': (data: any) => void;
    'policy:deleted': (data: any) => void;
    'compliance:kyc_required': (address: string) => void;
    'compliance:edd_required': (address: string, caseId: string) => void;
    'compliance:blocked': (address: string, reason: string) => void;
    'compliance:evaluated': (data: any) => void;
    'profile:updated': (data: any) => void;
    'explainability:explained': (data: any) => void;
    'sanctions:checked': (data: any) => void;
    'sanctions:match': (address: string, listName: string) => void;
    'geo:risk_assessed': (data: any) => void;
    'integrity:verified': (data: any) => void;
    'integrity:violation': (data: any) => void;
    'governance:action_created': (data: any) => void;
    'governance:signature_added': (data: any) => void;
    'governance:quorum_reached': (data: any) => void;
    'governance:action_executed': (data: any) => void;
    'governance:action_cancelled': (data: any) => void;
    'dashboard:alert_read': (data: any) => void;
    'dashboard:alert_dismissed': (data: any) => void;
    'dashboard:stats_updated': (data: any) => void;
    'dispute:created': (data: any) => void;
    'dispute:evidence_submitted': (disputeId: string, evidenceId: string) => void;
    'dispute:resolved': (disputeId: string, ruling: string) => void;
    'dispute:evidenceSubmitted': (data: any) => void;
    'dispute:escalated': (data: any) => void;
    'dispute:resolutionAccepted': (data: any) => void;
    'dispute:appealed': (data: any) => void;
    'dispute:withdrawn': (data: any) => void;
    'reputation:impactCalculated': (data: any) => void;
    'monitoring:alert': (alertId: string, address: string, type: string) => void;
    'monitoring:re-screened': (address: string, newScore: number) => void;
    'webhook:received': (eventType: string, payload: unknown) => void;
    'error': (error: Error) => void;
}
declare class EventEmitter extends EventEmitter3<AMTTPEvents> {
    /**
     * Wait for a specific event with timeout
     */
    waitFor(event: keyof AMTTPEvents, timeout?: number): Promise<unknown[]>;
    /**
     * Emit with logging
     */
    emitWithLog(event: keyof AMTTPEvents, ...args: unknown[]): boolean;
}

/**
 * Base service class for all AMTTP services
 */

declare abstract class BaseService {
    protected readonly http: AxiosInstance;
    protected readonly events: EventEmitter;
    constructor(http: AxiosInstance, events: EventEmitter);
}

/**
 * Risk Assessment Service
 * Wraps /risk endpoints for transaction risk scoring
 */

type RiskLevel$5 = 'low' | 'medium' | 'high' | 'critical';
interface LabelInfo$1 {
    label: string;
    category: string;
    severity: string;
    source: string;
}
interface RiskScore$1 {
    address: string;
    score: number;
    level: RiskLevel$5;
    timestamp: string;
    expiresAt: string;
}
interface RiskAssessmentRequest {
    address: string;
    transactionHash?: string;
    amount?: string;
    counterparty?: string;
    metadata?: Record<string, any>;
}
interface RiskAssessmentResponse {
    address: string;
    riskScore: number;
    riskLevel: RiskLevel$5;
    factors: RiskFactor[];
    labels: LabelInfo$1[];
    timestamp: string;
    expiresAt: string;
    cached: boolean;
}
interface RiskFactor {
    name: string;
    weight: number;
    value: number;
    description: string;
}
interface BatchRiskRequest {
    addresses: string[];
    includeLabels?: boolean;
    includeFactors?: boolean;
}
interface BatchRiskResponse {
    results: RiskAssessmentResponse[];
    processedCount: number;
    failedCount: number;
    failures: {
        address: string;
        error: string;
    }[];
}
interface RiskThreshold {
    level: RiskLevel$5;
    minScore: number;
    maxScore: number;
    action: 'allow' | 'review' | 'block';
}
declare class RiskService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Assess risk for a single address
     */
    assess(request: RiskAssessmentRequest): Promise<RiskAssessmentResponse>;
    /**
     * Get cached risk score for an address
     */
    getScore(address: string): Promise<RiskScore$1 | null>;
    /**
     * Batch assess multiple addresses
     */
    batchAssess(request: BatchRiskRequest): Promise<BatchRiskResponse>;
    /**
     * Get risk thresholds configuration
     */
    getThresholds(): Promise<RiskThreshold[]>;
    /**
     * Check if address passes risk threshold
     */
    checkThreshold(address: string, maxRiskLevel?: RiskLevel$5): Promise<{
        passed: boolean;
        riskScore: number;
        riskLevel: RiskLevel$5;
        action: 'allow' | 'review' | 'block';
    }>;
    /**
     * Get risk history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        history: RiskAssessmentResponse[];
        total: number;
    }>;
    /**
     * Invalidate cached risk score
     */
    invalidateCache(address: string): Promise<void>;
    /**
     * Get risk factors configuration
     */
    getFactors(): Promise<{
        factors: {
            name: string;
            weight: number;
            description: string;
            enabled: boolean;
        }[];
    }>;
}

/**
 * KYC Service
 * Wraps /kyc endpoints for Know Your Customer verification
 */

type KYCStatus$1 = 'none' | 'pending' | 'verified' | 'rejected' | 'expired';
type KYCLevel$2 = 'none' | 'basic' | 'standard' | 'enhanced';
interface KYCSubmission {
    address: string;
    documentType: 'passport' | 'driving_license' | 'national_id';
    documentNumber: string;
    firstName: string;
    lastName: string;
    dateOfBirth: string;
    nationality: string;
    documentFrontHash?: string;
    documentBackHash?: string;
    selfieHash?: string;
    metadata?: Record<string, any>;
}
interface KYCVerificationResult {
    address: string;
    status: KYCStatus$1;
    level: KYCLevel$2;
    verifiedAt?: string;
    expiresAt?: string;
    rejectionReason?: string;
    requiredDocuments?: string[];
    provider?: string;
}
interface KYCDocument {
    id: string;
    type: string;
    status: 'pending' | 'verified' | 'rejected';
    uploadedAt: string;
    verifiedAt?: string;
    expiresAt?: string;
}
interface KYCRequirements {
    level: KYCLevel$2;
    requiredDocuments: string[];
    maxTransactionLimit: string;
    features: string[];
}
declare class KYCService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Submit KYC documents for verification
     */
    submit(submission: KYCSubmission): Promise<KYCVerificationResult>;
    /**
     * Get KYC status for an address
     */
    getStatus(address: string): Promise<KYCVerificationResult>;
    /**
     * Check if address is KYC verified
     */
    isVerified(address: string): Promise<boolean>;
    /**
     * Get KYC level for an address
     */
    getLevel(address: string): Promise<KYCLevel$2>;
    /**
     * Upload document for KYC verification
     */
    uploadDocument(address: string, document: {
        type: 'document_front' | 'document_back' | 'selfie' | 'proof_of_address';
        contentHash: string;
        mimeType: string;
        encryptedContent?: string;
    }): Promise<{
        documentId: string;
        status: string;
    }>;
    /**
     * Get uploaded documents for an address
     */
    getDocuments(address: string): Promise<KYCDocument[]>;
    /**
     * Get KYC requirements for a specific level
     */
    getRequirements(level?: KYCLevel$2): Promise<KYCRequirements[]>;
    /**
     * Request KYC level upgrade
     */
    requestUpgrade(address: string, targetLevel: KYCLevel$2): Promise<{
        requestId: string;
        requiredDocuments: string[];
        status: string;
    }>;
    /**
     * Verify KYC attestation on-chain
     */
    verifyOnChain(address: string, chainId: number): Promise<{
        verified: boolean;
        attestationHash?: string;
        verifiedAt?: string;
        level?: KYCLevel$2;
    }>;
    /**
     * Renew expiring KYC
     */
    renew(address: string): Promise<KYCVerificationResult>;
    /**
     * Check if KYC is expiring soon
     */
    checkExpiry(address: string): Promise<{
        isExpiring: boolean;
        expiresAt?: string;
        daysRemaining?: number;
    }>;
}

/**
 * Transaction Service
 * Wraps /tx endpoints for transaction management
 */

type TransactionStatus$1 = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
type RiskLevel$4 = 'low' | 'medium' | 'high' | 'critical';
interface TransactionRequest {
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId: number;
    memo?: string;
    metadata?: Record<string, any>;
}
interface TransactionRecord {
    id: string;
    hash?: string;
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId: number;
    status: TransactionStatus$1;
    riskScore?: number;
    riskLevel?: RiskLevel$4;
    policyResult?: {
        allowed: boolean;
        reason?: string;
        appliedPolicies: string[];
    };
    createdAt: string;
    updatedAt: string;
    completedAt?: string;
    memo?: string;
}
interface TransactionValidation {
    valid: boolean;
    riskScore: number;
    riskLevel: RiskLevel$4;
    policyResult: {
        allowed: boolean;
        reason?: string;
        appliedPolicies: string[];
        requiredApprovals?: number;
    };
    labelWarnings: {
        address: string;
        labels: string[];
        severity: 'low' | 'medium' | 'high' | 'critical';
    }[];
    estimatedGas?: string;
    estimatedFee?: string;
}
interface TransactionHistoryOptions {
    address?: string;
    status?: TransactionStatus$1;
    startDate?: Date;
    endDate?: Date;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'amount' | 'riskScore';
    sortOrder?: 'asc' | 'desc';
}
declare class TransactionService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Validate a transaction before submission
     */
    validate(request: TransactionRequest): Promise<TransactionValidation>;
    /**
     * Submit a transaction for processing
     */
    submit(request: TransactionRequest): Promise<TransactionRecord>;
    /**
     * Get transaction by ID
     */
    get(id: string): Promise<TransactionRecord>;
    /**
     * Get transaction by hash
     */
    getByHash(hash: string): Promise<TransactionRecord>;
    /**
     * Get transaction history
     */
    getHistory(options?: TransactionHistoryOptions): Promise<{
        transactions: TransactionRecord[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Cancel a pending transaction
     */
    cancel(id: string, reason?: string): Promise<TransactionRecord>;
    /**
     * Retry a failed transaction
     */
    retry(id: string): Promise<TransactionRecord>;
    /**
     * Get transaction status updates
     */
    getStatusUpdates(id: string): Promise<{
        updates: {
            status: TransactionStatus$1;
            timestamp: string;
            message?: string;
        }[];
    }>;
    /**
     * Request expedited processing
     */
    expedite(id: string): Promise<{
        success: boolean;
        estimatedCompletionTime?: string;
        additionalFee?: string;
    }>;
    /**
     * Get transaction receipt
     */
    getReceipt(id: string): Promise<{
        transactionHash: string;
        blockNumber: number;
        blockHash: string;
        gasUsed: string;
        effectiveGasPrice: string;
        status: boolean;
        logs: any[];
    }>;
    /**
     * Estimate transaction cost
     */
    estimateCost(request: TransactionRequest): Promise<{
        gasEstimate: string;
        gasPriceWei: string;
        totalCostWei: string;
        totalCostEth: string;
        totalCostUsd?: string;
    }>;
    /**
     * Get pending transactions for an address
     */
    getPending(address: string): Promise<TransactionRecord[]>;
}

/**
 * Policy Service
 * Wraps /policy endpoints for policy management and evaluation
 */

type PolicyDecision$1 = 'allow' | 'deny' | 'review' | 'escalate';
type RiskLevel$3 = 'low' | 'medium' | 'high' | 'critical';
interface Policy {
    id: string;
    name: string;
    description: string;
    type: 'allow' | 'deny' | 'require_approval' | 'limit';
    conditions: PolicyCondition[];
    actions: PolicyAction[];
    priority: number;
    enabled: boolean;
    createdAt: string;
    updatedAt: string;
}
interface PolicyCondition {
    field: string;
    operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'nin' | 'contains' | 'regex';
    value: any;
    logical?: 'and' | 'or';
}
interface PolicyAction {
    type: 'allow' | 'deny' | 'require_approval' | 'notify' | 'delay' | 'limit';
    params?: Record<string, any>;
}
interface PolicyEvaluationRequest {
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId: number;
    transactionType?: string;
    metadata?: Record<string, any>;
}
interface PolicyEvaluationResult {
    decision: PolicyDecision$1;
    appliedPolicies: {
        id: string;
        name: string;
        action: string;
        reason?: string;
    }[];
    riskLevel: RiskLevel$3;
    requiredApprovals?: number;
    approvers?: string[];
    delaySeconds?: number;
    limits?: {
        type: string;
        current: string;
        max: string;
        remaining: string;
    }[];
    warnings: string[];
}
interface PolicyCreateRequest {
    name: string;
    description: string;
    type: 'allow' | 'deny' | 'require_approval' | 'limit';
    conditions: PolicyCondition[];
    actions: PolicyAction[];
    priority?: number;
    enabled?: boolean;
}
declare class PolicyService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Evaluate policies for a transaction
     */
    evaluate(request: PolicyEvaluationRequest): Promise<PolicyEvaluationResult>;
    /**
     * Get all policies
     */
    list(options?: {
        type?: string;
        enabled?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        policies: Policy[];
        total: number;
    }>;
    /**
     * Get policy by ID
     */
    get(id: string): Promise<Policy>;
    /**
     * Create a new policy
     */
    create(request: PolicyCreateRequest): Promise<Policy>;
    /**
     * Update an existing policy
     */
    update(id: string, updates: Partial<PolicyCreateRequest>): Promise<Policy>;
    /**
     * Delete a policy
     */
    delete(id: string): Promise<void>;
    /**
     * Enable a policy
     */
    enable(id: string): Promise<Policy>;
    /**
     * Disable a policy
     */
    disable(id: string): Promise<Policy>;
    /**
     * Test policy against sample data
     */
    test(id: string, testData: PolicyEvaluationRequest): Promise<{
        wouldApply: boolean;
        result: PolicyEvaluationResult;
    }>;
    /**
     * Get policy templates
     */
    getTemplates(): Promise<{
        templates: {
            id: string;
            name: string;
            description: string;
            category: string;
            policy: PolicyCreateRequest;
        }[];
    }>;
    /**
     * Create policy from template
     */
    createFromTemplate(templateId: string, overrides?: Partial<PolicyCreateRequest>): Promise<Policy>;
    /**
     * Get policy audit log
     */
    getAuditLog(id: string, options?: {
        limit?: number;
        offset?: number;
    }): Promise<{
        logs: {
            action: string;
            performedBy: string;
            timestamp: string;
            changes?: Record<string, any>;
        }[];
        total: number;
    }>;
    /**
     * Validate policy configuration
     */
    validate(policy: PolicyCreateRequest): Promise<{
        valid: boolean;
        errors: string[];
        warnings: string[];
    }>;
}

/**
 * Dispute Service
 * Wraps /dispute endpoints for Kleros-based dispute resolution
 */

type DisputeStatus$1 = 'open' | 'in_review' | 'awaiting_evidence' | 'resolved' | 'appealed' | 'closed';
type DisputeRuling$1 = 'claimant_wins' | 'respondent_wins' | 'split' | 'dismissed';
interface Dispute {
    id: string;
    klerosDisputeId?: string;
    transactionId: string;
    transactionHash?: string;
    claimant: string;
    respondent: string;
    amount: string;
    reason: string;
    category: 'fraud' | 'non_delivery' | 'quality' | 'unauthorized' | 'other';
    status: DisputeStatus$1;
    ruling?: DisputeRuling$1;
    evidence: Evidence[];
    timeline: TimelineEvent[];
    arbitrationCost?: string;
    createdAt: string;
    updatedAt: string;
    resolvedAt?: string;
}
interface Evidence {
    id: string;
    type: 'document' | 'screenshot' | 'communication' | 'blockchain_data' | 'other';
    title: string;
    description?: string;
    contentHash: string;
    submittedBy: string;
    submittedAt: string;
}
interface TimelineEvent {
    event: string;
    timestamp: string;
    actor?: string;
    details?: Record<string, any>;
}
interface DisputeCreateRequest {
    transactionId: string;
    reason: string;
    category: 'fraud' | 'non_delivery' | 'quality' | 'unauthorized' | 'other';
    description: string;
    evidence?: {
        type: Evidence['type'];
        title: string;
        description?: string;
        contentHash: string;
    }[];
}
interface DisputeListOptions {
    status?: DisputeStatus$1;
    claimant?: string;
    respondent?: string;
    category?: string;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'amount' | 'status';
    sortOrder?: 'asc' | 'desc';
}
declare class DisputeService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create a new dispute
     */
    create(request: DisputeCreateRequest): Promise<Dispute>;
    /**
     * Get dispute by ID
     */
    get(id: string): Promise<Dispute>;
    /**
     * Get dispute by Kleros dispute ID
     */
    getByKlerosId(klerosDisputeId: string): Promise<Dispute>;
    /**
     * List disputes
     */
    list(options?: DisputeListOptions): Promise<{
        disputes: Dispute[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Submit evidence for a dispute
     */
    submitEvidence(disputeId: string, evidence: {
        type: Evidence['type'];
        title: string;
        description?: string;
        contentHash: string;
    }): Promise<Evidence>;
    /**
     * Get evidence for a dispute
     */
    getEvidence(disputeId: string): Promise<Evidence[]>;
    /**
     * Escalate dispute to Kleros
     */
    escalateToKleros(disputeId: string): Promise<{
        klerosDisputeId: string;
        arbitrationCost: string;
        estimatedResolutionTime: string;
    }>;
    /**
     * Get arbitration cost estimate
     */
    getArbitrationCost(category: string): Promise<{
        cost: string;
        currency: string;
        estimatedDuration: string;
    }>;
    /**
     * Accept dispute resolution
     */
    acceptResolution(disputeId: string): Promise<Dispute>;
    /**
     * Appeal dispute ruling
     */
    appeal(disputeId: string, reason: string): Promise<{
        appealId: string;
        appealCost: string;
        deadline: string;
    }>;
    /**
     * Withdraw dispute
     */
    withdraw(disputeId: string, reason?: string): Promise<Dispute>;
    /**
     * Get dispute statistics
     */
    getStatistics(address?: string): Promise<{
        total: number;
        byStatus: Record<DisputeStatus$1, number>;
        byCategory: Record<string, number>;
        averageResolutionTime: number;
        winRate?: number;
    }>;
    /**
     * Get dispute timeline
     */
    getTimeline(disputeId: string): Promise<TimelineEvent[]>;
    /**
     * Check if dispute is eligible for arbitration
     */
    checkEligibility(disputeId: string): Promise<{
        eligible: boolean;
        reason?: string;
        requirements?: string[];
    }>;
}

/**
 * Reputation Service
 * Wraps /reputation endpoints for 5-tier reputation system
 */

type ReputationTier$1 = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
interface ReputationScore$1 {
    address: string;
    tier: ReputationTier$1;
    score: number;
    totalTransactions: number;
}
interface ReputationProfile {
    address: string;
    tier: ReputationTier$1;
    score: number;
    totalTransactions: number;
    successfulTransactions: number;
    disputesInitiated: number;
    disputesLost: number;
    averageTransactionValue: string;
    memberSince: string;
    lastActivityAt: string;
    badges: Badge[];
    history: ReputationEvent[];
}
interface Badge {
    id: string;
    name: string;
    description: string;
    icon: string;
    earnedAt: string;
    category: 'transaction' | 'community' | 'compliance' | 'special';
}
interface ReputationEvent {
    id: string;
    type: 'transaction' | 'dispute' | 'upgrade' | 'downgrade' | 'badge' | 'penalty';
    description: string;
    scoreChange: number;
    timestamp: string;
    metadata?: Record<string, any>;
}
interface TierRequirements {
    tier: ReputationTier$1;
    minScore: number;
    minTransactions: number;
    maxDisputeRate: number;
    benefits: string[];
    transactionLimits: {
        daily: string;
        weekly: string;
        monthly: string;
    };
}
interface LeaderboardEntry {
    rank: number;
    address: string;
    tier: ReputationTier$1;
    score: number;
    totalTransactions: number;
    badges: number;
}
declare class ReputationService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get reputation profile for an address
     */
    getProfile(address: string): Promise<ReputationProfile>;
    /**
     * Get reputation score
     */
    getScore(address: string): Promise<ReputationScore$1>;
    /**
     * Get reputation tier
     */
    getTier(address: string): Promise<ReputationTier$1>;
    /**
     * Get tier requirements
     */
    getTierRequirements(tier?: ReputationTier$1): Promise<TierRequirements[]>;
    /**
     * Get progress to next tier
     */
    getProgress(address: string): Promise<{
        currentTier: ReputationTier$1;
        nextTier?: ReputationTier$1;
        currentScore: number;
        requiredScore?: number;
        progress: number;
        missingRequirements: string[];
    }>;
    /**
     * Get reputation history
     */
    getHistory(address: string, options?: {
        type?: string;
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        events: ReputationEvent[];
        total: number;
    }>;
    /**
     * Get badges for an address
     */
    getBadges(address: string): Promise<Badge[]>;
    /**
     * Get available badges
     */
    getAvailableBadges(): Promise<{
        badges: {
            id: string;
            name: string;
            description: string;
            icon: string;
            category: string;
            requirements: string[];
        }[];
    }>;
    /**
     * Get leaderboard
     */
    getLeaderboard(options?: {
        tier?: ReputationTier$1;
        limit?: number;
        offset?: number;
    }): Promise<{
        entries: LeaderboardEntry[];
        total: number;
    }>;
    /**
     * Get reputation statistics
     */
    getStatistics(): Promise<{
        totalUsers: number;
        byTier: Record<ReputationTier$1, number>;
        averageScore: number;
        topBadges: {
            badge: Badge;
            count: number;
        }[];
    }>;
    /**
     * Calculate reputation impact of a transaction
     */
    calculateImpact(address: string, transaction: {
        amount: string;
        successful: boolean;
        counterpartyTier?: ReputationTier$1;
    }): Promise<{
        scoreChange: number;
        newScore: number;
        tierChange?: {
            from: ReputationTier$1;
            to: ReputationTier$1;
        };
        badgesEarned?: Badge[];
    }>;
    /**
     * Get transaction limits based on reputation
     */
    getLimits(address: string): Promise<{
        tier: ReputationTier$1;
        limits: {
            daily: {
                limit: string;
                used: string;
                remaining: string;
            };
            weekly: {
                limit: string;
                used: string;
                remaining: string;
            };
            monthly: {
                limit: string;
                used: string;
                remaining: string;
            };
        };
    }>;
    /**
     * Compare reputation between two addresses
     */
    compare(address1: string, address2: string): Promise<{
        address1: ReputationProfile;
        address2: ReputationProfile;
        comparison: {
            tierDifference: number;
            scoreDifference: number;
            transactionDifference: number;
        };
    }>;
}

/**
 * Bulk Scoring Service
 * Wraps /bulk endpoints for batch transaction scoring
 */

type RiskLevel$2 = 'low' | 'medium' | 'high' | 'critical';
interface BulkScoringRequest {
    transactions: BulkTransaction[];
    options?: {
        includeLabels?: boolean;
        includeFactors?: boolean;
        parallelism?: number;
        timeout?: number;
    };
}
interface BulkTransaction {
    id: string;
    from: string;
    to: string;
    amount: string;
    tokenAddress?: string;
    chainId?: number;
    metadata?: Record<string, any>;
}
interface BulkScoringResult {
    jobId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    results: TransactionScoreResult[];
    processedCount: number;
    failedCount: number;
    failures: {
        id: string;
        error: string;
    }[];
    startedAt: string;
    completedAt?: string;
    processingTimeMs?: number;
}
interface TransactionScoreResult {
    id: string;
    from: string;
    to: string;
    riskScore: number;
    riskLevel: RiskLevel$2;
    fromRisk: {
        score: number;
        level: RiskLevel$2;
    };
    toRisk: {
        score: number;
        level: RiskLevel$2;
    };
    labels?: {
        address: string;
        labels: string[];
    }[];
    factors?: {
        name: string;
        weight: number;
        value: number;
    }[];
    allowed: boolean;
    reason?: string;
}
interface BulkJobStatus {
    jobId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
    processedCount: number;
    totalCount: number;
    estimatedTimeRemaining?: number;
    startedAt: string;
    updatedAt: string;
}
declare class BulkService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Submit bulk scoring request
     */
    submit(request: BulkScoringRequest): Promise<{
        jobId: string;
        status: string;
        estimatedCompletionTime: string;
    }>;
    /**
     * Submit and wait for results (synchronous for small batches)
     */
    score(request: BulkScoringRequest): Promise<BulkScoringResult>;
    /**
     * Get job status
     */
    getStatus(jobId: string): Promise<BulkJobStatus>;
    /**
     * Get job results
     */
    getResults(jobId: string, options?: {
        limit?: number;
        offset?: number;
        status?: 'success' | 'failed';
    }): Promise<{
        results: TransactionScoreResult[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Cancel a bulk job
     */
    cancel(jobId: string): Promise<{
        cancelled: boolean;
        processedBeforeCancel: number;
    }>;
    /**
     * Get job history
     */
    getHistory(options?: {
        limit?: number;
        offset?: number;
        status?: string;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        jobs: BulkJobStatus[];
        total: number;
    }>;
    /**
     * Get bulk scoring statistics
     */
    getStatistics(): Promise<{
        totalJobs: number;
        totalTransactionsProcessed: number;
        averageProcessingTime: number;
        successRate: number;
        byStatus: Record<string, number>;
    }>;
    /**
     * Download results as CSV
     */
    downloadResults(jobId: string): Promise<Blob>;
    /**
     * Retry failed transactions in a job
     */
    retryFailed(jobId: string): Promise<{
        newJobId: string;
        transactionsToRetry: number;
    }>;
}

/**
 * Webhook Service
 * Wraps /webhook endpoints for webhook management
 */

type WebhookEventType = 'transaction.created' | 'transaction.completed' | 'transaction.failed' | 'risk.high_score' | 'risk.critical' | 'kyc.verified' | 'kyc.rejected' | 'dispute.created' | 'dispute.resolved' | 'pep.match' | 'edd.required' | 'monitoring.alert';
interface Webhook {
    id: string;
    url: string;
    events: WebhookEventType[];
    secret?: string;
    enabled: boolean;
    description?: string;
    metadata?: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    lastTriggeredAt?: string;
    failureCount: number;
}
interface WebhookDelivery {
    id: string;
    webhookId: string;
    event: WebhookEventType;
    payload: Record<string, any>;
    status: 'pending' | 'delivered' | 'failed';
    statusCode?: number;
    responseBody?: string;
    attempts: number;
    nextRetryAt?: string;
    createdAt: string;
    deliveredAt?: string;
}
interface WebhookCreateRequest {
    url: string;
    events: WebhookEventType[];
    description?: string;
    metadata?: Record<string, any>;
    enabled?: boolean;
}
declare class WebhookService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create a new webhook
     */
    create(request: WebhookCreateRequest): Promise<Webhook & {
        secret: string;
    }>;
    /**
     * List all webhooks
     */
    list(options?: {
        enabled?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        webhooks: Webhook[];
        total: number;
    }>;
    /**
     * Get webhook by ID
     */
    get(id: string): Promise<Webhook>;
    /**
     * Update a webhook
     */
    update(id: string, updates: Partial<WebhookCreateRequest>): Promise<Webhook>;
    /**
     * Delete a webhook
     */
    delete(id: string): Promise<void>;
    /**
     * Enable a webhook
     */
    enable(id: string): Promise<Webhook>;
    /**
     * Disable a webhook
     */
    disable(id: string): Promise<Webhook>;
    /**
     * Rotate webhook secret
     */
    rotateSecret(id: string): Promise<{
        secret: string;
    }>;
    /**
     * Test a webhook
     */
    test(id: string, event?: WebhookEventType): Promise<{
        success: boolean;
        statusCode?: number;
        responseTime?: number;
        error?: string;
    }>;
    /**
     * Get webhook deliveries
     */
    getDeliveries(webhookId: string, options?: {
        status?: 'pending' | 'delivered' | 'failed';
        event?: WebhookEventType;
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        deliveries: WebhookDelivery[];
        total: number;
    }>;
    /**
     * Retry a failed delivery
     */
    retryDelivery(webhookId: string, deliveryId: string): Promise<WebhookDelivery>;
    /**
     * Get available event types
     */
    getEventTypes(): Promise<{
        events: {
            type: WebhookEventType;
            description: string;
            samplePayload: Record<string, any>;
        }[];
    }>;
    /**
     * Get webhook statistics
     */
    getStatistics(webhookId?: string): Promise<{
        totalDeliveries: number;
        successfulDeliveries: number;
        failedDeliveries: number;
        averageResponseTime: number;
        byEvent: Record<WebhookEventType, number>;
    }>;
    /**
     * Verify webhook signature
     */
    verifySignature(payload: string, signature: string, secret: string): boolean;
}

/**
 * PEP Screening Service
 * Wraps /pep endpoints for Politically Exposed Person screening
 */

interface PEPScreeningRequest {
    address: string;
    fullName?: string;
    dateOfBirth?: string;
    nationality?: string;
    includeRelatives?: boolean;
    includeAssociates?: boolean;
    providers?: string[];
}
interface PEPMatch {
    id: string;
    name: string;
    matchScore: number;
    matchType: 'exact' | 'fuzzy' | 'partial';
    pepType: 'pep' | 'relative' | 'associate';
    position?: string;
    country?: string;
    dateOfBirth?: string;
    source: string;
    listType: 'sanction' | 'pep' | 'watchlist' | 'adverse_media';
    lastUpdated: string;
    details?: Record<string, any>;
}
interface PEPScreeningResult {
    address: string;
    screened: boolean;
    matches: PEPMatch[];
    highestMatchScore: number;
    riskLevel: 'clear' | 'low' | 'medium' | 'high' | 'critical';
    requiresEDD: boolean;
    screenedAt: string;
    expiresAt: string;
    providers: string[];
}
interface PEPHistoryEntry {
    id: string;
    address: string;
    result: PEPScreeningResult;
    triggeredBy: 'manual' | 'automated' | 'transaction';
    performedAt: string;
    performedBy?: string;
}
declare class PEPService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Screen an address for PEP matches
     */
    screen(request: PEPScreeningRequest): Promise<PEPScreeningResult>;
    /**
     * Get cached screening result
     */
    getResult(address: string): Promise<PEPScreeningResult | null>;
    /**
     * Check if address has PEP matches
     */
    hasPEPMatches(address: string): Promise<{
        hasMatches: boolean;
        matchCount: number;
        highestRisk: string;
    }>;
    /**
     * Get screening history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        history: PEPHistoryEntry[];
        total: number;
    }>;
    /**
     * Batch screen multiple addresses
     */
    batchScreen(addresses: string[]): Promise<{
        results: PEPScreeningResult[];
        processedCount: number;
        failedCount: number;
    }>;
    /**
     * Acknowledge a PEP match (mark as reviewed)
     */
    acknowledgeMatch(address: string, matchId: string, decision: {
        approved: boolean;
        reason: string;
        reviewedBy: string;
    }): Promise<{
        acknowledged: boolean;
    }>;
    /**
     * Get match details
     */
    getMatchDetails(address: string, matchId: string): Promise<PEPMatch & {
        fullProfile?: Record<string, any>;
        relatedEntities?: {
            name: string;
            relationship: string;
        }[];
    }>;
    /**
     * Get available screening providers
     */
    getProviders(): Promise<{
        providers: {
            id: string;
            name: string;
            description: string;
            coverage: string[];
            enabled: boolean;
        }[];
    }>;
    /**
     * Invalidate cached screening result
     */
    invalidateCache(address: string): Promise<void>;
    /**
     * Get PEP screening statistics
     */
    getStatistics(): Promise<{
        totalScreenings: number;
        matchesFound: number;
        byRiskLevel: Record<string, number>;
        byListType: Record<string, number>;
        averageMatchScore: number;
    }>;
    /**
     * Schedule periodic rescreening
     */
    scheduleRescreening(address: string, intervalDays: number): Promise<{
        scheduled: boolean;
        nextScreeningAt: string;
    }>;
}

/**
 * EDD (Enhanced Due Diligence) Service
 * Wraps /edd endpoints for EDD case management
 */

type EDDStatus = 'pending' | 'in_review' | 'awaiting_documents' | 'approved' | 'rejected' | 'escalated';
type EDDTrigger = 'high_risk_score' | 'pep_match' | 'large_transaction' | 'suspicious_pattern' | 'manual_request' | 'regulatory_requirement';
interface EDDCase {
    id: string;
    address: string;
    status: EDDStatus;
    trigger: EDDTrigger;
    triggerDetails: Record<string, any>;
    riskScore: number;
    assignedTo?: string;
    documents: EDDDocument[];
    notes: EDDNote[];
    timeline: EDDTimelineEvent[];
    createdAt: string;
    updatedAt: string;
    resolvedAt?: string;
    resolution?: {
        decision: 'approved' | 'rejected';
        reason: string;
        resolvedBy: string;
    };
}
interface EDDDocument {
    id: string;
    type: string;
    name: string;
    contentHash: string;
    mimeType: string;
    status: 'pending' | 'verified' | 'rejected';
    uploadedAt: string;
    verifiedAt?: string;
    verifiedBy?: string;
    rejectionReason?: string;
}
interface EDDNote {
    id: string;
    content: string;
    createdBy: string;
    createdAt: string;
    visibility: 'internal' | 'customer_visible';
}
interface EDDTimelineEvent {
    event: string;
    timestamp: string;
    actor?: string;
    details?: Record<string, any>;
}
interface EDDCreateRequest {
    address: string;
    trigger: EDDTrigger;
    triggerDetails?: Record<string, any>;
    priority?: 'low' | 'medium' | 'high' | 'urgent';
    notes?: string;
}
interface EDDListOptions {
    status?: EDDStatus;
    trigger?: EDDTrigger;
    assignedTo?: string;
    priority?: string;
    limit?: number;
    offset?: number;
    sortBy?: 'createdAt' | 'updatedAt' | 'riskScore';
    sortOrder?: 'asc' | 'desc';
}
declare class EDDService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create an EDD case
     */
    create(request: EDDCreateRequest): Promise<EDDCase>;
    /**
     * Get EDD case by ID
     */
    get(id: string): Promise<EDDCase>;
    /**
     * Get EDD case for an address
     */
    getByAddress(address: string): Promise<EDDCase | null>;
    /**
     * List EDD cases
     */
    list(options?: EDDListOptions): Promise<{
        cases: EDDCase[];
        total: number;
        hasMore: boolean;
    }>;
    /**
     * Assign EDD case to reviewer
     */
    assign(id: string, assignee: string): Promise<EDDCase>;
    /**
     * Update EDD case status
     */
    updateStatus(id: string, status: EDDStatus, note?: string): Promise<EDDCase>;
    /**
     * Upload document for EDD case
     */
    uploadDocument(id: string, document: {
        type: string;
        name: string;
        contentHash: string;
        mimeType: string;
    }): Promise<EDDDocument>;
    /**
     * Get documents for EDD case
     */
    getDocuments(id: string): Promise<EDDDocument[]>;
    /**
     * Verify document
     */
    verifyDocument(caseId: string, documentId: string, decision: {
        verified: boolean;
        reason?: string;
        verifiedBy: string;
    }): Promise<EDDDocument>;
    /**
     * Add note to EDD case
     */
    addNote(id: string, note: {
        content: string;
        visibility?: 'internal' | 'customer_visible';
    }): Promise<EDDNote>;
    /**
     * Get notes for EDD case
     */
    getNotes(id: string): Promise<EDDNote[]>;
    /**
     * Resolve EDD case
     */
    resolve(id: string, resolution: {
        decision: 'approved' | 'rejected';
        reason: string;
        resolvedBy: string;
    }): Promise<EDDCase>;
    /**
     * Escalate EDD case
     */
    escalate(id: string, reason: string, escalateTo?: string): Promise<EDDCase>;
    /**
     * Get EDD case timeline
     */
    getTimeline(id: string): Promise<EDDTimelineEvent[]>;
    /**
     * Get EDD requirements for a trigger type
     */
    getRequirements(trigger: EDDTrigger): Promise<{
        requiredDocuments: string[];
        requiredChecks: string[];
        estimatedDuration: string;
    }>;
    /**
     * Get EDD statistics
     */
    getStatistics(): Promise<{
        totalCases: number;
        byStatus: Record<EDDStatus, number>;
        byTrigger: Record<EDDTrigger, number>;
        averageResolutionTime: number;
        approvalRate: number;
    }>;
    /**
     * Check if address requires EDD
     */
    checkRequired(address: string): Promise<{
        required: boolean;
        reasons: EDDTrigger[];
        existingCase?: string;
    }>;
}

/**
 * Ongoing Monitoring Service
 * Wraps /monitoring endpoints for continuous compliance monitoring
 */

type AlertSeverity$1 = 'info' | 'low' | 'medium' | 'high' | 'critical';
type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'dismissed';
type AlertType$1 = 'risk_increase' | 'new_sanction_match' | 'suspicious_pattern' | 'velocity_breach' | 'pep_status_change' | 'kyc_expiry' | 'threshold_breach' | 'unusual_activity';
interface MonitoringAlert {
    id: string;
    type: AlertType$1;
    severity: AlertSeverity$1;
    status: AlertStatus;
    address: string;
    title: string;
    description: string;
    details: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    acknowledgedAt?: string;
    acknowledgedBy?: string;
    resolvedAt?: string;
    resolvedBy?: string;
    resolution?: string;
}
interface MonitoringRule {
    id: string;
    name: string;
    description: string;
    type: AlertType$1;
    conditions: RuleCondition[];
    severity: AlertSeverity$1;
    enabled: boolean;
    createdAt: string;
    updatedAt: string;
}
interface RuleCondition {
    field: string;
    operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'in' | 'change';
    value: any;
    timeWindow?: string;
}
interface MonitoredAddress {
    address: string;
    enabled: boolean;
    monitoringSince: string;
    lastCheckedAt: string;
    alertCount: number;
    currentRiskScore: number;
    riskTrend: 'stable' | 'increasing' | 'decreasing';
    tags?: string[];
}
interface MonitoringConfig {
    checkInterval: number;
    riskThreshold: number;
    velocityLimits: {
        daily: string;
        weekly: string;
        monthly: string;
    };
    enabledAlertTypes: AlertType$1[];
    notificationChannels: string[];
}
declare class MonitoringService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Add address to monitoring
     */
    addAddress(address: string, options?: {
        tags?: string[];
        priority?: 'low' | 'medium' | 'high';
    }): Promise<MonitoredAddress>;
    /**
     * Remove address from monitoring
     */
    removeAddress(address: string): Promise<void>;
    /**
     * Get monitored addresses
     */
    getAddresses(options?: {
        enabled?: boolean;
        hasAlerts?: boolean;
        tags?: string[];
        limit?: number;
        offset?: number;
    }): Promise<{
        addresses: MonitoredAddress[];
        total: number;
    }>;
    /**
     * Get address monitoring status
     */
    getAddressStatus(address: string): Promise<MonitoredAddress>;
    /**
     * Get alerts
     */
    getAlerts(options?: {
        address?: string;
        type?: AlertType$1;
        severity?: AlertSeverity$1;
        status?: AlertStatus;
        limit?: number;
        offset?: number;
        startDate?: Date;
        endDate?: Date;
    }): Promise<{
        alerts: MonitoringAlert[];
        total: number;
    }>;
    /**
     * Get alert by ID
     */
    getAlert(id: string): Promise<MonitoringAlert>;
    /**
     * Acknowledge an alert
     */
    acknowledgeAlert(id: string, acknowledgedBy: string): Promise<MonitoringAlert>;
    /**
     * Resolve an alert
     */
    resolveAlert(id: string, resolution: {
        resolvedBy: string;
        resolution: string;
        actionsTaken?: string[];
    }): Promise<MonitoringAlert>;
    /**
     * Dismiss an alert
     */
    dismissAlert(id: string, reason: string, dismissedBy: string): Promise<MonitoringAlert>;
    /**
     * Get monitoring rules
     */
    getRules(): Promise<MonitoringRule[]>;
    /**
     * Create a monitoring rule
     */
    createRule(rule: Omit<MonitoringRule, 'id' | 'createdAt' | 'updatedAt'>): Promise<MonitoringRule>;
    /**
     * Update a monitoring rule
     */
    updateRule(id: string, updates: Partial<MonitoringRule>): Promise<MonitoringRule>;
    /**
     * Delete a monitoring rule
     */
    deleteRule(id: string): Promise<void>;
    /**
     * Enable/disable a rule
     */
    toggleRule(id: string, enabled: boolean): Promise<MonitoringRule>;
    /**
     * Get monitoring configuration
     */
    getConfig(): Promise<MonitoringConfig>;
    /**
     * Update monitoring configuration
     */
    updateConfig(config: Partial<MonitoringConfig>): Promise<MonitoringConfig>;
    /**
     * Trigger manual check for an address
     */
    triggerCheck(address: string): Promise<{
        checked: boolean;
        alertsGenerated: number;
        results: Record<string, any>;
    }>;
    /**
     * Get monitoring statistics
     */
    getStatistics(): Promise<{
        monitoredAddresses: number;
        totalAlerts: number;
        openAlerts: number;
        alertsByType: Record<AlertType$1, number>;
        alertsBySeverity: Record<AlertSeverity$1, number>;
        averageResolutionTime: number;
    }>;
    /**
     * Get risk trend for an address
     */
    getRiskTrend(address: string, options?: {
        days?: number;
    }): Promise<{
        address: string;
        dataPoints: {
            timestamp: string;
            riskScore: number;
            events?: string[];
        }[];
        trend: 'stable' | 'increasing' | 'decreasing';
        averageScore: number;
    }>;
}

/**
 * Label Service
 * Wraps /label endpoints for address labeling and categorization
 */

type LabelCategory = 'exchange' | 'defi' | 'bridge' | 'mixer' | 'gambling' | 'scam' | 'sanctions' | 'darknet' | 'ransomware' | 'theft' | 'phishing' | 'nft' | 'dao' | 'custodian' | 'payment_processor' | 'other';
type LabelSeverity = 'info' | 'low' | 'medium' | 'high' | 'critical';
interface AddressLabel {
    id: string;
    address: string;
    label: string;
    category: LabelCategory;
    severity: LabelSeverity;
    confidence: number;
    source: string;
    description?: string;
    metadata?: Record<string, any>;
    createdAt: string;
    updatedAt: string;
    expiresAt?: string;
    verified: boolean;
}
interface LabelSearchResult {
    address: string;
    labels: AddressLabel[];
    riskImplication: 'safe' | 'caution' | 'warning' | 'danger';
    aggregatedSeverity: LabelSeverity;
}
interface LabelStatistics {
    totalLabels: number;
    byCategory: Record<LabelCategory, number>;
    bySeverity: Record<LabelSeverity, number>;
    bySource: Record<string, number>;
    recentlyAdded: number;
    recentlyUpdated: number;
}
declare class LabelService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get labels for an address
     */
    getLabels(address: string): Promise<LabelSearchResult>;
    /**
     * Check if address has specific label categories
     */
    hasLabels(address: string, categories?: LabelCategory[]): Promise<{
        hasLabels: boolean;
        matchedCategories: LabelCategory[];
        highestSeverity?: LabelSeverity;
    }>;
    /**
     * Batch check multiple addresses
     */
    batchCheck(addresses: string[], options?: {
        categories?: LabelCategory[];
        minSeverity?: LabelSeverity;
    }): Promise<{
        results: {
            address: string;
            hasLabels: boolean;
            labels: AddressLabel[];
            riskImplication: string;
        }[];
        processedCount: number;
    }>;
    /**
     * Add a label to an address
     */
    addLabel(label: {
        address: string;
        label: string;
        category: LabelCategory;
        severity: LabelSeverity;
        confidence?: number;
        description?: string;
        metadata?: Record<string, any>;
        expiresAt?: string;
    }): Promise<AddressLabel>;
    /**
     * Update a label
     */
    updateLabel(id: string, updates: Partial<{
        label: string;
        category: LabelCategory;
        severity: LabelSeverity;
        confidence: number;
        description: string;
        metadata: Record<string, any>;
        expiresAt: string;
        verified: boolean;
    }>): Promise<AddressLabel>;
    /**
     * Remove a label
     */
    removeLabel(id: string): Promise<void>;
    /**
     * Verify a label
     */
    verifyLabel(id: string, verified: boolean, verifiedBy: string): Promise<AddressLabel>;
    /**
     * Search labels
     */
    search(options?: {
        query?: string;
        category?: LabelCategory;
        severity?: LabelSeverity;
        source?: string;
        verified?: boolean;
        limit?: number;
        offset?: number;
    }): Promise<{
        labels: AddressLabel[];
        total: number;
    }>;
    /**
     * Get label categories with descriptions
     */
    getCategories(): Promise<{
        categories: {
            id: LabelCategory;
            name: string;
            description: string;
            defaultSeverity: LabelSeverity;
            riskWeight: number;
        }[];
    }>;
    /**
     * Get label sources
     */
    getSources(): Promise<{
        sources: {
            id: string;
            name: string;
            description: string;
            reliability: number;
            labelCount: number;
        }[];
    }>;
    /**
     * Get label statistics
     */
    getStatistics(): Promise<LabelStatistics>;
    /**
     * Get label history for an address
     */
    getHistory(address: string, options?: {
        limit?: number;
        offset?: number;
    }): Promise<{
        history: {
            action: 'added' | 'updated' | 'removed';
            label: AddressLabel;
            timestamp: string;
            actor?: string;
        }[];
        total: number;
    }>;
    /**
     * Report a label (for moderation)
     */
    reportLabel(id: string, report: {
        reason: string;
        details?: string;
        reportedBy: string;
    }): Promise<{
        reported: boolean;
        reportId: string;
    }>;
    /**
     * Get risky label categories that should trigger blocking
     */
    getBlockingCategories(): Promise<LabelCategory[]>;
}

/**
 * MEV Protection Service
 * Provides protection against Maximal Extractable Value attacks
 * Integrates with Flashbots and private mempool services
 */

type MEVProtectionLevel = 'none' | 'basic' | 'enhanced' | 'maximum';
interface MEVConfig {
    enabled: boolean;
    protectionLevel: MEVProtectionLevel;
    flashbotsEnabled: boolean;
    privateMempoolEnabled: boolean;
    maxSlippage: number;
    deadlineMinutes: number;
}
interface MEVProtectedTransaction {
    id: string;
    originalTx: {
        to: string;
        data: string;
        value: string;
        gasLimit: string;
    };
    protectedTx?: {
        bundleHash?: string;
        privateTxHash?: string;
    };
    status: 'pending' | 'submitted' | 'included' | 'failed';
    protectionType: 'flashbots' | 'private_mempool' | 'none';
    submittedAt?: string;
    includedAt?: string;
    blockNumber?: number;
    savings?: {
        estimatedMEV: string;
        savedAmount: string;
        protectionCost: string;
    };
}
interface FlashbotsBundle {
    bundleHash: string;
    transactions: string[];
    targetBlock: number;
    status: 'pending' | 'included' | 'failed';
    simulationResult?: {
        success: boolean;
        gasUsed: string;
        profit: string;
    };
}
interface MEVAnalysis {
    transactionHash?: string;
    vulnerabilities: {
        type: 'sandwich' | 'frontrun' | 'backrun' | 'liquidation';
        risk: 'low' | 'medium' | 'high';
        estimatedLoss: string;
        description: string;
    }[];
    recommendedProtection: MEVProtectionLevel;
    estimatedSavings: string;
}
declare class MEVProtection extends BaseService {
    private config;
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get current MEV protection configuration
     */
    getConfig(): MEVConfig;
    /**
     * Update MEV protection configuration
     */
    setConfig(config: Partial<MEVConfig>): void;
    /**
     * Analyze transaction for MEV vulnerabilities
     */
    analyze(transaction: {
        to: string;
        data: string;
        value: string;
        from?: string;
    }): Promise<MEVAnalysis>;
    /**
     * Submit transaction with MEV protection
     */
    submitProtected(transaction: {
        to: string;
        data: string;
        value: string;
        gasLimit: string;
        maxFeePerGas?: string;
        maxPriorityFeePerGas?: string;
        signature: string;
    }): Promise<MEVProtectedTransaction>;
    /**
     * Submit Flashbots bundle
     */
    submitBundle(bundle: {
        signedTransactions: string[];
        targetBlockNumber?: number;
        minTimestamp?: number;
        maxTimestamp?: number;
    }): Promise<FlashbotsBundle>;
    /**
     * Get bundle status
     */
    getBundleStatus(bundleHash: string): Promise<FlashbotsBundle>;
    /**
     * Simulate transaction
     */
    simulate(transaction: {
        to: string;
        data: string;
        value: string;
        from: string;
        gasLimit?: string;
    }): Promise<{
        success: boolean;
        gasUsed: string;
        returnValue: string;
        error?: string;
        logs: any[];
    }>;
    /**
     * Get protected transaction status
     */
    getTransactionStatus(id: string): Promise<MEVProtectedTransaction>;
    /**
     * Get transaction history with MEV protection
     */
    getHistory(options?: {
        address?: string;
        status?: string;
        limit?: number;
        offset?: number;
    }): Promise<{
        transactions: MEVProtectedTransaction[];
        total: number;
        totalSavings: string;
    }>;
    /**
     * Cancel pending protected transaction
     */
    cancel(id: string): Promise<{
        cancelled: boolean;
        reason?: string;
    }>;
    /**
     * Get MEV statistics
     */
    getStatistics(): Promise<{
        totalProtectedTransactions: number;
        totalSavings: string;
        averageSavingsPerTx: string;
        byProtectionType: Record<string, number>;
        successRate: number;
    }>;
    /**
     * Check if Flashbots relay is available
     */
    checkFlashbotsStatus(): Promise<{
        available: boolean;
        relayUrl: string;
        latestBlock: number;
        bundlePendingCount: number;
    }>;
    /**
     * Get recommended gas settings for protected transaction
     */
    getGasRecommendation(): Promise<{
        baseFee: string;
        maxPriorityFee: string;
        maxFee: string;
        estimatedConfirmationTime: number;
    }>;
}

/**
 * Compliance Service - Unified Compliance Evaluation
 *
 * Provides access to the AMTTP Orchestrator's compliance evaluation
 * which combines ML risk scoring, sanctions screening, AML monitoring,
 * and geographic risk assessment.
 */

type ComplianceAction = 'ALLOW' | 'REQUIRE_INFO' | 'REQUIRE_ESCROW' | 'BLOCK' | 'REVIEW';
type EntityType = 'RETAIL' | 'INSTITUTIONAL' | 'VASP' | 'HIGH_NET_WORTH' | 'PEP' | 'UNVERIFIED';
type KYCLevel$1 = 'NONE' | 'BASIC' | 'STANDARD' | 'ENHANCED';
type RiskTolerance = 'STRICT' | 'MODERATE' | 'RELAXED';
interface EntityProfile {
    address: string;
    entity_type: EntityType;
    kyc_level: KYCLevel$1;
    risk_tolerance: RiskTolerance;
    jurisdiction: string;
    daily_limit_eth: number;
    monthly_limit_eth: number;
    single_tx_limit_eth: number;
    sanctions_checked: boolean;
    pep_checked: boolean;
    source_of_funds_verified: boolean;
    travel_rule_threshold_eth: number;
    total_transactions: number;
    daily_volume_eth: number;
    monthly_volume_eth: number;
    risk_score_cache?: number;
    last_activity?: string;
    created_at: string;
    updated_at: string;
}
interface ComplianceCheck {
    service: string;
    check_type: string;
    passed: boolean;
    score?: number;
    details?: Record<string, unknown>;
    action_required?: string;
    reason?: string;
}
interface EvaluateRequest {
    from_address: string;
    to_address: string;
    value_eth: number;
    asset?: string;
    chain_id?: number;
    metadata?: Record<string, unknown>;
}
interface EvaluateResponse {
    decision_id: string;
    timestamp: string;
    from_address: string;
    to_address: string;
    value_eth: number;
    originator_profile: EntityProfile;
    beneficiary_profile: EntityProfile;
    checks: ComplianceCheck[];
    action: ComplianceAction;
    risk_score: number;
    reasons: string[];
    requires_travel_rule: boolean;
    requires_sar: boolean;
    requires_escrow: boolean;
    escrow_duration_hours: number;
    processing_time_ms: number;
}
interface DashboardStats$1 {
    total_transactions: number;
    transactions_today: number;
    high_risk_count: number;
    blocked_count: number;
    pending_review: number;
    total_value_eth: number;
    avg_risk_score: number;
    compliance_rate: number;
}
interface DashboardAlert {
    id: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    type: string;
    message: string;
    address: string;
    timestamp: string;
    acknowledged: boolean;
}
interface TimelineDataPoint {
    timestamp: string;
    transactions: number;
    volume: number;
    risk_score: number;
    blocked: number;
}
interface DecisionRecord {
    decision_id: string;
    timestamp: string;
    from_address: string;
    to_address: string;
    value_eth: number;
    action: ComplianceAction;
    risk_score: number;
}
interface DecisionListOptions {
    limit?: number;
    offset?: number;
    action?: ComplianceAction;
    from_date?: string;
    to_date?: string;
}
declare class ComplianceService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Evaluate a transaction for compliance
     * This is the main entry point for transaction evaluation
     */
    evaluate(request: EvaluateRequest): Promise<EvaluateResponse>;
    /**
     * Evaluate with UI integrity verification
     * Binds the evaluation to a UI snapshot hash for audit trail
     */
    evaluateWithIntegrity(request: EvaluateRequest, snapshotHash: string): Promise<EvaluateResponse & {
        integrity_verified: boolean;
    }>;
    /**
     * Get dashboard statistics
     */
    getDashboardStats(): Promise<DashboardStats$1>;
    /**
     * Get dashboard alerts
     */
    getDashboardAlerts(options?: {
        limit?: number;
        severity?: string;
    }): Promise<DashboardAlert[]>;
    /**
     * Get timeline data for charts
     */
    getTimelineData(options?: {
        hours?: number;
        interval?: string;
    }): Promise<TimelineDataPoint[]>;
    /**
     * Get Sankey flow data for value visualization
     */
    getSankeyFlow(options?: {
        limit?: number;
    }): Promise<{
        nodes: Array<{
            id: string;
            name: string;
            category: string;
        }>;
        links: Array<{
            source: string;
            target: string;
            value: number;
        }>;
    }>;
    /**
     * Get entity profile by address
     */
    getProfile(address: string): Promise<EntityProfile>;
    /**
     * Update entity profile
     */
    updateProfile(address: string, updates: Partial<EntityProfile>): Promise<EntityProfile>;
    /**
     * Set entity type for an address
     */
    setEntityType(address: string, entityType: EntityType): Promise<EntityProfile>;
    /**
     * List all profiles
     */
    listProfiles(options?: {
        limit?: number;
        offset?: number;
    }): Promise<EntityProfile[]>;
    /**
     * Get decision history
     */
    listDecisions(options?: DecisionListOptions): Promise<DecisionRecord[]>;
    /**
     * Get available entity types
     */
    getEntityTypes(): Promise<Array<{
        type: EntityType;
        description: string;
    }>>;
    /**
     * Check service health
     */
    health(): Promise<{
        status: string;
        service: string;
        connected_services: Record<string, string>;
        profiles_loaded: number;
    }>;
}

/**
 * Explainability Service - ML Decision Explanations
 *
 * Provides human-readable explanations for risk scores and decisions
 * using SHAP-based analysis and rule-based reasoning.
 */

type ImpactLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NEUTRAL';
type RecommendedAction = 'BLOCK' | 'ESCROW' | 'REVIEW' | 'ALLOW';
interface ExplanationFactor {
    feature: string;
    reason: string;
    detail: string;
    impact: ImpactLevel;
    contribution: number;
}
interface TypologyMatch {
    typology_id: string;
    typology_name: string;
    confidence: number;
    indicators: string[];
}
interface RiskExplanation {
    risk_score: number;
    action: RecommendedAction;
    confidence: number;
    summary: string;
    top_reasons: string[];
    factors: ExplanationFactor[];
    typologies_detected: TypologyMatch[];
    degraded_mode?: boolean;
}
interface ExplainRequest {
    risk_score: number;
    features: Record<string, unknown>;
    graph_context?: Record<string, unknown>;
}
interface TransactionExplainRequest {
    transaction_hash: string;
    risk_score: number;
    sender: string;
    receiver: string;
    amount: number;
    features: Record<string, unknown>;
}
interface TransactionExplanation extends RiskExplanation {
    transaction: {
        hash: string;
        sender: string;
        receiver: string;
        amount: number;
    };
}
interface Typology {
    id: string;
    name: string;
    description: string;
    indicators?: string[];
    risk_weight?: number;
}
declare class ExplainabilityService extends BaseService {
    private readonly baseUrl;
    constructor(http: AxiosInstance, events: EventEmitter, baseUrl?: string);
    /**
     * Get explanation for a risk score
     */
    explain(request: ExplainRequest): Promise<RiskExplanation>;
    /**
     * Get explanation for a specific transaction
     */
    explainTransaction(request: TransactionExplainRequest): Promise<TransactionExplanation>;
    /**
     * Get all known fraud typologies
     */
    getTypologies(): Promise<Typology[]>;
    /**
     * Get explanation for an address based on its features
     */
    explainAddress(address: string, features: Record<string, unknown>): Promise<RiskExplanation>;
    /**
     * Get a human-readable summary for a risk level
     */
    static getRiskSummary(riskScore: number): string;
    /**
     * Get recommended action based on risk score
     */
    static getRecommendedAction(riskScore: number): RecommendedAction;
    /**
     * Check service health
     */
    health(): Promise<{
        status: string;
        service: string;
        version: string;
    }>;
}

/**
 * Sanctions Service - OFAC/EU/UN Sanctions Screening
 *
 * Provides comprehensive sanctions screening against multiple lists
 * including OFAC SDN, EU Consolidated, UN Security Council, and
 * HMT (UK Treasury) sanctions lists.
 */

type MatchType = 'address' | 'name' | 'fuzzy_name' | 'alias';
interface SanctionedEntity {
    id: string;
    name: string;
    aliases?: string[];
    source_list: string;
    sanctions_type: string;
    country?: string;
    listed_date?: string;
    addresses?: string[];
    programs?: string[];
}
interface SanctionsMatch {
    match_type: MatchType;
    confidence: number;
    entity?: SanctionedEntity;
    matched_field?: string;
    matched_value?: string;
}
interface SanctionsCheckRequest {
    address?: string;
    name?: string;
    country?: string;
    include_fuzzy?: boolean;
    threshold?: number;
}
interface SanctionsCheckResponse {
    query: SanctionsCheckRequest;
    is_sanctioned: boolean;
    matches: SanctionsMatch[];
    check_timestamp: string;
    lists_checked: string[];
    processing_time_ms: number;
}
interface BatchCheckRequest {
    addresses: string[];
    include_fuzzy?: boolean;
}
interface BatchCheckResult {
    address: string;
    is_sanctioned: boolean;
    matches: SanctionsMatch[];
}
interface BatchCheckResponse {
    results: BatchCheckResult[];
    total_checked: number;
    total_sanctioned: number;
    check_timestamp: string;
}
interface SanctionsStats {
    total_entities: number;
    indexed_names: number;
    indexed_addresses: number;
    indexed_countries: number;
    hardcoded_crypto_addresses: number;
    last_refresh: Record<string, string>;
    load_timestamp: string;
}
interface SanctionsList {
    id: string;
    name: string;
    source: string;
    entity_count: number;
    last_updated: string;
}
declare class SanctionsService extends BaseService {
    private readonly baseUrl;
    constructor(http: AxiosInstance, events: EventEmitter, baseUrl?: string);
    /**
     * Check an address or name against sanctions lists
     */
    check(request: SanctionsCheckRequest): Promise<SanctionsCheckResponse>;
    /**
     * Check multiple addresses in batch
     */
    batchCheck(request: BatchCheckRequest): Promise<BatchCheckResponse>;
    /**
     * Check if an address is on any crypto-specific sanctions list
     * (e.g., Tornado Cash, Lazarus Group addresses)
     */
    checkCryptoAddress(address: string): Promise<SanctionsCheckResponse>;
    /**
     * Check a name with fuzzy matching for PEP/sanctions
     */
    checkName(name: string, threshold?: number): Promise<SanctionsCheckResponse>;
    /**
     * Refresh sanctions lists from sources
     */
    refresh(): Promise<{
        status: string;
        message: string;
    }>;
    /**
     * Get sanctions database statistics
     */
    getStats(): Promise<SanctionsStats>;
    /**
     * Get list of available sanctions lists
     */
    getLists(): Promise<SanctionsList[]>;
    /**
     * Check service health
     */
    health(): Promise<{
        status: string;
        service: string;
        database_stats: SanctionsStats;
    }>;
}

/**
 * Geographic Risk Service - Country and IP Risk Assessment
 *
 * Provides geographic risk scoring based on FATF lists,
 * tax haven status, and country-specific regulations.
 */

type RiskLevel$1 = 'PROHIBITED' | 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'MINIMAL';
type TransactionPolicy = 'BLOCK' | 'REVIEW' | 'ESCROW' | 'ALLOW' | 'ENHANCED_MONITORING';
interface CountryRiskRequest {
    country_code: string;
}
interface CountryRiskResponse {
    country_code: string;
    country_name?: string;
    risk_score: number;
    risk_level: RiskLevel$1;
    risk_factors: string[];
    is_fatf_black_list: boolean;
    is_fatf_grey_list: boolean;
    is_eu_high_risk: boolean;
    is_tax_haven: boolean;
    transaction_policy: TransactionPolicy;
}
interface IPRiskRequest {
    ip_address: string;
}
interface IPRiskResponse {
    ip_address: string;
    country_code: string;
    country_name: string;
    city?: string;
    region?: string;
    is_vpn: boolean;
    is_proxy: boolean;
    is_tor: boolean;
    is_datacenter: boolean;
    risk_score: number;
    risk_level: RiskLevel$1;
    risk_factors: string[];
}
interface TransactionGeoRiskRequest {
    originator_country: string;
    beneficiary_country: string;
    originator_ip?: string;
    beneficiary_ip?: string;
    value_usd?: number;
}
interface TransactionGeoRiskResponse {
    originator_country_risk: CountryRiskResponse;
    beneficiary_country_risk: CountryRiskResponse;
    originator_ip_risk?: IPRiskResponse;
    beneficiary_ip_risk?: IPRiskResponse;
    combined_risk_score: number;
    combined_risk_level: RiskLevel$1;
    transaction_policy: TransactionPolicy;
    requires_enhanced_due_diligence: boolean;
    requires_travel_rule: boolean;
    risk_factors: string[];
}
interface FATFListCountry {
    code: string;
    name: string;
    list_type: 'black' | 'grey';
    added_date?: string;
    reason?: string;
}
interface CountryInfo {
    code: string;
    name: string;
    region: string;
    risk_score: number;
    risk_level: RiskLevel$1;
    fatf_status?: 'black' | 'grey' | 'none';
    eu_high_risk: boolean;
    tax_haven: boolean;
    currency_code?: string;
    regulatory_framework?: string;
}
declare class GeographicRiskService extends BaseService {
    private readonly baseUrl;
    constructor(http: AxiosInstance, events: EventEmitter, baseUrl?: string);
    /**
     * Get risk assessment for a country
     */
    getCountryRisk(countryCode: string): Promise<CountryRiskResponse>;
    /**
     * Get risk assessment for an IP address
     */
    getIPRisk(ipAddress: string): Promise<IPRiskResponse>;
    /**
     * Get comprehensive geographic risk for a transaction
     */
    getTransactionRisk(request: TransactionGeoRiskRequest): Promise<TransactionGeoRiskResponse>;
    /**
     * Get FATF Black List countries
     */
    getFATFBlackList(): Promise<FATFListCountry[]>;
    /**
     * Get FATF Grey List countries
     */
    getFATFGreyList(): Promise<FATFListCountry[]>;
    /**
     * Get EU High Risk Third Countries
     */
    getEUHighRiskList(): Promise<FATFListCountry[]>;
    /**
     * Get Tax Haven jurisdictions
     */
    getTaxHavens(): Promise<FATFListCountry[]>;
    /**
     * Get detailed country information
     */
    getCountryInfo(countryCode: string): Promise<CountryInfo>;
    /**
     * Check if a country is high risk (FATF Black/Grey or EU High Risk)
     */
    isHighRiskCountry(countryCode: string): Promise<boolean>;
    /**
     * Check if transaction involves prohibited jurisdiction
     */
    isProhibitedTransaction(originatorCountry: string, beneficiaryCountry: string): Promise<boolean>;
    /**
     * Check service health
     */
    health(): Promise<{
        status: string;
        service: string;
        lists: {
            fatf_black: number;
            fatf_grey: number;
            eu_high_risk: number;
            tax_havens: number;
        };
    }>;
}

/**
 * Integrity Service - UI Snapshot and Audit Trail
 *
 * Provides UI integrity verification using cryptographic hashes
 * to ensure What-You-See-Is-What-You-Sign (WYSIWYS) compliance.
 */

interface SnapshotData {
    component_id: string;
    component_type: string;
    state: Record<string, unknown>;
    timestamp: string;
    user_id?: string;
    session_id?: string;
}
interface RegisterHashRequest {
    snapshot_hash: string;
    snapshot_data: SnapshotData;
    signature?: string;
}
interface RegisterHashResponse {
    hash_id: string;
    snapshot_hash: string;
    registered_at: string;
    expires_at: string;
}
interface VerifyIntegrityRequest {
    snapshot_hash: string;
    expected_state?: Record<string, unknown>;
}
interface VerifyIntegrityResponse {
    is_valid: boolean;
    snapshot_hash: string;
    registered_at?: string;
    mismatch_fields?: string[];
    reason?: string;
}
interface PaymentSubmission {
    payment_id: string;
    snapshot_hash: string;
    from_address: string;
    to_address: string;
    amount: number;
    asset: string;
    ui_state: Record<string, unknown>;
}
interface PaymentSubmissionResponse {
    submission_id: string;
    payment_id: string;
    integrity_verified: boolean;
    snapshot_hash: string;
    submitted_at: string;
    compliance_decision?: {
        action: string;
        risk_score: number;
        reasons: string[];
    };
}
interface IntegrityViolation {
    id: string;
    violation_type: string;
    expected_hash: string;
    actual_hash: string;
    detected_at: string;
    user_id?: string;
    session_id?: string;
    severity: 'low' | 'medium' | 'high' | 'critical';
    resolved: boolean;
}
interface ViolationListOptions {
    limit?: number;
    offset?: number;
    severity?: string;
    resolved?: boolean;
}
declare class IntegrityService extends BaseService {
    private readonly baseUrl;
    constructor(http: AxiosInstance, events: EventEmitter, baseUrl?: string);
    /**
     * Register a UI snapshot hash for later verification
     */
    registerHash(request: RegisterHashRequest): Promise<RegisterHashResponse>;
    /**
     * Verify the integrity of a UI snapshot
     */
    verifyIntegrity(request: VerifyIntegrityRequest): Promise<VerifyIntegrityResponse>;
    /**
     * Submit a payment with integrity verification
     */
    submitPayment(submission: PaymentSubmission): Promise<PaymentSubmissionResponse>;
    /**
     * Get list of integrity violations
     */
    getViolations(options?: ViolationListOptions): Promise<IntegrityViolation[]>;
    /**
     * Generate a snapshot hash from UI state
     */
    static generateSnapshotHash(state: Record<string, unknown>): Promise<string>;
    /**
     * Create a snapshot data object
     */
    static createSnapshotData(componentId: string, componentType: string, state: Record<string, unknown>, userId?: string, sessionId?: string): SnapshotData;
    /**
     * Check service health
     */
    health(): Promise<{
        status: string;
        service: string;
    }>;
}

/**
 * Governance Service - Multisig and Action Management
 *
 * Provides governance controls for multi-signature approvals,
 * policy changes, and enforcement actions.
 */

type ActionType = 'WALLET_PAUSE' | 'WALLET_UNPAUSE' | 'MANDATORY_ESCROW' | 'RELEASE_ESCROW' | 'POLICY_UPDATE' | 'WHITELIST_ADD' | 'WHITELIST_REMOVE' | 'BLACKLIST_ADD' | 'BLACKLIST_REMOVE' | 'EMERGENCY_STOP';
type ActionStatus = 'PENDING' | 'AWAITING_SIGNATURES' | 'QUORUM_REACHED' | 'EXECUTED' | 'EXPIRED' | 'CANCELLED';
type ActionScope = 'SINGLE_WALLET' | 'WALLET_CLUSTER' | 'GLOBAL';
interface RiskContext {
    summary: string;
    fanOut?: number;
    velocityDeviation?: number;
    priorDisputes?: boolean;
    mlConfidence?: number;
    relatedCaseIds?: string[];
}
interface Signature {
    signerId: string;
    signerRole: string;
    signerAddress: string;
    signature: string;
    signedAt: string;
    acknowledgedSnapshotHash: string;
    hashVerified: boolean;
    mfaMethod?: string;
    mfaVerifiedAt?: string;
}
interface GovernanceAction {
    id: string;
    type: ActionType;
    status: ActionStatus;
    scope: ActionScope;
    targetAddress?: string;
    durationHours?: number;
    expiresAt: string;
    riskContext: RiskContext;
    isReversible: boolean;
    reversalConditions?: string;
    initiatedBy: string;
    initiatedAt: string;
    uiSnapshotHash: string;
    uiSnapshotId: string;
    policyVersion: string;
    requiredSignatures: number;
    signatures: Signature[];
}
interface CreateActionRequest {
    type: ActionType;
    scope: ActionScope;
    targetAddress?: string;
    durationHours?: number;
    riskContext: RiskContext;
    uiSnapshotHash: string;
    policyVersion: string;
}
interface SignActionRequest {
    actionId: string;
    signature: string;
    acknowledgedSnapshotHash: string;
    mfaToken?: string;
}
interface SigningResult {
    success: boolean;
    actionId: string;
    signatureId?: string;
    currentSignatures: number;
    requiredSignatures: number;
    quorumReached: boolean;
    error?: string;
}
interface ExecutionResult {
    success: boolean;
    actionId: string;
    transactionHash?: string;
    executedAt?: string;
    error?: string;
}
interface WYASummary {
    actionType: string;
    scope: string;
    target: string;
    riskSummary: string;
    reversible: boolean;
    signatures: {
        current: number;
        required: number;
    };
}
interface ActionListOptions {
    status?: ActionStatus;
    type?: ActionType;
    limit?: number;
    offset?: number;
}
declare class GovernanceService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Create a new governance action
     */
    createAction(request: CreateActionRequest): Promise<GovernanceAction>;
    /**
     * Get a governance action by ID
     */
    getAction(actionId: string): Promise<GovernanceAction | null>;
    /**
     * List governance actions
     */
    listActions(options?: ActionListOptions): Promise<GovernanceAction[]>;
    /**
     * Get pending actions for a user
     */
    getPendingActions(userId: string): Promise<GovernanceAction[]>;
    /**
     * Sign a governance action
     */
    signAction(request: SignActionRequest): Promise<SigningResult>;
    /**
     * Execute a governance action (after quorum reached)
     */
    executeAction(actionId: string): Promise<ExecutionResult>;
    /**
     * Cancel a governance action
     */
    cancelAction(actionId: string, reason: string): Promise<{
        success: boolean;
    }>;
    /**
     * Get What-You-Approve summary for an action
     */
    getWYASummary(actionId: string): Promise<WYASummary>;
    /**
     * Get audit trail for an action
     */
    getAuditTrail(actionId: string): Promise<Array<{
        event: string;
        timestamp: string;
        userId: string;
        details: Record<string, unknown>;
    }>>;
    /**
     * Check if user can sign an action
     */
    canUserSign(actionId: string, userId: string): Promise<{
        canSign: boolean;
        reason?: string;
    }>;
    /**
     * Calculate quorum progress
     */
    static calculateQuorumProgress(action: GovernanceAction): {
        current: number;
        required: number;
        percentage: number;
    };
    /**
     * Get action type label
     */
    static getActionTypeLabel(type: ActionType): string;
}

/**
 * Dashboard Service - Analytics and Metrics
 *
 * Provides dashboard data for compliance monitoring,
 * including statistics, alerts, and visualizations.
 */

type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';
type AlertType = 'transaction' | 'policy' | 'sanctions' | 'ml' | 'system';
type TimeRange = '1h' | '24h' | '7d' | '30d' | '90d';
interface DashboardStats {
    totalTransactions: number;
    flaggedTransactions: number;
    pendingReviews: number;
    approvedToday: number;
    blockedToday: number;
    complianceScore: number;
    riskScore: number;
    activeAlerts: number;
}
interface Alert {
    id: string;
    type: AlertType;
    severity: AlertSeverity;
    title: string;
    message: string;
    source: string;
    timestamp: string;
    isRead: boolean;
    details?: Record<string, unknown>;
    relatedEntityId?: string;
}
interface RiskDistribution {
    low: number;
    medium: number;
    high: number;
    critical: number;
}
interface ActivityMetric {
    timestamp: string;
    transactions: number;
    flagged: number;
    blocked: number;
}
interface SankeyNode {
    id: string;
    name: string;
    value?: number;
}
interface SankeyLink {
    source: string;
    target: string;
    value: number;
}
interface SankeyData {
    nodes: SankeyNode[];
    links: SankeyLink[];
}
interface TopRiskEntity {
    address: string;
    riskScore: number;
    riskLevel: string;
    flagCount: number;
    lastActivity: string;
}
interface GeographicRiskMap {
    countries: Array<{
        code: string;
        name: string;
        riskLevel: string;
        transactionCount: number;
        flaggedCount: number;
    }>;
}
interface DashboardFilters {
    timeRange?: TimeRange;
    riskLevel?: string;
    transactionType?: string;
}
declare class DashboardService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Get dashboard overview statistics
     */
    getStats(filters?: DashboardFilters): Promise<DashboardStats>;
    /**
     * Get active alerts
     */
    getAlerts(options?: {
        severity?: AlertSeverity;
        type?: AlertType;
        limit?: number;
        unreadOnly?: boolean;
    }): Promise<Alert[]>;
    /**
     * Mark an alert as read
     */
    markAlertRead(alertId: string): Promise<void>;
    /**
     * Dismiss an alert
     */
    dismissAlert(alertId: string): Promise<void>;
    /**
     * Get risk distribution
     */
    getRiskDistribution(filters?: DashboardFilters): Promise<RiskDistribution>;
    /**
     * Get activity metrics over time
     */
    getActivityMetrics(timeRange?: TimeRange): Promise<ActivityMetric[]>;
    /**
     * Get Sankey flow visualization data
     */
    getSankeyFlow(options?: {
        limit?: number;
        minValue?: number;
        riskLevel?: string;
    }): Promise<SankeyData>;
    /**
     * Get top risk entities
     */
    getTopRiskEntities(limit?: number): Promise<TopRiskEntity[]>;
    /**
     * Get geographic risk map data
     */
    getGeographicRiskMap(): Promise<GeographicRiskMap>;
    /**
     * Get real-time metrics
     */
    getRealTimeMetrics(): Promise<{
        transactionsPerSecond: number;
        avgResponseTime: number;
        queueDepth: number;
        activeConnections: number;
    }>;
    /**
     * Export dashboard data
     */
    exportData(format: 'csv' | 'json' | 'pdf', filters?: DashboardFilters): Promise<Blob>;
    /**
     * Subscribe to real-time updates (returns cleanup function)
     */
    subscribeToUpdates(callback: (update: {
        type: string;
        data: unknown;
    }) => void): () => void;
    /**
     * Format alert for display
     */
    static formatAlert(alert: Alert): {
        title: string;
        description: string;
        time: string;
        color: string;
        icon: string;
    };
}

/**
 * AMTTP Client - Main entry point for SDK
 */

interface AMTTPClientConfig {
    /** Base URL for the AMTTP API */
    baseUrl: string;
    /** API key for authentication */
    apiKey?: string;
    /** Request timeout in milliseconds */
    timeout?: number;
    /** Number of retry attempts for failed requests */
    retryAttempts?: number;
    /** MEV protection configuration */
    mevConfig?: MEVConfig;
    /** Enable debug logging */
    debug?: boolean;
}
declare class AMTTPClient {
    private readonly http;
    private readonly config;
    readonly events: EventEmitter;
    readonly risk: RiskService;
    readonly kyc: KYCService;
    readonly transactions: TransactionService;
    readonly policy: PolicyService;
    readonly disputes: DisputeService;
    readonly reputation: ReputationService;
    readonly bulk: BulkService;
    readonly webhooks: WebhookService;
    readonly pep: PEPService;
    readonly edd: EDDService;
    readonly monitoring: MonitoringService;
    readonly labels: LabelService;
    readonly mev: MEVProtection;
    readonly compliance: ComplianceService;
    readonly explainability: ExplainabilityService;
    readonly sanctions: SanctionsService;
    readonly geographic: GeographicRiskService;
    readonly integrity: IntegrityService;
    readonly governance: GovernanceService;
    readonly dashboard: DashboardService;
    constructor(config: AMTTPClientConfig);
    private setupInterceptors;
    private handleError;
    /**
     * Health check for the API
     */
    healthCheck(): Promise<{
        status: string;
        version: string;
    }>;
    /**
     * Get current API configuration
     */
    getConfig(): Readonly<AMTTPClientConfig>;
    /**
     * Update API key
     */
    setApiKey(apiKey: string): void;
}

/**
 * AMTTP Error classes and error codes
 */
declare enum AMTTPErrorCode {
    NETWORK_ERROR = "NETWORK_ERROR",
    TIMEOUT = "TIMEOUT",
    UNAUTHORIZED = "UNAUTHORIZED",
    FORBIDDEN = "FORBIDDEN",
    INVALID_ADDRESS = "INVALID_ADDRESS",
    INVALID_AMOUNT = "INVALID_AMOUNT",
    INVALID_PARAMETERS = "INVALID_PARAMETERS",
    HIGH_RISK_BLOCKED = "HIGH_RISK_BLOCKED",
    SANCTIONED_ADDRESS = "SANCTIONED_ADDRESS",
    POLICY_VIOLATION = "POLICY_VIOLATION",
    KYC_REQUIRED = "KYC_REQUIRED",
    EDD_REQUIRED = "EDD_REQUIRED",
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE",
    TRANSACTION_FAILED = "TRANSACTION_FAILED",
    ESCROW_REQUIRED = "ESCROW_REQUIRED",
    DISPUTE_NOT_FOUND = "DISPUTE_NOT_FOUND",
    EVIDENCE_REJECTED = "EVIDENCE_REJECTED",
    NOT_FOUND = "NOT_FOUND",
    RATE_LIMITED = "RATE_LIMITED",
    SERVER_ERROR = "SERVER_ERROR",
    UNKNOWN = "UNKNOWN"
}
declare class AMTTPError extends Error {
    readonly code: AMTTPErrorCode;
    readonly statusCode?: number;
    readonly details?: Record<string, unknown>;
    constructor(message: string, code?: AMTTPErrorCode, statusCode?: number, details?: Record<string, unknown>);
    /**
     * Create an error from an API response
     */
    static fromResponse(response: {
        status: number;
        data?: {
            message?: string;
            code?: string;
            details?: Record<string, unknown>;
        };
    }): AMTTPError;
    /**
     * Check if error is retryable
     */
    isRetryable(): boolean;
    /**
     * Check if error requires user action
     */
    requiresUserAction(): boolean;
    toJSON(): {
        name: string;
        message: string;
        code: AMTTPErrorCode;
        statusCode: number | undefined;
        details: Record<string, unknown> | undefined;
    };
}

/**
 * AMTTP Client SDK
 *
 * A comprehensive SDK for interacting with the AMTTP (Advanced Money Transfer Transaction Protocol)
 * backend services. Provides regulatory-compliant transaction processing with Stacked Ensemble ML risk scoring.
 *
 * @packageDocumentation
 */
type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
type KYCStatus = 'none' | 'pending' | 'verified' | 'rejected' | 'expired';
type KYCLevel = 'none' | 'basic' | 'standard' | 'enhanced';
type TransactionStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
type PolicyDecision = 'allow' | 'deny' | 'review' | 'escalate';
type DisputeStatus = 'open' | 'in_review' | 'awaiting_evidence' | 'resolved' | 'appealed' | 'closed';
type DisputeRuling = 'claimant_wins' | 'respondent_wins' | 'split' | 'dismissed';
type ReputationTier = 'bronze' | 'silver' | 'gold' | 'platinum' | 'diamond';
interface RiskScore {
    address: string;
    score: number;
    level: RiskLevel;
    timestamp: string;
    expiresAt: string;
}
interface LabelInfo {
    label: string;
    category: string;
    severity: string;
    source: string;
}
interface ReputationScore {
    address: string;
    tier: ReputationTier;
    score: number;
    totalTransactions: number;
}

export { AMTTPClient, type AMTTPClientConfig, AMTTPError, AMTTPErrorCode, type AMTTPEvents, type ActionListOptions, type ActionScope, type ActionStatus, type ActionType, type ActivityMetric, type AddressLabel, type Alert, type AlertSeverity$1 as AlertSeverity, type AlertStatus, type AlertType$1 as AlertType, type Badge, type BatchCheckRequest, type BatchCheckResponse, type BatchCheckResult, type BatchRiskRequest, type BatchRiskResponse, type BulkJobStatus, type BulkScoringRequest, type BulkScoringResult, BulkService, type BulkTransaction, type ComplianceAction, type ComplianceCheck, ComplianceService, type CountryInfo, type CountryRiskRequest, type CountryRiskResponse, type CreateActionRequest, type DashboardAlert, type DashboardFilters, DashboardService, type DashboardStats, type DecisionListOptions, type DecisionRecord, type Dispute, type DisputeCreateRequest, type DisputeListOptions, type DisputeRuling, DisputeService, type DisputeStatus, type EDDCase, type EDDCreateRequest, type EDDDocument, type EDDListOptions, type EDDNote, EDDService, type EDDStatus, type EDDTimelineEvent, type EDDTrigger, type EntityProfile, type EntityType, type EvaluateRequest, type EvaluateResponse, EventEmitter, type Evidence, type ExecutionResult, type ExplainRequest, ExplainabilityService, type ExplanationFactor, type FATFListCountry, type FlashbotsBundle, type GeographicRiskMap, GeographicRiskService, type GovernanceAction, GovernanceService, type IPRiskRequest, type IPRiskResponse, type ImpactLevel, IntegrityService, type IntegrityViolation, type KYCDocument, type KYCLevel, type KYCRequirements, KYCService, type KYCStatus, type KYCSubmission, type KYCVerificationResult, type LabelCategory, type LabelInfo, type LabelSearchResult, LabelService, type LabelSeverity, type LabelStatistics, type LeaderboardEntry, type MEVAnalysis, type MEVConfig, type MEVProtectedTransaction, MEVProtection, type MEVProtectionLevel, type MatchType, type MonitoredAddress, type MonitoringAlert, type MonitoringConfig, type MonitoringRule, MonitoringService, type PEPHistoryEntry, type PEPMatch, type PEPScreeningRequest, type PEPScreeningResult, PEPService, type PaymentSubmission, type PaymentSubmissionResponse, type Policy, type PolicyAction, type PolicyCondition, type PolicyCreateRequest, type PolicyDecision, type PolicyEvaluationRequest, type PolicyEvaluationResult, PolicyService, type RecommendedAction, type RegisterHashRequest, type RegisterHashResponse, type ReputationEvent, type ReputationProfile, type ReputationScore, ReputationService, type ReputationTier, type RiskAssessmentRequest, type RiskAssessmentResponse, type RiskContext, type RiskDistribution, type RiskExplanation, type RiskFactor, type RiskLevel, type RiskScore, RiskService, type RiskThreshold, type RiskTolerance, type RuleCondition, type SanctionedEntity, type SanctionsCheckRequest, type SanctionsCheckResponse, type SanctionsList, type SanctionsMatch, SanctionsService, type SanctionsStats, type SankeyData, type SankeyLink, type SankeyNode, type SignActionRequest, type Signature, type SigningResult, type SnapshotData, type TierRequirements, type TimeRange, type TimelineDataPoint, type TimelineEvent, type TopRiskEntity, type TransactionExplainRequest, type TransactionExplanation, type TransactionGeoRiskRequest, type TransactionGeoRiskResponse, type TransactionHistoryOptions, type TransactionPolicy, type TransactionRecord, type TransactionRequest, type TransactionScoreResult, TransactionService, type TransactionStatus, type TransactionValidation, type Typology, type TypologyMatch, type VerifyIntegrityRequest, type VerifyIntegrityResponse, type ViolationListOptions, type WYASummary, type Webhook, type WebhookCreateRequest, type WebhookDelivery, type WebhookEventType, WebhookService };
