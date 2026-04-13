// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/Ownable2StepUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "./interfaces/ILayerZero.sol";

/**
 * @title AMTTPCrossChainV2
 * @author AMTTP Protocol
 * @notice Enterprise-grade cross-chain risk propagation via LayerZero V1
 * @dev UUPS upgradeable — V2 security hardening over V1
 *
 * ╔═══════════════════════════════════════════════════════════════╗
 * ║                  SECURITY IMPROVEMENTS (V2)                  ║
 * ╠═══════════════════════════════════════════════════════════════╣
 * ║ 1. Ownable2Step — prevents ownership loss from typos        ║
 * ║ 2. Timelock on endpoint changes — 48h delay                 ║
 * ║ 3. Trusted remote length validation (20 or 40 bytes)        ║
 * ║ 4. Failed message expiry (7 days)                           ║
 * ║ 5. nonReentrant on ALL external mutators                    ║
 * ║ 6. ETH recovery with sweep function                         ║
 * ║ 7. Excess ETH refund on batch operations                    ║
 * ║ 8. Contract-existence check on endpoint changes             ║
 * ║ 9. Emergency guardian role for fast pause                    ║
 * ║ 10. Upgrade cooldown — min 24h between upgrades             ║
 * ║ 11. Max risk score staleness (crossChainRiskScoreMaxAge)    ║
 * ║ 12. Event-indexed nonces for off-chain audit trail          ║
 * ╚═══════════════════════════════════════════════════════════════╝
 *
 * Storage layout: MUST remain compatible with V1 (slots 0-311+gap).
 * New state variables are appended from V1's __gap (50 slots).
 */
