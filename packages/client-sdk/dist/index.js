// src/index.ts
export { AMTTPClient } from './client.js';
export { AMTTP_ABI } from './abi.js';
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
    }
};
//# sourceMappingURL=index.js.map