// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title IAMTTPRiskRouter
 * @notice Interface for the AI Risk Router contract
 * @dev Used for integration with other AMTTP contracts and L1 bridges
 */
interface IAMTTPRiskRouter {
    // ═══════════════════════════════════════════════════════════════════════
    //                           ENUMS
    // ═══════════════════════════════════════════════════════════════════════
    
    enum RiskAction {
        APPROVE,
        REVIEW,
        ESCROW,
        BLOCK
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                           STRUCTS
    // ═══════════════════════════════════════════════════════════════════════
    
    struct RiskResult {
        uint128 riskScore;
        uint64 timestamp;
        RiskAction action;
        bool processed;
    }
    
    struct BatchRequest {
        address sender;
        address recipient;
        uint256 amount;
        uint128 riskScore;
        bytes32 txHash;
    }

    // ═══════════════════════════════════════════════════════════════════════
    //                           EVENTS
    // ═══════════════════════════════════════════════════════════════════════
    
    event RiskAssessed(
        bytes32 indexed txHash,
        address indexed sender,
        address indexed recipient,
        uint256 amount,
        uint256 riskScore,
        RiskAction action
    );
    
    event BatchProcessed(
        uint256 batchId,
        uint256 count,
        uint256 approved,
        uint256 reviewed,
        uint256 escrowed,
        uint256 blocked
    );

    // ═══════════════════════════════════════════════════════════════════════
    //                       CORE FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Assess and route a single transaction based on ML risk score
     * @param sender Transaction sender
     * @param recipient Transaction recipient
     * @param amount Transaction amount
     * @param riskScore ML-computed risk score (0-1000)
     * @param timestamp Score computation timestamp
     * @param signature Oracle signature
     * @return action The determined risk action
     * @return txHash The transaction hash for tracking
     */
    function assessRisk(
        address sender,
        address recipient,
        uint256 amount,
        uint128 riskScore,
        uint64 timestamp,
        bytes calldata signature
    ) external returns (RiskAction action, bytes32 txHash);
    
    /**
     * @notice Batch assess multiple transactions
     * @param requests Array of batch requests
     * @param signatures Array of oracle signatures
     * @return actions Array of determined actions
     * @return txHashes Array of transaction hashes
     */
    function batchAssessRisk(
        BatchRequest[] calldata requests,
        bytes[] calldata signatures
    ) external returns (RiskAction[] memory actions, bytes32[] memory txHashes);
    
    /**
     * @notice Quick risk check without storing
     * @param riskScore The risk score to evaluate
     * @return action The action that would be taken
     */
    function quickCheck(uint128 riskScore) external view returns (RiskAction action);
    
    /**
     * @notice Get risk result for a transaction
     * @param txHash Transaction hash
     * @return result The risk assessment result
     */
    function getRiskResult(bytes32 txHash) external view returns (RiskResult memory result);
    
    /**
     * @notice Mark a risk result as processed
     * @param txHash Transaction hash
     */
    function markProcessed(bytes32 txHash) external;

    // ═══════════════════════════════════════════════════════════════════════
    //                       VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════
    
    /**
     * @notice Get router statistics
     */
    function getStatistics() external view returns (
        uint256 totalAssessments,
        uint256 totalApproved,
        uint256 totalReviewed,
        uint256 totalEscrowed,
        uint256 totalBlocked,
        bool circuitBreakerActive
    );
    
    /**
     * @notice Get current thresholds
     */
    function getThresholds() external view returns (
        uint256 low,
        uint256 medium,
        uint256 high
    );
    
    /**
     * @notice Get model version
     */
    function modelVersion() external view returns (string memory);
}
