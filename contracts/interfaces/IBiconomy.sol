// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IBiconomy - Biconomy Account Abstraction interfaces for AMTTP
 * @dev Interfaces for ERC-4337 compliant smart accounts
 */

/**
 * @notice UserOperation struct as per ERC-4337
 */
struct UserOperation {
    address sender;
    uint256 nonce;
    bytes initCode;
    bytes callData;
    uint256 callGasLimit;
    uint256 verificationGasLimit;
    uint256 preVerificationGas;
    uint256 maxFeePerGas;
    uint256 maxPriorityFeePerGas;
    bytes paymasterAndData;
    bytes signature;
}

/**
 * @title IEntryPoint
 * @dev ERC-4337 EntryPoint interface
 */
interface IEntryPoint {
    /// @notice Execute a batch of UserOperations
    function handleOps(UserOperation[] calldata ops, address payable beneficiary) external;
    
    /// @notice Simulate UserOperation validation
    function simulateValidation(UserOperation calldata userOp) external;
    
    /// @notice Get deposit balance for account
    function balanceOf(address account) external view returns (uint256);
    
    /// @notice Deposit ETH for account
    function depositTo(address account) external payable;
    
    /// @notice Get user nonce
    function getNonce(address sender, uint192 key) external view returns (uint256 nonce);
}

/**
 * @title ISmartAccount
 * @dev Biconomy Smart Account interface
 */
interface ISmartAccount {
    /// @notice Execute a transaction
    function execute(
        address dest,
        uint256 value,
        bytes calldata func
    ) external;
    
    /// @notice Execute batch of transactions
    function executeBatch(
        address[] calldata dest,
        uint256[] calldata value,
        bytes[] calldata func
    ) external;
    
    /// @notice Validate UserOperation signature
    function validateUserOp(
        UserOperation calldata userOp,
        bytes32 userOpHash,
        uint256 missingAccountFunds
    ) external returns (uint256 validationData);
    
    /// @notice Get entry point address
    function entryPoint() external view returns (IEntryPoint);
    
    /// @notice Check if module is enabled
    function isModuleEnabled(address module) external view returns (bool);
    
    /// @notice Enable module
    function enableModule(address module) external;
    
    /// @notice Disable module
    function disableModule(address module) external;
}

/**
 * @title ISmartAccountFactory
 * @dev Factory for creating Biconomy Smart Accounts
 */
interface ISmartAccountFactory {
    /// @notice Deploy a new smart account
    function deployCounterFactualAccount(
        address moduleSetupContract,
        bytes calldata moduleSetupData,
        uint256 index
    ) external returns (address proxy);
    
    /// @notice Get counterfactual address
    function getAddressForCounterFactualAccount(
        address moduleSetupContract,
        bytes calldata moduleSetupData,
        uint256 index
    ) external view returns (address _account);
}

/**
 * @title IPaymaster
 * @dev ERC-4337 Paymaster interface for sponsored transactions
 */
interface IPaymaster {
    /// @notice Validate paymaster data
    function validatePaymasterUserOp(
        UserOperation calldata userOp,
        bytes32 userOpHash,
        uint256 maxCost
    ) external returns (bytes memory context, uint256 validationData);
    
    /// @notice Post operation hook
    function postOp(
        uint8 mode,
        bytes calldata context,
        uint256 actualGasCost
    ) external;
    
    /// @notice Deposit funds to EntryPoint
    function deposit() external payable;
    
    /// @notice Get deposit balance
    function getDeposit() external view returns (uint256);
}

/**
 * @title ISessionKeyManager
 * @dev Session key module for delegated transactions
 */
interface ISessionKeyManager {
    /// @notice Session key data structure
    struct SessionData {
        address sessionKey;
        uint48 validAfter;
        uint48 validUntil;
        address[] allowedTargets;
        bytes4[] allowedFunctions;
        uint256 spendingLimit;
    }
    
    /// @notice Create a new session
    function createSession(SessionData calldata sessionData) external;
    
    /// @notice Revoke a session
    function revokeSession(address sessionKey) external;
    
    /// @notice Check if session is valid
    function isSessionValid(address sessionKey) external view returns (bool);
    
    /// @notice Get session data
    function getSessionData(address sessionKey) external view returns (SessionData memory);
}
