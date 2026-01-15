// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "./interfaces/IKleros.sol";

/**
 * @title AMTTPDisputeResolver
 * @notice Decentralized dispute resolution for high-risk transactions using Kleros
 * @dev Implements IArbitrable to receive rulings from Kleros Court
 * 
 * Flow:
 * 1. ML/Oracle flags transaction as HIGH_RISK
 * 2. Funds are escrowed in this contract
 * 3. Challenge window opens (e.g., 24 hours)
 * 4. Anyone can challenge → Creates Kleros dispute
 * 5. Kleros jurors vote on evidence
 * 6. Ruling executed: APPROVE (release funds) or REJECT (return to sender)
 */
contract AMTTPDisputeResolver is IArbitrable, IEvidence, Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;
    
    // ============================================================
    // CONSTANTS
    // ============================================================
    
    uint256 public constant RULING_OPTIONS = 2;  // Approve or Reject
    uint256 public constant RULING_APPROVE = 1;
    uint256 public constant RULING_REJECT = 2;
    
    // Kleros Court IDs (Sepolia testnet)
    // See: https://docs.kleros.io/products/court/kleros-court-v2
    bytes public constant EXTRA_DATA = abi.encodePacked(
        uint96(0),      // General Court
        uint96(3),      // Min jurors
        uint96(1)       // Dispute kit
    );
    
    // ============================================================
    // STATE
    // ============================================================
    
    IArbitrator public immutable arbitrator;
    
    uint256 public challengeWindow = 24 hours;
    uint256 public metaEvidenceID;
    
    enum EscrowStatus {
        None,
        Pending,        // Waiting for challenge window
        Challenged,     // Dispute created in Kleros
        Resolved,       // Ruling received
        Executed        // Funds transferred
    }
    
    struct EscrowedTransaction {
        bytes32 txId;
        address sender;
        address recipient;
        address token;          // address(0) for ETH, token address for ERC20
        uint256 amount;
        uint256 riskScore;
        uint256 createdAt;
        uint256 challengeDeadline;
        EscrowStatus status;
        uint256 disputeID;
        uint256 ruling;
        uint8 partialPct;       // percentage given to recipient when partial ruling is used (0-100)
        string evidenceURI;     // IPFS link to ML evidence
    }
    
    // txId => EscrowedTransaction
    mapping(bytes32 => EscrowedTransaction) public escrows;
    
    // disputeID => txId (for Kleros callback)
    mapping(uint256 => bytes32) public disputeToTx;
    
    // Evidence group counter
    uint256 public evidenceGroupCounter;
    
    // txId => evidenceGroupID
    mapping(bytes32 => uint256) public txToEvidenceGroup;
    
    // ============================================================
    // EVENTS
    // ============================================================
    
    event TransactionEscrowed(
        bytes32 indexed txId,
        address indexed sender,
        address indexed recipient,
        address token,
        uint256 amount,
        uint256 riskScore,
        uint256 challengeDeadline
    );

    event AppealRequested(bytes32 indexed txId, address indexed requester, uint256 timestamp);
    
    event TransactionChallenged(
        bytes32 indexed txId,
        address indexed challenger,
        uint256 disputeID
    );
    
    event TransactionApproved(
        bytes32 indexed txId,
        address indexed recipient,
        uint256 amount
    );
    
    event TransactionRejected(
        bytes32 indexed txId,
        address indexed sender,
        uint256 amount
    );
    
    event ChallengeWindowExpired(
        bytes32 indexed txId,
        address indexed recipient,
        uint256 amount
    );
    
    // ============================================================
    // CONSTRUCTOR
    // ============================================================
    
    /**
     * @param _arbitrator Address of Kleros Arbitrator contract
     * @param _metaEvidenceURI IPFS URI containing dispute metadata/rules
     */
    constructor(
        address _arbitrator,
        string memory _metaEvidenceURI
    ) {
        require(_arbitrator != address(0), "Invalid arbitrator");
        arbitrator = IArbitrator(_arbitrator);
        
        // Emit MetaEvidence for this dispute type
        emit MetaEvidence(metaEvidenceID, _metaEvidenceURI);
    }
    
    // ============================================================
    // ESCROW FUNCTIONS
    // ============================================================
    
    /**
     * @notice Escrow a high-risk transaction for potential dispute
     * @param _txId Unique transaction identifier
     * @param _recipient Intended recipient of funds
     * @param _riskScore Risk score from ML model (0-1000)
     * @param _evidenceURI IPFS URI with ML evidence (features, signals, etc.)
     */
    function escrowTransaction(
        bytes32 _txId,
        address _recipient,
        uint256 _riskScore,
        string calldata _evidenceURI
    ) external payable nonReentrant {
        require(msg.value > 0, "No funds sent");
        require(_recipient != address(0), "Invalid recipient");
        require(escrows[_txId].status == EscrowStatus.None, "TX already exists");
        
        uint256 deadline = block.timestamp + challengeWindow;
        uint256 evidenceGroup = ++evidenceGroupCounter;
        
        escrows[_txId] = EscrowedTransaction({
            txId: _txId,
            sender: msg.sender,
            recipient: _recipient,
            token: address(0),
            amount: msg.value,
            riskScore: _riskScore,
            createdAt: block.timestamp,
            challengeDeadline: deadline,
            status: EscrowStatus.Pending,
            disputeID: 0,
            ruling: 0,
            partialPct: 0,
            evidenceURI: _evidenceURI
        });
        
        txToEvidenceGroup[_txId] = evidenceGroup;
        
        emit TransactionEscrowed(
            _txId,
            msg.sender,
            _recipient,
            address(0),
            msg.value,
            _riskScore,
            deadline
        );
        
        // Auto-submit ML evidence
        if (bytes(_evidenceURI).length > 0) {
            emit Evidence(arbitrator, evidenceGroup, msg.sender, _evidenceURI);
        }
    }
    
    /**
     * @notice Challenge an escrowed transaction - creates Kleros dispute
     * @param _txId Transaction to challenge
     */
    function challengeTransaction(bytes32 _txId) external payable nonReentrant {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        require(escrow.status == EscrowStatus.Pending, "Not challengeable");
        require(block.timestamp < escrow.challengeDeadline, "Challenge window closed");
        
        // Get arbitration cost
        uint256 arbitrationCost = arbitrator.arbitrationCost(EXTRA_DATA);
        require(msg.value >= arbitrationCost, "Insufficient arbitration fee");
        
        // CEI: Update state BEFORE external call to prevent reentrancy
        escrow.status = EscrowStatus.Challenged;
        
        // Create dispute in Kleros
        uint256 disputeID = arbitrator.createDispute{value: arbitrationCost}(
            RULING_OPTIONS,
            EXTRA_DATA
        );
        
        // Update remaining state after getting disputeID
        escrow.disputeID = disputeID;
        disputeToTx[disputeID] = _txId;
        
        // Emit dispute event for Kleros
        emit Dispute(
            arbitrator,
            disputeID,
            metaEvidenceID,
            txToEvidenceGroup[_txId]
        );
        
        emit TransactionChallenged(_txId, msg.sender, disputeID);
        
        // Refund excess
        if (msg.value > arbitrationCost) {
            payable(msg.sender).transfer(msg.value - arbitrationCost);
        }
    }

    /**
     * @notice Escrow an ERC20 token for potential dispute
     * @param _txId Unique transaction identifier
     * @param _recipient Intended recipient of funds
     * @param _token ERC20 token address
     * @param _amount Amount of tokens to escrow
     * @param _riskScore Risk score from ML model (0-1000)
     * @param _evidenceURI IPFS URI with ML evidence
     */
    function escrowTransactionERC20(
        bytes32 _txId,
        address _recipient,
        address _token,
        uint256 _amount,
        uint256 _riskScore,
        string calldata _evidenceURI
    ) external nonReentrant {
        require(_amount > 0, "No funds sent");
        require(_recipient != address(0), "Invalid recipient");
        require(_token != address(0), "Invalid token");
        require(escrows[_txId].status == EscrowStatus.None, "TX already exists");

        uint256 deadline = block.timestamp + challengeWindow;
        uint256 evidenceGroup = ++evidenceGroupCounter;

        // Transfer tokens to contract
        IERC20(_token).safeTransferFrom(msg.sender, address(this), _amount);

        escrows[_txId] = EscrowedTransaction({
            txId: _txId,
            sender: msg.sender,
            recipient: _recipient,
            token: _token,
            amount: _amount,
            riskScore: _riskScore,
            createdAt: block.timestamp,
            challengeDeadline: deadline,
            status: EscrowStatus.Pending,
            disputeID: 0,
            ruling: 0,
            partialPct: 0,
            evidenceURI: _evidenceURI
        });

        txToEvidenceGroup[_txId] = evidenceGroup;

        emit TransactionEscrowed(
            _txId,
            msg.sender,
            _recipient,
            _token,
            _amount,
            _riskScore,
            deadline
        );

        if (bytes(_evidenceURI).length > 0) {
            emit Evidence(arbitrator, evidenceGroup, msg.sender, _evidenceURI);
        }
    }
    
    /**
     * @notice Submit additional evidence for a dispute
     * @param _txId Transaction ID
     * @param _evidenceURI IPFS URI with evidence
     */
    function submitEvidence(bytes32 _txId, string calldata _evidenceURI) external {
        EscrowedTransaction storage escrow = escrows[_txId];
        require(escrow.status == EscrowStatus.Challenged, "No active dispute");
        require(
            msg.sender == escrow.sender || msg.sender == escrow.recipient,
            "Not a party"
        );
        
        emit Evidence(
            arbitrator,
            txToEvidenceGroup[_txId],
            msg.sender,
            _evidenceURI
        );
    }
    
    // ============================================================
    // KLEROS CALLBACK
    // ============================================================
    
    /**
     * @notice Called by Kleros when jurors reach a ruling
     * @param _disputeID The dispute ID
     * @param _ruling 1 = Approve (release to recipient), 2 = Reject (return to sender)
     */
    function rule(uint256 _disputeID, uint256 _ruling) external override {
        require(msg.sender == address(arbitrator), "Only arbitrator");
        
        bytes32 txId = disputeToTx[_disputeID];
        require(txId != bytes32(0), "Unknown dispute");
        
        EscrowedTransaction storage escrow = escrows[txId];
        require(escrow.status == EscrowStatus.Challenged, "Not challenged");
        
        escrow.status = EscrowStatus.Resolved;
        escrow.ruling = _ruling;
        
    // If arbitrator provided extra metadata indicating a partial pct, we don't have it here.
    // Owners/operators can set defaultPartialPct per-escrow in advance if needed via setEscrowPartialPct.
        
        emit Ruling(arbitrator, _disputeID, _ruling);
        
        // Execute ruling
        _executeRuling(txId);
    }
    
    // ============================================================
    // EXECUTION
    // ============================================================
    
    /**
     * @notice Execute the ruling or release after challenge window
     * @param _txId Transaction to execute
     */
    function executeTransaction(bytes32 _txId) external nonReentrant {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        if (escrow.status == EscrowStatus.Pending) {
            // No challenge - release after window expires
            require(
                block.timestamp >= escrow.challengeDeadline,
                "Challenge window active"
            );
            
            // Cache values before state change (CEI pattern)
            address recipient = escrow.recipient;
            uint256 amount = escrow.amount;
            
            escrow.status = EscrowStatus.Executed;
            
            // Emit event BEFORE external call (CEI pattern)
            emit ChallengeWindowExpired(_txId, recipient, amount);
            
            payable(recipient).transfer(amount);
            
        } else if (escrow.status == EscrowStatus.Resolved) {
            _executeRuling(_txId);
        } else {
            revert("Cannot execute");
        }
    }

    /**
     * @notice Request an appeal (off-chain coordination required to submit evidence to Kleros)
     * @param _txId Transaction ID to appeal
     */
    function requestAppeal(bytes32 _txId) external {
        EscrowedTransaction storage escrow = escrows[_txId];
        require(escrow.status == EscrowStatus.Resolved, "Not resolved");
        require(msg.sender == escrow.sender || msg.sender == escrow.recipient, "Not a party");

        emit AppealRequested(_txId, msg.sender, block.timestamp);
    }

    /**
     * @notice Set partial percentage for an escrow (only owner/operator). Useful when arbitrator indicates partial split off-chain.
     */
    function setEscrowPartialPct(bytes32 _txId, uint8 _pct) external onlyOwner {
        require(_pct <= 100, "Invalid pct");
        EscrowedTransaction storage escrow = escrows[_txId];
        escrow.partialPct = _pct;
    }
    
    function _executeRuling(bytes32 _txId) internal {
        EscrowedTransaction storage escrow = escrows[_txId];
        
        if (escrow.status == EscrowStatus.Executed) return;
        
        escrow.status = EscrowStatus.Executed;
        
        // Cache values to prevent reentrancy issues
        address recipient = escrow.recipient;
        address sender = escrow.sender;
        uint256 amount = escrow.amount;
        address token = escrow.token;
        uint256 ruling = escrow.ruling;
        uint256 pct = escrow.partialPct;
        
        if (ruling == RULING_APPROVE) {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionApproved(_txId, recipient, amount);
            // Explicitly approved by arbitrator - release to recipient
            if (token == address(0)) {
                payable(recipient).transfer(amount);
            } else {
                IERC20(token).safeTransfer(recipient, amount);
            }
        } else if (ruling == RULING_REJECT) {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionRejected(_txId, sender, amount);
            // Reject - return to sender
            if (token == address(0)) {
                payable(sender).transfer(amount);
            } else {
                IERC20(token).safeTransfer(sender, amount);
            }
        } else if (ruling == 3) {
            // Partial ruling - use partialPct stored on escrow (default 0 means fully reject)
            if (pct == 0) {
                // Emit event BEFORE external call (CEI pattern)
                emit TransactionRejected(_txId, sender, amount);
                // treat as reject
                if (token == address(0)) {
                    payable(sender).transfer(amount);
                } else {
                    IERC20(token).safeTransfer(sender, amount);
                }
            } else {
                uint256 toRecipient = (amount * pct) / 100;
                uint256 toSender = amount - toRecipient;
                // Emit events BEFORE external calls (CEI pattern)
                emit TransactionApproved(_txId, recipient, toRecipient);
                emit TransactionRejected(_txId, sender, toSender);
                if (token == address(0)) {
                    if (toRecipient > 0) payable(recipient).transfer(toRecipient);
                    if (toSender > 0) payable(sender).transfer(toSender);
                } else {
                    if (toRecipient > 0) IERC20(token).safeTransfer(recipient, toRecipient);
                    if (toSender > 0) IERC20(token).safeTransfer(sender, toSender);
                }
            }
        } else {
            // Emit event BEFORE external call (CEI pattern)
            emit TransactionRejected(_txId, sender, amount);
            // Unknown ruling - default to reject
            if (token == address(0)) {
                payable(sender).transfer(amount);
            } else {
                IERC20(token).safeTransfer(sender, amount);
            }
        }
    }
    
    // ============================================================
    // VIEW FUNCTIONS
    // ============================================================
    
    /**
     * @notice Get the cost to challenge a transaction
     */
    function getChallengeCost() external view returns (uint256) {
        return arbitrator.arbitrationCost(EXTRA_DATA);
    }
    
    /**
     * @notice Get escrow details
     */
    function getEscrow(bytes32 _txId) external view returns (
        address sender,
        address recipient,
        address token,
        uint256 amount,
        uint256 riskScore,
        uint256 challengeDeadline,
        EscrowStatus status,
        uint256 disputeID,
        uint256 ruling
    ) {
        EscrowedTransaction storage e = escrows[_txId];
        return (
            e.sender,
            e.recipient,
            e.token,
            e.amount,
            e.riskScore,
            e.challengeDeadline,
            e.status,
            e.disputeID,
            e.ruling
        );
    }
    
    /**
     * @notice Check if transaction can be executed
     */
    function canExecute(bytes32 _txId) external view returns (bool) {
        EscrowedTransaction storage e = escrows[_txId];
        
        if (e.status == EscrowStatus.Pending) {
            return block.timestamp >= e.challengeDeadline;
        } else if (e.status == EscrowStatus.Resolved) {
            return true;
        }
        return false;
    }
    
    // ============================================================
    // ADMIN
    // ============================================================
    
    /**
     * @notice Update challenge window (owner only)
     */
    function setChallengeWindow(uint256 _window) external onlyOwner {
        require(_window >= 1 hours && _window <= 7 days, "Invalid window");
        challengeWindow = _window;
    }
    
    /**
     * @notice Update meta evidence for new dispute types
     */
    function updateMetaEvidence(string calldata _uri) external onlyOwner {
        metaEvidenceID++;
        emit MetaEvidence(metaEvidenceID, _uri);
    }
    
    /**
     * @notice Emergency withdraw (owner only, for stuck funds)
     * @dev Returns funds to original sender after 30 days past deadline
     */
    function emergencyWithdraw(bytes32 _txId) external onlyOwner nonReentrant {
        EscrowedTransaction storage e = escrows[_txId];
        require(e.status != EscrowStatus.Executed, "Already executed");
        require(
            block.timestamp > e.challengeDeadline + 30 days,
            "Too early"
        );
        
        // Cache values before state change (CEI pattern)
        address sender = e.sender;
        uint256 amount = e.amount;
        address token = e.token;
        
        e.status = EscrowStatus.Executed;
        
        // Emit event BEFORE external call (CEI pattern)
        emit TransactionRejected(_txId, sender, amount);
        
        // SECURITY FIX: Return funds to original sender, not owner
        if (token == address(0)) {
            payable(sender).transfer(amount);
        } else {
            IERC20(token).safeTransfer(sender, amount);
        }
    }
    
    // ============================================================
    // HEALTH CHECK & ANALYTICS
    // ============================================================
    
    /**
     * @notice Get contract health status for monitoring
     * @return arbitratorAddress The Kleros arbitrator address
     * @return currentChallengeWindow Current challenge window duration
     * @return currentMetaEvidenceID Current meta evidence version
     * @return contractBalance ETH balance held in contract
     * @return isOperational Whether the contract can accept new escrows
     */
    function healthCheck() external view returns (
        address arbitratorAddress,
        uint256 currentChallengeWindow,
        uint256 currentMetaEvidenceID,
        uint256 contractBalance,
        bool isOperational
    ) {
        return (
            address(arbitrator),
            challengeWindow,
            metaEvidenceID,
            address(this).balance,
            address(arbitrator) != address(0)
        );
    }
    
    /**
     * @notice Get token balance held in contract (for ERC20 escrows)
     * @param _token Token address to check
     */
    function getTokenBalance(address _token) external view returns (uint256) {
        return IERC20(_token).balanceOf(address(this));
    }
}
