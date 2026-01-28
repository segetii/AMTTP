/**
 * Type Definitions for Production Explainability System
 *
 * All interfaces are designed for:
 * - Regulatory compliance (audit trails)
 * - API stability (versioned contracts)
 * - Type safety (strict mode compatible)
 */
// ═══════════════════════════════════════════════════════════════════════════════
// ENUMS
// ═══════════════════════════════════════════════════════════════════════════════
/**
 * Impact level for risk factors - determines weight and display priority
 */
export var ImpactLevel;
(function (ImpactLevel) {
    ImpactLevel["CRITICAL"] = "CRITICAL";
    ImpactLevel["HIGH"] = "HIGH";
    ImpactLevel["MEDIUM"] = "MEDIUM";
    ImpactLevel["LOW"] = "LOW";
    ImpactLevel["NEUTRAL"] = "NEUTRAL"; // No significant impact (weight: 0)
})(ImpactLevel || (ImpactLevel = {}));
/**
 * Known fraud/AML typology patterns
 */
export var TypologyType;
(function (TypologyType) {
    TypologyType["STRUCTURING"] = "structuring";
    TypologyType["LAYERING"] = "layering";
    TypologyType["ROUND_TRIP"] = "round_trip";
    TypologyType["SMURFING"] = "smurfing";
    TypologyType["FAN_OUT"] = "fan_out";
    TypologyType["FAN_IN"] = "fan_in";
    TypologyType["DORMANT_ACTIVATION"] = "dormant_activation";
    TypologyType["MIXER_INTERACTION"] = "mixer_interaction";
    TypologyType["SANCTIONS_PROXIMITY"] = "sanctions_proximity";
    TypologyType["HIGH_RISK_GEOGRAPHY"] = "high_risk_geography";
    TypologyType["RAPID_MOVEMENT"] = "rapid_movement";
    TypologyType["UNUSUAL_TIMING"] = "unusual_timing";
    TypologyType["PEP_INVOLVEMENT"] = "pep_involvement";
    TypologyType["SHELL_COMPANY"] = "shell_company";
})(TypologyType || (TypologyType = {}));
/**
 * Actions taken on transactions
 */
export var RiskAction;
(function (RiskAction) {
    RiskAction["ALLOW"] = "ALLOW";
    RiskAction["REVIEW"] = "REVIEW";
    RiskAction["ESCROW"] = "ESCROW";
    RiskAction["BLOCK"] = "BLOCK";
})(RiskAction || (RiskAction = {}));
/**
 * Severity levels for logging and alerts
 */
export var Severity;
(function (Severity) {
    Severity["DEBUG"] = "DEBUG";
    Severity["INFO"] = "INFO";
    Severity["WARN"] = "WARN";
    Severity["ERROR"] = "ERROR";
    Severity["CRITICAL"] = "CRITICAL";
})(Severity || (Severity = {}));
