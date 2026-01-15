/**
 * AMTTP zkNAF SDK - Zero-Knowledge Non-Disclosing Anti-Fraud
 * 
 * Privacy-preserving compliance verification for Web3 applications.
 * Enables users to prove compliance status without revealing sensitive data.
 * 
 * FCA COMPLIANCE NOTE:
 * This SDK generates proofs for PUBLIC verification only.
 * The regulated entity (AMTTP) maintains full records for regulatory disclosure.
 * 
 * @packageDocumentation
 */

import { ethers } from 'ethers';
import * as snarkjs from 'snarkjs';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export enum ProofType {
  SANCTIONS_NON_MEMBERSHIP = 0,
  RISK_RANGE_LOW = 1,
  RISK_RANGE_MEDIUM = 2,
  KYC_VERIFIED = 3,
  TRANSACTION_COMPLIANT = 4,
}

export interface Groth16Proof {
  a: [string, string];
  b: [[string, string], [string, string]];
  c: [string, string];
}

export interface ProofResult {
  proof: Groth16Proof;
  publicSignals: string[];
  proofType: ProofType;
  prover: string;
  timestamp: number;
  expiresAt: number;
}

export interface SanctionsProofInput {
  addressToCheck: string;
  sanctionsListRoot: string;
  leftNeighbor: string;
  rightNeighbor: string;
  leftProof: string[];
  rightProof: string[];
  leftPathIndices: number[];
  rightPathIndices: number[];
}

export interface RiskRangeProofInput {
  riskScore: number;
  userAddress: string;
  scoreTimestamp: number;
  oracleSecret: string;
  signatureCommitment: string;
  minScore: number;
  maxScore: number;
}

export interface KYCProofInput {
  userAddress: string;
  birthTimestamp: number;
  kycCompletedAt: number;
  kycExpiresAt: number;
  isPEP: boolean;
  providerSignature: string;
  providerSecret: string;
  kycDataHash: string;
  providerCommitment: string;
}

export interface ZkNAFConfig {
  providerUrl?: string;
  contractAddress?: string;
  circuitsPath?: string;
  trustedSetupPath?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// ZKNAF SERVICE
// ═══════════════════════════════════════════════════════════════════════════

/**
 * zkNAF Service - Generate and verify zero-knowledge compliance proofs
 */
export class ZkNAFService {
  private provider: ethers.Provider | null = null;
  private contract: ethers.Contract | null = null;
  private config: ZkNAFConfig;
  
  // Default paths for circuits and trusted setup
  private readonly defaultCircuitsPath = './circuits';
  private readonly defaultSetupPath = './trusted-setup';
  
  // Circuit files
  private readonly circuits = {
    sanctions: {
      wasm: 'sanctions_non_membership.wasm',
      zkey: 'sanctions_non_membership.zkey',
      vkey: 'sanctions_non_membership_verification_key.json',
    },
    riskRange: {
      wasm: 'risk_range_proof.wasm',
      zkey: 'risk_range_proof.zkey',
      vkey: 'risk_range_proof_verification_key.json',
    },
    kyc: {
      wasm: 'kyc_credential.wasm',
      zkey: 'kyc_credential.zkey',
      vkey: 'kyc_credential_verification_key.json',
    },
  };

  constructor(config: ZkNAFConfig = {}) {
    this.config = {
      circuitsPath: config.circuitsPath || this.defaultCircuitsPath,
      trustedSetupPath: config.trustedSetupPath || this.defaultSetupPath,
      ...config,
    };
  }

  /**
   * Connect to blockchain provider and zkNAF contract
   */
  async connect(providerUrl: string, contractAddress: string): Promise<void> {
    this.provider = new ethers.JsonRpcProvider(providerUrl);
    this.contract = new ethers.Contract(
      contractAddress,
      ZKNAF_ABI,
      this.provider
    );
    this.config.providerUrl = providerUrl;
    this.config.contractAddress = contractAddress;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // SANCTIONS PROOF
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Generate a proof that an address is NOT on the sanctions list
   * 
   * @param input - Sanctions proof input with Merkle proofs
   * @returns Groth16 proof and public signals
   */
  async generateSanctionsProof(input: SanctionsProofInput): Promise<ProofResult> {
    const circuitPath = `${this.config.circuitsPath}/${this.circuits.sanctions.wasm}`;
    const zkeyPath = `${this.config.trustedSetupPath}/${this.circuits.sanctions.zkey}`;

    const circuitInputs = {
      sanctionsListRoot: input.sanctionsListRoot,
      currentTimestamp: Math.floor(Date.now() / 1000),
      addressToCheck: this.addressToField(input.addressToCheck),
      leftNeighbor: input.leftNeighbor,
      rightNeighbor: input.rightNeighbor,
      leftProof: input.leftProof,
      rightProof: input.rightProof,
      leftPathIndices: input.leftPathIndices,
      rightPathIndices: input.rightPathIndices,
    };

    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
      circuitInputs,
      circuitPath,
      zkeyPath
    );

    return {
      proof: this.formatProof(proof),
      publicSignals,
      proofType: ProofType.SANCTIONS_NON_MEMBERSHIP,
      prover: input.addressToCheck,
      timestamp: circuitInputs.currentTimestamp,
      expiresAt: circuitInputs.currentTimestamp + 86400, // 24 hours
    };
  }

