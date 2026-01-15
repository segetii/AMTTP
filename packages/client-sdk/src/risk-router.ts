/**
 * AMTTP Risk Router SDK
 * 
 * Client SDK for interacting with the L2 AI Risk Router
 * Supports Polygon and Arbitrum networks with automatic chain detection
 */

import { ethers, Contract, Wallet, Provider, Signer } from 'ethers';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export enum RiskAction {
    APPROVE = 0,
    REVIEW = 1,
    ESCROW = 2,
    BLOCK = 3
}

export interface RiskResult {
    riskScore: bigint;
    timestamp: bigint;
    action: RiskAction;
    processed: boolean;
}

export interface BatchRequest {
    sender: string;
    recipient: string;
    amount: bigint;
    riskScore: number;
    txHash: string;
}

export interface RouterStatistics {
    totalAssessments: bigint;
    totalApproved: bigint;
    totalReviewed: bigint;
    totalEscrowed: bigint;
    totalBlocked: bigint;
    circuitBreakerActive: boolean;
}

export interface RiskThresholds {
    low: number;
    medium: number;
    high: number;
}

export interface RiskRouterConfig {
    providerUrl?: string;
    privateKey?: string;
    contractAddress?: string;
    chainId?: number;
}

// Network configurations
export const L2_ROUTER_ADDRESSES: Record<number, string> = {
    137: '',      // Polygon Mainnet - to be filled after deployment
    80001: '',    // Polygon Mumbai - to be filled after deployment
    42161: '',    // Arbitrum One - to be filled after deployment
    421614: '',   // Arbitrum Sepolia - to be filled after deployment
};

// Chain ID to name mapping
export const CHAIN_NAMES: Record<number, string> = {
    137: 'Polygon',
    80001: 'Polygon Mumbai',
    42161: 'Arbitrum One',
    421614: 'Arbitrum Sepolia',
    31337: 'Localhost'
};

// Minimal ABI for the Risk Router
const RISK_ROUTER_ABI = [
    // Core functions
    'function assessRisk(address sender, address recipient, uint256 amount, uint128 riskScore, uint64 timestamp, bytes signature) external returns (uint8 action, bytes32 txHash)',
    'function batchAssessRisk((address sender, address recipient, uint256 amount, uint128 riskScore, bytes32 txHash)[] requests, bytes[] signatures) external returns (uint8[] actions, bytes32[] txHashes)',
    'function quickCheck(uint128 riskScore) external view returns (uint8 action)',
    'function getRiskResult(bytes32 txHash) external view returns (tuple(uint128 riskScore, uint64 timestamp, uint8 action, bool processed))',
    'function markProcessed(bytes32 txHash) external',
    
    // View functions
    'function getStatistics() external view returns (uint256, uint256, uint256, uint256, uint256, bool)',
    'function getThresholds() external view returns (uint256, uint256, uint256)',
    'function modelVersion() external view returns (string)',
    'function circuitBreakerActive() external view returns (bool)',
    
    // Events
    'event RiskAssessed(bytes32 indexed txHash, address indexed sender, address indexed recipient, uint256 amount, uint256 riskScore, uint8 action)',
    'event BatchProcessed(uint256 batchId, uint256 count, uint256 approved, uint256 reviewed, uint256 escrowed, uint256 blocked)'
];

// ═══════════════════════════════════════════════════════════════════════════
// RISK ROUTER CLIENT
// ═══════════════════════════════════════════════════════════════════════════

export class RiskRouterClient {
    private provider: Provider;
    private signer: Signer | null = null;
    private contract: Contract;
    private chainId: number;
    
    constructor(config: RiskRouterConfig = {}) {
        // Setup provider
        if (config.providerUrl) {
            this.provider = new ethers.JsonRpcProvider(config.providerUrl);
        } else {
            throw new Error('Provider URL required');
        }
        
        this.chainId = config.chainId || 0;
        
        // Setup signer if private key provided
        if (config.privateKey) {
            this.signer = new Wallet(config.privateKey, this.provider);
        }
        
        // Get contract address
        const contractAddress = config.contractAddress || 
            L2_ROUTER_ADDRESSES[this.chainId];
        
        if (!contractAddress) {
            throw new Error(`No contract address for chain ${this.chainId}`);
        }
        
        // Create contract instance
        this.contract = new Contract(
            contractAddress,
            RISK_ROUTER_ABI,
            this.signer || this.provider
        );
    }
    
