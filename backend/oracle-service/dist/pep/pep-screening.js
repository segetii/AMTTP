/**
 * AMTTP PEP Database Integration
 * Connector for Dow Jones, Refinitiv, and other PEP screening providers
 */
import { Router } from 'express';
import { createHash, randomUUID } from 'crypto';
// ═══════════════════════════════════════════════════════════════════════════
// MOCK PEP DATABASE
// ═══════════════════════════════════════════════════════════════════════════
const MOCK_PEP_ENTRIES = [
    {
        id: 'pep-001',
        provider: 'DOW_JONES',
        name: 'Vladimir Putin',
        aliases: ['V. Putin', 'Владимир Путин'],
        dateOfBirth: '1952-10-07',
        nationality: 'Russian',
        countries: ['RU'],
        category: 'HEAD_OF_STATE',
        position: 'President',
        organization: 'Russian Federation',
        startDate: '2000-05-07',
        isActive: true,
        sanctioned: true,
        adverseMedia: true,
        lawEnforcement: false,
        lastUpdated: new Date(),
    },
    {
        id: 'pep-002',
        provider: 'REFINITIV',
        name: 'Kim Jong Un',
        aliases: ['Kim Jong-un', '김정은'],
        dateOfBirth: '1984-01-08',
        nationality: 'North Korean',
        countries: ['KP'],
        category: 'HEAD_OF_STATE',
        position: 'Supreme Leader',
        organization: 'DPRK',
        startDate: '2011-12-17',
        isActive: true,
        sanctioned: true,
        adverseMedia: true,
        lawEnforcement: false,
        lastUpdated: new Date(),
    },
    {
        id: 'pep-003',
        provider: 'OPEN_SANCTIONS',
        name: 'Bashar al-Assad',
        aliases: ['Bashar Hafez al-Assad'],
        dateOfBirth: '1965-09-11',
        nationality: 'Syrian',
        countries: ['SY'],
        category: 'HEAD_OF_STATE',
        position: 'President',
        organization: 'Syrian Arab Republic',
        startDate: '2000-07-17',
        isActive: true,
        sanctioned: true,
        adverseMedia: true,
        lawEnforcement: false,
        lastUpdated: new Date(),
    },
];
// ═══════════════════════════════════════════════════════════════════════════
// PEP SCREENING SERVICE
// ═══════════════════════════════════════════════════════════════════════════
export class PEPScreeningService {
    cache = new Map();
    cacheTimeoutMs = 24 * 60 * 60 * 1000; // 24 hours
    providers = ['DOW_JONES', 'REFINITIV', 'OPEN_SANCTIONS'];
    // Simulated API credentials (would be in env vars)
    apiKeys = {
        DOW_JONES: process.env.DOW_JONES_API_KEY || null,
        REFINITIV: process.env.REFINITIV_API_KEY || null,
        OPEN_SANCTIONS: 'public', // Open source
        UN_SC: 'public',
        OFAC: 'public',
        EU_CONSOLIDATED: 'public',
    };
    /**
     * Screen a name against PEP databases
     */
    async screenName(params) {
        const cacheKey = this.getCacheKey(params.name, params.dateOfBirth);
        // Check cache
        if (!params.forceRefresh) {
            const cached = this.cache.get(cacheKey);
            if (cached && cached.cacheExpiresAt && cached.cacheExpiresAt > new Date()) {
                return { ...cached, cachedResult: true };
            }
        }
        const startTime = Date.now();
        const matches = [];
        // Query each provider
        for (const provider of this.providers) {
            const providerMatches = await this.queryProvider(provider, params);
            matches.push(...providerMatches);
        }
        // Sort by match score
        matches.sort((a, b) => b.matchScore - a.matchScore);
        // Deduplicate
        const deduped = this.deduplicateMatches(matches);
        const result = {
            id: randomUUID(),
            queryName: params.name,
            queryAddress: params.address,
            timestamp: new Date(),
            matches: deduped,
            highestConfidence: deduped.length > 0 ? deduped[0].confidence : null,
            isPEP: deduped.some(m => m.entry.category !== 'FAMILY_MEMBER' && m.entry.category !== 'CLOSE_ASSOCIATE'),
            isSanctioned: deduped.some(m => m.entry.sanctioned),
            providersQueried: this.providers,
            processingTimeMs: Date.now() - startTime,
            cachedResult: false,
            cacheExpiresAt: new Date(Date.now() + this.cacheTimeoutMs),
        };
        // Cache result
        this.cache.set(cacheKey, result);
        return result;
    }
    /**
     * Batch screening for multiple names
     */
    async screenBatch(names) {
        const startTime = Date.now();
        const results = [];
        for (const item of names) {
            const result = await this.screenName(item);
            results.push(result);
        }
        return {
            results,
            summary: {
                total: names.length,
                pepMatches: results.filter(r => r.isPEP).length,
                sanctionMatches: results.filter(r => r.isSanctioned).length,
                processingTimeMs: Date.now() - startTime,
            },
        };
    }
    /**
     * Get provider status
     */
    getProviderStatus() {
        const status = {};
        for (const provider of Object.keys(this.apiKeys)) {
            const configured = this.apiKeys[provider] !== null;
            status[provider] = {
                configured,
                healthy: configured, // Simplified for demo
            };
        }
        return status;
    }
    /**
     * Clear cache
     */
    clearCache() {
        this.cache.clear();
    }
    /**
     * Get cache statistics
     */
    getCacheStats() {
        const entries = Array.from(this.cache.values());
        const now = new Date();
        return {
            totalEntries: entries.length,
            validEntries: entries.filter(e => e.cacheExpiresAt && e.cacheExpiresAt > now).length,
            expiredEntries: entries.filter(e => !e.cacheExpiresAt || e.cacheExpiresAt <= now).length,
            cacheTimeoutMs: this.cacheTimeoutMs,
        };
    }
    // ─────────────────────────────────────────────────────────────────────────
    // PRIVATE HELPERS
    // ─────────────────────────────────────────────────────────────────────────
    getCacheKey(name, dob) {
        return createHash('sha256')
            .update(`${name.toLowerCase()}:${dob || ''}`)
            .digest('hex');
    }
    async queryProvider(provider, params) {
        // Simulate API call delay
        await new Promise(resolve => setTimeout(resolve, 100 + Math.random() * 200));
        const matches = [];
        const queryNameLower = params.name.toLowerCase();
        // Search mock database
        for (const entry of MOCK_PEP_ENTRIES) {
            if (entry.provider !== provider)
                continue;
            const { score, reasons, confidence } = this.calculateMatch(queryNameLower, entry, params.dateOfBirth, params.nationality);
            if (score >= 50) {
                matches.push({
                    entry,
                    confidence,
                    matchScore: score,
                    matchReasons: reasons,
                });
            }
        }
        return matches;
    }
    calculateMatch(queryName, entry, queryDob, queryNationality) {
        let score = 0;
        const reasons = [];
        // Name matching
        const entryNameLower = entry.name.toLowerCase();
        const aliasesLower = entry.aliases.map(a => a.toLowerCase());
        if (queryName === entryNameLower) {
            score += 80;
            reasons.push('Exact name match');
        }
        else if (entryNameLower.includes(queryName) || queryName.includes(entryNameLower)) {
            score += 60;
            reasons.push('Partial name match');
        }
        else if (aliasesLower.some(a => a === queryName || a.includes(queryName))) {
            score += 70;
            reasons.push('Alias match');
        }
        else if (this.fuzzyMatch(queryName, entryNameLower) > 0.7) {
            score += 50;
            reasons.push('Fuzzy name match');
        }
        // DOB matching
        if (queryDob && entry.dateOfBirth) {
            if (queryDob === entry.dateOfBirth) {
                score += 15;
                reasons.push('Date of birth match');
            }
        }
        // Nationality matching
        if (queryNationality && entry.nationality) {
            if (queryNationality.toLowerCase() === entry.nationality.toLowerCase()) {
                score += 5;
                reasons.push('Nationality match');
            }
        }
        // Determine confidence
        let confidence;
        if (score >= 90) {
            confidence = 'EXACT';
        }
        else if (score >= 75) {
            confidence = 'STRONG';
        }
        else if (score >= 60) {
            confidence = 'POTENTIAL';
        }
        else {
            confidence = 'WEAK';
        }
        return { score: Math.min(100, score), reasons, confidence };
    }
    fuzzyMatch(a, b) {
        // Simple Levenshtein-based similarity
        const len = Math.max(a.length, b.length);
        if (len === 0)
            return 1;
        const distance = this.levenshtein(a, b);
        return (len - distance) / len;
    }
    levenshtein(a, b) {
        const matrix = [];
        for (let i = 0; i <= b.length; i++) {
            matrix[i] = [i];
        }
        for (let j = 0; j <= a.length; j++) {
            matrix[0][j] = j;
        }
        for (let i = 1; i <= b.length; i++) {
            for (let j = 1; j <= a.length; j++) {
                if (b.charAt(i - 1) === a.charAt(j - 1)) {
                    matrix[i][j] = matrix[i - 1][j - 1];
                }
                else {
                    matrix[i][j] = Math.min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1);
                }
            }
        }
        return matrix[b.length][a.length];
    }
    deduplicateMatches(matches) {
        const seen = new Set();
        const deduped = [];
        for (const match of matches) {
            const key = match.entry.id;
            if (!seen.has(key)) {
                seen.add(key);
                deduped.push(match);
            }
        }
        return deduped;
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════
export const pepRouter = Router();
const pepService = new PEPScreeningService();
// GET /pep - API info
pepRouter.get('/', (req, res) => {
    res.json({
        service: 'AMTTP PEP Screening',
        description: 'Politically Exposed Person database integration',
        providers: ['DOW_JONES', 'REFINITIV', 'OPEN_SANCTIONS', 'UN_SC', 'OFAC', 'EU_CONSOLIDATED'],
        categories: [
            'HEAD_OF_STATE', 'GOVERNMENT_MINISTER', 'SENIOR_CIVIL_SERVANT',
            'SENIOR_MILITARY', 'SENIOR_JUDICIARY', 'CENTRAL_BANK',
            'STATE_ENTERPRISE', 'INTERNATIONAL_ORG', 'POLITICAL_PARTY',
            'FAMILY_MEMBER', 'CLOSE_ASSOCIATE',
        ],
        endpoints: {
            'POST /pep/screen': 'Screen a single name',
            'POST /pep/batch': 'Batch screening',
            'GET /pep/providers': 'Get provider status',
            'GET /pep/cache': 'Get cache statistics',
            'POST /pep/cache/clear': 'Clear cache',
        },
    });
});
// POST /pep/screen - Screen single name
pepRouter.post('/screen', async (req, res) => {
    try {
        const result = await pepService.screenName({
            name: req.body.name,
            dateOfBirth: req.body.dateOfBirth,
            nationality: req.body.nationality,
            address: req.body.address,
            forceRefresh: req.body.forceRefresh,
        });
        res.json(result);
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// POST /pep/batch - Batch screening
pepRouter.post('/batch', async (req, res) => {
    try {
        const names = req.body.names;
        if (!names || !Array.isArray(names)) {
            res.status(400).json({ error: 'names array required' });
            return;
        }
        if (names.length > 100) {
            res.status(400).json({ error: 'Maximum 100 names per batch' });
            return;
        }
        const result = await pepService.screenBatch(names);
        res.json(result);
    }
    catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        res.status(400).json({ error: msg });
    }
});
// GET /pep/providers - Provider status
pepRouter.get('/providers', (req, res) => {
    res.json(pepService.getProviderStatus());
});
// GET /pep/cache - Cache stats
pepRouter.get('/cache', (req, res) => {
    res.json(pepService.getCacheStats());
});
// POST /pep/cache/clear - Clear cache
pepRouter.post('/cache/clear', (req, res) => {
    pepService.clearCache();
    res.json({ success: true, message: 'Cache cleared' });
});
export default pepRouter;
