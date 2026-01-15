// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IArbitrator
 * @notice Kleros Arbitrator interface for dispute resolution
 * @dev See: https://github.com/kleros/kleros-v2
 */
interface IArbitrator {
    /**
     * @dev Create a dispute and pay arbitration fees
     * @param _choices Number of ruling options (2 for approve/reject)
     * @param _extraData Additional data for the arbitrator
     * @return disputeID The ID of the created dispute
     */
    function createDispute(
        uint256 _choices,
        bytes calldata _extraData
    ) external payable returns (uint256 disputeID);
    
    /**
     * @dev Get the cost of arbitration
     * @param _extraData Additional data for the arbitrator
     * @return cost The arbitration cost in wei
     */
    function arbitrationCost(
        bytes calldata _extraData
    ) external view returns (uint256 cost);
    
    /**
     * @dev Get the current ruling for a dispute
     * @param _disputeID The ID of the dispute
     * @return ruling The current ruling (0 = no ruling, 1 = approve, 2 = reject)
     */
    function currentRuling(
        uint256 _disputeID
    ) external view returns (uint256 ruling);
}

/**
 * @title IArbitrable
 * @notice Interface for contracts that can be arbitrated by Kleros
 */
interface IArbitrable {
    /**
     * @dev Emitted when a ruling is given
     * @param _arbitrator The arbitrator giving the ruling
     * @param _disputeID The ID of the dispute
     * @param _ruling The ruling (1 = approve, 2 = reject)
     */
    event Ruling(
        IArbitrator indexed _arbitrator,
        uint256 indexed _disputeID,
        uint256 _ruling
    );
    
    /**
     * @dev Called by the arbitrator to give a ruling
     * @param _disputeID The ID of the dispute
     * @param _ruling The ruling (1 = approve, 2 = reject)
     */
    function rule(uint256 _disputeID, uint256 _ruling) external;
}

/**
 * @title IEvidence
 * @notice Interface for submitting evidence to Kleros disputes
 */
interface IEvidence {
    /**
     * @dev Emitted when evidence is submitted
     */
    event Evidence(
        IArbitrator indexed _arbitrator,
        uint256 indexed _evidenceGroupID,
        address indexed _party,
        string _evidence
    );
    
    /**
     * @dev Emitted when a dispute is created
     */
    event Dispute(
        IArbitrator indexed _arbitrator,
        uint256 indexed _disputeID,
        uint256 _metaEvidenceID,
        uint256 _evidenceGroupID
    );
    
    /**
     * @dev Emitted to link metaevidence to a dispute type
     */
    event MetaEvidence(
        uint256 indexed _metaEvidenceID,
        string _evidence
    );
}
