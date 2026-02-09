// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title MockZkNAF - Demo/Test zkNAF Verifier
 * @author AMTTP Team
 * @notice Mock implementation for demo and testing purposes
 * @dev Always returns true for proof verification - NOT FOR PRODUCTION
 * 
 * This contract simulates zkNAF verification without actual ZK circuits.
 * Use for:
 * - Integration testing
 * - UI/UX demonstration
 * - Development environment
 */
contract MockZkNAF {
    
    // ═══════════════════════════════════════════════════════════════════════
    // TYPES (matches real AMTTPzkNAF)
    // ═══════════════════════════════════════════════════════════════════════
    
    enum ProofType {
        SANCTIONS_NON_MEMBERSHIP,
        RISK_RANGE_LOW,
        RISK_RANGE_MEDIUM,
        KYC_VERIFIED,
        TRANSACTION_COMPLIANT
    }
    
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
    
    address public owner;
    bool public demoMode;
    
    /// @notice Proof records by hash
    mapping(bytes32 => ProofRecord) public proofRecords;
    
    /// @notice Valid proofs for an address (address => proofType => proofHash)
    mapping(address => mapping(ProofType => bytes32)) public addressProofs;
    
    /// @notice Demo: Auto-approve all addresses
    mapping(address => bool) public demoApproved;
    
    /// @notice Proof validity duration (default 24 hours)
    uint256 public proofValidityDuration;
    
    /// @notice Counter for total proofs
    uint256 public totalProofsVerified;
    
    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════
    
    event ProofGenerated(
        bytes32 indexed proofHash,
        ProofType indexed proofType,
        address indexed prover,
        uint256 expiresAt
    );
    event DemoModeChanged(bool enabled);
    event AddressDemoApproved(address indexed account, bool approved);
    
    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION
    // ═══════════════════════════════════════════════════════════════════════
    
    constructor() {
        owner = msg.sender;
        demoMode = true;
        proofValidityDuration = 24 hours;
    }
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // DEMO FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Generate a demo proof for any address
     * @dev In demo mode, anyone can generate proofs for themselves
     */
    function generateDemoProof(ProofType proofType) external returns (bytes32 proofHash) {
        return _generateProof(msg.sender, proofType);
    }
    
    /**
     * @notice Admin can generate proofs for any address
     */
    function generateProofFor(address account, ProofType proofType) external onlyOwner returns (bytes32 proofHash) {
        return _generateProof(account, proofType);
    }
    
    /**
     * @notice Generate all compliance proofs at once
     */
    function generateAllProofs() external returns (
        bytes32 sanctionsProof,
        bytes32 riskProof,
        bytes32 kycProof
    ) {
        sanctionsProof = _generateProof(msg.sender, ProofType.SANCTIONS_NON_MEMBERSHIP);
        riskProof = _generateProof(msg.sender, ProofType.RISK_RANGE_LOW);
        kycProof = _generateProof(msg.sender, ProofType.KYC_VERIFIED);
    }
    
    /**
     * @notice Set demo approval for an address
     */
    function setDemoApproval(address account, bool approved) external onlyOwner {
        demoApproved[account] = approved;
        emit AddressDemoApproved(account, approved);
    }
    
    /**
     * @notice Batch approve addresses for demo
     */
    function batchDemoApprove(address[] calldata accounts) external onlyOwner {
        for (uint256 i = 0; i < accounts.length; i++) {
            demoApproved[accounts[i]] = true;
            emit AddressDemoApproved(accounts[i], true);
        }
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // VERIFICATION (Mock Implementation)
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Check if an address has a valid proof of a specific type
     * @dev In demo mode, returns true if demoApproved or has generated proof
     */
    function hasValidProof(address account, ProofType proofType) external view returns (bool) {
        // Demo mode: auto-approve all
        if (demoMode && demoApproved[account]) {
            return true;
        }
        
        bytes32 proofHash = addressProofs[account][proofType];
        if (proofHash == bytes32(0)) return false;
        
        ProofRecord memory record = proofRecords[proofHash];
        return record.isValid && record.expiresAt > block.timestamp;
    }
    
    /**
     * @notice Check full compliance status
     */
    function isCompliant(address account) external view returns (
        bool sanctionsProof,
        bool riskProof,
        bool kycProof,
        bool fullyCompliant
    ) {
        // Demo mode shortcut
        if (demoMode && demoApproved[account]) {
            return (true, true, true, true);
        }
        
        sanctionsProof = this.hasValidProof(account, ProofType.SANCTIONS_NON_MEMBERSHIP);
        riskProof = this.hasValidProof(account, ProofType.RISK_RANGE_LOW) || 
                    this.hasValidProof(account, ProofType.RISK_RANGE_MEDIUM);
        kycProof = this.hasValidProof(account, ProofType.KYC_VERIFIED);
        
        fullyCompliant = sanctionsProof && riskProof && kycProof;
    }
    
    /**
     * @notice Get proof details
     */
    function getProof(bytes32 proofHash) external view returns (ProofRecord memory) {
        return proofRecords[proofHash];
    }
    
    /**
     * @notice Get user's proof for a specific type
     */
    function getUserProof(address account, ProofType proofType) external view returns (ProofRecord memory) {
        bytes32 proofHash = addressProofs[account][proofType];
        return proofRecords[proofHash];
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN
    // ═══════════════════════════════════════════════════════════════════════
    
    function setDemoMode(bool enabled) external onlyOwner {
        demoMode = enabled;
        emit DemoModeChanged(enabled);
    }
    
    function setProofValidityDuration(uint256 duration) external onlyOwner {
        proofValidityDuration = duration;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL
    // ═══════════════════════════════════════════════════════════════════════
    
    function _generateProof(address account, ProofType proofType) internal returns (bytes32 proofHash) {
        proofHash = keccak256(abi.encode(
            proofType,
            account,
            block.timestamp,
            totalProofsVerified
        ));
        
        uint256 expiresAt = block.timestamp + proofValidityDuration;
        
        proofRecords[proofHash] = ProofRecord({
            proofHash: proofHash,
            proofType: proofType,
            prover: account,
            timestamp: block.timestamp,
            expiresAt: expiresAt,
            isValid: true
        });
        
        addressProofs[account][proofType] = proofHash;
        totalProofsVerified++;
        
        emit ProofGenerated(proofHash, proofType, account, expiresAt);
        
        return proofHash;
    }
}
