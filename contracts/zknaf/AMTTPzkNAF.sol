// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";

/**
 * @title AMTTPzkNAF - Zero-Knowledge Non-Disclosing Anti-Fraud
 * @author AMTTP Team
 * @notice Privacy-preserving compliance verification using ZK proofs
 * @dev Implements Groth16 verification for:
 *      - Sanctions non-membership proofs
 *      - Risk score range proofs
 *      - KYC credential verification
 * 
 * FCA COMPLIANCE NOTE:
 * This contract enables PUBLIC verification of compliance status without
 * revealing sensitive data. The regulated entity (AMTTP oracle) maintains
 * full records for SAR filing and regulatory disclosure as required by
 * MLR 2017 and FSMA s.330.
 */
contract AMTTPzkNAF is OwnableUpgradeable, PausableUpgradeable, UUPSUpgradeable {
    
    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS - BN254 Curve Parameters (used by snarkjs/circom)
    // ═══════════════════════════════════════════════════════════════════════
    
    uint256 constant PRIME_Q = 21888242871839275222246405745257275088696311157297823662689037894645226208583;
    uint256 constant SNARK_SCALAR_FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617;
    
    // ═══════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Groth16 verification key structure
    struct VerifyingKey {
        uint256[2] alpha1;
        uint256[2][2] beta2;
        uint256[2][2] gamma2;
        uint256[2][2] delta2;
        uint256[2][] ic; // Input commitment points
    }
    
    /// @notice Groth16 proof structure
    struct Proof {
        uint256[2] a;
        uint256[2][2] b;
        uint256[2] c;
    }
    
    /// @notice Types of ZK proofs supported
    enum ProofType {
        SANCTIONS_NON_MEMBERSHIP,  // Prove address is NOT on sanctions list
        RISK_RANGE_LOW,            // Prove risk score < 40 (low risk)
        RISK_RANGE_MEDIUM,         // Prove risk score 40-70 (medium risk)
        KYC_VERIFIED,              // Prove KYC passed without revealing identity
        TRANSACTION_COMPLIANT      // Combined proof: not sanctioned + low risk + KYC
    }
    
    /// @notice Stored proof record for on-chain verification history
    struct ProofRecord {
        bytes32 proofHash;
        ProofType proofType;
        address prover;
        uint256 timestamp;
        uint256 expiresAt;
        bool isValid;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Verification keys for each proof type (internal, use getter)
    mapping(ProofType => VerifyingKey) internal _verifyingKeys;
    
    /// @notice Whether a verification key has been set
    mapping(ProofType => bool) public verifyingKeySet;
    
    /// @notice Proof records by hash
    mapping(bytes32 => ProofRecord) public proofRecords;
    
    /// @notice Valid proofs for an address (address => proofType => proofHash)
    mapping(address => mapping(ProofType => bytes32)) public addressProofs;
    
    /// @notice Sanctions list Merkle root (updated by oracle)
    bytes32 public sanctionsListRoot;
    
    /// @notice Last sanctions list update timestamp
    uint256 public sanctionsListUpdatedAt;
    
    /// @notice Proof validity duration (default 24 hours)
    uint256 public proofValidityDuration;
    
    /// @notice Authorized oracles that can update sanctions list
    mapping(address => bool) public authorizedOracles;
    
    /// @notice Counter for total proofs verified
    uint256 public totalProofsVerified;
    
    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════
    
    event VerifyingKeyUpdated(ProofType indexed proofType, bytes32 keyHash);
    event ProofVerified(
        bytes32 indexed proofHash,
        ProofType indexed proofType,
        address indexed prover,
        uint256 expiresAt
    );
    event ProofRevoked(bytes32 indexed proofHash, string reason);
    event SanctionsListUpdated(bytes32 indexed newRoot, uint256 timestamp);
    event OracleAuthorized(address indexed oracle, bool authorized);
    
    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════
    
    error InvalidProof();
    error VerifyingKeyNotSet();
    error ProofExpired();
    error ProofAlreadyExists();
    error NotAuthorizedOracle();
    error InvalidInput();
    
    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    function initialize(address _owner) public initializer {
        __Ownable_init();
        __Pausable_init();
        __UUPSUpgradeable_init();
        
        _transferOwnership(_owner);
        proofValidityDuration = 24 hours;
        authorizedOracles[_owner] = true;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Set verification key for a proof type
     * @dev Called after trusted setup ceremony completes
     */
    function setVerifyingKey(
        ProofType proofType,
        uint256[2] calldata alpha1,
        uint256[2][2] calldata beta2,
        uint256[2][2] calldata gamma2,
        uint256[2][2] calldata delta2,
        uint256[2][] calldata ic
    ) external onlyOwner {
        VerifyingKey storage vk = _verifyingKeys[proofType];
        vk.alpha1 = alpha1;
        vk.beta2 = beta2;
        vk.gamma2 = gamma2;
        vk.delta2 = delta2;
        
        // Clear and set IC points
        delete vk.ic;
        for (uint256 i = 0; i < ic.length; i++) {
            vk.ic.push(ic[i]);
        }
        
        verifyingKeySet[proofType] = true;
        
        emit VerifyingKeyUpdated(proofType, keccak256(abi.encode(alpha1, beta2, gamma2, delta2, ic)));
    }
    
    /**
     * @notice Authorize or revoke an oracle
     */
    function setAuthorizedOracle(address oracle, bool authorized) external onlyOwner {
        authorizedOracles[oracle] = authorized;
        emit OracleAuthorized(oracle, authorized);
    }
    
    /**
     * @notice Update sanctions list Merkle root
     * @dev Only authorized oracles can update
     */
    function updateSanctionsListRoot(bytes32 newRoot) external {
        if (!authorizedOracles[msg.sender]) revert NotAuthorizedOracle();
        
        sanctionsListRoot = newRoot;
        sanctionsListUpdatedAt = block.timestamp;
        
        emit SanctionsListUpdated(newRoot, block.timestamp);
    }
    
    /**
     * @notice Set proof validity duration
     */
    function setProofValidityDuration(uint256 duration) external onlyOwner {
        proofValidityDuration = duration;
    }
    
    function pause() external onlyOwner {
        _pause();
    }
    
    function unpause() external onlyOwner {
        _unpause();
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // VERIFICATION FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Verify a Groth16 proof and store the result
     * @param proofType The type of proof being verified
     * @param proof The Groth16 proof
     * @param publicInputs The public inputs to the circuit
     * @return proofHash The hash of the verified proof
     */
    function verifyAndStore(
        ProofType proofType,
        Proof calldata proof,
        uint256[] calldata publicInputs
    ) external whenNotPaused returns (bytes32 proofHash) {
        if (!verifyingKeySet[proofType]) revert VerifyingKeyNotSet();
        
        // Verify the proof
        bool isValid = _verifyProof(proofType, proof, publicInputs);
        if (!isValid) revert InvalidProof();
        
        // Generate proof hash
        proofHash = keccak256(abi.encode(
            proofType,
            msg.sender,
            publicInputs,
            block.timestamp
        ));
        
        // Check if proof already exists
        if (proofRecords[proofHash].timestamp != 0) revert ProofAlreadyExists();
        
        // Store proof record
        uint256 expiresAt = block.timestamp + proofValidityDuration;
        proofRecords[proofHash] = ProofRecord({
            proofHash: proofHash,
            proofType: proofType,
            prover: msg.sender,
            timestamp: block.timestamp,
            expiresAt: expiresAt,
            isValid: true
        });
        
        // Update address proof mapping
        addressProofs[msg.sender][proofType] = proofHash;
        
        totalProofsVerified++;
        
        emit ProofVerified(proofHash, proofType, msg.sender, expiresAt);
        
        return proofHash;
    }
    
    /**
     * @notice Verify a proof without storing (view function for off-chain checks)
     */
    function verify(
        ProofType proofType,
        Proof calldata proof,
        uint256[] calldata publicInputs
    ) external view returns (bool) {
        if (!verifyingKeySet[proofType]) revert VerifyingKeyNotSet();
        return _verifyProof(proofType, proof, publicInputs);
    }
    
    /**
     * @notice Check if an address has a valid proof of a specific type
     */
    function hasValidProof(address account, ProofType proofType) external view returns (bool) {
        bytes32 proofHash = addressProofs[account][proofType];
        if (proofHash == bytes32(0)) return false;
        
        ProofRecord memory record = proofRecords[proofHash];
        return record.isValid && record.expiresAt > block.timestamp;
    }
    
    /**
     * @notice Check if address is compliant (has all required proofs)
     * @dev For FCA compliance, this is PUBLIC verification only.
     *      Full records are maintained off-chain for regulatory disclosure.
     */
    function isCompliant(address account) external view returns (
        bool sanctionsProof,
        bool riskProof,
        bool kycProof,
        bool fullyCompliant
    ) {
        sanctionsProof = this.hasValidProof(account, ProofType.SANCTIONS_NON_MEMBERSHIP);
        riskProof = this.hasValidProof(account, ProofType.RISK_RANGE_LOW) || 
                    this.hasValidProof(account, ProofType.RISK_RANGE_MEDIUM);
        kycProof = this.hasValidProof(account, ProofType.KYC_VERIFIED);
        
        fullyCompliant = sanctionsProof && riskProof && kycProof;
    }
    
    /**
     * @notice Revoke a proof (e.g., if sanctions list updated)
     */
    function revokeProof(bytes32 proofHash, string calldata reason) external {
        if (!authorizedOracles[msg.sender]) revert NotAuthorizedOracle();
        
        ProofRecord storage record = proofRecords[proofHash];
        record.isValid = false;
        
        emit ProofRevoked(proofHash, reason);
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL - GROTH16 VERIFICATION (BN254)
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Internal Groth16 verification
     * @dev Uses precompiled contracts for elliptic curve operations
     */
    function _verifyProof(
        ProofType proofType,
        Proof calldata proof,
        uint256[] calldata publicInputs
    ) internal view returns (bool) {
        VerifyingKey storage vk = _verifyingKeys[proofType];
        
        // Check public inputs length matches IC length
        if (publicInputs.length + 1 != vk.ic.length) revert InvalidInput();
        
        // Compute linear combination of public inputs
        uint256[2] memory vk_x = vk.ic[0];
        for (uint256 i = 0; i < publicInputs.length; i++) {
            if (publicInputs[i] >= SNARK_SCALAR_FIELD) revert InvalidInput();
            
            // Scalar multiplication and addition
            (uint256 x, uint256 y) = _scalarMul(vk.ic[i + 1], publicInputs[i]);
            (vk_x[0], vk_x[1]) = _pointAdd(vk_x[0], vk_x[1], x, y);
        }
        
        // Pairing check
        return _pairing(
            _negate(proof.a),
            proof.b,
            vk.alpha1,
            vk.beta2,
            vk_x,
            vk.gamma2,
            proof.c,
            vk.delta2
        );
    }
    
    /**
     * @notice Elliptic curve scalar multiplication using precompile
     */
    function _scalarMul(uint256[2] storage p, uint256 s) internal view returns (uint256, uint256) {
        uint256[3] memory input;
        input[0] = p[0];
        input[1] = p[1];
        input[2] = s;
        
        uint256[2] memory result;
        assembly {
            // ecMul precompile at address 0x07
            let success := staticcall(gas(), 0x07, input, 0x60, result, 0x40)
            if iszero(success) {
                revert(0, 0)
            }
        }
        return (result[0], result[1]);
    }
    
    /**
     * @notice Elliptic curve point addition using precompile
     */
    function _pointAdd(uint256 x1, uint256 y1, uint256 x2, uint256 y2) internal view returns (uint256, uint256) {
        uint256[4] memory input;
        input[0] = x1;
        input[1] = y1;
        input[2] = x2;
        input[3] = y2;
        
        uint256[2] memory result;
        assembly {
            // ecAdd precompile at address 0x06
            let success := staticcall(gas(), 0x06, input, 0x80, result, 0x40)
            if iszero(success) {
                revert(0, 0)
            }
        }
        return (result[0], result[1]);
    }
    
    /**
     * @notice Negate a G1 point
     */
    function _negate(uint256[2] calldata p) internal pure returns (uint256[2] memory) {
        if (p[0] == 0 && p[1] == 0) {
            return [uint256(0), uint256(0)];
        }
        return [p[0], PRIME_Q - (p[1] % PRIME_Q)];
    }
    
    /**
     * @notice Pairing check using precompile
     */
    function _pairing(
        uint256[2] memory a1,
        uint256[2][2] calldata a2,
        uint256[2] storage b1,
        uint256[2][2] storage b2,
        uint256[2] memory c1,
        uint256[2][2] storage c2,
        uint256[2] calldata d1,
        uint256[2][2] storage d2
    ) internal view returns (bool) {
        uint256[24] memory input;
        
        // First pairing
        input[0] = a1[0];
        input[1] = a1[1];
        input[2] = a2[0][1];  // Note: Fp2 elements are stored in reverse
        input[3] = a2[0][0];
        input[4] = a2[1][1];
        input[5] = a2[1][0];
        
        // Second pairing
        input[6] = b1[0];
        input[7] = b1[1];
        input[8] = b2[0][1];
        input[9] = b2[0][0];
        input[10] = b2[1][1];
        input[11] = b2[1][0];
        
        // Third pairing
        input[12] = c1[0];
        input[13] = c1[1];
        input[14] = c2[0][1];
        input[15] = c2[0][0];
        input[16] = c2[1][1];
        input[17] = c2[1][0];
        
        // Fourth pairing
        input[18] = d1[0];
        input[19] = d1[1];
        input[20] = d2[0][1];
        input[21] = d2[0][0];
        input[22] = d2[1][1];
        input[23] = d2[1][0];
        
        uint256[1] memory result;
        assembly {
            // ecPairing precompile at address 0x08
            let success := staticcall(gas(), 0x08, input, 0x300, result, 0x20)
            if iszero(success) {
                revert(0, 0)
            }
        }
        
        return result[0] == 1;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // UUPS UPGRADE
    // ═══════════════════════════════════════════════════════════════════════
    
    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
    
    /**
     * @notice Get contract version
     */
    function version() external pure returns (string memory) {
        return "1.0.0";
    }
}
