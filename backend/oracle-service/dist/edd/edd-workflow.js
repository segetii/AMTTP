/**
 * AMTTP Enhanced Due Diligence (EDD) Workflow
 * Document upload and tracking for high-risk customers
 */
import { Router } from 'express';
import { createHash, randomUUID } from 'crypto';
// ═══════════════════════════════════════════════════════════════════════════
// EDD SERVICE
// ═══════════════════════════════════════════════════════════════════════════
export class EDDService {
    cases = new Map();
    defaultDueDays = 14;
    // Document requirements by trigger
    documentRequirements = {
        'HIGH_RISK_COUNTRY': ['PASSPORT', 'PROOF_OF_ADDRESS', 'SOURCE_OF_FUNDS'],
        'PEP_MATCH': ['PASSPORT', 'PROOF_OF_ADDRESS', 'SOURCE_OF_FUNDS', 'SOURCE_OF_WEALTH'],
        'HIGH_VALUE_TX': ['SOURCE_OF_FUNDS', 'BANK_STATEMENT'],
        'SANCTIONS_PROXIMITY': ['PASSPORT', 'PROOF_OF_ADDRESS', 'SOURCE_OF_FUNDS', 'REFERENCE_LETTER'],
        'CORPORATE_COMPLEX': ['BUSINESS_REGISTRATION', 'CORPORATE_STRUCTURE', 'BENEFICIAL_OWNERSHIP'],
    };
    /**
     * Create a new EDD case
     */
    createCase(params) {
        const id = `EDD-${Date.now()}-${randomUUID().slice(0, 8)}`;
        const now = new Date();
        // Determine required documents based on trigger
        const requiredDocuments = this.documentRequirements[params.triggerReason] ||
            ['PASSPORT', 'PROOF_OF_ADDRESS', 'SOURCE_OF_FUNDS'];
        const eddCase = {
            id,
            subjectType: params.subjectType,
            subjectId: params.subjectId,
            subjectName: params.subjectName,
            walletAddresses: params.walletAddresses,
            status: 'PENDING',
            priority: params.priority || this.calculatePriority(params.riskScore),
            triggerReason: params.triggerReason,
            triggerEvent: params.triggerEvent,
            riskScore: params.riskScore,
            requiredDocuments,
            documents: [],
            createdAt: now,
            lastUpdatedAt: now,
            dueDate: new Date(now.getTime() + this.defaultDueDays * 24 * 60 * 60 * 1000),
            assignedTo: params.assignedTo,
            reviewHistory: [],
        };
        // Log creation
        eddCase.reviewHistory.push({
            id: randomUUID(),
            action: 'CREATE',
            performedBy: 'SYSTEM',
            performedAt: now,
            notes: `EDD case created: ${params.triggerReason}`,
        });
        this.cases.set(id, eddCase);
        return eddCase;
    }
    /**
     * Request documents from subject
     */
    requestDocuments(caseId, requestedBy, additionalDocs) {
        const eddCase = this.cases.get(caseId);
        if (!eddCase)
            throw new Error('Case not found');
        if (additionalDocs) {
            const newDocs = additionalDocs.filter(d => !eddCase.requiredDocuments.includes(d));
            eddCase.requiredDocuments.push(...newDocs);
        }
        eddCase.status = 'DOCUMENTS_REQUESTED';
        eddCase.lastUpdatedAt = new Date();
        eddCase.reviewHistory.push({
            id: randomUUID(),
            action: 'REQUEST_DOCS',
            performedBy: requestedBy,
            performedAt: new Date(),
            notes: `Requested documents: ${eddCase.requiredDocuments.join(', ')}`,
        });
        this.cases.set(caseId, eddCase);
        return eddCase;
    }
    /**
     * Upload a document
     */
    uploadDocument(params) {
        const eddCase = this.cases.get(params.caseId);
        if (!eddCase)
            throw new Error('Case not found');
        const doc = {
            id: randomUUID(),
            caseId: params.caseId,
            type: params.type,
            filename: params.filename,
            mimeType: params.mimeType,
            sizeBytes: params.sizeBytes,
            hash: createHash('sha256').update(params.content).digest('hex'),
            storageUrl: `s3://amttp-edd/${params.caseId}/${randomUUID()}`, // Simulated
            encryptedAt: true,
            status: 'PENDING',
            uploadedAt: new Date(),
        };
        eddCase.documents.push(doc);
        eddCase.lastUpdatedAt = new Date();
        // Check if all required docs submitted
        const submittedTypes = new Set(eddCase.documents.map(d => d.type));
        const allSubmitted = eddCase.requiredDocuments.every(t => submittedTypes.has(t));
        if (allSubmitted) {
            eddCase.status = 'DOCUMENTS_SUBMITTED';
        }
        eddCase.reviewHistory.push({
            id: randomUUID(),
            action: 'SUBMIT_DOC',
            performedBy: params.uploadedBy,
            performedAt: new Date(),
            notes: `Uploaded: ${params.type} - ${params.filename}`,
        });
        this.cases.set(params.caseId, eddCase);
        return doc;
    }
    /**
     * Review a document
     */
    reviewDocument(params) {
        const eddCase = this.cases.get(params.caseId);
        if (!eddCase)
            throw new Error('Case not found');
        const doc = eddCase.documents.find(d => d.id === params.documentId);
        if (!doc)
            throw new Error('Document not found');
        doc.status = params.status;
        doc.reviewedBy = params.reviewedBy;
        doc.reviewedAt = new Date();
        doc.reviewNotes = params.notes;
        eddCase.lastUpdatedAt = new Date();
        eddCase.status = 'UNDER_REVIEW';
        this.cases.set(params.caseId, eddCase);
        return doc;
    }
    /**
     * Assign case to reviewer
     */
    assignCase(caseId, assignedTo, assignedBy) {
        const eddCase = this.cases.get(caseId);
        if (!eddCase)
            throw new Error('Case not found');
        eddCase.assignedTo = assignedTo;
        eddCase.lastUpdatedAt = new Date();
        eddCase.reviewHistory.push({
            id: randomUUID(),
            action: 'ASSIGN',
            performedBy: assignedBy,
            performedAt: new Date(),
            notes: `Assigned to: ${assignedTo}`,
        });
        this.cases.set(caseId, eddCase);
        return eddCase;
    }
    /**
     * Complete case review
     */
    completeReview(params) {
        const eddCase = this.cases.get(params.caseId);
        if (!eddCase)
            throw new Error('Case not found');
        const now = new Date();
        switch (params.outcome) {
            case 'APPROVE':
                eddCase.status = 'APPROVED';
                eddCase.completedAt = now;
                break;
            case 'REJECT':
                eddCase.status = 'REJECTED';
                eddCase.completedAt = now;
                break;
            case 'ESCALATE':
                eddCase.status = 'ESCALATED';
                eddCase.priority = 'CRITICAL';
                break;
            case 'REQUEST_MORE':
                eddCase.status = 'ADDITIONAL_INFO_REQUIRED';
                break;
        }
        eddCase.outcome = params.outcome;
        eddCase.outcomeNotes = params.notes;
        eddCase.lastUpdatedAt = now;
        eddCase.reviewHistory.push({
            id: randomUUID(),
            action: params.outcome === 'APPROVE' ? 'APPROVE' :
                params.outcome === 'REJECT' ? 'REJECT' :
                    params.outcome === 'ESCALATE' ? 'ESCALATE' : 'REVIEW',
            performedBy: params.reviewedBy,
            performedAt: now,
            notes: params.notes,
        });
        this.cases.set(params.caseId, eddCase);
        return eddCase;
    }
    /**
     * Get case by ID
     */
    getCase(id) {
        return this.cases.get(id);
    }
    /**
     * Get cases by status
     */
    getCasesByStatus(status) {
        return Array.from(this.cases.values()).filter(c => c.status === status);
    }
    /**
     * Get cases by assignee
     */
    getCasesByAssignee(assignee) {
        return Array.from(this.cases.values()).filter(c => c.assignedTo === assignee);
    }
    /**
     * Get overdue cases
     */
    getOverdueCases() {
        const now = new Date();
        return Array.from(this.cases.values())
            .filter(c => c.status !== 'APPROVED' && c.status !== 'REJECTED')
            .filter(c => c.dueDate < now);
    }
    /**
     * Get case statistics
     */
    getStats() {
        const all = Array.from(this.cases.values());
        const now = new Date();
        return {
            total: all.length,
            byStatus: {
                PENDING: all.filter(c => c.status === 'PENDING').length,
                DOCUMENTS_REQUESTED: all.filter(c => c.status === 'DOCUMENTS_REQUESTED').length,
                DOCUMENTS_SUBMITTED: all.filter(c => c.status === 'DOCUMENTS_SUBMITTED').length,
                UNDER_REVIEW: all.filter(c => c.status === 'UNDER_REVIEW').length,
                ADDITIONAL_INFO_REQUIRED: all.filter(c => c.status === 'ADDITIONAL_INFO_REQUIRED').length,
                APPROVED: all.filter(c => c.status === 'APPROVED').length,
                REJECTED: all.filter(c => c.status === 'REJECTED').length,
                ESCALATED: all.filter(c => c.status === 'ESCALATED').length,
            },
            byPriority: {
                LOW: all.filter(c => c.priority === 'LOW').length,
                MEDIUM: all.filter(c => c.priority === 'MEDIUM').length,
                HIGH: all.filter(c => c.priority === 'HIGH').length,
                CRITICAL: all.filter(c => c.priority === 'CRITICAL').length,
            },
            overdue: all.filter(c => c.dueDate < now && !c.completedAt).length,
            avgResolutionDays: this.calculateAvgResolution(all),
        };
    }
    // ─────────────────────────────────────────────────────────────────────────
    // PRIVATE HELPERS
    // ─────────────────────────────────────────────────────────────────────────
    calculatePriority(riskScore) {
        if (riskScore >= 90)
            return 'CRITICAL';
        if (riskScore >= 70)
            return 'HIGH';
        if (riskScore >= 50)
            return 'MEDIUM';
        return 'LOW';
    }
    calculateAvgResolution(cases) {
        const completed = cases.filter(c => c.completedAt);
        if (completed.length === 0)
            return 0;
        const totalDays = completed.reduce((sum, c) => {
            const days = (c.completedAt.getTime() - c.createdAt.getTime()) / (24 * 60 * 60 * 1000);
            return sum + days;
        }, 0);
        return Math.round(totalDays / completed.length * 10) / 10;
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════
export const eddRouter = Router();
const eddService = new EDDService();
// GET /edd - API info
eddRouter.get('/', (req, res) => {
    res.json({
        service: 'AMTTP Enhanced Due Diligence',
        description: 'Document workflow for high-risk customer onboarding',
        documentTypes: [
            'PASSPORT', 'NATIONAL_ID', 'DRIVING_LICENSE', 'PROOF_OF_ADDRESS',
            'BANK_STATEMENT', 'SOURCE_OF_FUNDS', 'SOURCE_OF_WEALTH',
            'BUSINESS_REGISTRATION', 'CORPORATE_STRUCTURE', 'BENEFICIAL_OWNERSHIP',
            'TAX_RETURN', 'REFERENCE_LETTER', 'OTHER',
        ],
        triggers: ['HIGH_RISK_COUNTRY', 'PEP_MATCH', 'HIGH_VALUE_TX', 'SANCTIONS_PROXIMITY', 'CORPORATE_COMPLEX'],
        endpoints: {
            'POST /edd/case': 'Create EDD case',
            'POST /edd/case/:id/request': 'Request documents',
            'POST /edd/case/:id/document': 'Upload document',
            'POST /edd/case/:id/assign': 'Assign case',
            'POST /edd/case/:id/review': 'Complete review',
            'GET /edd/case/:id': 'Get case details',
            'GET /edd/cases': 'List cases',
            'GET /edd/stats': 'Get statistics',
        },
    });
});
// POST /edd/case - Create case
eddRouter.post('/case', (req, res) => {
    try {
        const eddCase = eddService.createCase({
            subjectType: req.body.subjectType || 'INDIVIDUAL',
            subjectId: req.body.subjectId,
            subjectName: req.body.subjectName,
            walletAddresses: req.body.walletAddresses || [],
            triggerReason: req.body.triggerReason,
            triggerEvent: req.body.triggerEvent,
            riskScore: req.body.riskScore || 70,
            priority: req.body.priority,
            assignedTo: req.body.assignedTo,
        });
        res.status(201).json({
            success: true,
            caseId: eddCase.id,
            status: eddCase.status,
            requiredDocuments: eddCase.requiredDocuments,
            dueDate: eddCase.dueDate,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /edd/case/:id/request - Request documents
eddRouter.post('/case/:id/request', (req, res) => {
    try {
        const eddCase = eddService.requestDocuments(req.params.id, req.body.requestedBy || 'system', req.body.additionalDocs);
        res.json({
            success: true,
            status: eddCase.status,
            requiredDocuments: eddCase.requiredDocuments,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /edd/case/:id/document - Upload document
eddRouter.post('/case/:id/document', (req, res) => {
    try {
        const doc = eddService.uploadDocument({
            caseId: req.params.id,
            type: req.body.type,
            filename: req.body.filename,
            mimeType: req.body.mimeType || 'application/pdf',
            sizeBytes: req.body.sizeBytes || 0,
            content: req.body.content || '',
            uploadedBy: req.body.uploadedBy || 'customer',
        });
        res.status(201).json({
            success: true,
            documentId: doc.id,
            hash: doc.hash,
            storageUrl: doc.storageUrl,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /edd/case/:id/document/:docId/review - Review document
eddRouter.post('/case/:id/document/:docId/review', (req, res) => {
    try {
        const doc = eddService.reviewDocument({
            caseId: req.params.id,
            documentId: req.params.docId,
            status: req.body.status,
            reviewedBy: req.body.reviewedBy,
            notes: req.body.notes,
        });
        res.json({ success: true, document: doc });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /edd/case/:id/assign - Assign case
eddRouter.post('/case/:id/assign', (req, res) => {
    try {
        const eddCase = eddService.assignCase(req.params.id, req.body.assignedTo, req.body.assignedBy || 'system');
        res.json({ success: true, assignedTo: eddCase.assignedTo });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /edd/case/:id/review - Complete review
eddRouter.post('/case/:id/review', (req, res) => {
    try {
        const eddCase = eddService.completeReview({
            caseId: req.params.id,
            outcome: req.body.outcome,
            notes: req.body.notes,
            reviewedBy: req.body.reviewedBy,
        });
        res.json({
            success: true,
            status: eddCase.status,
            outcome: eddCase.outcome,
            completedAt: eddCase.completedAt,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /edd/case/:id - Get case
eddRouter.get('/case/:id', (req, res) => {
    const eddCase = eddService.getCase(req.params.id);
    if (!eddCase) {
        res.status(404).json({ error: 'Case not found' });
        return;
    }
    res.json(eddCase);
});
// GET /edd/cases - List cases
eddRouter.get('/cases', (req, res) => {
    let cases;
    if (req.query.status) {
        cases = eddService.getCasesByStatus(req.query.status);
    }
    else if (req.query.assignee) {
        cases = eddService.getCasesByAssignee(req.query.assignee);
    }
    else if (req.query.overdue === 'true') {
        cases = eddService.getOverdueCases();
    }
    else {
        cases = Array.from(eddService.cases.values());
    }
    res.json({ count: cases.length, cases });
});
// GET /edd/stats - Statistics
eddRouter.get('/stats', (req, res) => {
    res.json(eddService.getStats());
});
export default eddRouter;
