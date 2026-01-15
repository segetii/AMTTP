// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721Receiver.sol";
import "./interfaces/IAMTTP.sol";

/**
 * @title IAMTTPDisputeResolverLocal - Dispute Resolution Interface (local)  
 * @notice Local interface for dispute creation with different signature
 */
interface IAMTTPDisputeResolverLocal {
    function createDispute(
        bytes32 swapId,
        address claimant,
        uint256 amount,
        string calldata evidence
    ) external payable returns (uint256 disputeId);
}

/**
 * @title AMTTPNFT - ERC721 NFT Escrow Contract
 * @notice Handles NFT-to-NFT and NFT-to-ETH swaps with HTLC
 * @dev Part of the unified AMTTP protocol - works with AMTTPRouter
 * 
 * Features:
 * - ERC721 escrow with HTLC (Hash Time-Locked Contracts)
 * - NFT-to-NFT atomic swaps
 * - NFT-to-ETH trades
 * - Oracle signature verification for ML risk scores
 * - Policy Engine integration for risk-based actions
 * - Dispute resolution via Kleros
 * - Multi-approver workflow for high-risk transactions
 */
contract AMTTPNFT is 
    Initializable, 
    OwnableUpgradeable, 
    UUPSUpgradeable, 
    ReentrancyGuardUpgradeable,
    PausableUpgradeable,
    IERC721Receiver,
    IAMTTPNFT
{
    using ECDSA for bytes32;

    // ══════════════════════════════════════════════════════════════════
    //                           CONSTANTS
    // ══════════════════════════════════════════════════════════════════
    uint256 public constant RISK_SCALE = 1000;
    uint256 public constant HIGH_RISK_THRESHOLD = 700;
    uint256 public constant BLOCK_THRESHOLD = 900;
    
    // ══════════════════════════════════════════════════════════════════
    //                           ENUMS
    // ══════════════════════════════════════════════════════════════════
    enum SwapStatus { Pending, Approved, Completed, Refunded, Disputed, Blocked }
    enum SwapType { NFT_TO_ETH, NFT_TO_NFT }
    
    // ══════════════════════════════════════════════════════════════════
    //                           STRUCTS
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice NFT Swap structure for NFT-to-ETH swaps
     */
    struct NFTSwap {
        address seller;          // NFT owner (selling NFT for ETH)
        address buyer;           // ETH sender (buying NFT)
        address nftContract;     // ERC721 contract address
        uint256 tokenId;         // NFT token ID
        uint256 ethAmount;       // ETH amount for the NFT
        bytes32 hashlock;        // HTLC hashlock
        uint256 timelock;        // Expiration timestamp
        uint256 riskScore;       // ML risk score (0-1000)
        bytes32 kycHash;         // KYC verification hash
        SwapStatus status;       // Current status
        uint8 approvalCount;     // Number of approvals
        SwapType swapType;       // Type of swap
    }
    
    /**
     * @notice NFT-to-NFT atomic swap structure
     */
    struct NFTtoNFTSwap {
        address partyA;          // First NFT owner
        address partyB;          // Second NFT owner
        address nftContractA;    // First NFT contract
        address nftContractB;    // Second NFT contract
        uint256 tokenIdA;        // First NFT token ID
        uint256 tokenIdB;        // Second NFT token ID
        bytes32 hashlock;        // HTLC hashlock
        uint256 timelock;        // Expiration timestamp
        uint256 riskScore;       // ML risk score
        SwapStatus status;       // Current status
        bool partyADeposited;    // Party A deposited NFT
        bool partyBDeposited;    // Party B deposited NFT
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                           STATE
    // ══════════════════════════════════════════════════════════════════
    
    // NFT-to-ETH swaps
    mapping(bytes32 => NFTSwap) public nftSwaps;
    mapping(bytes32 => mapping(address => bool)) public approvals;
    
    // NFT-to-NFT swaps
    mapping(bytes32 => NFTtoNFTSwap) public nftToNftSwaps;
    
    // Governance
    address[] public approvers;
    mapping(address => bool) public isApprover;
    uint256 public approvalThreshold;
    
    // Oracle & Policy
    address public oracle;
    IAMTTPPolicyEngine public policyEngine;
    IAMTTPDisputeResolverLocal public disputeResolver;
    bool public policyEngineEnabled;
    
    // Router access
    address public router;
    
    // Model tracking
    string public activeModelVersion;
    uint256 public globalRiskThreshold;
    
    // ══════════════════════════════════════════════════════════════════
    //                           EVENTS
    // ══════════════════════════════════════════════════════════════════
    event NFTSwapInitiated(bytes32 indexed swapId, address indexed seller, address indexed buyer, address nftContract, uint256 tokenId, uint256 ethAmount);
    event NFTtoNFTSwapInitiated(bytes32 indexed swapId, address indexed partyA, address indexed partyB);
    event NFTDeposited(bytes32 indexed swapId, address indexed depositor, address nftContract, uint256 tokenId);
    event SwapApproved(bytes32 indexed swapId, address indexed approver);
    event SwapCompleted(bytes32 indexed swapId);
    event SwapRefunded(bytes32 indexed swapId);
    event SwapDisputed(bytes32 indexed swapId, uint256 disputeId);
    event SwapBlocked(bytes32 indexed swapId, uint256 riskScore, string reason);
    event PolicyEngineUpdated(address indexed newEngine);
    event RouterUpdated(address indexed newRouter);
    
    // ══════════════════════════════════════════════════════════════════
    //                           MODIFIERS
    // ══════════════════════════════════════════════════════════════════
    modifier onlyOracle() {
        require(msg.sender == oracle || msg.sender == owner(), "Not oracle");
        _;
    }
    
    modifier onlyApprover() {
        require(isApprover[msg.sender] || msg.sender == owner(), "Not approver");
        _;
    }
    
    modifier onlyRouterOrDirect() {
        require(msg.sender == router || router == address(0), "Use router");
        _;
    }
    
    modifier swapExists(bytes32 swapId) {
        require(nftSwaps[swapId].seller != address(0), "Swap not found");
        _;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                        INITIALIZATION
    // ══════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize(address _oracle) public initializer {
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();
        
        oracle = _oracle;
        approvalThreshold = 1;
        globalRiskThreshold = HIGH_RISK_THRESHOLD;
        activeModelVersion = "DQN-v1.0";
        policyEngineEnabled = false;
        
        // Add deployer as first approver
        approvers.push(msg.sender);
        isApprover[msg.sender] = true;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     CONFIGURATION FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function setRouter(address _router) external onlyOwner {
        router = _router;
        emit RouterUpdated(_router);
    }
    
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        policyEngine = IAMTTPPolicyEngine(_policyEngine);
        policyEngineEnabled = _policyEngine != address(0);
        emit PolicyEngineUpdated(_policyEngine);
    }
    
    function setDisputeResolver(address _disputeResolver) external onlyOwner {
        disputeResolver = IAMTTPDisputeResolverLocal(_disputeResolver);
    }
    
    function setOracle(address _oracle) external onlyOwner {
        oracle = _oracle;
    }
    
    function addApprover(address _approver) external onlyOwner {
        require(!isApprover[_approver], "Already approver");
        approvers.push(_approver);
        isApprover[_approver] = true;
    }
    
    function removeApprover(address _approver) external onlyOwner {
        require(isApprover[_approver], "Not approver");
        isApprover[_approver] = false;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     NFT-TO-ETH SWAP
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Seller initiates NFT-to-ETH swap by depositing NFT
     * @param buyer Address of the ETH buyer
     * @param nftContract ERC721 contract address
     * @param tokenId Token ID of the NFT
     * @param ethAmount Expected ETH amount
     * @param hashlock HTLC hashlock
     * @param timelock Expiration timestamp
     * @param riskScore ML risk score from oracle
     * @param kycHash KYC verification hash
     * @param oracleSignature Oracle's signature
     */
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
    ) external nonReentrant whenNotPaused returns (bytes32 swapId) {
        require(buyer != address(0), "Invalid buyer");
        require(nftContract != address(0), "Invalid NFT contract");
        require(ethAmount > 0, "Zero ETH amount");
        require(timelock > block.timestamp, "Invalid timelock");
        require(riskScore <= RISK_SCALE, "Invalid risk score");
        
        // Verify oracle signature
        require(_verifyNFTOracleSignature(msg.sender, buyer, nftContract, tokenId, ethAmount, riskScore, kycHash, oracleSignature), "Invalid signature");
        
        swapId = keccak256(abi.encodePacked(msg.sender, buyer, nftContract, tokenId, hashlock, timelock));
        require(nftSwaps[swapId].seller == address(0), "Swap exists");
        
        // Determine status based on risk
        SwapStatus initialStatus = _determineStatus(msg.sender, buyer, ethAmount, riskScore, kycHash);
        
        nftSwaps[swapId] = NFTSwap({
            seller: msg.sender,
            buyer: buyer,
            nftContract: nftContract,
            tokenId: tokenId,
            ethAmount: ethAmount,
            hashlock: hashlock,
            timelock: timelock,
            riskScore: riskScore,
            kycHash: kycHash,
            status: initialStatus,
            approvalCount: 0,
            swapType: SwapType.NFT_TO_ETH
        });
        
        // Transfer NFT to escrow
        IERC721(nftContract).transferFrom(msg.sender, address(this), tokenId);
        
        emit NFTSwapInitiated(swapId, msg.sender, buyer, nftContract, tokenId, ethAmount);
        emit NFTDeposited(swapId, msg.sender, nftContract, tokenId);
        
        if (initialStatus == SwapStatus.Blocked) {
            emit SwapBlocked(swapId, riskScore, "High risk transaction");
        }
        
        return swapId;
    }
    
    /**
     * @notice Buyer deposits ETH to complete the swap
     */
    function depositETHForNFT(bytes32 swapId) external payable nonReentrant swapExists(swapId) {
        NFTSwap storage swap = nftSwaps[swapId];
        require(msg.sender == swap.buyer, "Not buyer");
        require(msg.value == swap.ethAmount, "Wrong ETH amount");
        require(swap.status == SwapStatus.Approved, "Not approved");
        
        // ETH is now in escrow, waiting for preimage reveal
    }
    
    /**
     * @notice Complete NFT-to-ETH swap with preimage
     */
    function completeNFTSwap(bytes32 swapId, bytes32 preimage) external nonReentrant swapExists(swapId) {
        NFTSwap storage swap = nftSwaps[swapId];
        require(swap.status == SwapStatus.Approved, "Not approved");
        require(block.timestamp < swap.timelock, "Expired");
        require(keccak256(abi.encodePacked(preimage)) == swap.hashlock, "Invalid preimage");
        
        swap.status = SwapStatus.Completed;
        
        // Transfer NFT to buyer
        IERC721(swap.nftContract).transferFrom(address(this), swap.buyer, swap.tokenId);
        
        // Transfer ETH to seller
        (bool sent, ) = swap.seller.call{value: swap.ethAmount}("");
        require(sent, "ETH transfer failed");
        
        emit SwapCompleted(swapId);
    }
    
    /**
     * @notice Refund expired NFT swap
     */
    function refundNFTSwap(bytes32 swapId) external nonReentrant swapExists(swapId) {
        NFTSwap storage swap = nftSwaps[swapId];
        require(swap.status == SwapStatus.Pending || swap.status == SwapStatus.Approved, "Cannot refund");
        require(block.timestamp >= swap.timelock, "Not expired");
        
        swap.status = SwapStatus.Refunded;
        
        // Return NFT to seller
        IERC721(swap.nftContract).transferFrom(address(this), swap.seller, swap.tokenId);
        
        // Return ETH to buyer if deposited
        if (address(this).balance >= swap.ethAmount) {
            (bool sent, ) = swap.buyer.call{value: swap.ethAmount}("");
            require(sent, "ETH refund failed");
        }
        
        emit SwapRefunded(swapId);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     NFT-TO-NFT ATOMIC SWAP
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Initiate NFT-to-NFT atomic swap
     */
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
    ) external nonReentrant whenNotPaused returns (bytes32 swapId) {
        require(partyB != address(0), "Invalid party B");
        require(timelock > block.timestamp, "Invalid timelock");
        
        swapId = keccak256(abi.encodePacked(msg.sender, partyB, nftContractA, nftContractB, tokenIdA, tokenIdB, hashlock));
        
        nftToNftSwaps[swapId] = NFTtoNFTSwap({
            partyA: msg.sender,
            partyB: partyB,
            nftContractA: nftContractA,
            nftContractB: nftContractB,
            tokenIdA: tokenIdA,
            tokenIdB: tokenIdB,
            hashlock: hashlock,
            timelock: timelock,
            riskScore: riskScore,
            status: SwapStatus.Pending,
            partyADeposited: false,
            partyBDeposited: false
        });
        
        emit NFTtoNFTSwapInitiated(swapId, msg.sender, partyB);
        
        return swapId;
    }
    
    /**
     * @notice Deposit NFT for NFT-to-NFT swap
     * @dev Uses CEI pattern: state changes before external NFT transfer calls
     */
    function depositNFTForSwap(bytes32 swapId) external nonReentrant {
        NFTtoNFTSwap storage swap = nftToNftSwaps[swapId];
        require(swap.partyA != address(0), "Swap not found");
        require(swap.status == SwapStatus.Pending, "Wrong status");
        
        if (msg.sender == swap.partyA) {
            require(!swap.partyADeposited, "Already deposited");
            // CEI: Update state BEFORE external call
            swap.partyADeposited = true;
            IERC721(swap.nftContractA).transferFrom(msg.sender, address(this), swap.tokenIdA);
            emit NFTDeposited(swapId, msg.sender, swap.nftContractA, swap.tokenIdA);
        } else if (msg.sender == swap.partyB) {
            require(!swap.partyBDeposited, "Already deposited");
            // CEI: Update state BEFORE external call
            swap.partyBDeposited = true;
            IERC721(swap.nftContractB).transferFrom(msg.sender, address(this), swap.tokenIdB);
            emit NFTDeposited(swapId, msg.sender, swap.nftContractB, swap.tokenIdB);
        } else {
            revert("Not party to swap");
        }
        
        // Auto-approve when both NFTs deposited
        if (swap.partyADeposited && swap.partyBDeposited) {
            swap.status = SwapStatus.Approved;
        }
    }
    
    /**
     * @notice Complete NFT-to-NFT swap
     */
    function completeNFTtoNFTSwap(bytes32 swapId, bytes32 preimage) external nonReentrant {
        NFTtoNFTSwap storage swap = nftToNftSwaps[swapId];
        require(swap.status == SwapStatus.Approved, "Not approved");
        require(block.timestamp < swap.timelock, "Expired");
        require(keccak256(abi.encodePacked(preimage)) == swap.hashlock, "Invalid preimage");
        
        swap.status = SwapStatus.Completed;
        
        // Cross-transfer NFTs
        IERC721(swap.nftContractA).transferFrom(address(this), swap.partyB, swap.tokenIdA);
        IERC721(swap.nftContractB).transferFrom(address(this), swap.partyA, swap.tokenIdB);
        
        emit SwapCompleted(swapId);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     APPROVAL WORKFLOW
    // ══════════════════════════════════════════════════════════════════
    
    function approveSwap(bytes32 swapId) external onlyApprover swapExists(swapId) {
        NFTSwap storage swap = nftSwaps[swapId];
        require(swap.status == SwapStatus.Pending, "Not pending");
        require(!approvals[swapId][msg.sender], "Already approved");
        
        approvals[swapId][msg.sender] = true;
        swap.approvalCount++;
        
        emit SwapApproved(swapId, msg.sender);
        
        if (swap.approvalCount >= approvalThreshold) {
            swap.status = SwapStatus.Approved;
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     DISPUTE RESOLUTION
    // ══════════════════════════════════════════════════════════════════
    
    function raiseDispute(bytes32 swapId, string calldata evidence) external payable swapExists(swapId) {
        NFTSwap storage swap = nftSwaps[swapId];
        require(swap.status == SwapStatus.Pending || swap.status == SwapStatus.Approved, "Cannot dispute");
        require(msg.sender == swap.buyer || msg.sender == swap.seller, "Not party to swap");
        require(address(disputeResolver) != address(0), "Dispute resolver not set");
        
        swap.status = SwapStatus.Disputed;
        
        uint256 disputeId = disputeResolver.createDispute{value: msg.value}(
            swapId,
            msg.sender,
            swap.ethAmount,
            evidence
        );
        
        emit SwapDisputed(swapId, disputeId);
    }
    
    function executeDisputeRuling(bytes32 swapId, bool releaseTobuyer) external {
        require(msg.sender == address(disputeResolver), "Only dispute resolver");
        
        NFTSwap storage swap = nftSwaps[swapId];
        require(swap.status == SwapStatus.Disputed, "Not disputed");
        
        if (releaseTobuyer) {
            // Buyer wins: gets NFT
            swap.status = SwapStatus.Completed;
            IERC721(swap.nftContract).transferFrom(address(this), swap.buyer, swap.tokenId);
            emit SwapCompleted(swapId);
        } else {
            // Seller wins: gets NFT back
            swap.status = SwapStatus.Refunded;
            IERC721(swap.nftContract).transferFrom(address(this), swap.seller, swap.tokenId);
            emit SwapRefunded(swapId);
        }
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     RESCUE FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Rescue stuck NFT (admin only)
     */
    function rescueNFT(address nftContract, address to, uint256 tokenId) external onlyOwner {
        IERC721(nftContract).transferFrom(address(this), to, tokenId);
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     INTERNAL FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function _verifyNFTOracleSignature(
        address seller,
        address buyer,
        address nftContract,
        uint256 tokenId,
        uint256 ethAmount,
        uint256 riskScore,
        bytes32 kycHash,
        bytes calldata signature
    ) internal view returns (bool) {
        if (oracle == address(0)) return true;
        
        bytes32 messageHash = keccak256(abi.encodePacked(seller, buyer, nftContract, tokenId, ethAmount, riskScore, kycHash));
        bytes32 ethSignedHash = messageHash.toEthSignedMessageHash();
        address signer = ethSignedHash.recover(signature);
        
        return signer == oracle;
    }
    
    function _determineStatus(
        address seller,
        address buyer,
        uint256 amount,
        uint256 riskScore,
        bytes32 kycHash
    ) internal returns (SwapStatus) {
        if (policyEngineEnabled && address(policyEngine) != address(0)) {
            (IAMTTPPolicyEngine.PolicyAction action, ) = policyEngine.validateTransaction(
                seller, buyer, amount, riskScore, activeModelVersion, kycHash
            );
            
            if (action == IAMTTPPolicyEngine.PolicyAction.Block) {
                return SwapStatus.Blocked;
            } else if (action == IAMTTPPolicyEngine.PolicyAction.Escrow || 
                       action == IAMTTPPolicyEngine.PolicyAction.Review) {
                return SwapStatus.Pending;
            }
            return SwapStatus.Approved;
        }
        
        if (riskScore >= BLOCK_THRESHOLD) {
            return SwapStatus.Blocked;
        } else if (riskScore >= globalRiskThreshold) {
            return SwapStatus.Pending;
        }
        
        return SwapStatus.Approved;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     VIEW FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function getNFTSwap(bytes32 swapId) external view returns (NFTSwap memory) {
        return nftSwaps[swapId];
    }
    
    function getNFTtoNFTSwap(bytes32 swapId) external view returns (NFTtoNFTSwap memory) {
        return nftToNftSwaps[swapId];
    }
    
    function getApprovers() external view returns (address[] memory) {
        return approvers;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ERC721 RECEIVER
    // ══════════════════════════════════════════════════════════════════
    
    function onERC721Received(
        address,
        address,
        uint256,
        bytes calldata
    ) external pure override returns (bytes4) {
        return IERC721Receiver.onERC721Received.selector;
    }
    
    // ══════════════════════════════════════════════════════════════════
    //                     ADMIN FUNCTIONS
    // ══════════════════════════════════════════════════════════════════
    
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    receive() external payable {}
    
    // ══════════════════════════════════════════════════════════════════
    //              STORAGE GAP (Security Enhancement for Upgrades)
    // ══════════════════════════════════════════════════════════════════
    
    /**
     * @dev Reserved storage space for future upgrades.
     * This allows adding new state variables without shifting storage layout.
     */
    uint256[50] private __gap;
}
