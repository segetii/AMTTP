// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;

import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC721/IERC721.sol";

/**
 * @title AMTTP - Adaptive Multisig Trusted Transaction Protocol
 */
contract AMTTP is Initializable, OwnableUpgradeable, ReentrancyGuardUpgradeable {
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

    // ---------------- Initializer ----------------
    function initialize(address _oracle, uint256 _threshold) public initializer {
        __Ownable_init();
        __ReentrancyGuard_init();
        oracle = _oracle;
        threshold = _threshold;
    }

    // ---------------- ETH Swap ----------------
    function initiateSwap(
        address seller,
        bytes32 hashlock,
        uint256 timelock,
        uint8 risk,
        bytes32 kycHash,
        bytes calldata oracleSig
    ) external payable nonReentrant {
        require(msg.value > 0, "No ETH sent");
        _initiateSwapInternal(msg.sender, seller, msg.value, ZERO, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ETH);
    }

    // ---------------- ERC20 Swap ----------------
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
        _initiateSwapInternal(msg.sender, seller, amount, token, 0, hashlock, timelock, risk, kycHash, oracleSig, AssetType.ERC20);
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

    // ---------------- Internal Swap Logic ----------------
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
        require(seller != address(0), "Invalid seller");
        require(timelock > block.timestamp, "Invalid timelock");
        require(risk <= uint8(RiskLevel.High), "Invalid risk");

        // FIX: Call the helper function for verification
        require(_verifyOracleSignature(buyer, seller, amount, RiskLevel(risk), kycHash, oracleSig), "Invalid oracle signature");

        // FIX: Use abi.encodePacked for swapId to match test
        bytes32 swapId = keccak256(abi.encodePacked(buyer, seller, hashlock, timelock));
        require(swaps[swapId].buyer == address(0), "Swap exists");

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

        emit SwapInitiated(swapId, buyer, seller, amount, risk, kycHash, assetType);
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
}
