// Policy action enum matching smart contract
export var PolicyAction;
(function (PolicyAction) {
    PolicyAction[PolicyAction["APPROVE"] = 0] = "APPROVE";
    PolicyAction[PolicyAction["REVIEW"] = 1] = "REVIEW";
    PolicyAction[PolicyAction["ESCROW"] = 2] = "ESCROW";
    PolicyAction[PolicyAction["BLOCK"] = 3] = "BLOCK";
})(PolicyAction || (PolicyAction = {}));
// Risk level enum matching smart contract
export var RiskLevel;
(function (RiskLevel) {
    RiskLevel[RiskLevel["MINIMAL"] = 0] = "MINIMAL";
    RiskLevel[RiskLevel["LOW"] = 1] = "LOW";
    RiskLevel[RiskLevel["MEDIUM"] = 2] = "MEDIUM";
    RiskLevel[RiskLevel["HIGH"] = 3] = "HIGH";
})(RiskLevel || (RiskLevel = {}));
//# sourceMappingURL=types.js.map