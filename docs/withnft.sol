// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/token/ERC721/ERC721Upgradeable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";

// Policy Engine Interface
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
    
    function isTransactionAllowed(
        address user,
        address counterparty,
        uint256 amount,
        uint256 riskScore
    ) external view returns (bool allowed, string memory reason);
}

/**
 * @title AMTTP - Adaptive Multisig Trusted Transaction Protocol
 */
contract AMTTP is Initializable, ERC721Upgradeable, OwnableUpgradeable, UUPSUpgradeable, ReentrancyGuardUpgradeable {
    // FIX: Correct library name
    using ECDSA for bytes32;

    // ---------------- Constants ----------------
    address constant ZERO = address(0);

    // ---------------- Enums ----------------
    enum RiskLevel { None, Low, Medium, High }
    enum AssetType { ETH, ERC20, ERC721 }

    // ---------------- Structs ----------------
    struct Swap {
        address buyer;
        address seller;
        uint256 amount;       // ETH/ERC20 amount
        address token;        // ERC20/ERC721 address
        uint256 tokenId;      // ERC721 tokenId
        bytes32 hashlock;
        uint256 timelock;
        uint8 riskLevel;
        bytes32 kycHash;
        bool completed;
        bool refunded;
        bool frozen;
        AssetType assetType;
    }

    // ---------------- State ----------------
    mapping(bytes32 => Swap) public swaps;
    mapping(bytes32 => mapping(address => bool)) public approvals;
    mapping(bytes32 => uint256) public approvalCounts;

    address[] public approvers;
    uint256 public threshold;
    address public oracle;
    
    // Policy Engine Integration
    IAMTTPPolicyEngine public policyEngine;
    mapping(bytes32 => uint256) public swapRiskScores;        // Track DQN risk scores for swaps
    mapping(bytes32 => string) public swapModelVersions;     // Track model versions used
    mapping(address => bool) public trustedUsers;            // Users with reduced restrictions
    
    // DQN Risk Integration
    uint256 public constant RISK_SCALE = 1000;               // Risk scores scaled to 0-1000
    uint256 public globalRiskThreshold;                      // Global risk threshold (0.70)
    string public defaultModelVersion;                       // Default DQN model version
    bool public policyEngineEnabled;                         // Policy engine enabled flag

    // ---------------- Events ----------------
    event SwapInitiated(
        bytes32 indexed swapId,
        address indexed buyer,
        address indexed seller,
        uint256 amount,
        uint8 riskLevel,
        bytes32 kycHash,
        AssetType assetType
    );
    event SwapCompleted(bytes32 indexed swapId, address indexed seller);
    event SwapRefunded(bytes32 indexed swapId, address indexed buyer);
    event SwapEscalated(bytes32 indexed swapId);
    event Approved(bytes32 indexed swapId, address indexed approver);
    event ApproverAdded(address approver);
    event ApproverRemoved(address approver);
    
    // Policy Engine Events
    event PolicyEngineUpdated(address indexed newPolicyEngine);
    event TransactionPolicyChecked(address indexed user, uint256 amount, uint256 riskScore, string action);
    event RiskThresholdExceeded(bytes32 indexed swapId, uint256 riskScore, uint256 threshold);
    event TrustedUserAdded(address indexed user);
    event TrustedUserRemoved(address indexed user);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    // 1. Remove the 'initialOwner' parameter here
    function initialize() public initializer {
        __ERC721_init("AMTTP", "AMTTP");
        __Ownable_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init(); // Add this line
        
        // Initialize default settings
        threshold = 1;
        globalRiskThreshold = 700; // 0.70 default
        defaultModelVersion = "DQN-v1.0-real-fraud";
        policyEngineEnabled = false; // Start disabled until policy engine is set
    }
    
    // ---------------- Policy Engine Management ----------------
    
    /**
     * @dev Set the policy engine contract address
     */
    function setPolicyEngine(address _policyEngine) external onlyOwner {
        policyEngine = IAMTTPPolicyEngine(_policyEngine);
        policyEngineEnabled = true;
        emit PolicyEngineUpdated(_policyEngine);
    }
    
    /**
     * @dev Enable or disable policy engine
     */
    function setPolicyEngineEnabled(bool enabled) external onlyOwner {
        policyEngineEnabled = enabled;
    }
    
    /**
     * @dev Set global risk threshold (0-1000 scale)
     */
    function setGlobalRiskThreshold(uint256 threshold) external onlyOwner {
        require(threshold <= RISK_SCALE, "Invalid threshold");
        globalRiskThreshold = threshold;
    }
    
    /**
     * @dev Add trusted user (reduced policy restrictions)
     */
    function addTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = true;
        emit TrustedUserAdded(user);
    }
    
    /**
     * @dev Remove trusted user
     */
    function removeTrustedUser(address user) external onlyOwner {
        trustedUsers[user] = false;
        emit TrustedUserRemoved(user);
    }

    // ---------------- Enhanced ETH Swap with Policy Engine ----------------
    function initiateSwap(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig
    ) external payable nonReentrant {
        require(msg.value > 0, "No ETH sent");
        _initiateSwapWithPolicy(msg.sender, seller, msg.value, ZERO, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ETH, 0, defaultModelVersion);
    }
    
    /**
     * @dev Enhanced ETH swap with DQN risk score integration
     */
    function initiateSwapWithRiskScore(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig,
        uint256 dqnRiskScore,
        string memory modelVersion
    ) external payable nonReentrant {
        require(msg.value > 0, "No ETH sent");
        require(dqnRiskScore <= RISK_SCALE, "Invalid risk score");
        _initiateSwapWithPolicy(msg.sender, seller, msg.value, ZERO, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ETH, dqnRiskScore, modelVersion);
    }

    // ---------------- Enhanced ERC20 Swap ----------------
    function initiateSwapERC20(
        address seller,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig
    ) external nonReentrant {
        require(amount > 0, "Zero amount");
        _initiateSwapWithPolicy(msg.sender, seller, amount, token, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ERC20, 0, defaultModelVersion);
        IERC20(token).transferFrom(msg.sender, address(this), amount);
    }
    
    /**
     * @dev Enhanced ERC20 swap with DQN risk score
     */
    function initiateSwapERC20WithRiskScore(
        address seller,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig,
        uint256 dqnRiskScore,
        string memory modelVersion
    ) external nonReentrant {
        require(amount > 0, "Zero amount");
        require(dqnRiskScore <= RISK_SCALE, "Invalid risk score");
        _initiateSwapWithPolicy(msg.sender, seller, amount, token, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ERC20, dqnRiskScore, modelVersion);
        IERC20(token).transferFrom(msg.sender, address(this), amount);
    }

    // ---------------- ERC721 Swap ----------------
    function initiateSwapERC721(
        address seller,
        address token,
        uint256 tokenId,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig
    ) external nonReentrant {
        _initiateSwapInternal(msg.sender, seller, 1, token, tokenId, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ERC721);
        IERC721(token).transferFrom(msg.sender, address(this), tokenId);
    }

    // ---------------- Enhanced Internal Swap Logic with Policy Engine ----------------
    function _initiateSwapWithPolicy(
        address buyer,
        address seller,
        uint256 amount,
        address token,
        uint256 tokenId,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig,
        AssetType assetType,
        uint256 dqnRiskScore,
        string memory modelVersion
    ) internal {
        require(seller != address(0), "Invalid seller");
        require(timelock > block.timestamp, "Invalid timelock");
        require(risk <= uint8(RiskLevel.High), "Invalid risk");

        // FIX: Call the helper function for verification
        require(_verifyOracleSignature(buyer, seller, amount, RiskLevel(risk), kycHash, oracleSig), "Invalid oracle signature");

        // FIX: Use abi.encodePacked for swapId to match test
        bytes32 swapId = keccak256(abi.encodePacked(buyer, seller, hashlock, timelock));
        require(swaps[swapId].buyer == address(0), "Swap exists");

        // Policy Engine Integration - Validate transaction
        if (policyEngineEnabled && address(policyEngine) != address(0)) {
            (IAMTTPPolicyEngine.PolicyAction action, string memory reason) = policyEngine.validateTransaction(
                buyer,
                seller,
                amount,
                dqnRiskScore,
                modelVersion,
                kycHash
            );
            
            emit TransactionPolicyChecked(buyer, amount, dqnRiskScore, reason);
            
            // Handle policy actions
            if (action == IAMTTPPolicyEngine.PolicyAction.Block) {
                revert(string(abi.encodePacked("Transaction blocked: ", reason)));
            } else if (action == IAMTTPPolicyEngine.PolicyAction.Escrow) {
                // Force high risk level for escrow
                risk = uint8(RiskLevel.High);
                emit RiskThresholdExceeded(swapId, dqnRiskScore, globalRiskThreshold);
            } else if (action == IAMTTPPolicyEngine.PolicyAction.Review) {
                // Force medium risk level for review
                if (risk < uint8(RiskLevel.Medium)) {
                    risk = uint8(RiskLevel.Medium);
                }
            }
            // PolicyAction.Approve continues with original risk level
        } else {
            // Fallback policy check if policy engine is disabled
            if (dqnRiskScore > globalRiskThreshold) {
                risk = uint8(RiskLevel.High);
                emit RiskThresholdExceeded(swapId, dqnRiskScore, globalRiskThreshold);
            }
        }

        // Create swap
        swaps[swapId] = Swap({
            buyer: buyer,
            seller: seller,
            amount: amount,
            token: token,
            tokenId: tokenId,
            hashlock: hashlock,
            timelock: timelock,
            riskLevel: risk,
            kycHash: kycHash,
            completed: false,
            refunded: false,
            frozen: false,
            assetType: assetType
        });

        // Store DQN risk data for analytics
        swapRiskScores[swapId] = dqnRiskScore;
        swapModelVersions[swapId] = modelVersion;

        emit SwapInitiated(swapId, buyer, seller, amount, risk, kycHash, assetType);
        
        // Auto-escalate high-risk transactions
        if (risk == uint8(RiskLevel.High) && !trustedUsers[buyer]) {
            emit SwapEscalated(swapId);
        }
    }
    
    // Keep original internal function for backward compatibility
    function _initiateSwapInternal(
        address buyer,
        address seller,
        uint256 amount,
        address token,
        uint256 tokenId,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig,
        AssetType assetType
    ) internal {
        _initiateSwapWithPolicy(buyer, seller, amount, token, tokenId, hashlock, timelock, risk, kycHash, oracleSig, assetType, 0, defaultModelVersion);
    }

    // ---------------- Complete Swap ----------------
    function completeSwap(bytes32 swapId, bytes32 preimage) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(!s.completed, "Already completed");
        require(!s.refunded, "Already refunded");
        require(!s.frozen, "Frozen");
        require(block.timestamp < s.timelock, "Expired");
        // FIX: Use abi.encodePacked for preimage hash
        require(keccak256(abi.encodePacked(preimage)) == s.hashlock, "Invalid preimage");

        if (RiskLevel(s.riskLevel) == RiskLevel.Medium || RiskLevel(s.riskLevel) == RiskLevel.High) {
            require(approvalCounts[swapId] >= threshold, "Not enough approvals");
        }

        s.completed = true;

        if (s.assetType == AssetType.ETH) {
            (bool sent, ) = s.seller.call{value: s.amount}("");
            require(sent, "ETH transfer failed");
        } else if (s.assetType == AssetType.ERC20) {
            IERC20(s.token).transfer(s.seller, s.amount);
        } else if (s.assetType == AssetType.ERC721) {
            IERC721(s.token).transferFrom(address(this), s.seller, s.tokenId);
        }

        emit SwapCompleted(swapId, s.seller);
    }

    // ---------------- Refund ----------------
    function refundSwap(bytes32 swapId) external nonReentrant {
        Swap storage s = swaps[swapId];
        require(!s.completed, "Already completed");
        require(!s.refunded, "Already refunded");
        require(!s.frozen, "Frozen");
        require(block.timestamp >= s.timelock, "Not expired");

        s.refunded = true;

        if (s.assetType == AssetType.ETH) {
            (bool sent, ) = s.buyer.call{value: s.amount}("");
            require(sent, "ETH refund failed");
        } else if (s.assetType == AssetType.ERC20) {
            IERC20(s.token).transfer(s.buyer, s.amount);
        } else if (s.assetType == AssetType.ERC721) {
            IERC721(s.token).transferFrom(address(this), s.buyer, s.tokenId);
        }

        emit SwapRefunded(swapId, s.buyer);
    }

    // ---------------- Rescue ERC721 ----------------
    function rescueERC721(address token, address to, uint256 tokenId) external onlyOwner {
        IERC721(token).transferFrom(address(this), to, tokenId);
    }

    // ---------------- Approvals / Escalation ----------------
    function approveSwap(bytes32 swapId) external {
        require(isApprover(msg.sender), "Not approver");
        require(!approvals[swapId][msg.sender], "Already approved");
        Swap storage s = swaps[swapId];
        require(!s.completed && !s.refunded, "Finalized");

        approvals[swapId][msg.sender] = true;
        approvalCounts[swapId] += 1;

        emit Approved(swapId, msg.sender);
    }

    function escalateSwap(bytes32 swapId) external {
        Swap storage s = swaps[swapId];
        require(msg.sender == s.buyer || msg.sender == s.seller, "Not party");
        require(!s.completed && !s.refunded, "Finalized");
        s.frozen = true;

        emit SwapEscalated(swapId);
    }

    // ---------------- Admin Controls ----------------
    function addApprover(address a) external onlyOwner {
        require(a != address(0), "Zero address");
        approvers.push(a);
        emit ApproverAdded(a);
    }

    function removeApprover(address a) external onlyOwner {
        for (uint256 i = 0; i < approvers.length; i++) {
            if (approvers[i] == a) {
                approvers[i] = approvers[approvers.length - 1];
                approvers.pop();
                emit ApproverRemoved(a);
                break;
            }
        }
    }

    function setThreshold(uint256 t) external onlyOwner {
        require(t <= approvers.length, "Too high");
        threshold = t;
    }

    function setOracle(address o) external onlyOwner {
        require(o != address(0), "Zero address");
        oracle = o;
    }

    // ---------------- Helpers ----------------
    function isApprover(address a) public view returns (bool) {
        for (uint256 i = 0; i < approvers.length; i++) {
            if (approvers[i] == a) return true;
        }
        return false;
    }

    function _verifyOracleSignature(
        address buyer,
        address seller,
        uint256 amount,
        RiskLevel risk,
        bytes32 kycHash,
        bytes memory signature
    ) internal view returns (bool) {
        // FIX: Use abi.encode to match the test file's digest creation
        bytes32 digest = keccak256(abi.encode(buyer, seller, amount, uint8(risk), kycHash));
        bytes32 prefixedDigest = digest.toEthSignedMessageHash();
        address signer = prefixedDigest.recover(signature);
        return signer == oracle && signer != address(0);
    }
    
    // ---------------- Policy & Risk Analytics ----------------
    
    /**
     * @dev Get DQN risk score for a swap
     */
    function getSwapRiskScore(bytes32 swapId) external view returns (uint256 riskScore, string memory modelVersion) {
        return (swapRiskScores[swapId], swapModelVersions[swapId]);
    }
    
    /**
     * @dev Get comprehensive swap details including risk data
     */
    function getSwapWithRiskData(bytes32 swapId) external view returns (
        Swap memory swap,
        uint256 riskScore,
        string memory modelVersion,
        bool requiresApproval
    ) {
        swap = swaps[swapId];
        riskScore = swapRiskScores[swapId];
        modelVersion = swapModelVersions[swapId];
        requiresApproval = (swap.riskLevel >= uint8(RiskLevel.Medium)) && !trustedUsers[swap.buyer];
    }
    
    /**
     * @dev Check if transaction would be allowed under current policies
     */
    function preValidateTransaction(
        address buyer,
        address seller,
        uint256 amount,
        uint256 dqnRiskScore,
        string memory modelVersion,
        bytes32 kycHash
    ) external view returns (bool allowed, string memory reason, uint8 recommendedRiskLevel) {
        if (policyEngineEnabled && address(policyEngine) != address(0)) {
            (bool policyAllowed, string memory policyReason) = policyEngine.isTransactionAllowed(buyer, seller, amount, dqnRiskScore);
            if (!policyAllowed) {
                return (false, policyReason, uint8(RiskLevel.High));
            }
        }
        
        // Fallback risk assessment
        if (dqnRiskScore > globalRiskThreshold) {
            return (true, "High risk - escrow recommended", uint8(RiskLevel.High));
        } else if (dqnRiskScore > globalRiskThreshold * 6 / 10) { // 60% of threshold
            return (true, "Medium risk - review recommended", uint8(RiskLevel.Medium));
        } else {
            return (true, "Low risk - approved", uint8(RiskLevel.Low));
        }
    }
    
    /**
     * @dev Get risk statistics for analytics
     */
    function getRiskStatistics() external view returns (
        uint256 totalSwaps,
        uint256 highRiskSwaps,
        uint256 mediumRiskSwaps,
        uint256 lowRiskSwaps,
        uint256 averageRiskScore
    ) {
        // This would require additional storage optimization for gas efficiency
        // For now, return placeholder values
        totalSwaps = 0; // Would count total swaps
        highRiskSwaps = 0; // Would count high risk swaps
        mediumRiskSwaps = 0; // Would count medium risk swaps  
        lowRiskSwaps = 0; // Would count low risk swaps
        averageRiskScore = 0; // Would calculate average
    }
    
    /**
     * @dev Check if user is trusted
     */
    function isTrustedUser(address user) external view returns (bool) {
        return trustedUsers[user];
    }
    
    /**
     * @dev Get policy engine status
     */
    function getPolicyEngineStatus() external view returns (
        address policyEngineAddress,
        bool enabled,
        uint256 globalThreshold,
        string memory defaultModel
    ) {
        return (
            address(policyEngine),
            policyEngineEnabled,
            globalRiskThreshold,
            defaultModelVersion
        );
    }

    // 4. Add this required function to control upgrades
    function _authorizeUpgrade(address newImplementation)
        internal
        onlyOwner
        override
    {}
}
