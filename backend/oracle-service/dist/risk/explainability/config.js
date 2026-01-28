/**
 * Production Configuration for Explainability System
 *
 * All thresholds are calibrated based on:
 * - FCA regulatory guidance
 * - FATF recommendations
 * - Historical fraud patterns
 * - Expert compliance input
 */
import { ImpactLevel, TypologyType, Severity } from './types.js';
// ═══════════════════════════════════════════════════════════════════════════════
// DEFAULT CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════════
const DEFAULT_ACTION_THRESHOLDS = {
    allow: { max: 0.40 },
    review: { min: 0.40, max: 0.70 },
    escrow: { min: 0.70, max: 0.85 },
    block: { min: 0.85 }
};
const DEFAULT_CACHE_CONFIG = {
    enabled: true,
    ttlSeconds: 300, // 5 minutes
    maxSize: 10000,
    keyPrefix: 'expl:'
};
const DEFAULT_METRICS_CONFIG = {
    enabled: true,
    prefix: 'amttp_explainability',
    labels: ['action', 'typology', 'degraded']
};
const DEFAULT_LOGGING_CONFIG = {
    level: Severity.INFO,
    includeFeatures: false,
    redactPII: true
};
// ═══════════════════════════════════════════════════════════════════════════════
// FEATURE CONFIGURATIONS
// ═══════════════════════════════════════════════════════════════════════════════
const DEFAULT_FEATURE_CONFIGS = [
    // ─── Transaction Amount ─────────────────────────────────────────────────────
    {
        id: 'amountEth',
        name: 'Transaction Amount',
        category: 'TRANSACTION',
        enabled: true,
        regulatoryRef: 'FATF R.10',
        thresholds: {
            [ImpactLevel.CRITICAL]: 5000, // >5000 ETH (~$12.5M)
            [ImpactLevel.HIGH]: 500, // >500 ETH (~$1.25M)
            [ImpactLevel.MEDIUM]: 50 // >50 ETH (~$125k)
        },
        templates: {
            [ImpactLevel.CRITICAL]: 'Extremely large transaction ({value} ETH, ~${usd}) exceeds critical threshold requiring enhanced scrutiny',
            [ImpactLevel.HIGH]: 'Large transaction ({value} ETH, ~${usd}) is {ratio}x larger than sender\'s typical activity',
            [ImpactLevel.MEDIUM]: 'Transaction amount ({value} ETH, ~${usd}) is above typical patterns for this address'
        }
    },
    // ─── Amount vs Historical Average ───────────────────────────────────────────
    {
        id: 'amountVsAverage',
        name: 'Amount Deviation',
        category: 'BEHAVIOR',
        enabled: true,
        regulatoryRef: 'FCA SYSC 6.1.1',
        thresholds: {
            [ImpactLevel.HIGH]: 10, // 10x average
            [ImpactLevel.MEDIUM]: 3 // 3x average
        },
        templates: {
            [ImpactLevel.HIGH]: 'Transaction is {value}x larger than sender\'s 30-day average (${avg}), indicating potential unusual activity',
            [ImpactLevel.MEDIUM]: 'Transaction is {value}x larger than typical pattern for this address'
        }
    },
    // ─── Transaction Velocity (1 hour) ──────────────────────────────────────────
    {
        id: 'txCount1h',
        name: 'Hourly Transaction Velocity',
        category: 'BEHAVIOR',
        enabled: true,
        regulatoryRef: 'FATF R.15',
        thresholds: {
            [ImpactLevel.HIGH]: 10,
            [ImpactLevel.MEDIUM]: 5
        },
        templates: {
            [ImpactLevel.HIGH]: 'Unusually high activity: {value} transactions in the last hour (typical: 1-2)',
            [ImpactLevel.MEDIUM]: 'Elevated activity: {value} transactions in the last hour'
        }
    },
    // ─── Transaction Velocity (24 hours) ────────────────────────────────────────
    {
        id: 'txCount24h',
        name: 'Daily Transaction Velocity',
        category: 'BEHAVIOR',
        enabled: true,
        regulatoryRef: 'FATF R.15',
        thresholds: {
            [ImpactLevel.HIGH]: 50,
            [ImpactLevel.MEDIUM]: 20
        },
        templates: {
            [ImpactLevel.HIGH]: 'Very high 24-hour activity: {value} transactions (typical: <10)',
            [ImpactLevel.MEDIUM]: 'Elevated 24-hour activity: {value} transactions'
        }
    },
    // ─── Account Dormancy ───────────────────────────────────────────────────────
    {
        id: 'dormancyDays',
        name: 'Account Dormancy',
        category: 'BEHAVIOR',
        enabled: true,
        regulatoryRef: 'FATF Guidance on ML/TF',
        thresholds: {
            [ImpactLevel.HIGH]: 180, // 6 months
            [ImpactLevel.MEDIUM]: 90 // 3 months
        },
        templates: {
            [ImpactLevel.HIGH]: 'Account was dormant for {value} days before this high-value activity - classic indicator of account takeover or abuse',
            [ImpactLevel.MEDIUM]: 'Account was inactive for {value} days before this transaction'
        }
    },
    // ─── Unique Recipients ──────────────────────────────────────────────────────
    {
        id: 'uniqueRecipients24h',
        name: 'Recipient Diversity',
        category: 'BEHAVIOR',
        enabled: true,
        regulatoryRef: 'FATF R.10',
        thresholds: {
            [ImpactLevel.HIGH]: 20,
            [ImpactLevel.MEDIUM]: 10
        },
        templates: {
            [ImpactLevel.HIGH]: 'Funds sent to {value} unique recipients in 24 hours - potential fan-out/distribution pattern',
            [ImpactLevel.MEDIUM]: 'Funds sent to {value} unique recipients in 24 hours'
        }
    },
    // ─── Sanctions Proximity ────────────────────────────────────────────────────
    {
        id: 'hopsToSanctioned',
        name: 'Sanctions Proximity',
        category: 'COMPLIANCE',
        enabled: true,
        regulatoryRef: 'OFAC Compliance Framework',
        thresholds: {
            [ImpactLevel.CRITICAL]: 0, // Direct match
            [ImpactLevel.HIGH]: 1, // 1 hop
            [ImpactLevel.MEDIUM]: 2 // 2 hops
        },
        templates: {
            [ImpactLevel.CRITICAL]: 'DIRECT SANCTIONS MATCH - Address appears on OFAC/HMT/EU/UN consolidated list. Transaction MUST be blocked.',
            [ImpactLevel.HIGH]: 'Address has direct transaction history with sanctioned entity ({value} hop away)',
            [ImpactLevel.MEDIUM]: 'Transaction chain connects to sanctioned address ({value} hops away)'
        }
    },
    // ─── Mixer Proximity ────────────────────────────────────────────────────────
    {
        id: 'hopsToMixer',
        name: 'Mixer Proximity',
        category: 'NETWORK',
        enabled: true,
        regulatoryRef: 'FinCEN Guidance 2019-G001',
        thresholds: {
            [ImpactLevel.HIGH]: 1,
            [ImpactLevel.MEDIUM]: 2
        },
        templates: {
            [ImpactLevel.HIGH]: 'Address has direct interaction with known mixing service ({value} hop away)',
            [ImpactLevel.MEDIUM]: 'Transaction chain includes mixing service ({value} hops away)'
        }
    },
    // ─── Geographic Risk ────────────────────────────────────────────────────────
    {
        id: 'fatfCountryRisk',
        name: 'Geographic Risk',
        category: 'GEOGRAPHIC',
        enabled: true,
        regulatoryRef: 'FATF Mutual Evaluations',
        thresholds: {
            [ImpactLevel.CRITICAL]: 'blacklist',
            [ImpactLevel.HIGH]: 'greylist',
            [ImpactLevel.MEDIUM]: 'monitored'
        },
        templates: {
            [ImpactLevel.CRITICAL]: 'Transaction involves FATF blacklisted jurisdiction ({country}) - enhanced due diligence required',
            [ImpactLevel.HIGH]: 'Transaction involves FATF grey-listed jurisdiction ({country})',
            [ImpactLevel.MEDIUM]: 'Transaction involves jurisdiction under increased monitoring ({country})'
        }
    },
    // ─── PEP Match ──────────────────────────────────────────────────────────────
    {
        id: 'pepMatch',
        name: 'PEP Exposure',
        category: 'COMPLIANCE',
        enabled: true,
        regulatoryRef: 'FATF R.12',
        thresholds: {},
        templates: {
            [ImpactLevel.HIGH]: 'Transaction involves Politically Exposed Person ({pepCategory})'
        }
    },
    // ─── Network Centrality ─────────────────────────────────────────────────────
    {
        id: 'pagerank',
        name: 'Network Influence',
        category: 'NETWORK',
        enabled: true,
        thresholds: {
            [ImpactLevel.HIGH]: 0.001,
            [ImpactLevel.MEDIUM]: 0.0001
        },
        templates: {
            [ImpactLevel.HIGH]: 'Address has unusually high network influence (PageRank: {value}) - potential hub in transaction network',
            [ImpactLevel.MEDIUM]: 'Address has elevated network centrality'
        }
    },
    // ─── Clustering Coefficient ─────────────────────────────────────────────────
    {
        id: 'clusteringCoefficient',
        name: 'Network Clustering',
        category: 'NETWORK',
        enabled: true,
        thresholds: {
            [ImpactLevel.HIGH]: 0.8,
            [ImpactLevel.MEDIUM]: 0.5
        },
        templates: {
            [ImpactLevel.HIGH]: 'Address is part of a tightly interconnected cluster (coefficient: {value}) - potential coordinated group',
            [ImpactLevel.MEDIUM]: 'Address shows elevated clustering with related addresses'
        }
    },
    // ─── ML Model Scores (internal only) ────────────────────────────────────────
    {
        id: 'xgbProb',
        name: 'XGBoost Risk Score',
        category: 'MODEL',
        enabled: true,
        internalOnly: true,
        thresholds: {
            [ImpactLevel.HIGH]: 0.7,
            [ImpactLevel.MEDIUM]: 0.4
        },
        templates: {
            [ImpactLevel.HIGH]: 'Machine learning model detected high-risk transaction patterns',
            [ImpactLevel.MEDIUM]: 'Machine learning model detected moderate risk signals'
        }
    },
    {
        id: 'vaeReconError',
        name: 'Anomaly Detection Score',
        category: 'MODEL',
        enabled: true,
        internalOnly: true,
        thresholds: {
            [ImpactLevel.HIGH]: 2.0,
            [ImpactLevel.MEDIUM]: 1.5
        },
        templates: {
            [ImpactLevel.HIGH]: 'Transaction pattern is highly unusual compared to normal behavior (anomaly detected)',
            [ImpactLevel.MEDIUM]: 'Transaction shows some characteristics outside normal patterns'
        }
    },
    {
        id: 'sageProb',
        name: 'Graph Neural Network Score',
        category: 'MODEL',
        enabled: true,
        internalOnly: true,
        thresholds: {
            [ImpactLevel.HIGH]: 0.7,
            [ImpactLevel.MEDIUM]: 0.4
        },
        templates: {
            [ImpactLevel.HIGH]: 'Network analysis model indicates high-risk transaction pattern',
            [ImpactLevel.MEDIUM]: 'Network analysis model shows elevated risk signals'
        }
    }
];
// ═══════════════════════════════════════════════════════════════════════════════
// TYPOLOGY CONFIGURATIONS
// ═══════════════════════════════════════════════════════════════════════════════
const DEFAULT_TYPOLOGY_CONFIGS = [
    {
        type: TypologyType.STRUCTURING,
        enabled: true,
        minConfidence: 0.6,
        regulatoryGuidance: 'FATF Guidance on ML/TF Risk Assessment - Structuring/Smurfing',
        sarNarrative: 'Subject conducted multiple transactions just below reporting thresholds, potentially to avoid CTR filing requirements.'
    },
    {
        type: TypologyType.LAYERING,
        enabled: true,
        minConfidence: 0.6,
        regulatoryGuidance: 'FATF Typologies Report - Layering Techniques',
        sarNarrative: 'Subject engaged in complex transaction chain involving multiple intermediary addresses, potentially to obscure the origin of funds.'
    },
    {
        type: TypologyType.ROUND_TRIP,
        enabled: true,
        minConfidence: 0.7,
        regulatoryGuidance: 'FATF ML/TF Indicators',
        sarNarrative: 'Subject conducted round-trip transaction where funds returned to origin address through intermediaries.'
    },
    {
        type: TypologyType.FAN_OUT,
        enabled: true,
        minConfidence: 0.6,
        regulatoryGuidance: 'FATF Typologies - Distribution Patterns',
        sarNarrative: 'Subject distributed funds to multiple recipients in rapid succession, consistent with fund distribution pattern.'
    },
    {
        type: TypologyType.FAN_IN,
        enabled: true,
        minConfidence: 0.6,
        regulatoryGuidance: 'FATF Typologies - Aggregation Patterns',
        sarNarrative: 'Subject received funds from multiple sources in rapid succession, consistent with fund aggregation pattern.'
    },
    {
        type: TypologyType.DORMANT_ACTIVATION,
        enabled: true,
        minConfidence: 0.5,
        regulatoryGuidance: 'Account Takeover Red Flags',
        sarNarrative: 'Previously dormant account suddenly activated with significant transaction activity, potential indicator of account compromise.'
    },
    {
        type: TypologyType.MIXER_INTERACTION,
        enabled: true,
        minConfidence: 0.8,
        regulatoryGuidance: 'FinCEN Guidance on Convertible Virtual Currency - Mixing Services',
        sarNarrative: 'Subject interacted with known cryptocurrency mixing service, potentially to obscure transaction trail.'
    },
    {
        type: TypologyType.SANCTIONS_PROXIMITY,
        enabled: true,
        minConfidence: 0.7,
        regulatoryGuidance: 'OFAC Compliance Framework - Sanctions Screening',
        sarNarrative: 'Subject has transaction history connecting to OFAC-designated entity within [N] degrees of separation.'
    },
    {
        type: TypologyType.HIGH_RISK_GEOGRAPHY,
        enabled: true,
        minConfidence: 0.6,
        regulatoryGuidance: 'FATF High-Risk Jurisdictions Subject to Call for Action',
        sarNarrative: 'Transaction involves jurisdiction identified by FATF as high-risk for ML/TF.'
    },
    {
        type: TypologyType.RAPID_MOVEMENT,
        enabled: true,
        minConfidence: 0.5,
        regulatoryGuidance: 'FATF ML/TF Velocity Indicators',
        sarNarrative: 'Subject conducted rapid succession of transactions, potentially to prevent detection or asset freezing.'
    },
    {
        type: TypologyType.PEP_INVOLVEMENT,
        enabled: true,
        minConfidence: 0.7,
        regulatoryGuidance: 'FATF R.12 - Politically Exposed Persons',
        sarNarrative: 'Transaction involves individual identified as Politically Exposed Person, requiring enhanced due diligence.'
    }
];
// ═══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION LOADER
// ═══════════════════════════════════════════════════════════════════════════════
/**
 * Load configuration from environment or defaults
 */
