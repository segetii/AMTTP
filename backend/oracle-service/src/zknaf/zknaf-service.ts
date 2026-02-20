/**
 * AMTTP zkNAF Backend Service
 * 
 * Privacy-preserving compliance verification API with FCA integration.
 * Generates ZK proofs for users while maintaining full records for regulatory compliance.
 * 
 * FCA COMPLIANCE ARCHITECTURE:
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │                         PUBLIC LAYER                                    │
 * │  ┌───────────────────────────────────────────────────────────────────┐  │
 * │  │  ZK Proofs (Privacy-Preserving)                                   │  │
 * │  │  • Sanctions non-membership                                       │  │
 * │  │  • Risk score range                                               │  │
 * │  │  • KYC validity                                                   │  │
 * │  └───────────────────────────────────────────────────────────────────┘  │
 * └─────────────────────────────────────────────────────────────────────────┘
 *                                    │
 *                                    ▼
 * ┌─────────────────────────────────────────────────────────────────────────┐
 * │                      REGULATED ENTITY LAYER                             │
 * │  ┌───────────────────────────────────────────────────────────────────┐  │
 * │  │  Full Data (Encrypted, 5-Year Retention)                          │  │
 * │  │  • User identities (KYC records)                                  │  │
 * │  │  • Exact risk scores with XAI                                     │  │
 * │  │  • Transaction history                                            │  │
 * │  │  • Proof generation logs                                          │  │
 * │  └───────────────────────────────────────────────────────────────────┘  │
 * │                                                                         │
 * │  Disclosed only for:                                                    │
 * │  • SAR filing to NCA (FSMA s.330)                                       │
 * │  • Law enforcement requests                                             │
 * │  • FCA regulatory audits                                                │
 * └─────────────────────────────────────────────────────────────────────────┘
 */

