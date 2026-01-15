// src/crosschain.ts
import { ethers } from 'ethers';
import { CROSSCHAIN_ABI } from './abi.js';
/**
 * LayerZero Chain IDs
 */
export const LZ_CHAIN_IDS = {
    ethereum: 101,
    polygon: 109,
    arbitrum: 110,
    optimism: 111,
    base: 184,
    bsc: 102,
    avalanche: 106
};
/**
 * CrossChainService - LayerZero integration for AMTTP
 *
 * Enables cross-chain risk score propagation and global address blocking
 */
export class CrossChainService {
    constructor(config) {
        this.provider = config.provider;
        this.signer = config.signer;
        const contractInterface = new ethers.Interface(CROSSCHAIN_ABI);
        this.contract = new ethers.Contract(config.crossChainAddress, contractInterface, config.signer || config.provider);
    }
    /**
     * Get the LayerZero chain ID for a chain name
     */
    getChainId(chain) {
        return LZ_CHAIN_IDS[chain];
    }
    /**
     * Get chain name from LayerZero chain ID
     */
    getChainName(chainId) {
        const entry = Object.entries(LZ_CHAIN_IDS).find(([_, id]) => id === chainId);
        return entry ? entry[0] : 'Unknown';
    }
    /**
     * Get aggregated risk score across all chains
     */
    async getAggregatedRiskScore(address) {
        const [maxScore, sourceChain] = await this.contract.getAggregatedRiskScore(address);
        const isBlocked = await this.contract.isGloballyBlocked(address);
        const lastUpdate = await this.contract.lastRiskUpdate(address);
        return {
            address,
            maxScore: Number(maxScore),
            sourceChain: Number(sourceChain),
            chainName: this.getChainName(Number(sourceChain)),
            isGloballyBlocked: isBlocked,
            lastUpdate: Number(lastUpdate)
        };
    }
    /**
     * Check if an address is globally blocked across all chains
     */
    async isGloballyBlocked(address) {
        return await this.contract.isGloballyBlocked(address);
    }
    /**
     * Get risk score from a specific chain
     */
    async getRiskScoreFromChain(address, chain) {
        const chainId = this.getChainId(chain);
        const score = await this.contract.crossChainRiskScores(address, chainId);
        return Number(score);
    }
    /**
     * Estimate fee for sending risk score to another chain
     */
    async estimateRiskScoreFee(destinationChain, targetAddress, riskScore) {
        const chainId = this.getChainId(destinationChain);
        return await this.contract.estimateRiskScoreFee(chainId, targetAddress, riskScore);
    }
    /**
     * Send risk score to another chain
     */
    async sendRiskScore(destinationChain, targetAddress, riskScore, options) {
        if (!this.signer) {
            throw new Error('Signer required for sending transactions');
        }
        const chainId = this.getChainId(destinationChain);
        const adapterParams = options?.adapterParams || '0x';
        // Estimate fee
        const fee = await this.estimateRiskScoreFee(destinationChain, targetAddress, riskScore);
        // Add 10% buffer for gas fluctuations
        const feeWithBuffer = (fee * 110n) / 100n;
        const tx = await this.contract.sendRiskScore(chainId, targetAddress, riskScore, adapterParams, { value: feeWithBuffer });
        const receipt = await tx.wait();
        // Extract message ID from events
        const event = receipt.logs.find((log) => {
            try {
                const parsed = this.contract.interface.parseLog(log);
                return parsed?.name === 'RiskScoreSent';
            }
            catch {
                return false;
            }
        });
        const messageId = event ? this.contract.interface.parseLog(event)?.args?.messageId : '0x';
        return {
            success: receipt.status === 1,
            transactionHash: receipt.hash,
            messageId,
            destinationChain: chainId,
            fee
        };
    }
    /**
     * Block an address globally across multiple chains
     */
    async blockAddressGlobally(destinationChains, targetAddress, reason) {
        if (!this.signer) {
            throw new Error('Signer required for sending transactions');
        }
        const chainIds = destinationChains.map(c => this.getChainId(c));
        // Estimate total fee
        let totalFee = 0n;
        for (const chainId of chainIds) {
            const fee = await this.contract.estimateRiskScoreFee(chainId, targetAddress, 1000);
            totalFee += fee;
        }
        // Add 20% buffer for multiple messages
        const feeWithBuffer = (totalFee * 120n) / 100n;
        const tx = await this.contract.blockAddressGlobally(chainIds, targetAddress, reason, { value: feeWithBuffer });
        const receipt = await tx.wait();
        return {
            success: receipt.status === 1,
            transactionHash: receipt.hash,
            messageId: ethers.keccak256(ethers.toUtf8Bytes(`block-${targetAddress}-${Date.now()}`)),
            destinationChain: chainIds[0],
            fee: totalFee
        };
    }
    /**
     * Unblock an address globally
     */
    async unblockAddressGlobally(destinationChains, targetAddress) {
        if (!this.signer) {
            throw new Error('Signer required for sending transactions');
        }
        const chainIds = destinationChains.map(c => this.getChainId(c));
        let totalFee = 0n;
        for (const chainId of chainIds) {
            const fee = await this.contract.estimateRiskScoreFee(chainId, targetAddress, 0);
            totalFee += fee;
        }
        const feeWithBuffer = (totalFee * 120n) / 100n;
        const tx = await this.contract.unblockAddressGlobally(chainIds, targetAddress, { value: feeWithBuffer });
        const receipt = await tx.wait();
        return {
            success: receipt.status === 1,
            transactionHash: receipt.hash,
            messageId: ethers.keccak256(ethers.toUtf8Bytes(`unblock-${targetAddress}-${Date.now()}`)),
            destinationChain: chainIds[0],
            fee: totalFee
        };
    }
    /**
     * Get list of supported chains
     */
    getSupportedChains() {
        return Object.keys(LZ_CHAIN_IDS);
    }
    /**
     * Get all chain IDs
     */
    getAllChainIds() {
        return Object.values(LZ_CHAIN_IDS);
    }
    /**
     * Check if chain is supported
     */
    isChainSupported(chain) {
        return chain in LZ_CHAIN_IDS;
    }
}
/**
 * Create a new CrossChainService instance
 */
export function createCrossChainService(config) {
    return new CrossChainService(config);
}
//# sourceMappingURL=crosschain.js.map