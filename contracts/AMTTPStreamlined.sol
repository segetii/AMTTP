// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";

/**
 * @title AMTTPPolicyManager Interface
 */
interface IAMTTPPolicyManager {
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, uint8 recommendedRiskLevel, string memory reason);
}

/**
 * @title AMTTP - Anti-Money Transfer Transfer Protocol
 * @dev Main contract with integrated fraud protection and policy validation
 */
contract AMTTP is 
    Initializable, 
    ERC20Upgradeable, 
    OwnableUpgradeable, 
    UUPSUpgradeable, 
    PausableUpgradeable,
    ReentrancyGuardUpgradeable 
{
    
    // Core Components
    mapping(address => bool) public authorizedOracles;
    mapping(bytes32 => Transaction) public transactions;
    mapping(address => UserProfile) public userProfiles;
    mapping(address => bool) public kycVerified;
    
    // Policy integration
    IAMTTPPolicyManager public policyManager;
    bool public policyValidationEnabled;
    
    // Structs
    struct Transaction {
        address from;
        address to;
        uint256 amount;
        uint256 timestamp;
        uint256 riskScore;
        uint8 status; // 0: pending, 1: approved, 2: rejected, 3: escrowed
        bytes32 dataHash;
    }
    
    struct UserProfile {
        uint256 totalTransactions;
        uint256 totalVolume;
        uint256 lastActivity;
        uint8 reputationScore;
        bool isActive;
    }
    
    // Events
    event TransactionInitiated(bytes32 indexed txId, address indexed from, address indexed to, uint256 amount);
    event TransactionApproved(bytes32 indexed txId, uint256 riskScore);
    event TransactionRejected(bytes32 indexed txId, uint256 riskScore, string reason);
    event TransactionEscrowed(bytes32 indexed txId, uint256 riskScore);
    event RiskScoreUpdated(bytes32 indexed txId, uint256 oldScore, uint256 newScore);
    event UserProfileUpdated(address indexed user, uint8 reputationScore);
    event KYCStatusUpdated(address indexed user, bool verified);
    event OracleUpdated(address indexed oracle, bool authorized);
    event PolicyManagerUpdated(address indexed newManager);
    
    // Modifiers
    modifier onlyOracle() {
        require(authorizedOracles[msg.sender], "Not authorized oracle");
        _;
    }
    
    modifier validTransaction(bytes32 txId) {
        require(transactions[txId].from != address(0), "Transaction not found");
        _;
    }
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize(
        string memory name,
        string memory symbol,
        uint256 initialSupply
    ) public initializer {
        __ERC20_init(name, symbol);
        __Ownable_init();
        __UUPSUpgradeable_init();
        __Pausable_init();
        __ReentrancyGuard_init();
        
        _mint(msg.sender, initialSupply);
        authorizedOracles[msg.sender] = true;
        policyValidationEnabled = false;
    }
    
    /**
     * @dev Set policy manager
     */
    function setPolicyManager(address _policyManager) external onlyOwner {
        policyManager = IAMTTPPolicyManager(_policyManager);
        policyValidationEnabled = _policyManager != address(0);
        emit PolicyManagerUpdated(_policyManager);
    }
    
    /**
     * @dev Authorize/deauthorize oracle
     */
    function setOracle(address oracle, bool authorized) external onlyOwner {
        authorizedOracles[oracle] = authorized;
        emit OracleUpdated(oracle, authorized);
    }
    
    /**
     * @dev Update KYC status
     */
    function updateKYCStatus(address user, bool verified) external onlyOracle {
        kycVerified[user] = verified;
        emit KYCStatusUpdated(user, verified);
    }
    
    /**
     * @dev Initiate secure transfer
     */
    function secureTransfer(
        address to,
        uint256 amount,
        bytes32 dataHash
    ) external nonReentrant whenNotPaused returns (bytes32 txId) {
        require(to != address(0), "Invalid recipient");
        require(amount > 0, "Invalid amount");
        require(balanceOf(msg.sender) >= amount, "Insufficient balance");
        
        txId = keccak256(abi.encodePacked(msg.sender, to, amount, block.timestamp, block.number));
        
        transactions[txId] = Transaction({
            from: msg.sender,
            to: to,
            amount: amount,
            timestamp: block.timestamp,
            riskScore: 0,
            status: 0,
            dataHash: dataHash
        });
        
        emit TransactionInitiated(txId, msg.sender, to, amount);
        
        // Auto-approve if policy validation disabled or not risky
        if (!policyValidationEnabled) {
            _approveTransaction(txId, 0);
        }
        
        return txId;
    }
    
    /**
     * @dev Submit risk score and validate transaction
     */
    function submitRiskScore(
        bytes32 txId,
        uint256 riskScore
    ) external onlyOracle validTransaction(txId) {
        require(transactions[txId].status == 0, "Transaction already processed");
        
        Transaction storage txn = transactions[txId];
        uint256 oldScore = txn.riskScore;
        txn.riskScore = riskScore;
        
        emit RiskScoreUpdated(txId, oldScore, riskScore);
        
        // Validate with policy manager if enabled
        if (policyValidationEnabled && address(policyManager) != address(0)) {
            (bool allowed, uint8 riskLevel, string memory reason) = policyManager.validateTransaction(
                txn.from,
                txn.to,
                txn.amount,
                riskScore
            );
            
            if (!allowed) {
                _rejectTransaction(txId, reason);
            } else if (riskLevel >= 3) {
                _escrowTransaction(txId);
            } else {
                _approveTransaction(txId, riskScore);
            }
        } else {
            // Fallback validation
            if (riskScore >= 800) {
                _rejectTransaction(txId, "High risk");
            } else if (riskScore >= 600) {
                _escrowTransaction(txId);
            } else {
                _approveTransaction(txId, riskScore);
            }
        }
    }
    
    /**
     * @dev Approve transaction
     */
    function _approveTransaction(bytes32 txId, uint256 riskScore) internal {
        Transaction storage txn = transactions[txId];
        txn.status = 1;
        
        // Execute transfer
        _transfer(txn.from, txn.to, txn.amount);
        
        // Update user profiles
        _updateUserProfile(txn.from, txn.amount, true);
        _updateUserProfile(txn.to, txn.amount, false);
        
        emit TransactionApproved(txId, riskScore);
    }
    
    /**
     * @dev Reject transaction
     */
    function _rejectTransaction(bytes32 txId, string memory reason) internal {
        transactions[txId].status = 2;
        emit TransactionRejected(txId, transactions[txId].riskScore, reason);
    }
    
    /**
     * @dev Escrow transaction for manual review
     */
    function _escrowTransaction(bytes32 txId) internal {
        Transaction storage txn = transactions[txId];
        txn.status = 3;
        
        // Lock funds (simplified - in production would use proper escrow)
        _transfer(txn.from, address(this), txn.amount);
        
        emit TransactionEscrowed(txId, txn.riskScore);
    }
    
    /**
     * @dev Release escrowed transaction
     */
    function releaseEscrow(bytes32 txId, bool approve) external onlyOracle validTransaction(txId) {
        require(transactions[txId].status == 3, "Not escrowed");
        
        Transaction storage txn = transactions[txId];
        
        if (approve) {
            _transfer(address(this), txn.to, txn.amount);
            txn.status = 1;
            _updateUserProfile(txn.from, txn.amount, true);
            _updateUserProfile(txn.to, txn.amount, false);
            emit TransactionApproved(txId, txn.riskScore);
        } else {
            _transfer(address(this), txn.from, txn.amount);
            txn.status = 2;
            emit TransactionRejected(txId, txn.riskScore, "Manual rejection");
        }
    }
    
    /**
     * @dev Update user profile
     */
    function _updateUserProfile(address user, uint256 amount, bool isSender) internal {
        UserProfile storage profile = userProfiles[user];
        profile.totalTransactions++;
        profile.totalVolume += amount;
        profile.lastActivity = block.timestamp;
        profile.isActive = true;
        
        // Simple reputation scoring
        if (profile.totalTransactions <= 10) {
            profile.reputationScore = 50;
        } else if (profile.totalTransactions <= 100) {
            profile.reputationScore = 70;
        } else {
            profile.reputationScore = 90;
        }
        
        emit UserProfileUpdated(user, profile.reputationScore);
    }
    
    /**
     * @dev Get transaction details
     */
    function getTransaction(bytes32 txId) external view returns (Transaction memory) {
        return transactions[txId];
    }
    
    /**
     * @dev Get user profile
     */
    function getUserProfile(address user) external view returns (UserProfile memory) {
        return userProfiles[user];
    }
    
    /**
     * @dev Check if user can transfer amount
     */
    function canTransfer(address user, address to, uint256 amount) external view returns (bool) {
        if (!policyValidationEnabled || address(policyManager) == address(0)) {
            return balanceOf(user) >= amount;
        }
        
        // Use current risk score estimation or 0 for check
        (bool allowed,,) = policyManager.validateTransaction(user, to, amount, 0);
        return allowed && balanceOf(user) >= amount;
    }
    
    // Administrative functions
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}