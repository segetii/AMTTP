// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ILayerZeroEndpoint
 * @dev LayerZero endpoint interface for cross-chain messaging
 * @notice Implements LayerZero V1 endpoint specification
 */
interface ILayerZeroEndpoint {
    /**
     * @notice Send a LayerZero message to a destination chain
     * @param _dstChainId The destination chain identifier
     * @param _destination The address on destination chain (in bytes)
     * @param _payload Encoded message payload
     * @param _refundAddress Address to refund excess gas payment
     * @param _zroPaymentAddress Address of ZRO token holder for fee payment
     * @param _adapterParams Parameters for the adapter layer
     */
    function send(
        uint16 _dstChainId,
        bytes calldata _destination,
        bytes calldata _payload,
        address payable _refundAddress,
        address _zroPaymentAddress,
        bytes calldata _adapterParams
    ) external payable;

    /**
     * @notice Estimate fees for sending a message
     * @param _dstChainId Destination chain id
     * @param _userApplication User application address
     * @param _payload Message payload
     * @param _payInZRO Whether to pay in ZRO token
     * @param _adapterParam Adapter parameters
     * @return nativeFee Native token fee amount
     * @return zroFee ZRO token fee amount
     */
    function estimateFees(
        uint16 _dstChainId,
        address _userApplication,
        bytes calldata _payload,
        bool _payInZRO,
        bytes calldata _adapterParam
    ) external view returns (uint256 nativeFee, uint256 zroFee);

    /**
     * @notice Get the inbound nonce for a source chain
     * @param _srcChainId Source chain id
     * @param _srcAddress Source address in bytes
     * @return Inbound nonce
     */
    function getInboundNonce(uint16 _srcChainId, bytes calldata _srcAddress) external view returns (uint64);

    /**
     * @notice Get the outbound nonce for a destination chain
     * @param _dstChainId Destination chain id
     * @param _srcAddress Source address
     * @return Outbound nonce
     */
    function getOutboundNonce(uint16 _dstChainId, address _srcAddress) external view returns (uint64);

    /**
     * @notice Retry a failed message
     * @param _srcChainId Source chain id
     * @param _srcAddress Source address in bytes
     * @param _payload Original payload
     */
    function retryPayload(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        bytes calldata _payload
    ) external;

    /**
     * @notice Check if there's a stored payload
     * @param _srcChainId Source chain id
     * @param _srcAddress Source address in bytes
     * @return True if payload exists
     */
    function hasStoredPayload(uint16 _srcChainId, bytes calldata _srcAddress) external view returns (bool);

    /**
     * @notice Get send library address
     * @param _userApplication User application address
     * @return Library address
     */
    function getSendLibraryAddress(address _userApplication) external view returns (address);

    /**
     * @notice Get receive library address
     * @param _userApplication User application address
     * @return Library address
     */
    function getReceiveLibraryAddress(address _userApplication) external view returns (address);

    /**
     * @notice Check if sending is enabled
     * @return True if sending is enabled
     */
    function isSendingPayload() external view returns (bool);

    /**
     * @notice Check if receiving is enabled
     * @return True if receiving is enabled
     */
    function isReceivingPayload() external view returns (bool);

    /**
     * @notice Get chain id
     * @return Local chain id
     */
    function getChainId() external view returns (uint16);
    
    /**
     * @notice Set configuration for messaging
     * @param _version Messaging library version
     * @param _chainId Chain id for configuration
     * @param _configType Configuration type
     * @param _config Configuration data
     */
    function setConfig(
        uint16 _version,
        uint16 _chainId,
        uint256 _configType,
        bytes calldata _config
    ) external;
    
    /**
     * @notice Set the send messaging library version
     * @param _version Version number
     */
    function setSendVersion(uint16 _version) external;
    
    /**
     * @notice Set the receive messaging library version
     * @param _version Version number
     */
    function setReceiveVersion(uint16 _version) external;
    
    /**
     * @notice Force resume receiving from a source
     * @param _srcChainId Source chain id
     * @param _srcAddress Source address
     */
    function forceResumeReceive(uint16 _srcChainId, bytes calldata _srcAddress) external;
}

/**
 * @title ILayerZeroReceiver
 * @dev Interface for contracts that receive LayerZero messages
 */
interface ILayerZeroReceiver {
    /**
     * @notice Receive a LayerZero message
     * @param _srcChainId Source chain identifier
     * @param _srcAddress Source address in bytes format
     * @param _nonce Unique message nonce
     * @param _payload Encoded message payload
     */
    function lzReceive(
        uint16 _srcChainId,
        bytes calldata _srcAddress,
        uint64 _nonce,
        bytes calldata _payload
    ) external;
}

/**
 * @title ILayerZeroUserApplicationConfig
 * @dev Configuration interface for LayerZero user applications
 */
interface ILayerZeroUserApplicationConfig {
    /**
     * @notice Set the configuration for sending/receiving messages
     * @param _version Messaging library version
     * @param _chainId Chain id for the configuration
     * @param _configType Type of configuration
     * @param _config Configuration data
     */
    function setConfig(
        uint16 _version,
        uint16 _chainId,
        uint256 _configType,
        bytes calldata _config
    ) external;

    /**
     * @notice Set the send version
     * @param _version Version number
     */
    function setSendVersion(uint16 _version) external;

    /**
     * @notice Set the receive version
     * @param _version Version number
     */
    function setReceiveVersion(uint16 _version) external;

    /**
     * @notice Force resume receiving
     * @param _srcChainId Source chain id
     * @param _srcAddress Source address
     */
    function forceResumeReceive(uint16 _srcChainId, bytes calldata _srcAddress) external;
}
