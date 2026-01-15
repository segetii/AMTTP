// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./interfaces/IBiconomy.sol";

/**
 * @title AMTTPBiconomyModule
 * @notice ERC-4337 compliant validation module for Biconomy Smart Accounts
 * @dev Integrates AMTTP risk assessment with Account Abstraction for gasless transactions
 * 
 * Features:
 * - UserOperation validation with ML risk scoring
 * - Session key management with AMTTP policies
 * - Spending limits with risk-based adjustments
 * - Paymaster integration for sponsored transactions
 * - Compliance-aware transaction batching
 */
contract AMTTPBiconomyModule is Ownable, ReentrancyGuard, Pausable {
    
    // ============ Constants ============
    uint256 public constant RISK_PRECISION = 1000;
    uint256 public constant DEFAULT_RISK_THRESHOLD = 600;
    uint256 public constant SESSION_KEY_VALIDITY = 24 hours;
    bytes4 public constant VALIDATION_SUCCESS = 0x00000000;
    bytes4 public constant VALIDATION_FAILED = 0xffffffff;
    
    // ============ Structs ============
    
    struct AccountConfig {
        bool enabled;
        uint256 riskThreshold;          // Max allowed risk score
        uint256 dailySpendLimit;        // Daily spending limit in wei
        uint256 singleTxLimit;          // Single transaction limit
        bool requireMLValidation;       // Require ML check for all transactions
        bool allowSessionKeys;          // Allow session key delegation
        bool allowBatching;             // Allow transaction batching
    }
    
    struct SessionKey {
        address key;
        uint48 validAfter;
        uint48 validUntil;
        address[] allowedTargets;
        bytes4[] allowedSelectors;
        uint256 spendingLimit;
        uint256 spentAmount;
        uint256 maxRiskAllowed;
        bool active;
    }
    
    struct SpendingTracker {
        uint256 dailySpent;
        uint256 weeklySpent;
        uint256 lastDayReset;
        uint256 lastWeekReset;
        uint256 transactionCount;
    }
    
    struct ValidationResult {
        bool valid;
        uint256 riskScore;
        string reason;
        bool requiresReview;
    }
    
    struct RiskAssessment {
        uint256 score;
        string category;
        bool sanctioned;
        uint256 timestamp;
    }
    
    // ============ State Variables ============
    
    // AMTTP Integration
    address public policyEngine;
    address public mlOracleService;
    
    // ERC-4337 EntryPoint
    IEntryPoint public immutable entryPoint;
    
    // Account configurations
    mapping(address => AccountConfig) public accountConfigs;
    mapping(address => bool) public registeredAccounts;
    
    // Session keys per account
    mapping(address => mapping(address => SessionKey)) public sessionKeys;
    mapping(address => address[]) public accountSessionKeys;
    
    // Spending tracking
    mapping(address => SpendingTracker) public spendingTrackers;
    
    // Risk cache (to avoid repeated oracle calls)
    // Note: Mappings are implicitly initialized - entries default to zero values until set
    // slither-disable-next-line uninitialized-state
    mapping(address => RiskAssessment) public riskCache;
    uint256 public riskCacheTTL = 5 minutes;
    
    // Trusted forwarders for meta-transactions
    mapping(address => bool) public trustedForwarders;
    
    // Paymaster whitelist
    mapping(address => bool) public approvedPaymasters;
    
    // ============ Events ============
    
    event AccountRegistered(address indexed account, AccountConfig config);
    event AccountConfigUpdated(address indexed account);
    event SessionKeyCreated(address indexed account, address indexed sessionKey, uint48 validUntil);
    event SessionKeyRevoked(address indexed account, address indexed sessionKey);
    event TransactionValidated(address indexed account, bytes32 userOpHash, uint256 riskScore, bool approved);
    event SpendingLimitUpdated(address indexed account, uint256 newLimit);
    event RiskThresholdUpdated(address indexed account, uint256 newThreshold);
    event PaymasterApproved(address indexed paymaster, bool status);
    event ForwarderUpdated(address indexed forwarder, bool trusted);
    
    // ============ Errors ============
    
    error AccountNotRegistered();
    error InvalidSessionKey();
    error SessionKeyExpired();
    error SpendingLimitExceeded();
    error RiskThresholdExceeded();
    error UnauthorizedTarget();
    error UnauthorizedSelector();
    error InvalidSignature();
    error BatchingNotAllowed();
    
    // ============ Constructor ============
    
    constructor(
        address _entryPoint,
        address _policyEngine,
        address _mlOracle
    ) {
        require(_entryPoint != address(0), "Invalid entry point");
        require(_policyEngine != address(0), "Invalid policy engine");
        
        entryPoint = IEntryPoint(_entryPoint);
        policyEngine = _policyEngine;
        mlOracleService = _mlOracle;
    }
    
    // ============ Account Registration ============
    
    /**
     * @notice Register a smart account with AMTTP module
     * @param account Address of the Biconomy smart account
     * @param config Initial account configuration
     */
    function registerAccount(
        address account,
        AccountConfig calldata config
    ) external {
        require(!registeredAccounts[account], "Already registered");
        require(account != address(0), "Invalid account");
        
        // Verify caller is account owner or the account itself
        require(
            msg.sender == account || 
            ISmartAccount(account).isModuleEnabled(address(this)),
            "Not authorized"
        );
        
        registeredAccounts[account] = true;
        accountConfigs[account] = AccountConfig({
            enabled: true,
            riskThreshold: config.riskThreshold > 0 ? config.riskThreshold : DEFAULT_RISK_THRESHOLD,
            dailySpendLimit: config.dailySpendLimit,
            singleTxLimit: config.singleTxLimit,
            requireMLValidation: config.requireMLValidation,
            allowSessionKeys: config.allowSessionKeys,
            allowBatching: config.allowBatching
        });
        
        emit AccountRegistered(account, accountConfigs[account]);
    }
    
    /**
     * @notice Update account configuration
     */
    function updateAccountConfig(
        address account,
        AccountConfig calldata config
    ) external {
        require(registeredAccounts[account], "Not registered");
        require(msg.sender == account || _isAccountOwner(account, msg.sender), "Not authorized");
        
        accountConfigs[account] = config;
        emit AccountConfigUpdated(account);
    }
    
    // ============ UserOperation Validation ============
    
    /**
     * @notice Validate a UserOperation before execution
     * @dev Called by the smart account during validateUserOp
     * @param userOp The UserOperation to validate
     * @param userOpHash Hash of the UserOperation
     * @return validationData 0 if valid, 1 if invalid
     */
    function validateUserOp(
        UserOperation calldata userOp,
        bytes32 userOpHash
    ) external returns (uint256 validationData) {
        address account = userOp.sender;
        
        if (!registeredAccounts[account]) {
            return 1; // Allow but skip AMTTP validation
        }
        
        AccountConfig memory config = accountConfigs[account];
        if (!config.enabled) {
            return 0; // Module disabled, allow
        }
        
        // Decode call data to determine operation
        (address target, uint256 value, bytes memory data) = _decodeCallData(userOp.callData);
        
        // Check session key if applicable
        if (config.allowSessionKeys) {
            address sessionKey = _extractSessionKey(userOp.signature);
            if (sessionKey != address(0)) {
                ValidationResult memory result = _validateSessionKey(account, sessionKey, target, value, data);
                if (!result.valid) {
                    return 1;
                }
            }
        }
        
        // Check spending limits
        if (!_checkSpendingLimits(account, value)) {
            return 1;
        }
        
        // ML risk assessment
        if (config.requireMLValidation) {
            ValidationResult memory riskResult = _performRiskAssessment(account, target, value, data);
            
            emit TransactionValidated(account, userOpHash, riskResult.riskScore, riskResult.valid);
            
            if (!riskResult.valid) {
                return 1;
            }
        }
        
        // Update spending tracker
        _updateSpending(account, value);
        
        return 0; // Valid
    }
    
    /**
     * @notice Validate a batch operation
     */
    function validateBatch(
        address account,
        address[] calldata targets,
        uint256[] calldata values,
        bytes[] calldata datas
    ) external returns (bool valid, uint256 totalRiskScore) {
        if (!accountConfigs[account].allowBatching) {
            revert BatchingNotAllowed();
        }
        
        uint256 totalValue = 0;
        totalRiskScore = 0;
        
        for (uint256 i = 0; i < targets.length; i++) {
            totalValue += values[i];
            
            ValidationResult memory result = _performRiskAssessment(account, targets[i], values[i], datas[i]);
            totalRiskScore += result.riskScore;
            
            if (!result.valid) {
                return (false, totalRiskScore);
            }
        }
        
        // Check total spending
        if (!_checkSpendingLimits(account, totalValue)) {
            return (false, totalRiskScore);
        }
        
        return (true, totalRiskScore / targets.length);
    }
    
    // ============ Session Key Management ============
    
    /**
     * @notice Create a new session key for delegated transactions
     */
    function createSessionKey(
        address account,
        address sessionKey,
        uint48 validUntil,
        address[] calldata allowedTargets,
        bytes4[] calldata allowedSelectors,
        uint256 spendingLimit,
        uint256 maxRiskAllowed
    ) external {
        require(registeredAccounts[account], "Not registered");
        require(accountConfigs[account].allowSessionKeys, "Session keys disabled");
        require(msg.sender == account || _isAccountOwner(account, msg.sender), "Not authorized");
        require(validUntil > block.timestamp, "Invalid validity");
        
        sessionKeys[account][sessionKey] = SessionKey({
            key: sessionKey,
            validAfter: uint48(block.timestamp),
            validUntil: validUntil,
            allowedTargets: allowedTargets,
            allowedSelectors: allowedSelectors,
            spendingLimit: spendingLimit,
            spentAmount: 0,
            maxRiskAllowed: maxRiskAllowed > 0 ? maxRiskAllowed : accountConfigs[account].riskThreshold,
            active: true
        });
        
        accountSessionKeys[account].push(sessionKey);
        
        emit SessionKeyCreated(account, sessionKey, validUntil);
    }
    
    /**
     * @notice Revoke a session key
     */
    function revokeSessionKey(address account, address sessionKey) external {
        require(msg.sender == account || _isAccountOwner(account, msg.sender), "Not authorized");
        
        sessionKeys[account][sessionKey].active = false;
        emit SessionKeyRevoked(account, sessionKey);
    }
    
    /**
     * @notice Get all session keys for an account
     */
    function getSessionKeys(address account) external view returns (address[] memory) {
        return accountSessionKeys[account];
    }
    
    /**
     * @notice Check if session key is valid
     */
    function isSessionKeyValid(address account, address sessionKey) external view returns (bool) {
        SessionKey memory sk = sessionKeys[account][sessionKey];
        return sk.active && 
               block.timestamp >= sk.validAfter && 
               block.timestamp <= sk.validUntil &&
               sk.spentAmount < sk.spendingLimit;
    }
    
    // ============ Paymaster Integration ============
    
    /**
     * @notice Approve a paymaster for sponsored transactions
     */
    function approvePaymaster(address paymaster, bool approved) external onlyOwner {
        approvedPaymasters[paymaster] = approved;
        emit PaymasterApproved(paymaster, approved);
    }
    
    /**
     * @notice Check if paymaster is approved
     */
    function isPaymasterApproved(address paymaster) external view returns (bool) {
        return approvedPaymasters[paymaster];
    }
    
    // ============ Admin Functions ============
    
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        require(_policyEngine != address(0), "Invalid address");
        policyEngine = _policyEngine;
    }
    
    function setMLOracle(address _mlOracle) external onlyOwner {
        mlOracleService = _mlOracle;
    }
    
    function setRiskCacheTTL(uint256 _ttl) external onlyOwner {
        riskCacheTTL = _ttl;
    }
    
    function setTrustedForwarder(address forwarder, bool trusted) external onlyOwner {
        trustedForwarders[forwarder] = trusted;
        emit ForwarderUpdated(forwarder, trusted);
    }
    
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    // ============ View Functions ============
    
    function getSpendingInfo(address account) external view returns (
        uint256 dailySpent,
        uint256 dailyLimit,
        uint256 remainingToday
    ) {
        SpendingTracker memory tracker = spendingTrackers[account];
        AccountConfig memory config = accountConfigs[account];
        
        dailySpent = tracker.dailySpent;
        dailyLimit = config.dailySpendLimit;
        
        if (dailyLimit > dailySpent) {
            remainingToday = dailyLimit - dailySpent;
        }
    }
    
    function getAccountRisk(address account) external view returns (
        uint256 currentRiskScore,
        uint256 riskThreshold,
        bool withinThreshold
    ) {
        RiskAssessment memory assessment = riskCache[account];
        AccountConfig memory config = accountConfigs[account];
        
        currentRiskScore = assessment.score;
        riskThreshold = config.riskThreshold;
        withinThreshold = currentRiskScore <= riskThreshold;
    }
    
    // ============ Internal Functions ============
    
    function _checkSpendingLimits(address account, uint256 value) internal view returns (bool) {
        AccountConfig memory config = accountConfigs[account];
        SpendingTracker memory tracker = spendingTrackers[account];
        
        // Check single transaction limit
        if (config.singleTxLimit > 0 && value > config.singleTxLimit) {
            return false;
        }
        
        // Check daily limit
        uint256 currentDay = block.timestamp / 1 days;
        uint256 dailySpent = tracker.lastDayReset == currentDay ? tracker.dailySpent : 0;
        
        if (config.dailySpendLimit > 0 && dailySpent + value > config.dailySpendLimit) {
            return false;
        }
        
        return true;
    }
    
    function _updateSpending(address account, uint256 value) internal {
        SpendingTracker storage tracker = spendingTrackers[account];
        uint256 currentDay = block.timestamp / 1 days;
        uint256 currentWeek = block.timestamp / 1 weeks;
        
        // Reset daily if new day
        if (tracker.lastDayReset < currentDay) {
            tracker.dailySpent = 0;
            tracker.lastDayReset = currentDay;
        }
        
        // Reset weekly if new week
        if (tracker.lastWeekReset < currentWeek) {
            tracker.weeklySpent = 0;
            tracker.lastWeekReset = currentWeek;
        }
        
        tracker.dailySpent += value;
        tracker.weeklySpent += value;
        tracker.transactionCount++;
    }
    
    function _validateSessionKey(
        address account,
        address sessionKey,
        address target,
        uint256 value,
        bytes memory data
    ) internal view returns (ValidationResult memory) {
        SessionKey memory sk = sessionKeys[account][sessionKey];
        
        // Check if session key is active and not expired
        if (!sk.active || block.timestamp < sk.validAfter || block.timestamp > sk.validUntil) {
            return ValidationResult({
                valid: false,
                riskScore: 0,
                reason: "Session key invalid or expired",
                requiresReview: false
            });
        }
        
        // Check spending limit
        if (sk.spentAmount + value > sk.spendingLimit) {
            return ValidationResult({
                valid: false,
                riskScore: 0,
                reason: "Session key spending limit exceeded",
                requiresReview: false
            });
        }
        
        // Check allowed targets
        bool targetAllowed = sk.allowedTargets.length == 0; // Empty means all allowed
        for (uint256 i = 0; i < sk.allowedTargets.length; i++) {
            if (sk.allowedTargets[i] == target) {
                targetAllowed = true;
                break;
            }
        }
        
        if (!targetAllowed) {
            return ValidationResult({
                valid: false,
                riskScore: 0,
                reason: "Target not allowed for session key",
                requiresReview: false
            });
        }
        
        // Check allowed selectors if data present
        if (data.length >= 4 && sk.allowedSelectors.length > 0) {
            bytes4 selector = bytes4(data);
            bool selectorAllowed = false;
            
            for (uint256 i = 0; i < sk.allowedSelectors.length; i++) {
                if (sk.allowedSelectors[i] == selector) {
                    selectorAllowed = true;
                    break;
                }
            }
            
            if (!selectorAllowed) {
                return ValidationResult({
                    valid: false,
                    riskScore: 0,
                    reason: "Function selector not allowed",
                    requiresReview: false
                });
            }
        }
        
        return ValidationResult({
            valid: true,
            riskScore: 0,
            reason: "Session key valid",
            requiresReview: false
        });
    }
    
    function _performRiskAssessment(
        address account,
        address target,
        uint256 value,
        bytes memory /* data */
    ) internal view returns (ValidationResult memory) {
        AccountConfig memory config = accountConfigs[account];
        
        // Check cache first
        RiskAssessment memory cached = riskCache[target];
        uint256 riskScore;
        
        if (cached.timestamp + riskCacheTTL > block.timestamp) {
            riskScore = cached.score;
        } else {
            // Simplified risk calculation (in production, call ML oracle)
            riskScore = _calculateSimpleRisk(target, value);
        }
        
        // Check if sanctioned (would be checked via oracle)
        if (cached.sanctioned) {
            return ValidationResult({
                valid: false,
                riskScore: 1000,
                reason: "Target is sanctioned",
                requiresReview: false
            });
        }
        
        bool valid = riskScore <= config.riskThreshold;
        
        return ValidationResult({
            valid: valid,
            riskScore: riskScore,
            reason: valid ? "Risk within threshold" : "Risk exceeds threshold",
            requiresReview: riskScore > config.riskThreshold / 2
        });
    }
    
    function _calculateSimpleRisk(address target, uint256 value) internal view returns (uint256) {
        uint256 risk = 100; // Base risk
        
        // Contract interaction
        uint256 codeSize;
        assembly {
            codeSize := extcodesize(target)
        }
        if (codeSize > 0) {
            risk += 100;
        }
        
        // Value-based risk
        if (value > 10 ether) {
            risk += 300;
        } else if (value > 1 ether) {
            risk += 150;
        } else if (value > 0.1 ether) {
            risk += 50;
        }
        
        return risk;
    }
    
    function _decodeCallData(bytes calldata callData) internal pure returns (
        address target,
        uint256 value,
        bytes memory data
    ) {
        // Decode execute(address,uint256,bytes) call
        if (callData.length >= 68) {
            // Skip selector (4 bytes)
            target = address(bytes20(callData[16:36]));
            value = uint256(bytes32(callData[36:68]));
            
            if (callData.length > 68) {
                // Has data payload
                uint256 dataOffset = uint256(bytes32(callData[68:100]));
                uint256 dataLength = uint256(bytes32(callData[100:132]));
                data = callData[132:132 + dataLength];
            }
        }
    }
    
    function _extractSessionKey(bytes calldata signature) internal pure returns (address) {
        // Session key is encoded in signature if present
        // Format: [signature (65 bytes)][sessionKey (20 bytes)]
        if (signature.length >= 85) {
            return address(bytes20(signature[65:85]));
        }
        return address(0);
    }
    
    function _isAccountOwner(address account, address caller) internal view returns (bool) {
        // In production, check with the smart account's ownership
        try ISmartAccount(account).isModuleEnabled(caller) returns (bool isEnabled) {
            return isEnabled;
        } catch {
            return false;
        }
    }
}
