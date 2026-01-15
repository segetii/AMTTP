// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../interfaces/IKleros.sol";

/**
 * @title MockArbitrator
 * @notice Mock Kleros arbitrator for local testing
 * @dev Simulates Kleros behavior for development/testing
 */
contract MockArbitrator is IArbitrator {
    
    uint256 public constant ARBITRATION_COST = 0.01 ether;
    
    struct Dispute {
        address arbitrable;
        uint256 choices;
        uint256 ruling;
        bool resolved;
    }
    
    mapping(uint256 => Dispute) public disputes;
    uint256 public disputeCounter;
    
    event DisputeCreated(uint256 indexed disputeID, address indexed arbitrable, uint256 choices);
    event RulingGiven(uint256 indexed disputeID, uint256 ruling);
    
    /**
     * @notice Create a dispute (called by Arbitrable contracts)
     */
    function createDispute(
        uint256 _choices,
        bytes calldata /* _extraData */
    ) external payable override returns (uint256 disputeID) {
        require(msg.value >= ARBITRATION_COST, "Insufficient fee");
        
        disputeID = disputeCounter++;
        disputes[disputeID] = Dispute({
            arbitrable: msg.sender,
            choices: _choices,
            ruling: 0,
            resolved: false
        });
        
        emit DisputeCreated(disputeID, msg.sender, _choices);
        
        return disputeID;
    }
    
    /**
     * @notice Get the cost of arbitration
     */
    function arbitrationCost(
        bytes calldata /* _extraData */
    ) external pure override returns (uint256 cost) {
        return ARBITRATION_COST;
    }
    
    /**
     * @notice Get the current ruling
     */
    function currentRuling(
        uint256 _disputeID
    ) external view override returns (uint256 ruling) {
        return disputes[_disputeID].ruling;
    }
    
    // ============================================================
    // TESTING FUNCTIONS (NOT IN REAL KLEROS)
    // ============================================================
    
    /**
     * @notice Give a ruling (simulates juror vote)
     * @dev In real Kleros, this is done through juror voting
     * @param _disputeID The dispute to rule on
     * @param _ruling 1 = Approve, 2 = Reject
     */
    function giveRuling(uint256 _disputeID, uint256 _ruling) external {
        _giveRuling(_disputeID, _ruling);
    }
    
    function _giveRuling(uint256 _disputeID, uint256 _ruling) internal {
        Dispute storage dispute = disputes[_disputeID];
        require(!dispute.resolved, "Already resolved");
        require(_ruling <= dispute.choices, "Invalid ruling");
        
        dispute.ruling = _ruling;
        dispute.resolved = true;
        
        // Call the arbitrable contract with the ruling
        IArbitrable(dispute.arbitrable).rule(_disputeID, _ruling);
        
        emit RulingGiven(_disputeID, _ruling);
    }
    
    /**
     * @notice Simulate auto-approval after timeout (no challenge)
     */
    function autoApprove(uint256 _disputeID) external {
        _giveRuling(_disputeID, 1); // 1 = Approve
    }
    
    /**
     * @notice Simulate rejection
     */
    function reject(uint256 _disputeID) external {
        _giveRuling(_disputeID, 2); // 2 = Reject
    }
    
    /**
     * @notice Withdraw accumulated fees (for testing)
     */
    function withdraw() external {
        payable(msg.sender).transfer(address(this).balance);
    }
    
    receive() external payable {}
}
