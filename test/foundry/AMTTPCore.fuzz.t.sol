// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../../contracts/AMTTPCore.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title MockERC20 - Test token for fuzz testing
 */
contract MockERC20 is ERC20 {
    constructor() ERC20("MockToken", "MTK") {
        _mint(msg.sender, 1_000_000_000 ether);
    }
    
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/**
 * @title AMTTPCoreFuzzTest - Fuzz testing for AMTTPCore contract
 * @notice Tests critical functions with randomized inputs to find edge cases
 */
contract AMTTPCoreFuzzTest is Test {
    AMTTPCore public implementation;
    AMTTPCore public amttp;
    MockERC20 public token;
    
    address public oracle;
    uint256 public oraclePrivateKey;
    address public buyer;
    address public seller;
    
    // Constants matching contract
    uint256 constant RISK_SCALE = 1000;
    uint256 constant HIGH_RISK_THRESHOLD = 700;
    
    function setUp() public {
        // Create oracle with known private key for signature generation
        oraclePrivateKey = 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef;
        oracle = vm.addr(oraclePrivateKey);
        
        buyer = address(0x1111);
        seller = address(0x2222);
        
        // Deploy implementation
        implementation = new AMTTPCore();
        
        // Deploy proxy and initialize
        bytes memory initData = abi.encodeWithSelector(
            AMTTPCore.initialize.selector,
            oracle
        );
        ERC1967Proxy proxy = new ERC1967Proxy(address(implementation), initData);
        amttp = AMTTPCore(payable(address(proxy)));
        
        // Deploy mock token
        token = new MockERC20();
        
        // Fund accounts
        vm.deal(buyer, 1000 ether);
        vm.deal(seller, 100 ether);
        token.mint(buyer, 1_000_000 ether);
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     HELPER FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════
    
    function _generateOracleSignature(
        address _buyer,
        address _seller,
        uint256 _amount,
        uint256 _riskScore,
        bytes32 _kycHash
    ) internal view returns (bytes memory) {
        bytes32 messageHash = keccak256(abi.encodePacked(_buyer, _seller, _amount, _riskScore, _kycHash));
        bytes32 ethSignedHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(oraclePrivateKey, ethSignedHash);
        return abi.encodePacked(r, s, v);
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - initiateSwap
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test initiateSwap with random amounts
     * @dev Tests that any valid amount can be escrowed
     */
    function testFuzz_InitiateSwap_Amount(uint256 amount) public {
        // Bound amount to reasonable range (avoid overflow and zero)
        amount = bound(amount, 1, 100 ether);
        
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.deal(buyer, amount + 1 ether);
        vm.prank(buyer);
        bytes32 swapId = amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
        
        // Verify swap was created - Swap struct has 11 fields
        (address storedBuyer,,,,,,,,,,) = amttp.swaps(swapId);
        assertEq(storedBuyer, buyer);
    }
    
    /**
     * @notice Fuzz test initiateSwap with random risk scores
     * @dev Tests behavior at different risk levels
     */
    function testFuzz_InitiateSwap_RiskScore(uint256 riskScore) public {
        // Bound to valid range [0, 1000]
        riskScore = bound(riskScore, 0, RISK_SCALE);
        
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.prank(buyer);
        bytes32 swapId = amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
        
        // Verify risk score - get the 10th element (index 9) - riskScore
        (,,,,,,,,,uint256 storedRisk,) = amttp.swaps(swapId);
        assertEq(storedRisk, riskScore);
    }
    
    /**
     * @notice Fuzz test that invalid risk scores are rejected
     */
    function testFuzz_InitiateSwap_InvalidRiskScore(uint256 riskScore) public {
        // Force invalid range (> 1000)
        riskScore = bound(riskScore, RISK_SCALE + 1, type(uint256).max);
        
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        bytes32 kycHash = keccak256("kyc");
        
        // Signature will be invalid but we should revert with InvalidRiskScore first
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.prank(buyer);
        vm.expectRevert(AMTTPCore.InvalidRiskScore.selector);
        amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
    }
    
    /**
     * @notice Fuzz test initiateSwap with random timelocks
     * @dev Tests that only future timelocks are accepted
     */
    function testFuzz_InitiateSwap_Timelock(uint256 timelock) public {
        // Bound to future timestamps
        timelock = bound(timelock, block.timestamp + 1, block.timestamp + 365 days);
        
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.prank(buyer);
        bytes32 swapId = amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
        
        // Verify timelock - get the 9th element (index 8) - timelock
        (,,,,,,,,uint256 storedTimelock,,) = amttp.swaps(swapId);
        assertEq(storedTimelock, timelock);
    }
    
    /**
     * @notice Fuzz test that past timelocks are rejected
     */
    function testFuzz_InitiateSwap_InvalidTimelock(uint256 timelock) public {
        // Bound to past or current timestamps
        timelock = bound(timelock, 0, block.timestamp);
        
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.prank(buyer);
        vm.expectRevert(AMTTPCore.InvalidTimelock.selector);
        amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - completeSwap
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test completeSwap with random preimages
     * @dev Only the correct preimage should succeed
     */
    function testFuzz_CompleteSwap_Preimage(bytes32 preimage, bytes32 wrongPreimage) public {
        // Ensure wrong preimage is actually wrong
        vm.assume(preimage != wrongPreimage);
        vm.assume(preimage != bytes32(0));
        vm.assume(wrongPreimage != bytes32(0));
        
        bytes32 hashlock = keccak256(abi.encodePacked(preimage));
        uint256 amount = 1 ether;
        uint256 timelock = block.timestamp + 1 days;
        // Use risk score >= 700 (HIGH_RISK_THRESHOLD) to keep swap in Pending status
        uint256 riskScore = 750;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        // Create swap
        vm.prank(buyer);
        bytes32 swapId = amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
        
        // Manually approve the swap
        amttp.approveSwap(swapId);
        
        // Wrong preimage should fail
        vm.expectRevert(AMTTPCore.InvalidPreimage.selector);
        amttp.completeSwap(swapId, wrongPreimage);
        
        // Correct preimage should succeed
        uint256 sellerBalanceBefore = seller.balance;
        amttp.completeSwap(swapId, preimage);
        
        assertEq(seller.balance, sellerBalanceBefore + amount);
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - refundSwap
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test refundSwap timing
     * @dev Refund should only work after timelock expires
     */
    function testFuzz_RefundSwap_Timing(uint256 warpTime) public {
        // Bound warp time
        warpTime = bound(warpTime, 0, 365 days);
        
        bytes32 hashlock = keccak256("secret");
        uint256 amount = 1 ether;
        uint256 timelockDuration = 1 days;
        uint256 timelock = block.timestamp + timelockDuration;
        // Use risk score >= 700 (HIGH_RISK_THRESHOLD) to keep in Pending state initially
        uint256 riskScore = 750;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, amount, riskScore, kycHash);
        
        vm.prank(buyer);
        bytes32 swapId = amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, sig);
        
        // Approve the swap first
        amttp.approveSwap(swapId);
        
        // Warp time
        vm.warp(block.timestamp + warpTime);
        
        if (warpTime < timelockDuration) {
            // Should fail - not expired yet
            vm.expectRevert(AMTTPCore.SwapNotExpired.selector);
            amttp.refundSwap(swapId);
        } else {
            // Should succeed - expired
            uint256 buyerBalanceBefore = buyer.balance;
            amttp.refundSwap(swapId);
            assertEq(buyer.balance, buyerBalanceBefore + amount);
        }
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     INVARIANT TESTS
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Invariant: Contract balance should match sum of pending/approved swap amounts
     */
    function testFuzz_Invariant_BalanceIntegrity(
        uint256 amount1,
        uint256 amount2,
        uint256 amount3
    ) public {
        // Bound amounts
        amount1 = bound(amount1, 0.1 ether, 10 ether);
        amount2 = bound(amount2, 0.1 ether, 10 ether);
        amount3 = bound(amount3, 0.1 ether, 10 ether);
        
        uint256 totalEscrowed = 0;
        
        // Create multiple swaps
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        // Swap 1
        bytes memory sig1 = _generateOracleSignature(buyer, seller, amount1, riskScore, kycHash);
        vm.prank(buyer);
        amttp.initiateSwap{value: amount1}(seller, hashlock, timelock, riskScore, kycHash, sig1);
        totalEscrowed += amount1;
        
        // Swap 2 (different hashlock for unique swapId)
        bytes32 hashlock2 = keccak256("secret2");
        bytes memory sig2 = _generateOracleSignature(buyer, seller, amount2, riskScore, kycHash);
        vm.warp(block.timestamp + 1); // Ensure different timestamp
        vm.prank(buyer);
        amttp.initiateSwap{value: amount2}(seller, hashlock2, timelock + 1, riskScore, kycHash, sig2);
        totalEscrowed += amount2;
        
        // Swap 3
        bytes32 hashlock3 = keccak256("secret3");
        bytes memory sig3 = _generateOracleSignature(buyer, seller, amount3, riskScore, kycHash);
        vm.warp(block.timestamp + 1);
        vm.prank(buyer);
        amttp.initiateSwap{value: amount3}(seller, hashlock3, timelock + 2, riskScore, kycHash, sig3);
        totalEscrowed += amount3;
        
        // Invariant: contract balance should equal total escrowed
        assertEq(address(amttp).balance, totalEscrowed);
    }
    
    /**
     * @notice Fuzz test signature verification
     * @dev Random signatures should be rejected (either via custom error or ECDSA error)
     */
    function testFuzz_InvalidSignature(bytes32 r, bytes32 s, uint8 v) public {
        // Create a 65-byte signature with random values
        bytes memory randomSig = abi.encodePacked(r, s, v);
        
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        vm.prank(buyer);
        // Expect any revert - could be InvalidSignature custom error or ECDSA library error
        vm.expectRevert();
        amttp.initiateSwap{value: amount}(seller, hashlock, timelock, riskScore, kycHash, randomSig);
    }
    
    /**
     * @notice Fuzz test that zero amount is rejected
     */
    function testFuzz_ZeroAmount() public {
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, seller, 0, riskScore, kycHash);
        
        vm.prank(buyer);
        vm.expectRevert(AMTTPCore.NoETHSent.selector);
        amttp.initiateSwap{value: 0}(seller, hashlock, timelock, riskScore, kycHash, sig);
    }
    
    /**
     * @notice Fuzz test seller address validation
     */
    function testFuzz_InvalidSeller() public {
        uint256 amount = 1 ether;
        bytes32 hashlock = keccak256("secret");
        uint256 timelock = block.timestamp + 1 days;
        uint256 riskScore = 100;
        bytes32 kycHash = keccak256("kyc");
        
        bytes memory sig = _generateOracleSignature(buyer, address(0), amount, riskScore, kycHash);
        
        vm.prank(buyer);
        vm.expectRevert(AMTTPCore.InvalidSeller.selector);
        amttp.initiateSwap{value: amount}(address(0), hashlock, timelock, riskScore, kycHash, sig);
    }
}
