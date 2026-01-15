// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";

/**
 * @title AMTTPPolicyEngine - Advanced policy management for AMTTP
 * @dev Manages user-defined transaction policies, risk thresholds, and approval workflows
 * @notice This contract has a richer implementation than the minimal IAMTTPPolicyEngine interface
 * used by AMTTPRouter. The Router uses a minimal interface for gas efficiency.
 */
contract AMTTPPolicyEngine is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable, 
    ReentrancyGuardUpgradeable
{
    
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
    mapping(address => bool) public trustedUsers;  // Global trusted users list
    
    // Global settings
    uint256 public globalRiskThreshold;
    uint256 public globalMaxAmount;
    bool public emergencyPause;
    address public amttpContract;
    address public oracleService;
    
    // Kleros Dispute Resolution
    address public disputeResolver;  // AMTTPDisputeResolver contract
    uint256 public escrowThreshold;  // Risk score threshold for escrow (default: 700)
    
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
    event TransactionEscrowedForDispute(bytes32 indexed txId, address indexed user, uint256 amount, uint256 riskScore);
    event HighRiskAutoBlocked(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    event MediumRiskFlagged(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    event LowRiskAutoApproved(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    
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
        
        // 6. HIGH RISK: Auto-block and flag for Kleros dispute
        // Transactions with risk score >= 700 are auto-blocked
        if (riskAction == PolicyAction.Block) {
            emit HighRiskAutoBlocked(user, counterparty, amount, dqnRiskScore);
            emit RiskThresholdExceeded(user, dqnRiskScore, riskPolicy.mediumThreshold);
            // Caller should route to Kleros escrow via routeToKlerosEscrow()
            return (PolicyAction.Block, "HIGH_RISK: Auto-blocked - route to Kleros for dispute");
        }
        
        // 7. MEDIUM RISK: Flag for human review
        // Transactions with risk score 400-699 need manual verification
        if (riskAction == PolicyAction.Review) {
            emit MediumRiskFlagged(user, counterparty, amount, dqnRiskScore);
            return (PolicyAction.Review, "MEDIUM_RISK: Flagged for human review");
        }
        
        // 8. Special approval requirements
        if (compliance.requireApproval && amount >= compliance.approvalThreshold) {
            return (PolicyAction.Review, "Manual approval required");
        }
        
        // 9. Cooldown period for large transactions
        if (amount >= policy.maxAmount / 2 && 
            block.timestamp < policy.lastLargeTransaction + policy.cooldownPeriod) {
            return (PolicyAction.Review, "Cooldown period active");
        }
        
        // 10. Trusted counterparty override (only affects Review → Approve)
        if (trustedCounterparties[user][counterparty] && riskAction == PolicyAction.Review) {
            riskAction = PolicyAction.Approve;
        }
        
        // 11. LOW RISK: Auto-approval for low/minimal risk scores (< 400)
        if (riskAction == PolicyAction.Approve) {
            _recordSuccessfulTransaction(user, amount);
            emit LowRiskAutoApproved(user, counterparty, amount, dqnRiskScore);
            emit TransactionValidated(user, counterparty, amount, PolicyAction.Approve);
            return (PolicyAction.Approve, "LOW_RISK: Auto-approved");
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
     * 
     * Default policy thresholds:
     * - LOW (0-399): Auto-approve - trusted transactions
     * - MEDIUM (400-699): Review - requires human verification  
     * - HIGH (700-1000): Block - auto-blocked, routed to Kleros escrow
     */
    function _getUserRiskPolicyWithDefaults(address user) internal view returns (RiskPolicy memory) {
        RiskPolicy memory policy = userRiskPolicies[user];
        
        if (policy.highThreshold == 0) {
            // Default risk policy: HIGH = Block, MEDIUM = Review, LOW = Approve
            policy = RiskPolicy({
                minimalThreshold: 200,    // 0-200: Very low risk
                lowThreshold: 400,        // 200-400: Low risk (auto-approve)
                mediumThreshold: 700,     // 400-700: Medium risk (review)
                highThreshold: 1000,      // 700-1000: High risk (auto-block)
                minimalAction: PolicyAction.Approve,  // Very low → approve
                lowAction: PolicyAction.Approve,      // Low → approve
                mediumAction: PolicyAction.Review,    // Medium → human review
                highAction: PolicyAction.Block,       // High → auto-block + Kleros
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
    
    // ---------------- Trusted User Management ----------------
    
    /**
     * @dev Add a user to the global trusted users list
     */
    function addTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = true;
    }
    
    /**
     * @dev Remove a user from the global trusted users list
     */
    function removeTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = false;
    }
    
    /**
     * @dev Check if a user is in the trusted users list
     */
    function isTrustedUser(address user) external view returns (bool) {
        return trustedUsers[user];
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
    
    /**
     * @dev Get policy engine status for tests and UI
     */
    struct PolicyEngineStatus {
        address policyEngineAddress;
        bool enabled;
        uint256 globalThreshold;
        string defaultModel;
    }
    
    function getPolicyEngineStatus() external view returns (PolicyEngineStatus memory) {
        return PolicyEngineStatus({
            policyEngineAddress: address(this),
            enabled: !emergencyPause,
            globalThreshold: globalRiskThreshold,
            defaultModel: activeModelVersion
        });
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
    
    // ============================================================
    // KLEROS DISPUTE RESOLUTION INTEGRATION
    // ============================================================
    
    /**
     * @dev Set the Kleros dispute resolver contract address
     * @param _disputeResolver Address of AMTTPDisputeResolver contract
     */
    function setDisputeResolver(address _disputeResolver) external onlyOwner {
        require(_disputeResolver != address(0), "Invalid address");
        disputeResolver = _disputeResolver;
    }
    
    /**
     * @dev Set the risk score threshold for escrow routing
     * @param _threshold Risk score (0-1000) above which transactions go to escrow
     */
    function setEscrowThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold <= 1000, "Invalid threshold");
        escrowThreshold = _threshold;
    }
    
    /**
     * @dev Check if a transaction should be routed to Kleros escrow
     * @param riskScore The risk score from ML model (0-1000)
     * @return shouldEscrow Whether transaction should go to dispute resolver
     */
    function shouldRouteToKleros(uint256 riskScore) public view returns (bool shouldEscrow) {
        if (disputeResolver == address(0)) return false;
        if (escrowThreshold == 0) return false;
        return riskScore >= escrowThreshold;
    }
    
    /**
     * @dev Get dispute resolver address
     */
    function getDisputeResolver() external view returns (address) {
        return disputeResolver;
    }
    
    /**
     * @dev Route a high-risk transaction to Kleros escrow for potential dispute
     * @param txId Unique transaction identifier
     * @param recipient Intended recipient
     * @param riskScore Risk score from ML model
     * @param evidenceURI IPFS URI containing ML evidence
     * @return success Whether the escrow was created
     */
    function routeToKlerosEscrow(
        bytes32 txId,
        address recipient,
        uint256 riskScore,
        string calldata evidenceURI
    ) external payable nonReentrant returns (bool success) {
        require(disputeResolver != address(0), "Dispute resolver not set");
        require(msg.value > 0, "No funds sent");
        require(riskScore >= escrowThreshold, "Risk below threshold");
        
        // Call the dispute resolver to escrow funds
        (bool sent, ) = disputeResolver.call{value: msg.value}(
            abi.encodeWithSignature(
                "escrowTransaction(bytes32,address,uint256,string)",
                txId,
                recipient,
                riskScore,
                evidenceURI
            )
        );
        
        require(sent, "Escrow failed");
        
        emit TransactionEscrowedForDispute(txId, msg.sender, msg.value, riskScore);
        
        return true;
    }
    
    // ---------------- Upgrade Authorization ----------------
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    // ════════════════════════════════════════════════════════════════════
    //              STORAGE GAP (Security Enhancement for Upgrades)
    // ════════════════════════════════════════════════════════════════════
    
    /**
     * @dev Reserved storage space for future upgrades.
     * This allows adding new state variables without shifting storage layout.
     */
    uint256[50] private __gap;
}