  /**
   * Verify a sanctions non-membership proof locally
   */
  async verifySanctionsProof(
    proof: Groth16Proof,
    publicSignals: string[]
  ): Promise<boolean> {
    const vkeyPath = `${this.config.trustedSetupPath}/${this.circuits.sanctions.vkey}`;
    const vkey = await this.loadVerificationKey(vkeyPath);
    
    return await snarkjs.groth16.verify(vkey, publicSignals, proof);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RISK RANGE PROOF
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Generate a proof that risk score is in a specific range
   * 
   * @param input - Risk range proof input
   * @param range - 'low' (0-39), 'medium' (40-69), or custom [min, max]
   */
  async generateRiskRangeProof(
    input: RiskRangeProofInput,
    range: 'low' | 'medium' | [number, number] = 'low'
  ): Promise<ProofResult> {
    const circuitPath = `${this.config.circuitsPath}/${this.circuits.riskRange.wasm}`;
    const zkeyPath = `${this.config.trustedSetupPath}/${this.circuits.riskRange.zkey}`;

    // Determine range bounds
    let minScore: number, maxScore: number;
    if (range === 'low') {
      minScore = 0;
      maxScore = 39;
    } else if (range === 'medium') {
      minScore = 40;
      maxScore = 69;
    } else {
      [minScore, maxScore] = range;
    }

    const userAddressHash = this.poseidonHash([this.addressToField(input.userAddress)]);
    const currentTimestamp = Math.floor(Date.now() / 1000);

    const circuitInputs = {
      signatureCommitment: input.signatureCommitment,
      userAddressHash,
      minScore,
      maxScore,
      currentTimestamp,
      riskScore: input.riskScore,
      userAddress: this.addressToField(input.userAddress),
      scoreTimestamp: input.scoreTimestamp,
      oracleSecret: input.oracleSecret,
    };

    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
      circuitInputs,
      circuitPath,
      zkeyPath
    );

    const proofType = range === 'low' 
      ? ProofType.RISK_RANGE_LOW 
      : ProofType.RISK_RANGE_MEDIUM;

    return {
      proof: this.formatProof(proof),
      publicSignals,
      proofType,
      prover: input.userAddress,
      timestamp: currentTimestamp,
      expiresAt: currentTimestamp + 86400,
    };
  }

  /**
   * Verify a risk range proof locally
   */
  async verifyRiskRangeProof(
    proof: Groth16Proof,
    publicSignals: string[]
  ): Promise<boolean> {
    const vkeyPath = `${this.config.trustedSetupPath}/${this.circuits.riskRange.vkey}`;
    const vkey = await this.loadVerificationKey(vkeyPath);
    
    return await snarkjs.groth16.verify(vkey, publicSignals, proof);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // KYC PROOF
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Generate a proof that user has valid KYC without revealing identity
   * 
   * @param input - KYC proof input
   */
  async generateKYCProof(input: KYCProofInput): Promise<ProofResult> {
    const circuitPath = `${this.config.circuitsPath}/${this.circuits.kyc.wasm}`;
    const zkeyPath = `${this.config.trustedSetupPath}/${this.circuits.kyc.zkey}`;

    const userAddressHash = this.poseidonHash([this.addressToField(input.userAddress)]);
    const currentTimestamp = Math.floor(Date.now() / 1000);
    const minAgeSeconds = 18 * 365 * 24 * 60 * 60; // 18 years in seconds

    const circuitInputs = {
      providerCommitment: input.providerCommitment,
      userAddressHash,
      currentTimestamp,
      minAgeSeconds,
      userAddress: this.addressToField(input.userAddress),
      birthTimestamp: input.birthTimestamp,
      kycCompletedAt: input.kycCompletedAt,
      kycExpiresAt: input.kycExpiresAt,
      isPEP: input.isPEP ? 1 : 0,
      providerSignature: input.providerSignature,
      providerSecret: input.providerSecret,
      kycDataHash: input.kycDataHash,
    };

    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
      circuitInputs,
      circuitPath,
      zkeyPath
    );

    return {
      proof: this.formatProof(proof),
      publicSignals,
      proofType: ProofType.KYC_VERIFIED,
      prover: input.userAddress,
      timestamp: currentTimestamp,
      expiresAt: currentTimestamp + 86400,
    };
  }

