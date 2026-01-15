export { AMTTPClient } from './client.js';
export { MLService, createMLService } from './ml.js';
export { CrossChainService, createCrossChainService, LZ_CHAIN_IDS } from './crosschain.js';
export type { ChainName, CrossChainRiskScore, CrossChainMessageResult, CrossChainConfig } from './crosschain.js';
export { PolicyAction, RiskLevel } from './types.js';
export type { AMTTPConfig, TransactionRequest, TransactionMetadata, RiskScore, KYCStatus, SwapParams, PolicySettings, AMTTPResult, } from './types.js';
export { AMTTP_ABI, CROSSCHAIN_ABI } from './abi.js';
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
     * Get action color for UI
     */
    getActionColor: (action: string) => string;
    /**
     * Check if address is valid Ethereum address
     */
    isValidAddress: (address: string) => boolean;
    /**
     * Format wei amount to readable string
     */
    formatAmount: (wei: bigint, decimals?: number) => string;
    /**
     * Convert risk score (0-1) to contract format (0-1000)
     */
    toContractScore: (score: number) => number;
    /**
     * Convert contract score (0-1000) to normalized (0-1)
     */
    fromContractScore: (score: number) => number;
};
//# sourceMappingURL=index.d.ts.map