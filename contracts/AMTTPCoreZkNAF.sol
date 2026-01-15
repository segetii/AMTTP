// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import "./zknaf/AMTTPzkNAF.sol";

/**
 * @title AMTTPCoreZkNAF
 * @dev Extension module that integrates zkNAF proofs with AMTTPCore
 * 
 * This module acts as a security layer that can be enabled/disabled
 * for privacy-preserving compliance verification before transfers.
 * 
 * FCA COMPLIANCE:
 * - ZK proofs provide PUBLIC privacy (counterparties don't see your data)
 * - AMTTP (regulated entity) maintains full records for regulatory disclosure
 * - Satisfies both privacy needs AND regulatory requirements
 */
contract AMTTPCoreZkNAF is Initializable, OwnableUpgradeable, PausableUpgradeable {
    
    // ═══════════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @notice Reference to the zkNAF verifier contract
    AMTTPzkNAF public zkNAF;
    
    /// @notice Whether zkNAF verification is required for transfers
    bool public zkVerificationEnabled;
    
    /// @notice Minimum proof requirements per transfer tier
    struct TierRequirements {
        bool requireSanctions;      // Require sanctions non-membership proof
        bool requireRiskProof;      // Require risk range proof
        bool requireKYC;            // Require KYC verification proof
        AMTTPzkNAF.ProofType minRiskLevel; // Minimum acceptable risk level
        uint256 maxTransferAmount;  // Max amount for this tier
    }
    
    /// @notice Transfer tiers (0 = lowest, higher = more stringent)
    mapping(uint256 => TierRequirements) public transferTiers;
    
    /// @notice Custom tier overrides for specific addresses
    mapping(address => uint256) public addressTierOverride;
    
    /// @notice Addresses exempt from zkNAF verification (e.g., contracts, bridges)
    mapping(address => bool) public verificationExempt;
    
    /// @notice Number of defined tiers
    uint256 public tierCount;
    
    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════
    
    event ZkVerificationEnabled(bool enabled);
    event TierConfigured(uint256 indexed tier, TierRequirements requirements);
    event AddressExempted(address indexed account, bool exempt);
    event AddressTierOverride(address indexed account, uint256 tier);
    event TransferVerified(
        address indexed from,
        address indexed to,
        uint256 amount,
        uint256 tier,
        bool sanctionsVerified,
        bool riskVerified,
        bool kycVerified
    );
    event VerificationFailed(
        address indexed from,
        address indexed to,
        uint256 amount,
        string reason
    );
    
    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION
    // ═══════════════════════════════════════════════════════════════════════
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    /**
     * @notice Initialize the zkNAF integration module
     * @param _zkNAF Address of the AMTTPzkNAF verifier contract
     */
    function initialize(address _zkNAF) external initializer {
        __Ownable_init();
        __Pausable_init();
        
        require(_zkNAF != address(0), "Invalid zkNAF address");
        zkNAF = AMTTPzkNAF(_zkNAF);
        zkVerificationEnabled = false; // Start disabled for safe migration
        
        // Setup default tiers
        _setupDefaultTiers();
    }
    
    /**
     * @dev Setup default transfer tiers based on FCA guidelines
     */
    function _setupDefaultTiers() internal {
        // Tier 0: Small transfers (< 1000 units) - Sanctions only
        transferTiers[0] = TierRequirements({
            requireSanctions: true,
            requireRiskProof: false,
            requireKYC: false,
            minRiskLevel: AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP,
            maxTransferAmount: 1000 * 1e18
        });
        
        // Tier 1: Medium transfers (< 10000 units) - Sanctions + Risk
        transferTiers[1] = TierRequirements({
            requireSanctions: true,
            requireRiskProof: true,
            requireKYC: false,
            minRiskLevel: AMTTPzkNAF.ProofType.RISK_RANGE_MEDIUM,
            maxTransferAmount: 10000 * 1e18
        });
        
        // Tier 2: Large transfers (< 100000 units) - All proofs required
        transferTiers[2] = TierRequirements({
            requireSanctions: true,
            requireRiskProof: true,
            requireKYC: true,
            minRiskLevel: AMTTPzkNAF.ProofType.RISK_RANGE_LOW,
            maxTransferAmount: 100000 * 1e18
        });
        
        // Tier 3: Very large transfers - Full verification, LOW risk only
        transferTiers[3] = TierRequirements({
            requireSanctions: true,
            requireRiskProof: true,
            requireKYC: true,
            minRiskLevel: AMTTPzkNAF.ProofType.RISK_RANGE_LOW,
            maxTransferAmount: type(uint256).max
        });
        
        tierCount = 4;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // VERIFICATION LOGIC
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Verify a transfer is allowed based on zkNAF proofs
     * @param from Sender address
     * @param to Recipient address  
     * @param amount Transfer amount
     * @return allowed Whether the transfer should proceed
     * @return reason Failure reason if not allowed
     */
    function verifyTransfer(
        address from,
        address to,
        uint256 amount
    ) external view returns (bool allowed, string memory reason) {
        // If verification is disabled, allow all
        if (!zkVerificationEnabled) {
            return (true, "");
        }
        
        // Check exemptions
        if (verificationExempt[from]) {
            return (true, "");
        }
        
        // Determine applicable tier
        uint256 tier = _getTierForTransfer(from, amount);
        TierRequirements memory req = transferTiers[tier];
        
        // Verify sanctions proof
        if (req.requireSanctions) {
            if (!zkNAF.hasValidProof(from, AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP)) {
                return (false, "ZKNAF: Valid sanctions proof required");
            }
        }
        
        // Verify risk range proof
        if (req.requireRiskProof) {
            // Check if user has acceptable risk level
            bool hasValidRisk = false;
            
            if (req.minRiskLevel == AMTTPzkNAF.ProofType.RISK_RANGE_LOW) {
                // Only LOW risk accepted
                hasValidRisk = zkNAF.hasValidProof(from, AMTTPzkNAF.ProofType.RISK_RANGE_LOW);
            } else if (req.minRiskLevel == AMTTPzkNAF.ProofType.RISK_RANGE_MEDIUM) {
                // LOW or MEDIUM accepted
                hasValidRisk = zkNAF.hasValidProof(from, AMTTPzkNAF.ProofType.RISK_RANGE_LOW) ||
                              zkNAF.hasValidProof(from, AMTTPzkNAF.ProofType.RISK_RANGE_MEDIUM);
            }
            
            if (!hasValidRisk) {
                return (false, "ZKNAF: Valid risk range proof required");
            }
        }
        
        // Verify KYC proof
        if (req.requireKYC) {
            if (!zkNAF.hasValidProof(from, AMTTPzkNAF.ProofType.KYC_VERIFIED)) {
                return (false, "ZKNAF: Valid KYC proof required");
            }
        }
        
        return (true, "");
    }
    
    /**
     * @notice Batch verify multiple addresses (for multi-sig, etc.)
     * @param addresses Array of addresses to verify
     * @param proofType Type of proof to check
     * @return allValid Whether all addresses have valid proofs
     * @return invalidAddresses Array of addresses that failed verification
     */
    function batchVerify(
        address[] calldata addresses,
        AMTTPzkNAF.ProofType proofType
    ) external view returns (bool allValid, address[] memory invalidAddresses) {
        uint256 invalidCount = 0;
        address[] memory tempInvalid = new address[](addresses.length);
        
        for (uint256 i = 0; i < addresses.length; i++) {
            if (!verificationExempt[addresses[i]] && 
                !zkNAF.hasValidProof(addresses[i], proofType)) {
                tempInvalid[invalidCount] = addresses[i];
                invalidCount++;
            }
        }
        
        // Create correctly sized array
        invalidAddresses = new address[](invalidCount);
        for (uint256 i = 0; i < invalidCount; i++) {
            invalidAddresses[i] = tempInvalid[i];
        }
        
        return (invalidCount == 0, invalidAddresses);
    }
    
    /**
     * @notice Get the compliance status summary for an address
     * @param account Address to check
     * @return hasSanctionsProof Whether sanctions proof is valid
     * @return hasRiskProof Whether any risk proof is valid
     * @return hasKYCProof Whether KYC proof is valid
     * @return maxAllowedTier Maximum tier this address qualifies for
     */
    function getComplianceStatus(address account) external view returns (
        bool hasSanctionsProof,
        bool hasRiskProof,
        bool hasKYCProof,
        uint256 maxAllowedTier
    ) {
        hasSanctionsProof = zkNAF.hasValidProof(account, AMTTPzkNAF.ProofType.SANCTIONS_NON_MEMBERSHIP);
        hasRiskProof = zkNAF.hasValidProof(account, AMTTPzkNAF.ProofType.RISK_RANGE_LOW) ||
                       zkNAF.hasValidProof(account, AMTTPzkNAF.ProofType.RISK_RANGE_MEDIUM);
        hasKYCProof = zkNAF.hasValidProof(account, AMTTPzkNAF.ProofType.KYC_VERIFIED);
        
        // Determine max allowed tier
        if (hasSanctionsProof && hasRiskProof && hasKYCProof) {
            maxAllowedTier = tierCount - 1; // Highest tier
        } else if (hasSanctionsProof && hasRiskProof) {
            maxAllowedTier = 1;
        } else if (hasSanctionsProof) {
            maxAllowedTier = 0;
        } else {
            maxAllowedTier = 0; // No proofs = lowest tier only (will fail if verification enabled)
        }
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL HELPERS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @dev Determine which tier applies for a transfer
     */
    function _getTierForTransfer(address from, uint256 amount) internal view returns (uint256) {
        // Check for address-specific override first
        if (addressTierOverride[from] > 0) {
            return addressTierOverride[from];
        }
        
        // Otherwise, determine by amount
        for (uint256 i = 0; i < tierCount; i++) {
            if (amount <= transferTiers[i].maxTransferAmount) {
                return i;
            }
        }
        
        return tierCount - 1; // Highest tier
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Enable or disable zkNAF verification
     * @param enabled Whether to require zkNAF proofs
     */
    function setVerificationEnabled(bool enabled) external onlyOwner {
        zkVerificationEnabled = enabled;
        emit ZkVerificationEnabled(enabled);
    }
    
    /**
     * @notice Configure a transfer tier
     * @param tier Tier index
     * @param requirements Tier requirements
     */
    function configureTier(
        uint256 tier,
        TierRequirements calldata requirements
    ) external onlyOwner {
        require(tier < 10, "Tier too high"); // Reasonable limit
        transferTiers[tier] = requirements;
        
        if (tier >= tierCount) {
            tierCount = tier + 1;
        }
        
        emit TierConfigured(tier, requirements);
    }
    
    /**
     * @notice Set exemption status for an address
     * @param account Address to exempt/unexempt
     * @param exempt Whether to exempt from verification
     */
    function setExemption(address account, bool exempt) external onlyOwner {
        verificationExempt[account] = exempt;
        emit AddressExempted(account, exempt);
    }
    
    /**
     * @notice Set tier override for specific address
     * @param account Address to override
     * @param tier Tier to apply (0 to remove override)
     */
    function setTierOverride(address account, uint256 tier) external onlyOwner {
        addressTierOverride[account] = tier;
        emit AddressTierOverride(account, tier);
    }
    
    /**
     * @notice Update the zkNAF contract reference
     * @param _zkNAF New zkNAF contract address
     */
    function setZkNAF(address _zkNAF) external onlyOwner {
        require(_zkNAF != address(0), "Invalid address");
        zkNAF = AMTTPzkNAF(_zkNAF);
    }
    
    /**
     * @notice Pause verification (emergency)
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @notice Unpause verification
     */
    function unpause() external onlyOwner {
        _unpause();
    }
}
