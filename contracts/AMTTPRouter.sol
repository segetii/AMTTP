// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";

/**
 * @title IAMTTPCore - Core Protocol Interface
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
 */
interface IAMTTPPolicyEngine {
    function validateTransaction(
        address user,
        address counterparty,
        uint256 amount,
        uint256 dqnRiskScore,
        string memory modelVersion,
        bytes32 kycHash
    ) external returns (uint8 action, string memory reason);
    
    function getGlobalRiskThreshold() external view returns (uint256);
    function getUserPolicy(address user) external view returns (uint256 dailyLimit, uint256 singleTxLimit, bool kycVerified, bool trusted);
}

/**
 * @title IAMTTPCrossChain - Cross-Chain Interface
 */
interface IAMTTPCrossChain {
    function syncRiskScore(uint16 dstChainId, address user, uint256 riskScore, bytes calldata adapterParams) external payable;
    function getChainRiskScore(uint16 chainId, address user) external view returns (uint256);
}

/**
 * @title AMTTPRouter - Unified Entry Point for AMTTP Protocol
 * @notice Single interface for all AMTTP operations across ETH, ERC20, and NFT swaps
 * @dev Routes calls to appropriate sub-contracts based on asset type
 * 
 * Architecture:
 * ┌──────────────────────────────────────────────────────────────────┐
 * │                        AMTTPRouter                               │
 * │  • Unified API for all swap types                                │
 * │  • Analytics aggregation                                         │
 * │  • Cross-contract coordination                                   │
 * └────────────┬─────────────────────┬───────────────────────────────┘
 *              │                     │
 *    ┌─────────▼─────────┐ ┌─────────▼─────────┐
 *    │    AMTTPCore      │ │     AMTTPNFT      │
 *    │   ETH / ERC20     │ │   ERC721 / NFTs   │
 *    └─────────┬─────────┘ └─────────┬─────────┘
 *              │                     │
 *    ┌─────────▼─────────────────────▼─────────┐
 *    │           PolicyEngine                   │
 *    │   Risk Assessment / User Policies        │
 *    └─────────────────┬───────────────────────┘
 *                      │
 *    ┌─────────────────▼───────────────────────┐
 *    │         DisputeResolver (Kleros)         │
 *    └─────────────────────────────────────────┘
 */
