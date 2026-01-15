/**
 * AMTTP Oracle Trust Model
 * Signed responses with (decision, score, explanation_hash, signature)
 * IPFS integration for immutable audit trail
 */

import { createHash, createSign, createVerify, generateKeyPairSync } from 'crypto';
import { ethers } from 'ethers';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface OracleRequest {
  transactionHash?: string;
  from: string;
  to: string;
  amount: number;
  assetType: string;
  data?: string;
  timestamp: Date;
  nonce: string;
}

export interface OracleDecision {
  requestId: string;
  decision: 'ALLOW' | 'BLOCK' | 'REVIEW' | 'ESCALATE';
  riskScore: number;
  confidence: number;
  policyTriggered: string[];
  sarRequired: boolean;
  freezeRequired: boolean;
}

export interface SignedOracleResponse {
  // Core response data
  requestId: string;
  decision: OracleDecision['decision'];
  riskScore: number;
  confidence: number;
  
  // Audit trail
  explanationHash: string;  // IPFS CID or SHA256 of full explanation
  policyVersion: string;
  modelVersion: string;
  timestamp: number;
  expiresAt: number;
  
  // Cryptographic proof
  signature: string;
  signerAddress: string;
  signatureType: 'ECDSA' | 'RSA' | 'HSM';
  
  // On-chain verification
  chainId: number;
  oracleContractAddress: string;
}

export interface ExplanationPayload {
  requestId: string;
  request: OracleRequest;
  decision: OracleDecision;
  features: Record<string, number>;
  policyEvaluations: Array<{
    policyId: string;
    policyName: string;
    triggered: boolean;
    reason: string;
  }>;
  modelOutputs: {
    dqnScore: number;
    autoencoderAnomaly: number;
    xgboostScore: number;
    ensembleScore: number;
  };
  timestamp: Date;
}

// ═══════════════════════════════════════════════════════════════════════════
// ORACLE SIGNER CLASS
// ═══════════════════════════════════════════════════════════════════════════

export class OracleSigner {
  private wallet: ethers.Wallet | ethers.HDNodeWallet | null = null;
  private rsaKeyPair: { publicKey: string; privateKey: string } | null = null;
  private signatureType: SignedOracleResponse['signatureType'];
  private oracleContractAddress: string;
  private chainId: number;
  private responseTTL: number; // seconds

  constructor(config: {
    privateKey?: string;
    signatureType?: SignedOracleResponse['signatureType'];
    oracleContractAddress?: string;
    chainId?: number;
    responseTTL?: number;
  }) {
    this.signatureType = config.signatureType || 'ECDSA';
    this.oracleContractAddress = config.oracleContractAddress || '0x0000000000000000000000000000000000000000';
    this.chainId = config.chainId || 31337;
    this.responseTTL = config.responseTTL || 300; // 5 minutes default

    if (this.signatureType === 'ECDSA') {
      const pk = config.privateKey || process.env.ORACLE_PRIVATE_KEY;
      if (pk) {
        this.wallet = new ethers.Wallet(pk);
      } else {
        // Generate ephemeral key for development
        this.wallet = ethers.Wallet.createRandom();
        console.warn('Using ephemeral oracle key. Set ORACLE_PRIVATE_KEY in production.');
      }
    } else if (this.signatureType === 'RSA') {
      this.rsaKeyPair = generateKeyPairSync('rsa', {
        modulusLength: 2048,
        publicKeyEncoding: { type: 'spki', format: 'pem' },
        privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
      });
    }
  }

  /**
   * Get the oracle's signing address
   */
  getSignerAddress(): string {
    if (this.signatureType === 'ECDSA' && this.wallet) {
      return this.wallet.address;
    }
    if (this.signatureType === 'RSA' && this.rsaKeyPair) {
      return createHash('sha256').update(this.rsaKeyPair.publicKey).digest('hex').substring(0, 40);
    }
    throw new Error('No signer configured');
  }

  /**
   * Create a signed oracle response
   */
  async signResponse(
    request: OracleRequest,
    decision: OracleDecision,
    explanation: ExplanationPayload,
    policyVersion: string,
    modelVersion: string
  ): Promise<SignedOracleResponse> {
    const requestId = this.computeRequestId(request);
    const timestamp = Math.floor(Date.now() / 1000);
    const expiresAt = timestamp + this.responseTTL;

    // Compute explanation hash (would be IPFS CID in production)
    const explanationHash = this.computeExplanationHash(explanation);

    // Create the response payload to sign
    const payload = {
      requestId,
      decision: decision.decision,
      riskScore: decision.riskScore,
      confidence: decision.confidence,
      explanationHash,
      policyVersion,
      modelVersion,
      timestamp,
      expiresAt,
      chainId: this.chainId,
      oracleContractAddress: this.oracleContractAddress,
    };

    // Sign the payload
    const signature = await this.sign(payload);

    return {
      ...payload,
      signature,
      signerAddress: this.getSignerAddress(),
      signatureType: this.signatureType,
    };
  }

  /**
   * Verify a signed response
   */
  verifySignature(response: SignedOracleResponse): boolean {
    const { signature, signerAddress, signatureType, ...payload } = response;

    if (signatureType === 'ECDSA') {
      return this.verifyECDSA(payload, signature, signerAddress);
    } else if (signatureType === 'RSA' && this.rsaKeyPair) {
      return this.verifyRSA(payload, signature);
    }
    return false;
  }

