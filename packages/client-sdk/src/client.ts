// src/client.ts
import { ethers } from 'ethers';
import axios from 'axios';
import { 
  AMTTPConfig, 
  TransactionRequest, 
  AMTTPResult, 
  RiskScore, 
  KYCStatus,
  SwapParams,
  PolicySettings 
} from './types.js';
import { AMTTP_ABI } from './abi.js';

export class AMTTPClient {
  private provider: ethers.Provider;
  private signer?: ethers.Signer;
  private contract: ethers.Contract;
  private oracleUrl: string;

  constructor(config: AMTTPConfig) {
    // Setup provider
    if (config.provider) {
      this.provider = config.provider;
    } else {
      this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
    }

    // Setup signer
    if (config.signer) {
      this.signer = config.signer;
    } else if (config.privateKey) {
      this.signer = new ethers.Wallet(config.privateKey, this.provider);
    }

    // Setup contract
    this.contract = new ethers.Contract(
      config.contractAddress,
      AMTTP_ABI,
      this.signer || this.provider
    );

    this.oracleUrl = config.oracleUrl;
  }

  /**
   * Submit a transaction with AMTTP protection
   */
  async submitTransaction(txRequest: TransactionRequest): Promise<AMTTPResult> {
    try {
      if (!this.signer) {
        throw new Error('Signer required for transaction submission');
      }

      // Step 1: Score the transaction risk
      const riskScore = await this.scoreTransactionRisk({
        from: await this.signer.getAddress(),
        to: txRequest.to,
        amount: Number(ethers.formatEther(txRequest.value)),
        metadata: txRequest.metadata
      });

      // Step 2: Check if user has valid KYC
      const kycStatus = await this.getKYCStatus(await this.signer.getAddress());
      if (kycStatus.status !== 'approved') {
        return {
          success: false,
          error: 'KYC approval required',
          riskScore
        };
      }

      // Step 3: Determine if approval is required based on risk
      const requiresApproval = this.shouldRequireApproval(riskScore);

      if (requiresApproval) {
        // High risk - use AMTTP escrow system
        return await this.submitWithEscrow(txRequest, riskScore, kycStatus);
      } else {
        // Low risk - direct transaction with monitoring
        return await this.submitDirect(txRequest, riskScore);
      }

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Score transaction risk using your trained DQN model
   */
  async scoreTransactionRisk(params: {
    from: string;
    to: string;
    amount: number;
    metadata?: any;
  }): Promise<RiskScore> {
    try {
      const response = await axios.post(`${this.oracleUrl}/risk/dqn-score`, {
        from: params.from,
        to: params.to,
        amount: params.amount,
        timestamp: Math.floor(Date.now() / 1000),
        ...params.metadata
      });

      return response.data as RiskScore;
    } catch (error) {
      // Fallback to basic risk assessment
      return {
        riskScore: 0.5,
        riskCategory: 'MEDIUM',
        confidence: 0.6,
        recommendations: ['Manual review recommended'],
        modelVersion: 'fallback-v1.0'
      };
    }
  }

  /**
   * Get KYC status for an address
   */
  async getKYCStatus(address: string): Promise<KYCStatus> {
    try {
      // This would typically be implemented with a mapping from address to userId
      // For now, we'll use a simplified approach
      const response = await axios.get(`${this.oracleUrl}/kyc/status-by-address/${address}`);
      return response.data as KYCStatus;
    } catch (error) {
      return {
        status: 'pending',
        kycHash: '0x0000000000000000000000000000000000000000000000000000000000000000'
      };
    }
  }

  /**
   * Submit transaction through AMTTP escrow (for high-risk transactions)
   */
  private async submitWithEscrow(
    txRequest: TransactionRequest, 
    riskScore: RiskScore, 
    kycStatus: KYCStatus
  ): Promise<AMTTPResult> {
    try {
      // Generate swap parameters
      const preimage = ethers.randomBytes(32);
      const hashlock = ethers.keccak256(preimage);
      const timelock = Math.floor(Date.now() / 1000) + 3600; // 1 hour

      // Get oracle signature for the swap
      const digest = ethers.keccak256(
        ethers.AbiCoder.defaultAbiCoder().encode(
          ['address', 'address', 'uint256', 'uint8', 'bytes32'],
          [
            await this.signer!.getAddress(),
            txRequest.to,
            txRequest.value,
            this.riskCategoryToLevel(riskScore.riskCategory),
            kycStatus.kycHash
          ]
        )
      );

      // Request oracle signature
      const oracleSignature = await this.getOracleSignature(digest);

      // Initiate AMTTP swap
      const tx = await this.contract.initiateSwap(
        txRequest.to,
        hashlock,
        timelock,
        this.riskCategoryToLevel(riskScore.riskCategory),
        kycStatus.kycHash,
        oracleSignature,
        { value: txRequest.value }
      );

      const receipt = await tx.wait();

      return {
        success: true,
        transactionHash: receipt.hash,
        riskScore,
        approvalRequired: true,
        estimatedConfirmation: timelock
      };

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Escrow submission failed',
        riskScore
      };
    }
  }

  /**
   * Submit transaction directly (for low-risk transactions)
   */
  private async submitDirect(
    txRequest: TransactionRequest, 
    riskScore: RiskScore
  ): Promise<AMTTPResult> {
    try {
      const tx = await this.signer!.sendTransaction({
        to: txRequest.to,
        value: txRequest.value,
        data: txRequest.data
      });

      const receipt = await tx.wait();

      // Log the transaction for monitoring
      await this.logTransaction(tx.hash, riskScore);

      return {
        success: true,
        transactionHash: receipt!.hash,
        riskScore,
        approvalRequired: false
      };

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Direct submission failed',
        riskScore
      };
    }
  }

