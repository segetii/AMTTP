// src/index.ts
export { AMTTPClient } from './client.js';
export { MLService, createMLService } from './ml.js';
export { CrossChainService, createCrossChainService, LZ_CHAIN_IDS } from './crosschain.js';
export { PolicyAction, RiskLevel } from './types.js';
export { AMTTP_ABI, CROSSCHAIN_ABI } from './abi.js';
// Utility functions
export const utils = {
    /**
     * Format risk score for display
     */
    formatRiskScore: (score) => {
        return `${(score * 100).toFixed(1)}%`;
    },
    /**
     * Get risk color for UI
     */
    getRiskColor: (category) => {
        switch (category) {
            case 'MINIMAL': return '#22c55e'; // green
            case 'LOW': return '#84cc16'; // lime  
            case 'MEDIUM': return '#f59e0b'; // amber
            case 'HIGH': return '#ef4444'; // red
            default: return '#6b7280'; // gray
        }
    },
    /**
     * Get action color for UI
     */
    getActionColor: (action) => {
        switch (action) {
            case 'APPROVE': return '#22c55e'; // green
            case 'REVIEW': return '#f59e0b'; // amber
            case 'ESCROW': return '#f97316'; // orange
            case 'BLOCK': return '#ef4444'; // red
            default: return '#6b7280'; // gray
        }
    },
    /**
     * Check if address is valid Ethereum address
     */
    isValidAddress: (address) => {
        return /^0x[a-fA-F0-9]{40}$/.test(address);
    },
    /**
     * Format wei amount to readable string
     */
    formatAmount: (wei, decimals = 18) => {
        return (Number(wei) / Math.pow(10, decimals)).toFixed(4);
    },
    /**
     * Convert risk score (0-1) to contract format (0-1000)
     */
    toContractScore: (score) => {
        return Math.round(Math.max(0, Math.min(1, score)) * 1000);
    },
    /**
     * Convert contract score (0-1000) to normalized (0-1)
     */
    fromContractScore: (score) => {
        return Math.max(0, Math.min(1000, score)) / 1000;
    }
};
//# sourceMappingURL=index.js.map