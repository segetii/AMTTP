// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../../contracts/zknaf/AMTTPzkNAF.sol";
import "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title AMTTPzkNAF Test
 * @dev Foundry tests for the zkNAF Groth16 verifier contract
 */
contract AMTTPzkNAFTest is Test {
    AMTTPzkNAF public implementation;
    AMTTPzkNAF public zknaf;
    
    address public owner;
    address public user1;
    address public user2;
    address public oracle;
    
    // Sample verification key points (test values - not real keys)
    uint256[2] testAlpha1 = [
        0x2260e724844bca5251829f9e8f2d2f2b8b9dc3e6b3b3c7a7e6f8d8d8d8d8d8d8,
        0x1260e724844bca5251829f9e8f2d2f2b8b9dc3e6b3b3c7a7e6f8d8d8d8d8d8d8
    ];
    
    uint256[2][2] testBeta2 = [
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef],
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef]
    ];
    
    uint256[2][2] testGamma2 = [
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef],
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef]
    ];
    
    uint256[2][2] testDelta2 = [
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef],
        [0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef,
         0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef]
    ];
    
    uint256[2][] testIC;

    event VerifyingKeyUpdated(AMTTPzkNAF.ProofType indexed proofType, bytes32 keyHash);
    event OracleAuthorized(address indexed oracle, bool authorized);
    event SanctionsListUpdated(bytes32 indexed newRoot, uint256 timestamp);

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);
        oracle = address(0x3);
        
        // Initialize IC array
        testIC = new uint256[2][](2);
        testIC[0] = [uint256(0x1), uint256(0x2)];
        testIC[1] = [uint256(0x3), uint256(0x4)];
        
        // Deploy implementation
        implementation = new AMTTPzkNAF();
        
        // Deploy proxy and initialize
        bytes memory initData = abi.encodeWithSelector(AMTTPzkNAF.initialize.selector, owner);
        ERC1967Proxy proxy = new ERC1967Proxy(address(implementation), initData);
        zknaf = AMTTPzkNAF(address(proxy));
    }

    function testInitialize() public view {
        assertEq(zknaf.owner(), owner);
        assertFalse(zknaf.paused());
    }

    function testSetVerifyingKey() public {
        assertFalse(zknaf.verifyingKeySet(AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP));
        
        zknaf.setVerifyingKey(
            AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
        
        assertTrue(zknaf.verifyingKeySet(AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP));
    }

    function testSetVerifyingKeyUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.setVerifyingKey(
            AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
    }

    function testHasValidProof() public view {
        // No proof submitted yet
        assertFalse(zknaf.hasValidProof(user1, AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP));
    }

    function testPauseUnpause() public {
        assertFalse(zknaf.paused());
        
        zknaf.pause();
        assertTrue(zknaf.paused());
        
        zknaf.unpause();
        assertFalse(zknaf.paused());
    }

    function testPauseUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.pause();
    }

    function testSetProofValidityDuration() public {
        uint256 validity = 365 days;
        zknaf.setProofValidityDuration(validity);
        assertEq(zknaf.proofValidityDuration(), validity);
    }

    function testSetProofValidityDurationUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.setProofValidityDuration(365 days);
    }

    function testSetAuthorizedOracle() public {
        assertFalse(zknaf.authorizedOracles(oracle));
        
        zknaf.setAuthorizedOracle(oracle, true);
        assertTrue(zknaf.authorizedOracles(oracle));
        
        zknaf.setAuthorizedOracle(oracle, false);
        assertFalse(zknaf.authorizedOracles(oracle));
    }

    function testSetAuthorizedOracleUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.setAuthorizedOracle(oracle, true);
    }

    function testUpdateSanctionsListRoot() public {
        // First authorize the oracle
        zknaf.setAuthorizedOracle(oracle, true);
        
        bytes32 newRoot = keccak256("test_root");
        
        vm.prank(oracle);
        zknaf.updateSanctionsListRoot(newRoot);
        
        assertEq(zknaf.sanctionsListRoot(), newRoot);
    }

    function testUpdateSanctionsListRootUnauthorized() public {
        bytes32 newRoot = keccak256("test_root");
        
        vm.prank(user1); // user1 is not an authorized oracle
        vm.expectRevert(AMTTPzkNAF.NotAuthorizedOracle.selector);
        zknaf.updateSanctionsListRoot(newRoot);
    }

    function testBatchOperations() public {
        // Test setting verification keys for multiple proof types
        AMTTPzkNAF.ProofType[] memory types = new AMTTPzkNAF.ProofType[](3);
        types[0] = AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP;
        types[1] = AMTTPzkNAF.ProofType.RISK_RANGE_LOW;
        types[2] = AMTTPzkNAF.ProofType.KYC_VERIFIED;
        
        for (uint256 i = 0; i < types.length; i++) {
            zknaf.setVerifyingKey(
                types[i],
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                testIC
            );
            
            assertTrue(zknaf.verifyingKeySet(types[i]));
        }
    }

    function testProofTypeEnumValues() public pure {
        // Verify enum values match expected
        assertEq(uint(AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP), 0);
        assertEq(uint(AMTTPzkNAF.ProofType.RISK_RANGE_LOW), 1);
        assertEq(uint(AMTTPzkNAF.ProofType.RISK_RANGE_MEDIUM), 2);
        assertEq(uint(AMTTPzkNAF.ProofType.KYC_VERIFIED), 3);
        assertEq(uint(AMTTPzkNAF.ProofType.TRANSACTION_COMPLIANT), 4);
    }

    function testUpgradeability() public {
        // Test that the contract is properly initialized for upgrades
        // The initialize function should only be callable once
        vm.expectRevert();
        zknaf.initialize(owner);
    }

    // Fuzz testing for proof validity periods
    function testFuzzProofValidityDuration(uint256 validity) public {
        // Bound validity to reasonable range (1 hour to 10 years)
        validity = bound(validity, 1 hours, 3650 days);
        
        zknaf.setProofValidityDuration(validity);
        assertEq(zknaf.proofValidityDuration(), validity);
    }

    // Test gas consumption patterns
    function testGasEstimation() public {
        uint256 gasStart = gasleft();
        
        zknaf.setVerifyingKey(
            AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
        
        uint256 gasUsed = gasStart - gasleft();
        
        // Log gas used for analysis
        emit log_named_uint("Gas used for setVerifyingKey", gasUsed);
        
        // Ensure gas is within reasonable bounds (less than 600k)
        assertLt(gasUsed, 600000);
    }

    function testIsCompliant() public view {
        // No proofs submitted, should not be compliant
        (bool sanctionsProof, bool riskProof, bool kycProof, bool fullyCompliant) = 
            zknaf.isCompliant(user1);
        
        assertFalse(sanctionsProof);
        assertFalse(riskProof);
        assertFalse(kycProof);
        assertFalse(fullyCompliant);
    }

    function testTotalProofsVerified() public view {
        assertEq(zknaf.totalProofsVerified(), 0);
    }

    function testVersion() public view {
        string memory version = zknaf.version();
        assertTrue(bytes(version).length > 0);
    }
    
    function testOwnerIsAuthorizedOracle() public view {
        // Owner should be auto-authorized as oracle during initialization
        assertTrue(zknaf.authorizedOracles(owner));
    }
    
    function testDefaultProofValidityDuration() public view {
        // Default should be 24 hours
        assertEq(zknaf.proofValidityDuration(), 24 hours);
    }
}
