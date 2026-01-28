/**
 * AMTTP Ongoing Monitoring Service
 * Continuous PEP/sanctions re-screening and transaction monitoring
 */
import { Router } from 'express';
import { randomUUID } from 'crypto';
import { EventEmitter } from 'events';
// ═══════════════════════════════════════════════════════════════════════════
// MONITORING SERVICE
// ═══════════════════════════════════════════════════════════════════════════
export class OngoingMonitoringService extends EventEmitter {
    entities = new Map();
    alerts = new Map();
    runs = [];
    defaultRescreenDays = 30;
    isRunning = false;
    intervalId;
    constructor() {
        super();
        this.setMaxListeners(50);
    }
    /**
     * Add entity to monitoring
     */
    addEntity(params) {
        const id = randomUUID();
        const now = new Date();
        const entity = {
            id,
            type: params.type,
            name: params.name,
            walletAddresses: params.walletAddresses,
            monitoringTypes: params.monitoringTypes || ['SANCTIONS_RESCREENING', 'PEP_RESCREENING'],
            rescreenFrequencyDays: params.rescreenFrequencyDays || this.defaultRescreenDays,
            active: true,
            nextScreeningDue: new Date(now.getTime() + (params.rescreenFrequencyDays || this.defaultRescreenDays) * 24 * 60 * 60 * 1000),
            currentRiskScore: params.initialRiskScore || 30,
            previousRiskScore: params.initialRiskScore || 30,
            riskTrend: 'STABLE',
            createdAt: now,
            updatedAt: now,
        };
        this.entities.set(id, entity);
        return entity;
    }
    /**
     * Remove entity from monitoring
     */
    removeEntity(id) {
        return this.entities.delete(id);
    }
    /**
     * Update entity monitoring config
     */
    updateEntity(id, updates) {
        const entity = this.entities.get(id);
        if (!entity)
            throw new Error('Entity not found');
        const allowed = ['monitoringTypes', 'rescreenFrequencyDays', 'active'];
        for (const key of allowed) {
            if (key in updates) {
                entity[key] = updates[key];
            }
        }
        entity.updatedAt = new Date();
        this.entities.set(id, entity);
        return entity;
    }
    /**
     * Get entity by ID
     */
    getEntity(id) {
        return this.entities.get(id);
    }
    /**
     * List all monitored entities
     */
    listEntities(activeOnly = true) {
        let entities = Array.from(this.entities.values());
        if (activeOnly) {
            entities = entities.filter(e => e.active);
        }
        return entities;
    }
    /**
     * Get entities due for rescreening
     */
    getEntitiesDueForScreening() {
        const now = new Date();
        return Array.from(this.entities.values())
            .filter(e => e.active)
            .filter(e => e.nextScreeningDue <= now);
    }
    /**
     * Run screening for a single entity
     */
    async screenEntity(entityId) {
        const entity = this.entities.get(entityId);
        if (!entity)
            throw new Error('Entity not found');
        const alerts = [];
        const now = new Date();
        // Simulate screening checks
        for (const monitorType of entity.monitoringTypes) {
            const result = await this.performCheck(entity, monitorType);
            if (result.alertNeeded) {
                const alert = this.createAlert({
                    entityId: entity.id,
                    entityName: entity.name,
                    type: monitorType,
                    severity: result.severity,
                    title: result.title,
                    description: result.description,
                    details: result.details,
                });
                alerts.push(alert);
            }
        }
        // Update entity
        entity.previousRiskScore = entity.currentRiskScore;
        entity.currentRiskScore = this.calculateNewRiskScore(entity, alerts);
        entity.riskTrend = this.calculateTrend(entity);
        entity.lastScreenedAt = now;
        entity.nextScreeningDue = new Date(now.getTime() + entity.rescreenFrequencyDays * 24 * 60 * 60 * 1000);
        entity.updatedAt = now;
        this.entities.set(entityId, entity);
        return alerts;
    }
    /**
     * Run batch screening
     */
    async runBatchScreening(type) {
        const run = {
            id: randomUUID(),
            type: type || 'SANCTIONS_RESCREENING',
            startedAt: new Date(),
            entitiesChecked: 0,
            alertsGenerated: 0,
            errors: 0,
            status: 'RUNNING',
        };
        this.runs.push(run);
        try {
            const duEntities = this.getEntitiesDueForScreening();
            for (const entity of duEntities) {
                try {
                    const alerts = await this.screenEntity(entity.id);
                    run.entitiesChecked++;
                    run.alertsGenerated += alerts.length;
                }
                catch (err) {
                    run.errors++;
                }
            }
            run.status = 'COMPLETED';
        }
        catch (err) {
            run.status = 'FAILED';
            run.errorMessage = err instanceof Error ? err.message : String(err);
        }
        run.completedAt = new Date();
        return run;
    }
    /**
     * Create alert manually
     */
    createAlert(params) {
        const alert = {
            id: randomUUID(),
            entityId: params.entityId,
            entityName: params.entityName,
            type: params.type,
            severity: params.severity,
            status: 'NEW',
            title: params.title,
            description: params.description,
            details: params.details || {},
            createdAt: new Date(),
        };
        this.alerts.set(alert.id, alert);
        this.emit('alert', alert);
        return alert;
    }
    /**
     * Acknowledge alert
     */
    acknowledgeAlert(alertId, acknowledgedBy) {
        const alert = this.alerts.get(alertId);
        if (!alert)
            throw new Error('Alert not found');
        alert.status = 'ACKNOWLEDGED';
        alert.acknowledgedAt = new Date();
        alert.assignedTo = acknowledgedBy;
        this.alerts.set(alertId, alert);
        return alert;
    }
    /**
     * Resolve alert
     */
    resolveAlert(params) {
        const alert = this.alerts.get(params.alertId);
        if (!alert)
            throw new Error('Alert not found');
        alert.status = params.resolution;
        alert.resolvedAt = new Date();
        alert.resolutionNotes = params.notes;
        this.alerts.set(params.alertId, alert);
        return alert;
    }
    /**
     * Get alert by ID
     */
    getAlert(id) {
        return this.alerts.get(id);
    }
    /**
     * List alerts
     */
    listAlerts(filters) {
        let alerts = Array.from(this.alerts.values());
        if (filters?.entityId) {
            alerts = alerts.filter(a => a.entityId === filters.entityId);
        }
        if (filters?.status) {
            alerts = alerts.filter(a => a.status === filters.status);
        }
        if (filters?.severity) {
            alerts = alerts.filter(a => a.severity === filters.severity);
        }
        if (filters?.type) {
            alerts = alerts.filter(a => a.type === filters.type);
        }
        return alerts.sort((a, b) => b.createdAt.getTime() - a.createdAt.getTime());
    }
    /**
     * Get open alerts count
     */
    getOpenAlertsCount() {
        const openAlerts = Array.from(this.alerts.values())
            .filter(a => a.status === 'NEW' || a.status === 'ACKNOWLEDGED' || a.status === 'INVESTIGATING');
        return {
            LOW: openAlerts.filter(a => a.severity === 'LOW').length,
            MEDIUM: openAlerts.filter(a => a.severity === 'MEDIUM').length,
            HIGH: openAlerts.filter(a => a.severity === 'HIGH').length,
            CRITICAL: openAlerts.filter(a => a.severity === 'CRITICAL').length,
        };
    }
    /**
     * Start automated monitoring
     */
    startAutomatedMonitoring(intervalMinutes = 60) {
        if (this.isRunning)
            return;
        this.isRunning = true;
        this.intervalId = setInterval(async () => {
            await this.runBatchScreening();
        }, intervalMinutes * 60 * 1000);
        // Run immediately
        this.runBatchScreening();
    }
    /**
     * Stop automated monitoring
     */
    stopAutomatedMonitoring() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = undefined;
        }
        this.isRunning = false;
    }
    /**
     * Get monitoring status
     */
    getStatus() {
        return {
            isRunning: this.isRunning,
            totalEntities: this.entities.size,
            activeEntities: Array.from(this.entities.values()).filter(e => e.active).length,
            entitiesDueForScreening: this.getEntitiesDueForScreening().length,
            openAlerts: this.getOpenAlertsCount(),
            recentRuns: this.runs.slice(-10),
        };
    }
    /**
     * Get statistics
     */
    getStats() {
        const entities = Array.from(this.entities.values());
        const alerts = Array.from(this.alerts.values());
        return {
            entities: {
                total: entities.length,
                active: entities.filter(e => e.active).length,
                byType: {
                    INDIVIDUAL: entities.filter(e => e.type === 'INDIVIDUAL').length,
                    CORPORATE: entities.filter(e => e.type === 'CORPORATE').length,
                },
                avgRiskScore: entities.reduce((s, e) => s + e.currentRiskScore, 0) / entities.length || 0,
            },
            alerts: {
                total: alerts.length,
                byStatus: {
                    NEW: alerts.filter(a => a.status === 'NEW').length,
                    ACKNOWLEDGED: alerts.filter(a => a.status === 'ACKNOWLEDGED').length,
                    INVESTIGATING: alerts.filter(a => a.status === 'INVESTIGATING').length,
                    RESOLVED: alerts.filter(a => a.status === 'RESOLVED').length,
                    FALSE_POSITIVE: alerts.filter(a => a.status === 'FALSE_POSITIVE').length,
                },
                bySeverity: this.getOpenAlertsCount(),
            },
            runs: {
                total: this.runs.length,
                completed: this.runs.filter(r => r.status === 'COMPLETED').length,
                failed: this.runs.filter(r => r.status === 'FAILED').length,
            },
        };
    }
    // ─────────────────────────────────────────────────────────────────────────
    // PRIVATE HELPERS
    // ─────────────────────────────────────────────────────────────────────────
    async performCheck(entity, type) {
        // Simulate check delay
        await new Promise(r => setTimeout(r, 50 + Math.random() * 100));
        // Simulate random findings (5% chance)
        const hasIssue = Math.random() < 0.05;
        if (!hasIssue) {
            return {
                alertNeeded: false,
                severity: 'LOW',
                title: '',
                description: '',
                details: {},
            };
        }
        switch (type) {
            case 'SANCTIONS_RESCREENING':
                return {
                    alertNeeded: true,
                    severity: 'CRITICAL',
                    title: `Potential sanctions match for ${entity.name}`,
                    description: 'New sanctions list update may affect this entity',
                    details: { matchType: 'NAME_SIMILARITY', confidence: 0.85 },
                };
            case 'PEP_RESCREENING':
                return {
                    alertNeeded: true,
                    severity: 'HIGH',
                    title: `PEP status change for ${entity.name}`,
                    description: 'Entity may have new political exposure',
                    details: { newPosition: 'Government Advisor' },
                };
            case 'TRANSACTION_VELOCITY':
                return {
                    alertNeeded: true,
                    severity: 'MEDIUM',
                    title: `Unusual transaction velocity for ${entity.name}`,
                    description: 'Transaction frequency exceeds normal patterns',
                    details: { txCount: 45, period: '24h', baseline: 10 },
                };
            default:
                return {
                    alertNeeded: true,
                    severity: 'LOW',
                    title: `Monitoring alert for ${entity.name}`,
                    description: `Check type: ${type}`,
                    details: {},
                };
        }
    }
    calculateNewRiskScore(entity, newAlerts) {
        let score = entity.currentRiskScore;
        for (const alert of newAlerts) {
            switch (alert.severity) {
                case 'CRITICAL':
                    score += 30;
                    break;
                case 'HIGH':
                    score += 20;
                    break;
                case 'MEDIUM':
                    score += 10;
                    break;
                case 'LOW':
                    score += 5;
                    break;
            }
        }
        // If no alerts, slight decay
        if (newAlerts.length === 0) {
            score = Math.max(10, score - 5);
        }
        return Math.min(100, score);
    }
    calculateTrend(entity) {
        const diff = entity.currentRiskScore - entity.previousRiskScore;
        if (diff > 5)
            return 'INCREASING';
        if (diff < -5)
            return 'DECREASING';
        return 'STABLE';
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════
export const monitoringRouter = Router();
const monitoringService = new OngoingMonitoringService();
// GET /monitoring - API info
monitoringRouter.get('/', (req, res) => {
    res.json({
        service: 'AMTTP Ongoing Monitoring',
        description: 'Continuous PEP/sanctions re-screening and transaction monitoring',
        monitoringTypes: [
            'SANCTIONS_RESCREENING', 'PEP_RESCREENING', 'TRANSACTION_VELOCITY',
            'UNUSUAL_PATTERN', 'HIGH_RISK_COUNTRY', 'DORMANT_ACCOUNT', 'THRESHOLD_BREACH',
        ],
        endpoints: {
            'POST /monitoring/entity': 'Add entity to monitoring',
            'GET /monitoring/entity/:id': 'Get entity details',
            'DELETE /monitoring/entity/:id': 'Remove entity',
            'GET /monitoring/entities': 'List entities',
            'POST /monitoring/screen/:id': 'Screen single entity',
            'POST /monitoring/batch': 'Run batch screening',
            'GET /monitoring/alerts': 'List alerts',
            'POST /monitoring/alert/:id/acknowledge': 'Acknowledge alert',
            'POST /monitoring/alert/:id/resolve': 'Resolve alert',
            'POST /monitoring/start': 'Start automated monitoring',
            'POST /monitoring/stop': 'Stop automated monitoring',
            'GET /monitoring/status': 'Get monitoring status',
            'GET /monitoring/stats': 'Get statistics',
        },
    });
});
// POST /monitoring/entity - Add entity
monitoringRouter.post('/entity', (req, res) => {
    try {
        const entity = monitoringService.addEntity({
            type: req.body.type || 'INDIVIDUAL',
            name: req.body.name,
            walletAddresses: req.body.walletAddresses || [],
            monitoringTypes: req.body.monitoringTypes,
            rescreenFrequencyDays: req.body.rescreenFrequencyDays,
            initialRiskScore: req.body.initialRiskScore,
        });
        res.status(201).json({
            success: true,
            entityId: entity.id,
            nextScreeningDue: entity.nextScreeningDue,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /monitoring/entity/:id - Get entity
monitoringRouter.get('/entity/:id', (req, res) => {
    const entity = monitoringService.getEntity(req.params.id);
    if (!entity) {
        res.status(404).json({ error: 'Entity not found' });
        return;
    }
    res.json(entity);
});
// DELETE /monitoring/entity/:id - Remove entity
monitoringRouter.delete('/entity/:id', (req, res) => {
    const deleted = monitoringService.removeEntity(req.params.id);
    if (deleted) {
        res.json({ success: true });
    }
    else {
        res.status(404).json({ error: 'Entity not found' });
    }
});
// GET /monitoring/entities - List entities
monitoringRouter.get('/entities', (req, res) => {
    const activeOnly = req.query.active !== 'false';
    const entities = monitoringService.listEntities(activeOnly);
    res.json({ count: entities.length, entities });
});
// GET /monitoring/entities/due - Get entities due for screening
monitoringRouter.get('/entities/due', (req, res) => {
    const entities = monitoringService.getEntitiesDueForScreening();
    res.json({ count: entities.length, entities });
});
// POST /monitoring/screen/:id - Screen single entity
monitoringRouter.post('/screen/:id', async (req, res) => {
    try {
        const alerts = await monitoringService.screenEntity(req.params.id);
        res.json({
            success: true,
            alertsGenerated: alerts.length,
            alerts,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /monitoring/batch - Run batch screening
monitoringRouter.post('/batch', async (req, res) => {
    try {
        const run = await monitoringService.runBatchScreening(req.body.type);
        res.json({
            success: true,
            run,
        });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /monitoring/alerts - List alerts
monitoringRouter.get('/alerts', (req, res) => {
    const alerts = monitoringService.listAlerts({
        entityId: req.query.entityId,
        status: req.query.status,
        severity: req.query.severity,
        type: req.query.type,
    });
    res.json({ count: alerts.length, alerts });
});
// GET /monitoring/alert/:id - Get alert
monitoringRouter.get('/alert/:id', (req, res) => {
    const alert = monitoringService.getAlert(req.params.id);
    if (!alert) {
        res.status(404).json({ error: 'Alert not found' });
        return;
    }
    res.json(alert);
});
// POST /monitoring/alert/:id/acknowledge - Acknowledge alert
monitoringRouter.post('/alert/:id/acknowledge', (req, res) => {
    try {
        const alert = monitoringService.acknowledgeAlert(req.params.id, req.body.acknowledgedBy || 'system');
        res.json({ success: true, alert });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /monitoring/alert/:id/resolve - Resolve alert
monitoringRouter.post('/alert/:id/resolve', (req, res) => {
    try {
        const alert = monitoringService.resolveAlert({
            alertId: req.params.id,
            resolution: req.body.resolution || 'RESOLVED',
            notes: req.body.notes || '',
            resolvedBy: req.body.resolvedBy || 'system',
        });
        res.json({ success: true, alert });
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /monitoring/start - Start automated monitoring
monitoringRouter.post('/start', (req, res) => {
    const intervalMinutes = req.body.intervalMinutes || 60;
    monitoringService.startAutomatedMonitoring(intervalMinutes);
    res.json({
        success: true,
        message: `Automated monitoring started with ${intervalMinutes} minute interval`,
    });
});
// POST /monitoring/stop - Stop automated monitoring
monitoringRouter.post('/stop', (req, res) => {
    monitoringService.stopAutomatedMonitoring();
    res.json({ success: true, message: 'Automated monitoring stopped' });
});
// GET /monitoring/status - Get status
monitoringRouter.get('/status', (req, res) => {
    res.json(monitoringService.getStatus());
});
// GET /monitoring/stats - Get statistics
monitoringRouter.get('/stats', (req, res) => {
    res.json(monitoringService.getStats());
});
export default monitoringRouter;
