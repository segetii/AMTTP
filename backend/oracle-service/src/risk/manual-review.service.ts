// backend/src/risk/manual-review.service.ts
/**
 * Manual Review Queue Service
 * 
 * Handles transactions flagged for human review when risk score > 900.
 * Implements the "Human Override for High-Risk" security requirement.
 * 
 * Features:
 * - Queue management for pending reviews
 * - Reviewer assignment and escalation
 * - Approval/rejection workflow
 * - Audit trail for compliance
 * - SLA monitoring and alerts
 */

import { EventEmitter } from 'events';

// ═══════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════

export interface ManualReviewItem {
    id: string;
    transactionHash?: string;
    buyer: string;
    seller: string;
    amountWei: string;
    riskScore: number;
    riskCategory: string;
    flagReason: string;
    mlExplanation?: string;
    features?: Record<string, any>;
    status: ReviewStatus;
    priority: ReviewPriority;
    assignedTo?: string;
    createdAt: Date;
    updatedAt: Date;
    reviewedAt?: Date;
    reviewedBy?: string;
    decision?: ReviewDecision;
    decisionReason?: string;
    escalationLevel: number;
    slaDeadline: Date;
}

export type ReviewStatus = 'pending' | 'assigned' | 'under_review' | 'completed' | 'escalated' | 'expired';
export type ReviewPriority = 'critical' | 'high' | 'medium' | 'low';
export type ReviewDecision = 'approve' | 'reject' | 'escalate' | 'request_info';

export interface ReviewerInfo {
    id: string;
    name: string;
    email: string;
    role: 'reviewer' | 'senior_reviewer' | 'mlro';
    activeReviews: number;
    maxReviews: number;
}

export interface ReviewDecisionInput {
    reviewId: string;
    decision: ReviewDecision;
    reason: string;
    reviewerId: string;
    additionalNotes?: string;
}

export interface ReviewQueueStats {
    pending: number;
    assigned: number;
    underReview: number;
    completedToday: number;
    averageReviewTimeMs: number;
    slaBreaches: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════

// Risk score threshold for mandatory manual review
export const MANUAL_REVIEW_THRESHOLD = 900;

// SLA times by priority (in minutes)
const SLA_TIMES: Record<ReviewPriority, number> = {
    critical: 15,    // 15 minutes for critical (score >= 950)
    high: 60,        // 1 hour for high (score >= 900)
    medium: 240,     // 4 hours for medium
    low: 1440,       // 24 hours for low
};

// Escalation thresholds (minutes past SLA)
const ESCALATION_THRESHOLDS = [30, 60, 120]; // Escalate at 30, 60, 120 minutes past SLA

// ═══════════════════════════════════════════════════════════════════════════
// In-Memory Store (Replace with DB in production)
// ═══════════════════════════════════════════════════════════════════════════

class ReviewStore {
    private reviews: Map<string, ManualReviewItem> = new Map();
    private reviewers: Map<string, ReviewerInfo> = new Map();
    private auditLog: Array<{ timestamp: Date; action: string; details: any }> = [];
    
    addReview(review: ManualReviewItem): void {
        this.reviews.set(review.id, review);
        this.logAudit('REVIEW_CREATED', { reviewId: review.id, riskScore: review.riskScore });
    }
    
    getReview(id: string): ManualReviewItem | undefined {
        return this.reviews.get(id);
    }
    
    updateReview(id: string, updates: Partial<ManualReviewItem>): ManualReviewItem | undefined {
        const review = this.reviews.get(id);
        if (review) {
            const updated = { ...review, ...updates, updatedAt: new Date() };
            this.reviews.set(id, updated);
            this.logAudit('REVIEW_UPDATED', { reviewId: id, updates });
            return updated;
        }
        return undefined;
    }
    
    getReviewsByStatus(status: ReviewStatus): ManualReviewItem[] {
        return Array.from(this.reviews.values()).filter(r => r.status === status);
    }
    
    getPendingReviews(): ManualReviewItem[] {
        return Array.from(this.reviews.values())
            .filter(r => ['pending', 'assigned', 'under_review'].includes(r.status))
            .sort((a, b) => {
                // Sort by priority, then by creation time
                const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
                if (priorityOrder[a.priority] !== priorityOrder[b.priority]) {
                    return priorityOrder[a.priority] - priorityOrder[b.priority];
                }
                return a.createdAt.getTime() - b.createdAt.getTime();
            });
    }
    
    addReviewer(reviewer: ReviewerInfo): void {
        this.reviewers.set(reviewer.id, reviewer);
    }
    
    getAvailableReviewer(): ReviewerInfo | undefined {
        return Array.from(this.reviewers.values())
            .filter(r => r.activeReviews < r.maxReviews)
            .sort((a, b) => a.activeReviews - b.activeReviews)[0];
    }
    
    logAudit(action: string, details: any): void {
        this.auditLog.push({ timestamp: new Date(), action, details });
        // Keep last 10000 entries
        if (this.auditLog.length > 10000) {
            this.auditLog = this.auditLog.slice(-10000);
        }
    }
    
