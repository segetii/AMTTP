// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IAMTTPCore - Core Protocol Interface
 * @notice Interface for AMTTP core swap functionality
 */
interface IAMTTPCore {
    function initiateSwap(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external payable returns (bytes32 swapId);
    
    function initiateSwapERC20(
        address seller,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external returns (bytes32 swapId);
    
    function completeSwap(bytes32 swapId, bytes32 preimage) external;
    function refundSwap(bytes32 swapId) external;
    function approveSwap(bytes32 swapId) external;
    function raiseDispute(bytes32 swapId, string calldata evidence) external payable;
}

/**
 * @title IAMTTPNFT - NFT Protocol Interface
 * @notice Interface for AMTTP NFT swap functionality
 */
interface IAMTTPNFT {
    function initiateNFTtoETHSwap(
        address buyer,
        address nftContract,
        uint256 tokenId,
        uint256 ethAmount,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external returns (bytes32 swapId);
    
    function initiateNFTtoNFTSwap(
        address partyB,
        address nftContractA,
        uint256 tokenIdA,
        address nftContractB,
        uint256 tokenIdB,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes calldata oracleSignature
    ) external returns (bytes32 swapId);
    
    function depositETHForNFT(bytes32 swapId) external payable;
    function depositNFTForSwap(bytes32 swapId) external;
    function completeNFTSwap(bytes32 swapId, bytes32 preimage) external;
    function completeNFTtoNFTSwap(bytes32 swapId, bytes32 preimage) external;
    function refundNFTSwap(bytes32 swapId) external;
    function approveSwap(bytes32 swapId) external;
    function raiseDispute(bytes32 swapId, string calldata evidence) external payable;
}

/**
 * @title IAMTTPPolicyEngine - Policy Engine Interface
 * @notice Interface for AMTTP risk assessment and policy validation
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
    
    function getGlobalRiskThreshold() external view returns (uint256);
    
    function getUserPolicy(address user) external view returns (
        uint256 dailyLimit, 
        uint256 singleTxLimit, 
        bool kycVerified, 
        bool trusted
    );
}

/**
 * @title IAMTTPPolicy - Policy Manager Interface
 * @notice Interface for user policy management
 */
interface IAMTTPPolicy {
    function setUserPolicy(
        address user,
        uint256 maxAmount,
        uint256 riskThreshold
    ) external;
    
    function getUserPolicy(address user) external view returns (
        uint256 maxAmount,
        uint256 riskThreshold,
        bool trusted
    );
    
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, uint8 recommendedRiskLevel, string memory reason);
    
    function isTransactionAllowed(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool);
}

/**
 * @title IAMTTPCrossChain - Cross-Chain Interface
 * @notice Interface for LayerZero cross-chain operations
 */
interface IAMTTPCrossChain {
    function syncRiskScore(
        uint16 dstChainId, 
        address user, 
        uint256 riskScore, 
        bytes calldata adapterParams
    ) external payable;
    
    function getChainRiskScore(uint16 chainId, address user) external view returns (uint256);
    
    function isGloballyBlocked(address user) external view returns (bool);
}

/**
 * @title IAMTTPDisputeResolver - Dispute Resolution Interface
 * @notice Interface for Kleros dispute resolution
 */
interface IAMTTPDisputeResolver {
    function escrowTransaction(
        bytes32 txId,
        address recipient,
        uint256 riskScore,
        string calldata evidenceURI
    ) external payable;
    
    function challengeTransaction(bytes32 txId) external payable;
    
    function executeTransaction(bytes32 txId) external;
    
    function canExecute(bytes32 txId) external view returns (bool);
}
