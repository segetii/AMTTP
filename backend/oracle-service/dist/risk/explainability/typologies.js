/**
 * Typology Detection Engine
 *
 * Detects known fraud/AML patterns from features and rules.
 * Each typology includes regulatory guidance and SAR narratives.
 */
import { TypologyType } from './types.js';
import { loadConfig } from './config.js';
// ═══════════════════════════════════════════════════════════════════════════════
// TYPOLOGY MATCHER
// ═══════════════════════════════════════════════════════════════════════════════
export class TypologyMatcher {
    configs;
    constructor(configs) {
        const typologyConfigs = configs ?? loadConfig().typologies;
        this.configs = new Map(typologyConfigs.filter(t => t.enabled).map(t => [t.type, t]));
    }
    /**
     * Match all applicable typologies
     */
    matchAll(features, graphContext, ruleResults) {
        const matches = [];
        // Rule-based typologies
        matches.push(...this.matchFromRules(ruleResults));
        // Feature-based typologies
        matches.push(...this.matchFromFeatures(features, graphContext));
        // Graph-based typologies
        matches.push(...this.matchFromGraph(graphContext));
        // Filter by minimum confidence and sort
        return matches
            .filter(m => {
            const config = this.configs.get(m.typology);
            return config && m.confidence >= config.minConfidence;
        })
            .sort((a, b) => b.confidence - a.confidence);
    }
    // ─── Rule-Based Detection ───────────────────────────────────────────────────
    matchFromRules(ruleResults) {
        const matches = [];
        for (const rule of ruleResults) {
            if (!rule.triggered)
                continue;
            const match = this.ruleToTypology(rule);
            if (match) {
                matches.push(match);
            }
        }
        return matches;
    }
    ruleToTypology(rule) {
        const evidence = rule.evidence ?? {};
        switch (rule.ruleType.toUpperCase()) {
            case 'STRUCTURING':
            case 'SMURFING':
                return this.createMatch(TypologyType.STRUCTURING, rule.confidence ?? 0.8, 'Multiple transactions structured just below reporting thresholds to avoid detection', [
                    `Total volume: ${evidence.totalValueEth ?? '?'} ETH`,
                    `Transaction count: ${evidence.transactionCount ?? '?'}`,
                    'Individual transactions below threshold',
                    rule.description ?? ''
                ].filter(Boolean), evidence);
            case 'LAYERING':
                return this.createMatch(TypologyType.LAYERING, rule.confidence ?? 0.85, 'Complex transaction chain detected, potentially to obscure the origin of funds', [
                    `Chain length: ${evidence.chainLength ?? '?'} hops`,
                    `Value preserved: ${((evidence.valuePreserved ?? 0) * 100).toFixed(0)}%`,
                    `Time window: ${evidence.timeWindowHours ?? '?'} hours`,
                    'Rapid movement through multiple addresses'
                ].filter(Boolean), evidence);
            case 'ROUND_TRIP':
                return this.createMatch(TypologyType.ROUND_TRIP, rule.confidence ?? 0.75, 'Funds returned to original sender through intermediary addresses', [
                    `Round-trip amount: ${evidence.amount ?? '?'} ETH`,
                    `Intermediaries: ${evidence.intermediaryCount ?? '?'}`,
                    'Potential wash trading or self-laundering'
                ].filter(Boolean), evidence);
            case 'FAN_OUT':
            case 'DISTRIBUTION':
                return this.createMatch(TypologyType.FAN_OUT, rule.confidence ?? 0.7, 'Funds distributed to many recipients in rapid succession', [
                    `Recipients: ${evidence.recipientCount ?? '?'}`,
                    `Time window: ${evidence.timeWindowMinutes ?? '?'} minutes`,
                    'Potential money mule network distribution'
                ].filter(Boolean), evidence);
            case 'FAN_IN':
            case 'AGGREGATION':
                return this.createMatch(TypologyType.FAN_IN, rule.confidence ?? 0.7, 'Funds aggregated from many sources in rapid succession', [
                    `Sources: ${evidence.sourceCount ?? '?'}`,
                    `Time window: ${evidence.timeWindowMinutes ?? '?'} minutes`,
                    'Potential money mule network collection'
                ].filter(Boolean), evidence);
            case 'VELOCITY_ANOMALY':
            case 'RAPID_MOVEMENT':
                return this.createMatch(TypologyType.RAPID_MOVEMENT, rule.confidence ?? 0.7, 'Unusual transaction velocity detected', [
                    `Transactions in 24h: ${evidence.txCount24h ?? '?'}`,
                    `After dormancy: ${evidence.dormancyDays ?? '?'} days`,
                    rule.description ?? ''
                ].filter(Boolean), evidence);
            default:
                return null;
        }
    }
    // ─── Feature-Based Detection ────────────────────────────────────────────────
    matchFromFeatures(features, graphContext) {
        const matches = [];
        // Dormant Activation
        if (features.dormancyDays && features.dormancyDays >= 90) {
            const confidence = Math.min(0.9, 0.5 + features.dormancyDays / 365);
            matches.push(this.createMatch(TypologyType.DORMANT_ACTIVATION, confidence, 'Account reactivated after extended dormancy period with significant activity', [
                `Account inactive for ${features.dormancyDays} days`,
                'Sudden high-value activity after dormancy',
                'Classic indicator of account takeover or abuse'
            ], { dormancyDays: features.dormancyDays }));
        }
        // High-Risk Geography
        if (features.fatfCountryRisk === 'blacklist' || features.fatfCountryRisk === 'greylist') {
            const confidence = features.fatfCountryRisk === 'blacklist' ? 0.95 : 0.75;
            matches.push(this.createMatch(TypologyType.HIGH_RISK_GEOGRAPHY, confidence, `Transaction involves FATF ${features.fatfCountryRisk}ed jurisdiction`, [
                `Country: ${features.countryCode ?? 'Unknown'}`,
                `FATF status: ${features.fatfCountryRisk}`,
                'Enhanced due diligence required'
            ], {
                country: features.countryCode,
                fatfStatus: features.fatfCountryRisk
            }));
        }
        // PEP Involvement
        if (features.pepMatch) {
            matches.push(this.createMatch(TypologyType.PEP_INVOLVEMENT, 0.85, 'Transaction involves Politically Exposed Person', [
                `PEP category: ${features.pepCategory ?? 'Unknown'}`,
                `Risk level: ${features.pepRiskLevel ?? 'Unknown'}`,
                'Enhanced due diligence and source of wealth required'
            ], {
                pepCategory: features.pepCategory,
                pepRiskLevel: features.pepRiskLevel
            }));
        }
        // Fan-out from velocity
        if (features.uniqueRecipients24h && features.uniqueRecipients24h >= 15) {
            matches.push(this.createMatch(TypologyType.FAN_OUT, Math.min(0.9, 0.5 + features.uniqueRecipients24h / 50), 'Funds distributed to many recipients, potential distribution pattern', [
                `${features.uniqueRecipients24h} unique recipients in 24 hours`,
                'Pattern consistent with money mule distribution'
            ], { uniqueRecipients24h: features.uniqueRecipients24h }));
        }
        return matches;
    }
    // ─── Graph-Based Detection ──────────────────────────────────────────────────
    matchFromGraph(graphContext) {
        const matches = [];
        // Sanctions Proximity
        if (graphContext.hopsToSanctioned !== undefined && graphContext.hopsToSanctioned <= 3) {
            const hops = graphContext.hopsToSanctioned;
            const confidence = hops === 0 ? 1.0 : Math.max(0.4, 0.9 - hops * 0.2);
            matches.push(this.createMatch(TypologyType.SANCTIONS_PROXIMITY, confidence, hops === 0
                ? 'DIRECT SANCTIONS MATCH - Address on consolidated sanctions list'
                : `Transaction chain ${hops} hop(s) from sanctioned entity`, hops === 0
                ? [
                    'Direct match on OFAC/HMT/EU/UN sanctions list',
                    'Transaction MUST be blocked',
                    'File SAR immediately'
                ]
                : [
                    `${hops} hop(s) from sanctioned entity`,
                    'Elevated risk due to sanctions proximity',
                    'Review transaction chain for evasion'
                ], { hops: graphContext.hopsToSanctioned }));
        }
        // Mixer Interaction
        if (graphContext.mixerInteraction ||
            (graphContext.hopsToMixer !== undefined && graphContext.hopsToMixer <= 2)) {
            const hops = graphContext.hopsToMixer ?? 0;
            const confidence = graphContext.mixerInteraction ? 0.95 : Math.max(0.6, 0.85 - hops * 0.15);
            matches.push(this.createMatch(TypologyType.MIXER_INTERACTION, confidence, graphContext.mixerInteraction
                ? 'Direct interaction with known cryptocurrency mixing service'
                : `Transaction chain connects to mixing service (${hops} hops)`, [
                graphContext.mixerInteraction
                    ? 'Direct mixer deposit/withdrawal detected'
                    : `${hops} hop(s) from known mixer`,
                'Mixing services are used to obscure transaction trails',
                'High indicator of illicit funds obfuscation'
            ], {
                mixerInteraction: graphContext.mixerInteraction,
                hopsToMixer: graphContext.hopsToMixer
            }));
        }
        return matches;
    }
    // ─── Helper Methods ─────────────────────────────────────────────────────────
    createMatch(typology, confidence, description, indicators, evidence) {
        const config = this.configs.get(typology);
        return {
            typology,
            confidence: Math.min(1, Math.max(0, confidence)),
            description,
            indicators: indicators.filter(i => i && i !== ''),
            evidence,
            regulatoryGuidance: config?.regulatoryGuidance,
            sarNarrative: config?.sarNarrative
        };
    }
}
// ═══════════════════════════════════════════════════════════════════════════════
// EXPORTED UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════
/**
 * Get typology display name
 */
export function getTypologyDisplayName(typology) {
    const names = {
        [TypologyType.STRUCTURING]: 'Structuring / Smurfing',
        [TypologyType.LAYERING]: 'Layering',
        [TypologyType.ROUND_TRIP]: 'Round-Trip Transaction',
        [TypologyType.SMURFING]: 'Smurfing',
        [TypologyType.FAN_OUT]: 'Fan-Out Distribution',
        [TypologyType.FAN_IN]: 'Fan-In Aggregation',
        [TypologyType.DORMANT_ACTIVATION]: 'Dormant Account Activation',
        [TypologyType.MIXER_INTERACTION]: 'Mixer Interaction',
        [TypologyType.SANCTIONS_PROXIMITY]: 'Sanctions Proximity',
        [TypologyType.HIGH_RISK_GEOGRAPHY]: 'High-Risk Geography',
        [TypologyType.RAPID_MOVEMENT]: 'Rapid Fund Movement',
        [TypologyType.UNUSUAL_TIMING]: 'Unusual Timing Pattern',
        [TypologyType.PEP_INVOLVEMENT]: 'PEP Involvement',
        [TypologyType.SHELL_COMPANY]: 'Shell Company Indicators'
    };
    return names[typology] ?? typology;
}
