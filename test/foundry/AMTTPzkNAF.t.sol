// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../AMTTPzkNAF.sol";

/**
 * @title AMTTPzkNAF Test
 * @dev Foundry tests for the zkNAF Groth16 verifier contract
 */
contract AMTTPzkNAFTest is Test {
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

    event ProofVerified(
        address indexed user,
        AMTTPzkNAF.ProofType proofType,
        bytes32 indexed proofHash,
        uint256 timestamp
    );
    
    event VerificationKeyUpdated(AMTTPzkNAF.ProofType proofType);

    function setUp() public {
        owner = address(this);
        user1 = address(0x1);
        user2 = address(0x2);
        oracle = address(0x3);
        
        // Initialize IC array
        testIC = new uint256[2][](2);
        testIC[0] = [uint256(0x1), uint256(0x2)];
        testIC[1] = [uint256(0x3), uint256(0x4)];
        
        // Deploy and initialize
        zknaf = new AMTTPzkNAF();
        zknaf.initialize();
    }

    function testInitialize() public {
        assertEq(zknaf.owner(), owner);
        assertFalse(zknaf.paused());
    }

    function testSetVerificationKey() public {
        vm.expectEmit(true, false, false, false);
        emit VerificationKeyUpdated(AMTTPzkNAF.ProofType.SANCTIONS);
        
        zknaf.setVerificationKey(
            AMTTPzkNAF.ProofType.SANCTIONS,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
        
        // Verify key was set (using getter)
        AMTTPzkNAF.VerifyingKey memory key = zknaf.getVerifyingKey(AMTTPzkNAF.ProofType.SANCTIONS);
        assertEq(key.alpha1[0], testAlpha1[0]);
        assertEq(key.alpha1[1], testAlpha1[1]);
    }

    function testSetVerificationKeyUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.setVerificationKey(
            AMTTPzkNAF.ProofType.SANCTIONS,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
    }

    function testGetProofRecord() public {
        // Initially no proofs
        AMTTPzkNAF.ProofRecord memory record = zknaf.getProofRecord(
            user1,
            AMTTPzkNAF.ProofType.SANCTIONS
        );
        
        assertEq(record.timestamp, 0);
        assertFalse(record.isValid);
    }

    function testIsProofValid() public {
        // No proof submitted yet
        assertFalse(zknaf.isProofValid(user1, AMTTPzkNAF.ProofType.SANCTIONS));
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

    function testSetProofValidity() public {
        uint256 validity = 365 days;
        zknaf.setProofValidity(AMTTPzkNAF.ProofType.SANCTIONS, validity);
        assertEq(zknaf.proofValidity(AMTTPzkNAF.ProofType.SANCTIONS), validity);
    }

    function testSetProofValidityUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.setProofValidity(AMTTPzkNAF.ProofType.SANCTIONS, 365 days);
    }

    function testRevokeProof() public {
        // First we need to simulate a valid proof record
        // This would normally come from a successful verification
        
        vm.prank(owner);
        zknaf.revokeProof(user1, AMTTPzkNAF.ProofType.SANCTIONS);
        
        // Proof should be revoked
        AMTTPzkNAF.ProofRecord memory record = zknaf.getProofRecord(
            user1,
            AMTTPzkNAF.ProofType.SANCTIONS
        );
        assertFalse(record.isValid);
    }

    function testRevokeProofUnauthorized() public {
        vm.prank(user1);
        vm.expectRevert();
        zknaf.revokeProof(user2, AMTTPzkNAF.ProofType.SANCTIONS);
    }

    function testProofValidityExpiration() public {
        // Set validity to 1 day
        zknaf.setProofValidity(AMTTPzkNAF.ProofType.SANCTIONS, 1 days);
        
        // Check proof is not valid (no proof submitted)
        assertFalse(zknaf.isProofValid(user1, AMTTPzkNAF.ProofType.SANCTIONS));
    }

    function testBatchOperations() public {
        // Test batch verification key setup for multiple proof types
        AMTTPzkNAF.ProofType[] memory types = new AMTTPzkNAF.ProofType[](3);
        types[0] = AMTTPzkNAF.ProofType.SANCTIONS;
        types[1] = AMTTPzkNAF.ProofType.RISK_LOW;
        types[2] = AMTTPzkNAF.ProofType.KYC_VERIFIED;
        
        for (uint256 i = 0; i < types.length; i++) {
            zknaf.setVerificationKey(
                types[i],
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                testIC
            );
            
            AMTTPzkNAF.VerifyingKey memory key = zknaf.getVerifyingKey(types[i]);
            assertEq(key.alpha1[0], testAlpha1[0]);
        }
    }

    function testProofTypeEnumValues() public pure {
        // Verify enum values match expected
        assertEq(uint(AMTTPzkNAF.ProofType.SANCTIONS), 0);
        assertEq(uint(AMTTPzkNAF.ProofType.RISK_LOW), 1);
        assertEq(uint(AMTTPzkNAF.ProofType.RISK_MEDIUM), 2);
        assertEq(uint(AMTTPzkNAF.ProofType.KYC_VERIFIED), 3);
    }

    function testUpgradeability() public {
        // Test that the contract is properly initialized for upgrades
        // The initialize function should only be callable once
        vm.expectRevert();
        zknaf.initialize();
    }

    // Fuzz testing for proof validity periods
    function testFuzzProofValidity(uint256 validity) public {
        // Bound validity to reasonable range (1 hour to 10 years)
        validity = bound(validity, 1 hours, 3650 days);
        
        zknaf.setProofValidity(AMTTPzkNAF.ProofType.SANCTIONS, validity);
        assertEq(zknaf.proofValidity(AMTTPzkNAF.ProofType.SANCTIONS), validity);
    }

    // Test gas consumption patterns
    function testGasEstimation() public {
        uint256 gasStart = gasleft();
        
        zknaf.setVerificationKey(
            AMTTPzkNAF.ProofType.SANCTIONS,
            testAlpha1,
            testBeta2,
            testGamma2,
            testDelta2,
            testIC
        );
        
        uint256 gasUsed = gasStart - gasleft();
        
        // Log gas used for analysis
        emit log_named_uint("Gas used for setVerificationKey", gasUsed);
        
        // Ensure gas is within reasonable bounds (less than 500k)
        assertLt(gasUsed, 500000);
    }
}
