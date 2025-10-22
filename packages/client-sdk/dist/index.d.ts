export { AMTTPClient } from './client.js';
export type { AMTTPConfig, TransactionRequest, TransactionMetadata, RiskScore, KYCStatus, SwapParams, PolicySettings, AMTTPResult } from './types.js';
export { AMTTP_ABI } from './abi.js';
export declare const utils: {
    /**
     * Format risk score for display
     */
    formatRiskScore: (score: number) => string;
    /**
     * Get risk color for UI
     */
    getRiskColor: (category: string) => string;
    /**
     * Check if address is valid Ethereum address
     */
    isValidAddress: (address: string) => boolean;
    /**
     * Format wei amount to readable string
     */
    formatAmount: (wei: bigint, decimals?: number) => string;
};
//# sourceMappingURL=index.d.ts.map