    /**
     * Create client with automatic chain detection
     */
    static async create(config: RiskRouterConfig): Promise<RiskRouterClient> {
        const provider = new ethers.JsonRpcProvider(config.providerUrl);
        const network = await provider.getNetwork();
        config.chainId = Number(network.chainId);
        return new RiskRouterClient(config);
    }
    
    /**
     * Quick risk check (view function - no gas)
     */
    async quickCheck(riskScore: number): Promise<RiskAction> {
        const action = await this.contract.quickCheck(riskScore);
        return action as RiskAction;
    }
    
    /**
     * Get risk action name
     */
    getActionName(action: RiskAction): string {
        const names = ['APPROVE', 'REVIEW', 'ESCROW', 'BLOCK'];
        return names[action] || 'UNKNOWN';
    }
    
    /**
     * Assess risk for a transaction
     */
    async assessRisk(
        sender: string,
        recipient: string,
        amount: bigint,
        riskScore: number,
        oracleSignature: string
    ): Promise<{ action: RiskAction; txHash: string }> {
        if (!this.signer) {
            throw new Error('Signer required for assessRisk');
        }
        
        const timestamp = Math.floor(Date.now() / 1000);
        
        const tx = await this.contract.assessRisk(
            sender,
            recipient,
            amount,
            riskScore,
            timestamp,
            oracleSignature
        );
        
        const receipt = await tx.wait();
        
        // Parse event to get action and txHash
        const event = receipt.logs.find((log: any) => {
            try {
                const parsed = this.contract.interface.parseLog(log);
                return parsed?.name === 'RiskAssessed';
            } catch {
                return false;
            }
        });
        
        if (event) {
            const parsed = this.contract.interface.parseLog(event);
            return {
                action: Number(parsed?.args.action) as RiskAction,
                txHash: parsed?.args.txHash
            };
        }
        
        throw new Error('RiskAssessed event not found');
    }
    
    /**
     * Batch assess multiple transactions
     */
    async batchAssessRisk(
        requests: BatchRequest[],
        signatures: string[]
    ): Promise<{ actions: RiskAction[]; txHashes: string[] }> {
        if (!this.signer) {
            throw new Error('Signer required for batchAssessRisk');
        }
        
        const tx = await this.contract.batchAssessRisk(requests, signatures);
        const receipt = await tx.wait();
        
        // Parse BatchProcessed event
        const event = receipt.logs.find((log: any) => {
            try {
                const parsed = this.contract.interface.parseLog(log);
                return parsed?.name === 'BatchProcessed';
            } catch {
                return false;
            }
        });
        
        // Collect all RiskAssessed events
        const riskEvents = receipt.logs.filter((log: any) => {
            try {
                const parsed = this.contract.interface.parseLog(log);
                return parsed?.name === 'RiskAssessed';
            } catch {
                return false;
            }
        });
        
        const actions: RiskAction[] = [];
        const txHashes: string[] = [];
        
        for (const log of riskEvents) {
            const parsed = this.contract.interface.parseLog(log);
            if (parsed) {
                actions.push(Number(parsed.args.action) as RiskAction);
                txHashes.push(parsed.args.txHash);
            }
        }
        
        return { actions, txHashes };
    }
    
    /**
     * Get risk result for a transaction
     */
    async getRiskResult(txHash: string): Promise<RiskResult> {
        const result = await this.contract.getRiskResult(txHash);
        return {
            riskScore: result.riskScore,
            timestamp: result.timestamp,
            action: Number(result.action) as RiskAction,
            processed: result.processed
        };
    }
    
    /**
     * Get router statistics
     */
    async getStatistics(): Promise<RouterStatistics> {
        const [total, approved, reviewed, escrowed, blocked, circuitBreaker] = 
            await this.contract.getStatistics();
        
        return {
            totalAssessments: total,
            totalApproved: approved,
            totalReviewed: reviewed,
            totalEscrowed: escrowed,
            totalBlocked: blocked,
            circuitBreakerActive: circuitBreaker
        };
    }
    
