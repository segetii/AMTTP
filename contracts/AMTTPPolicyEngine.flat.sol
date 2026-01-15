// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0 ^0.8.1 ^0.8.2 ^0.8.24;

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

// contracts/AMTTPPolicyEngine.sol

/**
 * @title AMTTPPolicyEngine - Advanced policy management for AMTTP
 * @dev Manages user-defined transaction policies, risk thresholds, and approval workflows
 * @notice This contract has a richer implementation than the minimal IAMTTPPolicyEngine interface
 * used by AMTTPRouter. The Router uses a minimal interface for gas efficiency.
 */
contract AMTTPPolicyEngine is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable, 
    ReentrancyGuardUpgradeable
{
    
    // ---------------- Enums ----------------
    enum RiskLevel { Minimal, Low, Medium, High }
    enum PolicyAction { Approve, Review, Escrow, Block }
    enum VelocityWindow { Hour, Day, Week, Month }
    
    // ---------------- Structs ----------------
    struct TransactionPolicy {
        uint256 maxAmount;                    // Maximum transaction amount
        uint256 dailyLimit;                   // 24-hour transaction limit
        uint256 weeklyLimit;                  // 7-day transaction limit
        uint256 monthlyLimit;                 // 30-day transaction limit
        uint256 riskThreshold;                // Risk threshold (0-1000, representing 0-1.0)
        address[] allowedCounterparties;      // Whitelist of addresses
        address[] blockedCounterparties;      // Blacklist of addresses
        bool autoApprove;                     // Auto-approve low risk transactions
        bool enabled;                         // Policy is active
        uint256 cooldownPeriod;               // Time between large transactions
        uint256 lastLargeTransaction;         // Timestamp of last large transaction
    }
    
    struct RiskPolicy {
        uint256 minimalThreshold;             // 0-250 (0-0.25)
        uint256 lowThreshold;                 // 250-400 (0.25-0.40)  
        uint256 mediumThreshold;              // 400-700 (0.40-0.70)
        uint256 highThreshold;                // 700-1000 (0.70-1.0)
        PolicyAction minimalAction;
        PolicyAction lowAction;
        PolicyAction mediumAction;
        PolicyAction highAction;
        bool adaptiveThresholds;              // Adjust thresholds based on user behavior
    }
    
    struct VelocityLimit {
        uint256 maxTransactions;              // Max transactions in window
        uint256 maxVolume;                    // Max volume in window
        VelocityWindow window;                // Time window
        bool enabled;
    }
    
    struct ComplianceRule {
        bool requireKYC;                      // KYC required for transactions
        bool requireApproval;                 // Manual approval required
        uint256 approvalThreshold;            // Amount requiring approval
        address[] approvers;                  // List of approved addresses
        uint256 approvalTimeout;              // Timeout for approvals
        bool geofencing;                      // Geographic restrictions
        string[] allowedCountries;            // Allowed country codes
    }
    
    struct UserActivity {
        uint256 dailyVolume;                  // Today's transaction volume
        uint256 weeklyVolume;                 // This week's volume
        uint256 monthlyVolume;                // This month's volume
        uint256 dailyCount;                   // Today's transaction count
        uint256 lastTransactionTime;         // Last transaction timestamp
        uint256 lastResetTime;                // Last reset timestamp
        uint256 suspiciousScore;              // Cumulative suspicious activity score
        bool frozen;                          // Account frozen status
    }
    
    // ---------------- State Variables ----------------
    mapping(address => TransactionPolicy) public userPolicies;
    mapping(address => RiskPolicy) public userRiskPolicies;
    mapping(address => VelocityLimit[]) public userVelocityLimits;
    mapping(address => ComplianceRule) public userComplianceRules;
    mapping(address => UserActivity) public userActivity;
    mapping(address => mapping(address => bool)) public trustedCounterparties;
    mapping(address => bool) public globalApprovers;
    mapping(address => bool) public trustedUsers;  // Global trusted users list
    
    // Global settings
    uint256 public globalRiskThreshold;
    uint256 public globalMaxAmount;
    bool public emergencyPause;
    address public amttpContract;
    address public oracleService;
    
    // Kleros Dispute Resolution
    address public disputeResolver;  // AMTTPDisputeResolver contract
    uint256 public escrowThreshold;  // Risk score threshold for escrow (default: 700)
    
    // DQN Model integration
    mapping(string => uint256) public modelVersionScores; // Model version -> F1 score
    string public activeModelVersion;
    uint256 public minimumModelScore;                     // Minimum F1 score (e.g., 669 for 0.669)
    
    // ---------------- Events ----------------
    event PolicyUpdated(address indexed user, string policyType);
    event TransactionValidated(address indexed user, address indexed counterparty, uint256 amount, PolicyAction action);
    event RiskThresholdExceeded(address indexed user, uint256 riskScore, uint256 threshold);
    event VelocityLimitExceeded(address indexed user, VelocityWindow window, uint256 amount);
    event AccountFrozen(address indexed user, string reason);
    event AccountUnfrozen(address indexed user);
    event EmergencyPauseToggled(bool paused);
    event ModelVersionUpdated(string version, uint256 f1Score);
    event ComplianceViolation(address indexed user, string reason);
    event TransactionEscrowedForDispute(bytes32 indexed txId, address indexed user, uint256 amount, uint256 riskScore);
    event HighRiskAutoBlocked(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    event MediumRiskFlagged(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    event LowRiskAutoApproved(address indexed user, address indexed counterparty, uint256 amount, uint256 riskScore);
    
    // ---------------- Modifiers ----------------
    modifier onlyAMTTP() {
        require(msg.sender == amttpContract, "Only AMTTP contract");
        _;
    }
    
    modifier notPaused() {
        require(!emergencyPause, "System paused");
        _;
    }
    
    modifier notFrozen(address user) {
        require(!userActivity[user].frozen, "Account frozen");
        _;
    }
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    // ---------------- Initialization ----------------
    function initialize(address _amttpContract, address _oracleService) public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        
        amttpContract = _amttpContract;
        oracleService = _oracleService;
        globalRiskThreshold = 700; // 0.70 default
        globalMaxAmount = 100 ether; // 100 ETH default
        activeModelVersion = "DQN-v1.0-real-fraud";
        minimumModelScore = 669; // 0.669 F1 score minimum
        
        // Set default model score
        modelVersionScores["DQN-v1.0-real-fraud"] = 669;
    }
    
    // ---------------- Policy Management ----------------
    
    /**
     * @dev Set transaction policy for a user
     */
    function setTransactionPolicy(
        address user,
        uint256 maxAmount,
        uint256 dailyLimit,
        uint256 weeklyLimit,
        uint256 monthlyLimit,
        uint256 riskThreshold,
        bool autoApprove,
        uint256 cooldownPeriod
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        require(maxAmount <= globalMaxAmount, "Exceeds global limit");
        require(riskThreshold <= 1000, "Invalid risk threshold");
        
        userPolicies[user] = TransactionPolicy({
            maxAmount: maxAmount,
            dailyLimit: dailyLimit,
            weeklyLimit: weeklyLimit,
            monthlyLimit: monthlyLimit,
            riskThreshold: riskThreshold,
            allowedCounterparties: userPolicies[user].allowedCounterparties,
            blockedCounterparties: userPolicies[user].blockedCounterparties,
            autoApprove: autoApprove,
            enabled: true,
            cooldownPeriod: cooldownPeriod,
            lastLargeTransaction: userPolicies[user].lastLargeTransaction
        });
        
        emit PolicyUpdated(user, "transaction");
    }
    
    /**
     * @dev Set risk policy for a user  
     */
    function setRiskPolicy(
        address user,
        uint256[4] memory thresholds, // [minimal, low, medium, high]
        PolicyAction[4] memory actions,
        bool adaptiveThresholds
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        require(thresholds[0] < thresholds[1] && thresholds[1] < thresholds[2] && thresholds[2] < thresholds[3], "Invalid thresholds");
        
        userRiskPolicies[user] = RiskPolicy({
            minimalThreshold: thresholds[0],
            lowThreshold: thresholds[1],
            mediumThreshold: thresholds[2],
            highThreshold: thresholds[3],
            minimalAction: actions[0],
            lowAction: actions[1],
            mediumAction: actions[2],
            highAction: actions[3],
            adaptiveThresholds: adaptiveThresholds
        });
        
        emit PolicyUpdated(user, "risk");
    }
    
    /**
     * @dev Add velocity limit for a user
     */
    function addVelocityLimit(
        address user,
        uint256 maxTransactions,
        uint256 maxVolume,
        VelocityWindow window
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        
        userVelocityLimits[user].push(VelocityLimit({
            maxTransactions: maxTransactions,
            maxVolume: maxVolume,
            window: window,
            enabled: true
        }));
        
        emit PolicyUpdated(user, "velocity");
    }
    
    /**
     * @dev Set compliance rules for a user
     */
    function setComplianceRules(
        address user,
        bool requireKYC,
        bool requireApproval,
        uint256 approvalThreshold,
        uint256 approvalTimeout,
        bool geofencing
    ) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        
        userComplianceRules[user].requireKYC = requireKYC;
        userComplianceRules[user].requireApproval = requireApproval;
        userComplianceRules[user].approvalThreshold = approvalThreshold;
        userComplianceRules[user].approvalTimeout = approvalTimeout;
        userComplianceRules[user].geofencing = geofencing;
        
        emit PolicyUpdated(user, "compliance");
    }
    
    // ---------------- Transaction Validation ----------------
    
    /**
     * @dev Validate transaction against user policies and DQN risk score
     */
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 dqnRiskScore,        // Risk score from your DQN model (0-1000)
        string memory modelVersion,
        bytes32 kycHash
    ) external onlyAMTTP notPaused notFrozen(user) returns (PolicyAction action, string memory reason) {
        
        // Update user activity
        _updateUserActivity(user, amount);
        
        // Check model version
        require(modelVersionScores[modelVersion] >= minimumModelScore, "Model version not approved");
        
        // Get user policies (with defaults if not set)
        TransactionPolicy memory policy = _getUserPolicyWithDefaults(user);
        RiskPolicy memory riskPolicy = _getUserRiskPolicyWithDefaults(user);
        ComplianceRule memory compliance = userComplianceRules[user];
        
        // 1. Basic policy checks
        if (amount > policy.maxAmount) {
            return (PolicyAction.Block, "Exceeds maximum amount");
        }
        
        // 2. Velocity checks
        if (!_checkVelocityLimits(user, amount)) {
            return (PolicyAction.Block, "Velocity limit exceeded");
        }
        
        // 3. Counterparty checks
        if (_isBlockedCounterparty(user, counterparty)) {
            return (PolicyAction.Block, "Blocked counterparty");
        }
        
        // 4. KYC compliance
        if (compliance.requireKYC && kycHash == bytes32(0)) {
            return (PolicyAction.Block, "KYC required");
        }
        
        // 5. DQN Risk Assessment - Your trained model integration
        PolicyAction riskAction = _assessDQNRisk(dqnRiskScore, riskPolicy);
        
        // 6. HIGH RISK: Auto-block and flag for Kleros dispute
        // Transactions with risk score >= 700 are auto-blocked
        if (riskAction == PolicyAction.Block) {
            emit HighRiskAutoBlocked(user, counterparty, amount, dqnRiskScore);
            emit RiskThresholdExceeded(user, dqnRiskScore, riskPolicy.mediumThreshold);
            // Caller should route to Kleros escrow via routeToKlerosEscrow()
            return (PolicyAction.Block, "HIGH_RISK: Auto-blocked - route to Kleros for dispute");
        }
        
        // 7. MEDIUM RISK: Flag for human review
        // Transactions with risk score 400-699 need manual verification
        if (riskAction == PolicyAction.Review) {
            emit MediumRiskFlagged(user, counterparty, amount, dqnRiskScore);
            return (PolicyAction.Review, "MEDIUM_RISK: Flagged for human review");
        }
        
        // 8. Special approval requirements
        if (compliance.requireApproval && amount >= compliance.approvalThreshold) {
            return (PolicyAction.Review, "Manual approval required");
        }
        
        // 9. Cooldown period for large transactions
        if (amount >= policy.maxAmount / 2 && 
            block.timestamp < policy.lastLargeTransaction + policy.cooldownPeriod) {
            return (PolicyAction.Review, "Cooldown period active");
        }
        
        // 10. Trusted counterparty override (only affects Review → Approve)
        if (trustedCounterparties[user][counterparty] && riskAction == PolicyAction.Review) {
            riskAction = PolicyAction.Approve;
        }
        
        // 11. LOW RISK: Auto-approval for low/minimal risk scores (< 400)
        if (riskAction == PolicyAction.Approve) {
            _recordSuccessfulTransaction(user, amount);
            emit LowRiskAutoApproved(user, counterparty, amount, dqnRiskScore);
            emit TransactionValidated(user, counterparty, amount, PolicyAction.Approve);
            return (PolicyAction.Approve, "LOW_RISK: Auto-approved");
        }
        
        emit TransactionValidated(user, counterparty, amount, riskAction);
        return (riskAction, _getRiskActionReason(dqnRiskScore, riskAction));
    }
    
    /**
     * @dev Assess risk using your DQN model scores
     */
    function _assessDQNRisk(uint256 riskScore, RiskPolicy memory policy) internal pure returns (PolicyAction) {
        if (riskScore <= policy.minimalThreshold) {
            return policy.minimalAction;
        } else if (riskScore <= policy.lowThreshold) {
            return policy.lowAction;
        } else if (riskScore <= policy.mediumThreshold) {
            return policy.mediumAction;
        } else {
            return policy.highAction;
        }
    }
    
    /**
     * @dev Update user activity tracking
     */
    function _updateUserActivity(address user, uint256 amount) internal {
        UserActivity storage activity = userActivity[user];
        
        // Reset counters if new day/week/month
        if (block.timestamp >= activity.lastResetTime + 1 days) {
            activity.dailyVolume = 0;
            activity.dailyCount = 0;
            activity.lastResetTime = block.timestamp;
        }
        
        if (block.timestamp >= activity.lastResetTime + 7 days) {
            activity.weeklyVolume = 0;
        }
        
        if (block.timestamp >= activity.lastResetTime + 30 days) {
            activity.monthlyVolume = 0;
        }
        
        // Update counters
        activity.dailyVolume += amount;
        activity.weeklyVolume += amount;
        activity.monthlyVolume += amount;
        activity.dailyCount += 1;
        activity.lastTransactionTime = block.timestamp;
    }
    
    /**
     * @dev Check velocity limits
     */
    function _checkVelocityLimits(address user, uint256 amount) internal view returns (bool) {
        VelocityLimit[] memory limits = userVelocityLimits[user];
        UserActivity memory activity = userActivity[user];
        
        for (uint i = 0; i < limits.length; i++) {
            if (!limits[i].enabled) continue;
            
            if (limits[i].window == VelocityWindow.Day) {
                if (activity.dailyVolume + amount > limits[i].maxVolume ||
                    activity.dailyCount + 1 > limits[i].maxTransactions) {
                    return false;
                }
            }
            // Add other window checks as needed
        }
        
        return true;
    }
    
    /**
     * @dev Get user policy with defaults
     */
    function _getUserPolicyWithDefaults(address user) internal view returns (TransactionPolicy memory) {
        TransactionPolicy memory policy = userPolicies[user];
        
        if (!policy.enabled) {
            // Return default policy
            policy = TransactionPolicy({
                maxAmount: 10 ether,
                dailyLimit: 50 ether,
                weeklyLimit: 200 ether,
                monthlyLimit: 500 ether,
                riskThreshold: 700, // 0.70
                allowedCounterparties: new address[](0),
                blockedCounterparties: new address[](0),
                autoApprove: true,
                enabled: true,
                cooldownPeriod: 1 hours,
                lastLargeTransaction: 0
            });
        }
        
        return policy;
    }
    
    /**
     * @dev Get user risk policy with defaults
     * 
     * Default policy thresholds:
     * - LOW (0-399): Auto-approve - trusted transactions
     * - MEDIUM (400-699): Review - requires human verification  
     * - HIGH (700-1000): Block - auto-blocked, routed to Kleros escrow
     */
    function _getUserRiskPolicyWithDefaults(address user) internal view returns (RiskPolicy memory) {
        RiskPolicy memory policy = userRiskPolicies[user];
        
        if (policy.highThreshold == 0) {
            // Default risk policy: HIGH = Block, MEDIUM = Review, LOW = Approve
            policy = RiskPolicy({
                minimalThreshold: 200,    // 0-200: Very low risk
                lowThreshold: 400,        // 200-400: Low risk (auto-approve)
                mediumThreshold: 700,     // 400-700: Medium risk (review)
                highThreshold: 1000,      // 700-1000: High risk (auto-block)
                minimalAction: PolicyAction.Approve,  // Very low → approve
                lowAction: PolicyAction.Approve,      // Low → approve
                mediumAction: PolicyAction.Review,    // Medium → human review
                highAction: PolicyAction.Block,       // High → auto-block + Kleros
                adaptiveThresholds: false
            });
        }
        
        return policy;
    }
    
    function _isBlockedCounterparty(address user, address counterparty) internal view returns (bool) {
        address[] memory blocked = userPolicies[user].blockedCounterparties;
        for (uint i = 0; i < blocked.length; i++) {
            if (blocked[i] == counterparty) return true;
        }
        return false;
    }
    
    function _recordSuccessfulTransaction(address user, uint256 amount) internal {
        if (amount >= userPolicies[user].maxAmount / 2) {
            userPolicies[user].lastLargeTransaction = block.timestamp;
        }
    }
    
    function _getRiskActionReason(uint256 riskScore, PolicyAction action) internal pure returns (string memory) {
        if (action == PolicyAction.Approve) return "Low risk - approved";
        if (action == PolicyAction.Review) return "Medium risk - review required";
        if (action == PolicyAction.Escrow) return "High risk - escrow required";
        return "Very high risk - blocked";
    }
    
    // ---------------- DQN Model Management ----------------
    
    /**
     * @dev Update DQN model version and performance score
     */
    function updateModelVersion(string memory version, uint256 f1Score) external {
        require(msg.sender == oracleService || msg.sender == owner(), "Unauthorized");
        require(f1Score >= minimumModelScore, "Model performance too low");
        
        modelVersionScores[version] = f1Score;
        activeModelVersion = version;
        
        emit ModelVersionUpdated(version, f1Score);
    }
    
    /**
     * @dev Set minimum model performance requirement
     */
    function setMinimumModelScore(uint256 score) external onlyOwner {
        require(score <= 1000, "Invalid score");
        minimumModelScore = score;
    }
    
    // ---------------- Admin Functions ----------------
    
    function setEmergencyPause(bool paused) external onlyOwner {
        emergencyPause = paused;
        emit EmergencyPauseToggled(paused);
    }
    
    function freezeAccount(address user, string memory reason) external onlyOwner {
        userActivity[user].frozen = true;
        emit AccountFrozen(user, reason);
    }
    
    function unfreezeAccount(address user) external onlyOwner {
        userActivity[user].frozen = false;
        emit AccountUnfrozen(user);
    }
    
    function addTrustedCounterparty(address user, address counterparty) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        trustedCounterparties[user][counterparty] = true;
    }
    
    function removeTrustedCounterparty(address user, address counterparty) external {
        require(msg.sender == user || msg.sender == owner(), "Unauthorized");
        trustedCounterparties[user][counterparty] = false;
    }
    
    // ---------------- Trusted User Management ----------------
    
    /**
     * @dev Add a user to the global trusted users list
     */
    function addTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = true;
    }
    
    /**
     * @dev Remove a user from the global trusted users list
     */
    function removeTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = false;
    }
    
    /**
     * @dev Check if a user is in the trusted users list
     */
    function isTrustedUser(address user) external view returns (bool) {
        return trustedUsers[user];
    }
    
    // ---------------- View Functions ----------------
    
    function getUserPolicy(address user) external view returns (TransactionPolicy memory) {
        return _getUserPolicyWithDefaults(user);
    }
    
    function getUserRiskPolicy(address user) external view returns (RiskPolicy memory) {
        return _getUserRiskPolicyWithDefaults(user);
    }
    
    function getUserActivity(address user) external view returns (UserActivity memory) {
        return userActivity[user];
    }
    
    function getModelPerformance(string memory version) external view returns (uint256) {
        return modelVersionScores[version];
    }
    
    /**
     * @dev Get policy engine status for tests and UI
     */
    struct PolicyEngineStatus {
        address policyEngineAddress;
        bool enabled;
        uint256 globalThreshold;
        string defaultModel;
    }
    
    function getPolicyEngineStatus() external view returns (PolicyEngineStatus memory) {
        return PolicyEngineStatus({
            policyEngineAddress: address(this),
            enabled: !emergencyPause,
            globalThreshold: globalRiskThreshold,
            defaultModel: activeModelVersion
        });
    }
    
    function isTransactionAllowed(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, string memory reason) {
        if (emergencyPause) return (false, "System paused");
        if (userActivity[user].frozen) return (false, "Account frozen");
        
        TransactionPolicy memory policy = _getUserPolicyWithDefaults(user);
        
        if (amount > policy.maxAmount) return (false, "Exceeds maximum amount");
        if (_isBlockedCounterparty(user, counterparty)) return (false, "Blocked counterparty");
        
        RiskPolicy memory riskPolicy = _getUserRiskPolicyWithDefaults(user);
        PolicyAction action = _assessDQNRisk(riskScore, riskPolicy);
        
        if (action == PolicyAction.Block) return (false, "Risk too high");
        
        return (true, "Transaction allowed");
    }
    
    // ============================================================
    // KLEROS DISPUTE RESOLUTION INTEGRATION
    // ============================================================
    
    /**
     * @dev Set the Kleros dispute resolver contract address
     * @param _disputeResolver Address of AMTTPDisputeResolver contract
     */
    function setDisputeResolver(address _disputeResolver) external onlyOwner {
        require(_disputeResolver != address(0), "Invalid address");
        disputeResolver = _disputeResolver;
    }
    
    /**
     * @dev Set the risk score threshold for escrow routing
     * @param _threshold Risk score (0-1000) above which transactions go to escrow
     */
    function setEscrowThreshold(uint256 _threshold) external onlyOwner {
        require(_threshold <= 1000, "Invalid threshold");
        escrowThreshold = _threshold;
    }
    
    /**
     * @dev Check if a transaction should be routed to Kleros escrow
     * @param riskScore The risk score from ML model (0-1000)
     * @return shouldEscrow Whether transaction should go to dispute resolver
     */
    function shouldRouteToKleros(uint256 riskScore) public view returns (bool shouldEscrow) {
        if (disputeResolver == address(0)) return false;
        if (escrowThreshold == 0) return false;
        return riskScore >= escrowThreshold;
    }
    
    /**
     * @dev Get dispute resolver address
     */
    function getDisputeResolver() external view returns (address) {
        return disputeResolver;
    }
    
    /**
     * @dev Route a high-risk transaction to Kleros escrow for potential dispute
     * @param txId Unique transaction identifier
     * @param recipient Intended recipient
     * @param riskScore Risk score from ML model
     * @param evidenceURI IPFS URI containing ML evidence
     * @return success Whether the escrow was created
     */
    function routeToKlerosEscrow(
        bytes32 txId,
        address recipient,
        uint256 riskScore,
        string calldata evidenceURI
    ) external payable nonReentrant returns (bool success) {
        require(disputeResolver != address(0), "Dispute resolver not set");
        require(msg.value > 0, "No funds sent");
        require(riskScore >= escrowThreshold, "Risk below threshold");
        
        // Call the dispute resolver to escrow funds
        (bool sent, ) = disputeResolver.call{value: msg.value}(
            abi.encodeWithSignature(
                "escrowTransaction(bytes32,address,uint256,string)",
                txId,
                recipient,
                riskScore,
                evidenceURI
            )
        );
        
        require(sent, "Escrow failed");
        
        emit TransactionEscrowedForDispute(txId, msg.sender, msg.value, riskScore);
        
        return true;
    }
    
    // ---------------- Upgrade Authorization ----------------
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    // ════════════════════════════════════════════════════════════════════
    //              STORAGE GAP (Security Enhancement for Upgrades)
    // ════════════════════════════════════════════════════════════════════
    
    /**
     * @dev Reserved storage space for future upgrades.
     * This allows adding new state variables without shifting storage layout.
     */
    uint256[50] private __gap;
}