contract AMTTPRouter is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable
{
    // ══════════════════════════════════════════════════════════════════
    //                           STATE
    // ══════════════════════════════════════════════════════════════════
    
    // Sub-contracts
    IAMTTPCore public coreContract;
    IAMTTPNFT public nftContract;
    IAMTTPPolicyEngine public policyEngine;
    IAMTTPCrossChain public crossChain;
    
    // Contract addresses for reference
    address public disputeResolver;
    
    // Analytics
    uint256 public totalSwapsInitiated;
    uint256 public totalSwapsCompleted;
    uint256 public totalVolumeETH;
    uint256 public totalVolumeERC20;
    uint256 public totalNFTSwaps;
    
    // Swap tracking
    mapping(bytes32 => SwapType) public swapTypes;
    mapping(address => uint256) public userSwapCount;
    
    enum SwapType { NONE, ETH, ERC20, NFT_TO_ETH, NFT_TO_NFT }
    
    // ══════════════════════════════════════════════════════════════════
    //                           EVENTS
    // ══════════════════════════════════════════════════════════════════
    
    event SwapRouted(bytes32 indexed swapId, SwapType swapType, address indexed initiator);
    event ContractsUpdated(address core, address nft, address policy, address crossChain);
    event AnalyticsUpdated(uint256 totalSwaps, uint256 totalCompleted, uint256 totalVolumeETH);
    
    // ══════════════════════════════════════════════════════════════════
    //                        INITIALIZATION
    // ══════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize(
        address _core,
        address _nft,
        address _policyEngine,
        address _crossChain,
        address _disputeResolver
    ) public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        
        coreContract = IAMTTPCore(_core);
        nftContract = IAMTTPNFT(_nft);
        policyEngine = IAMTTPPolicyEngine(_policyEngine);
        crossChain = IAMTTPCrossChain(_crossChain);
        disputeResolver = _disputeResolver;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     CONFIGURATION
    // ══════════════════════════════════════════════════════════════════
    
    function setContracts(
        address _core,
        address _nft,
        address _policyEngine,
        address _crossChain,
        address _disputeResolver
    ) external onlyOwner {
        if (_core != address(0)) coreContract = IAMTTPCore(_core);
        if (_nft != address(0)) nftContract = IAMTTPNFT(_nft);
        if (_policyEngine != address(0)) policyEngine = IAMTTPPolicyEngine(_policyEngine);
        if (_crossChain != address(0)) crossChain = IAMTTPCrossChain(_crossChain);
        if (_disputeResolver != address(0)) disputeResolver = _disputeResolver;
        
        emit ContractsUpdated(_core, _nft, _policyEngine, _crossChain);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ETH SWAP (via Core)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Initiate ETH swap through unified router
     */
    function swapETH(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external payable nonReentrant returns (bytes32 swapId) {
        require(address(coreContract) != address(0), "Core not set");
        
        swapId = coreContract.initiateSwap{value: msg.value}(
            seller,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature
        );
        
        _recordSwap(swapId, SwapType.ETH, msg.sender, msg.value);
        totalVolumeETH += msg.value;
        
        return swapId;
    }
    
    /**
     * @notice Initiate ERC20 swap through unified router
     */
    function swapERC20(
        address seller,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external nonReentrant returns (bytes32 swapId) {
        require(address(coreContract) != address(0), "Core not set");
        
        swapId = coreContract.initiateSwapERC20(
            seller,
            token,
            amount,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature
        );
        
        _recordSwap(swapId, SwapType.ERC20, msg.sender, amount);
        totalVolumeERC20 += amount;
        
        return swapId;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     NFT SWAPS (via NFT Contract)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Initiate NFT-to-ETH swap (seller deposits NFT)
     */
    function swapNFTforETH(
        address buyer,
        address nftContract_,
        uint256 tokenId,
        uint256 ethAmount,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata oracleSignature
    ) external nonReentrant returns (bytes32 swapId) {
        require(address(nftContract) != address(0), "NFT contract not set");
        
        swapId = nftContract.initiateNFTtoETHSwap(
            buyer,
            nftContract_,
            tokenId,
            ethAmount,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature
        );
        
        _recordSwap(swapId, SwapType.NFT_TO_ETH, msg.sender, ethAmount);
        totalNFTSwaps++;
        
        return swapId;
    }
    
    /**
     * @notice Initiate NFT-to-NFT atomic swap
     */
    function swapNFTforNFT(
        address partyB,
        address nftContractA,
        uint256 tokenIdA,
        address nftContractB,
        uint256 tokenIdB,
        bytes32 hashlock,
        uint256 timelock,
        uint256 riskScore,
        bytes calldata oracleSignature
    ) external nonReentrant returns (bytes32 swapId) {
        require(address(nftContract) != address(0), "NFT contract not set");
        
        swapId = nftContract.initiateNFTtoNFTSwap(
            partyB,
            nftContractA,
            tokenIdA,
            nftContractB,
            tokenIdB,
            hashlock,
            timelock,
            riskScore,
            oracleSignature
        );
        
        _recordSwap(swapId, SwapType.NFT_TO_NFT, msg.sender, 0);
        totalNFTSwaps++;
        
        return swapId;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     SWAP COMPLETION / REFUND
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Complete any swap type with preimage
     */
    function completeSwap(bytes32 swapId, bytes32 preimage) external nonReentrant {
        SwapType sType = swapTypes[swapId];
        require(sType != SwapType.NONE, "Unknown swap");
        
        if (sType == SwapType.ETH || sType == SwapType.ERC20) {
            coreContract.completeSwap(swapId, preimage);
        } else if (sType == SwapType.NFT_TO_ETH) {
            nftContract.completeNFTSwap(swapId, preimage);
        } else if (sType == SwapType.NFT_TO_NFT) {
            nftContract.completeNFTtoNFTSwap(swapId, preimage);
        }
        
        totalSwapsCompleted++;
    }
    
    /**
     * @notice Refund any swap type
     */
    function refundSwap(bytes32 swapId) external nonReentrant {
        SwapType sType = swapTypes[swapId];
        require(sType != SwapType.NONE, "Unknown swap");
        
        if (sType == SwapType.ETH || sType == SwapType.ERC20) {
            coreContract.refundSwap(swapId);
        } else if (sType == SwapType.NFT_TO_ETH || sType == SwapType.NFT_TO_NFT) {
            nftContract.refundNFTSwap(swapId);
        }
    }
    
    /**
     * @notice Approve any swap type (approvers only)
     */
    function approveSwap(bytes32 swapId) external {
        SwapType sType = swapTypes[swapId];
        require(sType != SwapType.NONE, "Unknown swap");
        
        if (sType == SwapType.ETH || sType == SwapType.ERC20) {
            coreContract.approveSwap(swapId);
        } else {
            nftContract.approveSwap(swapId);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     DISPUTE RESOLUTION
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Raise dispute for any swap type
     */
    function raiseDispute(bytes32 swapId, string calldata evidence) external payable {
        SwapType sType = swapTypes[swapId];
        require(sType != SwapType.NONE, "Unknown swap");
        
        if (sType == SwapType.ETH || sType == SwapType.ERC20) {
            coreContract.raiseDispute{value: msg.value}(swapId, evidence);
        } else {
            nftContract.raiseDispute{value: msg.value}(swapId, evidence);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     CROSS-CHAIN OPERATIONS
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Sync risk score to another chain
     */
    function syncRiskToChain(
        uint16 dstChainId,
        address user,
        uint256 riskScore,
        bytes calldata adapterParams
    ) external payable {
        require(address(crossChain) != address(0), "CrossChain not set");
        crossChain.syncRiskScore{value: msg.value}(dstChainId, user, riskScore, adapterParams);
    }
    
    /**
     * @notice Get risk score from another chain
     */
    function getChainRiskScore(uint16 chainId, address user) external view returns (uint256) {
        require(address(crossChain) != address(0), "CrossChain not set");
        return crossChain.getChainRiskScore(chainId, user);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     POLICY QUERIES
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Get global risk threshold
     */
    function getRiskThreshold() external view returns (uint256) {
        require(address(policyEngine) != address(0), "Policy not set");
        return policyEngine.getGlobalRiskThreshold();
    }
    
    /**
     * @notice Get user policy
     */
    function getUserPolicy(address user) external view returns (
        uint256 dailyLimit,
        uint256 singleTxLimit,
        bool kycVerified,
        bool trusted
    ) {
        require(address(policyEngine) != address(0), "Policy not set");
        return policyEngine.getUserPolicy(user);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ANALYTICS
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Get protocol statistics
     */
    function getProtocolStats() external view returns (
        uint256 _totalSwaps,
        uint256 _totalCompleted,
        uint256 _volumeETH,
        uint256 _volumeERC20,
        uint256 _nftSwaps
    ) {
        return (
            totalSwapsInitiated,
            totalSwapsCompleted,
            totalVolumeETH,
            totalVolumeERC20,
            totalNFTSwaps
        );
    }
    
    /**
     * @notice Get all contract addresses
     */
    function getContractAddresses() external view returns (
        address core,
        address nft,
        address policy,
        address crossChainAddr,
        address dispute
    ) {
        return (
            address(coreContract),
            address(nftContract),
            address(policyEngine),
            address(crossChain),
            disputeResolver
        );
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     INTERNAL FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function _recordSwap(bytes32 swapId, SwapType sType, address initiator, uint256 amount) internal {
        swapTypes[swapId] = sType;
        userSwapCount[initiator]++;
        totalSwapsInitiated++;
        
        emit SwapRouted(swapId, sType, initiator);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ADMIN
    // ══════════════════════════════════════════════════════════════════
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    receive() external payable {}
}
