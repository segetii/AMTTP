// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "./interfaces/IAMTTP.sol";

/**
 * @title IAMTTPPolicyLocal - Minimal interface for policy validation
 * @dev Lightweight interface to integrate with AMTTP without bloating the main contract
 */
interface IAMTTPPolicyLocal {
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, uint8 recommendedRiskLevel);
}

/**
 * @title AMTTPPolicyManager - Lightweight policy integration
 * @dev Manages policy validation without adding bulk to main contract
 */
contract AMTTPPolicyManager is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable,
    IAMTTPPolicy 
{
    
    // Policy engine address
    IAMTTPPolicyLocal public policyEngine;
    
    // Simple user policies
    mapping(address => uint256) public userMaxAmounts;
    mapping(address => uint256) public userRiskThresholds;
    mapping(address => bool) public trustedUsers;
    
    // Global settings
    uint256 public globalRiskThreshold;
    bool public policyEngineEnabled;
    
    // Events
    event PolicyEngineUpdated(address indexed newEngine);
    event UserPolicyUpdated(address indexed user, uint256 maxAmount, uint256 riskThreshold);
    event TrustedUserUpdated(address indexed user, bool trusted);
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize() public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        
        globalRiskThreshold = 700; // 0.70 default
        policyEngineEnabled = false;
    }
    
    /**
     * @dev Set policy engine
     */
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        policyEngine = IAMTTPPolicyLocal(_policyEngine);
        policyEngineEnabled = _policyEngine != address(0);
        emit PolicyEngineUpdated(_policyEngine);
    }
    
    /**
     * @dev Set user policy (simplified)
     */
    function setUserPolicy(
        address user,
        uint256 maxAmount,
        uint256 riskThreshold
    ) external override {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        require(riskThreshold <= 1000, "Invalid threshold");
        
        userMaxAmounts[user] = maxAmount;
        userRiskThresholds[user] = riskThreshold;
        
        emit UserPolicyUpdated(user, maxAmount, riskThreshold);
    }
    
    /**
     * @dev Set trusted user status
     */
    function setTrustedUser(address user, bool trusted) external onlyOwner {
        trustedUsers[user] = trusted;
        emit TrustedUserUpdated(user, trusted);
    }
    
    /**
     * @dev Validate transaction (main integration point)
     */
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view override returns (bool allowed, uint8 recommendedRiskLevel, string memory reason) {
        
        // Check user limits
        uint256 userMaxAmount = userMaxAmounts[user];
        if (userMaxAmount > 0 && amount > userMaxAmount) {
            return (false, 3, "Exceeds user limit");
        }
        
        // Check risk threshold
        uint256 userThreshold = userRiskThresholds[user];
        if (userThreshold == 0) userThreshold = globalRiskThreshold;
        
        // Determine risk level and actions
        if (riskScore >= 800) {
            return (false, 3, "Risk too high");
        } else if (riskScore >= userThreshold) {
            if (trustedUsers[user]) {
                return (true, 2, "High risk - trusted user");
            } else {
                return (true, 3, "High risk - escrow required");
            }
        } else if (riskScore >= 400) {
            return (true, 2, "Medium risk - review recommended");
        } else {
            return (true, 1, "Low risk - approved");
        }
    }
    
    /**
     * @dev Check if transaction would be allowed
     */
    function isTransactionAllowed(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view override returns (bool) {
        (bool allowed,,) = this.validateTransaction(user, counterparty, amount, riskScore);
        return allowed;
    }
    
    /**
     * @dev Get user policy
     */
    function getUserPolicy(address user) external view override returns (
        uint256 maxAmount,
        uint256 riskThreshold,
        bool trusted
    ) {
        maxAmount = userMaxAmounts[user];
        riskThreshold = userRiskThresholds[user];
        if (riskThreshold == 0) riskThreshold = globalRiskThreshold;
        trusted = trustedUsers[user];
    }
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}