    /**
     * Get current risk thresholds
     */
    async getThresholds(): Promise<RiskThresholds> {
        const [low, medium, high] = await this.contract.getThresholds();
        return {
            low: Number(low),
            medium: Number(medium),
            high: Number(high)
        };
    }
    
    /**
     * Get current model version
     */
    async getModelVersion(): Promise<string> {
        return await this.contract.modelVersion();
    }
    
    /**
     * Check if circuit breaker is active
     */
    async isCircuitBreakerActive(): Promise<boolean> {
        return await this.contract.circuitBreakerActive();
    }
    
    /**
     * Sign a risk assessment for oracle submission
     */
    async signRiskAssessment(
        sender: string,
        recipient: string,
        amount: bigint,
        riskScore: number,
        timestamp: number
    ): Promise<string> {
        if (!this.signer) {
            throw new Error('Signer required for signing');
        }
        
        const messageHash = ethers.solidityPackedKeccak256(
            ['address', 'address', 'uint256', 'uint128', 'uint64', 'uint256'],
            [sender, recipient, amount, riskScore, timestamp, this.chainId]
        );
        
        return await this.signer.signMessage(ethers.getBytes(messageHash));
    }
    
    /**
     * Get chain name
     */
    getChainName(): string {
        return CHAIN_NAMES[this.chainId] || `Chain ${this.chainId}`;
    }
    
    /**
     * Get contract address
     */
    getContractAddress(): string {
        return this.contract.target as string;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get action color for UI display
 */
export function getActionColor(action: RiskAction): string {
    switch (action) {
        case RiskAction.APPROVE:
            return '#22c55e'; // green
        case RiskAction.REVIEW:
            return '#f59e0b'; // amber
        case RiskAction.ESCROW:
            return '#f97316'; // orange
        case RiskAction.BLOCK:
            return '#ef4444'; // red
        default:
            return '#6b7280'; // gray
    }
}

/**
 * Get action icon for UI display
 */
export function getActionIcon(action: RiskAction): string {
    switch (action) {
        case RiskAction.APPROVE:
            return '✅';
        case RiskAction.REVIEW:
            return '👁️';
        case RiskAction.ESCROW:
            return '🔒';
        case RiskAction.BLOCK:
            return '🚫';
        default:
            return '❓';
    }
}

/**
 * Calculate expected action from score
 */
export function predictAction(
    score: number,
    thresholds: RiskThresholds = { low: 300, medium: 600, high: 850 }
): RiskAction {
    if (score <= thresholds.low) return RiskAction.APPROVE;
    if (score <= thresholds.medium) return RiskAction.REVIEW;
    if (score <= thresholds.high) return RiskAction.ESCROW;
    return RiskAction.BLOCK;
}

/**
 * Format statistics for display
 */
export function formatStatistics(stats: RouterStatistics): string {
    const total = Number(stats.totalAssessments);
    if (total === 0) return 'No assessments yet';
    
    const approveRate = (Number(stats.totalApproved) / total * 100).toFixed(1);
    const reviewRate = (Number(stats.totalReviewed) / total * 100).toFixed(1);
    const escrowRate = (Number(stats.totalEscrowed) / total * 100).toFixed(1);
    const blockRate = (Number(stats.totalBlocked) / total * 100).toFixed(1);
    
    return `
Total: ${total}
├─ Approved: ${stats.totalApproved} (${approveRate}%)
├─ Reviewed: ${stats.totalReviewed} (${reviewRate}%)
├─ Escrowed: ${stats.totalEscrowed} (${escrowRate}%)
└─ Blocked:  ${stats.totalBlocked} (${blockRate}%)
Circuit Breaker: ${stats.circuitBreakerActive ? '🔴 ACTIVE' : '🟢 Normal'}
    `.trim();
}

// Export factory function
export function createRiskRouterClient(config: RiskRouterConfig): RiskRouterClient {
    return new RiskRouterClient(config);
}

export default RiskRouterClient;
