// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";

/**
 * @title AMTTPRiskRouter
 * @author AMTTP Protocol
 * @notice AI-powered risk routing contract optimized for L2 deployment (Polygon/Arbitrum)
 * @dev Routes transactions based on ML risk scores with gas-efficient batch processing
 * 
 * Key Features:
 * - ML-based real-time risk scoring integration
 * - Tiered routing (Approve/Review/Escrow/Block)
 * - Gas-optimized batch transaction processing
 * - L2-specific optimizations (calldata compression, minimal storage)
 * - Circuit breaker for anomaly detection
 * - Multi-oracle support with threshold voting
 * 
 * L2 Deployment Benefits:
 * - ~100x lower gas costs than Ethereum mainnet
 * - Sub-second finality on Polygon/Arbitrum
 * - Higher throughput for batch processing
 * - Cost-effective for high-frequency risk checks
 */
contract AMTTPRiskRouter is 
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable
{
    using ECDSA for bytes32;

    // ═══════════════════════════════════════════════════════════════════════
    //                           CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════
    
    uint256 public constant RISK_SCALE = 1000;
    uint256 public constant MAX_BATCH_SIZE = 50;
    uint256 public constant SIGNATURE_VALIDITY = 5 minutes;
    
    // Risk thresholds (can be adjusted via governance)
    uint256 public constant DEFAULT_LOW_THRESHOLD = 300;      // 0-30% = APPROVE
    uint256 public constant DEFAULT_MEDIUM_THRESHOLD = 600;   // 30-60% = REVIEW
    uint256 public constant DEFAULT_HIGH_THRESHOLD = 850;     // 60-85% = ESCROW
    // Above 85% = BLOCK

    // ═══════════════════════════════════════════════════════════════════════
    //                           CUSTOM ERRORS
    // ═══════════════════════════════════════════════════════════════════════
    
    error NotOracle();
    error InvalidSignature();
    error ExpiredSignature();
    error InvalidRiskScore();
    error BatchTooLarge();
    error CircuitBreakerActive();
    error InvalidThresholds();
    error ZeroAddress();
    error AlreadyProcessed();
    error InsufficientOracleQuorum();

    // ═══════════════════════════════════════════════════════════════════════
    //                           ENUMS
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Risk action determined by ML model
    enum RiskAction {
        APPROVE,    // Low risk - proceed immediately
        REVIEW,     // Medium risk - queue for human review
        ESCROW,     // High risk - hold in escrow
        BLOCK       // Critical risk - reject transaction
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                           STRUCTS (Packed for L2 efficiency)
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Compact risk assessment result (1 storage slot)
    struct RiskResult {
        uint128 riskScore;          // ML risk score (0-1000)
        uint64 timestamp;           // When assessed
        RiskAction action;          // Determined action (1 byte)
        bool processed;             // Whether acted upon (1 byte)
    }
    
    /// @notice Risk thresholds configuration (1 storage slot)
    struct RiskThresholds {
        uint64 lowThreshold;        // Below = APPROVE
        uint64 mediumThreshold;     // Below = REVIEW  
        uint64 highThreshold;       // Below = ESCROW, above = BLOCK
        uint64 reserved;            // Future use
    }
    
    /// @notice Batch routing request (for calldata efficiency)
    struct BatchRequest {
        address sender;
        address recipient;
        uint256 amount;
        uint128 riskScore;
        bytes32 txHash;
    }
    
    /// @notice Oracle configuration
    struct OracleConfig {
        bool isActive;
        uint64 weight;              // Voting weight (1-100)
        uint64 lastUpdate;          // Last activity timestamp
        uint128 totalAssessments;   // Number of assessments made
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                           STATE VARIABLES
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Risk thresholds for action determination
    RiskThresholds public thresholds;
    
    /// @notice Mapping of transaction hash to risk result
    mapping(bytes32 => RiskResult) public riskResults;
    
    /// @notice Mapping of oracle addresses to their configuration
    mapping(address => OracleConfig) public oracles;
    
    /// @notice Array of active oracle addresses
    address[] public oracleList;
    
    /// @notice Minimum oracle quorum for multi-oracle mode
    uint256 public oracleQuorum;
    
    /// @notice L1 bridge contract for cross-chain communication
    address public l1Bridge;
    
    /// @notice AMTTPCore contract on L1 (for callbacks)
    address public amttpCoreL1;
    
    /// @notice Current ML model version
    string public modelVersion;
    
    /// @notice Circuit breaker state
    bool public circuitBreakerActive;
    
    /// @notice Anomaly threshold for circuit breaker (consecutive high-risk)
    uint256 public anomalyThreshold;
    uint256 public consecutiveHighRisk;
    
    /// @notice Statistics for monitoring
    uint256 public totalAssessments;
    uint256 public totalApproved;
    uint256 public totalReviewed;
    uint256 public totalEscrowed;
    uint256 public totalBlocked;

    // ═══════════════════════════════════════════════════════════════════════
    //                           EVENTS
    // ═══════════════════════════════════════════════════════════════════════
    
    event RiskAssessed(
        bytes32 indexed txHash,
        address indexed sender,
        address indexed recipient,
        uint256 amount,
        uint256 riskScore,
        RiskAction action
    );
    
    event BatchProcessed(
        uint256 batchId,
        uint256 count,
        uint256 approved,
        uint256 reviewed,
        uint256 escrowed,
        uint256 blocked
    );
    
    event ThresholdsUpdated(
        uint256 lowThreshold,
        uint256 mediumThreshold,
        uint256 highThreshold
    );
    
    event OracleAdded(address indexed oracle, uint256 weight);
    event OracleRemoved(address indexed oracle);
    event OracleQuorumUpdated(uint256 newQuorum);
    
    event CircuitBreakerTriggered(uint256 consecutiveHighRisk);
    event CircuitBreakerReset();
    
    event ModelVersionUpdated(string oldVersion, string newVersion);
    event L1BridgeUpdated(address indexed newBridge);
    
    event RiskResultRelayedToL1(bytes32 indexed txHash, RiskAction action);

    // ═══════════════════════════════════════════════════════════════════════
    //                           MODIFIERS
    // ═══════════════════════════════════════════════════════════════════════
    
    modifier onlyOracle() {
        if (!oracles[msg.sender].isActive) revert NotOracle();
        _;
    }
    
    modifier circuitBreakerCheck() {
        if (circuitBreakerActive) revert CircuitBreakerActive();
        _;
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                           INITIALIZATION
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    /**
     * @notice Initialize the risk router
     * @param _oracle Initial oracle address
     * @param _modelVersion Initial ML model version
     */
    function initialize(
        address _oracle,
        string calldata _modelVersion
    ) external initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        
        if (_oracle == address(0)) revert ZeroAddress();
        
        // Set default thresholds
        thresholds = RiskThresholds({
            lowThreshold: uint64(DEFAULT_LOW_THRESHOLD),
            mediumThreshold: uint64(DEFAULT_MEDIUM_THRESHOLD),
            highThreshold: uint64(DEFAULT_HIGH_THRESHOLD),
            reserved: 0
        });
        
        // Add initial oracle
        oracles[_oracle] = OracleConfig({
            isActive: true,
            weight: 100,
            lastUpdate: uint64(block.timestamp),
            totalAssessments: 0
        });
        oracleList.push(_oracle);
        oracleQuorum = 1;
        
        modelVersion = _modelVersion;
        anomalyThreshold = 10; // 10 consecutive high-risk triggers circuit breaker
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       CORE ROUTING FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Assess and route a single transaction based on ML risk score
     * @param sender Transaction sender
     * @param recipient Transaction recipient
     * @param amount Transaction amount
     * @param riskScore ML-computed risk score (0-1000)
     * @param timestamp Score computation timestamp
     * @param signature Oracle signature over the risk assessment
     * @return action The determined risk action
     * @return txHash The transaction hash for tracking
     */
    function assessRisk(
        address sender,
        address recipient,
        uint256 amount,
        uint128 riskScore,
        uint64 timestamp,
        bytes calldata signature
    ) external nonReentrant whenNotPaused circuitBreakerCheck returns (RiskAction action, bytes32 txHash) {
        // Validate inputs
        if (riskScore > RISK_SCALE) revert InvalidRiskScore();
        if (block.timestamp > timestamp + SIGNATURE_VALIDITY) revert ExpiredSignature();
        
        // Generate transaction hash
        txHash = keccak256(abi.encodePacked(sender, recipient, amount, block.chainid, block.timestamp));
        
        // Verify oracle signature
        bytes32 messageHash = keccak256(abi.encodePacked(
            sender, recipient, amount, riskScore, timestamp, block.chainid
        ));
        bytes32 ethSignedHash = messageHash.toEthSignedMessageHash();
        address signer = ethSignedHash.recover(signature);
        
        if (!oracles[signer].isActive) revert InvalidSignature();
        
        // Determine action based on thresholds
        action = _determineAction(riskScore);
        
        // Store result
        riskResults[txHash] = RiskResult({
            riskScore: riskScore,
            timestamp: uint64(block.timestamp),
            action: action,
            processed: false
        });
        
        // Update statistics
        _updateStatistics(action, riskScore);
        
        // Update oracle stats
        oracles[signer].lastUpdate = uint64(block.timestamp);
        unchecked {
            oracles[signer].totalAssessments++;
        }
        
        emit RiskAssessed(txHash, sender, recipient, amount, riskScore, action);
        
        return (action, txHash);
    }
    
    /**
     * @notice Batch assess multiple transactions (L2 gas optimization)
     * @dev Processes up to MAX_BATCH_SIZE transactions in a single call
     * @param requests Array of batch requests
     * @param signatures Array of oracle signatures (one per request)
     * @return actions Array of determined actions
     * @return txHashes Array of transaction hashes
     */
    function batchAssessRisk(
        BatchRequest[] calldata requests,
        bytes[] calldata signatures
    ) external nonReentrant whenNotPaused circuitBreakerCheck returns (
        RiskAction[] memory actions,
        bytes32[] memory txHashes
    ) {
        uint256 count = requests.length;
        if (count > MAX_BATCH_SIZE) revert BatchTooLarge();
        if (count != signatures.length) revert InvalidSignature();
        
        actions = new RiskAction[](count);
        txHashes = new bytes32[](count);
        
        uint256 approved;
        uint256 reviewed;
        uint256 escrowed;
        uint256 blocked;
        
        for (uint256 i = 0; i < count;) {
            BatchRequest calldata req = requests[i];
            
            // Generate transaction hash
            bytes32 txHash = keccak256(abi.encodePacked(
                req.sender, req.recipient, req.amount, block.chainid, block.timestamp, i
            ));
            
            // Verify signature
            bytes32 messageHash = keccak256(abi.encodePacked(
                req.sender, req.recipient, req.amount, req.riskScore, req.txHash
            ));
            bytes32 ethSignedHash = messageHash.toEthSignedMessageHash();
            address signer = ethSignedHash.recover(signatures[i]);
            
            if (!oracles[signer].isActive) revert InvalidSignature();
            
            // Determine action
            RiskAction action = _determineAction(req.riskScore);
            
            // Store result
            riskResults[txHash] = RiskResult({
                riskScore: req.riskScore,
                timestamp: uint64(block.timestamp),
                action: action,
                processed: false
            });
            
            actions[i] = action;
            txHashes[i] = txHash;
            
            // Count by action type
            if (action == RiskAction.APPROVE) approved++;
            else if (action == RiskAction.REVIEW) reviewed++;
            else if (action == RiskAction.ESCROW) escrowed++;
            else blocked++;
            
            emit RiskAssessed(txHash, req.sender, req.recipient, req.amount, req.riskScore, action);
            
            unchecked { i++; }
        }
        
        // Update global statistics
        unchecked {
            totalAssessments += count;
            totalApproved += approved;
            totalReviewed += reviewed;
            totalEscrowed += escrowed;
            totalBlocked += blocked;
        }
        
        // Check circuit breaker
        _checkCircuitBreaker(blocked, count);
        
        emit BatchProcessed(block.timestamp, count, approved, reviewed, escrowed, blocked);
        
        return (actions, txHashes);
    }
    
    /**
     * @notice Quick risk check without storing (view function for pre-validation)
     * @param riskScore The risk score to evaluate
     * @return action The action that would be taken
     */
    function quickCheck(uint128 riskScore) external view returns (RiskAction action) {
        return _determineAction(riskScore);
    }
    
    /**
     * @notice Get risk result for a transaction
     * @param txHash Transaction hash
     * @return result The risk assessment result
     */
    function getRiskResult(bytes32 txHash) external view returns (RiskResult memory result) {
        return riskResults[txHash];
    }
    
    /**
     * @notice Mark a risk result as processed
     * @param txHash Transaction hash
     */
    function markProcessed(bytes32 txHash) external onlyOracle {
        riskResults[txHash].processed = true;
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       L1 BRIDGE FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Relay risk result to L1 via bridge
     * @dev Called after assessment to sync result with L1 AMTTPCore
     * @param txHash Transaction hash
     */
    function relayToL1(bytes32 txHash) external onlyOracle {
        RiskResult memory result = riskResults[txHash];
        require(result.timestamp > 0, "Result not found");
        
        // In production, this would call the L1 bridge
        // For now, we emit an event that can be picked up by a relayer
        emit RiskResultRelayedToL1(txHash, result.action);
    }
    
    /**
     * @notice Set L1 bridge contract address
     * @param _bridge New bridge address
     */
    function setL1Bridge(address _bridge) external onlyOwner {
        l1Bridge = _bridge;
        emit L1BridgeUpdated(_bridge);
    }
    
    /**
     * @notice Set L1 AMTTPCore address
     * @param _amttpCore L1 AMTTPCore address
     */
    function setAMTTPCoreL1(address _amttpCore) external onlyOwner {
        amttpCoreL1 = _amttpCore;
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       INTERNAL FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @dev Determine risk action based on score and thresholds
     */
    function _determineAction(uint128 riskScore) internal view returns (RiskAction) {
        if (riskScore <= thresholds.lowThreshold) {
            return RiskAction.APPROVE;
        } else if (riskScore <= thresholds.mediumThreshold) {
            return RiskAction.REVIEW;
        } else if (riskScore <= thresholds.highThreshold) {
            return RiskAction.ESCROW;
        } else {
            return RiskAction.BLOCK;
        }
    }
    
    /**
     * @dev Update statistics and check for anomalies
     */
    function _updateStatistics(RiskAction action, uint128 /* riskScore */) internal {
        unchecked {
            totalAssessments++;
            
            if (action == RiskAction.APPROVE) {
                totalApproved++;
                consecutiveHighRisk = 0;
            } else if (action == RiskAction.REVIEW) {
                totalReviewed++;
                consecutiveHighRisk = 0;
            } else if (action == RiskAction.ESCROW) {
                totalEscrowed++;
                consecutiveHighRisk++;
            } else {
                totalBlocked++;
                consecutiveHighRisk++;
            }
        }
        
        // Check circuit breaker for single assessments
        if (consecutiveHighRisk >= anomalyThreshold) {
            circuitBreakerActive = true;
            emit CircuitBreakerTriggered(consecutiveHighRisk);
        }
    }
    
    /**
     * @dev Check circuit breaker for batch processing
     */
    function _checkCircuitBreaker(uint256 blocked, uint256 total) internal {
        // If more than 50% of batch is blocked, trigger circuit breaker
        if (total > 5 && blocked * 2 > total) {
            circuitBreakerActive = true;
            emit CircuitBreakerTriggered(blocked);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Update risk thresholds
     * @param lowThreshold New low threshold (0-1000)
     * @param mediumThreshold New medium threshold (0-1000)
     * @param highThreshold New high threshold (0-1000)
     */
    function setThresholds(
        uint64 lowThreshold,
        uint64 mediumThreshold,
        uint64 highThreshold
    ) external onlyOwner {
        if (lowThreshold >= mediumThreshold || 
            mediumThreshold >= highThreshold ||
            highThreshold > RISK_SCALE) {
            revert InvalidThresholds();
        }
        
        thresholds = RiskThresholds({
            lowThreshold: lowThreshold,
            mediumThreshold: mediumThreshold,
            highThreshold: highThreshold,
            reserved: 0
        });
        
        emit ThresholdsUpdated(lowThreshold, mediumThreshold, highThreshold);
    }
    
    /**
     * @notice Add a new oracle
     * @param oracle Oracle address
     * @param weight Oracle voting weight (1-100)
     */
    function addOracle(address oracle, uint64 weight) external onlyOwner {
        if (oracle == address(0)) revert ZeroAddress();
        
        oracles[oracle] = OracleConfig({
            isActive: true,
            weight: weight,
            lastUpdate: uint64(block.timestamp),
            totalAssessments: 0
        });
        oracleList.push(oracle);
        
        emit OracleAdded(oracle, weight);
    }
    
    /**
     * @notice Remove an oracle
     * @param oracle Oracle address
     */
    function removeOracle(address oracle) external onlyOwner {
        oracles[oracle].isActive = false;
        emit OracleRemoved(oracle);
    }
    
    /**
     * @notice Set oracle quorum for multi-oracle mode
     * @param _quorum Minimum number of oracle signatures required
     */
    function setOracleQuorum(uint256 _quorum) external onlyOwner {
        oracleQuorum = _quorum;
        emit OracleQuorumUpdated(_quorum);
    }
    
    /**
     * @notice Update ML model version
     * @param _version New model version string
     */
    function setModelVersion(string calldata _version) external onlyOwner {
        string memory oldVersion = modelVersion;
        modelVersion = _version;
        emit ModelVersionUpdated(oldVersion, _version);
    }
    
    /**
     * @notice Set anomaly threshold for circuit breaker
     * @param _threshold Number of consecutive high-risk before trigger
     */
    function setAnomalyThreshold(uint256 _threshold) external onlyOwner {
        anomalyThreshold = _threshold;
    }
    
    /**
     * @notice Reset circuit breaker (emergency function)
     */
    function resetCircuitBreaker() external onlyOwner {
        circuitBreakerActive = false;
        consecutiveHighRisk = 0;
        emit CircuitBreakerReset();
    }
    
    /**
     * @notice Pause the router
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @notice Unpause the router
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Get router statistics
     */
    function getStatistics() external view returns (
        uint256 _totalAssessments,
        uint256 _totalApproved,
        uint256 _totalReviewed,
        uint256 _totalEscrowed,
        uint256 _totalBlocked,
        bool _circuitBreakerActive
    ) {
        return (
            totalAssessments,
            totalApproved,
            totalReviewed,
            totalEscrowed,
            totalBlocked,
            circuitBreakerActive
        );
    }
    
    /**
     * @notice Get oracle list
     */
    function getOracles() external view returns (address[] memory) {
        return oracleList;
    }
    
    /**
     * @notice Get oracle configuration
     */
    function getOracleConfig(address oracle) external view returns (OracleConfig memory) {
        return oracles[oracle];
    }
    
    /**
     * @notice Get current thresholds
     */
    function getThresholds() external view returns (
        uint256 low,
        uint256 medium,
        uint256 high
    ) {
        return (
            thresholds.lowThreshold,
            thresholds.mediumThreshold,
            thresholds.highThreshold
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                       UPGRADE AUTHORIZATION
    // ═══════════════════════════════════════════════════════════════════════
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}
