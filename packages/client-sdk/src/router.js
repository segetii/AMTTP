/**
 * AMTTP Off-Chain Router SDK
 * 
 * Routes transactions to the correct contract based on asset type.
 * Saves ~21,000 gas per transaction by eliminating the on-chain router hop.
 * 
 * Architecture:
 * ┌──────────────────────────────────────────────────────────────────┐
 * │                    Frontend / dApp                               │
 * └────────────────────────────┬─────────────────────────────────────┘
 *                              │
 *                              ▼
 * ┌──────────────────────────────────────────────────────────────────┐
 * │               AMTTPRouter (Off-Chain SDK)                        │
 * │   • Asset type detection                                         │
 * │   • Contract selection                                           │
 * │   • Gas estimation                                               │
 * │   • Analytics (free)                                             │
 * └─────────┬──────────────────────────────────────┬─────────────────┘
 *           │                                      │
 *           ▼                                      ▼
 * ┌─────────────────────┐              ┌─────────────────────────────┐
 * │     AMTTPCore       │              │        AMTTPNFT             │
 * │   (ETH / ERC20)     │              │   (ERC721 / NFT-to-NFT)     │
 * └─────────────────────┘              └─────────────────────────────┘
 */

import { ethers } from 'ethers';

// Contract addresses (Sepolia)
export const CONTRACTS = {
    core: '0x2cF0a1D4FB44C97E80c7935E136a181304A67923',
    nft: '0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f',
    policyEngine: '0x520393A448543FF55f02ddA1218881a8E5851CEc',
    disputeResolver: '0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade',
    crossChain: '0xc8d887665411ecB4760435fb3d20586C1111bc37'
};

// Minimal ABIs for gas efficiency
const CORE_ABI = [
    'function initiateSwap(address seller, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes32 kycHash, bytes oracleSignature) payable returns (bytes32)',
    'function initiateSwapERC20(address seller, address token, uint256 amount, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes32 kycHash, bytes oracleSignature) returns (bytes32)',
    'function completeSwap(bytes32 swapId, bytes32 preimage)',
    'function refundSwap(bytes32 swapId)',
    'function approveSwap(bytes32 swapId)',
    'function raiseDispute(bytes32 swapId, string evidence) payable',
    'function getSwap(bytes32 swapId) view returns (tuple(address buyer, uint8 status, uint8 approvalCount, uint8 assetType, address seller, address token, uint256 amount, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes32 kycHash))'
];

const NFT_ABI = [
    'function initiateNFTtoETHSwap(address buyer, address nftContract, uint256 tokenId, uint256 ethAmount, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes32 kycHash, bytes oracleSignature) returns (bytes32)',
    'function initiateNFTtoNFTSwap(address partyB, address nftContractA, uint256 tokenIdA, address nftContractB, uint256 tokenIdB, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes oracleSignature) returns (bytes32)',
    'function depositETHForNFT(bytes32 swapId) payable',
    'function depositNFTForSwap(bytes32 swapId)',
    'function completeNFTSwap(bytes32 swapId, bytes32 preimage)',
    'function completeNFTtoNFTSwap(bytes32 swapId, bytes32 preimage)',
    'function refundNFTSwap(bytes32 swapId)',
    'function approveSwap(bytes32 swapId)',
    'function raiseDispute(bytes32 swapId, string evidence) payable',
    'function getNFTSwap(bytes32 swapId) view returns (tuple(address seller, address buyer, address nftContract, uint256 tokenId, uint256 ethAmount, bytes32 hashlock, uint256 timelock, uint256 riskScore, bytes32 kycHash, uint8 status, uint8 approvalCount, uint8 swapType))'
];

// Asset types for routing
export const AssetType = {
    ETH: 'ETH',
    ERC20: 'ERC20',
    ERC721: 'ERC721',
    NFT_TO_NFT: 'NFT_TO_NFT'
};

// Swap status mapping
export const SwapStatus = {
    0: 'Pending',
    1: 'Approved',
    2: 'Completed',
    3: 'Refunded',
    4: 'Disputed',
    5: 'Blocked'
};

/**
 * AMTTP Off-Chain Router
 */