    getAuditLog(reviewId?: string): Array<{ timestamp: Date; action: string; details: any }> {
        if (reviewId) {
            return this.auditLog.filter(l => l.details?.reviewId === reviewId);
        }
        return this.auditLog.slice(-100);
    }
    
    getStats(): ReviewQueueStats {
        const now = new Date();
        const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        
        const reviews = Array.from(this.reviews.values());
        const completedToday = reviews.filter(
            r => r.status === 'completed' && r.reviewedAt && r.reviewedAt >= todayStart
        );
        
        const avgTime = completedToday.length > 0
            ? completedToday.reduce((sum, r) => 
                sum + (r.reviewedAt!.getTime() - r.createdAt.getTime()), 0) / completedToday.length
            : 0;
        
        const slaBreaches = reviews.filter(
            r => ['pending', 'assigned', 'under_review'].includes(r.status) && now > r.slaDeadline
        ).length;
        
        return {
            pending: reviews.filter(r => r.status === 'pending').length,
            assigned: reviews.filter(r => r.status === 'assigned').length,
            underReview: reviews.filter(r => r.status === 'under_review').length,
            completedToday: completedToday.length,
            averageReviewTimeMs: avgTime,
            slaBreaches,
        };
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Manual Review Service
// ═══════════════════════════════════════════════════════════════════════════

export class ManualReviewService extends EventEmitter {
    private store: ReviewStore;
    private slaCheckInterval?: NodeJS.Timeout;
    
    constructor() {
        super();
        this.store = new ReviewStore();
        this.startSLAMonitoring();
        this.initializeDefaultReviewers();
    }
    
    /**
     * Check if a transaction requires manual review
     */
    requiresManualReview(riskScore: number): boolean {
        return riskScore >= MANUAL_REVIEW_THRESHOLD;
    }
    
    /**
     * Submit a transaction for manual review
     */
    async submitForReview(params: {
        transactionHash?: string;
        buyer: string;
        seller: string;
        amountWei: string;
        riskScore: number;
        riskCategory: string;
        flagReason: string;
        mlExplanation?: string;
        features?: Record<string, any>;
    }): Promise<ManualReviewItem> {
        const id = `MR-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const priority = this.determinePriority(params.riskScore);
        const slaMinutes = SLA_TIMES[priority];
        
        const review: ManualReviewItem = {
            id,
            ...params,
            status: 'pending',
            priority,
            createdAt: new Date(),
            updatedAt: new Date(),
            escalationLevel: 0,
            slaDeadline: new Date(Date.now() + slaMinutes * 60 * 1000),
        };
        
        this.store.addReview(review);
        
        // Auto-assign to available reviewer
        await this.tryAutoAssign(review);
        
        // Emit event for notifications
        this.emit('review:created', review);
        
        // For critical priority, also trigger immediate alert
        if (priority === 'critical') {
            this.emit('alert:critical', review);
        }
        
        return this.store.getReview(id)!;
    }
    
    /**
     * Get a review by ID
     */
    getReview(id: string): ManualReviewItem | undefined {
        return this.store.getReview(id);
    }
    
    /**
     * Get all pending reviews
     */
    getPendingReviews(): ManualReviewItem[] {
        return this.store.getPendingReviews();
    }
    
    /**
     * Assign a review to a reviewer
     */
    async assignReview(reviewId: string, reviewerId: string): Promise<ManualReviewItem | undefined> {
        const review = this.store.getReview(reviewId);
        if (!review || review.status === 'completed') {
            return undefined;
        }
        
        const updated = this.store.updateReview(reviewId, {
            status: 'assigned',
            assignedTo: reviewerId,
        });
        
        if (updated) {
            this.emit('review:assigned', updated);
        }
        
        return updated;
    }
    
    /**
     * Start reviewing (marks as under review)
     */
    async startReview(reviewId: string, reviewerId: string): Promise<ManualReviewItem | undefined> {
        const review = this.store.getReview(reviewId);
        if (!review || review.status === 'completed') {
            return undefined;
        }
        
        return this.store.updateReview(reviewId, {
            status: 'under_review',
            assignedTo: reviewerId,
        });
    }
    
    /**
     * Submit a review decision
     */
    async submitDecision(input: ReviewDecisionInput): Promise<ManualReviewItem | undefined> {
        const review = this.store.getReview(input.reviewId);
        if (!review) {
            throw new Error('Review not found');
        }
        
        if (review.status === 'completed') {
            throw new Error('Review already completed');
        }
        
        if (input.decision === 'escalate') {
            return this.escalateReview(input.reviewId, input.reason);
        }
        
        const updated = this.store.updateReview(input.reviewId, {
            status: 'completed',
            decision: input.decision,
            decisionReason: input.reason,
            reviewedAt: new Date(),
            reviewedBy: input.reviewerId,
        });
        
        if (updated) {
            this.emit('review:completed', updated);
            
            // Log for compliance
            this.store.logAudit('REVIEW_DECISION', {
                reviewId: input.reviewId,
                decision: input.decision,
                reason: input.reason,
                reviewerId: input.reviewerId,
                riskScore: updated.riskScore,
            });
        }
        
        return updated;
    }
    
    /**
     * Escalate a review to senior reviewer
     */
    async escalateReview(reviewId: string, reason: string): Promise<ManualReviewItem | undefined> {
        const review = this.store.getReview(reviewId);
        if (!review) {
            return undefined;
        }
        
        const newLevel = review.escalationLevel + 1;
        const escalationRoles = ['reviewer', 'senior_reviewer', 'mlro'];
        
        const updated = this.store.updateReview(reviewId, {
            status: 'escalated',
            escalationLevel: newLevel,
            assignedTo: undefined, // Clear assignment for re-assignment
        });
        
        if (updated) {
            this.emit('review:escalated', {
                review: updated,
                reason,
                targetRole: escalationRoles[Math.min(newLevel, escalationRoles.length - 1)],
            });
        }
        
        return updated;
    }
    
    /**
     * Get queue statistics
     */
    getStats(): ReviewQueueStats {
        return this.store.getStats();
    }
    
    /**
     * Get audit log for a review
     */
    getAuditLog(reviewId?: string): Array<{ timestamp: Date; action: string; details: any }> {
        return this.store.getAuditLog(reviewId);
    }
    
    /**
     * Add a reviewer to the system
     */
    addReviewer(reviewer: ReviewerInfo): void {
        this.store.addReviewer(reviewer);
    }
    
    // ═══ Private Methods ═══
    
    private determinePriority(riskScore: number): ReviewPriority {
        if (riskScore >= 950) return 'critical';
        if (riskScore >= 900) return 'high';
        if (riskScore >= 800) return 'medium';
        return 'low';
    }
    
    private async tryAutoAssign(review: ManualReviewItem): Promise<void> {
        const reviewer = this.store.getAvailableReviewer();
        if (reviewer) {
            await this.assignReview(review.id, reviewer.id);
        }
    }
    
    private startSLAMonitoring(): void {
        // Check SLAs every minute
        this.slaCheckInterval = setInterval(() => {
            this.checkSLAs();
        }, 60 * 1000);
    }
    
    private checkSLAs(): void {
        const now = new Date();
        const pending = this.store.getPendingReviews();
        
        for (const review of pending) {
            if (review.status === 'completed') continue;
            
            const msOverdue = now.getTime() - review.slaDeadline.getTime();
            
            if (msOverdue > 0) {
                const minutesOverdue = msOverdue / (60 * 1000);
                
                // Check escalation thresholds
                for (let i = ESCALATION_THRESHOLDS.length - 1; i >= 0; i--) {
                    if (minutesOverdue >= ESCALATION_THRESHOLDS[i] && review.escalationLevel <= i) {
                        this.escalateReview(review.id, `SLA breach: ${Math.floor(minutesOverdue)} minutes overdue`);
                        break;
                    }
                }
                
                this.emit('sla:breach', { review, minutesOverdue });
            }
        }
    }
    
    private initializeDefaultReviewers(): void {
        // Add default reviewers (in production, load from DB)
        this.store.addReviewer({
            id: 'reviewer-1',
            name: 'Default Reviewer',
            email: 'reviewer@amttp.io',
            role: 'reviewer',
            activeReviews: 0,
            maxReviews: 10,
        });
        
        this.store.addReviewer({
            id: 'senior-1',
            name: 'Senior Reviewer',
            email: 'senior@amttp.io',
            role: 'senior_reviewer',
            activeReviews: 0,
            maxReviews: 5,
        });
        
        this.store.addReviewer({
            id: 'mlro-1',
            name: 'MLRO',
            email: 'mlro@amttp.io',
            role: 'mlro',
            activeReviews: 0,
            maxReviews: 3,
        });
    }
    
    /**
     * Cleanup on shutdown
     */
    shutdown(): void {
        if (this.slaCheckInterval) {
            clearInterval(this.slaCheckInterval);
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Singleton Instance
// ═══════════════════════════════════════════════════════════════════════════

let instance: ManualReviewService | null = null;

export function getManualReviewService(): ManualReviewService {
    if (!instance) {
        instance = new ManualReviewService();
    }
    return instance;
}

// ═══════════════════════════════════════════════════════════════════════════
// Integration Helper
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Middleware to check and queue high-risk transactions
 * Use this in the risk scoring flow
 */
export async function checkAndQueueForReview(
    riskScore: number,
    transactionData: {
        transactionHash?: string;
        buyer: string;
        seller: string;
        amountWei: string;
        riskCategory: string;
        mlExplanation?: string;
        features?: Record<string, any>;
    }
): Promise<{ requiresReview: boolean; reviewId?: string }> {
    const service = getManualReviewService();
    
    if (service.requiresManualReview(riskScore)) {
        const review = await service.submitForReview({
            ...transactionData,
            riskScore,
            flagReason: `Risk score ${riskScore} exceeds threshold ${MANUAL_REVIEW_THRESHOLD}`,
        });
        
        return {
            requiresReview: true,
            reviewId: review.id,
        };
    }
    
    return { requiresReview: false };
}
