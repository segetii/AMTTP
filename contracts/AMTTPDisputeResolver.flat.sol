// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0 ^0.8.1 ^0.8.20 ^0.8.24;

// node_modules/@openzeppelin/contracts/utils/Address.sol

// OpenZeppelin Contracts (last updated v4.9.0) (utils/Address.sol)

/**
 * @dev Collection of functions related to the address type
 */
library Address {
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

// node_modules/@openzeppelin/contracts/utils/Context.sol

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
abstract contract Context {
    function _msgSender() internal view virtual returns (address) {
        return msg.sender;
    }

    function _msgData() internal view virtual returns (bytes calldata) {
        return msg.data;
    }

    function _contextSuffixLength() internal view virtual returns (uint256) {
        return 0;
    }
}

// node_modules/@openzeppelin/contracts/token/ERC20/IERC20.sol

// OpenZeppelin Contracts (last updated v4.9.0) (token/ERC20/IERC20.sol)

/**
 * @dev Interface of the ERC20 standard as defined in the EIP.
 */
interface IERC20 {
    /**
     * @dev Emitted when `value` tokens are moved from one account (`from`) to
     * another (`to`).
     *
     * Note that `value` may be zero.
     */
    event Transfer(address indexed from, address indexed to, uint256 value);

    /**
     * @dev Emitted when the allowance of a `spender` for an `owner` is set by
     * a call to {approve}. `value` is the new allowance.
     */
    event Approval(address indexed owner, address indexed spender, uint256 value);

    /**
     * @dev Returns the amount of tokens in existence.
     */
    function totalSupply() external view returns (uint256);

    /**
     * @dev Returns the amount of tokens owned by `account`.
     */
    function balanceOf(address account) external view returns (uint256);

    /**
     * @dev Moves `amount` tokens from the caller's account to `to`.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * Emits a {Transfer} event.
     */
    function transfer(address to, uint256 amount) external returns (bool);

    /**
     * @dev Returns the remaining number of tokens that `spender` will be
     * allowed to spend on behalf of `owner` through {transferFrom}. This is
     * zero by default.
     *
     * This value changes when {approve} or {transferFrom} are called.
     */
    function allowance(address owner, address spender) external view returns (uint256);

    /**
     * @dev Sets `amount` as the allowance of `spender` over the caller's tokens.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * IMPORTANT: Beware that changing an allowance with this method brings the risk
     * that someone may use both the old and the new allowance by unfortunate
     * transaction ordering. One possible solution to mitigate this race
     * condition is to first reduce the spender's allowance to 0 and set the
     * desired value afterwards:
     * https://github.com/ethereum/EIPs/issues/20#issuecomment-263524729
     *
     * Emits an {Approval} event.
     */
    function approve(address spender, uint256 amount) external returns (bool);

    /**
     * @dev Moves `amount` tokens from `from` to `to` using the
     * allowance mechanism. `amount` is then deducted from the caller's
     * allowance.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * Emits a {Transfer} event.
     */
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

// node_modules/@openzeppelin/contracts/token/ERC20/extensions/IERC20Permit.sol

// OpenZeppelin Contracts (last updated v4.9.4) (token/ERC20/extensions/IERC20Permit.sol)

/**
 * @dev Interface of the ERC20 Permit extension allowing approvals to be made via signatures, as defined in
 * https://eips.ethereum.org/EIPS/eip-2612[EIP-2612].
 *
 * Adds the {permit} method, which can be used to change an account's ERC20 allowance (see {IERC20-allowance}) by
 * presenting a message signed by the account. By not relying on {IERC20-approve}, the token holder account doesn't
 * need to send a transaction, and thus is not required to hold Ether at all.
 *
 * ==== Security Considerations
 *
 * There are two important considerations concerning the use of `permit`. The first is that a valid permit signature
 * expresses an allowance, and it should not be assumed to convey additional meaning. In particular, it should not be
 * considered as an intention to spend the allowance in any specific way. The second is that because permits have
 * built-in replay protection and can be submitted by anyone, they can be frontrun. A protocol that uses permits should
 * take this into consideration and allow a `permit` call to fail. Combining these two aspects, a pattern that may be
 * generally recommended is:
 *
 * ```solidity
 * function doThingWithPermit(..., uint256 value, uint256 deadline, uint8 v, bytes32 r, bytes32 s) public {
 *     try token.permit(msg.sender, address(this), value, deadline, v, r, s) {} catch {}
 *     doThing(..., value);
 * }
 *
 * function doThing(..., uint256 value) public {
 *     token.safeTransferFrom(msg.sender, address(this), value);
 *     ...
 * }
 * ```
 *
 * Observe that: 1) `msg.sender` is used as the owner, leaving no ambiguity as to the signer intent, and 2) the use of
 * `try/catch` allows the permit to fail and makes the code tolerant to frontrunning. (See also
 * {SafeERC20-safeTransferFrom}).
 *
 * Additionally, note that smart contract wallets (such as Argent or Safe) are not able to produce permit signatures, so
 * contracts should have entry points that don't rely on permit.
 */
interface IERC20Permit {
    /**
     * @dev Sets `value` as the allowance of `spender` over ``owner``'s tokens,
     * given ``owner``'s signed approval.
     *
     * IMPORTANT: The same issues {IERC20-approve} has related to transaction
     * ordering also apply here.
     *
     * Emits an {Approval} event.
     *
     * Requirements:
     *
     * - `spender` cannot be the zero address.
     * - `deadline` must be a timestamp in the future.
     * - `v`, `r` and `s` must be a valid `secp256k1` signature from `owner`
     * over the EIP712-formatted function arguments.
     * - the signature must use ``owner``'s current nonce (see {nonces}).
     *
     * For more information on the signature format, see the
     * https://eips.ethereum.org/EIPS/eip-2612#specification[relevant EIP
     * section].
     *
     * CAUTION: See Security Considerations above.
     */
    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external;

    /**
     * @dev Returns the current nonce for `owner`. This value must be
     * included whenever a signature is generated for {permit}.
     *
     * Every successful call to {permit} increases ``owner``'s nonce by one. This
     * prevents a signature from being used multiple times.
     */
    function nonces(address owner) external view returns (uint256);

    /**
     * @dev Returns the domain separator used in the encoding of the signature for {permit}, as defined by {EIP712}.
     */
    // solhint-disable-next-line func-name-mixedcase
    function DOMAIN_SEPARATOR() external view returns (bytes32);
}

// contracts/interfaces/IKleros.sol

/**
 * @title IArbitrator
 * @notice Kleros Arbitrator interface for dispute resolution
 * @dev See: https://github.com/kleros/kleros-v2
 */
interface IArbitrator {
    /**
     * @dev Create a dispute and pay arbitration fees
     * @param _choices Number of ruling options (2 for approve/reject)
     * @param _extraData Additional data for the arbitrator
     * @return disputeID The ID of the created dispute
     */
    function createDispute(
        uint256 _choices,
        bytes calldata _extraData
    ) external payable returns (uint256 disputeID);
    
    /**
     * @dev Get the cost of arbitration
     * @param _extraData Additional data for the arbitrator
     * @return cost The arbitration cost in wei
     */
    function arbitrationCost(
        bytes calldata _extraData
    ) external view returns (uint256 cost);
    
    /**
     * @dev Get the current ruling for a dispute
     * @param _disputeID The ID of the dispute
     * @return ruling The current ruling (0 = no ruling, 1 = approve, 2 = reject)
     */
    function currentRuling(
        uint256 _disputeID
    ) external view returns (uint256 ruling);
}

/**
 * @title IArbitrable
 * @notice Interface for contracts that can be arbitrated by Kleros
 */
interface IArbitrable {
    /**
     * @dev Emitted when a ruling is given
     * @param _arbitrator The arbitrator giving the ruling
     * @param _disputeID The ID of the dispute
     * @param _ruling The ruling (1 = approve, 2 = reject)
     */
    event Ruling(
        IArbitrator indexed _arbitrator,
        uint256 indexed _disputeID,
        uint256 _ruling
    );
    
    /**
     * @dev Called by the arbitrator to give a ruling
     * @param _disputeID The ID of the dispute
     * @param _ruling The ruling (1 = approve, 2 = reject)
     */
    function rule(uint256 _disputeID, uint256 _ruling) external;
}

/**
 * @title IEvidence
 * @notice Interface for submitting evidence to Kleros disputes
 */
interface IEvidence {
    /**
     * @dev Emitted when evidence is submitted
     */
    event Evidence(
        IArbitrator indexed _arbitrator,
        uint256 indexed _evidenceGroupID,
        address indexed _party,
        string _evidence
    );
    
    /**
     * @dev Emitted when a dispute is created
     */
    event Dispute(
        IArbitrator indexed _arbitrator,
        uint256 indexed _disputeID,
        uint256 _metaEvidenceID,
        uint256 _evidenceGroupID
    );
    
    /**
     * @dev Emitted to link metaevidence to a dispute type
     */
    event MetaEvidence(
        uint256 indexed _metaEvidenceID,
        string _evidence
    );
}

// node_modules/@openzeppelin/contracts/security/ReentrancyGuard.sol

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
abstract contract ReentrancyGuard {
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

    constructor() {
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
}

// node_modules/@openzeppelin/contracts/access/Ownable.sol

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
abstract contract Ownable is Context {
    address private _owner;

    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    /**
     * @dev Initializes the contract setting the deployer as the initial owner.
     */
    constructor() {
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
}

// node_modules/@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol

// OpenZeppelin Contracts (last updated v4.9.3) (token/ERC20/utils/SafeERC20.sol)

/**
 * @title SafeERC20
 * @dev Wrappers around ERC20 operations that throw on failure (when the token
 * contract returns false). Tokens that return no value (and instead revert or
 * throw on failure) are also supported, non-reverting calls are assumed to be
 * successful.
 * To use this library you can add a `using SafeERC20 for IERC20;` statement to your contract,
 * which allows you to call the safe operations as `token.safeTransfer(...)`, etc.
 */
library SafeERC20 {
    using Address for address;

    /**
     * @dev Transfer `value` amount of `token` from the calling contract to `to`. If `token` returns no value,
     * non-reverting calls are assumed to be successful.
     */
    function safeTransfer(IERC20 token, address to, uint256 value) internal {
        _callOptionalReturn(token, abi.encodeWithSelector(token.transfer.selector, to, value));
    }

    /**
     * @dev Transfer `value` amount of `token` from `from` to `to`, spending the approval given by `from` to the
     * calling contract. If `token` returns no value, non-reverting calls are assumed to be successful.
     */
    function safeTransferFrom(IERC20 token, address from, address to, uint256 value) internal {
        _callOptionalReturn(token, abi.encodeWithSelector(token.transferFrom.selector, from, to, value));
    }

    /**
     * @dev Deprecated. This function has issues similar to the ones found in
     * {IERC20-approve}, and its usage is discouraged.
     *
     * Whenever possible, use {safeIncreaseAllowance} and
     * {safeDecreaseAllowance} instead.
     */
    function safeApprove(IERC20 token, address spender, uint256 value) internal {
        // safeApprove should only be called when setting an initial allowance,
        // or when resetting it to zero. To increase and decrease it, use
        // 'safeIncreaseAllowance' and 'safeDecreaseAllowance'
        require(
            (value == 0) || (token.allowance(address(this), spender) == 0),
            "SafeERC20: approve from non-zero to non-zero allowance"
        );
        _callOptionalReturn(token, abi.encodeWithSelector(token.approve.selector, spender, value));
    }

    /**
     * @dev Increase the calling contract's allowance toward `spender` by `value`. If `token` returns no value,
     * non-reverting calls are assumed to be successful.
     */
    function safeIncreaseAllowance(IERC20 token, address spender, uint256 value) internal {
        uint256 oldAllowance = token.allowance(address(this), spender);
        _callOptionalReturn(token, abi.encodeWithSelector(token.approve.selector, spender, oldAllowance + value));
    }

    /**
     * @dev Decrease the calling contract's allowance toward `spender` by `value`. If `token` returns no value,
     * non-reverting calls are assumed to be successful.
     */
    function safeDecreaseAllowance(IERC20 token, address spender, uint256 value) internal {
        unchecked {
            uint256 oldAllowance = token.allowance(address(this), spender);
            require(oldAllowance >= value, "SafeERC20: decreased allowance below zero");
            _callOptionalReturn(token, abi.encodeWithSelector(token.approve.selector, spender, oldAllowance - value));
        }
    }

    /**
     * @dev Set the calling contract's allowance toward `spender` to `value`. If `token` returns no value,
     * non-reverting calls are assumed to be successful. Meant to be used with tokens that require the approval
     * to be set to zero before setting it to a non-zero value, such as USDT.
     */
    function forceApprove(IERC20 token, address spender, uint256 value) internal {
        bytes memory approvalCall = abi.encodeWithSelector(token.approve.selector, spender, value);

        if (!_callOptionalReturnBool(token, approvalCall)) {
            _callOptionalReturn(token, abi.encodeWithSelector(token.approve.selector, spender, 0));
            _callOptionalReturn(token, approvalCall);
        }
    }

    /**
     * @dev Use a ERC-2612 signature to set the `owner` approval toward `spender` on `token`.
     * Revert on invalid signature.
     */
    function safePermit(
        IERC20Permit token,
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) internal {
        uint256 nonceBefore = token.nonces(owner);
        token.permit(owner, spender, value, deadline, v, r, s);
        uint256 nonceAfter = token.nonces(owner);
        require(nonceAfter == nonceBefore + 1, "SafeERC20: permit did not succeed");
    }

    /**
     * @dev Imitates a Solidity high-level call (i.e. a regular function call to a contract), relaxing the requirement
     * on the return value: the return value is optional (but if data is returned, it must not be false).
     * @param token The token targeted by the call.
     * @param data The call data (encoded using abi.encode or one of its variants).
     */
    function _callOptionalReturn(IERC20 token, bytes memory data) private {
        // We need to perform a low level call here, to bypass Solidity's return data size checking mechanism, since
        // we're implementing it ourselves. We use {Address-functionCall} to perform this call, which verifies that
        // the target address contains contract code and also asserts for success in the low-level call.

        bytes memory returndata = address(token).functionCall(data, "SafeERC20: low-level call failed");
        require(returndata.length == 0 || abi.decode(returndata, (bool)), "SafeERC20: ERC20 operation did not succeed");
    }

    /**
     * @dev Imitates a Solidity high-level call (i.e. a regular function call to a contract), relaxing the requirement
     * on the return value: the return value is optional (but if data is returned, it must not be false).
     * @param token The token targeted by the call.
     * @param data The call data (encoded using abi.encode or one of its variants).
     *
     * This is a variant of {_callOptionalReturn} that silents catches all reverts and returns a bool instead.
     */
    function _callOptionalReturnBool(IERC20 token, bytes memory data) private returns (bool) {
        // We need to perform a low level call here, to bypass Solidity's return data size checking mechanism, since
        // we're implementing it ourselves. We cannot use {Address-functionCall} here since this should return false
        // and not revert is the subcall reverts.

        (bool success, bytes memory returndata) = address(token).call(data);
        return
            success && (returndata.length == 0 || abi.decode(returndata, (bool))) && Address.isContract(address(token));
    }
}

// contracts/AMTTPDisputeResolver.sol

/**
 * @title AMTTPDisputeResolver
 * @notice Decentralized dispute resolution for high-risk transactions using Kleros
 * @dev Implements IArbitrable to receive rulings from Kleros Court
 * 
 * Flow:
 * 1. ML/Oracle flags transaction as HIGH_RISK
 * 2. Funds are escrowed in this contract
 * 3. Challenge window opens (e.g., 24 hours)
 * 4. Anyone can challenge → Creates Kleros dispute
 * 5. Kleros jurors vote on evidence
 * 6. Ruling executed: APPROVE (release funds) or REJECT (return to sender)
 */
contract AMTTPDisputeResolver is IArbitrable, IEvidence, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;
    
    // ============================================================
    // CONSTANTS
    // ============================================================
    
    uint256 public constant RULING_OPTIONS = 2;  // Approve or Reject
    uint256 public constant RULING_APPROVE = 1;
    uint256 public constant RULING_REJECT = 2;
    
    // Kleros Court IDs (Sepolia testnet)
    // See: https://docs.kleros.io/products/court/kleros-court-v2
    bytes public constant EXTRA_DATA = abi.encodePacked(
        uint96(0),      // General Court
        uint96(3),      // Min jurors
        uint96(1)       // Dispute kit
    );
    
    // ============================================================
    // STATE
    // ============================================================
    
    IArbitrator public immutable arbitrator;
    
    uint256 public challengeWindow = 24 hours;
    uint256 public metaEvidenceID;
    
    enum EscrowStatus {
        None,
        Pending,        // Waiting for challenge window
        Challenged,     // Dispute created in Kleros
        Resolved,       // Ruling received
        Executed        // Funds transferred
    }
    
    struct EscrowedTransaction {
        bytes32 txId;
        address sender;
        address recipient;
        address token;          // address(0) for ETH, token address for ERC20
        uint256 amount;
        uint256 riskScore;
        uint256 createdAt;
        uint256 challengeDeadline;
        EscrowStatus status;
        uint256 disputeID;
        uint256 ruling;
        uint8 partialPct;       // percentage given to recipient when partial ruling is used (0-100)
        string evidenceURI;     // IPFS link to ML evidence
    }
    
    // txId => EscrowedTransaction
    mapping(bytes32 => EscrowedTransaction) public escrows;
    
    // disputeID => txId (for Kleros callback)
    mapping(uint256 => bytes32) public disputeToTx;
    
    // Evidence group counter
    uint256 public evidenceGroupCounter;
    
    // txId => evidenceGroupID
    mapping(bytes32 => uint256) public txToEvidenceGroup;
    
    // ============================================================
    // EVENTS
    // ============================================================
    
    event TransactionEscrowed(
        bytes32 indexed txId,
        address indexed sender,
        address indexed recipient,
        address token,
        uint256 amount,
        uint256 riskScore,
        uint256 challengeDeadline
    );

    event AppealRequested(bytes32 indexed txId, address indexed requester, uint256 timestamp);
    
    event TransactionChallenged(
        bytes32 indexed txId,
        address indexed challenger,
        uint256 disputeID
    );
    
    event TransactionApproved(
        bytes32 indexed txId,
        address indexed recipient,
        uint256 amount
    );
    
    event TransactionRejected(
        bytes32 indexed txId,
        address indexed sender,
        uint256 amount
    );
    
    event ChallengeWindowExpired(
        bytes32 indexed txId,
        address indexed recipient,
        uint256 amount
    );
    
    // ============================================================
    // CONSTRUCTOR
    // ============================================================
    
    /**
     * @param _arbitrator Address of Kleros Arbitrator contract
     * @param _metaEvidenceURI IPFS URI containing dispute metadata/rules
     */
    constructor(
        address _arbitrator,
        string memory _metaEvidenceURI
    ) {
        require(_arbitrator != address(0), "Invalid arbitrator");
        arbitrator = IArbitrator(_arbitrator);
        
        // Emit MetaEvidence for this dispute type
        emit MetaEvidence(metaEvidenceID, _metaEvidenceURI);
    }
    
    // ============================================================
    // ESCROW FUNCTIONS
    // ============================================================
    
    /**
     * @notice Escrow a high-risk transaction for potential dispute
     * @param _txId Unique transaction identifier
     * @param _recipient Intended recipient of funds
     * @param _riskScore Risk score from ML model (0-1000)
     * @param _evidenceURI IPFS URI with ML evidence (features, signals, etc.)
     */
    function escrowTransaction(
        bytes32 _txId,
        address _recipient,
        uint256 _riskScore,
        string calldata _evidenceURI
    ) external payable nonReentrant {
        require(msg.value > 0, "No funds sent");
        require(_recipient != address(0), "Invalid recipient");
        require(escrows[_txId].status == EscrowStatus.None, "TX already exists");
        
        uint256 deadline = block.timestamp + challengeWindow;
        uint256 evidenceGroup = ++evidenceGroupCounter;
        
        escrows[_txId] = EscrowedTransaction({
            txId: _txId,
            sender: msg.sender,
            recipient: _recipient,
            token: address(0),
            amount: msg.value,
            riskScore: _riskScore,
            createdAt: block.timestamp,
            challengeDeadline: deadline,
            status: EscrowStatus.Pending,
            disputeID: 0,
            ruling: 0,
            partialPct: 0,
            evidenceURI: _evidenceURI
        });
        
        txToEvidenceGroup[_txId] = evidenceGroup;
        
        emit TransactionEscrowed(
            _txId,
            msg.sender,
            _recipient,
            address(0),
            msg.value,
            _riskScore,
            deadline
        );
        
        // Auto-submit ML evidence
        if (bytes(_evidenceURI).length > 0) {
            emit Evidence(arbitrator, evidenceGroup, msg.sender, _evidenceURI);
        }
    }
    
    /**
     * @notice Challenge an escrowed transaction - creates Kleros dispute
     * @param _txId Transaction to challenge
     */
    function challengeTransaction(bytes32 _txId) external payable nonReentrant {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        require(escrow.status == EscrowStatus.Pending, "Not challengeable");
        require(block.timestamp < escrow.challengeDeadline, "Challenge window closed");
        
        // Get arbitration cost
        uint256 arbitrationCost = arbitrator.arbitrationCost(EXTRA_DATA);
        require(msg.value >= arbitrationCost, "Insufficient arbitration fee");
        
        // CEI: Update state BEFORE external call to prevent reentrancy
        escrow.status = EscrowStatus.Challenged;
        
        // Create dispute in Kleros
        uint256 disputeID = arbitrator.createDispute{value: arbitrationCost}(
            RULING_OPTIONS,
            EXTRA_DATA
        );
        
        // Update remaining state after getting disputeID
        escrow.disputeID = disputeID;
        disputeToTx[disputeID] = _txId;
        
        // Emit dispute event for Kleros
        emit Dispute(
            arbitrator,
            disputeID,
            metaEvidenceID,
            txToEvidenceGroup[_txId]
        );
        
        emit TransactionChallenged(_txId, msg.sender, disputeID);
        
        // Refund excess
        if (msg.value > arbitrationCost) {
            payable(msg.sender).transfer(msg.value - arbitrationCost);
        }
    }

    /**
     * @notice Escrow an ERC20 token for potential dispute
     * @param _txId Unique transaction identifier
     * @param _recipient Intended recipient of funds
     * @param _token ERC20 token address
     * @param _amount Amount of tokens to escrow
     * @param _riskScore Risk score from ML model (0-1000)
     * @param _evidenceURI IPFS URI with ML evidence
     */
    function escrowTransactionERC20(
        bytes32 _txId,
        address _recipient,
        address _token,
        uint256 _amount,
        uint256 _riskScore,
        string calldata _evidenceURI
    ) external nonReentrant {
        require(_amount > 0, "No funds sent");
        require(_recipient != address(0), "Invalid recipient");
        require(_token != address(0), "Invalid token");
        require(escrows[_txId].status == EscrowStatus.None, "TX already exists");

        uint256 deadline = block.timestamp + challengeWindow;
        uint256 evidenceGroup = ++evidenceGroupCounter;

        // Transfer tokens to contract
        IERC20(_token).safeTransferFrom(msg.sender, address(this), _amount);

        escrows[_txId] = EscrowedTransaction({
            txId: _txId,
            sender: msg.sender,
            recipient: _recipient,
            token: _token,
            amount: _amount,
            riskScore: _riskScore,
            createdAt: block.timestamp,
            challengeDeadline: deadline,
            status: EscrowStatus.Pending,
            disputeID: 0,
            ruling: 0,
            partialPct: 0,
            evidenceURI: _evidenceURI
        });

        txToEvidenceGroup[_txId] = evidenceGroup;

        emit TransactionEscrowed(
            _txId,
            msg.sender,
            _recipient,
            _token,
            _amount,
            _riskScore,
            deadline
        );

        if (bytes(_evidenceURI).length > 0) {
            emit Evidence(arbitrator, evidenceGroup, msg.sender, _evidenceURI);
        }
    }
    
    /**
     * @notice Submit additional evidence for a dispute
     * @param _txId Transaction ID
     * @param _evidenceURI IPFS URI with evidence
     */
    function submitEvidence(bytes32 _txId, string calldata _evidenceURI) external {
        EscrowedTransaction storage escrow = escrows[_txId];
        require(escrow.status == EscrowStatus.Challenged, "No active dispute");
        require(
            msg.sender == escrow.sender || msg.sender == escrow.recipient,
            "Not a party"
        );
        
        emit Evidence(
            arbitrator,
            txToEvidenceGroup[_txId],
            msg.sender,
            _evidenceURI
        );
    }
    
    // ============================================================
    // KLEROS CALLBACK
    // ============================================================
    
    /**
     * @notice Called by Kleros when jurors reach a ruling
     * @param _disputeID The dispute ID
     * @param _ruling 1 = Approve (release to recipient), 2 = Reject (return to sender)
     */
    function rule(uint256 _disputeID, uint256 _ruling) external override {
        require(msg.sender == address(arbitrator), "Only arbitrator");
        
        bytes32 txId = disputeToTx[_disputeID];
        require(txId != bytes32(0), "Unknown dispute");
        
        EscrowedTransaction storage escrow = escrows[txId];
        require(escrow.status == EscrowStatus.Challenged, "Not challenged");
        
        escrow.status = EscrowStatus.Resolved;
        escrow.ruling = _ruling;
        
    // If arbitrator provided extra metadata indicating a partial pct, we don't have it here.
    // Owners/operators can set defaultPartialPct per-escrow in advance if needed via setEscrowPartialPct.
        
        emit Ruling(arbitrator, _disputeID, _ruling);
        
        // Execute ruling
        _executeRuling(txId);
    }
    
    // ============================================================
    // EXECUTION
    // ============================================================
    
    /**
     * @notice Execute the ruling or release after challenge window
     * @param _txId Transaction to execute
     */
    function executeTransaction(bytes32 _txId) external nonReentrant {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        if (escrow.status == EscrowStatus.Pending) {
            // No challenge - release after window expires
            require(
                block.timestamp >= escrow.challengeDeadline,
                "Challenge window active"
            );
            
            // Cache values before state change (CEI pattern)
            address recipient = escrow.recipient;
            uint256 amount = escrow.amount;
            
            escrow.status = EscrowStatus.Executed;
            
            // Emit event BEFORE external call (CEI pattern)
            emit ChallengeWindowExpired(_txId, recipient, amount);
            
            payable(recipient).transfer(amount);
            
        } else if (escrow.status == EscrowStatus.Resolved) {
            _executeRuling(_txId);
        } else {
            revert("Cannot execute");
        }
    }

    /**
     * @notice Request an appeal (off-chain coordination required to submit evidence to Kleros)
     * @param _txId Transaction ID to appeal
     */
    function requestAppeal(bytes32 _txId) external {
        EscrowedTransaction storage escrow = escrows[_txId];
        require(escrow.status == EscrowStatus.Resolved, "Not resolved");
        require(msg.sender == escrow.sender || msg.sender == escrow.recipient, "Not a party");

        emit AppealRequested(_txId, msg.sender, block.timestamp);
    }

    /**
     * @notice Set partial percentage for an escrow (only owner/operator). Useful when arbitrator indicates partial split off-chain.
     */
    function setEscrowPartialPct(bytes32 _txId, uint8 _pct) external onlyOwner {
        require(_pct <= 100, "Invalid pct");
        EscrowedTransaction storage escrow = escrows[_txId];
        escrow.partialPct = _pct;
    }
    
    function _executeRuling(bytes32 _txId) internal {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        if (escrow.status == EscrowStatus.Executed) return;
        
        escrow.status = EscrowStatus.Executed;
        
        // Cache values to prevent reentrancy issues
        address recipient = escrow.recipient;
        address sender = escrow.sender;
        uint256 amount = escrow.amount;
        address token = escrow.token;
        uint256 ruling = escrow.ruling;
        uint256 pct = escrow.partialPct;
        
        if (ruling == RULING_APPROVE) {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionApproved(_txId, recipient, amount);
            // Explicitly approved by arbitrator - release to recipient
            if (token == address(0)) {
                payable(recipient).transfer(amount);
            } else {
                IERC20(token).safeTransfer(recipient, amount);
            }
        } else if (ruling == RULING_REJECT) {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionRejected(_txId, sender, amount);
            // Reject - return to sender
            if (token == address(0)) {
                payable(sender).transfer(amount);
            } else {
                IERC20(token).safeTransfer(sender, amount);
            }
        } else if (ruling == 3) {
            // Partial ruling - use partialPct stored on escrow (default 0 means fully reject)
            if (pct == 0) {
                // Emit event BEFORE external call (CEI pattern)
                emit TransactionRejected(_txId, sender, amount);
                // treat as reject
                if (token == address(0)) {
                    payable(sender).transfer(amount);
                } else {
                    IERC20(token).safeTransfer(sender, amount);
                }
            } else {
                uint256 toRecipient = (amount * pct) / 100;
                uint256 toSender = amount - toRecipient;
                // Emit events BEFORE external calls (CEI pattern)
                emit TransactionApproved(_txId, recipient, toRecipient);
                emit TransactionRejected(_txId, sender, toSender);
                if (token == address(0)) {
                    if (toRecipient > 0) payable(recipient).transfer(toRecipient);
                    if (toSender > 0) payable(sender).transfer(toSender);
                } else {
                    if (toRecipient > 0) IERC20(token).safeTransfer(recipient, toRecipient);
                    if (toSender > 0) IERC20(token).safeTransfer(sender, toSender);
                }
            }
        } else {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionRejected(_txId, sender, amount);
            // Unknown ruling - default to reject
            if (token == address(0)) {
                payable(sender).transfer(amount);
            } else {
                IERC20(token).safeTransfer(sender, amount);
            }
        }
    }
    
    // ============================================================
    // VIEW FUNCTIONS
    // ============================================================
    
    /**
     * @notice Get the cost to challenge a transaction
     */
    function getChallengeCost() external view returns (uint256) {
        return arbitrator.arbitrationCost(EXTRA_DATA);
    }
    
    /**
     * @notice Get escrow details
     */
    function getEscrow(bytes32 _txId) external view returns (
        address sender,
        address recipient,
        address token,
        uint256 amount,
        uint256 riskScore,
        uint256 challengeDeadline,
        EscrowStatus status,
        uint256 disputeID,
        uint256 ruling
    ) {
        EscrowedTransaction storage e = escrows[_txId];
        return (
            e.sender,
            e.recipient,
            e.token,
            e.amount,
            e.riskScore,
            e.challengeDeadline,
            e.status,
            e.disputeID,
            e.ruling
        );
    }
    
    /**
     * @notice Check if transaction can be executed
     */
    function canExecute(bytes32 _txId) external view returns (bool) {
        EscrowedTransaction storage e = escrows[_txId];
        
        if (e.status == EscrowStatus.Pending) {
            return block.timestamp >= e.challengeDeadline;
        } else if (e.status == EscrowStatus.Resolved) {
            return true;
        }
        return false;
    }
    
    // ============================================================
    // ADMIN
    // ============================================================
    
    /**
     * @notice Update challenge window (owner only)
     */
    function setChallengeWindow(uint256 _window) external onlyOwner {
        require(_window >= 1 hours && _window <= 7 days, "Invalid window");
        challengeWindow = _window;
    }
    
    /**
     * @notice Update meta evidence for new dispute types
     */
    function updateMetaEvidence(string calldata _uri) external onlyOwner {
        metaEvidenceID++;
        emit MetaEvidence(metaEvidenceID, _uri);
    }
    
    /**
     * @notice Emergency withdraw (owner only, for stuck funds)
     * @dev Returns funds to original sender after 30 days past deadline
     */
    function emergencyWithdraw(bytes32 _txId) external onlyOwner nonReentrant {
        EscrowedTransaction storage e = escrows[_txId];
        require(e.status != EscrowStatus.Executed, "Already executed");
        require(
            block.timestamp > e.challengeDeadline + 30 days,
            "Too early"
        );
        
        // Cache values before state change (CEI pattern)
        address sender = e.sender;
        uint256 amount = e.amount;
        address token = e.token;
        
        e.status = EscrowStatus.Executed;
        
        // Emit event BEFORE external call (CEI pattern)
        emit TransactionRejected(_txId, sender, amount);
        
        // SECURITY FIX: Return funds to original sender, not owner
        if (token == address(0)) {
            payable(sender).transfer(amount);
        } else {
            IERC20(token).safeTransfer(sender, amount);
        }
    }
    
    // ============================================================
    // HEALTH CHECK & ANALYTICS
    // ============================================================
    
    /**
     * @notice Get contract health status for monitoring
     * @return arbitratorAddress The Kleros arbitrator address
     * @return currentChallengeWindow Current challenge window duration
     * @return currentMetaEvidenceID Current meta evidence version
     * @return contractBalance ETH balance held in contract
     * @return isOperational Whether the contract can accept new escrows
     */
    function healthCheck() external view returns (
        address arbitratorAddress,
        uint256 currentChallengeWindow,
        uint256 currentMetaEvidenceID,
        uint256 contractBalance,
        bool isOperational
    ) {
        return (
            address(arbitrator),
            challengeWindow,
            metaEvidenceID,
            address(this).balance,
            address(arbitrator) != address(0)
        );
    }
    
    /**
     * @notice Get token balance held in contract (for ERC20 escrows)
     * @param _token Token address to check
     */
    function getTokenBalance(address _token) external view returns (uint256) {
        return IERC20(_token).balanceOf(address(this));
    }
}
