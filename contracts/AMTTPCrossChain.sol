// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "./interfaces/ILayerZero.sol";

/**
 * @title AMTTPCrossChain
 * @dev Cross-chain risk scoring and policy enforcement using LayerZero
 * @notice Enables AMTTP to propagate risk scores and block malicious addresses across chains
 * 
 * Architecture:
 * 
 *   Ethereum (Source)              Polygon (Destination)
 *   ┌─────────────────┐            ┌─────────────────┐
 *   │ AMTTPCrossChain │  ──LZ──▶   │ AMTTPCrossChain │
 *   │                 │            │                 │
 *   │ • Risk Scores   │            │ • Receive Score │
 *   │ • Block Lists   │            │ • Apply Policy  │
 *   │ • Policy Sync   │            │ • Emit Events   │
 *   └─────────────────┘            └─────────────────┘
 *          │                              │
 *          ▼                              ▼
 *   ┌─────────────────┐            ┌─────────────────┐
 *   │ PolicyEngine    │            │ PolicyEngine    │
 *   └─────────────────┘            └─────────────────┘
 */
contract AMTTPCrossChain is 
    Initializable,
    OwnableUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable,
    UUPSUpgradeable,
    ILayerZeroReceiver,
    ILayerZeroUserApplicationConfig
{
    // ============ Constants ============
    
    // Message types for cross-chain communication
    uint8 public constant MSG_RISK_SCORE = 1;
    uint8 public constant MSG_BLOCK_ADDRESS = 2;
    uint8 public constant MSG_UNBLOCK_ADDRESS = 3;
    uint8 public constant MSG_POLICY_UPDATE = 4;
    uint8 public constant MSG_DISPUTE_RESULT = 5;
    
    // Maximum number of chains for batch operations (prevents DoS via unbounded loops)
    uint256 public constant MAX_BATCH_CHAINS = 20;
    
    // ============ State Variables ============
    
    /// @notice LayerZero endpoint contract
    ILayerZeroEndpoint public lzEndpoint;
    
    /// @notice Trusted remote contracts on other chains (chainId => address)
    mapping(uint16 => bytes) public trustedRemotes;
    
    /// @notice Mapping of chain IDs to human-readable names
    mapping(uint16 => string) public chainNames;
    
    /// @notice Cross-chain risk scores (address => chainId => riskScore)
    mapping(address => mapping(uint16 => uint256)) public crossChainRiskScores;
    
    /// @notice Global blocked addresses (propagated across all chains)
    mapping(address => bool) public globallyBlocked;
    
    /// @notice Timestamp of last risk score update
    mapping(address => uint256) public lastRiskUpdate;
    
    /// @notice Local chain ID
    uint16 public localChainId;
    
    /// @notice Policy engine contract address
    address public policyEngine;
    
    /// @notice Minimum gas for destination execution
    uint256 public minDstGas;
    
    /// @notice Default adapter params
    bytes public defaultAdapterParams;
    
    /// @notice Message nonces for replay protection
    mapping(uint16 => mapping(bytes => uint64)) public receivedNonces;
    
    /// @notice Failed messages for retry
    mapping(uint16 => mapping(bytes => mapping(uint64 => bytes32))) public failedMessages;
    
    // ═══ PER-CHAIN RATE LIMITING ═══
    // chainId => blockNumber => count
    mapping(uint16 => mapping(uint256 => uint256)) public chainBlockMessageCount;
    // chainId => max messages per block
    mapping(uint16 => uint256) public chainRateLimit;

    // ═══ PER-CHAIN PAUSE ═══
    // chainId => paused status
    mapping(uint16 => bool) public chainPaused;

    // ============ Events ============
    
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
        uint64 nonce
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
        uint64 nonce
    );
    
    event DisputeResultReceived(
        uint16 indexed srcChainId,
        bytes32 indexed disputeId,
        bool approved,
        uint64 nonce
    );
    
    event TrustedRemoteSet(
        uint16 indexed chainId,
        bytes trustedRemote
    );
    
    event MessageFailed(
        uint16 indexed srcChainId,
        bytes srcAddress,
        uint64 nonce,
        bytes payload,
        bytes reason
    );
    
    event RetryMessageSuccess(
        uint16 indexed srcChainId,
        bytes srcAddress,
        uint64 nonce,
        bytes32 payloadHash
    );

    event ChainRateLimitExceeded(uint16 indexed chainId, uint256 blockNumber);

    event ChainPaused(uint16 indexed chainId);
    event ChainUnpaused(uint16 indexed chainId);
    
    // ============ Errors ============
    
    error InvalidEndpoint();
    error InvalidSourceChain();
    error UntrustedRemote();
    error InvalidPayload();
    error InsufficientGas();
    error MessageAlreadyProcessed();
    error NoFailedMessage();
    error ChainIsPaused();
    
    // ============ Initializer ============
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    /**
     * @notice Initialize the cross-chain contract
     * @param _lzEndpoint LayerZero endpoint address
     * @param _localChainId Local chain identifier
     * @param _policyEngine Policy engine contract address
     */
    function initialize(
        address _lzEndpoint,
        uint16 _localChainId,
        address _policyEngine
    ) external initializer {
        __Ownable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        __UUPSUpgradeable_init();
        
        if (_lzEndpoint == address(0)) revert InvalidEndpoint();
        
        lzEndpoint = ILayerZeroEndpoint(_lzEndpoint);
        localChainId = _localChainId;
        policyEngine = _policyEngine;
        minDstGas = 200000; // Default minimum gas
        
        // Set default adapter params (version 1, 200k gas)
        defaultAdapterParams = abi.encodePacked(uint16(1), uint256(200000));
        
        // Initialize chain names
        _initializeChainNames();
    }
    
    // ============ External Functions ============
    
    /**
     * @notice Send risk score to another chain
     * @param _dstChainId Destination chain ID
     * @param _targetAddress Address being scored
     * @param _riskScore Risk score (0-1000)
     * @param _adapterParams LayerZero adapter parameters
     */
    function sendRiskScore(
        uint16 _dstChainId,
        address _targetAddress,
        uint256 _riskScore,
        bytes calldata _adapterParams
    ) external payable whenNotPaused nonReentrant {
        require(msg.sender == policyEngine || msg.sender == owner(), "Unauthorized");
        require(_riskScore <= 1000, "Invalid risk score");
        
        bytes memory trustedRemote = trustedRemotes[_dstChainId];
        require(trustedRemote.length > 0, "Untrusted destination");
        
        // Encode payload
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
        
        // ═══ PER-CHAIN RATE LIMITING ═══
        // Call this before sending a cross-chain message
        _enforceChainRateLimit(_dstChainId);
        
        // ═══ PER-CHAIN PAUSE CHECK ═══
        _enforceChainNotPaused(_dstChainId);
        
        // Send via LayerZero
        lzEndpoint.send{value: msg.value}(
            _dstChainId,
            trustedRemote,
            payload,
            payable(msg.sender),
            address(0), // No ZRO payment
            adapterParams
        );
        
        bytes32 messageId = keccak256(abi.encode(
            _dstChainId,
            _targetAddress,
            _riskScore,
            block.timestamp
        ));
        
        emit RiskScoreSent(_dstChainId, _targetAddress, _riskScore, messageId);
    }
    
    /**
     * @notice Block an address globally across all chains
     * @param _dstChainIds Array of destination chain IDs
     * @param _targetAddress Address to block
     * @param _reason Reason for blocking
     */
    function blockAddressGlobally(
        uint16[] calldata _dstChainIds,
        address _targetAddress,
        string calldata _reason
    ) external payable whenNotPaused nonReentrant {
        require(msg.sender == policyEngine || msg.sender == owner(), "Unauthorized");
        // SECURITY: Prevent DoS via unbounded array
        require(_dstChainIds.length <= MAX_BATCH_CHAINS, "Too many chains");
        
        // Block locally first
        globallyBlocked[_targetAddress] = true;
        emit AddressBlockedGlobally(_targetAddress, localChainId, _reason);
        
        // Propagate to other chains
        bytes memory payload = abi.encode(
            MSG_BLOCK_ADDRESS,
            _targetAddress,
            _reason,
            block.timestamp
        );
        
        uint256 totalFee = 0;
        for (uint256 i = 0; i < _dstChainIds.length; i++) {
            uint16 dstChainId = _dstChainIds[i];
            bytes memory trustedRemote = trustedRemotes[dstChainId];
            
            if (trustedRemote.length > 0) {
                (uint256 nativeFee, ) = lzEndpoint.estimateFees(
                    dstChainId,
                    address(this),
                    payload,
                    false,
                    defaultAdapterParams
                );
                totalFee += nativeFee;
            }
        }
        
        require(msg.value >= totalFee, "Insufficient fee");
        
        // Send to all chains
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
                
                lzEndpoint.send{value: nativeFee}(
                    dstChainId,
                    trustedRemote,
                    payload,
                    payable(msg.sender),
                    address(0),
                    defaultAdapterParams
                );
            }
        }
    }
    
    /**
    /**
     * @notice Unblock an address globally
     * @param _dstChainIds Array of destination chain IDs
     * @param _targetAddress Address to unblock
     */
    function unblockAddressGlobally(
        uint16[] calldata _dstChainIds,
        address _targetAddress
    ) external payable whenNotPaused nonReentrant {
        require(msg.sender == policyEngine || msg.sender == owner(), "Unauthorized");
        // SECURITY: Prevent DoS via unbounded array
        require(_dstChainIds.length <= MAX_BATCH_CHAINS, "Too many chains");
        
        // Unblock locally
        globallyBlocked[_targetAddress] = false;
        emit AddressUnblockedGlobally(_targetAddress, localChainId);
        
        // Propagate to other chains
        bytes memory payload = abi.encode(
            MSG_UNBLOCK_ADDRESS,
            _targetAddress,
            block.timestamp
        );
        
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
                
                lzEndpoint.send{value: nativeFee}(
                    dstChainId,
                    trustedRemote,
                    payload,
                    payable(msg.sender),
                    address(0),
                    defaultAdapterParams
                );
            }
        }
    }
    
    /**
     * @notice Propagate dispute result to other chains
     * @param _dstChainId Destination chain
     * @param _disputeId Dispute identifier
     * @param _approved Whether the transaction was approved
     */
    function propagateDisputeResult(
        uint16 _dstChainId,
        bytes32 _disputeId,
        bool _approved
    ) external payable whenNotPaused {
        require(msg.sender == policyEngine || msg.sender == owner(), "Unauthorized");
        
        bytes memory trustedRemote = trustedRemotes[_dstChainId];
        require(trustedRemote.length > 0, "Untrusted destination");
        
        // ═══ PER-CHAIN PAUSE CHECK ═══
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
    }
    
    // ============ LayerZero Receiver ============
    
    /**
     * @notice Receive LayerZero message (called by endpoint)
     * @param _srcChainId Source chain ID
     * @param _srcAddress Source address in bytes
     * @param _nonce Message nonce
     * @param _payload Encoded message payload
     */
    function lzReceive(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external override {
        // Verify caller is the LayerZero endpoint
        require(msg.sender == address(lzEndpoint), "Invalid endpoint caller");
        
        // ═══ PER-CHAIN PAUSE CHECK ═══
        // Reject messages from paused chains
        _enforceChainNotPaused(_srcChainId);
        
        // Verify the source is trusted
        bytes memory trustedRemote = trustedRemotes[_srcChainId];
        require(
            trustedRemote.length == _srcAddress.length &&
            keccak256(trustedRemote) == keccak256(_srcAddress),
            "Untrusted source"
        );
        
        // Check nonce hasn't been processed
        require(
            receivedNonces[_srcChainId][_srcAddress] < _nonce,
            "Nonce already processed"
        );
        
        // Try to process, store on failure for retry
        try this.processMessage(_srcChainId, _srcAddress, _nonce, _payload) {
            receivedNonces[_srcChainId][_srcAddress] = _nonce;
        } catch (bytes memory reason) {
            // Store failed message for retry
            failedMessages[_srcChainId][_srcAddress][_nonce] = keccak256(_payload);
            emit MessageFailed(_srcChainId, _srcAddress, _nonce, _payload, reason);
        }
    }
    
    /**
     * @notice Process incoming cross-chain message
     * @dev External for try/catch, only callable by this contract
     */
    function processMessage(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external {
        require(msg.sender == address(this), "Only self");
        
        // Decode message type
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
     * @param _srcChainId Source chain ID
     * @param _srcAddress Source address
     * @param _nonce Message nonce
     * @param _payload Original payload
     */
    function retryMessage(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external nonReentrant {
        bytes32 payloadHash = failedMessages[_srcChainId][_srcAddress][_nonce];
        require(payloadHash != bytes32(0), "No failed message");
        require(keccak256(_payload) == payloadHash, "Payload mismatch");
        
        // Clear failed message
        delete failedMessages[_srcChainId][_srcAddress][_nonce];
        
        // Reprocess
        this.processMessage(_srcChainId, _srcAddress, _nonce, _payload);
        receivedNonces[_srcChainId][_srcAddress] = _nonce;
        
        emit RetryMessageSuccess(_srcChainId, _srcAddress, _nonce, payloadHash);
    }
    
    // ============ Internal Handlers ============
    
    function _handleRiskScore(
        uint16 _srcChainId,
        uint64 _nonce,
        bytes calldata _payload
    ) internal {
        (, address targetAddress, uint256 riskScore, ) = abi.decode(
            _payload,
            (uint8, address, uint256, uint256)
        );
        
        // Store cross-chain risk score
        crossChainRiskScores[targetAddress][_srcChainId] = riskScore;
        lastRiskUpdate[targetAddress] = block.timestamp;
        
        emit RiskScoreReceived(_srcChainId, targetAddress, riskScore, _nonce);
        
        // If high risk, auto-block locally
        if (riskScore >= 700) {
            globallyBlocked[targetAddress] = true;
            emit AddressBlockedGlobally(
                targetAddress,
                _srcChainId,
                "High cross-chain risk score"
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
        
        // Emit event for off-chain indexers to process
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
    
    // ============ View Functions ============
    
    /**
     * @notice Get aggregated risk score from all chains
     * @param _address Address to check
     * @return maxScore Highest risk score across all chains
     * @return sourceChain Chain with highest score
     */
    function getAggregatedRiskScore(address _address) 
        external 
        view 
        returns (uint256 maxScore, uint16 sourceChain) 
    {
        uint16[] memory chains = getSupportedChains();
        
        for (uint256 i = 0; i < chains.length; i++) {
            uint256 score = crossChainRiskScores[_address][chains[i]];
            if (score > maxScore) {
                maxScore = score;
                sourceChain = chains[i];
            }
        }
    }
    
    /**
     * @notice Check if an address is blocked globally
     * @param _address Address to check
     * @return True if blocked
     */
    function isGloballyBlocked(address _address) external view returns (bool) {
        return globallyBlocked[_address];
    }
    
    /**
     * @notice Estimate fee for sending risk score
     * @param _dstChainId Destination chain
     * @param _targetAddress Target address
     * @param _riskScore Risk score
     * @return nativeFee Fee in native token
     */
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
    
    /**
     * @notice Get list of supported chains
     * @return Array of chain IDs
     */
    function getSupportedChains() public pure returns (uint16[] memory) {
        uint16[] memory chains = new uint16[](5);
        chains[0] = 101;  // Ethereum
        chains[1] = 109;  // Polygon
        chains[2] = 110;  // Arbitrum
        chains[3] = 184;  // Base
        chains[4] = 111;  // Optimism
        return chains;
    }
    
    // ============ Admin Functions ============
    
    /**
     * @notice Set trusted remote for a chain
     * @param _chainId Chain ID
     * @param _remoteAddress Remote contract address
     */
    function setTrustedRemote(
        uint16 _chainId,
        bytes calldata _remoteAddress
    ) external onlyOwner {
        trustedRemotes[_chainId] = _remoteAddress;
        emit TrustedRemoteSet(_chainId, _remoteAddress);
    }
    
    /**
     * @notice Set trusted remote with path format (remote + local)
     * @param _chainId Chain ID
     * @param _path Path bytes (remote address + local address)
     */
    function setTrustedRemotePath(
        uint16 _chainId,
        bytes calldata _path
    ) external onlyOwner {
        trustedRemotes[_chainId] = _path;
        emit TrustedRemoteSet(_chainId, _path);
    }
    
    /**
     * @notice Set policy engine address
     * @param _policyEngine New policy engine address
     */
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        policyEngine = _policyEngine;
    }
    
    /**
     * @notice Set minimum destination gas
     * @param _minDstGas Minimum gas amount
     */
    function setMinDstGas(uint256 _minDstGas) external onlyOwner {
        minDstGas = _minDstGas;
    }
    
    /**
     * @notice Set default adapter params
     * @param _adapterParams Adapter parameters
     */
    function setDefaultAdapterParams(bytes calldata _adapterParams) external onlyOwner {
        defaultAdapterParams = _adapterParams;
    }
    
    /**
     * @notice Set per-chain rate limit (max messages per block)
     */
    function setChainRateLimit(uint16 chainId, uint256 maxPerBlock) external onlyOwner {
        require(maxPerBlock > 0 && maxPerBlock < 1000, "Unreasonable limit");
        chainRateLimit[chainId] = maxPerBlock;
    }

    /**
     * @notice Internal function to enforce per-chain rate limiting
     * @param chainId The chain to rate limit for
     */
    function _enforceChainRateLimit(uint16 chainId) internal {
        uint256 limit = chainRateLimit[chainId];
        // If no limit is set, allow unlimited
        if (limit == 0) return;
        uint256 currentBlock = block.number;
        uint256 count = chainBlockMessageCount[chainId][currentBlock];
        if (count >= limit) {
            emit ChainRateLimitExceeded(chainId, currentBlock);
            revert("Rate limit exceeded");
        }
        chainBlockMessageCount[chainId][currentBlock] = count + 1;
    }

    /**
     * @notice Pause the contract
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @notice Unpause the contract
     */
    function unpause() external onlyOwner {
        _unpause();
    }

    /**
     * @notice Pause a specific chain bridge
     * @param chainId The chain ID to pause
     */
    function pauseChain(uint16 chainId) external onlyOwner {
        chainPaused[chainId] = true;
        emit ChainPaused(chainId);
    }

    /**
     * @notice Unpause a specific chain bridge
     * @param chainId The chain ID to unpause
     */
    function unpauseChain(uint16 chainId) external onlyOwner {
        chainPaused[chainId] = false;
        emit ChainUnpaused(chainId);
    }

    /**
     * @notice Check if a chain is paused
     * @param chainId The chain ID to check
     */
    function isChainPaused(uint16 chainId) external view returns (bool) {
        return chainPaused[chainId];
    }

    /**
     * @notice Internal function to enforce per-chain pause
     * @param chainId The chain to check
     */
    function _enforceChainNotPaused(uint16 chainId) internal view {
        if (chainPaused[chainId]) revert ChainIsPaused();
    }
    
    // ============ LayerZero Config ============
    
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
    
    // ============ Internal Helpers ============
    
    function _initializeChainNames() internal {
        chainNames[101] = "Ethereum";
        chainNames[109] = "Polygon";
        chainNames[110] = "Arbitrum";
        chainNames[184] = "Base";
        chainNames[111] = "Optimism";
        chainNames[102] = "BSC";
        chainNames[106] = "Avalanche";
    }
    
    function _authorizeUpgrade(address) internal override onlyOwner {}
    
    // ============ Receive ETH ============
    
    receive() external payable {}
    
    // ════════════════════════════════════════════════════════════════════
    //              STORAGE GAP (Security Enhancement for Upgrades)
    // ════════════════════════════════════════════════════════════════════
    
    /**
     * @dev Reserved storage space for future upgrades.
     * This allows adding new state variables without shifting storage layout.
     */
    uint256[50] private __gap;
}
