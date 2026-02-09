// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IAMTTPCoreZkNAF.sol";
import "./MockZkNAF.sol";

/**
 * @title MockZkNAFModule - Demo Integration Module
 * @author AMTTP Team
 * @notice Demo implementation of zkNAF verification for AMTTPCore
 * @dev For testing and demonstration only - NOT FOR PRODUCTION
 * 
 * Features:
 * - Always allows transfers in demo mode
 * - Can require proof generation for more realistic testing
 * - Integrates with MockZkNAF for proof management
 */
contract MockZkNAFModule is IAMTTPCoreZkNAF {
    
    MockZkNAF public mockZkNAF;
    address public owner;
    bool public zkVerificationEnabled;
    bool public strictMode;  // If true, require actual proof generation
    
    // Whitelist for addresses that bypass verification
    mapping(address => bool) public whitelisted;
    
    event VerificationToggled(bool enabled);
    event StrictModeToggled(bool enabled);
    event AddressWhitelisted(address indexed account, bool status);
    event TransferVerified(address indexed from, address indexed to, uint256 amount, bool allowed);
    
    constructor(address _mockZkNAF) {
        owner = msg.sender;
        mockZkNAF = MockZkNAF(_mockZkNAF);
        zkVerificationEnabled = true;  // Start enabled in demo
        strictMode = false;  // Start permissive
    }
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // IAMTTPCoreZkNAF Implementation
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Verify transfer - in demo mode, always allows unless strictMode is on
     */
    function verifyTransfer(
        address from,
        address to,
        uint256 amount
    ) external view override returns (bool allowed, string memory reason) {
        // If verification is disabled, always allow
        if (!zkVerificationEnabled) {
            return (true, "");
        }
        
        // Whitelisted addresses always pass
        if (whitelisted[from]) {
            return (true, "");
        }
        
        // In non-strict mode, always allow (demo behavior)
        if (!strictMode) {
            return (true, "");
        }
        
        // Strict mode: check actual proofs from MockZkNAF
        (bool sanctions, bool risk, bool kyc, bool compliant) = mockZkNAF.isCompliant(from);
        
        // For demo, we only require sanctions proof
        if (!sanctions) {
            return (false, "ZKNAF_DEMO: Generate sanctions proof first");
        }
        
        // Large amounts need risk proof
        if (amount > 1000 ether && !risk) {
            return (false, "ZKNAF_DEMO: Large transfer requires risk proof");
        }
        
        // Very large amounts need full compliance
        if (amount > 10000 ether && !compliant) {
            return (false, "ZKNAF_DEMO: Very large transfer requires full compliance proofs");
        }
        
        return (true, "");
    }
    
    /**
     * @notice Get compliance status for an address
     */
    function getComplianceStatus(address account) external view override returns (
        bool hasSanctionsProof,
        bool hasRiskProof,
        bool hasKYCProof,
        uint256 maxAllowedTier
    ) {
        (hasSanctionsProof, hasRiskProof, hasKYCProof, ) = mockZkNAF.isCompliant(account);
        
        // Determine max tier based on proofs
        if (hasSanctionsProof && hasRiskProof && hasKYCProof) {
            maxAllowedTier = 3; // Unlimited
        } else if (hasSanctionsProof && hasRiskProof) {
            maxAllowedTier = 2; // Up to 100k
        } else if (hasSanctionsProof) {
            maxAllowedTier = 1; // Up to 10k
        } else {
            maxAllowedTier = 0; // Up to 1k
        }
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // Admin Functions
    // ═══════════════════════════════════════════════════════════════════════
    
    function setZkVerificationEnabled(bool enabled) external onlyOwner {
        zkVerificationEnabled = enabled;
        emit VerificationToggled(enabled);
    }
    
    function setStrictMode(bool enabled) external onlyOwner {
        strictMode = enabled;
        emit StrictModeToggled(enabled);
    }
    
    function setWhitelisted(address account, bool status) external onlyOwner {
        whitelisted[account] = status;
        emit AddressWhitelisted(account, status);
    }
    
    function batchWhitelist(address[] calldata accounts) external onlyOwner {
        for (uint256 i = 0; i < accounts.length; i++) {
            whitelisted[accounts[i]] = true;
            emit AddressWhitelisted(accounts[i], true);
        }
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // Demo Helpers
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Quick setup: generate all proofs for sender
     */
    function setupDemoCompliance() external {
        mockZkNAF.generateDemoProof(MockZkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP);
        mockZkNAF.generateDemoProof(MockZkNAF.ProofType.RISK_RANGE_LOW);
        mockZkNAF.generateDemoProof(MockZkNAF.ProofType.KYC_VERIFIED);
    }
}
