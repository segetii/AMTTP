// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0 ^0.8.1 ^0.8.2 ^0.8.20 ^0.8.24;

// node_modules/@openzeppelin/contracts-upgradeable/utils/AddressUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (utils/Address.sol)

/**
 * @dev Collection of functions related to the address type
 */
library AddressUpgradeable {
    /**
     * @dev Returns true if `account` is a contract.
     *
     * [IMPORTANT]
     * ====
     * It is unsafe to assume that an address for which this function returns
     * false is an externally-owned account (EOA) and not a contract.
     *
     * Among others, `isContract` will return false for the following
     * types of addresses:
     *
     *  - an externally-owned account
     *  - a contract in construction
     *  - an address where a contract will be created
     *  - an address where a contract lived, but was destroyed
     *
     * Furthermore, `isContract` will also return true if the target contract within
     * the same transaction is already scheduled for destruction by `SELFDESTRUCT`,
     * which only has an effect at the end of a transaction.
     * ====
     *
     * [IMPORTANT]
     * ====
     * You shouldn't rely on `isContract` to protect against flash loan attacks!
     *
     * Preventing calls from contracts is highly discouraged. It breaks composability, breaks support for smart wallets
     * like Gnosis Safe, and does not provide security since it can be circumvented by calling from a contract
     * constructor.
     * ====
     */
    function isContract(address account) internal view returns (bool) {
        // This method relies on extcodesize/address.code.length, which returns 0
        // for contracts in construction, since the code is only stored at the end
        // of the constructor execution.

        return account.code.length > 0;
    }

    /**
     * @dev Replacement for Solidity's `transfer`: sends `amount` wei to
     * `recipient`, forwarding all available gas and reverting on errors.
     *
     * https://eips.ethereum.org/EIPS/eip-1884[EIP1884] increases the gas cost
     * of certain opcodes, possibly making contracts go over the 2300 gas limit
     * imposed by `transfer`, making them unable to receive funds via
     * `transfer`. {sendValue} removes this limitation.
     *
     * https://consensys.net/diligence/blog/2019/09/stop-using-soliditys-transfer-now/[Learn more].
     *
     * IMPORTANT: because control is transferred to `recipient`, care must be
     * taken to not create reentrancy vulnerabilities. Consider using
     * {ReentrancyGuard} or the
     * https://solidity.readthedocs.io/en/v0.8.0/security-considerations.html#use-the-checks-effects-interactions-pattern[checks-effects-interactions pattern].
     */
    function sendValue(address payable recipient, uint256 amount) internal {
        require(address(this).balance >= amount, "Address: insufficient balance");

        (bool success, ) = recipient.call{value: amount}("");
        require(success, "Address: unable to send value, recipient may have reverted");
    }

    /**
     * @dev Performs a Solidity function call using a low level `call`. A
     * plain `call` is an unsafe replacement for a function call: use this
     * function instead.
     *
     * If `target` reverts with a revert reason, it is bubbled up by this
     * function (like regular Solidity function calls).
     *
     * Returns the raw returned data. To convert to the expected return value,
     * use https://solidity.readthedocs.io/en/latest/units-and-global-variables.html?highlight=abi.decode#abi-encoding-and-decoding-functions[`abi.decode`].
     *
     * Requirements:
     *
     * - `target` must be a contract.
     * - calling `target` with `data` must not revert.
     *
     * _Available since v3.1._
     */
    function functionCall(address target, bytes memory data) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, "Address: low-level call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`], but with
     * `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal returns (bytes memory) {
        return functionCallWithValue(target, data, 0, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but also transferring `value` wei to `target`.
     *
     * Requirements:
     *
     * - the calling contract must have an ETH balance of at least `value`.
     * - the called Solidity function must be `payable`.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(address target, bytes memory data, uint256 value) internal returns (bytes memory) {
        return functionCallWithValue(target, data, value, "Address: low-level call with value failed");
    }

    /**
     * @dev Same as {xref-Address-functionCallWithValue-address-bytes-uint256-}[`functionCallWithValue`], but
     * with `errorMessage` as a fallback revert reason when `target` reverts.
     *
     * _Available since v3.1._
     */
    function functionCallWithValue(
        address target,
        bytes memory data,
        uint256 value,
        string memory errorMessage
    ) internal returns (bytes memory) {
        require(address(this).balance >= value, "Address: insufficient balance for call");
        (bool success, bytes memory returndata) = target.call{value: value}(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(address target, bytes memory data) internal view returns (bytes memory) {
        return functionStaticCall(target, data, "Address: low-level static call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-string-}[`functionCall`],
     * but performing a static call.
     *
     * _Available since v3.3._
     */
    function functionStaticCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        (bool success, bytes memory returndata) = target.staticcall(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-}[`functionCall`],
     * but performing a delegate call.
     *
     * _Available since v3.4._
     */
    function functionDelegateCall(address target, bytes memory data) internal returns (bytes memory) {
        return functionDelegateCall(target, data, "Address: low-level delegate call failed");
    }

    /**
     * @dev Same as {xref-Address-functionCall-address-bytes-string-}[`functionCall`],
     * but performing a delegate call.
     *
     * _Available since v3.4._
     */
    function functionDelegateCall(
        address target,
        bytes memory data,
        string memory errorMessage
    ) internal returns (bytes memory) {
        (bool success, bytes memory returndata) = target.delegatecall(data);
        return verifyCallResultFromTarget(target, success, returndata, errorMessage);
    }

    /**
     * @dev Tool to verify that a low level call to smart-contract was successful, and revert (either by bubbling
     * the revert reason or using the provided one) in case of unsuccessful call or if target was not a contract.
     *
     * _Available since v4.8._
     */
    function verifyCallResultFromTarget(
        address target,
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal view returns (bytes memory) {
        if (success) {
            if (returndata.length == 0) {
                // only check isContract if the call was successful and the return data is empty
                // otherwise we already know that it was a contract
                require(isContract(target), "Address: call to non-contract");
            }
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    /**
     * @dev Tool to verify that a low level call was successful, and revert if it wasn't, either by bubbling the
     * revert reason or using the provided one.
     *
     * _Available since v4.3._
     */
    function verifyCallResult(
        bool success,
        bytes memory returndata,
        string memory errorMessage
    ) internal pure returns (bytes memory) {
        if (success) {
            return returndata;
        } else {
            _revert(returndata, errorMessage);
        }
    }

    function _revert(bytes memory returndata, string memory errorMessage) private pure {
        // Look for revert reason and bubble it up if present
        if (returndata.length > 0) {
            // The easiest way to bubble the revert reason is using memory via assembly
            /// @solidity memory-safe-assembly
            assembly {
                let returndata_size := mload(returndata)
                revert(add(32, returndata), returndata_size)
            }
        } else {
            revert(errorMessage);
        }
    }
}

// node_modules/@openzeppelin/contracts-upgradeable/proxy/beacon/IBeaconUpgradeable.sol

// OpenZeppelin Contracts v4.4.1 (proxy/beacon/IBeacon.sol)

/**
 * @dev This is the interface that {BeaconProxy} expects of its beacon.
 */
interface IBeaconUpgradeable {
    /**
     * @dev Must return an address that can be used as a delegate call target.
     *
     * {BeaconProxy} will check that this address is a contract.
     */
    function implementation() external view returns (address);
}

// node_modules/@openzeppelin/contracts-upgradeable/interfaces/IERC1967Upgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (interfaces/IERC1967.sol)

/**
 * @dev ERC-1967: Proxy Storage Slots. This interface contains the events defined in the ERC.
 *
 * _Available since v4.8.3._
 */
interface IERC1967Upgradeable {
    /**
     * @dev Emitted when the implementation is upgraded.
     */
    event Upgraded(address indexed implementation);

    /**
     * @dev Emitted when the admin account has changed.
     */
    event AdminChanged(address previousAdmin, address newAdmin);

    /**
     * @dev Emitted when the beacon is changed.
     */
    event BeaconUpgraded(address indexed beacon);
}

// contracts/interfaces/ILayerZero.sol

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

// node_modules/@openzeppelin/contracts-upgradeable/utils/StorageSlotUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (utils/StorageSlot.sol)
// This file was procedurally generated from scripts/generate/templates/StorageSlot.js.

/**
 * @dev Library for reading and writing primitive types to specific storage slots.
 *
 * Storage slots are often used to avoid storage conflict when dealing with upgradeable contracts.
 * This library helps with reading and writing to such slots without the need for inline assembly.
 *
 * The functions in this library return Slot structs that contain a `value` member that can be used to read or write.
 *
 * Example usage to set ERC1967 implementation slot:
 * ```solidity
 * contract ERC1967 {
 *     bytes32 internal constant _IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
 *
 *     function _getImplementation() internal view returns (address) {
 *         return StorageSlot.getAddressSlot(_IMPLEMENTATION_SLOT).value;
 *     }
 *
 *     function _setImplementation(address newImplementation) internal {
 *         require(Address.isContract(newImplementation), "ERC1967: new implementation is not a contract");
 *         StorageSlot.getAddressSlot(_IMPLEMENTATION_SLOT).value = newImplementation;
 *     }
 * }
 * ```
 *
 * _Available since v4.1 for `address`, `bool`, `bytes32`, `uint256`._
 * _Available since v4.9 for `string`, `bytes`._
 */
library StorageSlotUpgradeable {
    struct AddressSlot {
        address value;
    }

    struct BooleanSlot {
        bool value;
    }

    struct Bytes32Slot {
        bytes32 value;
    }

    struct Uint256Slot {
        uint256 value;
    }

    struct StringSlot {
        string value;
    }

    struct BytesSlot {
        bytes value;
    }

    /**
     * @dev Returns an `AddressSlot` with member `value` located at `slot`.
     */
    function getAddressSlot(bytes32 slot) internal pure returns (AddressSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `BooleanSlot` with member `value` located at `slot`.
     */
    function getBooleanSlot(bytes32 slot) internal pure returns (BooleanSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `Bytes32Slot` with member `value` located at `slot`.
     */
    function getBytes32Slot(bytes32 slot) internal pure returns (Bytes32Slot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `Uint256Slot` with member `value` located at `slot`.
     */
    function getUint256Slot(bytes32 slot) internal pure returns (Uint256Slot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `StringSlot` with member `value` located at `slot`.
     */
    function getStringSlot(bytes32 slot) internal pure returns (StringSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `StringSlot` representation of the string storage pointer `store`.
     */
    function getStringSlot(string storage store) internal pure returns (StringSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := store.slot
        }
    }

    /**
     * @dev Returns an `BytesSlot` with member `value` located at `slot`.
     */
    function getBytesSlot(bytes32 slot) internal pure returns (BytesSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := slot
        }
    }

    /**
     * @dev Returns an `BytesSlot` representation of the bytes storage pointer `store`.
     */
    function getBytesSlot(bytes storage store) internal pure returns (BytesSlot storage r) {
        /// @solidity memory-safe-assembly
        assembly {
            r.slot := store.slot
        }
    }
}

// node_modules/@openzeppelin/contracts-upgradeable/interfaces/draft-IERC1822Upgradeable.sol

// OpenZeppelin Contracts (last updated v4.5.0) (interfaces/draft-IERC1822.sol)

/**
 * @dev ERC1822: Universal Upgradeable Proxy Standard (UUPS) documents a method for upgradeability through a simplified
 * proxy whose upgrades are fully controlled by the current implementation.
 */
interface IERC1822ProxiableUpgradeable {
    /**
     * @dev Returns the storage slot that the proxiable contract assumes is being used to store the implementation
     * address.
     *
     * IMPORTANT: A proxy pointing at a proxiable contract should not be considered proxiable itself, because this risks
     * bricking a proxy that upgrades to it, by delegating to itself until out of gas. Thus it is critical that this
     * function revert if invoked through a proxy.
     */
    function proxiableUUID() external view returns (bytes32);
}

// node_modules/@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (proxy/utils/Initializable.sol)

/**
 * @dev This is a base contract to aid in writing upgradeable contracts, or any kind of contract that will be deployed
 * behind a proxy. Since proxied contracts do not make use of a constructor, it's common to move constructor logic to an
 * external initializer function, usually called `initialize`. It then becomes necessary to protect this initializer
 * function so it can only be called once. The {initializer} modifier provided by this contract will have this effect.
 *
 * The initialization functions use a version number. Once a version number is used, it is consumed and cannot be
 * reused. This mechanism prevents re-execution of each "step" but allows the creation of new initialization steps in
 * case an upgrade adds a module that needs to be initialized.
 *
 * For example:
 *
 * [.hljs-theme-light.nopadding]
 * ```solidity
 * contract MyToken is ERC20Upgradeable {
 *     function initialize() initializer public {
 *         __ERC20_init("MyToken", "MTK");
 *     }
 * }
 *
 * contract MyTokenV2 is MyToken, ERC20PermitUpgradeable {
 *     function initializeV2() reinitializer(2) public {
 *         __ERC20Permit_init("MyToken");
 *     }
 * }
 * ```
 *
 * TIP: To avoid leaving the proxy in an uninitialized state, the initializer function should be called as early as
 * possible by providing the encoded function call as the `_data` argument to {ERC1967Proxy-constructor}.
 *
 * CAUTION: When used with inheritance, manual care must be taken to not invoke a parent initializer twice, or to ensure
 * that all initializers are idempotent. This is not verified automatically as constructors are by Solidity.
 *
 * [CAUTION]
 * ====
 * Avoid leaving a contract uninitialized.
 *
 * An uninitialized contract can be taken over by an attacker. This applies to both a proxy and its implementation
 * contract, which may impact the proxy. To prevent the implementation contract from being used, you should invoke
 * the {_disableInitializers} function in the constructor to automatically lock it when it is deployed:
 *
 * [.hljs-theme-light.nopadding]
 * ```
 * /// @custom:oz-upgrades-unsafe-allow constructor
 * constructor() {
 *     _disableInitializers();
 * }
 * ```
 * ====
 */
abstract contract Initializable {
    /**
     * @dev Indicates that the contract has been initialized.
     * @custom:oz-retyped-from bool
     */
    uint8 private _initialized;

    /**
     * @dev Indicates that the contract is in the process of being initialized.
     */
    bool private _initializing;

    /**
     * @dev Triggered when the contract has been initialized or reinitialized.
     */
    event Initialized(uint8 version);

    /**
     * @dev A modifier that defines a protected initializer function that can be invoked at most once. In its scope,
     * `onlyInitializing` functions can be used to initialize parent contracts.
     *
     * Similar to `reinitializer(1)`, except that functions marked with `initializer` can be nested in the context of a
     * constructor.
     *
     * Emits an {Initialized} event.
     */
    modifier initializer() {
        bool isTopLevelCall = !_initializing;
        require(
            (isTopLevelCall && _initialized < 1) || (!AddressUpgradeable.isContract(address(this)) && _initialized == 1),
            "Initializable: contract is already initialized"
        );
        _initialized = 1;
        if (isTopLevelCall) {
            _initializing = true;
        }
        _;
        if (isTopLevelCall) {
            _initializing = false;
            emit Initialized(1);
        }
    }

    /**
     * @dev A modifier that defines a protected reinitializer function that can be invoked at most once, and only if the
     * contract hasn't been initialized to a greater version before. In its scope, `onlyInitializing` functions can be
     * used to initialize parent contracts.
     *
     * A reinitializer may be used after the original initialization step. This is essential to configure modules that
     * are added through upgrades and that require initialization.
     *
     * When `version` is 1, this modifier is similar to `initializer`, except that functions marked with `reinitializer`
     * cannot be nested. If one is invoked in the context of another, execution will revert.
     *
     * Note that versions can jump in increments greater than 1; this implies that if multiple reinitializers coexist in
     * a contract, executing them in the right order is up to the developer or operator.
     *
     * WARNING: setting the version to 255 will prevent any future reinitialization.
     *
     * Emits an {Initialized} event.
     */
    modifier reinitializer(uint8 version) {
        require(!_initializing && _initialized < version, "Initializable: contract is already initialized");
        _initialized = version;
        _initializing = true;
        _;
        _initializing = false;
        emit Initialized(version);
    }

    /**
     * @dev Modifier to protect an initialization function so that it can only be invoked by functions with the
     * {initializer} and {reinitializer} modifiers, directly or indirectly.
     */
    modifier onlyInitializing() {
        require(_initializing, "Initializable: contract is not initializing");
        _;
    }

    /**
     * @dev Locks the contract, preventing any future reinitialization. This cannot be part of an initializer call.
     * Calling this in the constructor of a contract will prevent that contract from being initialized or reinitialized
     * to any version. It is recommended to use this to lock implementation contracts that are designed to be called
     * through proxies.
     *
     * Emits an {Initialized} event the first time it is successfully executed.
     */
    function _disableInitializers() internal virtual {
        require(!_initializing, "Initializable: contract is initializing");
        if (_initialized != type(uint8).max) {
            _initialized = type(uint8).max;
            emit Initialized(type(uint8).max);
        }
    }

    /**
     * @dev Returns the highest version that has been initialized. See {reinitializer}.
     */
    function _getInitializedVersion() internal view returns (uint8) {
        return _initialized;
    }

    /**
     * @dev Returns `true` if the contract is currently initializing. See {onlyInitializing}.
     */
    function _isInitializing() internal view returns (bool) {
        return _initializing;
    }
}

// node_modules/@openzeppelin/contracts-upgradeable/utils/ContextUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.4) (utils/Context.sol)

/**
 * @dev Provides information about the current execution context, including the
 * sender of the transaction and its data. While these are generally available
 * via msg.sender and msg.data, they should not be accessed in such a direct
 * manner, since when dealing with meta-transactions the account sending and
 * paying for execution may not be the actual sender (as far as an application
 * is concerned).
 *
 * This contract is only required for intermediate, library-like contracts.
 */
abstract contract ContextUpgradeable is Initializable {
    function __Context_init() internal onlyInitializing {
    }

    function __Context_init_unchained() internal onlyInitializing {
    }
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    function _msgData() internal view virtual returns (bytes calldata) {
        return msg.data;
    }

    function _contextSuffixLength() internal view virtual returns (uint256) {
        return 0;
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[50] private __gap;
}

// node_modules/@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (security/ReentrancyGuard.sol)

/**
 * @dev Contract module that helps prevent reentrant calls to a function.
 *
 * Inheriting from `ReentrancyGuard` will make the {nonReentrant} modifier
 * available, which can be applied to functions to make sure there are no nested
 * (reentrant) calls to them.
 *
 * Note that because there is a single `nonReentrant` guard, functions marked as
 * `nonReentrant` may not call one another. This can be worked around by making
 * those functions `private`, and then adding `external` `nonReentrant` entry
 * points to them.
 *
 * TIP: If you would like to learn more about reentrancy and alternative ways
 * to protect against it, check out our blog post
 * https://blog.openzeppelin.com/reentrancy-after-istanbul/[Reentrancy After Istanbul].
 */
abstract contract ReentrancyGuardUpgradeable is Initializable {
    // Booleans are more expensive than uint256 or any type that takes up a full
    // word because each write operation emits an extra SLOAD to first read the
    // slot's contents, replace the bits taken up by the boolean, and then write
    // back. This is the compiler's defense against contract upgrades and
    // pointer aliasing, and it cannot be disabled.

    // The values being non-zero value makes deployment a bit more expensive,
    // but in exchange the refund on every call to nonReentrant will be lower in
    // amount. Since refunds are capped to a percentage of the total
    // transaction's gas, it is best to keep them low in cases like this one, to
    // increase the likelihood of the full refund coming into effect.
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;

    uint256 private _status;

    function __ReentrancyGuard_init() internal onlyInitializing {
        __ReentrancyGuard_init_unchained();
    }

    function __ReentrancyGuard_init_unchained() internal onlyInitializing {
        _status = _NOT_ENTERED;
    }

    /**
     * @dev Prevents a contract from calling itself, directly or indirectly.
     * Calling a `nonReentrant` function from another `nonReentrant`
     * function is not supported. It is possible to prevent this from happening
     * by making the `nonReentrant` function external, and making it call a
     * `private` function that does the actual work.
     */
    modifier nonReentrant() {
        _nonReentrantBefore();
        _;
        _nonReentrantAfter();
    }

    function _nonReentrantBefore() private {
        // On the first call to nonReentrant, _status will be _NOT_ENTERED
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");

        // Any calls to nonReentrant after this point will fail
        _status = _ENTERED;
    }

    function _nonReentrantAfter() private {
        // By storing the original value once again, a refund is triggered (see
        // https://eips.ethereum.org/EIPS/eip-2200)
        _status = _NOT_ENTERED;
    }

    /**
     * @dev Returns true if the reentrancy guard is currently set to "entered", which indicates there is a
     * `nonReentrant` function in the call stack.
     */
    function _reentrancyGuardEntered() internal view returns (bool) {
        return _status == _ENTERED;
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[49] private __gap;
}

// node_modules/@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (access/Ownable.sol)

/**
 * @dev Contract module which provides a basic access control mechanism, where
 * there is an account (an owner) that can be granted exclusive access to
 * specific functions.
 *
 * By default, the owner account will be the one that deploys the contract. This
 * can later be changed with {transferOwnership}.
 *
 * This module is used through inheritance. It will make available the modifier
 * `onlyOwner`, which can be applied to your functions to restrict their use to
 * the owner.
 */
abstract contract OwnableUpgradeable is Initializable, ContextUpgradeable {
    address private _owner;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    /**
     * @dev Initializes the contract setting the deployer as the initial owner.
     */
    function __Ownable_init() internal onlyInitializing {
        __Ownable_init_unchained();
    }

    function __Ownable_init_unchained() internal onlyInitializing {
        _transferOwnership(_msgSender());
    }

    /**
     * @dev Throws if called by any account other than the owner.
     */
    modifier onlyOwner() {
        _checkOwner();
        _;
    }

    /**
     * @dev Returns the address of the current owner.
     */
    function owner() public view virtual returns (address) {
        return _owner;
    }

    /**
     * @dev Throws if the sender is not the owner.
     */
    function _checkOwner() internal view virtual {
        require(owner() == _msgSender(), "Ownable: caller is not the owner");
    }

    /**
     * @dev Leaves the contract without owner. It will not be possible to call
     * `onlyOwner` functions. Can only be called by the current owner.
     *
     * NOTE: Renouncing ownership will leave the contract without an owner,
     * thereby disabling any functionality that is only available to the owner.
     */
    function renounceOwnership() public virtual onlyOwner {
        _transferOwnership(address(0));
    }

    /**
     * @dev Transfers ownership of the contract to a new account (`newOwner`).
     * Can only be called by the current owner.
     */
    function transferOwnership(address newOwner) public virtual onlyOwner {
        require(newOwner != address(0), "Ownable: new owner is the zero address");
        _transferOwnership(newOwner);
    }

    /**
     * @dev Transfers ownership of the contract to a new account (`newOwner`).
     * Internal function without access restriction.
     */
    function _transferOwnership(address newOwner) internal virtual {
        address oldOwner = _owner;
        _owner = newOwner;
        emit OwnershipTransferred(oldOwner, newOwner);
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[49] private __gap;
}

// node_modules/@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.7.0) (security/Pausable.sol)

/**
 * @dev Contract module which allows children to implement an emergency stop
 * mechanism that can be triggered by an authorized account.
 *
 * This module is used through inheritance. It will make available the
 * modifiers `whenNotPaused` and `whenPaused`, which can be applied to
 * the functions of your contract. Note that they will not be pausable by
 * simply including this module, only once the modifiers are put in place.
 */
abstract contract PausableUpgradeable is Initializable, ContextUpgradeable {
    /**
     * @dev Emitted when the pause is triggered by `account`.
     */
    event Paused(address account);

    /**
     * @dev Emitted when the pause is lifted by `account`.
     */
    event Unpaused(address account);

    bool private _paused;

    /**
     * @dev Initializes the contract in unpaused state.
     */
    function __Pausable_init() internal onlyInitializing {
        __Pausable_init_unchained();
    }

    function __Pausable_init_unchained() internal onlyInitializing {
        _paused = false;
    }

    /**
     * @dev Modifier to make a function callable only when the contract is not paused.
     *
     * Requirements:
     *
     * - The contract must not be paused.
     */
    modifier whenNotPaused() {
        _requireNotPaused();
        _;
    }

    /**
     * @dev Modifier to make a function callable only when the contract is paused.
     *
     * Requirements:
     *
     * - The contract must be paused.
     */
    modifier whenPaused() {
        _requirePaused();
        _;
    }

    /**
     * @dev Returns true if the contract is paused, and false otherwise.
     */
    function paused() public view virtual returns (bool) {
        return _paused;
    }

    /**
     * @dev Throws if the contract is paused.
     */
    function _requireNotPaused() internal view virtual {
        require(!paused(), "Pausable: paused");
    }

    /**
     * @dev Throws if the contract is not paused.
     */
    function _requirePaused() internal view virtual {
        require(paused(), "Pausable: not paused");
    }

    /**
     * @dev Triggers stopped state.
     *
     * Requirements:
     *
     * - The contract must not be paused.
     */
    function _pause() internal virtual whenNotPaused {
        _paused = true;
        emit Paused(_msgSender());
    }

    /**
     * @dev Returns to normal state.
     *
     * Requirements:
     *
     * - The contract must be paused.
     */
    function _unpause() internal virtual whenPaused {
        _paused = false;
        emit Unpaused(_msgSender());
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[49] private __gap;
}

// node_modules/@openzeppelin/contracts-upgradeable/proxy/ERC1967/ERC1967UpgradeUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (proxy/ERC1967/ERC1967Upgrade.sol)

/**
 * @dev This abstract contract provides getters and event emitting update functions for
 * https://eips.ethereum.org/EIPS/eip-1967[EIP1967] slots.
 *
 * _Available since v4.1._
 */
abstract contract ERC1967UpgradeUpgradeable is Initializable, IERC1967Upgradeable {
    // This is the keccak-256 hash of "eip1967.proxy.rollback" subtracted by 1
    bytes32 private constant _ROLLBACK_SLOT = 0x4910fdfa16fed3260ed0e7147f7cc6da11a60208b5b9406d12a635614ffd9143;

    /**
     * @dev Storage slot with the address of the current implementation.
     * This is the keccak-256 hash of "eip1967.proxy.implementation" subtracted by 1, and is
     * validated in the constructor.
     */
    bytes32 internal constant _IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    function __ERC1967Upgrade_init() internal onlyInitializing {
    }

    function __ERC1967Upgrade_init_unchained() internal onlyInitializing {
    }
    /**
     * @dev Returns the current implementation address.
     */
    function _getImplementation() internal view returns (address) {
        return StorageSlotUpgradeable.getAddressSlot(_IMPLEMENTATION_SLOT).value;
    }

    /**
     * @dev Stores a new address in the EIP1967 implementation slot.
     */
    function _setImplementation(address newImplementation) private {
        require(AddressUpgradeable.isContract(newImplementation), "ERC1967: new implementation is not a contract");
        StorageSlotUpgradeable.getAddressSlot(_IMPLEMENTATION_SLOT).value = newImplementation;
    }

    /**
     * @dev Perform implementation upgrade
     *
     * Emits an {Upgraded} event.
     */
    function _upgradeTo(address newImplementation) internal {
        _setImplementation(newImplementation);
        emit Upgraded(newImplementation);
    }

    /**
     * @dev Perform implementation upgrade with additional setup call.
     *
     * Emits an {Upgraded} event.
     */
    function _upgradeToAndCall(address newImplementation, bytes memory data, bool forceCall) internal {
        _upgradeTo(newImplementation);
        if (data.length > 0 || forceCall) {
            AddressUpgradeable.functionDelegateCall(newImplementation, data);
        }
    }

    /**
     * @dev Perform implementation upgrade with security checks for UUPS proxies, and additional setup call.
     *
     * Emits an {Upgraded} event.
     */
    function _upgradeToAndCallUUPS(address newImplementation, bytes memory data, bool forceCall) internal {
        // Upgrades from old implementations will perform a rollback test. This test requires the new
        // implementation to upgrade back to the old, non-ERC1822 compliant, implementation. Removing
        // this special case will break upgrade paths from old UUPS implementation to new ones.
        if (StorageSlotUpgradeable.getBooleanSlot(_ROLLBACK_SLOT).value) {
            _setImplementation(newImplementation);
        } else {
            try IERC1822ProxiableUpgradeable(newImplementation).proxiableUUID() returns (bytes32 slot) {
                require(slot == _IMPLEMENTATION_SLOT, "ERC1967Upgrade: unsupported proxiableUUID");
            } catch {
                revert("ERC1967Upgrade: new implementation is not UUPS");
            }
            _upgradeToAndCall(newImplementation, data, forceCall);
        }
    }

    /**
     * @dev Storage slot with the admin of the contract.
     * This is the keccak-256 hash of "eip1967.proxy.admin" subtracted by 1, and is
     * validated in the constructor.
     */
    bytes32 internal constant _ADMIN_SLOT = 0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103;

    /**
     * @dev Returns the current admin.
     */
    function _getAdmin() internal view returns (address) {
        return StorageSlotUpgradeable.getAddressSlot(_ADMIN_SLOT).value;
    }

    /**
     * @dev Stores a new address in the EIP1967 admin slot.
     */
    function _setAdmin(address newAdmin) private {
        require(newAdmin != address(0), "ERC1967: new admin is the zero address");
        StorageSlotUpgradeable.getAddressSlot(_ADMIN_SLOT).value = newAdmin;
    }

    /**
     * @dev Changes the admin of the proxy.
     *
     * Emits an {AdminChanged} event.
     */
    function _changeAdmin(address newAdmin) internal {
        emit AdminChanged(_getAdmin(), newAdmin);
        _setAdmin(newAdmin);
    }

    /**
     * @dev The storage slot of the UpgradeableBeacon contract which defines the implementation for this proxy.
     * This is bytes32(uint256(keccak256('eip1967.proxy.beacon')) - 1)) and is validated in the constructor.
     */
    bytes32 internal constant _BEACON_SLOT = 0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50;

    /**
     * @dev Returns the current beacon.
     */
    function _getBeacon() internal view returns (address) {
        return StorageSlotUpgradeable.getAddressSlot(_BEACON_SLOT).value;
    }

    /**
     * @dev Stores a new beacon in the EIP1967 beacon slot.
     */
    function _setBeacon(address newBeacon) private {
        require(AddressUpgradeable.isContract(newBeacon), "ERC1967: new beacon is not a contract");
        require(
            AddressUpgradeable.isContract(IBeaconUpgradeable(newBeacon).implementation()),
            "ERC1967: beacon implementation is not a contract"
        );
        StorageSlotUpgradeable.getAddressSlot(_BEACON_SLOT).value = newBeacon;
    }

    /**
     * @dev Perform beacon upgrade with additional setup call. Note: This upgrades the address of the beacon, it does
     * not upgrade the implementation contained in the beacon (see {UpgradeableBeacon-_setImplementation} for that).
     *
     * Emits a {BeaconUpgraded} event.
     */
    function _upgradeBeaconToAndCall(address newBeacon, bytes memory data, bool forceCall) internal {
        _setBeacon(newBeacon);
        emit BeaconUpgraded(newBeacon);
        if (data.length > 0 || forceCall) {
            AddressUpgradeable.functionDelegateCall(IBeaconUpgradeable(newBeacon).implementation(), data);
        }
    }

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[50] private __gap;
}

// node_modules/@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol

// OpenZeppelin Contracts (last updated v4.9.0) (proxy/utils/UUPSUpgradeable.sol)

/**
 * @dev An upgradeability mechanism designed for UUPS proxies. The functions included here can perform an upgrade of an
 * {ERC1967Proxy}, when this contract is set as the implementation behind such a proxy.
 *
 * A security mechanism ensures that an upgrade does not turn off upgradeability accidentally, although this risk is
 * reinstated if the upgrade retains upgradeability but removes the security mechanism, e.g. by replacing
 * `UUPSUpgradeable` with a custom implementation of upgrades.
 *
 * The {_authorizeUpgrade} function must be overridden to include access restriction to the upgrade mechanism.
 *
 * _Available since v4.1._
 */
abstract contract UUPSUpgradeable is Initializable, IERC1822ProxiableUpgradeable, ERC1967UpgradeUpgradeable {
    /// @custom:oz-upgrades-unsafe-allow state-variable-immutable state-variable-assignment
    address private immutable __self = address(this);

    /**
     * @dev Check that the execution is being performed through a delegatecall call and that the execution context is
     * a proxy contract with an implementation (as defined in ERC1967) pointing to self. This should only be the case
     * for UUPS and transparent proxies that are using the current contract as their implementation. Execution of a
     * function through ERC1167 minimal proxies (clones) would not normally pass this test, but is not guaranteed to
     * fail.
     */
    modifier onlyProxy() {
        require(address(this) != __self, "Function must be called through delegatecall");
        require(_getImplementation() == __self, "Function must be called through active proxy");
        _;
    }

    /**
     * @dev Check that the execution is not being performed through a delegate call. This allows a function to be
     * callable on the implementing contract but not through proxies.
     */
    modifier notDelegated() {
        require(address(this) == __self, "UUPSUpgradeable: must not be called through delegatecall");
        _;
    }

    function __UUPSUpgradeable_init() internal onlyInitializing {
    }

    function __UUPSUpgradeable_init_unchained() internal onlyInitializing {
    }
    /**
     * @dev Implementation of the ERC1822 {proxiableUUID} function. This returns the storage slot used by the
     * implementation. It is used to validate the implementation's compatibility when performing an upgrade.
     *
     * IMPORTANT: A proxy pointing at a proxiable contract should not be considered proxiable itself, because this risks
     * bricking a proxy that upgrades to it, by delegating to itself until out of gas. Thus it is critical that this
     * function revert if invoked through a proxy. This is guaranteed by the `notDelegated` modifier.
     */
    function proxiableUUID() external view virtual override notDelegated returns (bytes32) {
        return _IMPLEMENTATION_SLOT;
    }

    /**
     * @dev Upgrade the implementation of the proxy to `newImplementation`.
     *
     * Calls {_authorizeUpgrade}.
     *
     * Emits an {Upgraded} event.
     *
     * @custom:oz-upgrades-unsafe-allow-reachable delegatecall
     */
    function upgradeTo(address newImplementation) public virtual onlyProxy {
        _authorizeUpgrade(newImplementation);
        _upgradeToAndCallUUPS(newImplementation, new bytes(0), false);
    }

    /**
     * @dev Upgrade the implementation of the proxy to `newImplementation`, and subsequently execute the function call
     * encoded in `data`.
     *
     * Calls {_authorizeUpgrade}.
     *
     * Emits an {Upgraded} event.
     *
     * @custom:oz-upgrades-unsafe-allow-reachable delegatecall
     */
    function upgradeToAndCall(address newImplementation, bytes memory data) public payable virtual onlyProxy {
        _authorizeUpgrade(newImplementation);
        _upgradeToAndCallUUPS(newImplementation, data, true);
    }

    /**
     * @dev Function that should revert when `msg.sender` is not authorized to upgrade the contract. Called by
     * {upgradeTo} and {upgradeToAndCall}.
     *
     * Normally, this function will use an xref:access.adoc[access control] modifier such as {Ownable-onlyOwner}.
     *
     * ```solidity
     * function _authorizeUpgrade(address) internal override onlyOwner {}
     * ```
     */
    function _authorizeUpgrade(address newImplementation) internal virtual;

    /**
     * @dev This empty reserved space is put in place to allow future versions to add new
     * variables without shifting down storage in the inheritance chain.
     * See https://docs.openzeppelin.com/contracts/4.x/upgradeable#storage_gaps
     */
    uint256[50] private __gap;
}

// contracts/AMTTPCrossChain.sol

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
