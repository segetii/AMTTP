// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../../contracts/AMTTPPolicyEngine.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title AMTTPPolicyEngineFuzzTest - Fuzz testing for policy engine
 * @notice Tests policy validation with randomized inputs
 */
contract AMTTPPolicyEngineFuzzTest is Test {
    AMTTPPolicyEngine public implementation;
    AMTTPPolicyEngine public policyEngine;
    
    address public owner;
    address public user1;
    address public user2;
    address public amttpCore;
    
    uint256 constant MAX_RISK_SCORE = 1000;
    
    function setUp() public {
        owner = address(this);
        user1 = address(0x1111);
        user2 = address(0x2222);
        amttpCore = address(0x3333);
        
        // Deploy implementation
        implementation = new AMTTPPolicyEngine();
        
        // Deploy proxy and initialize with AMTTP core and oracle
        bytes memory initData = abi.encodeWithSelector(
            AMTTPPolicyEngine.initialize.selector,
            amttpCore,      // _amttpContract
            address(this)   // _oracleService
        );
        ERC1967Proxy proxy = new ERC1967Proxy(address(implementation), initData);
        policyEngine = AMTTPPolicyEngine(address(proxy));
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - Risk Threshold
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test risk threshold validation via user's transaction policy
     * @dev Transactions above threshold should be flagged
     */
    function testFuzz_RiskThreshold(uint256 riskScore, uint256 threshold) public {
        // Bound inputs to valid ranges
        riskScore = bound(riskScore, 0, MAX_RISK_SCORE);
        threshold = bound(threshold, 1, MAX_RISK_SCORE);
        
        // Set user's transaction policy with specific risk threshold
        policyEngine.setTransactionPolicy(
            user1,
            100 ether,     // maxAmount
            1000 ether,    // dailyLimit
            7000 ether,    // weeklyLimit
            30000 ether,   // monthlyLimit
            threshold,     // riskThreshold
            true,          // autoApprove
            0              // cooldownPeriod
        );
        
        // Validate transaction using isTransactionAllowed
        (bool allowed,) = policyEngine.isTransactionAllowed(user1, user2, 1 ether, riskScore);
        
        // Transaction behavior depends on risk policy and threshold
        // This test verifies the function doesn't revert with various inputs
        // Detailed behavior depends on default risk policy actions
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - Amount Limits
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test transaction amount limits
     */
    function testFuzz_AmountLimits(uint256 amount, uint256 maxAmount) public {
        // Bound inputs - must be within globalMaxAmount (100 ether default)
        maxAmount = bound(maxAmount, 1 ether, 100 ether);
        amount = bound(amount, 0, 200 ether);
        
        // Set max transaction amount via user policy
        policyEngine.setTransactionPolicy(
            user1,
            maxAmount,     // maxAmount
            1000 ether,    // dailyLimit
            7000 ether,    // weeklyLimit
            30000 ether,   // monthlyLimit
            500,           // riskThreshold
            true,          // autoApprove
            0              // cooldownPeriod
        );
        
        // Low risk score
        uint256 riskScore = 100;
        (bool allowed,) = policyEngine.isTransactionAllowed(user1, user2, amount, riskScore);
        
        // Transaction should be blocked if amount > maxAmount
        if (amount > maxAmount) {
            assertFalse(allowed, "Transaction exceeding limit should be blocked");
        }
        // Note: could still be blocked for other reasons (risk, etc.)
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - Trusted Users
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test trusted user management
     * @dev Trusted users should be properly tracked
     */
    function testFuzz_TrustedUserManagement(address user) public {
        // Exclude zero address
        vm.assume(user != address(0));
        
        // Initially user should not be trusted
        assertFalse(policyEngine.isTrustedUser(user), "User should not be trusted initially");
        
        // Add user as trusted
        policyEngine.addTrustedUser(user);
        assertTrue(policyEngine.isTrustedUser(user), "User should be trusted");
        
        // Remove user from trusted
        policyEngine.removeTrustedUser(user);
        assertFalse(policyEngine.isTrustedUser(user), "User should not be trusted after removal");
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - Frozen Accounts
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test frozen account functionality
     */
    function testFuzz_FrozenAccount(address frozenUser) public {
        // Exclude zero address
        vm.assume(frozenUser != address(0));
        vm.assume(frozenUser != user2);
        
        // Freeze the account
        policyEngine.freezeAccount(frozenUser, "Suspicious activity");
        
        // Low risk score should still be blocked for frozen accounts
        uint256 riskScore = 10;
        (bool allowed, string memory reason) = policyEngine.isTransactionAllowed(frozenUser, user2, 1 ether, riskScore);
        
        assertFalse(allowed, "Frozen account should be blocked");
        assertEq(reason, "Account frozen");
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     FUZZ TESTS - Compliance Rules
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Fuzz test compliance rules
     */
    function testFuzz_ComplianceRules(uint256 approvalThreshold) public {
        // Bound inputs
        approvalThreshold = bound(approvalThreshold, 1 ether, 100 ether);
        
        // Set compliance rules
        policyEngine.setComplianceRules(
            user1,
            true,               // requireKYC
            true,               // requireApproval
            approvalThreshold,  // approvalThreshold
            1 days,            // approvalTimeout
            false              // geofencing
        );
        
        // Verify rules were set (no revert)
        // The compliance rules are stored and will be used in transaction validation
    }
    
    // ═══════════════════════════════════════════════════════════════════
    //                     INVARIANT TESTS
    // ═══════════════════════════════════════════════════════════════════
    
    /**
     * @notice Invariant: Frozen accounts should always be blocked
     */
    function testFuzz_Invariant_FrozenAccountAlwaysBlocks(
        address user,
        uint256 amount,
        uint256 riskScore
    ) public {
        vm.assume(user != address(0));
        vm.assume(user != user2);
        amount = bound(amount, 0.01 ether, 100 ether);
        riskScore = bound(riskScore, 0, MAX_RISK_SCORE);
        
        // Freeze account
        policyEngine.freezeAccount(user, "Test freeze");
        
        // Should always be blocked regardless of other parameters
        (bool allowed,) = policyEngine.isTransactionAllowed(user, user2, amount, riskScore);
        assertFalse(allowed, "Frozen account should always be blocked");
    }
    
    /**
     * @notice Fuzz test emergency pause
     */
    function testFuzz_EmergencyPause(uint256 riskScore) public {
        riskScore = bound(riskScore, 0, MAX_RISK_SCORE);
        
        // Enable emergency pause
        policyEngine.setEmergencyPause(true);
        
        // All transactions should be blocked during emergency
        (bool allowed, string memory reason) = policyEngine.isTransactionAllowed(user1, user2, 1 ether, riskScore);
        assertFalse(allowed, "Transactions should be blocked during emergency pause");
        assertEq(reason, "System paused");
    }
}
