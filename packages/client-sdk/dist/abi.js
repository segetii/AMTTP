// src/abi.ts
export const AMTTP_ABI = [
    {
        "inputs": [
            { "internalType": "address", "name": "_oracle", "type": "address" },
            { "internalType": "uint256", "name": "_threshold", "type": "uint256" }
        ],
        "name": "initialize",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "seller", "type": "address" },
            { "internalType": "bytes32", "name": "hashlock", "type": "bytes32" },
            { "internalType": "uint256", "name": "timelock", "type": "uint256" },
            { "internalType": "uint8", "name": "riskLevel", "type": "uint8" },
            { "internalType": "bytes32", "name": "kycHash", "type": "bytes32" },
            { "internalType": "bytes", "name": "oracleSignature", "type": "bytes" }
        ],
        "name": "initiateSwap",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "bytes32", "name": "swapId", "type": "bytes32" },
            { "internalType": "bytes32", "name": "preimage", "type": "bytes32" }
        ],
        "name": "completeSwap",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "bytes32", "name": "swapId", "type": "bytes32" }
        ],
        "name": "refund",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "bytes32", "name": "swapId", "type": "bytes32" }
        ],
        "name": "getSwap",
        "outputs": [
            {
                "components": [
                    { "internalType": "address", "name": "buyer", "type": "address" },
                    { "internalType": "address", "name": "seller", "type": "address" },
                    { "internalType": "uint256", "name": "amount", "type": "uint256" },
                    { "internalType": "bytes32", "name": "hashlock", "type": "bytes32" },
                    { "internalType": "uint256", "name": "timelock", "type": "uint256" },
                    { "internalType": "uint8", "name": "riskLevel", "type": "uint8" },
                    { "internalType": "bytes32", "name": "kycHash", "type": "bytes32" },
                    { "internalType": "bool", "name": "completed", "type": "bool" },
                    { "internalType": "bool", "name": "refunded", "type": "bool" }
                ],
                "internalType": "struct AMTTP.Swap",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "approver", "type": "address" }
        ],
        "name": "addApprover",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "approver", "type": "address" }
        ],
        "name": "removeApprover",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "uint256", "name": "_threshold", "type": "uint256" }
        ],
        "name": "setThreshold",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "_oracle", "type": "address" }
        ],
        "name": "setOracle",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "", "type": "address" }
        ],
        "name": "isApprover",
        "outputs": [
            { "internalType": "bool", "name": "", "type": "bool" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "threshold",
        "outputs": [
            { "internalType": "uint256", "name": "", "type": "uint256" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "oracle",
        "outputs": [
            { "internalType": "address", "name": "", "type": "address" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [
            { "internalType": "address", "name": "", "type": "address" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "bytes32", "name": "swapId", "type": "bytes32" },
            { "indexed": true, "internalType": "address", "name": "buyer", "type": "address" },
            { "indexed": true, "internalType": "address", "name": "seller", "type": "address" },
            { "indexed": false, "internalType": "uint256", "name": "amount", "type": "uint256" },
            { "indexed": false, "internalType": "uint8", "name": "riskLevel", "type": "uint8" }
        ],
        "name": "SwapInitiated",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "bytes32", "name": "swapId", "type": "bytes32" },
            { "indexed": false, "internalType": "bytes32", "name": "preimage", "type": "bytes32" }
        ],
        "name": "SwapCompleted",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "bytes32", "name": "swapId", "type": "bytes32" }
        ],
        "name": "SwapRefunded",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "address", "name": "approver", "type": "address" }
        ],
        "name": "ApproverAdded",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "address", "name": "approver", "type": "address" }
        ],
        "name": "ApproverRemoved",
        "type": "event"
    }
];
// Cross-chain contract ABI (LayerZero integration)
export const CROSSCHAIN_ABI = [
    {
        "inputs": [
            { "internalType": "address", "name": "_address", "type": "address" }
        ],
        "name": "getAggregatedRiskScore",
        "outputs": [
            { "internalType": "uint256", "name": "maxScore", "type": "uint256" },
            { "internalType": "uint16", "name": "sourceChain", "type": "uint16" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "_address", "type": "address" }
        ],
        "name": "isGloballyBlocked",
        "outputs": [
            { "internalType": "bool", "name": "", "type": "bool" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "", "type": "address" },
            { "internalType": "uint16", "name": "", "type": "uint16" }
        ],
        "name": "crossChainRiskScores",
        "outputs": [
            { "internalType": "uint256", "name": "", "type": "uint256" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "address", "name": "", "type": "address" }
        ],
        "name": "lastRiskUpdate",
        "outputs": [
            { "internalType": "uint256", "name": "", "type": "uint256" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "uint16", "name": "_dstChainId", "type": "uint16" },
            { "internalType": "address", "name": "_targetAddress", "type": "address" },
            { "internalType": "uint256", "name": "_riskScore", "type": "uint256" }
        ],
        "name": "estimateRiskScoreFee",
        "outputs": [
            { "internalType": "uint256", "name": "nativeFee", "type": "uint256" }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "uint16", "name": "_dstChainId", "type": "uint16" },
            { "internalType": "address", "name": "_targetAddress", "type": "address" },
            { "internalType": "uint256", "name": "_riskScore", "type": "uint256" },
            { "internalType": "bytes", "name": "_adapterParams", "type": "bytes" }
        ],
        "name": "sendRiskScore",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "uint16[]", "name": "_dstChainIds", "type": "uint16[]" },
            { "internalType": "address", "name": "_targetAddress", "type": "address" },
            { "internalType": "string", "name": "_reason", "type": "string" }
        ],
        "name": "blockAddressGlobally",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            { "internalType": "uint16[]", "name": "_dstChainIds", "type": "uint16[]" },
            { "internalType": "address", "name": "_targetAddress", "type": "address" }
        ],
        "name": "unblockAddressGlobally",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "uint16", "name": "dstChainId", "type": "uint16" },
            { "indexed": true, "internalType": "address", "name": "targetAddress", "type": "address" },
            { "indexed": false, "internalType": "uint256", "name": "riskScore", "type": "uint256" },
            { "indexed": false, "internalType": "bytes32", "name": "messageId", "type": "bytes32" }
        ],
        "name": "RiskScoreSent",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "uint16", "name": "srcChainId", "type": "uint16" },
            { "indexed": true, "internalType": "address", "name": "targetAddress", "type": "address" },
            { "indexed": false, "internalType": "uint256", "name": "riskScore", "type": "uint256" },
            { "indexed": false, "internalType": "uint64", "name": "nonce", "type": "uint64" }
        ],
        "name": "RiskScoreReceived",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "address", "name": "targetAddress", "type": "address" },
            { "indexed": true, "internalType": "uint16", "name": "originChain", "type": "uint16" },
            { "indexed": false, "internalType": "string", "name": "reason", "type": "string" }
        ],
        "name": "AddressBlockedGlobally",
        "type": "event"
    },
    {
        "anonymous": false,
        "inputs": [
            { "indexed": true, "internalType": "address", "name": "targetAddress", "type": "address" },
            { "indexed": true, "internalType": "uint16", "name": "originChain", "type": "uint16" }
        ],
        "name": "AddressUnblockedGlobally",
        "type": "event"
    }
];
//# sourceMappingURL=abi.js.map