export function loadConfig() {
    // Check for environment overrides
    const env = process.env;
    const config = {
        version: '2.0.0',
        actionThresholds: {
            allow: { max: parseFloat(env.EXPLAIN_ALLOW_MAX || '0.40') },
            review: {
                min: parseFloat(env.EXPLAIN_REVIEW_MIN || '0.40'),
                max: parseFloat(env.EXPLAIN_REVIEW_MAX || '0.70')
            },
            escrow: {
                min: parseFloat(env.EXPLAIN_ESCROW_MIN || '0.70'),
                max: parseFloat(env.EXPLAIN_ESCROW_MAX || '0.85')
            },
            block: { min: parseFloat(env.EXPLAIN_BLOCK_MIN || '0.85') }
        },
        features: DEFAULT_FEATURE_CONFIGS,
        typologies: DEFAULT_TYPOLOGY_CONFIGS,
        cache: {
            enabled: env.EXPLAIN_CACHE_ENABLED !== 'false',
            ttlSeconds: parseInt(env.EXPLAIN_CACHE_TTL || '300'),
            maxSize: parseInt(env.EXPLAIN_CACHE_MAX_SIZE || '10000'),
            keyPrefix: env.EXPLAIN_CACHE_PREFIX || 'expl:'
        },
        metrics: {
            enabled: env.EXPLAIN_METRICS_ENABLED !== 'false',
            prefix: env.EXPLAIN_METRICS_PREFIX || 'amttp_explainability',
            labels: ['action', 'typology', 'degraded']
        },
        logging: {
            level: env.EXPLAIN_LOG_LEVEL || Severity.INFO,
            includeFeatures: env.EXPLAIN_LOG_FEATURES === 'true',
            redactPII: env.EXPLAIN_REDACT_PII !== 'false'
        }
    };
    return config;
}
/**
 * Get configuration hash for reproducibility
 */
export function getConfigHash(config) {
    const str = JSON.stringify({
        version: config.version,
        actionThresholds: config.actionThresholds,
        featureIds: config.features.map(f => `${f.id}:${f.enabled}`).join(','),
        typologyIds: config.typologies.map(t => `${t.type}:${t.enabled}`).join(',')
    });
    // Simple hash
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return Math.abs(hash).toString(16).padStart(8, '0');
}
// Export defaults for testing
export const DEFAULTS = {
    actionThresholds: DEFAULT_ACTION_THRESHOLDS,
    cache: DEFAULT_CACHE_CONFIG,
    metrics: DEFAULT_METRICS_CONFIG,
    logging: DEFAULT_LOGGING_CONFIG,
    features: DEFAULT_FEATURE_CONFIGS,
    typologies: DEFAULT_TYPOLOGY_CONFIGS
};
