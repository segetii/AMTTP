// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/ILayerZero.sol";

/**
 * @title MockLayerZeroEndpoint
 * @dev Mock LayerZero endpoint for local testing
 * @notice Simulates cross-chain messaging for development/testing
 */
contract MockLayerZeroEndpoint is ILayerZeroEndpoint {
    // ============ State ============
    
    uint16 public chainId;
    uint64 public nonce;
    uint256 public mockFee = 0.001 ether;
    
    mapping(address => mapping(uint16 => uint64)) public outboundNonces;
    mapping(uint16 => mapping(bytes => uint64)) public inboundNonces;
    
    // Store pending messages for simulation
    struct PendingMessage {
        uint16 srcChainId;
        bytes srcAddress;
        uint64 nonce;
        bytes payload;
        address destination;
        bool delivered;
    }
    
    PendingMessage[] public pendingMessages;
    
    // Linked mock endpoints on "other chains"
    mapping(uint16 => address) public linkedEndpoints;
    
    // ============ Events ============
    
    event MockMessageSent(
        uint16 dstChainId,
        bytes destination,
        bytes payload,
        uint64 nonce
    );
    
    event MockMessageReceived(
        uint16 srcChainId,
        bytes srcAddress,
        address destination,
        bytes payload,
        uint64 nonce
    );
    
    // ============ Constructor ============
    
    constructor(uint16 _chainId) {
        chainId = _chainId;
    }
    
    // ============ Send Function ============
    
    function send(
        uint16 _dstChainId,
        bytes calldata _destination,
        bytes calldata _payload,
        address payable _refundAddress,
        address _zroPaymentAddress,
        bytes calldata _adapterParams
    ) external payable override {
        require(msg.value >= mockFee, "Insufficient fee");
        
        // Increment nonce
        outboundNonces[msg.sender][_dstChainId]++;
        uint64 currentNonce = outboundNonces[msg.sender][_dstChainId];
        
        // Extract destination address from bytes
        address destAddr;
        if (_destination.length == 20) {
            destAddr = address(bytes20(_destination));
        } else if (_destination.length == 40) {
            // Path format: remoteAddress + localAddress
            destAddr = address(bytes20(_destination[:20]));
        }
        
        // Store pending message for manual delivery
        pendingMessages.push(PendingMessage({
            srcChainId: chainId,
            srcAddress: abi.encodePacked(msg.sender),
            nonce: currentNonce,
            payload: _payload,
            destination: destAddr,
            delivered: false
        }));
        
        emit MockMessageSent(_dstChainId, _destination, _payload, currentNonce);
        
        // Refund excess
        if (msg.value > mockFee && _refundAddress != address(0)) {
            (bool success, ) = _refundAddress.call{value: msg.value - mockFee}("");
            require(success, "Refund failed");
        }
        
        // Silence unused variable warnings
        _zroPaymentAddress;
        _adapterParams;
    }
    
    // ============ Fee Estimation ============
    
    function estimateFees(
        uint16 _dstChainId,
        address _userApplication,
        bytes calldata _payload,
        bool _payInZRO,
        bytes calldata _adapterParam
    ) external view override returns (uint256 nativeFee, uint256 zroFee) {
        // Silence unused variable warnings
        _dstChainId;
        _userApplication;
        _payload;
        _payInZRO;
        _adapterParam;
        
        return (mockFee, 0);
    }
    
    // ============ Test Helpers ============
    
    /**
     * @notice Manually deliver a message (simulates cross-chain delivery)
     * @param _messageIndex Index of pending message
     */
    function deliverMessage(uint256 _messageIndex) external {
        require(_messageIndex < pendingMessages.length, "Invalid message index");
        PendingMessage storage message = pendingMessages[_messageIndex];
        require(!message.delivered, "Already delivered");
        
        message.delivered = true;
        
        // Deliver to receiver
        ILayerZeroReceiver(message.destination).lzReceive(
            message.srcChainId,
            message.srcAddress,
            message.nonce,
            message.payload
        );
        
        emit MockMessageReceived(
            message.srcChainId,
            message.srcAddress,
            message.destination,
            message.payload,
            message.nonce
        );
    }
    
    /**
     * @notice Simulate receiving a message from another chain
     * @param _srcChainId Source chain ID
     * @param _srcAddress Source contract address
     * @param _destAddress Destination contract on this chain
     * @param _payload Message payload
     */
    function simulateReceive(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        address _destAddress,
        bytes calldata _payload
    ) external {
        inboundNonces[_srcChainId][_srcAddress]++;
        uint64 currentNonce = inboundNonces[_srcChainId][_srcAddress];
        
        ILayerZeroReceiver(_destAddress).lzReceive(
            _srcChainId,
            _srcAddress,
            currentNonce,
            _payload
        );
        
        emit MockMessageReceived(
            _srcChainId,
            _srcAddress,
            _destAddress,
            _payload,
            currentNonce
        );
    }
    
    /**
     * @notice Set the mock fee
     * @param _fee New fee amount
     */
    function setMockFee(uint256 _fee) external {
        mockFee = _fee;
    }
    
    /**
     * @notice Link another mock endpoint for testing
     * @param _chainId Chain ID
     * @param _endpoint Endpoint address
     */
    function linkEndpoint(uint16 _chainId, address _endpoint) external {
        linkedEndpoints[_chainId] = _endpoint;
    }
    
    /**
     * @notice Get pending messages count
     */
    function getPendingMessagesCount() external view returns (uint256) {
        return pendingMessages.length;
    }
    
    // ============ View Functions ============
    
    function getInboundNonce(uint16 _srcChainId, bytes calldata _srcAddress) 
        external 
        view 
        override 
        returns (uint64) 
    {
        return inboundNonces[_srcChainId][_srcAddress];
    }
    
    function getOutboundNonce(uint16 _dstChainId, address _srcAddress) 
        external 
        view 
        override 
        returns (uint64) 
    {
        return outboundNonces[_srcAddress][_dstChainId];
    }
    
    function retryPayload(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        bytes calldata _payload
    ) external override {
        // No-op for mock
        _srcChainId;
        _srcAddress;
        _payload;
    }
    
    function hasStoredPayload(uint16 _srcChainId, bytes calldata _srcAddress) 
        external 
        pure 
        override 
        returns (bool) 
    {
        _srcChainId;
        _srcAddress;
        return false;
    }
    
    function getSendLibraryAddress(address _userApplication) 
        external 
        view 
        override 
        returns (address) 
    {
        _userApplication;
        return address(this);
    }
    
    function getReceiveLibraryAddress(address _userApplication) 
        external 
        view 
        override 
        returns (address) 
    {
        _userApplication;
        return address(this);
    }
    
    function isSendingPayload() external pure override returns (bool) {
        return false;
    }
    
    function isReceivingPayload() external pure override returns (bool) {
        return false;
    }
    
    function getChainId() external view override returns (uint16) {
        return chainId;
    }
    
    // ============ Config Functions ============
    
    function setConfig(
        uint16 _version,
        uint16 _chainId,
        uint256 _configType,
        bytes calldata _config
    ) external {
        // No-op for mock
        _version;
        _chainId;
        _configType;
        _config;
    }
    
    function setSendVersion(uint16 _version) external {
        _version;
    }
    
    function setReceiveVersion(uint16 _version) external {
        _version;
    }
    
    function forceResumeReceive(uint16 _srcChainId, bytes calldata _srcAddress) external {
        _srcChainId;
        _srcAddress;
    }
    
    // ============ Receive ETH ============
    
    receive() external payable {}
}