  private async sign(payload: object): Promise<string> {
    const message = JSON.stringify(payload);
    const messageHash = createHash('sha256').update(message).digest('hex');

    if (this.signatureType === 'ECDSA' && this.wallet) {
      // EIP-191 style signing for on-chain verification
      return await this.wallet.signMessage(messageHash);
    } else if (this.signatureType === 'RSA' && this.rsaKeyPair) {
      const sign = createSign('SHA256');
      sign.update(message);
      return sign.sign(this.rsaKeyPair.privateKey, 'hex');
    }
    throw new Error('No signing method available');
  }

  private verifyECDSA(payload: object, signature: string, expectedAddress: string): boolean {
    try {
      const message = JSON.stringify(payload);
      const messageHash = createHash('sha256').update(message).digest('hex');
      const recoveredAddress = ethers.verifyMessage(messageHash, signature);
      return recoveredAddress.toLowerCase() === expectedAddress.toLowerCase();
    } catch {
      return false;
    }
  }

  private verifyRSA(payload: object, signature: string): boolean {
    if (!this.rsaKeyPair) return false;
    try {
      const verify = createVerify('SHA256');
      verify.update(JSON.stringify(payload));
      return verify.verify(this.rsaKeyPair.publicKey, signature, 'hex');
    } catch {
      return false;
    }
  }

  private computeRequestId(request: OracleRequest): string {
    const data = `${request.from}:${request.to}:${request.amount}:${request.nonce}:${request.timestamp.toISOString()}`;
    return createHash('sha256').update(data).digest('hex').substring(0, 32);
  }

  private computeExplanationHash(explanation: ExplanationPayload): string {
    return createHash('sha256').update(JSON.stringify(explanation)).digest('hex');
  }

  /**
   * Create EIP-712 typed data for on-chain verification
   */
  createTypedData(response: SignedOracleResponse): object {
    return {
      types: {
        EIP712Domain: [
          { name: 'name', type: 'string' },
          { name: 'version', type: 'string' },
          { name: 'chainId', type: 'uint256' },
          { name: 'verifyingContract', type: 'address' },
        ],
        OracleResponse: [
          { name: 'requestId', type: 'bytes32' },
          { name: 'decision', type: 'uint8' },
          { name: 'riskScore', type: 'uint256' },
          { name: 'explanationHash', type: 'bytes32' },
          { name: 'timestamp', type: 'uint256' },
          { name: 'expiresAt', type: 'uint256' },
        ],
      },
      primaryType: 'OracleResponse',
      domain: {
        name: 'AMTTP Oracle',
        version: '1',
        chainId: this.chainId,
        verifyingContract: this.oracleContractAddress,
      },
      message: {
        requestId: `0x${response.requestId}`,
        decision: this.decisionToUint(response.decision),
        riskScore: Math.floor(response.riskScore * 1e18),
        explanationHash: `0x${response.explanationHash}`,
        timestamp: response.timestamp,
        expiresAt: response.expiresAt,
      },
    };
  }

  private decisionToUint(decision: OracleDecision['decision']): number {
    const mapping = { ALLOW: 0, REVIEW: 1, ESCALATE: 2, BLOCK: 3 };
    return mapping[decision];
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// IPFS INTEGRATION (Mock for now, replace with actual IPFS client)
// ═══════════════════════════════════════════════════════════════════════════

export class ExplanationStore {
  private storage: Map<string, ExplanationPayload> = new Map();

  /**
   * Store explanation and return CID (mock IPFS)
   */
  async store(explanation: ExplanationPayload): Promise<string> {
    const hash = createHash('sha256').update(JSON.stringify(explanation)).digest('hex');
    const cid = `bafybeih${hash.substring(0, 50)}`; // Mock IPFS CID format
    this.storage.set(cid, explanation);
    
    // In production: use actual IPFS client
    // const cid = await ipfs.add(JSON.stringify(explanation));
    // return cid.toString();
    
    return cid;
  }

  /**
   * Retrieve explanation by CID
   */
  async retrieve(cid: string): Promise<ExplanationPayload | null> {
    return this.storage.get(cid) || null;
  }

  /**
   * Verify explanation matches hash
   */
  verify(explanation: ExplanationPayload, expectedHash: string): boolean {
    const actualHash = createHash('sha256').update(JSON.stringify(explanation)).digest('hex');
    return actualHash === expectedHash;
  }
}

// Singleton instances
let signerInstance: OracleSigner | null = null;
let storeInstance: ExplanationStore | null = null;

export function getOracleSigner(): OracleSigner {
  if (!signerInstance) {
    signerInstance = new OracleSigner({
      privateKey: process.env.ORACLE_PRIVATE_KEY,
      signatureType: 'ECDSA',
      chainId: parseInt(process.env.CHAIN_ID || '31337'),
      oracleContractAddress: process.env.ORACLE_CONTRACT_ADDRESS,
    });
  }
  return signerInstance;
}

export function getExplanationStore(): ExplanationStore {
  if (!storeInstance) {
    storeInstance = new ExplanationStore();
  }
  return storeInstance;
}

export default { OracleSigner, ExplanationStore, getOracleSigner, getExplanationStore };