export class AMTTPRouter {
    constructor(providerOrSigner, network = 'sepolia') {
        this.provider = providerOrSigner.provider || providerOrSigner;
        this.signer = providerOrSigner.provider ? providerOrSigner : null;
        
        // Use network-specific addresses
        const addresses = network === 'sepolia' ? CONTRACTS : CONTRACTS;
        
        this.core = new ethers.Contract(addresses.core, CORE_ABI, providerOrSigner);
        this.nft = new ethers.Contract(addresses.nft, NFT_ABI, providerOrSigner);
        
        // Off-chain analytics (free!)
        this.analytics = {
            totalSwaps: 0,
            ethVolume: 0n,
            erc20Volume: 0n,
            nftSwaps: 0
        };
        
        // Swap tracking
        this.swapRegistry = new Map();
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    ROUTING LOGIC (OFF-CHAIN)
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Detect asset type and return appropriate contract
     */
    getContractForAsset(assetType) {
        switch (assetType) {
            case AssetType.ETH:
            case AssetType.ERC20:
                return this.core;
            case AssetType.ERC721:
            case AssetType.NFT_TO_NFT:
                return this.nft;
            default:
                throw new Error(`Unknown asset type: ${assetType}`);
        }
    }

    /**
     * Auto-detect asset type from parameters
     */
    detectAssetType(params) {
        if (params.nftContractA && params.nftContractB) {
            return AssetType.NFT_TO_NFT;
        }
        if (params.nftContract) {
            return AssetType.ERC721;
        }
        if (params.token && params.token !== ethers.ZeroAddress) {
            return AssetType.ERC20;
        }
        return AssetType.ETH;
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    ETH / ERC20 SWAPS (via Core)
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Initiate ETH swap - routes directly to AMTTPCore
     * Saves 21,000 gas vs on-chain router
     */
    async swapETH(seller, hashlock, timelock, riskScore, kycHash, oracleSignature, ethAmount) {
        const tx = await this.core.initiateSwap(
            seller,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature,
            { value: ethAmount }
        );
        
        const receipt = await tx.wait();
        const swapId = this._extractSwapId(receipt);
        
        // Track off-chain
        this._recordSwap(swapId, AssetType.ETH, ethAmount);
        
        return { tx, receipt, swapId };
    }

    /**
     * Initiate ERC20 swap
     */
    async swapERC20(seller, token, amount, hashlock, timelock, riskScore, kycHash, oracleSignature) {
        const tx = await this.core.initiateSwapERC20(
            seller,
            token,
            amount,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature
        );
        
        const receipt = await tx.wait();
        const swapId = this._extractSwapId(receipt);
        
        this._recordSwap(swapId, AssetType.ERC20, amount);
        
        return { tx, receipt, swapId };
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    NFT SWAPS (via AMTTPNFT)
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Initiate NFT-to-ETH swap
     */
    async swapNFTforETH(buyer, nftContract, tokenId, ethAmount, hashlock, timelock, riskScore, kycHash, oracleSignature) {
        const tx = await this.nft.initiateNFTtoETHSwap(
            buyer,
            nftContract,
            tokenId,
            ethAmount,
            hashlock,
            timelock,
            riskScore,
            kycHash,
            oracleSignature
        );
        
        const receipt = await tx.wait();
        const swapId = this._extractSwapId(receipt);
        
        this._recordSwap(swapId, AssetType.ERC721, ethAmount);
        
        return { tx, receipt, swapId };
    }

    /**
     * Initiate NFT-to-NFT atomic swap
     */
    async swapNFTforNFT(partyB, nftContractA, tokenIdA, nftContractB, tokenIdB, hashlock, timelock, riskScore, oracleSignature) {
        const tx = await this.nft.initiateNFTtoNFTSwap(
            partyB,
            nftContractA,
            tokenIdA,
            nftContractB,
            tokenIdB,
            hashlock,
            timelock,
            riskScore,
            oracleSignature
        );
        
        const receipt = await tx.wait();
        const swapId = this._extractSwapId(receipt);
        
        this._recordSwap(swapId, AssetType.NFT_TO_NFT, 0n);
        
        return { tx, receipt, swapId };
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    UNIVERSAL OPERATIONS
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Complete any swap - auto-routes based on swap type
     */
    async completeSwap(swapId, preimage) {
        const swapInfo = this.swapRegistry.get(swapId);
        
        if (!swapInfo) {
            // Try to detect from chain
            const assetType = await this._detectSwapType(swapId);
            return this._completeByType(swapId, preimage, assetType);
        }
        
        return this._completeByType(swapId, preimage, swapInfo.assetType);
    }

    async _completeByType(swapId, preimage, assetType) {
        let tx;
        
        switch (assetType) {
            case AssetType.ETH:
            case AssetType.ERC20:
                tx = await this.core.completeSwap(swapId, preimage);
                break;
            case AssetType.ERC721:
                tx = await this.nft.completeNFTSwap(swapId, preimage);
                break;
            case AssetType.NFT_TO_NFT:
                tx = await this.nft.completeNFTtoNFTSwap(swapId, preimage);
                break;
        }
        
        const receipt = await tx.wait();
        this.analytics.totalSwaps++;
        
        return { tx, receipt };
    }

    /**
     * Refund any swap
     */
    async refundSwap(swapId) {
        const swapInfo = this.swapRegistry.get(swapId);
        const assetType = swapInfo?.assetType || await this._detectSwapType(swapId);
        
        let tx;
        if (assetType === AssetType.ETH || assetType === AssetType.ERC20) {
            tx = await this.core.refundSwap(swapId);
        } else {
            tx = await this.nft.refundNFTSwap(swapId);
        }
        
        return { tx, receipt: await tx.wait() };
    }

    /**
     * Approve any swap
     */
    async approveSwap(swapId) {
        const swapInfo = this.swapRegistry.get(swapId);
        const assetType = swapInfo?.assetType || await this._detectSwapType(swapId);
        
        let tx;
        if (assetType === AssetType.ETH || assetType === AssetType.ERC20) {
            tx = await this.core.approveSwap(swapId);
        } else {
            tx = await this.nft.approveSwap(swapId);
        }
        
        return { tx, receipt: await tx.wait() };
    }

    /**
     * Raise dispute for any swap
     */
    async raiseDispute(swapId, evidence, arbitrationFee) {
        const swapInfo = this.swapRegistry.get(swapId);
        const assetType = swapInfo?.assetType || await this._detectSwapType(swapId);
        
        let tx;
        if (assetType === AssetType.ETH || assetType === AssetType.ERC20) {
            tx = await this.core.raiseDispute(swapId, evidence, { value: arbitrationFee });
        } else {
            tx = await this.nft.raiseDispute(swapId, evidence, { value: arbitrationFee });
        }
        
        return { tx, receipt: await tx.wait() };
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Get swap details from either contract
     */
    async getSwap(swapId) {
        // Try Core first
        try {
            const swap = await this.core.getSwap(swapId);
            if (swap.buyer !== ethers.ZeroAddress) {
                return {
                    ...swap,
                    contract: 'AMTTPCore',
                    assetType: swap.assetType === 0 ? 'ETH' : 'ERC20',
                    statusName: SwapStatus[swap.status]
                };
            }
        } catch (e) {}
        
        // Try NFT
        try {
            const swap = await this.nft.getNFTSwap(swapId);
            if (swap.seller !== ethers.ZeroAddress) {
                return {
                    ...swap,
                    contract: 'AMTTPNFT',
                    assetType: swap.swapType === 0 ? 'NFT_TO_ETH' : 'NFT_TO_NFT',
                    statusName: SwapStatus[swap.status]
                };
            }
        } catch (e) {}
        
        throw new Error('Swap not found');
    }

    /**
     * Get protocol statistics (off-chain, free!)
     */
    getStats() {
        return {
            ...this.analytics,
            registeredSwaps: this.swapRegistry.size
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    INTERNAL HELPERS
    // ═══════════════════════════════════════════════════════════════════

    _extractSwapId(receipt) {
        // Extract from SwapInitiated or NFTSwapInitiated event
        for (const log of receipt.logs) {
            if (log.topics[0] && log.topics[1]) {
                return log.topics[1]; // swapId is typically first indexed param
            }
        }
        return null;
    }

    _recordSwap(swapId, assetType, amount) {
        this.swapRegistry.set(swapId, {
            assetType,
            amount,
            timestamp: Date.now()
        });
        
        // Update analytics
        if (assetType === AssetType.ETH) {
            this.analytics.ethVolume += BigInt(amount);
        } else if (assetType === AssetType.ERC20) {
            this.analytics.erc20Volume += BigInt(amount);
        } else {
            this.analytics.nftSwaps++;
        }
    }

    async _detectSwapType(swapId) {
        try {
            const swap = await this.core.getSwap(swapId);
            if (swap.buyer !== ethers.ZeroAddress) {
                return swap.assetType === 0 ? AssetType.ETH : AssetType.ERC20;
            }
        } catch (e) {}
        
        try {
            const swap = await this.nft.getNFTSwap(swapId);
            if (swap.seller !== ethers.ZeroAddress) {
                return swap.swapType === 0 ? AssetType.ERC721 : AssetType.NFT_TO_NFT;
            }
        } catch (e) {}
        
        throw new Error('Cannot detect swap type');
    }

    // ═══════════════════════════════════════════════════════════════════
    //                    GAS ESTIMATION
    // ═══════════════════════════════════════════════════════════════════

    /**
     * Estimate gas for any operation
     */
    async estimateGas(operation, params) {
        const contract = this.getContractForAsset(this.detectAssetType(params));
        
        switch (operation) {
            case 'initiateSwap':
                if (params.token) {
                    return await this.core.initiateSwapERC20.estimateGas(...Object.values(params));
                }
                return await this.core.initiateSwap.estimateGas(...Object.values(params));
            case 'complete':
                return await contract.completeSwap.estimateGas(params.swapId, params.preimage);
            case 'refund':
                return await contract.refundSwap.estimateGas(params.swapId);
            default:
                throw new Error(`Unknown operation: ${operation}`);
        }
    }
}

// Export singleton factory
export function createRouter(providerOrSigner, network = 'sepolia') {
    return new AMTTPRouter(providerOrSigner, network);
}

export default AMTTPRouter;