  /**
   * Create atomic swap for secure transactions
   */
  async createAtomicSwap(params: SwapParams): Promise<AMTTPResult> {
    try {
      if (!this.signer) {
        throw new Error('Signer required for swap creation');
      }

      const kycStatus = await this.getKYCStatus(await this.signer.getAddress());
      const riskScore = await this.scoreTransactionRisk({
        from: await this.signer.getAddress(),
        to: params.seller,
        amount: Number(ethers.formatEther(params.amount))
      });

      const oracleSignature = await this.getOracleSignature(
        ethers.keccak256(
          ethers.AbiCoder.defaultAbiCoder().encode(
            ['address', 'address', 'uint256', 'uint8', 'bytes32'],
            [
              await this.signer.getAddress(),
              params.seller,
              params.amount,
              this.riskCategoryToLevel(riskScore.riskCategory),
              kycStatus.kycHash
            ]
          )
        )
      );

      const tx = await this.contract.initiateSwap(
        params.seller,
        params.hashlock,
        params.timelock,
        this.riskCategoryToLevel(riskScore.riskCategory),
        kycStatus.kycHash,
        oracleSignature,
        { value: params.amount }
      );

      const receipt = await tx.wait();

      return {
        success: true,
        transactionHash: receipt.hash,
        riskScore,
        swapId: ethers.solidityPackedKeccak256(
          ['address', 'address', 'bytes32', 'uint256'],
          [await this.signer.getAddress(), params.seller, params.hashlock, params.timelock]
        )
      };

    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Swap creation failed'
      };
    }
  }

  /**
   * Get user's policy settings
   */
  async getUserPolicy(address: string): Promise<PolicySettings> {
    // This would integrate with your policy engine contract
    return {
      maxAmount: ethers.parseEther('10'),
      dailyLimit: ethers.parseEther('100'),
      allowedCounterparties: [],
      riskThreshold: 0.7,
      autoApprove: false
    };
  }

  /**
   * Update user's policy settings
   */
  async updateUserPolicy(policy: Partial<PolicySettings>): Promise<boolean> {
    try {
      if (!this.signer) {
        throw new Error('Signer required for policy updates');
      }

      // This would call your policy engine contract
      // For now, we'll just return true
      return true;

    } catch (error) {
      console.error('Policy update failed:', error);
      return false;
    }
  }

  // Private helper methods
  private shouldRequireApproval(riskScore: RiskScore): boolean {
    return riskScore.riskCategory === 'HIGH' || riskScore.riskScore >= 0.7;
  }

  private riskCategoryToLevel(category: string): number {
    switch (category) {
      case 'MINIMAL': return 0;
      case 'LOW': return 1;
      case 'MEDIUM': return 2;
      case 'HIGH': return 3;
      default: return 2;
    }
  }

  private async getOracleSignature(digest: string): Promise<string> {
    try {
      const response = await axios.post(`${this.oracleUrl}/oracle/sign`, {
        digest
      });
      return response.data.signature;
    } catch (error) {
      // For testing, return a dummy signature
      return '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000';
    }
  }

  private async logTransaction(txHash: string, riskScore: RiskScore): Promise<void> {
    try {
      await axios.post(`${this.oracleUrl}/risk/log`, {
        transactionHash: txHash,
        riskScore: riskScore.riskScore,
        riskCategory: riskScore.riskCategory,
        modelVersion: riskScore.modelVersion
      });
    } catch (error) {
      // Silent fail for logging
      console.warn('Failed to log transaction:', error);
    }
  }
}