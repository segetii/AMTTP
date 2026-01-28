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
import Fastify from 'fastify';
import cors from '@fastify/cors';
import { ethers } from 'ethers';
import { randomUUID } from 'crypto';
// ═══════════════════════════════════════════════════════════════════════════
// DATA STORES (In production: PostgreSQL + encrypted storage)
// ═══════════════════════════════════════════════════════════════════════════
class ZkNAFDataStore {
    proofRecords = new Map();
    sanctionsList = new Map();
    sanctionsListRoot = '';
    trustedSetups = new Map();
    oracleSecrets = new Map(); // Secure key storage
    // ── PROOF RECORDS ────────────────────────────────────────────────────────
    saveProofRecord(record) {
        this.proofRecords.set(record.id, record);
    }
    getProofRecord(id) {
        return this.proofRecords.get(id);
    }
    getProofsByAddress(address) {
        return Array.from(this.proofRecords.values())
            .filter(r => r.userAddress.toLowerCase() === address.toLowerCase());
    }
    // ── SANCTIONS LIST ───────────────────────────────────────────────────────
    async updateSanctionsList(entries) {
        this.sanctionsList.clear();
        for (const entry of entries) {
            this.sanctionsList.set(entry.address.toLowerCase(), entry);
        }
        // Compute Merkle root
        this.sanctionsListRoot = await this.computeSanctionsRoot();
        return this.sanctionsListRoot;
    }
    isAddressSanctioned(address) {
        return this.sanctionsList.has(address.toLowerCase());
    }
    getSanctionsListRoot() {
        return this.sanctionsListRoot;
    }
    // Get neighbors for non-membership proof
    getNeighbors(address) {
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
            }
            else if (sorted[i] > target) {
                right = sorted[i];
                break;
            }
            else {
                // Address is in the list
                return null;
            }
        }
        return {
            left: '0x' + left.toString(16).padStart(40, '0'),
            right: '0x' + right.toString(16).padStart(40, '0'),
        };
    }
    async computeSanctionsRoot() {
        // Compute Poseidon Merkle root of sorted addresses
        // Simplified: using keccak256 for demonstration
        const sorted = Array.from(this.sanctionsList.keys()).sort();
        const packed = ethers.solidityPacked(sorted.map(() => 'address'), sorted);
        return ethers.keccak256(packed);
    }
    // ── TRUSTED SETUP ────────────────────────────────────────────────────────
    registerTrustedSetup(setup) {
        this.trustedSetups.set(setup.proofType, setup);
    }
    getTrustedSetup(proofType) {
        return this.trustedSetups.get(proofType);
    }
    // ── ORACLE SECRETS ───────────────────────────────────────────────────────
    setOracleSecret(proofType, secret) {
        this.oracleSecrets.set(proofType, secret);
    }
    getOracleSecret(proofType) {
        return this.oracleSecrets.get(proofType);
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// ZKNAF SERVICE
// ═══════════════════════════════════════════════════════════════════════════
class ZkNAFService {
    dataStore;
    provider;
    oracleSigner;
    constructor(rpcUrl, oraclePrivateKey) {
        this.dataStore = new ZkNAFDataStore();
        this.provider = new ethers.JsonRpcProvider(rpcUrl);
        this.oracleSigner = new ethers.Wallet(oraclePrivateKey, this.provider);
        // Initialize with demo data
        this.initializeDemoData();
    }
    initializeDemoData() {
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
                address: '0x8576acc5c05d6ce88f4e49bf65bdf0c62f91353c', // Tornado Cash
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
    async generateSanctionsProof(userAddress, signature) {
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
        // In production: generate actual ZK proof using snarkjs
        // For demo: create a placeholder proof hash
        const proofHash = ethers.keccak256(ethers.solidityPacked(['address', 'bytes32', 'uint256'], [userAddress, this.dataStore.getSanctionsListRoot(), Math.floor(Date.now() / 1000)]));
        const record = {
            id: randomUUID(),
            userAddress,
            proofType: 'sanctions',
            proofHash,
            publicSignals: [
                this.dataStore.getSanctionsListRoot(),
                Math.floor(Date.now() / 1000).toString(),
            ],
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
    async generateRiskRangeProof(userAddress, range, signature) {
        // Verify user signature
        await this.verifySignature(userAddress, `generate-risk-proof-${range}`, signature);
        // Get user's actual risk score from ML API
        const riskScore = await this.fetchRiskScore(userAddress);
        // Check if score is in requested range
        const [minScore, maxScore] = range === 'low' ? [0, 39] : [40, 69];
        if (riskScore < minScore || riskScore > maxScore) {
            throw new Error(`RISK_RANGE_MISMATCH: Score ${riskScore} not in ${range} range [${minScore}-${maxScore}]`);
        }
        // Generate signature commitment
        const oracleSecret = this.dataStore.getOracleSecret('risk');
        const signatureCommitment = ethers.keccak256(ethers.solidityPacked(['uint256', 'address', 'uint256', 'bytes32'], [riskScore, userAddress, Math.floor(Date.now() / 1000), oracleSecret]));
        const proofHash = ethers.keccak256(ethers.solidityPacked(['address', 'bytes32', 'uint256', 'uint256'], [userAddress, signatureCommitment, minScore, maxScore]));
        const record = {
            id: randomUUID(),
            userAddress,
            proofType: `risk-${range}`,
            proofHash,
            publicSignals: [
                signatureCommitment,
                ethers.keccak256(ethers.solidityPacked(['address'], [userAddress])),
                minScore.toString(),
                maxScore.toString(),
                Math.floor(Date.now() / 1000).toString(),
            ],
            createdAt: new Date(),
            expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
            internalData: {
                exactRiskScore: riskScore, // FCA: Actual score stored for regulatory disclosure
            },
        };
        this.dataStore.saveProofRecord(record);
        return record;
    }
    /**
     * Generate KYC verification proof
     */
    async generateKYCProof(userAddress, kycRecordId, signature) {
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
        const providerSecret = this.dataStore.getOracleSecret('kyc');
        const kycDataHash = ethers.keccak256(ethers.solidityPacked(['string', 'address', 'uint256'], [kycRecordId, userAddress, kycRecord.completedAt]));
        const providerCommitment = ethers.keccak256(ethers.solidityPacked(['bytes32', 'bytes32'], [kycDataHash, providerSecret]));
        const proofHash = ethers.keccak256(ethers.solidityPacked(['address', 'bytes32', 'uint256'], [userAddress, providerCommitment, Math.floor(Date.now() / 1000)]));
        const record = {
            id: randomUUID(),
            userAddress,
            proofType: 'kyc',
            proofHash,
            publicSignals: [
                providerCommitment,
                ethers.keccak256(ethers.solidityPacked(['address'], [userAddress])),
                Math.floor(Date.now() / 1000).toString(),
                (18 * 365 * 24 * 60 * 60).toString(), // minAgeSeconds
            ],
            createdAt: new Date(),
            expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
            internalData: {
                kycRecordId, // FCA: Full KYC record ID for regulatory disclosure
            },
        };
        this.dataStore.saveProofRecord(record);
        return record;
    }
    // ── HELPER METHODS ───────────────────────────────────────────────────────
    async verifySignature(address, message, signature) {
        const recoveredAddress = ethers.verifyMessage(message, signature);
        if (recoveredAddress.toLowerCase() !== address.toLowerCase()) {
            throw new Error('INVALID_SIGNATURE: Signature does not match address');
        }
    }
    async fetchRiskScore(address) {
        // In production: call ML Hybrid API
        // For demo: return random score
        return Math.floor(Math.random() * 50); // 0-49 (mostly low risk)
    }
    async fetchKYCRecord(address, recordId) {
        // In production: call Sumsub API or internal KYC DB
        // For demo: return valid record
        return {
            isValid: true,
            isPEP: false,
            completedAt: Math.floor(Date.now() / 1000) - 30 * 24 * 60 * 60, // 30 days ago
            expiresAt: Math.floor(Date.now() / 1000) + 335 * 24 * 60 * 60, // 335 days from now
        };
    }
    // ── GETTERS ──────────────────────────────────────────────────────────────
    getProofsByAddress(address) {
        return this.dataStore.getProofsByAddress(address);
    }
    getSanctionsListRoot() {
        return this.dataStore.getSanctionsListRoot();
    }
    isAddressSanctioned(address) {
        return this.dataStore.isAddressSanctioned(address);
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// API SERVER
// ═══════════════════════════════════════════════════════════════════════════
const app = Fastify({ logger: true });
// Initialize service
const zkNAFService = new ZkNAFService(process.env.RPC_URL || 'http://localhost:8545', process.env.ORACLE_PRIVATE_KEY || ethers.Wallet.createRandom().privateKey);
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
    proofTypes: ['sanctions', 'risk-low', 'risk-medium', 'kyc'],
    sanctionsListRoot: zkNAFService.getSanctionsListRoot(),
    fcaCompliant: true,
    endpoints: {
        'POST /zknaf/proof/sanctions': 'Generate sanctions non-membership proof',
        'POST /zknaf/proof/risk': 'Generate risk range proof',
        'POST /zknaf/proof/kyc': 'Generate KYC verification proof',
        'GET /zknaf/proofs/:address': 'Get proofs for address',
        'GET /zknaf/sanctions/check/:address': 'Check if address is sanctioned',
    },
}));
// Generate sanctions proof
app.post('/zknaf/proof/sanctions', async (request, reply) => {
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
    }
    catch (error) {
        reply.status(400);
        return { success: false, error: error.message };
    }
});
// Generate risk range proof
app.post('/zknaf/proof/risk', async (request, reply) => {
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
    }
    catch (error) {
        reply.status(400);
        return { success: false, error: error.message };
    }
});
// Generate KYC proof
app.post('/zknaf/proof/kyc', async (request, reply) => {
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
    }
    catch (error) {
        reply.status(400);
        return { success: false, error: error.message };
    }
});
// Get proofs for address
app.get('/zknaf/proofs/:address', async (request) => {
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
});
// Check if address is sanctioned (public check)
app.get('/zknaf/sanctions/check/:address', async (request) => {
    const { address } = request.params;
    const isSanctioned = zkNAFService.isAddressSanctioned(address);
    return {
        address,
        isSanctioned,
        sanctionsListRoot: zkNAFService.getSanctionsListRoot(),
        checkedAt: new Date().toISOString(),
    };
});
// ── START SERVER ───────────────────────────────────────────────────────────
const start = async () => {
    try {
        const port = parseInt(process.env.ZKNAF_PORT || '8003', 10);
        await app.listen({ port, host: '0.0.0.0' });
        console.log(`\n🔐 AMTTP zkNAF Service running on http://localhost:${port}`);
        console.log(`   - Health: http://localhost:${port}/zknaf/health`);
        console.log(`   - Info: http://localhost:${port}/zknaf/info`);
        console.log('\n📋 FCA Compliance: Full records maintained for regulatory disclosure\n');
    }
    catch (err) {
        app.log.error(err);
        process.exit(1);
    }
};
start();
export { ZkNAFService, app };
