import { AMTTPConfig, TransactionRequest, AMTTPResult, RiskScore, KYCStatus, SwapParams, PolicySettings } from './types.js';
export declare class AMTTPClient {
    private provider;
    private signer?;
    private contract;
    private oracleUrl;
    constructor(config: AMTTPConfig);
    /**
     * Submit a transaction with AMTTP protection
     */
    submitTransaction(txRequest: TransactionRequest): Promise<AMTTPResult>;
    /**
     * Score transaction risk using your trained DQN model
     */
    scoreTransactionRisk(params: {
        from: string;
        to: string;
        amount: number;
        metadata?: any;
    }): Promise<RiskScore>;
    /**
     * Get KYC status for an address
     */
    getKYCStatus(address: string): Promise<KYCStatus>;
    /**
     * Submit transaction through AMTTP escrow (for high-risk transactions)
     */
    private submitWithEscrow;
    /**
     * Submit transaction directly (for low-risk transactions)
     */
    private submitDirect;
    /**
     * Create atomic swap for secure transactions
     */
    createAtomicSwap(params: SwapParams): Promise<AMTTPResult>;
    /**
     * Get user's policy settings
     */
    getUserPolicy(address: string): Promise<PolicySettings>;
    /**
     * Update user's policy settings
     */
    updateUserPolicy(policy: Partial<PolicySettings>): Promise<boolean>;
    private shouldRequireApproval;
    private riskCategoryToLevel;
    private getOracleSignature;
    private logTransaction;
}
//# sourceMappingURL=client.d.ts.map