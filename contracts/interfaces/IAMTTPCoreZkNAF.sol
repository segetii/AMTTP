// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IAMTTPCoreZkNAF
 * @dev Interface for zkNAF integration with AMTTPCore
 * 
 * Use this interface to add optional zkNAF verification to transfers.
 * The verification can be enabled/disabled without contract upgrades.
 */
interface IAMTTPCoreZkNAF {
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
    ) external view returns (bool allowed, string memory reason);
    
    /**
     * @notice Check if zkNAF verification is currently enabled
     */
    function zkVerificationEnabled() external view returns (bool);
    
    /**
     * @notice Get compliance status summary for an address
     */
    function getComplianceStatus(address account) external view returns (
        bool hasSanctionsProof,
        bool hasRiskProof,
        bool hasKYCProof,
        uint256 maxAllowedTier
    );
}
