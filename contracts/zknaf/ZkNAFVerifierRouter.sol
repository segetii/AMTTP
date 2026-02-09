// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title ZkNAFVerifierRouter
 * @notice Routes ZK proof verification to the appropriate Groth16 verifier
 * @dev Integrates sanctions, risk, and KYC verifiers for AMTTP compliance
 * 
 * FCA COMPLIANCE:
 * - Sanctions: MLR 2017 reg. 33 - Customer screening against sanctions lists
 * - Risk: MLR 2017 reg. 28(11) - Risk-based transaction monitoring
 * - KYC: MLR 2017 reg. 28 - Customer due diligence requirements
 */

interface IGroth16Verifier {
    function verifyProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[] calldata _pubSignals
    ) external view returns (bool);
}

contract ZkNAFVerifierRouter {
    // ═══════════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════════
    
    address public owner;
    
    IGroth16Verifier public sanctionsVerifier;
    IGroth16Verifier public riskVerifier;
    IGroth16Verifier public kycVerifier;
    
    // Proof type registry
    mapping(bytes32 => bool) public usedProofs;
    
    // ═══════════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════════
    
    event SanctionsProofVerified(address indexed user, bytes32 proofHash, uint256 timestamp);
    event RiskProofVerified(address indexed user, bytes32 proofHash, uint8 riskLevel, uint256 timestamp);
    event KYCProofVerified(address indexed user, bytes32 proofHash, uint256 timestamp);
    event VerifierUpdated(string verifierType, address oldAddress, address newAddress);
    
    // ═══════════════════════════════════════════════════════════════════════════
    // MODIFIERS
    // ═══════════════════════════════════════════════════════════════════════════
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    // ═══════════════════════════════════════════════════════════════════════════
    // CONSTRUCTOR
    // ═══════════════════════════════════════════════════════════════════════════
    
    constructor(
        address _sanctionsVerifier,
        address _riskVerifier,
        address _kycVerifier
    ) {
        owner = msg.sender;
        sanctionsVerifier = IGroth16Verifier(_sanctionsVerifier);
        riskVerifier = IGroth16Verifier(_riskVerifier);
        kycVerifier = IGroth16Verifier(_kycVerifier);
    }
    
    // ═══════════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════
    
    function updateSanctionsVerifier(address _newVerifier) external onlyOwner {
        emit VerifierUpdated("sanctions", address(sanctionsVerifier), _newVerifier);
        sanctionsVerifier = IGroth16Verifier(_newVerifier);
    }
    
    function updateRiskVerifier(address _newVerifier) external onlyOwner {
        emit VerifierUpdated("risk", address(riskVerifier), _newVerifier);
        riskVerifier = IGroth16Verifier(_newVerifier);
    }
    
    function updateKYCVerifier(address _newVerifier) external onlyOwner {
        emit VerifierUpdated("kyc", address(kycVerifier), _newVerifier);
        kycVerifier = IGroth16Verifier(_newVerifier);
    }
    
    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "Invalid owner");
        owner = _newOwner;
    }
    
    // ═══════════════════════════════════════════════════════════════════════════
    // VERIFICATION FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Verify a sanctions non-membership proof
     * @param _pA Proof element A
     * @param _pB Proof element B
     * @param _pC Proof element C
     * @param _pubSignals Public signals [isNotSanctioned, proofTimestamp, sanctionsRoot, timestamp]
     * @return valid True if proof is valid and user is not sanctioned
     */
    function verifySanctionsProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[] calldata _pubSignals
    ) external returns (bool valid) {
        require(address(sanctionsVerifier) != address(0), "Sanctions verifier not set");
        require(_pubSignals.length >= 4, "Invalid public signals");
        
        // Verify the proof
        valid = sanctionsVerifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        
        if (valid) {
            // Check that isNotSanctioned = 1
            require(_pubSignals[0] == 1, "User is sanctioned");
            
            // Record proof usage
            bytes32 proofHash = keccak256(abi.encodePacked(_pA, _pB, _pC));
            require(!usedProofs[proofHash], "Proof already used");
            usedProofs[proofHash] = true;
            
            emit SanctionsProofVerified(msg.sender, proofHash, block.timestamp);
        }
        
        return valid;
    }
    
    /**
     * @notice Verify a risk score range proof
     * @param _pA Proof element A
     * @param _pB Proof element B
     * @param _pC Proof element C
     * @param _pubSignals Public signals [isInRange, isSignatureValid, isNotExpired, ...]
     * @return valid True if proof is valid
     * @return riskLevel Risk level (0=low, 1=medium, 2=high)
     */
    function verifyRiskProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[] calldata _pubSignals
    ) external returns (bool valid, uint8 riskLevel) {
        require(address(riskVerifier) != address(0), "Risk verifier not set");
        require(_pubSignals.length >= 8, "Invalid public signals");
        
        // Verify the proof
        valid = riskVerifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        
        if (valid) {
            // Extract risk level from maxScore public signal
            uint maxScore = _pubSignals[4];
            
            if (maxScore <= 39) {
                riskLevel = 0; // LOW
            } else if (maxScore <= 69) {
                riskLevel = 1; // MEDIUM
            } else {
                riskLevel = 2; // HIGH
            }
            
            bytes32 proofHash = keccak256(abi.encodePacked(_pA, _pB, _pC));
            require(!usedProofs[proofHash], "Proof already used");
            usedProofs[proofHash] = true;
            
            emit RiskProofVerified(msg.sender, proofHash, riskLevel, block.timestamp);
        }
        
        return (valid, riskLevel);
    }
    
    /**
     * @notice Verify a KYC credential proof
     * @param _pA Proof element A
     * @param _pB Proof element B
     * @param _pC Proof element C
     * @param _pubSignals Public signals [kycValid, isOldEnough, isNotPEP, ...]
     * @return valid True if proof is valid
     * @return kycStatus Bitmask of KYC status (bit 0=valid, bit 1=oldEnough, bit 2=notPEP, bit 3=notExpired)
     */
    function verifyKYCProof(
        uint[2] calldata _pA,
        uint[2][2] calldata _pB,
        uint[2] calldata _pC,
        uint[] calldata _pubSignals
    ) external returns (bool valid, uint8 kycStatus) {
        require(address(kycVerifier) != address(0), "KYC verifier not set");
        require(_pubSignals.length >= 9, "Invalid public signals");
        
        // Verify the proof
        valid = kycVerifier.verifyProof(_pA, _pB, _pC, _pubSignals);
        
        if (valid) {
            // Build KYC status bitmask from public signals
            // Outputs: kycValid, isOldEnough, isNotPEP, isNotExpired, isProviderAuthorized
            kycStatus = 0;
            if (_pubSignals[0] == 1) kycStatus |= 1;  // kycValid
            if (_pubSignals[1] == 1) kycStatus |= 2;  // isOldEnough
            if (_pubSignals[2] == 1) kycStatus |= 4;  // isNotPEP
            if (_pubSignals[3] == 1) kycStatus |= 8;  // isNotExpired
            if (_pubSignals[4] == 1) kycStatus |= 16; // isProviderAuthorized
            
            bytes32 proofHash = keccak256(abi.encodePacked(_pA, _pB, _pC));
            require(!usedProofs[proofHash], "Proof already used");
            usedProofs[proofHash] = true;
            
            emit KYCProofVerified(msg.sender, proofHash, block.timestamp);
        }
        
        return (valid, kycStatus);
    }
    
    /**
     * @notice Verify all three proofs in one transaction (for full compliance check)
     * @return sanctionsValid True if sanctions proof valid
     * @return riskValid True if risk proof valid
     * @return kycValid True if KYC proof valid
     * @return riskLevel Risk level (0-2)
     * @return kycStatus KYC status bitmask
     */
    function verifyFullCompliance(
        uint[2] calldata _sanctionsPa, uint[2][2] calldata _sanctionsPb, uint[2] calldata _sanctionsPc, uint[] calldata _sanctionsSignals,
        uint[2] calldata _riskPa, uint[2][2] calldata _riskPb, uint[2] calldata _riskPc, uint[] calldata _riskSignals,
        uint[2] calldata _kycPa, uint[2][2] calldata _kycPb, uint[2] calldata _kycPc, uint[] calldata _kycSignals
    ) external returns (
        bool sanctionsValid,
        bool riskValid,
        bool kycValid,
        uint8 riskLevel,
        uint8 kycStatus
    ) {
        // Verify each proof - will revert if any fail constraints
        sanctionsValid = this.verifySanctionsProof(_sanctionsPa, _sanctionsPb, _sanctionsPc, _sanctionsSignals);
        (riskValid, riskLevel) = this.verifyRiskProof(_riskPa, _riskPb, _riskPc, _riskSignals);
        (kycValid, kycStatus) = this.verifyKYCProof(_kycPa, _kycPb, _kycPc, _kycSignals);
        
        return (sanctionsValid, riskValid, kycValid, riskLevel, kycStatus);
    }
    
    // ═══════════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════════
    
    function isProofUsed(bytes32 _proofHash) external view returns (bool) {
        return usedProofs[_proofHash];
    }
    
    function getVerifiers() external view returns (
        address sanctions,
        address risk,
        address kyc
    ) {
        return (
            address(sanctionsVerifier),
            address(riskVerifier),
            address(kycVerifier)
        );
    }
}
