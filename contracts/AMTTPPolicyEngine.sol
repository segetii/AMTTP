// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";

/**
 * @title AMTTPPolicyEngine - Advanced policy management for AMTTP
 * @dev Manages user-defined transaction policies, risk thresholds, and approval workflows
 */
contract AMTTPPolicyEngine is Initializable, OwnableUpgradeable, UUPSUpgradeable, ReentrancyGuardUpgradeable {
    
    // ---------------- Enums ----------------
    enum RiskLevel { Minimal, Low, Medium, High }
    enum PolicyAction { Approve, Review, Escrow, Block }
    enum VelocityWindow { Hour, Day, Week, Month }
    
    // ---------------- Structs ----------------
    struct TransactionPolicy {
        uint256 maxAmount;                    // Maximum transaction amount
        uint256 dailyLimit;                   // 24-hour transaction limit
        uint256 weeklyLimit;                  // 7-day transaction limit
        uint256 monthlyLimit;                 // 30-day transaction limit
        uint256 riskThreshold;                // Risk threshold (0-1000, representing 0-1.0)
        address[] allowedCounterparties;      // Whitelist of addresses
        address[] blockedCounterparties;      // Blacklist of addresses
        bool autoApprove;                     // Auto-approve low risk transactions
        bool enabled;                         // Policy is active
        uint256 cooldownPeriod;               // Time between large transactions
        uint256 lastLargeTransaction;         // Timestamp of last large transaction
    }
    
    struct RiskPolicy {
        uint256 minimalThreshold;             // 0-250 (0-0.25)
        uint256 lowThreshold;                 // 250-400 (0.25-0.40)  
        uint256 mediumThreshold;              // 400-700 (0.40-0.70)
        uint256 highThreshold;                // 700-1000 (0.70-1.0)
        PolicyAction minimalAction;
        PolicyAction lowAction;
        PolicyAction mediumAction;
        PolicyAction highAction;
        bool adaptiveThresholds;              // Adjust thresholds based on user behavior
    }
    
    struct VelocityLimit {
        uint256 maxTransactions;              // Max transactions in window
        uint256 maxVolume;                    // Max volume in window
        VelocityWindow window;                // Time window
        bool enabled;
    }
    
    struct ComplianceRule {
        bool requireKYC;                      // KYC required for transactions
        bool requireApproval;                 // Manual approval required
        uint256 approvalThreshold;            // Amount requiring approval
        address[] approvers;                  // List of approved addresses
        uint256 approvalTimeout;              // Timeout for approvals
        bool geofencing;                      // Geographic restrictions
        string[] allowedCountries;            // Allowed country codes
    }
    
    struct UserActivity {
        uint256 dailyVolume;                  // Today's transaction volume
        uint256 weeklyVolume;                 // This week's volume
        uint256 monthlyVolume;                // This month's volume
        uint256 dailyCount;                   // Today's transaction count
        uint256 lastTransactionTime;         // Last transaction timestamp
        uint256 lastResetTime;                // Last reset timestamp
        uint256 suspiciousScore;              // Cumulative suspicious activity score
        bool frozen;                          // Account frozen status
    }
    
    // ---------------- State Variables ----------------
    mapping(address => TransactionPolicy) public userPolicies;
    mapping(address => RiskPolicy) public userRiskPolicies;
    mapping(address => VelocityLimit[]) public userVelocityLimits;
    mapping(address => ComplianceRule) public userComplianceRules;
    mapping(address => UserActivity) public userActivity;
    mapping(address => mapping(address => bool)) public trustedCounterparties;
    mapping(address => bool) public globalApprovers;
    
    // Global settings
    uint256 public globalRiskThreshold;
    uint256 public globalMaxAmount;
    bool public emergencyPause;
    address public amttpContract;
    address public oracleService;
    
    // DQN Model integration
    mapping(string => uint256) public modelVersionScores; // Model version -> F1 score
    string public activeModelVersion;
    uint256 public minimumModelScore;                     // Minimum F1 score (e.g., 669 for 0.669)
    
    // ---------------- Events ----------------
    event PolicyUpdated(address indexed user, string policyType);
    event TransactionValidated(address indexed user, address indexed counterparty, uint256 amount, PolicyAction action);
    event RiskThresholdExceeded(address indexed user, uint256 riskScore, uint256 threshold);
    event VelocityLimitExceeded(address indexed user, VelocityWindow window, uint256 amount);
    event AccountFrozen(address indexed user, string reason);
    event AccountUnfrozen(address indexed user);
    event EmergencyPauseToggled(bool paused);
    event ModelVersionUpdated(string version, uint256 f1Score);
    event ComplianceViolation(address indexed user, string reason);
    
    // ---------------- Modifiers ----------------
    modifier onlyAMTTP() {
        require(msg.sender == amttpContract, "Only AMTTP contract");
        _;
    }
    
    modifier notPaused() {
        require(!emergencyPause, "System paused");
        _;
    }
    
    modifier notFrozen(address user) {
        require(!userActivity[user].frozen, "Account frozen");
        _;
    }
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    // ---------------- Initialization ----------------
    function initialize(address _amttpContract, address _oracleService) public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        
        amttpContract = _amttpContract;
        oracleService = _oracleService;
        globalRiskThreshold = 700; // 0.70 default
        globalMaxAmount = 100 ether; // 100 ETH default
        activeModelVersion = "DQN-v1.0-real-fraud";
        minimumModelScore = 669; // 0.669 F1 score minimum
        
        // Set default model score
        modelVersionScores["DQN-v1.0-real-fraud"] = 669;
    }
    
    // ---------------- Policy Management ----------------
    
    /**
     * @dev Set transaction policy for a user
     */
    function setTransactionPolicy(
        address user,
        uint256 maxAmount,
        uint256 dailyLimit,
        uint256 weeklyLimit,
        uint256 monthlyLimit,
        uint256 riskThreshold,
        bool autoApprove,
        uint256 cooldownPeriod
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        require(maxAmount <= globalMaxAmount, "Exceeds global limit");
        require(riskThreshold <= 1000, "Invalid risk threshold");
        
        userPolicies[user] = TransactionPolicy({
            maxAmount: maxAmount,
            dailyLimit: dailyLimit,
            weeklyLimit: weeklyLimit,
            monthlyLimit: monthlyLimit,
            riskThreshold: riskThreshold,
            allowedCounterparties: userPolicies[user].allowedCounterparties,
            blockedCounterparties: userPolicies[user].blockedCounterparties,
            autoApprove: autoApprove,
            enabled: true,
            cooldownPeriod: cooldownPeriod,
            lastLargeTransaction: userPolicies[user].lastLargeTransaction
        });
        
        emit PolicyUpdated(user, "transaction");
    }
    
    /**
     * @dev Set risk policy for a user  
     */
    function setRiskPolicy(
        address user,
        uint256[4] memory thresholds, // [minimal, low, medium, high]
        PolicyAction[4] memory actions,
        bool adaptiveThresholds
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        require(thresholds[0] < thresholds[1] && thresholds[1] < thresholds[2] && thresholds[2] < thresholds[3], "Invalid thresholds");
        
        userRiskPolicies[user] = RiskPolicy({
            minimalThreshold: thresholds[0],
            lowThreshold: thresholds[1],
            mediumThreshold: thresholds[2],
            highThreshold: thresholds[3],
            minimalAction: actions[0],
            lowAction: actions[1],
            mediumAction: actions[2],
            highAction: actions[3],
            adaptiveThresholds: adaptiveThresholds
        });
        
        emit PolicyUpdated(user, "risk");
    }
    
    /**
     * @dev Add velocity limit for a user
     */
    function addVelocityLimit(
        address user,
        uint256 maxTransactions,
        uint256 maxVolume,
        VelocityWindow window
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        
        userVelocityLimits[user].push(VelocityLimit({
            maxTransactions: maxTransactions,
            maxVolume: maxVolume,
            window: window,
            enabled: true
        }));
        
        emit PolicyUpdated(user, "velocity");
    }
    
    /**
     * @dev Set compliance rules for a user
     */
    function setComplianceRules(
        address user,
        bool requireKYC,
        bool requireApproval,
        uint256 approvalThreshold,
        uint256 approvalTimeout,
        bool geofencing
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        
        userComplianceRules[user].requireKYC = requireKYC;
        userComplianceRules[user].requireApproval = requireApproval;
        userComplianceRules[user].approvalThreshold = approvalThreshold;
        userComplianceRules[user].approvalTimeout = approvalTimeout;
        userComplianceRules[user].geofencing = geofencing;
        
        emit PolicyUpdated(user, "compliance");
    }
    
    // ---------------- Transaction Validation ----------------
    
    /**
     * @dev Validate transaction against user policies and DQN risk score
     */
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 dqnRiskScore,        // Risk score from your DQN model (0-1000)
        string memory modelVersion,
        bytes32 kycHash
    ) external onlyAMTTP notPaused notFrozen(user) returns (PolicyAction action, string memory reason) {
        
        // Update user activity
        _updateUserActivity(user, amount);
        
        // Check model version
        require(modelVersionScores[modelVersion] >= minimumModelScore, "Model version not approved");
        
        // Get user policies (with defaults if not set)
        TransactionPolicy memory policy = _getUserPolicyWithDefaults(user);
        RiskPolicy memory riskPolicy = _getUserRiskPolicyWithDefaults(user);
        ComplianceRule memory compliance = userComplianceRules[user];
        
        // 1. Basic policy checks
        if (amount > policy.maxAmount) {
            return (PolicyAction.Block, "Exceeds maximum amount");
        }
        
        // 2. Velocity checks
        if (!_checkVelocityLimits(user, amount)) {
            return (PolicyAction.Block, "Velocity limit exceeded");
        }
        
        // 3. Counterparty checks
        if (_isBlockedCounterparty(user, counterparty)) {
            return (PolicyAction.Block, "Blocked counterparty");
        }
        
        // 4. KYC compliance
        if (compliance.requireKYC && kycHash == bytes32(0)) {
            return (PolicyAction.Block, "KYC required");
        }
        
        // 5. DQN Risk Assessment - Your trained model integration
        PolicyAction riskAction = _assessDQNRisk(dqnRiskScore, riskPolicy);
        
        // 6. Special approval requirements
        if (compliance.requireApproval && amount >= compliance.approvalThreshold) {
            return (PolicyAction.Review, "Manual approval required");
        }
        
        // 7. Cooldown period for large transactions
        if (amount >= policy.maxAmount / 2 && 
            block.timestamp < policy.lastLargeTransaction + policy.cooldownPeriod) {
            return (PolicyAction.Review, "Cooldown period active");
        }
        
        // 8. Trusted counterparty override
        if (trustedCounterparties[user][counterparty] && riskAction == PolicyAction.Review) {
            riskAction = PolicyAction.Approve;
        }
        
        // 9. Auto-approval for low risk
        if (policy.autoApprove && riskAction == PolicyAction.Approve) {
            _recordSuccessfulTransaction(user, amount);
            emit TransactionValidated(user, counterparty, amount, PolicyAction.Approve);
            return (PolicyAction.Approve, "Auto-approved");
        }
        
        emit TransactionValidated(user, counterparty, amount, riskAction);
        return (riskAction, _getRiskActionReason(dqnRiskScore, riskAction));
    }
    
    /**
     * @dev Assess risk using your DQN model scores
     */
    function _assessDQNRisk(uint256 riskScore, RiskPolicy memory policy) internal pure returns (PolicyAction) {
        if (riskScore <= policy.minimalThreshold) {
            return policy.minimalAction;
        } else if (riskScore <= policy.lowThreshold) {
            return policy.lowAction;
        } else if (riskScore <= policy.mediumThreshold) {
            return policy.mediumAction;
        } else {
            return policy.highAction;
        }
    }
    
    /**
     * @dev Update user activity tracking
     */
    function _updateUserActivity(address user, uint256 amount) internal {
        UserActivity storage activity = userActivity[user];
        
        // Reset counters if new day/week/month
        if (block.timestamp >= activity.lastResetTime + 1 days) {
            activity.dailyVolume = 0;
            activity.dailyCount = 0;
            activity.lastResetTime = block.timestamp;
        }
        
        if (block.timestamp >= activity.lastResetTime + 7 days) {
            activity.weeklyVolume = 0;
        }
        
        if (block.timestamp >= activity.lastResetTime + 30 days) {
            activity.monthlyVolume = 0;
        }
        
        // Update counters
        activity.dailyVolume += amount;
        activity.weeklyVolume += amount;
        activity.monthlyVolume += amount;
        activity.dailyCount += 1;
        activity.lastTransactionTime = block.timestamp;
    }
    
    /**
     * @dev Check velocity limits
     */
    function _checkVelocityLimits(address user, uint256 amount) internal view returns (bool) {
        VelocityLimit[] memory limits = userVelocityLimits[user];
        UserActivity memory activity = userActivity[user];
        
        for (uint i = 0; i < limits.length; i++) {
            if (!limits[i].enabled) continue;
            
            if (limits[i].window == VelocityWindow.Day) {
                if (activity.dailyVolume + amount > limits[i].maxVolume ||
                    activity.dailyCount + 1 > limits[i].maxTransactions) {
                    return false;
                }
            }
            // Add other window checks as needed
        }
        
        return true;
    }
    
    /**
     * @dev Get user policy with defaults
     */
    function _getUserPolicyWithDefaults(address user) internal view returns (TransactionPolicy memory) {
        TransactionPolicy memory policy = userPolicies[user];
        
        if (!policy.enabled) {
            // Return default policy
            policy = TransactionPolicy({
                maxAmount: 10 ether,
                dailyLimit: 50 ether,
                weeklyLimit: 200 ether,
                monthlyLimit: 500 ether,
                riskThreshold: 700, // 0.70
                allowedCounterparties: new address[](0),
                blockedCounterparties: new address[](0),
                autoApprove: true,
                enabled: true,
                cooldownPeriod: 1 hours,
                lastLargeTransaction: 0
            });
        }
        
        return policy;
    }
    
    /**
     * @dev Get user risk policy with defaults
     */
    function _getUserRiskPolicyWithDefaults(address user) internal view returns (RiskPolicy memory) {
        RiskPolicy memory policy = userRiskPolicies[user];
        
        if (policy.highThreshold == 0) {
            // Return default risk policy based on your DQN model performance
            policy = RiskPolicy({
                minimalThreshold: 200,    // 0.20
                lowThreshold: 400,        // 0.40  
                mediumThreshold: 700,     // 0.70
                highThreshold: 1000,      // 1.00
                minimalAction: PolicyAction.Approve,
                lowAction: PolicyAction.Approve,
                mediumAction: PolicyAction.Review,
                highAction: PolicyAction.Escrow,
                adaptiveThresholds: false
            });
        }
        
        return policy;
    }
    
    function _isBlockedCounterparty(address user, address counterparty) internal view returns (bool) {
        address[] memory blocked = userPolicies[user].blockedCounterparties;
        for (uint i = 0; i < blocked.length; i++) {
            if (blocked[i] == counterparty) return true;
        }
        return false;
    }
    
    function _recordSuccessfulTransaction(address user, uint256 amount) internal {
        if (amount >= userPolicies[user].maxAmount / 2) {
            userPolicies[user].lastLargeTransaction = block.timestamp;
        }
    }
    
    function _getRiskActionReason(uint256 riskScore, PolicyAction action) internal pure returns (string memory) {
        if (action == PolicyAction.Approve) return "Low risk - approved";
        if (action == PolicyAction.Review) return "Medium risk - review required";
        if (action == PolicyAction.Escrow) return "High risk - escrow required";
        return "Very high risk - blocked";
    }
    
    // ---------------- DQN Model Management ----------------
    
    /**
     * @dev Update DQN model version and performance score
     */
    function updateModelVersion(string memory version, uint256 f1Score) external {
        require(msg.sender == oracleService || msg.sender == owner(), "Unauthorized");
        require(f1Score >= minimumModelScore, "Model performance too low");
        
        modelVersionScores[version] = f1Score;
        activeModelVersion = version;
        
        emit ModelVersionUpdated(version, f1Score);
    }
    
    /**
     * @dev Set minimum model performance requirement
     */
    function setMinimumModelScore(uint256 score) external onlyOwner {
        require(score <= 1000, "Invalid score");
        minimumModelScore = score;
    }
    
    // ---------------- Admin Functions ----------------
    
    function setEmergencyPause(bool paused) external onlyOwner {
        emergencyPause = paused;
        emit EmergencyPauseToggled(paused);
    }
    
    function freezeAccount(address user, string memory reason) external onlyOwner {
        userActivity[user].frozen = true;
        emit AccountFrozen(user, reason);
    }
    
    function unfreezeAccount(address user) external onlyOwner {
        userActivity[user].frozen = false;
        emit AccountUnfrozen(user);
    }
    
    function addTrustedCounterparty(address user, address counterparty) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        trustedCounterparties[user][counterparty] = true;
    }
    
    function removeTrustedCounterparty(address user, address counterparty) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        trustedCounterparties[user][counterparty] = false;
    }
    
    // ---------------- View Functions ----------------
    
    function getUserPolicy(address user) external view returns (TransactionPolicy memory) {
        return _getUserPolicyWithDefaults(user);
    }
    
    function getUserRiskPolicy(address user) external view returns (RiskPolicy memory) {
        return _getUserRiskPolicyWithDefaults(user);
    }
    
    function getUserActivity(address user) external view returns (UserActivity memory) {
        return userActivity[user];
    }
    
    function getModelPerformance(string memory version) external view returns (uint256) {
        return modelVersionScores[version];
    }
    
    function isTransactionAllowed(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, string memory reason) {
        if (emergencyPause) return (false, "System paused");
        if (userActivity[user].frozen) return (false, "Account frozen");
        
        TransactionPolicy memory policy = _getUserPolicyWithDefaults(user);
        
        if (amount > policy.maxAmount) return (false, "Exceeds maximum amount");
        if (_isBlockedCounterparty(user, counterparty)) return (false, "Blocked counterparty");
        
        RiskPolicy memory riskPolicy = _getUserRiskPolicyWithDefaults(user);
        PolicyAction action = _assessDQNRisk(riskScore, riskPolicy);
        
        if (action == PolicyAction.Block) return (false, "Risk too high");
        
        return (true, "Transaction allowed");
    }
    
    // ---------------- Upgrade Authorization ----------------
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}