  /**
   * Verify a KYC proof locally
   */
  async verifyKYCProof(
    proof: Groth16Proof,
    publicSignals: string[]
  ): Promise<boolean> {
    const vkeyPath = `${this.config.trustedSetupPath}/${this.circuits.kyc.vkey}`;
    const vkey = await this.loadVerificationKey(vkeyPath);
    
    return await snarkjs.groth16.verify(vkey, publicSignals, proof);
  }

  // ─────────────────────────────────────────────────────────────────────────
  // ON-CHAIN VERIFICATION
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Submit proof to on-chain contract for verification and storage
   */
  async submitProofOnChain(
    signer: ethers.Signer,
    proofResult: ProofResult
  ): Promise<string> {
    if (!this.contract) {
      throw new Error('Not connected to contract. Call connect() first.');
    }

    const contractWithSigner = this.contract.connect(signer);
    
    const proofData = {
      a: proofResult.proof.a,
      b: proofResult.proof.b,
      c: proofResult.proof.c,
    };

    const tx = await contractWithSigner.verifyAndStore(
      proofResult.proofType,
      proofData,
      proofResult.publicSignals.map(s => BigInt(s))
    );

    const receipt = await tx.wait();
    
    // Extract proof hash from event
    const event = receipt.logs.find(
      (log: any) => log.fragment?.name === 'ProofVerified'
    );
    
    return event?.args?.proofHash || tx.hash;
  }

  /**
   * Check if an address has a valid proof on-chain
   */
  async hasValidProof(address: string, proofType: ProofType): Promise<boolean> {
    if (!this.contract) {
      throw new Error('Not connected to contract. Call connect() first.');
    }

    return await this.contract.hasValidProof(address, proofType);
  }

  /**
   * Get full compliance status for an address
   */
  async getComplianceStatus(address: string): Promise<{
    sanctionsProof: boolean;
    riskProof: boolean;
    kycProof: boolean;
    fullyCompliant: boolean;
  }> {
    if (!this.contract) {
      throw new Error('Not connected to contract. Call connect() first.');
    }

    const result = await this.contract.isCompliant(address);
    return {
      sanctionsProof: result[0],
      riskProof: result[1],
      kycProof: result[2],
      fullyCompliant: result[3],
    };
  }

  // ─────────────────────────────────────────────────────────────────────────
  // UTILITY FUNCTIONS
  // ─────────────────────────────────────────────────────────────────────────

  /**
   * Convert Ethereum address to field element
   */
  private addressToField(address: string): string {
    return BigInt(address).toString();
  }

  /**
   * Poseidon hash (simplified - in production use circomlibjs)
   */
  private poseidonHash(inputs: string[]): string {
    // In production, use circomlibjs Poseidon implementation
    // This is a placeholder that uses keccak256
    const packed = ethers.solidityPacked(
      inputs.map(() => 'uint256'),
      inputs.map(i => BigInt(i))
    );
    return BigInt(ethers.keccak256(packed)).toString();
  }

  /**
   * Format snarkjs proof to Solidity-compatible format
   */
  private formatProof(proof: any): Groth16Proof {
    return {
      a: [proof.pi_a[0], proof.pi_a[1]],
      b: [
        [proof.pi_b[0][1], proof.pi_b[0][0]], // Note: reversed for Solidity
        [proof.pi_b[1][1], proof.pi_b[1][0]],
      ],
      c: [proof.pi_c[0], proof.pi_c[1]],
    };
  }

  /**
   * Load verification key from file
   */
  private async loadVerificationKey(path: string): Promise<any> {
    // In browser, fetch from URL
    // In Node.js, read from file
    if (typeof window !== 'undefined') {
      const response = await fetch(path);
      return await response.json();
    } else {
      const fs = await import('fs/promises');
      const content = await fs.readFile(path, 'utf-8');
      return JSON.parse(content);
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// CONTRACT ABI (Minimal for SDK usage)
// ═══════════════════════════════════════════════════════════════════════════

const ZKNAF_ABI = [
  'function verifyAndStore(uint8 proofType, tuple(uint256[2] a, uint256[2][2] b, uint256[2] c) proof, uint256[] publicInputs) returns (bytes32)',
  'function verify(uint8 proofType, tuple(uint256[2] a, uint256[2][2] b, uint256[2] c) proof, uint256[] publicInputs) view returns (bool)',
  'function hasValidProof(address account, uint8 proofType) view returns (bool)',
  'function isCompliant(address account) view returns (bool, bool, bool, bool)',
  'function proofRecords(bytes32) view returns (bytes32, uint8, address, uint256, uint256, bool)',
  'event ProofVerified(bytes32 indexed proofHash, uint8 indexed proofType, address indexed prover, uint256 expiresAt)',
];

// ═══════════════════════════════════════════════════════════════════════════
// EXPORTS
// ═══════════════════════════════════════════════════════════════════════════

export { ZkNAFService };
export default ZkNAFService;
