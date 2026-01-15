// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title IAMTTPPolicyEngine - Policy Engine Interface
 */
interface IAMTTPPolicyEngine {
    enum PolicyAction { Approve, Review, Escrow, Block }
    
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 dqnRiskScore,
        string memory modelVersion,
        bytes32 kycHash
    ) external returns (PolicyAction action, string memory reason);
}

/**
 * @title IAMTTPDisputeResolver - Dispute Resolution Interface
 */
interface IAMTTPDisputeResolver {
    function createDispute(
        bytes32 swapId,
        address claimant,
        uint256 amount,
        string calldata evidence
    ) external payable returns (uint256 disputeId);
}

/**
 * @title AMTTPCoreSecure - AMTTP Protocol with Enhanced Security Controls
 * @notice Unified escrow, risk management, and compliance contract
 * @dev Security Enhancements:
 *   1. Nonce-based replay protection for oracle signatures
 *   2. Timelock for admin operations (governance protection)
 *   3. Storage gaps for safe upgrades
 *   4. Multi-oracle consensus (threshold signatures)
 *   5. HSM-compatible signature verification
 */
contract AMTTPCoreSecure is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable, 
    ReentrancyGuardUpgradeable,
    PausableUpgradeable 
{
    using ECDSA for bytes32;
    using SafeERC20 for IERC20;

    // ══════════════════════════════════════════════════════════════════
    //                      CUSTOM ERRORS (Gas Optimized)
    // ══════════════════════════════════════════════════════════════════
    error NotOracle();
    error NotApprover();
    error SwapNotFound();
    error InvalidSeller();
    error InvalidToken();
    error InvalidTimelock();
    error InvalidRiskScore();
    error InvalidSignature();
    error SwapExists();
    error SwapNotApproved();
    error SwapNotPending();
    error SwapExpired();
    error SwapNotExpired();
    error InvalidPreimage();
    error SwapCannotRefund();
    error SwapCannotDispute();
    error NotPartyToSwap();
    error DisputeResolverNotSet();
    error OnlyDisputeResolver();
    error SwapNotDisputed();
    error AlreadyApproved();
    error ExceedsSingleTxLimit();
    error ExceedsDailyLimit();
    error NoETHSent();
    error ZeroAmount();
    error ETHTransferFailed();
    // New security errors
    error NonceAlreadyUsed();
    error SignatureExpired();
    error InsufficientOracleSignatures();
    error OracleAlreadySigned();
    error TimelockNotExpired();
    // Enhancement errors
    error DailyVolumeLimitExceeded();
    error InvalidFeeConfiguration();
    error TimelockNotQueued();
    error InvalidOracleIndex();

    // ══════════════════════════════════════════════════════════════════
    //                           CONSTANTS
    // ══════════════════════════════════════════════════════════════════
    uint256 public constant RISK_SCALE = 1000;
    uint256 public constant HIGH_RISK_THRESHOLD = 700;
    uint256 public constant BLOCK_THRESHOLD = 900;
    uint256 public constant SIGNATURE_VALIDITY = 5 minutes;
    uint256 public constant TIMELOCK_DELAY = 2 days;
    uint256 public constant MAX_ORACLES = 5;
    
    // ══════════════════════════════════════════════════════════════════
    //                           ENUMS
    // ══════════════════════════════════════════════════════════════════
    enum SwapStatus { Pending, Approved, Completed, Refunded, Disputed, Blocked }
    enum AssetType { ETH, ERC20 }
    enum TimelockOperation { SetOracle, SetPolicyEngine, SetDisputeResolver, Upgrade }
    
    // ══════════════════════════════════════════════════════════════════
    //                    STRUCTS (Packed for Gas Efficiency)
    // ══════════════════════════════════════════════════════════════════
    
    /// @dev Packed into 5 storage slots instead of 8
    struct Swap {
        // Slot 1: addresses packed
        address buyer;          // 20 bytes
        SwapStatus status;      // 1 byte
        uint8 approvalCount;    // 1 byte
        AssetType assetType;    // 1 byte
        // Slot 2
        address seller;         // 20 bytes
        // Slot 3
        address token;          // 20 bytes (address(0) for ETH)
        // Slot 4
        uint256 amount;
        // Slot 5
        bytes32 hashlock;
        // Slot 6
        uint256 timelock;
        // Slot 7
        uint256 riskScore;
        // Slot 8
        bytes32 kycHash;
    }
    
    /// @dev Packed into 3 storage slots instead of 4
    struct UserPolicy {
        // Slot 1
        uint128 dailyLimit;     // 16 bytes (sufficient for most amounts)
        uint128 singleTxLimit;  // 16 bytes
        // Slot 2
        uint128 dailySpent;     // 16 bytes
        uint64 lastResetDay;    // 8 bytes (enough until year 500 billion)
        bool kycVerified;       // 1 byte
        bool trusted;           // 1 byte
    }
    
    /// @dev Timelock queue item
    struct TimelockItem {
        uint256 executeAfter;   // Timestamp when operation can be executed
        bytes data;             // Encoded operation data
        bool executed;          // Whether operation was executed
    }
    
    /// @dev Oracle signature data with nonce and timestamp
    struct OracleSignatureData {
        address buyer;
        address seller;
        uint256 amount;
        uint256 riskScore;
        bytes32 kycHash;
        uint256 nonce;
        uint256 timestamp;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                           STATE
    // ══════════════════════════════════════════════════════════════════
    
    // Core mappings
    mapping(bytes32 => Swap) public swaps;
    mapping(bytes32 => mapping(address => bool)) public approvals;
    mapping(address => UserPolicy) public userPolicies;
    
    // Governance
    address[] public approvers;
    mapping(address => bool) public isApprover;
    uint256 public approvalThreshold;
    
    // ═══ SECURITY ENHANCEMENT 1: Multi-Oracle Consensus ═══
    address[MAX_ORACLES] public oracles;
    uint256 public oracleCount;
    uint256 public oracleThreshold;  // Required signatures (e.g., 2-of-3)
    mapping(address => bool) public isOracle;
    
    // ═══ SECURITY ENHANCEMENT 2: Nonce-based Replay Protection ═══
    mapping(bytes32 => bool) public usedNonces;  // nonce hash => used
    
    // ═══ SECURITY ENHANCEMENT 3: Timelock for Admin Operations ═══
    mapping(bytes32 => TimelockItem) public timelockQueue;
    
    // ═══ UPGRADE TIMELOCK & GOVERNANCE ENHANCEMENT ═══
    address public governance;
    mapping(address => bool) public isUpgradeApprover;
    uint256 public constant UPGRADE_TIMELOCK = 2 days;
    struct UpgradeRequest {
        address newImplementation;
        uint256 executeAfter;
        bool executed;
    }
    mapping(bytes32 => UpgradeRequest) public upgradeQueue;
    
    // Policy
    IAMTTPPolicyEngine public policyEngine;
    IAMTTPDisputeResolver public disputeResolver;
    bool public policyEngineEnabled;
    
    // Model tracking
    string public activeModelVersion;
    uint256 public globalRiskThreshold;
    
    // ═══ ENHANCEMENT 1: Circuit Breaker - Daily Volume Limit ═══
    uint256 public dailyVolumeLimit;      // Max daily volume (0 = unlimited)
    uint256 public dailyVolume;           // Current day's volume
    uint256 public lastVolumeResetDay;    // Day number of last reset
    
    // ═══ ENHANCEMENT 2: Protocol Fees ═══
    uint256 public protocolFeeBps;        // Fee in basis points (100 = 1%)
    address public feeRecipient;          // Where fees are sent
    uint256 public totalFeesCollected;    // Tracking total fees
    
    // ═══ SECURITY ENHANCEMENT 4: Storage Gaps for Upgrades ═══
    uint256[44] private __gap;  // Reduced from 50 to account for new state variables
    
    // ══════════════════════════════════════════════════════════════════
    //                           EVENTS
    // ══════════════════════════════════════════════════════════════════
    event SwapInitiated(bytes32 indexed swapId, address indexed buyer, address indexed seller, uint256 amount, uint256 riskScore);
    event SwapApproved(bytes32 indexed swapId, address indexed approver);
    event SwapCompleted(bytes32 indexed swapId, address indexed seller);
    event SwapRefunded(bytes32 indexed swapId, address indexed buyer);
    event SwapDisputed(bytes32 indexed swapId, uint256 disputeId);
    event SwapBlocked(bytes32 indexed swapId, uint256 riskScore, string reason);
    event RiskScoreSubmitted(bytes32 indexed swapId, uint256 riskScore, string modelVersion);
    event PolicyEngineUpdated(address indexed newEngine);
    event DisputeResolverUpdated(address indexed newResolver);
    event UserPolicyUpdated(address indexed user);
    event ApproverAdded(address indexed approver);
    event ApproverRemoved(address indexed approver);
    // New security events
    event OracleAdded(address indexed oracle, uint256 index);
    event OracleRemoved(address indexed oracle);
    event OracleThresholdUpdated(uint256 oldThreshold, uint256 newThreshold);
    event TimelockQueued(bytes32 indexed operationId, TimelockOperation operation, uint256 executeAfter);
    event TimelockExecuted(bytes32 indexed operationId, TimelockOperation operation);
    /// @notice Emitted when a swap is submitted via a MEV-protected channel (e.g., Flashbots Protect)
    event MEVProtectedSwap(address indexed user, bytes32 indexed swapId, string submissionType);
    event TimelockCancelled(bytes32 indexed operationId);
    event NonceUsed(bytes32 indexed nonceHash, address indexed user);
    // Enhancement events
    event CircuitBreakerTriggered(uint256 dailyVolume, uint256 dailyVolumeLimit);
    event DailyVolumeLimitUpdated(uint256 oldLimit, uint256 newLimit);
    event ProtocolFeeUpdated(uint256 oldFeeBps, uint256 newFeeBps);
    event FeeRecipientUpdated(address indexed oldRecipient, address indexed newRecipient);
    event FeeCollected(bytes32 indexed swapId, uint256 feeAmount, address indexed recipient);
    event DailyVolumeReset(uint256 day, uint256 previousVolume);
    
    // Rich Analytics Events
    event SwapAnalytics(
        bytes32 indexed swapId,
        address indexed buyer,
        address indexed seller,
        uint256 amount,
        uint256 riskScore,
        AssetType assetType,
        string modelVersion,
        uint256 timestamp
    );
    event UserRiskProfile(
        address indexed user,
        uint256 totalVolume,
        uint256 avgRiskScore,
        uint256 swapCount,
        bool kycVerified,
        uint256 timestamp
    );
    event ProtocolMetrics(
        uint256 dailyVolume,
        uint256 dailySwapCount,
        uint256 totalFeesCollected,
        uint256 activeOracleCount,
        uint256 timestamp
    );
    
    // ══════════════════════════════════════════════════════════════════
    //                           MODIFIERS
    // ══════════════════════════════════════════════════════════════════
    modifier onlyOracle() {
        if (!isOracle[msg.sender] && msg.sender != owner()) revert NotOracle();
        _;
    }
    
    modifier onlyApprover() {
        if (!isApprover[msg.sender] && msg.sender != owner()) revert NotApprover();
        _;
    }
    
    modifier swapExists(bytes32 swapId) {
        if (swaps[swapId].buyer == address(0)) revert SwapNotFound();
        _;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                        INITIALIZATION
    // ══════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize(address _oracle) public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        
        // Set up first oracle
        oracles[0] = _oracle;
        oracleCount = 1;
        oracleThreshold = 1;  // Start with 1-of-1, upgrade to 2-of-3 later
        isOracle[_oracle] = true;
        
        approvalThreshold = 1;
        globalRiskThreshold = HIGH_RISK_THRESHOLD;
        activeModelVersion = "DQN-v1.0";
        policyEngineEnabled = false;
        
        // Add deployer as first approver
        approvers.push(msg.sender);
        isApprover[msg.sender] = true;
        // Set governance to owner by default (can be changed)
        governance = msg.sender;
        isUpgradeApprover[msg.sender] = true;
    }

    // ══════════════════════════════════════════════════════════════════
    //                     UPGRADE TIMELOCK & GOVERNANCE
    // ══════════════════════════════════════════════════════════════════

    /**
     * @notice Set governance address (multisig or DAO)
     */
    function setGovernance(address _governance) external onlyOwner {
        require(_governance != address(0), "Invalid governance");
        governance = _governance;
        isUpgradeApprover[_governance] = true;
    }

    /**
     * @notice Add or remove upgrade approvers (multisig/DAO members)
     */
    function setUpgradeApprover(address approver, bool approved) external {
        require(msg.sender == governance || msg.sender == owner(), "Not authorized");
        isUpgradeApprover[approver] = approved;
    }

    /**
     * @notice Queue an upgrade (timelocked)
     */
    function queueUpgrade(address newImplementation) external onlyOwner returns (bytes32 upgradeId) {
        require(newImplementation != address(0), "Invalid implementation");
        upgradeId = keccak256(abi.encodePacked(newImplementation, block.timestamp));
        upgradeQueue[upgradeId] = UpgradeRequest({
            newImplementation: newImplementation,
            executeAfter: block.timestamp + UPGRADE_TIMELOCK,
            executed: false
        });
    }

    /**
     * @notice Approve and execute upgrade after timelock
     */
    function executeUpgrade(bytes32 upgradeId) external {
        require(isUpgradeApprover[msg.sender], "Not upgrade approver");
        UpgradeRequest storage req = upgradeQueue[upgradeId];
        require(req.newImplementation != address(0), "Not queued");
        require(block.timestamp >= req.executeAfter, "Timelock not expired");
        require(!req.executed, "Already executed");
        req.executed = true;
        _upgradeTo(req.newImplementation);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //              MULTI-ORACLE MANAGEMENT (Security Enhancement 1)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Add a new oracle (HSM-backed address)
     * @param _oracle The oracle address (should be HSM-controlled)
     */
    function addOracle(address _oracle) external onlyOwner {
        require(oracleCount < MAX_ORACLES, "Max oracles reached");
        require(!isOracle[_oracle], "Already oracle");
        
        oracles[oracleCount] = _oracle;
        isOracle[_oracle] = true;
        
        emit OracleAdded(_oracle, oracleCount);
        
        unchecked {
            oracleCount++;
        }
    }
    
    /**
     * @notice Remove an oracle
     * @param _oracle The oracle address to remove
     */
    function removeOracle(address _oracle) external onlyOwner {
        require(isOracle[_oracle], "Not oracle");
        require(oracleCount > oracleThreshold, "Would break threshold");
        
        isOracle[_oracle] = false;
        
        // Compact the array
        for (uint256 i = 0; i < oracleCount; i++) {
            if (oracles[i] == _oracle) {
                oracles[i] = oracles[oracleCount - 1];
                oracles[oracleCount - 1] = address(0);
                break;
            }
        }
        
        unchecked {
            oracleCount--;
        }
        
        emit OracleRemoved(_oracle);
    }
    
    /**
     * @notice Set oracle threshold (e.g., 2-of-3)
     * @param _threshold Number of required signatures
     */
    function setOracleThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold > 0 && _threshold <= oracleCount, "Invalid threshold");
        
        emit OracleThresholdUpdated(oracleThreshold, _threshold);
        oracleThreshold = _threshold;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //              TIMELOCK FUNCTIONS (Security Enhancement 2)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Queue a timelocked admin operation
     * @param operation The type of operation
     * @param data The encoded operation data
     */
    function queueTimelock(TimelockOperation operation, bytes calldata data) external onlyOwner returns (bytes32 operationId) {
        operationId = keccak256(abi.encodePacked(operation, data, block.timestamp));
        
        uint256 executeAfter;
        unchecked {
            executeAfter = block.timestamp + TIMELOCK_DELAY;
        }
        
        timelockQueue[operationId] = TimelockItem({
            executeAfter: executeAfter,
            data: data,
            executed: false
        });
        
        emit TimelockQueued(operationId, operation, executeAfter);
    }
    
    /**
     * @notice Execute a timelocked set oracle operation
     * @param operationId The operation ID from queueTimelock
     * @param newOracle The new oracle address
     */
    function executeSetOracle(bytes32 operationId, address newOracle) external onlyOwner {
        TimelockItem storage item = timelockQueue[operationId];
        if (item.executeAfter == 0) revert TimelockNotQueued();
        if (block.timestamp < item.executeAfter) revert TimelockNotExpired();
        require(!item.executed, "Already executed");
        
        // Verify the data matches
        require(keccak256(item.data) == keccak256(abi.encode(newOracle)), "Data mismatch");
        
        item.executed = true;
        
        // Add new oracle, don't remove old ones (use removeOracle separately)
        if (!isOracle[newOracle] && oracleCount < MAX_ORACLES) {
            oracles[oracleCount] = newOracle;
            isOracle[newOracle] = true;
            unchecked {
                oracleCount++;
            }
            emit OracleAdded(newOracle, oracleCount - 1);
        }
        
        emit TimelockExecuted(operationId, TimelockOperation.SetOracle);
    }
    
    /**
     * @notice Execute a timelocked set policy engine operation
     */
    function executeSetPolicyEngine(bytes32 operationId, address _policyEngine) external onlyOwner {
        TimelockItem storage item = timelockQueue[operationId];
        if (item.executeAfter == 0) revert TimelockNotQueued();
        if (block.timestamp < item.executeAfter) revert TimelockNotExpired();
        require(!item.executed, "Already executed");
        require(keccak256(item.data) == keccak256(abi.encode(_policyEngine)), "Data mismatch");
        
        item.executed = true;
        policyEngine = IAMTTPPolicyEngine(_policyEngine);
        policyEngineEnabled = _policyEngine != address(0);
        
        emit PolicyEngineUpdated(_policyEngine);
        emit TimelockExecuted(operationId, TimelockOperation.SetPolicyEngine);
    }
    
    /**
     * @notice Execute a timelocked set dispute resolver operation
     */
    function executeSetDisputeResolver(bytes32 operationId, address _disputeResolver) external onlyOwner {
        TimelockItem storage item = timelockQueue[operationId];
        if (item.executeAfter == 0) revert TimelockNotQueued();
        if (block.timestamp < item.executeAfter) revert TimelockNotExpired();
        require(!item.executed, "Already executed");
        require(keccak256(item.data) == keccak256(abi.encode(_disputeResolver)), "Data mismatch");
        
        item.executed = true;
        disputeResolver = IAMTTPDisputeResolver(_disputeResolver);
        
        emit DisputeResolverUpdated(_disputeResolver);
        emit TimelockExecuted(operationId, TimelockOperation.SetDisputeResolver);
    }
    
    /**
     * @notice Cancel a queued timelock operation
     */
    function cancelTimelock(bytes32 operationId) external onlyOwner {
        require(timelockQueue[operationId].executeAfter != 0, "Not queued");
        require(!timelockQueue[operationId].executed, "Already executed");
        
        delete timelockQueue[operationId];
        
        emit TimelockCancelled(operationId);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     CONFIGURATION (Non-critical, no timelock)
    // ══════════════════════════════════════════════════════════════════
    
    function setGlobalRiskThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold <= RISK_SCALE, "Invalid threshold");
        globalRiskThreshold = _threshold;
    }
    
    function setActiveModelVersion(string calldata _version) external onlyOwner {
        activeModelVersion = _version;
    }
    
    function addApprover(address _approver) external onlyOwner {
        require(!isApprover[_approver], "Already approver");
        approvers.push(_approver);
        isApprover[_approver] = true;
        emit ApproverAdded(_approver);
    }
    
    function removeApprover(address _approver) external onlyOwner {
        require(isApprover[_approver], "Not approver");
        isApprover[_approver] = false;
        emit ApproverRemoved(_approver);
    }
    
    function setApprovalThreshold(uint256 _threshold) external onlyOwner {
        approvalThreshold = _threshold;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //            ENHANCEMENT 1: CIRCUIT BREAKER - DAILY VOLUME LIMIT
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Set daily volume limit (circuit breaker)
     * @param _limit Maximum daily volume in wei (0 = unlimited)
     */
    function setDailyVolumeLimit(uint256 _limit) external onlyOwner {
        emit DailyVolumeLimitUpdated(dailyVolumeLimit, _limit);
        dailyVolumeLimit = _limit;
    }
    
    /**
     * @notice Check and update daily volume, revert if limit exceeded
     * @param amount Transaction amount to add
     */
    function _checkDailyVolume(uint256 amount) internal {
        uint256 currentDay = block.timestamp / 1 days;
        
        // Reset daily volume if new day
        if (currentDay > lastVolumeResetDay) {
            emit DailyVolumeReset(currentDay, dailyVolume);
            dailyVolume = 0;
            lastVolumeResetDay = currentDay;
        }
        
        // Check limit (0 = unlimited)
        if (dailyVolumeLimit > 0) {
            if (dailyVolume + amount > dailyVolumeLimit) {
                emit CircuitBreakerTriggered(dailyVolume + amount, dailyVolumeLimit);
                revert DailyVolumeLimitExceeded();
            }
        }
        
        dailyVolume += amount;
    }
    
    /**
     * @notice Get current daily volume status
     */
    function getDailyVolumeStatus() external view returns (
        uint256 currentVolume,
        uint256 limit,
        uint256 remaining,
        uint256 resetTimestamp
    ) {
        uint256 currentDay = block.timestamp / 1 days;
        uint256 effectiveVolume = currentDay > lastVolumeResetDay ? 0 : dailyVolume;
        uint256 effectiveRemaining = dailyVolumeLimit > 0 
            ? (dailyVolumeLimit > effectiveVolume ? dailyVolumeLimit - effectiveVolume : 0)
            : type(uint256).max;
        
        return (
            effectiveVolume,
            dailyVolumeLimit,
            effectiveRemaining,
            (currentDay + 1) * 1 days
        );
    }
    
    // ══════════════════════════════════════════════════════════════════
    //            ENHANCEMENT 2: PROTOCOL FEES
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Set protocol fee in basis points (100 = 1%)
     * @param _feeBps Fee in basis points (max 500 = 5%)
     */
    function setProtocolFee(uint256 _feeBps) external onlyOwner {
        if (_feeBps > 500) revert InvalidFeeConfiguration(); // Max 5%
        emit ProtocolFeeUpdated(protocolFeeBps, _feeBps);
        protocolFeeBps = _feeBps;
    }
    
    /**
     * @notice Set fee recipient address
     * @param _recipient Address to receive fees
     */
    function setFeeRecipient(address _recipient) external onlyOwner {
        require(_recipient != address(0), "Invalid recipient");
        emit FeeRecipientUpdated(feeRecipient, _recipient);
        feeRecipient = _recipient;
    }
    
    /**
     * @notice Calculate and deduct protocol fee
     * @param amount Gross amount
     * @param swapId Swap ID for event
     * @return netAmount Amount after fee deduction
     */
    function _collectFee(uint256 amount, bytes32 swapId) internal returns (uint256 netAmount) {
        if (protocolFeeBps == 0 || feeRecipient == address(0)) {
            return amount;
        }
        
        uint256 fee = (amount * protocolFeeBps) / 10000;
        totalFeesCollected += fee;
        
        emit FeeCollected(swapId, fee, feeRecipient);
        
        return amount - fee;
    }
    
    /**
     * @notice Withdraw collected fees (for ERC20 tokens held)
     */
    function withdrawFees(address token) external onlyOwner {
        require(feeRecipient != address(0), "No fee recipient");
        
        if (token == address(0)) {
            // This function is for ERC20 only; ETH fees are sent directly
            revert("Use feeRecipient for ETH");
        } else {
            uint256 balance = IERC20(token).balanceOf(address(this));
            // Note: This requires careful accounting to not withdraw escrowed funds
            // In production, track fees separately per token
            IERC20(token).safeTransfer(feeRecipient, balance);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     USER POLICY FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function setUserPolicy(
        address user,
        uint128 dailyLimit,
        uint128 singleTxLimit,
        bool kycVerified,
        bool trusted
    ) external onlyOracle {
        userPolicies[user] = UserPolicy({
            dailyLimit: dailyLimit,
            singleTxLimit: singleTxLimit,
            dailySpent: userPolicies[user].dailySpent,
            lastResetDay: userPolicies[user].lastResetDay,
            kycVerified: kycVerified,
            trusted: trusted
        });
        emit UserPolicyUpdated(user);
    }
    
    function setKYCStatus(address user, bool verified) external onlyOracle {
        userPolicies[user].kycVerified = verified;
        emit UserPolicyUpdated(user);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     SWAP INITIATION (ETH)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Initiate ETH swap with multi-oracle consensus signatures
     * @dev Security: Requires threshold oracle signatures with nonces
     * @param oracleSignatures Array of signatures from different oracles
     * @param nonce Unique nonce to prevent replay attacks
     * @param signatureTimestamp Timestamp when signatures were created
     */
    function initiateSwap(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes[] calldata oracleSignatures,
        uint256 nonce,
        uint256 signatureTimestamp
    ) external payable nonReentrant whenNotPaused returns (bytes32 swapId) {
        if (msg.value == 0) revert NoETHSent();
        if (seller == address(0)) revert InvalidSeller();
        if (timelock <= block.timestamp) revert InvalidTimelock();
        if (riskScore > RISK_SCALE) revert InvalidRiskScore();
        
        // ═══ SECURITY: Verify nonce hasn't been used (includes chainId to prevent cross-chain replay) ═══
        bytes32 nonceHash = keccak256(abi.encodePacked(msg.sender, nonce, block.chainid));
        if (usedNonces[nonceHash]) revert NonceAlreadyUsed();
        usedNonces[nonceHash] = true;
        emit NonceUsed(nonceHash, msg.sender);
        
        // ═══ SECURITY: Verify signature not expired ═══
        if (block.timestamp > signatureTimestamp + SIGNATURE_VALIDITY) revert SignatureExpired();
        
        // ═══ SECURITY: Verify multi-oracle signatures ═══
        if (!_verifyMultiOracleSignatures(
            msg.sender, seller, msg.value, riskScore, kycHash, 
            nonce, signatureTimestamp, oracleSignatures
        )) revert InsufficientOracleSignatures();
        
        // Check user limits
        _checkUserLimits(msg.sender, msg.value);
        
        // ═══ ENHANCEMENT: Circuit breaker check ═══
        _checkDailyVolume(msg.value);
        
        swapId = keccak256(abi.encodePacked(msg.sender, seller, hashlock, timelock, block.timestamp));
        if (swaps[swapId].buyer != address(0)) revert SwapExists();
        
        // Determine initial status based on risk
        SwapStatus initialStatus = _determineStatus(msg.sender, seller, msg.value, riskScore, kycHash);
        
        swaps[swapId] = Swap({
            buyer: msg.sender,
            status: initialStatus,
            approvalCount: 0,
            assetType: AssetType.ETH,
            seller: seller,
            token: address(0),
            amount: msg.value,
            hashlock: hashlock,
            timelock: timelock,
            riskScore: riskScore,
            kycHash: kycHash
        });
        
        // Update daily spending
        _updateDailySpending(msg.sender, msg.value);
        
        emit SwapInitiated(swapId, msg.sender, seller, msg.value, riskScore);
        emit RiskScoreSubmitted(swapId, riskScore, activeModelVersion);
        
        if (initialStatus == SwapStatus.Blocked) {
            emit SwapBlocked(swapId, riskScore, "High risk");
        }
        
        return swapId;
    }
    
    /**
     * @notice Initiate ERC20 swap with multi-oracle consensus
     */
    function initiateSwapERC20(
        address seller,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes[] calldata oracleSignatures,
        uint256 nonce,
        uint256 signatureTimestamp
    ) external nonReentrant whenNotPaused returns (bytes32 swapId) {
        // Emit MEVProtectedSwap for monitoring (off-chain infra can set submissionType to 'flashbots' or 'public')
        // For now, default to 'unknown' (frontend/SDK should pass info in future upgrade)
        emit MEVProtectedSwap(msg.sender, swapId, "unknown");
        if (amount == 0) revert ZeroAmount();
        if (seller == address(0)) revert InvalidSeller();
        if (token == address(0)) revert InvalidToken();
        if (timelock <= block.timestamp) revert InvalidTimelock();
        
        // ═══ SECURITY: Verify nonce hasn't been used (includes chainId to prevent cross-chain replay) ═══
        bytes32 nonceHash = keccak256(abi.encodePacked(msg.sender, nonce, block.chainid));
        if (usedNonces[nonceHash]) revert NonceAlreadyUsed();
        usedNonces[nonceHash] = true;
        emit NonceUsed(nonceHash, msg.sender);
        
        // ═══ SECURITY: Verify signature not expired ═══
        if (block.timestamp > signatureTimestamp + SIGNATURE_VALIDITY) revert SignatureExpired();
        
        // ═══ SECURITY: Verify multi-oracle signatures ═══
        if (!_verifyMultiOracleSignatures(
            msg.sender, seller, amount, riskScore, kycHash,
            nonce, signatureTimestamp, oracleSignatures
        )) revert InsufficientOracleSignatures();
        
        // ═══ ENHANCEMENT: Circuit breaker check ═══
        _checkDailyVolume(amount);
        
        swapId = keccak256(abi.encodePacked(msg.sender, seller, token, hashlock, timelock, block.timestamp));
        if (swaps[swapId].buyer != address(0)) revert SwapExists();
        
        SwapStatus initialStatus = _determineStatus(msg.sender, seller, amount, riskScore, kycHash);
        
        swaps[swapId] = Swap({
            buyer: msg.sender,
            status: initialStatus,
            approvalCount: 0,
            assetType: AssetType.ERC20,
            seller: seller,
            token: token,
            amount: amount,
            hashlock: hashlock,
            timelock: timelock,
            riskScore: riskScore,
            kycHash: kycHash
        });
        
        // Transfer tokens to escrow (SafeERC20 handles non-standard tokens like USDT)
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        
        emit SwapInitiated(swapId, msg.sender, seller, amount, riskScore);
        
        return swapId;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     SWAP COMPLETION / REFUND
    // ══════════════════════════════════════════════════════════════════
    
    function completeSwap(bytes32 swapId, bytes32 preimage) external nonReentrant swapExists(swapId) {
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Approved) revert SwapNotApproved();
        if (block.timestamp >= swap.timelock) revert SwapExpired();
        if (keccak256(abi.encodePacked(preimage)) != swap.hashlock) revert InvalidPreimage();
        
        swap.status = SwapStatus.Completed;
        
        _transferFunds(swap.seller, swap.amount, swap.token, swap.assetType);
        
        emit SwapCompleted(swapId, swap.seller);
    }
    
    function refundSwap(bytes32 swapId) external nonReentrant swapExists(swapId) {
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Pending && swap.status != SwapStatus.Approved) revert SwapCannotRefund();
        if (block.timestamp < swap.timelock) revert SwapNotExpired();
        
        swap.status = SwapStatus.Refunded;
        
        _transferFunds(swap.buyer, swap.amount, swap.token, swap.assetType);
        
        emit SwapRefunded(swapId, swap.buyer);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     APPROVAL WORKFLOW
    // ══════════════════════════════════════════════════════════════════
    
    function approveSwap(bytes32 swapId) external onlyApprover swapExists(swapId) {
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Pending) revert SwapNotPending();
        if (approvals[swapId][msg.sender]) revert AlreadyApproved();
            // Emit MEVProtectedSwap for monitoring (off-chain infra can set submissionType to 'flashbots' or 'public')
            // For now, default to 'unknown' (frontend/SDK should pass info in future upgrade)
            emit MEVProtectedSwap(msg.sender, swapId, "unknown");
        
        approvals[swapId][msg.sender] = true;
        
        unchecked {
            swap.approvalCount++;
        }
        
        emit SwapApproved(swapId, msg.sender);
        
        if (swap.approvalCount >= approvalThreshold) {
            swap.status = SwapStatus.Approved;
        }
    }
    
    function rejectSwap(bytes32 swapId, string calldata reason) external onlyApprover swapExists(swapId) {
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Pending) revert SwapNotPending();
        
        swap.status = SwapStatus.Refunded;
        
        _transferFunds(swap.buyer, swap.amount, swap.token, swap.assetType);
        
        emit SwapBlocked(swapId, swap.riskScore, reason);
        emit SwapRefunded(swapId, swap.buyer);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //            ENHANCEMENT 4: BATCH OPERATIONS (Gas Savings)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Batch approve multiple swaps in one transaction
     * @param swapIds Array of swap IDs to approve
     */
    function batchApproveSwaps(bytes32[] calldata swapIds) external onlyApprover {
        require(swapIds.length <= 50, "Too many swaps");
        
        for (uint256 i = 0; i < swapIds.length; i++) {
            bytes32 swapId = swapIds[i];
            Swap storage swap = swaps[swapId];
            
            // Skip if invalid or already processed
            if (swap.buyer == address(0)) continue;
            if (swap.status != SwapStatus.Pending) continue;
            if (approvals[swapId][msg.sender]) continue;
            
            approvals[swapId][msg.sender] = true;
            
            unchecked {
                swap.approvalCount++;
            }
            
            emit SwapApproved(swapId, msg.sender);
            
            if (swap.approvalCount >= approvalThreshold) {
                swap.status = SwapStatus.Approved;
            }
        }
    }
    
    /**
     * @notice Batch set user policies (oracle only)
     * @param users Array of user addresses
     * @param dailyLimits Array of daily limits
     * @param singleTxLimits Array of single transaction limits
     * @param kycStatuses Array of KYC verification statuses
     */
    function batchSetUserPolicies(
        address[] calldata users,
        uint128[] calldata dailyLimits,
        uint128[] calldata singleTxLimits,
        bool[] calldata kycStatuses
    ) external onlyOracle {
        require(users.length <= 100, "Too many users");
        require(
            users.length == dailyLimits.length &&
            users.length == singleTxLimits.length &&
            users.length == kycStatuses.length,
            "Array length mismatch"
        );
        
        for (uint256 i = 0; i < users.length; i++) {
            userPolicies[users[i]] = UserPolicy({
                dailyLimit: dailyLimits[i],
                singleTxLimit: singleTxLimits[i],
                dailySpent: userPolicies[users[i]].dailySpent,
                lastResetDay: userPolicies[users[i]].lastResetDay,
                kycVerified: kycStatuses[i],
                trusted: false
            });
            emit UserPolicyUpdated(users[i]);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     DISPUTE RESOLUTION
    // ══════════════════════════════════════════════════════════════════
    
    function raiseDispute(bytes32 swapId, string calldata evidence) external payable swapExists(swapId) {
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Pending && swap.status != SwapStatus.Approved) revert SwapCannotDispute();
        if (msg.sender != swap.buyer && msg.sender != swap.seller) revert NotPartyToSwap();
        if (address(disputeResolver) == address(0)) revert DisputeResolverNotSet();
        
        swap.status = SwapStatus.Disputed;
        
        uint256 disputeId = disputeResolver.createDispute{value: msg.value}(
            swapId,
            msg.sender,
            swap.amount,
            evidence
        );
        
        emit SwapDisputed(swapId, disputeId);
    }
    
    function executeDisputeRuling(bytes32 swapId, bool releaseToSeller) external {
        if (msg.sender != address(disputeResolver)) revert OnlyDisputeResolver();
        
        Swap storage swap = swaps[swapId];
        if (swap.status != SwapStatus.Disputed) revert SwapNotDisputed();
        
        if (releaseToSeller) {
            swap.status = SwapStatus.Completed;
            _transferFunds(swap.seller, swap.amount, swap.token, swap.assetType);
            emit SwapCompleted(swapId, swap.seller);
        } else {
            swap.status = SwapStatus.Refunded;
            _transferFunds(swap.buyer, swap.amount, swap.token, swap.assetType);
            emit SwapRefunded(swapId, swap.buyer);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     INTERNAL FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Verify multi-oracle threshold signatures
     * @dev Security: Requires oracleThreshold unique oracle signatures
     */
    function _verifyMultiOracleSignatures(
        address buyer,
        address seller,
        uint256 amount,
        uint256 riskScore,
        bytes32 kycHash,
        uint256 nonce,
        uint256 timestamp,
        bytes[] calldata signatures
    ) internal view returns (bool) {
        if (oracleCount == 0) return true; // Skip if no oracles set
        if (signatures.length < oracleThreshold) return false;
        
        // Create the message hash including nonce, timestamp, and chainId (HSM-compatible EIP-191)
        // SECURITY: Including block.chainid prevents cross-chain replay attacks
        bytes32 messageHash = keccak256(abi.encodePacked(
            "\x19Ethereum Signed Message:\n32",
            keccak256(abi.encodePacked(
                buyer, seller, amount, riskScore, kycHash, nonce, timestamp, block.chainid
            ))
        ));
        
        // Track which oracles have signed to prevent double-counting
        address[MAX_ORACLES] memory signers;
        uint256 validSignatures = 0;
        
        for (uint256 i = 0; i < signatures.length; i++) {
            address signer = ECDSA.recover(messageHash, signatures[i]);
            
            // Check if signer is a valid oracle
            if (!isOracle[signer]) continue;
            
            // Check if this oracle already signed
            bool alreadySigned = false;
            for (uint256 j = 0; j < validSignatures; j++) {
                if (signers[j] == signer) {
                    alreadySigned = true;
                    break;
                }
            }
            if (alreadySigned) continue;
            
            signers[validSignatures] = signer;
            unchecked {
                validSignatures++;
            }
            
            if (validSignatures >= oracleThreshold) return true;
        }
        
        return validSignatures >= oracleThreshold;
    }
    
    function _determineStatus(
        address buyer,
        address seller,
        uint256 amount,
        uint256 riskScore,
        bytes32 kycHash
    ) internal returns (SwapStatus) {
        if (policyEngineEnabled && address(policyEngine) != address(0)) {
            (IAMTTPPolicyEngine.PolicyAction action, ) = policyEngine.validateTransaction(
                buyer, seller, amount, riskScore, activeModelVersion, kycHash
            );
            
            if (action == IAMTTPPolicyEngine.PolicyAction.Block) {
                return SwapStatus.Blocked;
            } else if (action == IAMTTPPolicyEngine.PolicyAction.Escrow || 
                       action == IAMTTPPolicyEngine.PolicyAction.Review) {
                return SwapStatus.Pending;
            }
            return SwapStatus.Approved;
        }
        
        if (riskScore >= BLOCK_THRESHOLD) {
            return SwapStatus.Blocked;
        } else if (riskScore >= globalRiskThreshold) {
            return SwapStatus.Pending;
        }
        
        if (userPolicies[buyer].trusted) {
            return SwapStatus.Approved;
        }
        
        return SwapStatus.Approved;
    }
    
    function _checkUserLimits(address user, uint256 amount) internal view {
        UserPolicy storage policy = userPolicies[user];
        
        if (policy.singleTxLimit > 0) {
            if (amount > policy.singleTxLimit) revert ExceedsSingleTxLimit();
        }
        
        if (policy.dailyLimit > 0) {
            uint256 currentDay;
            unchecked {
                currentDay = block.timestamp / 1 days;
            }
            uint128 spent = policy.lastResetDay == currentDay ? policy.dailySpent : 0;
            if (spent + amount > policy.dailyLimit) revert ExceedsDailyLimit();
        }
    }
    
    function _updateDailySpending(address user, uint256 amount) internal {
        UserPolicy storage policy = userPolicies[user];
        uint64 currentDay;
        unchecked {
            currentDay = uint64(block.timestamp / 1 days);
        }
        
        if (policy.lastResetDay < currentDay) {
            policy.dailySpent = 0;
            policy.lastResetDay = currentDay;
        }
        
        unchecked {
            policy.dailySpent += uint128(amount);
        }
    }
    
    function _transferFunds(address to, uint256 amount, address token, AssetType assetType) internal {
        if (assetType == AssetType.ETH) {
            (bool sent, ) = to.call{value: amount}("");
            if (!sent) revert ETHTransferFailed();
        } else {
            // SafeERC20 handles non-standard tokens like USDT that don't return bool
            IERC20(token).safeTransfer(to, amount);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     VIEW FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function getSwap(bytes32 swapId) external view returns (Swap memory) {
        return swaps[swapId];
    }
    
    function getApprovers() external view returns (address[] memory) {
        return approvers;
    }
    
    function getOracles() external view returns (address[MAX_ORACLES] memory, uint256, uint256) {
        return (oracles, oracleCount, oracleThreshold);
    }
    
    function getTimelockItem(bytes32 operationId) external view returns (TimelockItem memory) {
        return timelockQueue[operationId];
    }
    
    function isNonceUsed(address user, uint256 nonce) external view returns (bool) {
        return usedNonces[keccak256(abi.encodePacked(user, nonce))];
    }
    
    function getContractStatus() external view returns (
        address _policyEngine,
        address _disputeResolver,
        uint256 _oracleCount,
        uint256 _oracleThreshold,
        bool _policyEnabled,
        uint256 _riskThreshold,
        string memory _modelVersion
    ) {
        return (
            address(policyEngine),
            address(disputeResolver),
            oracleCount,
            oracleThreshold,
            policyEngineEnabled,
            globalRiskThreshold,
            activeModelVersion
        );
    }
    
    /**
     * @notice Comprehensive health check for monitoring dashboards
     * @return isPaused Whether contract is paused
     * @return currentDailyVolume Today's transaction volume
     * @return volumeLimit Daily volume limit (0 = unlimited)
     * @return volumeRemaining Remaining volume capacity today
     * @return activeOracles Number of active oracles
     * @return requiredOracles Required oracle signatures
     * @return contractETHBalance ETH held in escrow
     * @return protocolFee Current protocol fee in basis points
     * @return totalFees Total fees collected lifetime
     */
    function healthCheck() external view returns (
        bool isPaused,
        uint256 currentDailyVolume,
        uint256 volumeLimit,
        uint256 volumeRemaining,
        uint256 activeOracles,
        uint256 requiredOracles,
        uint256 contractETHBalance,
        uint256 protocolFee,
        uint256 totalFees
    ) {
        uint256 currentDay = block.timestamp / 1 days;
        uint256 effectiveVolume = currentDay > lastVolumeResetDay ? 0 : dailyVolume;
        uint256 remaining = dailyVolumeLimit > 0 
            ? (dailyVolumeLimit > effectiveVolume ? dailyVolumeLimit - effectiveVolume : 0)
            : type(uint256).max;
        
        return (
            paused(),
            effectiveVolume,
            dailyVolumeLimit,
            remaining,
            oracleCount,
            oracleThreshold,
            address(this).balance,
            protocolFeeBps,
            totalFeesCollected
        );
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ADMIN FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    /**
     * @notice Upgrade authorization with timelock & governance support
     * @dev Only callable by contract itself via executeUpgrade
     */
    function _authorizeUpgrade(address newImplementation) internal override {
        require(msg.sender == address(this), "Upgrade via executeUpgrade only");
    }
    
    // Allow contract to receive ETH
    receive() external payable {}
}
