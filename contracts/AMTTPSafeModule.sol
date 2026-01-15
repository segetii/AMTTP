// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";
import "./interfaces/ISafe.sol";

/**
 * @title AMTTPSafeModule
 * @notice Safe (Gnosis) module for AMTTP transaction risk assessment
 * @dev Integrates AMTTP PolicyEngine with Safe multisig wallets for institutional compliance
 * 
 * Features:
 * - Pre-transaction risk assessment via AMTTP ML engine
 * - Configurable risk thresholds per Safe
 * - Transaction queuing for high-risk operations
 * - Multi-signature override for blocked transactions
 * - Compliance audit logging
 */
contract AMTTPSafeModule is Ownable, ReentrancyGuard, Pausable, IGuard, IModule {
    
    // ============ Constants ============
    uint256 public constant RISK_PRECISION = 1000; // Risk scores 0-1000
    uint256 public constant DEFAULT_HIGH_RISK_THRESHOLD = 700;
    uint256 public constant DEFAULT_BLOCK_THRESHOLD = 900;
    uint256 public constant MAX_QUEUE_TIME = 7 days;
    
    // ============ Enums ============
    enum TransactionStatus { Pending, Approved, Blocked, Executed, Expired }
    enum RiskAction { Allow, Queue, Block }
    
    // ============ Structs ============
    struct SafeConfig {
        bool enabled;
        uint256 highRiskThreshold;      // Queue for review
        uint256 blockThreshold;         // Auto-block
        uint256 dailyLimit;             // Daily volume limit
        uint256 singleTxLimit;          // Single transaction limit
        bool requiresMLCheck;           // Require ML risk assessment
        bool autoApproveWhitelisted;    // Auto-approve whitelisted addresses
        address[] operators;            // Authorized operators
    }
    
    struct QueuedTransaction {
        bytes32 txHash;
        address safe;
        address to;
        uint256 value;
        bytes data;
        uint8 operation;
        uint256 riskScore;
        uint256 queuedAt;
        uint256 approvalCount;
        TransactionStatus status;
        string riskReason;
    }
    
    struct DailyVolume {
        uint256 volume;
        uint256 lastResetDay;
    }
    
    struct AuditLog {
        bytes32 txHash;
        address safe;
        uint256 riskScore;
        RiskAction action;
        uint256 timestamp;
        string reason;
    }
    
    // ============ State Variables ============
    
    // AMTTP Integration
    address public policyEngine;
    address public mlOracleService;
    
    // Safe configurations
    mapping(address => SafeConfig) public safeConfigs;
    mapping(address => bool) public registeredSafes;
    
    // Transaction queue
    mapping(bytes32 => QueuedTransaction) public queuedTransactions;
    mapping(address => bytes32[]) public safeQueuedTxs;
    
    // Volume tracking
    mapping(address => DailyVolume) public dailyVolumes;
    
    // Whitelist/Blacklist per Safe
    mapping(address => mapping(address => bool)) public whitelist;
    mapping(address => mapping(address => bool)) public blacklist;
    
    // Approvals for queued transactions
    mapping(bytes32 => mapping(address => bool)) public txApprovals;
    
    // Audit trail
    AuditLog[] public auditLogs;
    mapping(address => uint256[]) public safeAuditIndexes;
    
    // ============ Events ============
    event SafeRegistered(address indexed safe, address[] operators);
    event SafeConfigUpdated(address indexed safe, uint256 highRiskThreshold, uint256 blockThreshold);
    event TransactionQueued(bytes32 indexed txHash, address indexed safe, uint256 riskScore, string reason);
    event TransactionApproved(bytes32 indexed txHash, address indexed approver);
    event TransactionBlocked(bytes32 indexed txHash, address indexed safe, uint256 riskScore, string reason);
    event TransactionExecuted(bytes32 indexed txHash, address indexed safe, bool success);
    event WhitelistUpdated(address indexed safe, address indexed target, bool status);
    event BlacklistUpdated(address indexed safe, address indexed target, bool status);
    event PolicyEngineUpdated(address indexed newEngine);
    event MLOracleUpdated(address indexed newOracle);
    
    // ============ Modifiers ============
    modifier onlySafeOperator(address safe) {
        require(isOperator(safe, msg.sender), "Not authorized operator");
        _;
    }
    
    modifier onlyRegisteredSafe(address safe) {
        require(registeredSafes[safe], "Safe not registered");
        _;
    }
    
    // ============ Constructor ============
    constructor(address _policyEngine, address _mlOracle) {
        require(_policyEngine != address(0), "Invalid policy engine");
        policyEngine = _policyEngine;
        mlOracleService = _mlOracle;
    }
    
    // ============ Safe Registration ============
    
    /**
     * @notice Register a Safe with AMTTP module
     * @param safe Address of the Safe wallet
     * @param operators Array of authorized operators
     * @param config Initial configuration
     */
    function registerSafe(
        address safe,
        address[] calldata operators,
        SafeConfig calldata config
    ) external {
        require(!registeredSafes[safe], "Safe already registered");
        require(safe != address(0), "Invalid safe address");
        require(operators.length > 0, "Need at least one operator");
        
        // Verify caller is Safe owner or module is enabled
        require(
            IGnosisSafe(safe).isOwner(msg.sender) || 
            IGnosisSafe(safe).isModuleEnabled(address(this)),
            "Not authorized"
        );
        
        registeredSafes[safe] = true;
        safeConfigs[safe] = SafeConfig({
            enabled: config.enabled,
            highRiskThreshold: config.highRiskThreshold > 0 ? config.highRiskThreshold : DEFAULT_HIGH_RISK_THRESHOLD,
            blockThreshold: config.blockThreshold > 0 ? config.blockThreshold : DEFAULT_BLOCK_THRESHOLD,
            dailyLimit: config.dailyLimit,
            singleTxLimit: config.singleTxLimit,
            requiresMLCheck: config.requiresMLCheck,
            autoApproveWhitelisted: config.autoApproveWhitelisted,
            operators: operators
        });
        
        emit SafeRegistered(safe, operators);
    }
    
    /**
     * @notice Update Safe configuration
     */
    function updateSafeConfig(
        address safe,
        SafeConfig calldata config
    ) external onlySafeOperator(safe) onlyRegisteredSafe(safe) {
        safeConfigs[safe] = config;
        emit SafeConfigUpdated(safe, config.highRiskThreshold, config.blockThreshold);
    }
    
    // ============ IGuard Implementation ============
    
    /**
     * @notice Pre-transaction guard check (called by Safe before execution)
     */
    function checkTransaction(
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address refundReceiver,
        bytes memory signatures,
        address msgSender
    ) external override {
        address safe = msg.sender;
        
        if (!registeredSafes[safe] || !safeConfigs[safe].enabled) {
            return; // Skip if not registered or disabled
        }
        
        // Check blacklist
        require(!blacklist[safe][to], "Recipient blacklisted");
        
        // Check daily volume
        _checkDailyVolume(safe, value);
        
        // Check single transaction limit
        SafeConfig memory config = safeConfigs[safe];
        if (config.singleTxLimit > 0) {
            require(value <= config.singleTxLimit, "Exceeds single tx limit");
        }
        
        // Auto-approve whitelisted if enabled
        if (config.autoApproveWhitelisted && whitelist[safe][to]) {
            _logAudit(bytes32(0), safe, 0, RiskAction.Allow, "Whitelisted recipient");
            return;
        }
        
        // Get risk assessment
        if (config.requiresMLCheck && mlOracleService != address(0)) {
            (uint256 riskScore, string memory reason) = _getRiskAssessment(safe, to, value, data);
            
            bytes32 txHash = keccak256(abi.encodePacked(safe, to, value, data, block.timestamp));
            
            if (riskScore >= config.blockThreshold) {
                // Block high-risk transaction
                _logAudit(txHash, safe, riskScore, RiskAction.Block, reason);
                emit TransactionBlocked(txHash, safe, riskScore, reason);
                revert("Transaction blocked: high risk");
            } else if (riskScore >= config.highRiskThreshold) {
                // Queue for review
                _queueTransaction(txHash, safe, to, value, data, operation, riskScore, reason);
                revert("Transaction queued: elevated risk");
            }
            
            _logAudit(txHash, safe, riskScore, RiskAction.Allow, reason);
        }
    }
    
    /**
     * @notice Post-transaction check
     */
    function checkAfterExecution(bytes32 txHash, bool success) external override {
        // Log execution result
        emit TransactionExecuted(txHash, msg.sender, success);
    }
    
    // ============ IModule Implementation ============
    
    /**
     * @notice Execute an approved queued transaction
     */
    function execute(
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation
    ) external override onlyRegisteredSafe(msg.sender) returns (bool success) {
        address safe = msg.sender;
        bytes32 txHash = keccak256(abi.encodePacked(safe, to, value, data, block.timestamp));
        
        QueuedTransaction storage queuedTx = queuedTransactions[txHash];
        require(queuedTx.status == TransactionStatus.Approved, "Transaction not approved");
        
        queuedTx.status = TransactionStatus.Executed;
        
        success = IGnosisSafe(safe).execTransactionFromModule(to, value, data, operation);
        
        emit TransactionExecuted(txHash, safe, success);
    }
    
    /**
     * @notice Execute approved queued transaction by hash
     */
    function executeQueuedTransaction(bytes32 txHash) external nonReentrant returns (bool) {
        QueuedTransaction storage queuedTx = queuedTransactions[txHash];
        require(queuedTx.status == TransactionStatus.Approved, "Transaction not approved");
        require(block.timestamp <= queuedTx.queuedAt + MAX_QUEUE_TIME, "Transaction expired");
        
        address safe = queuedTx.safe;
        require(isOperator(safe, msg.sender), "Not authorized");
        
        queuedTx.status = TransactionStatus.Executed;
        
        bool success = IGnosisSafe(safe).execTransactionFromModule(
            queuedTx.to,
            queuedTx.value,
            queuedTx.data,
            queuedTx.operation
        );
        
        emit TransactionExecuted(txHash, safe, success);
        return success;
    }
    
    // ============ Queued Transaction Management ============
    
    /**
     * @notice Approve a queued transaction
     */
    function approveQueuedTransaction(bytes32 txHash) external {
        QueuedTransaction storage queuedTx = queuedTransactions[txHash];
        require(queuedTx.status == TransactionStatus.Pending, "Invalid status");
        require(isOperator(queuedTx.safe, msg.sender), "Not authorized");
        require(!txApprovals[txHash][msg.sender], "Already approved");
        
        txApprovals[txHash][msg.sender] = true;
        queuedTx.approvalCount++;
        
        emit TransactionApproved(txHash, msg.sender);
        
        // Check if enough approvals (require >50% of operators)
        uint256 requiredApprovals = (safeConfigs[queuedTx.safe].operators.length + 1) / 2;
        if (queuedTx.approvalCount >= requiredApprovals) {
            queuedTx.status = TransactionStatus.Approved;
        }
    }
    
    /**
     * @notice Reject a queued transaction
     */
    function rejectQueuedTransaction(bytes32 txHash) external {
        QueuedTransaction storage queuedTx = queuedTransactions[txHash];
        require(queuedTx.status == TransactionStatus.Pending, "Invalid status");
        require(isOperator(queuedTx.safe, msg.sender), "Not authorized");
        
        queuedTx.status = TransactionStatus.Blocked;
        emit TransactionBlocked(txHash, queuedTx.safe, queuedTx.riskScore, "Rejected by operator");
    }
    
    /**
     * @notice Get queued transactions for a Safe
     */
    function getQueuedTransactions(address safe) external view returns (bytes32[] memory) {
        return safeQueuedTxs[safe];
    }
    
    // ============ Whitelist/Blacklist Management ============
    
    function addToWhitelist(address safe, address target) external onlySafeOperator(safe) {
        whitelist[safe][target] = true;
        emit WhitelistUpdated(safe, target, true);
    }
    
    function removeFromWhitelist(address safe, address target) external onlySafeOperator(safe) {
        whitelist[safe][target] = false;
        emit WhitelistUpdated(safe, target, false);
    }
    
    function addToBlacklist(address safe, address target) external onlySafeOperator(safe) {
        blacklist[safe][target] = true;
        emit BlacklistUpdated(safe, target, true);
    }
    
    function removeFromBlacklist(address safe, address target) external onlySafeOperator(safe) {
        blacklist[safe][target] = false;
        emit BlacklistUpdated(safe, target, false);
    }
    
    // ============ View Functions ============
    
    function isOperator(address safe, address account) public view returns (bool) {
        address[] memory operators = safeConfigs[safe].operators;
        for (uint256 i = 0; i < operators.length; i++) {
            if (operators[i] == account) return true;
        }
        // Safe owners are also operators
        return IGnosisSafe(safe).isOwner(account);
    }
    
    function getAuditLogs(address safe, uint256 limit) external view returns (AuditLog[] memory) {
        uint256[] memory indexes = safeAuditIndexes[safe];
        uint256 count = indexes.length < limit ? indexes.length : limit;
        AuditLog[] memory logs = new AuditLog[](count);
        
        for (uint256 i = 0; i < count; i++) {
            logs[i] = auditLogs[indexes[indexes.length - 1 - i]];
        }
        
        return logs;
    }
    
    // ============ Admin Functions ============
    
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        require(_policyEngine != address(0), "Invalid address");
        policyEngine = _policyEngine;
        emit PolicyEngineUpdated(_policyEngine);
    }
    
    function setMLOracle(address _mlOracle) external onlyOwner {
        mlOracleService = _mlOracle;
        emit MLOracleUpdated(_mlOracle);
    }
    
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    // ============ Internal Functions ============
    
    function _queueTransaction(
        bytes32 txHash,
        address safe,
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation,
        uint256 riskScore,
        string memory reason
    ) internal {
        queuedTransactions[txHash] = QueuedTransaction({
            txHash: txHash,
            safe: safe,
            to: to,
            value: value,
            data: data,
            operation: operation,
            riskScore: riskScore,
            queuedAt: block.timestamp,
            approvalCount: 0,
            status: TransactionStatus.Pending,
            riskReason: reason
        });
        
        safeQueuedTxs[safe].push(txHash);
        
        emit TransactionQueued(txHash, safe, riskScore, reason);
    }
    
    function _checkDailyVolume(address safe, uint256 value) internal {
        DailyVolume storage dv = dailyVolumes[safe];
        uint256 currentDay = block.timestamp / 1 days;
        
        if (dv.lastResetDay < currentDay) {
            dv.volume = 0;
            dv.lastResetDay = currentDay;
        }
        
        uint256 limit = safeConfigs[safe].dailyLimit;
        if (limit > 0) {
            require(dv.volume + value <= limit, "Daily limit exceeded");
        }
        
        dv.volume += value;
    }
    
    function _getRiskAssessment(
        address safe,
        address to,
        uint256 value,
        bytes memory data
    ) internal view returns (uint256 riskScore, string memory reason) {
        // In production, this would call the ML oracle service
        // For now, return a simulated risk score based on simple heuristics
        
        // Check if recipient is a contract
        uint256 codeSize;
        assembly {
            codeSize := extcodesize(to)
        }
        
        riskScore = 100; // Base score
        reason = "Standard transaction";
        
        // Large value transactions
        if (value > 10 ether) {
            riskScore += 200;
            reason = "High value transaction";
        } else if (value > 1 ether) {
            riskScore += 100;
            reason = "Medium value transaction";
        }
        
        // Contract interaction
        if (codeSize > 0 && data.length > 0) {
            riskScore += 150;
            reason = "Contract interaction";
        }
        
        // New address check would require historical data
        // This is placeholder for ML integration
        
        return (riskScore, reason);
    }
    
    function _logAudit(
        bytes32 txHash,
        address safe,
        uint256 riskScore,
        RiskAction action,
        string memory reason
    ) internal {
        uint256 index = auditLogs.length;
        auditLogs.push(AuditLog({
            txHash: txHash,
            safe: safe,
            riskScore: riskScore,
            action: action,
            timestamp: block.timestamp,
            reason: reason
        }));
        safeAuditIndexes[safe].push(index);
    }
}
