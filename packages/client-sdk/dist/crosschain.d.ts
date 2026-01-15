import { ethers } from 'ethers';
/**
 * LayerZero Chain IDs
 */
export declare const LZ_CHAIN_IDS: {
    readonly ethereum: 101;
    readonly polygon: 109;
    readonly arbitrum: 110;
    readonly optimism: 111;
    readonly base: 184;
    readonly bsc: 102;
    readonly avalanche: 106;
};
export type ChainName = keyof typeof LZ_CHAIN_IDS;
/**
 * Cross-chain risk score result
 */
export interface CrossChainRiskScore {
    address: string;
    maxScore: number;
    sourceChain: number;
    chainName: string;
    isGloballyBlocked: boolean;
    lastUpdate: number;
}
/**
 * Cross-chain message result
 */
export interface CrossChainMessageResult {
    success: boolean;
    transactionHash: string;
    messageId: string;
    destinationChain: number;
    fee: bigint;
}
/**
 * Cross-chain configuration
 */
export interface CrossChainConfig {
    crossChainAddress: string;
    provider: ethers.Provider;
    signer?: ethers.Signer;
}
/**
 * CrossChainService - LayerZero integration for AMTTP
 *
 * Enables cross-chain risk score propagation and global address blocking
 */
export declare class CrossChainService {
    private contract;
    private provider;
    private signer?;
    constructor(config: CrossChainConfig);
    /**
     * Get the LayerZero chain ID for a chain name
     */
    getChainId(chain: ChainName): number;
    /**
     * Get chain name from LayerZero chain ID
     */
    getChainName(chainId: number): string;
    /**
     * Get aggregated risk score across all chains
     */
    getAggregatedRiskScore(address: string): Promise<CrossChainRiskScore>;
    /**
     * Check if an address is globally blocked across all chains
     */
    isGloballyBlocked(address: string): Promise<boolean>;
    /**
     * Get risk score from a specific chain
     */
    getRiskScoreFromChain(address: string, chain: ChainName): Promise<number>;
    /**
     * Estimate fee for sending risk score to another chain
     */
    estimateRiskScoreFee(destinationChain: ChainName, targetAddress: string, riskScore: number): Promise<bigint>;
    /**
     * Send risk score to another chain
     */
    sendRiskScore(destinationChain: ChainName, targetAddress: string, riskScore: number, options?: {
        adapterParams?: string;
    }): Promise<CrossChainMessageResult>;
    /**
     * Block an address globally across multiple chains
     */
    blockAddressGlobally(destinationChains: ChainName[], targetAddress: string, reason: string): Promise<CrossChainMessageResult>;
    /**
     * Unblock an address globally
     */
    unblockAddressGlobally(destinationChains: ChainName[], targetAddress: string): Promise<CrossChainMessageResult>;
    /**
     * Get list of supported chains
     */
    getSupportedChains(): ChainName[];
    /**
     * Get all chain IDs
     */
    getAllChainIds(): number[];
    /**
     * Check if chain is supported
     */
    isChainSupported(chain: string): chain is ChainName;
}
/**
 * Create a new CrossChainService instance
 */
export declare function createCrossChainService(config: CrossChainConfig): CrossChainService;
//# sourceMappingURL=crosschain.d.ts.map