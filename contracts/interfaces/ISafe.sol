// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title ISafe - Gnosis Safe interfaces for AMTTP integration
 * @dev Interfaces for Safe multisig wallet operations
 */

/// @notice Safe Transaction structure
struct SafeTransaction {
    address to;
    uint256 value;
    bytes data;
    uint8 operation;
    uint256 safeTxGas;
    uint256 baseGas;
    uint256 gasPrice;
    address gasToken;
    address refundReceiver;
    bytes signatures;
}

/// @notice Module Transaction structure
struct ModuleTransaction {
    address to;
    uint256 value;
    bytes data;
    uint8 operation;
}

/**
 * @title IGnosisSafe
 * @dev Interface for Gnosis Safe core functions
 */
interface IGnosisSafe {
    /// @notice Execute a transaction from the Safe
    function execTransaction(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address payable refundReceiver,
        bytes memory signatures
    ) external payable returns (bool success);
    
    /// @notice Execute transaction via module (no signatures required)
    function execTransactionFromModule(
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation
    ) external returns (bool success);
    
    /// @notice Check if address is module
    function isModuleEnabled(address module) external view returns (bool);
    
    /// @notice Enable a module
    function enableModule(address module) external;
    
    /// @notice Disable a module
    function disableModule(address prevModule, address module) external;
    
    /// @notice Get transaction hash
    function getTransactionHash(
        address to,
        uint256 value,
        bytes calldata data,
        uint8 operation,
        uint256 safeTxGas,
        uint256 baseGas,
        uint256 gasPrice,
        address gasToken,
        address refundReceiver,
        uint256 nonce
    ) external view returns (bytes32);
    
    /// @notice Get Safe nonce
    function nonce() external view returns (uint256);
    
    /// @notice Get Safe owners
    function getOwners() external view returns (address[] memory);
    
    /// @notice Get required confirmations
    function getThreshold() external view returns (uint256);
    
    /// @notice Check if address is owner
    function isOwner(address owner) external view returns (bool);
}

/**
 * @title ISafeProxyFactory
 * @dev Interface for creating Safe proxies
 */
interface ISafeProxyFactory {
    function createProxy(address singleton, bytes memory data) external returns (address proxy);
    function createProxyWithNonce(address singleton, bytes memory data, uint256 saltNonce) external returns (address proxy);
}

/**
 * @title IGuard
 * @dev Interface for Safe transaction guards
 */
interface IGuard {
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
    ) external;
    
    function checkAfterExecution(bytes32 txHash, bool success) external;
}

/**
 * @title IModule
 * @dev Interface for Safe modules
 */
interface IModule {
    function execute(
        address to,
        uint256 value,
        bytes memory data,
        uint8 operation
    ) external returns (bool success);
}