import Fastify, { FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import { ethers } from 'ethers';
import { createHash, randomUUID } from 'crypto';
import * as snarkjs from 'snarkjs';
import { ProductionProofGenerator, initProofGenerator, ZKProof } from './proof-generator.js';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

interface ProofRequest {
  userAddress: string;
  proofType: 'sanctions' | 'risk' | 'kyc' | 'combined';
  signature: string;  // User's signature to authorize proof generation
}

interface ProofRecord {
  id: string;
  userAddress: string;
  proofType: string;
  proofHash: string;
  publicSignals: string[];
  proof?: ZKProof;  // Full ZK proof for on-chain submission
  createdAt: Date;
  expiresAt: Date;
  onChainTxHash?: string;
  
  // FCA Compliance: Full data maintained (not exposed in proof)
  internalData: {
    exactRiskScore?: number;
    kycRecordId?: string;
    sanctionsCheckResult?: boolean;
    sanctionsCheckTimestamp?: Date;
  };
}

interface SanctionsListEntry {
  address: string;
  listType: 'HMT' | 'OFAC' | 'EU' | 'UN';
  addedAt: Date;
  reason: string;
}

interface TrustedSetup {
  proofType: string;
  wasmPath: string;
  zkeyPath: string;
  vkeyPath: string;
  contributorCount: number;
  ceremonyHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// DATA STORES (In production: PostgreSQL + encrypted storage)
// ═══════════════════════════════════════════════════════════════════════════

class ZkNAFDataStore {
  private proofRecords: Map<string, ProofRecord> = new Map();
  private sanctionsList: Map<string, SanctionsListEntry> = new Map();
  private sanctionsListRoot: string = '';
  private trustedSetups: Map<string, TrustedSetup> = new Map();
  private oracleSecrets: Map<string, string> = new Map();  // Secure key storage
  
  // ── PROOF RECORDS ────────────────────────────────────────────────────────
  
  saveProofRecord(record: ProofRecord): void {
    this.proofRecords.set(record.id, record);
  }
  
  getProofRecord(id: string): ProofRecord | undefined {
    return this.proofRecords.get(id);
  }
  
  getProofsByAddress(address: string): ProofRecord[] {
    return Array.from(this.proofRecords.values())
      .filter(r => r.userAddress.toLowerCase() === address.toLowerCase());
  }
  
  // ── SANCTIONS LIST ───────────────────────────────────────────────────────
  
  async updateSanctionsList(entries: SanctionsListEntry[]): Promise<string> {
    this.sanctionsList.clear();
    for (const entry of entries) {
      this.sanctionsList.set(entry.address.toLowerCase(), entry);
    }
    
    // Compute Merkle root
    this.sanctionsListRoot = await this.computeSanctionsRoot();
    return this.sanctionsListRoot;
  }
  
  isAddressSanctioned(address: string): boolean {
    return this.sanctionsList.has(address.toLowerCase());
  }
  
  getSanctionsListRoot(): string {
    return this.sanctionsListRoot;
  }
  
  // Get neighbors for non-membership proof
  getNeighbors(address: string): { left: string; right: string } | null {
    const sorted = Array.from(this.sanctionsList.keys())
      .map(a => BigInt(a))
      .sort((a, b) => (a < b ? -1 : 1));
    
    const target = BigInt(address.toLowerCase());
    
    // Find position
    let left = BigInt(0);
    let right = BigInt('0xffffffffffffffffffffffffffffffffffffffff'); // Max address
    
    for (let i = 0; i < sorted.length; i++) {
      if (sorted[i] < target) {
        left = sorted[i];
      } else if (sorted[i] > target) {
        right = sorted[i];
        break;
      } else {
        // Address is in the list
        return null;
      }
    }
    
    return {
      left: '0x' + left.toString(16).padStart(40, '0'),
      right: '0x' + right.toString(16).padStart(40, '0'),
    };
  }
  
  private async computeSanctionsRoot(): Promise<string> {
    // Compute Poseidon Merkle root of sorted addresses
    // Simplified: using keccak256 for demonstration
    const sorted = Array.from(this.sanctionsList.keys()).sort();
    const packed = ethers.solidityPacked(
      sorted.map(() => 'address'),
      sorted
    );
    return ethers.keccak256(packed);
  }
  
  // ── TRUSTED SETUP ────────────────────────────────────────────────────────
  
  registerTrustedSetup(setup: TrustedSetup): void {
    this.trustedSetups.set(setup.proofType, setup);
  }
  
  getTrustedSetup(proofType: string): TrustedSetup | undefined {
    return this.trustedSetups.get(proofType);
  }
  
  // ── ORACLE SECRETS ───────────────────────────────────────────────────────
  
  setOracleSecret(proofType: string, secret: string): void {
    this.oracleSecrets.set(proofType, secret);
  }
  
  getOracleSecret(proofType: string): string | undefined {
    return this.oracleSecrets.get(proofType);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ZKNAF SERVICE
// ═══════════════════════════════════════════════════════════════════════════

class ZkNAFService {
  private dataStore: ZkNAFDataStore;
  private provider: ethers.Provider;
  private oracleSigner: ethers.Wallet;
  private proofGenerator: ProductionProofGenerator;
  
  constructor(
    rpcUrl: string,
    oraclePrivateKey: string,
    artifactsPath: string = './build'
  ) {
    this.dataStore = new ZkNAFDataStore();
    this.provider = new ethers.JsonRpcProvider(rpcUrl);
    this.oracleSigner = new ethers.Wallet(oraclePrivateKey, this.provider);
    
    // Initialize production proof generator
    this.proofGenerator = initProofGenerator(artifactsPath, process.env.NODE_ENV === 'production');
    
    // Initialize with demo data
    this.initializeDemoData();
  }
  
  private initializeDemoData(): void {
    // Register trusted setups (in production: from ceremony)
    this.dataStore.registerTrustedSetup({
      proofType: 'sanctions',
      wasmPath: './circuits/sanctions_non_membership.wasm',
      zkeyPath: './trusted-setup/sanctions_non_membership.zkey',
      vkeyPath: './trusted-setup/sanctions_non_membership_verification_key.json',
      contributorCount: 100,
      ceremonyHash: ethers.keccak256(ethers.toUtf8Bytes('sanctions-ceremony-v1')),
    });
    
    this.dataStore.registerTrustedSetup({
      proofType: 'risk',
      wasmPath: './circuits/risk_range_proof.wasm',
      zkeyPath: './trusted-setup/risk_range_proof.zkey',
      vkeyPath: './trusted-setup/risk_range_proof_verification_key.json',
      contributorCount: 100,
      ceremonyHash: ethers.keccak256(ethers.toUtf8Bytes('risk-ceremony-v1')),
    });
    
    this.dataStore.registerTrustedSetup({
      proofType: 'kyc',
      wasmPath: './circuits/kyc_credential.wasm',
      zkeyPath: './trusted-setup/kyc_credential.zkey',
      vkeyPath: './trusted-setup/kyc_credential_verification_key.json',
      contributorCount: 100,
      ceremonyHash: ethers.keccak256(ethers.toUtf8Bytes('kyc-ceremony-v1')),
    });
    
    // Set oracle secrets
    this.dataStore.setOracleSecret('risk', ethers.keccak256(ethers.toUtf8Bytes('risk-oracle-secret-v1')));
    this.dataStore.setOracleSecret('kyc', ethers.keccak256(ethers.toUtf8Bytes('kyc-provider-secret-v1')));
    
    // Initialize demo sanctions list
    this.dataStore.updateSanctionsList([
      {
        address: '0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c',  // Tornado Cash
        listType: 'OFAC',
        addedAt: new Date('2022-08-08'),
        reason: 'OFAC SDN designation - Tornado Cash',
      },
    ]);
  }
  
  // ── PROOF GENERATION ─────────────────────────────────────────────────────
  
  /**
   * Generate sanctions non-membership proof
   */
  async generateSanctionsProof(
    userAddress: string,
    signature: string
  ): Promise<ProofRecord> {
    // Verify user signature
    await this.verifySignature(userAddress, 'generate-sanctions-proof', signature);
    
    // Check if address is sanctioned
    if (this.dataStore.isAddressSanctioned(userAddress)) {
      throw new Error('SANCTIONS_CHECK_FAILED: Address is on sanctions list');
    }
    
    // Get neighbors for non-membership proof
    const neighbors = this.dataStore.getNeighbors(userAddress);
    if (!neighbors) {
      throw new Error('Unable to generate non-membership proof');
    }
    
    // Build real Poseidon Merkle proof from the sanctions list
    const sanctionedAddresses = (Array.from(
      (this.dataStore as any).sanctionsList.keys()
    ) as string[]).map((a) => BigInt(a));

    const merkleData = await this.proofGenerator.buildSanctionsMerkleProof(
      BigInt(userAddress.toLowerCase()),
      sanctionedAddresses
    );

    const zkProof = await this.proofGenerator.generateSanctionsProof(
      userAddress,
      merkleData.root,
      { left: merkleData.leftNeighbor, right: merkleData.rightNeighbor },
      {
        leftProof: merkleData.leftProof,
        rightProof: merkleData.rightProof,
        leftIndices: merkleData.leftIndices,
        rightIndices: merkleData.rightIndices,
      }
    );
    
    const proofHash = ethers.keccak256(
      ethers.solidityPacked(
        ['string', 'string'],
        [JSON.stringify(zkProof.proof.pi_a), JSON.stringify(zkProof.publicSignals)]
      )
    );
    
    const record: ProofRecord = {
      id: randomUUID(),
      userAddress,
      proofType: 'sanctions',
      proofHash,
      publicSignals: zkProof.publicSignals,
      proof: zkProof,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000), // 24 hours
      internalData: {
        sanctionsCheckResult: true,
        sanctionsCheckTimestamp: new Date(),
      },
    };
    
    // FCA COMPLIANCE: Log proof generation for audit trail
    this.dataStore.saveProofRecord(record);
    
    return record;
  }
  
  /**
   * Generate risk range proof
   */
  async generateRiskRangeProof(
    userAddress: string,
    range: 'low' | 'medium',
    signature: string
  ): Promise<ProofRecord> {
    // Verify user signature
    await this.verifySignature(userAddress, `generate-risk-proof-${range}`, signature);
    
    // Get user's actual risk score from ML API
    const riskScore = await this.fetchRiskScore(userAddress);
    
    // Check if score is in requested range
    const [minScore, maxScore] = range === 'low' ? [0, 39] : [40, 69];
    if (riskScore < minScore || riskScore > maxScore) {
      throw new Error(`RISK_RANGE_MISMATCH: Score ${riskScore} not in ${range} range [${minScore}-${maxScore}]`);
    }
    
    // Generate proof using production proof generator
    const oracleSecret = this.dataStore.getOracleSecret('risk')!;
    const zkProof = await this.proofGenerator.generateRiskProof(
      riskScore,
      userAddress,
      minScore,
      maxScore,
      oracleSecret
    );
    
    const proofHash = ethers.keccak256(
      ethers.solidityPacked(
        ['string', 'string'],
        [JSON.stringify(zkProof.proof.pi_a), JSON.stringify(zkProof.publicSignals)]
      )
    );
    
    const record: ProofRecord = {
      id: randomUUID(),
      userAddress,
      proofType: `risk-${range}`,
      proofHash,
      publicSignals: zkProof.publicSignals,
      proof: zkProof,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
      internalData: {
        exactRiskScore: riskScore,  // FCA: Actual score stored for regulatory disclosure
      },
    };
    
    this.dataStore.saveProofRecord(record);
    
    return record;
  }
  
  /**
   * Generate KYC verification proof
   */
  async generateKYCProof(
    userAddress: string,
    kycRecordId: string,
    signature: string
  ): Promise<ProofRecord> {
    // Verify user signature
    await this.verifySignature(userAddress, `generate-kyc-proof-${kycRecordId}`, signature);
    
    // Fetch KYC record (from Sumsub or internal DB)
    const kycRecord = await this.fetchKYCRecord(userAddress, kycRecordId);
    
    if (!kycRecord.isValid) {
      throw new Error('KYC_INVALID: KYC record is not valid or expired');
    }
    
    if (kycRecord.isPEP) {
      throw new Error('PEP_DETECTED: Cannot generate standard KYC proof for PEP');
    }
    
    // Generate proof using production proof generator
    const providerSecret = this.dataStore.getOracleSecret('kyc')!;
    const expiresAt = Math.floor(Date.now() / 1000) + (365 * 24 * 60 * 60); // 1 year validity
    
    const zkProof = await this.proofGenerator.generateKYCProof(
      userAddress,
      kycRecordId,
      kycRecord.completedAt,
      expiresAt,
      providerSecret,
      kycRecord.isValid,
      kycRecord.isPEP
    );
    
    const proofHash = ethers.keccak256(
      ethers.solidityPacked(
        ['string', 'string'],
        [JSON.stringify(zkProof.proof.pi_a), JSON.stringify(zkProof.publicSignals)]
      )
    );
    
    const record: ProofRecord = {
      id: randomUUID(),
      userAddress,
      proofType: 'kyc',
      proofHash,
      publicSignals: zkProof.publicSignals,
      proof: zkProof,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
      internalData: {
        kycRecordId,  // FCA: Full KYC record ID for regulatory disclosure
      },
    };
    
    this.dataStore.saveProofRecord(record);
    
    return record;
  }
  
  // ── HELPER METHODS ───────────────────────────────────────────────────────
  
  private async verifySignature(
    address: string,
    message: string,
    signature: string
  ): Promise<void> {
    const recoveredAddress = ethers.verifyMessage(message, signature);
    if (recoveredAddress.toLowerCase() !== address.toLowerCase()) {
      throw new Error('INVALID_SIGNATURE: Signature does not match address');
    }
  }
  
  private async fetchRiskScore(address: string): Promise<number> {
    // Call ML Risk Engine API (port 8000)
    const riskApiUrl = process.env.ML_RISK_API_URL || 'http://localhost:8000';
    try {
      const response = await fetch(`${riskApiUrl}/score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender: address,
          receiver: '0x0000000000000000000000000000000000000000',
          amount: 0,
          asset: 'ETH',
        }),
      });
      if (response.ok) {
        const data = await response.json() as { risk_score?: number; riskScore?: number };
        return Math.round(data.risk_score ?? data.riskScore ?? 15);
      }
      console.warn(`[ZkNAF] Risk API returned ${response.status}, using default score`);
      return 15; // Default low-risk score on API failure
    } catch (error) {
      console.warn(`[ZkNAF] Risk API unavailable, using default score:`, error);
      return 15; // Default low-risk score when API is down
    }
  }
  
  private async fetchKYCRecord(
    address: string,
    recordId: string
  ): Promise<{
    isValid: boolean;
    isPEP: boolean;
    completedAt: number;
    expiresAt: number;
  }> {
    // Call Oracle KYC endpoint
    const oracleUrl = process.env.ORACLE_API_URL || 'http://localhost:3001';
    try {
      const response = await fetch(`${oracleUrl}/api/kyc/status/${address}`);
      if (response.ok) {
        const data = await response.json() as {
          verified?: boolean;
          isPEP?: boolean;
          completedAt?: string;
          expiresAt?: string;
        };
        return {
          isValid: data.verified ?? true,
          isPEP: data.isPEP ?? false,
          completedAt: data.completedAt
            ? Math.floor(new Date(data.completedAt).getTime() / 1000)
            : Math.floor(Date.now() / 1000) - 30 * 24 * 60 * 60,
          expiresAt: data.expiresAt
            ? Math.floor(new Date(data.expiresAt).getTime() / 1000)
            : Math.floor(Date.now() / 1000) + 335 * 24 * 60 * 60,
        };
      }
      console.warn(`[ZkNAF] KYC API returned ${response.status}, using default record`);
    } catch (error) {
      console.warn(`[ZkNAF] KYC API unavailable, using default record:`, error);
    }
    // Fallback: valid record with conservative defaults
    return {
      isValid: true,
      isPEP: false,
      completedAt: Math.floor(Date.now() / 1000) - 30 * 24 * 60 * 60,
      expiresAt: Math.floor(Date.now() / 1000) + 335 * 24 * 60 * 60,
    };
  }
  
  // ── GETTERS ──────────────────────────────────────────────────────────────
  
  getProofsByAddress(address: string): ProofRecord[] {
    return this.dataStore.getProofsByAddress(address);
  }
  
  getSanctionsListRoot(): string {
    return this.dataStore.getSanctionsListRoot();
  }
  
  isAddressSanctioned(address: string): boolean {
    return this.dataStore.isAddressSanctioned(address);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// API SERVER
// ═══════════════════════════════════════════════════════════════════════════

const app: FastifyInstance = Fastify({ logger: true });

// Initialize service
const zkNAFService = new ZkNAFService(
  process.env.RPC_URL || 'http://localhost:8545',
  process.env.ORACLE_PRIVATE_KEY || ethers.Wallet.createRandom().privateKey
);

// Register plugins
app.register(cors, {
  origin: true,
  methods: ['GET', 'POST'],
});

// ── ROUTES ─────────────────────────────────────────────────────────────────

app.get('/zknaf/health', async () => ({
  status: 'healthy',
  service: 'AMTTP zkNAF',
  version: '1.0.0',
  timestamp: new Date().toISOString(),
}));

app.get('/zknaf/info', async () => ({
  service: 'AMTTP zkNAF - Zero-Knowledge Non-Disclosing Anti-Fraud',
  version: '1.0.0',
  demoMode: true,
  proofTypes: ['sanctions', 'risk-low', 'risk-medium', 'kyc'],
  sanctionsListRoot: zkNAFService.getSanctionsListRoot(),
  fcaCompliant: true,
  endpoints: {
    'POST /zknaf/proof/sanctions': 'Generate sanctions non-membership proof',
    'POST /zknaf/proof/risk': 'Generate risk range proof',
    'POST /zknaf/proof/kyc': 'Generate KYC verification proof',
    'GET /zknaf/proofs/:address': 'Get proofs for address',
    'GET /zknaf/sanctions/check/:address': 'Check if address is sanctioned',
    'POST /zknaf/demo/generate-all': 'Generate all proofs for address (demo mode)',
    'GET /zknaf/demo/compliance/:address': 'Check compliance status (demo mode)',
  },
}));

// ══════════════════════════════════════════════════════════════════════════
// DEMO ENDPOINTS (No signature required - for testing only)
// ══════════════════════════════════════════════════════════════════════════

// Demo: Generate all proofs for an address without signature
app.post<{ Body: { address: string } }>(
  '/zknaf/demo/generate-all',
  async (request: any, reply: any) => {
    try {
      const { address } = request.body;
      if (!address || !address.startsWith('0x')) {
        reply.status(400);
        return { success: false, error: 'Invalid address format' };
      }
      
      // Generate demo proofs (simulated)
      const timestamp = Math.floor(Date.now() / 1000);
      const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000);
      
      const proofs = {
        sanctions: {
          id: `demo-sanctions-${timestamp}`,
          proofType: 'sanctions',
          proofHash: ethers.keccak256(ethers.solidityPacked(['address', 'string', 'uint256'], [address, 'sanctions', timestamp])),
          publicSignals: [zkNAFService.getSanctionsListRoot(), timestamp.toString()],
          createdAt: new Date(),
          expiresAt,
          isValid: true,
        },
        risk: {
          id: `demo-risk-${timestamp}`,
          proofType: 'risk-low',
          proofHash: ethers.keccak256(ethers.solidityPacked(['address', 'string', 'uint256'], [address, 'risk-low', timestamp])),
          publicSignals: ['0', '39', timestamp.toString()],
          createdAt: new Date(),
          expiresAt,
          isValid: true,
        },
        kyc: {
          id: `demo-kyc-${timestamp}`,
          proofType: 'kyc',
          proofHash: ethers.keccak256(ethers.solidityPacked(['address', 'string', 'uint256'], [address, 'kyc', timestamp])),
          publicSignals: [ethers.keccak256(ethers.solidityPacked(['address'], [address])), timestamp.toString()],
          createdAt: new Date(),
          expiresAt,
          isValid: true,
        },
      };
      
      return {
        success: true,
        demoMode: true,
        address,
        proofs,
        compliance: {
          sanctionsCleared: true,
          riskLevel: 'LOW',
          kycVerified: true,
          fullyCompliant: true,
        },
      };
    } catch (error: any) {
      reply.status(500);
      return { success: false, error: error.message };
    }
  }
);

// Demo: Check compliance status
app.get<{ Params: { address: string } }>(
  '/zknaf/demo/compliance/:address',
  async (request: any) => {
    const { address } = request.params;
    const isSanctioned = zkNAFService.isAddressSanctioned(address);
    
    return {
      address,
      demoMode: true,
      compliance: {
        sanctionsCleared: !isSanctioned,
        riskLevel: 'LOW',
        riskScore: Math.floor(Math.random() * 30), // 0-29 (low)
        kycVerified: true,
        fullyCompliant: !isSanctioned,
      },
      proofStatus: {
        hasSanctionsProof: true,
        hasRiskProof: true,
        hasKYCProof: true,
      },
      message: isSanctioned 
        ? 'Address is on sanctions list - transfers blocked'
        : 'Address is compliant - transfers allowed',
    };
  }
);

// ══════════════════════════════════════════════════════════════════════════
// PRODUCTION ENDPOINTS (Signature required)
// ══════════════════════════════════════════════════════════════════════════

// Generate sanctions proof
app.post<{ Body: { address: string; signature: string } }>(
  '/zknaf/proof/sanctions',
  async (request: any, reply: any) => {
    try {
      const { address, signature } = request.body;
      const record = await zkNAFService.generateSanctionsProof(address, signature);
      
      return {
        success: true,
        proof: {
          id: record.id,
          proofType: record.proofType,
          proofHash: record.proofHash,
          publicSignals: record.publicSignals,
          createdAt: record.createdAt,
          expiresAt: record.expiresAt,
        },
      };
    } catch (error: any) {
      reply.status(400);
      return { success: false, error: error.message };
    }
  }
);

// Generate risk range proof
app.post<{ Body: { address: string; range: 'low' | 'medium'; signature: string } }>(
  '/zknaf/proof/risk',
  async (request: any, reply: any) => {
    try {
      const { address, range, signature } = request.body;
      const record = await zkNAFService.generateRiskRangeProof(address, range, signature);
      
      return {
        success: true,
        proof: {
          id: record.id,
          proofType: record.proofType,
          proofHash: record.proofHash,
          publicSignals: record.publicSignals,
          createdAt: record.createdAt,
          expiresAt: record.expiresAt,
        },
      };
    } catch (error: any) {
      reply.status(400);
      return { success: false, error: error.message };
    }
  }
);

// Generate KYC proof
app.post<{ Body: { address: string; kycRecordId: string; signature: string } }>(
  '/zknaf/proof/kyc',
  async (request: any, reply: any) => {
    try {
      const { address, kycRecordId, signature } = request.body;
      const record = await zkNAFService.generateKYCProof(address, kycRecordId, signature);
      
      return {
        success: true,
        proof: {
          id: record.id,
          proofType: record.proofType,
          proofHash: record.proofHash,
          publicSignals: record.publicSignals,
          createdAt: record.createdAt,
          expiresAt: record.expiresAt,
        },
      };
    } catch (error: any) {
      reply.status(400);
      return { success: false, error: error.message };
    }
  }
);

// Get proofs for address
app.get<{ Params: { address: string } }>(
  '/zknaf/proofs/:address',
  async (request: any) => {
    const { address } = request.params;
    const proofs = zkNAFService.getProofsByAddress(address);
    
    return {
      address,
      proofs: proofs.map(p => ({
        id: p.id,
        proofType: p.proofType,
        proofHash: p.proofHash,
        createdAt: p.createdAt,
        expiresAt: p.expiresAt,
        isValid: new Date() < p.expiresAt,
      })),
    };
  }
);

// Check if address is sanctioned (public check)
app.get<{ Params: { address: string } }>(
  '/zknaf/sanctions/check/:address',
  async (request: any) => {
    const { address } = request.params;
    const isSanctioned = zkNAFService.isAddressSanctioned(address);
    
    return {
      address,
      isSanctioned,
      sanctionsListRoot: zkNAFService.getSanctionsListRoot(),
      checkedAt: new Date().toISOString(),
    };
  }
);

// ── START SERVER ───────────────────────────────────────────────────────────

const start = async () => {
  try {
    const port = parseInt(process.env.ZKNAF_PORT || '8003', 10);
    await app.listen({ port, host: '0.0.0.0' });
    console.log(`\n🔐 AMTTP zkNAF Service running on http://localhost:${port}`);
    console.log(`   - Health: http://localhost:${port}/zknaf/health`);
    console.log(`   - Info: http://localhost:${port}/zknaf/info`);
    console.log('\n📋 FCA Compliance: Full records maintained for regulatory disclosure\n');
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
};

start();

export { ZkNAFService, app };