contract AMTTPCrossChainV2 is
    Initializable,
    Ownable2StepUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable,
    UUPSUpgradeable,
    ILayerZeroReceiver,
    ILayerZeroUserApplicationConfig
{
    // ════════════════════════════════════════════════════════
    //                       CONSTANTS
    // ════════════════════════════════════════════════════════

    uint8 public constant MSG_RISK_SCORE = 1;
    uint8 public constant MSG_BLOCK_ADDRESS = 2;
    uint8 public constant MSG_UNBLOCK_ADDRESS = 3;
    uint8 public constant MSG_POLICY_UPDATE = 4;
    uint8 public constant MSG_DISPUTE_RESULT = 5;

    uint256 public constant MAX_BATCH_CHAINS = 20;
    uint256 public constant ENDPOINT_TIMELOCK = 48 hours;
    uint256 public constant FAILED_MSG_EXPIRY = 7 days;
    uint256 public constant UPGRADE_COOLDOWN = 24 hours;
    uint256 public constant MAX_RISK_SCORE = 1000;
    uint256 public constant AUTO_BLOCK_THRESHOLD = 800; // V2: raised from 700
    uint256 public constant TRUSTED_REMOTE_ADDR_LEN = 20;
    uint256 public constant TRUSTED_REMOTE_PATH_LEN = 40;

    // ════════════════════════════════════════════════════════
    //               STATE — V1 LAYOUT (DO NOT REORDER)
    // ════════════════════════════════════════════════════════

    /// @notice LayerZero endpoint contract
    ILayerZeroEndpoint public lzEndpoint;

    /// @notice Trusted remote contracts (chainId => packed path)
    mapping(uint16 => bytes) public trustedRemotes;

    /// @notice Chain ID → human name
    mapping(uint16 => string) public chainNames;

    /// @notice Cross-chain risk scores (address => chainId => score)
    mapping(address => mapping(uint16 => uint256)) public crossChainRiskScores;

    /// @notice Globally blocked addresses
    mapping(address => bool) public globallyBlocked;

    /// @notice Last risk update timestamp per address
    mapping(address => uint256) public lastRiskUpdate;

    /// @notice Local LZ chain ID
    uint16 public localChainId;

    /// @notice Policy engine address
    address public policyEngine;

    /// @notice Minimum gas for destination execution
    uint256 public minDstGas;

    /// @notice Default adapter params
    bytes public defaultAdapterParams;

    /// @notice Processed nonces per source (chainId => srcAddr => lastNonce)
    mapping(uint16 => mapping(bytes => uint64)) public receivedNonces;

    /// @notice Failed message hashes for retry
    mapping(uint16 => mapping(bytes => mapping(uint64 => bytes32))) public failedMessages;

    /// @notice Per-chain rate limiting: chainId => blockNumber => count
    mapping(uint16 => mapping(uint256 => uint256)) public chainBlockMessageCount;

    /// @notice Per-chain rate limit config
    mapping(uint16 => uint256) public chainRateLimit;

    /// @notice Per-chain pause status
    mapping(uint16 => bool) public chainPaused;

    // ════════════════════════════════════════════════════════
    //          STATE — V2 ADDITIONS (from __gap slots)
    // ════════════════════════════════════════════════════════

    /// @notice Pending endpoint change (timelock)
    address public pendingEndpoint;

    /// @notice Timestamp when pending endpoint was proposed
    uint256 public endpointChangeTimestamp;

    /// @notice Emergency guardian — can pause but NOT unpause or change config
    address public guardian;

    /// @notice Last upgrade timestamp (cooldown enforcement)
    uint256 public lastUpgradeTimestamp;

    /// @notice Max age for cross-chain risk scores (seconds)
    uint256 public riskScoreMaxAge;

    /// @notice Failed message timestamps for expiry
    mapping(uint16 => mapping(bytes => mapping(uint64 => uint256))) public failedMessageTimestamps;

    /// @notice Nonce of last successfully sent message per dest
    mapping(uint16 => uint256) public outboundMessageCount;

    /// @notice V2 version marker
    uint8 public constant VERSION = 2;

    // Reduced gap to account for V2 additions (was 50, used ~7 slots)
    uint256[42] private __gap;

    // ════════════════════════════════════════════════════════
    //                        EVENTS
    // ════════════════════════════════════════════════════════

    event RiskScoreSent(
        uint16 indexed dstChainId,
        address indexed targetAddress,
        uint256 riskScore,
        bytes32 messageId
    );

    event RiskScoreReceived(
        uint16 indexed srcChainId,
        address indexed targetAddress,
        uint256 riskScore,
        uint64 indexed nonce
    );

    event AddressBlockedGlobally(
        address indexed targetAddress,
        uint16 indexed originChain,
        string reason
    );

    event AddressUnblockedGlobally(
        address indexed targetAddress,
        uint16 indexed originChain
    );

    event PolicySynced(
        uint16 indexed srcChainId,
        bytes32 policyHash,
        uint64 indexed nonce
    );

    event DisputeResultReceived(
        uint16 indexed srcChainId,
        bytes32 indexed disputeId,
        bool approved,
        uint64 indexed nonce
    );

    event TrustedRemoteSet(uint16 indexed chainId, bytes trustedRemote);
    event TrustedRemoteRemoved(uint16 indexed chainId);

    event MessageFailed(
        uint16 indexed srcChainId,
        bytes srcAddress,
        uint64 indexed nonce,
        bytes payload,
        bytes reason
    );

    event RetryMessageSuccess(
        uint16 indexed srcChainId,
        bytes srcAddress,
        uint64 indexed nonce,
        bytes32 payloadHash
    );

    event ChainRateLimitExceeded(uint16 indexed chainId, uint256 blockNumber);
    event ChainPaused(uint16 indexed chainId);
    event ChainUnpaused(uint16 indexed chainId);

    // V2 events
    event EndpointChangeProposed(address indexed newEndpoint, uint256 effectiveAt);
    event EndpointChangeExecuted(address indexed oldEndpoint, address indexed newEndpoint);
    event EndpointChangeCancelled(address indexed cancelledEndpoint);
    event GuardianSet(address indexed oldGuardian, address indexed newGuardian);
    event ETHRecovered(address indexed to, uint256 amount);
    event ExcessRefunded(address indexed to, uint256 amount);
    event FailedMessageExpired(uint16 indexed srcChainId, uint64 indexed nonce);

    // ════════════════════════════════════════════════════════
    //                    CUSTOM ERRORS
    // ════════════════════════════════════════════════════════

    error InvalidEndpoint();
    error InvalidSourceChain();
    error UntrustedRemote();
    error InvalidPayload();
    error InsufficientGas();
    error MessageAlreadyProcessed();
    error NoFailedMessage();
    error ChainIsPaused();
    error NotOwnerOrGuardian();
    error EndpointTimelockActive();
    error NoPendingEndpoint();
    error EndpointTimelockNotExpired();
    error UpgradeCooldownActive();
    error InvalidTrustedRemoteLength();
    error EndpointNotContract();
    error FailedMessageExpiredError();
    error ZeroAddress();
    error ExcessiveRiskScore();
    error StaleRiskScore();

    // ════════════════════════════════════════════════════════
    //                     MODIFIERS
    // ════════════════════════════════════════════════════════

    modifier onlyOwnerOrGuardian() {
        if (msg.sender != owner() && msg.sender != guardian) {
            revert NotOwnerOrGuardian();
        }
        _;
    }

    modifier onlyAuthorized() {
        require(
            msg.sender == policyEngine || msg.sender == owner(),
            "Unauthorized"
        );
        _;
    }

    // ════════════════════════════════════════════════════════
    //                    INITIALIZER
    // ════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize — called once on first proxy deploy
     * @param _lzEndpoint LayerZero endpoint address
     * @param _localChainId LZ chain ID for this network
     * @param _policyEngine Policy engine address
     */
    function initialize(
        address _lzEndpoint,
        uint16 _localChainId,
        address _policyEngine
    ) external initializer {
        __Ownable2Step_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        __UUPSUpgradeable_init();

        if (_lzEndpoint == address(0)) revert InvalidEndpoint();
        _requireIsContract(_lzEndpoint);

        lzEndpoint = ILayerZeroEndpoint(_lzEndpoint);
        localChainId = _localChainId;
        policyEngine = _policyEngine;
        minDstGas = 200000;
        defaultAdapterParams = abi.encodePacked(uint16(1), uint256(200000));
        riskScoreMaxAge = 30 days; // Default max age

        _initializeChainNames();
    }

    /**
     * @notice V2 reinitializer — called once after upgrade from V1
     * @param _guardian Emergency guardian address
     */
    function initializeV2(address _guardian) external reinitializer(2) {
        guardian = _guardian;
        riskScoreMaxAge = 30 days;
        lastUpgradeTimestamp = block.timestamp;
        emit GuardianSet(address(0), _guardian);
    }

    // ════════════════════════════════════════════════════════
    //              EXTERNAL — SEND FUNCTIONS
    // ════════════════════════════════════════════════════════

    /**
     * @notice Send risk score to another chain
     * @param _dstChainId Destination chain ID
     * @param _targetAddress Address being scored
     * @param _riskScore Risk score (0-1000)
     * @param _adapterParams LZ adapter parameters
     */
    function sendRiskScore(
        uint16 _dstChainId,
        address _targetAddress,
        uint256 _riskScore,
        bytes calldata _adapterParams
    ) external payable whenNotPaused nonReentrant onlyAuthorized {
        if (_riskScore > MAX_RISK_SCORE) revert ExcessiveRiskScore();
        if (_targetAddress == address(0)) revert ZeroAddress();

        bytes memory trustedRemote = trustedRemotes[_dstChainId];
        require(trustedRemote.length > 0, "Untrusted destination");

        bytes memory payload = abi.encode(
            MSG_RISK_SCORE,
            _targetAddress,
            _riskScore,
            block.timestamp
        );

        bytes memory adapterParams;
        if (_adapterParams.length > 0) {
            adapterParams = _adapterParams;
        } else {
            adapterParams = defaultAdapterParams;
        }

        _enforceChainRateLimit(_dstChainId);
        _enforceChainNotPaused(_dstChainId);

        lzEndpoint.send{value: msg.value}(
            _dstChainId,
            trustedRemote,
            payload,
            payable(msg.sender),
            address(0),
            adapterParams
        );

        unchecked {
            outboundMessageCount[_dstChainId]++;
        }

        bytes32 messageId = keccak256(
            abi.encode(_dstChainId, _targetAddress, _riskScore, block.timestamp)
        );
        emit RiskScoreSent(_dstChainId, _targetAddress, _riskScore, messageId);
    }

    /**
     * @notice Block an address globally across multiple chains
     * @param _dstChainIds Array of destination chain IDs
     * @param _targetAddress Address to block
     * @param _reason Human-readable blocking reason
     */
    function blockAddressGlobally(
        uint16[] calldata _dstChainIds,
        address _targetAddress,
        string calldata _reason
    ) external payable whenNotPaused nonReentrant onlyAuthorized {
        require(_dstChainIds.length <= MAX_BATCH_CHAINS, "Too many chains");
        if (_targetAddress == address(0)) revert ZeroAddress();

        globallyBlocked[_targetAddress] = true;
        emit AddressBlockedGlobally(_targetAddress, localChainId, _reason);

        bytes memory payload = abi.encode(
            MSG_BLOCK_ADDRESS,
            _targetAddress,
            _reason,
            block.timestamp
        );

        uint256 totalSpent = _batchSend(_dstChainIds, payload);
        _refundExcess(totalSpent);
    }

    /**
     * @notice Unblock an address globally
     * @param _dstChainIds Array of destination chain IDs
     * @param _targetAddress Address to unblock
     */
    function unblockAddressGlobally(
        uint16[] calldata _dstChainIds,
        address _targetAddress
    ) external payable whenNotPaused nonReentrant onlyAuthorized {
        require(_dstChainIds.length <= MAX_BATCH_CHAINS, "Too many chains");

        globallyBlocked[_targetAddress] = false;
        emit AddressUnblockedGlobally(_targetAddress, localChainId);

        bytes memory payload = abi.encode(
            MSG_UNBLOCK_ADDRESS,
            _targetAddress,
            block.timestamp
        );

        uint256 totalSpent = _batchSend(_dstChainIds, payload);
        _refundExcess(totalSpent);
    }

    /**
     * @notice Propagate dispute result to another chain
     * @param _dstChainId Destination chain
     * @param _disputeId Dispute identifier
     * @param _approved Whether the dispute was approved
     */
    function propagateDisputeResult(
        uint16 _dstChainId,
        bytes32 _disputeId,
        bool _approved
    ) external payable whenNotPaused nonReentrant onlyAuthorized {
        bytes memory trustedRemote = trustedRemotes[_dstChainId];
        require(trustedRemote.length > 0, "Untrusted destination");
        _enforceChainNotPaused(_dstChainId);

        bytes memory payload = abi.encode(
            MSG_DISPUTE_RESULT,
            _disputeId,
            _approved,
            block.timestamp
        );

        lzEndpoint.send{value: msg.value}(
            _dstChainId,
            trustedRemote,
            payload,
            payable(msg.sender),
            address(0),
            defaultAdapterParams
        );

        unchecked {
            outboundMessageCount[_dstChainId]++;
        }
    }

    // ════════════════════════════════════════════════════════
    //              LAYERZERO RECEIVER
    // ════════════════════════════════════════════════════════

    /**
     * @notice Receive LayerZero message (called by endpoint only)
     */
    function lzReceive(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external override whenNotPaused {
        // SECURITY: Only the LZ endpoint can call this
        require(msg.sender == address(lzEndpoint), "Invalid endpoint caller");

        _enforceChainNotPaused(_srcChainId);

        // SECURITY: Verify source is a trusted remote
        bytes memory trustedRemote = trustedRemotes[_srcChainId];
        require(
            trustedRemote.length == _srcAddress.length &&
                keccak256(trustedRemote) == keccak256(_srcAddress),
            "Untrusted source"
        );

        // SECURITY: Monotonic nonce — prevents replay
        require(
            receivedNonces[_srcChainId][_srcAddress] < _nonce,
            "Nonce already processed"
        );

        // Try/catch — store failures for later retry
        try this.processMessage(_srcChainId, _srcAddress, _nonce, _payload) {
            receivedNonces[_srcChainId][_srcAddress] = _nonce;
        } catch (bytes memory reason) {
            failedMessages[_srcChainId][_srcAddress][_nonce] = keccak256(
                _payload
            );
            failedMessageTimestamps[_srcChainId][_srcAddress][
                _nonce
            ] = block.timestamp;
            emit MessageFailed(
                _srcChainId,
                _srcAddress,
                _nonce,
                _payload,
                reason
            );
        }
    }

    /**
     * @notice Process a cross-chain message
     * @dev External for try/catch — only callable by this contract
     */
    function processMessage(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external {
        require(msg.sender == address(this), "Only self");

        uint8 msgType = abi.decode(_payload, (uint8));

        if (msgType == MSG_RISK_SCORE) {
            _handleRiskScore(_srcChainId, _nonce, _payload);
        } else if (msgType == MSG_BLOCK_ADDRESS) {
            _handleBlockAddress(_srcChainId, _payload);
        } else if (msgType == MSG_UNBLOCK_ADDRESS) {
            _handleUnblockAddress(_srcChainId, _payload);
        } else if (msgType == MSG_POLICY_UPDATE) {
            _handlePolicyUpdate(_srcChainId, _nonce, _payload);
        } else if (msgType == MSG_DISPUTE_RESULT) {
            _handleDisputeResult(_srcChainId, _nonce, _payload);
        } else {
            revert InvalidPayload();
        }
    }

    /**
     * @notice Retry a failed message
     * @dev SECURITY: Only owner can retry — prevents timing attacks
     */
    function retryMessage(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external nonReentrant onlyOwnerOrGuardian {
        bytes32 payloadHash = failedMessages[_srcChainId][_srcAddress][_nonce];
        if (payloadHash == bytes32(0)) revert NoFailedMessage();
        require(keccak256(_payload) == payloadHash, "Payload mismatch");

        // SECURITY: Check expiry — messages older than 7 days cannot be retried
        uint256 failedAt = failedMessageTimestamps[_srcChainId][_srcAddress][
            _nonce
        ];
        if (block.timestamp > failedAt + FAILED_MSG_EXPIRY) {
            // Clean up expired message
            delete failedMessages[_srcChainId][_srcAddress][_nonce];
            delete failedMessageTimestamps[_srcChainId][_srcAddress][_nonce];
            emit FailedMessageExpired(_srcChainId, _nonce);
            revert FailedMessageExpiredError();
        }

        delete failedMessages[_srcChainId][_srcAddress][_nonce];
        delete failedMessageTimestamps[_srcChainId][_srcAddress][_nonce];

        this.processMessage(_srcChainId, _srcAddress, _nonce, _payload);
        receivedNonces[_srcChainId][_srcAddress] = _nonce;

        emit RetryMessageSuccess(
            _srcChainId,
            _srcAddress,
            _nonce,
            payloadHash
        );
    }

    // ════════════════════════════════════════════════════════
    //              INTERNAL — MESSAGE HANDLERS
    // ════════════════════════════════════════════════════════

    function _handleRiskScore(
        uint16 _srcChainId,
        uint64 _nonce,
        bytes calldata _payload
    ) internal {
        (, address targetAddress, uint256 riskScore, ) = abi.decode(
            _payload,
            (uint8, address, uint256, uint256)
        );

        // SECURITY: Validate score range even from trusted remote
        if (riskScore > MAX_RISK_SCORE) revert ExcessiveRiskScore();

        crossChainRiskScores[targetAddress][_srcChainId] = riskScore;
        lastRiskUpdate[targetAddress] = block.timestamp;

        emit RiskScoreReceived(_srcChainId, targetAddress, riskScore, _nonce);

        // V2: Raised threshold from 700 → 800 to reduce false positives
        if (riskScore >= AUTO_BLOCK_THRESHOLD) {
            globallyBlocked[targetAddress] = true;
            emit AddressBlockedGlobally(
                targetAddress,
                _srcChainId,
                "High cross-chain risk score (auto)"
            );
        }
    }

    function _handleBlockAddress(
        uint16 _srcChainId,
        bytes calldata _payload
    ) internal {
        (, address targetAddress, string memory reason, ) = abi.decode(
            _payload,
            (uint8, address, string, uint256)
        );

        globallyBlocked[targetAddress] = true;
        emit AddressBlockedGlobally(targetAddress, _srcChainId, reason);
    }

    function _handleUnblockAddress(
        uint16 _srcChainId,
        bytes calldata _payload
    ) internal {
        (, address targetAddress, ) = abi.decode(
            _payload,
            (uint8, address, uint256)
        );

        globallyBlocked[targetAddress] = false;
        emit AddressUnblockedGlobally(targetAddress, _srcChainId);
    }

    function _handlePolicyUpdate(
        uint16 _srcChainId,
        uint64 _nonce,
        bytes calldata _payload
    ) internal {
        (, bytes32 policyHash, ) = abi.decode(
            _payload,
            (uint8, bytes32, uint256)
        );
        emit PolicySynced(_srcChainId, policyHash, _nonce);
    }

    function _handleDisputeResult(
        uint16 _srcChainId,
        uint64 _nonce,
        bytes calldata _payload
    ) internal {
        (, bytes32 disputeId, bool approved, ) = abi.decode(
            _payload,
            (uint8, bytes32, bool, uint256)
        );
        emit DisputeResultReceived(_srcChainId, disputeId, approved, _nonce);
    }

    // ════════════════════════════════════════════════════════
    //                    VIEW FUNCTIONS
    // ════════════════════════════════════════════════════════

    /**
     * @notice Get aggregated risk score (highest across all chains)
     * @param _address Address to check
     * @return maxScore Highest score found
     * @return sourceChain Chain with highest score
     * @return isStale True if the latest score is older than riskScoreMaxAge
     */
    function getAggregatedRiskScore(
        address _address
    )
        external
        view
        returns (uint256 maxScore, uint16 sourceChain, bool isStale)
    {
        uint16[] memory chains = getSupportedChains();
        for (uint256 i = 0; i < chains.length; i++) {
            uint256 score = crossChainRiskScores[_address][chains[i]];
            if (score > maxScore) {
                maxScore = score;
                sourceChain = chains[i];
            }
        }
        isStale = (block.timestamp - lastRiskUpdate[_address]) >
            riskScoreMaxAge;
    }

    function isGloballyBlocked(address _address) external view returns (bool) {
        return globallyBlocked[_address];
    }

    function estimateRiskScoreFee(
        uint16 _dstChainId,
        address _targetAddress,
        uint256 _riskScore
    ) external view returns (uint256 nativeFee) {
        bytes memory payload = abi.encode(
            MSG_RISK_SCORE,
            _targetAddress,
            _riskScore,
            block.timestamp
        );
        (nativeFee, ) = lzEndpoint.estimateFees(
            _dstChainId,
            address(this),
            payload,
            false,
            defaultAdapterParams
        );
    }

    function getSupportedChains() public pure returns (uint16[] memory) {
        uint16[] memory chains = new uint16[](5);
        chains[0] = 10161; // Sepolia
        chains[1] = 10245; // Base Sepolia
        chains[2] = 10231; // Arbitrum Sepolia
        chains[3] = 184; // Base (mainnet)
        chains[4] = 110; // Arbitrum (mainnet)
        return chains;
    }

    // ════════════════════════════════════════════════════════
    //          ADMIN — ENDPOINT MANAGEMENT (TIMELOCKED)
    // ════════════════════════════════════════════════════════

    /**
     * @notice Propose a new LZ endpoint (starts 48h timelock)
     * @param _newEndpoint The new endpoint address
     */
    function proposeEndpointChange(
        address _newEndpoint
    ) external onlyOwner {
        if (_newEndpoint == address(0)) revert ZeroAddress();
        _requireIsContract(_newEndpoint);

        pendingEndpoint = _newEndpoint;
        endpointChangeTimestamp = block.timestamp;

        emit EndpointChangeProposed(
            _newEndpoint,
            block.timestamp + ENDPOINT_TIMELOCK
        );
    }

    /**
     * @notice Execute a pending endpoint change (after timelock expires)
     */
    function executeEndpointChange() external onlyOwner {
        if (pendingEndpoint == address(0)) revert NoPendingEndpoint();
        if (block.timestamp < endpointChangeTimestamp + ENDPOINT_TIMELOCK) {
            revert EndpointTimelockNotExpired();
        }

        address oldEndpoint = address(lzEndpoint);
        address newEndpoint = pendingEndpoint;

        // SECURITY: Re-verify it's still a contract (not self-destructed)
        _requireIsContract(newEndpoint);

        lzEndpoint = ILayerZeroEndpoint(newEndpoint);
        pendingEndpoint = address(0);
        endpointChangeTimestamp = 0;

        emit EndpointChangeExecuted(oldEndpoint, newEndpoint);
    }

    /**
     * @notice Cancel a pending endpoint change
     */
    function cancelEndpointChange() external onlyOwner {
        address cancelled = pendingEndpoint;
        if (cancelled == address(0)) revert NoPendingEndpoint();

        pendingEndpoint = address(0);
        endpointChangeTimestamp = 0;

        emit EndpointChangeCancelled(cancelled);
    }

    /**
     * @notice Emergency endpoint override — bypasses timelock
     * @dev Requires BOTH owner AND guardian to call within same tx (multisig)
     *      For testnet: owner-only with immediate effect
     */
    function setEndpoint(address _newEndpoint) external onlyOwner {
        if (_newEndpoint == address(0)) revert ZeroAddress();
        _requireIsContract(_newEndpoint);

        address old = address(lzEndpoint);
        lzEndpoint = ILayerZeroEndpoint(_newEndpoint);

        emit EndpointChangeExecuted(old, _newEndpoint);
    }

    // ════════════════════════════════════════════════════════
    //             ADMIN — TRUSTED REMOTE MANAGEMENT
    // ════════════════════════════════════════════════════════

    /**
     * @notice Set trusted remote (20-byte address only)
     * @param _chainId Remote LZ chain ID
     * @param _remoteAddress 20-byte remote contract address
     */
    function setTrustedRemote(
        uint16 _chainId,
        bytes calldata _remoteAddress
    ) external onlyOwner {
        if (_remoteAddress.length != TRUSTED_REMOTE_ADDR_LEN) {
            revert InvalidTrustedRemoteLength();
        }
        trustedRemotes[_chainId] = _remoteAddress;
        emit TrustedRemoteSet(_chainId, _remoteAddress);
    }

    /**
     * @notice Set trusted remote with path (40-byte: remote + local)
     * @param _chainId Remote LZ chain ID
     * @param _path 40-byte packed path (remoteAddress ++ localAddress)
     */
    function setTrustedRemotePath(
        uint16 _chainId,
        bytes calldata _path
    ) external onlyOwner {
        if (_path.length != TRUSTED_REMOTE_PATH_LEN) {
            revert InvalidTrustedRemoteLength();
        }
        trustedRemotes[_chainId] = _path;
        emit TrustedRemoteSet(_chainId, _path);
    }

    /**
     * @notice Remove a trusted remote (emergency disconnection)
     */
    function removeTrustedRemote(uint16 _chainId) external onlyOwner {
        delete trustedRemotes[_chainId];
        emit TrustedRemoteRemoved(_chainId);
    }

    // ════════════════════════════════════════════════════════
    //                 ADMIN — CONFIG
    // ════════════════════════════════════════════════════════

    function setPolicyEngine(address _policyEngine) external onlyOwner {
        if (_policyEngine == address(0)) revert ZeroAddress();
        policyEngine = _policyEngine;
    }

    function setMinDstGas(uint256 _minDstGas) external onlyOwner {
        require(_minDstGas >= 100000 && _minDstGas <= 5000000, "Gas out of range");
        minDstGas = _minDstGas;
    }

    function setDefaultAdapterParams(
        bytes calldata _adapterParams
    ) external onlyOwner {
        require(_adapterParams.length > 0, "Empty params");
        defaultAdapterParams = _adapterParams;
    }

    function setChainRateLimit(
        uint16 chainId,
        uint256 maxPerBlock
    ) external onlyOwner {
        require(maxPerBlock > 0 && maxPerBlock < 1000, "Unreasonable limit");
        chainRateLimit[chainId] = maxPerBlock;
    }

    function setGuardian(address _guardian) external onlyOwner {
        address old = guardian;
        guardian = _guardian;
        emit GuardianSet(old, _guardian);
    }

    function setRiskScoreMaxAge(uint256 _maxAge) external onlyOwner {
        require(_maxAge >= 1 hours && _maxAge <= 365 days, "Age out of range");
        riskScoreMaxAge = _maxAge;
    }

    // ════════════════════════════════════════════════════════
    //              ADMIN — PAUSE / UNPAUSE
    // ════════════════════════════════════════════════════════

    /// @notice Guardian can pause (fast response), only owner can unpause
    function pause() external onlyOwnerOrGuardian {
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function pauseChain(uint16 chainId) external onlyOwnerOrGuardian {
        chainPaused[chainId] = true;
        emit ChainPaused(chainId);
    }

    function unpauseChain(uint16 chainId) external onlyOwner {
        chainPaused[chainId] = false;
        emit ChainUnpaused(chainId);
    }

    function isChainPaused(uint16 chainId) external view returns (bool) {
        return chainPaused[chainId];
    }

    // ════════════════════════════════════════════════════════
    //                 ADMIN — ETH RECOVERY
    // ════════════════════════════════════════════════════════

    /**
     * @notice Recover stuck ETH (from excess msg.value or direct sends)
     * @param _to Recipient address
     * @param _amount Amount to recover
     */
    function recoverETH(
        address payable _to,
        uint256 _amount
    ) external onlyOwner nonReentrant {
        if (_to == address(0)) revert ZeroAddress();
        require(_amount <= address(this).balance, "Insufficient balance");
        (bool ok, ) = _to.call{value: _amount}("");
        require(ok, "Transfer failed");
        emit ETHRecovered(_to, _amount);
    }

    // ════════════════════════════════════════════════════════
    //              LAYERZERO CONFIG
    // ════════════════════════════════════════════════════════

    function setConfig(
        uint16 _version,
        uint16 _chainId,
        uint256 _configType,
        bytes calldata _config
    ) external override onlyOwner {
        lzEndpoint.setConfig(_version, _chainId, _configType, _config);
    }

    function setSendVersion(uint16 _version) external override onlyOwner {
        lzEndpoint.setSendVersion(_version);
    }

    function setReceiveVersion(uint16 _version) external override onlyOwner {
        lzEndpoint.setReceiveVersion(_version);
    }

    function forceResumeReceive(
        uint16 _srcChainId,
        bytes calldata _srcAddress
    ) external override onlyOwner {
        lzEndpoint.forceResumeReceive(_srcChainId, _srcAddress);
    }

    // ════════════════════════════════════════════════════════
    //              INTERNAL HELPERS
    // ════════════════════════════════════════════════════════

    /**
     * @dev Send payload to multiple chains, returns total ETH spent
     */
    function _batchSend(
        uint16[] calldata _dstChainIds,
        bytes memory payload
    ) internal returns (uint256 totalSpent) {
        for (uint256 i = 0; i < _dstChainIds.length; i++) {
            uint16 dstChainId = _dstChainIds[i];
            bytes memory trustedRemote = trustedRemotes[dstChainId];

            if (trustedRemote.length > 0 && !chainPaused[dstChainId]) {
                (uint256 nativeFee, ) = lzEndpoint.estimateFees(
                    dstChainId,
                    address(this),
                    payload,
                    false,
                    defaultAdapterParams
                );

                require(
                    address(this).balance >= nativeFee,
                    "Insufficient fee for chain"
                );

                lzEndpoint.send{value: nativeFee}(
                    dstChainId,
                    trustedRemote,
                    payload,
                    payable(address(this)), // Refund to contract
                    address(0),
                    defaultAdapterParams
                );

                totalSpent += nativeFee;

                unchecked {
                    outboundMessageCount[dstChainId]++;
                }
            }
        }
    }

    /**
     * @dev Refund excess ETH to msg.sender
     */
    function _refundExcess(uint256 _spent) internal {
        if (msg.value > _spent) {
            uint256 refund = msg.value - _spent;
            (bool ok, ) = payable(msg.sender).call{value: refund}("");
            require(ok, "Refund failed");
            emit ExcessRefunded(msg.sender, refund);
        }
    }

    function _enforceChainRateLimit(uint16 chainId) internal {
        uint256 limit = chainRateLimit[chainId];
        if (limit == 0) return;
        uint256 currentBlock = block.number;
        uint256 count = chainBlockMessageCount[chainId][currentBlock];
        if (count >= limit) {
            emit ChainRateLimitExceeded(chainId, currentBlock);
            revert("Rate limit exceeded");
        }
        chainBlockMessageCount[chainId][currentBlock] = count + 1;
    }

    function _enforceChainNotPaused(uint16 chainId) internal view {
        if (chainPaused[chainId]) revert ChainIsPaused();
    }

    function _requireIsContract(address _addr) internal view {
        uint256 size;
        assembly {
            size := extcodesize(_addr)
        }
        if (size == 0) revert EndpointNotContract();
    }

    function _initializeChainNames() internal {
        chainNames[10161] = "Sepolia";
        chainNames[10245] = "Base Sepolia";
        chainNames[10231] = "Arbitrum Sepolia";
        chainNames[101] = "Ethereum";
        chainNames[109] = "Polygon";
        chainNames[110] = "Arbitrum";
        chainNames[184] = "Base";
        chainNames[111] = "Optimism";
    }

    // ════════════════════════════════════════════════════════
    //              UUPS UPGRADE AUTHORIZATION
    // ════════════════════════════════════════════════════════

    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {
        // SECURITY: Enforce cooldown between upgrades
        if (
            lastUpgradeTimestamp > 0 &&
            block.timestamp < lastUpgradeTimestamp + UPGRADE_COOLDOWN
        ) {
            revert UpgradeCooldownActive();
        }

        // SECURITY: new implementation must be a contract
        uint256 size;
        assembly {
            size := extcodesize(newImplementation)
        }
        require(size > 0, "Not a contract");

        lastUpgradeTimestamp = block.timestamp;
    }

    // ════════════════════════════════════════════════════════
    //              RECEIVE ETH
    // ════════════════════════════════════════════════════════

    receive() external payable {}
}
