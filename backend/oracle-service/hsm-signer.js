/**
 * AMTTP HSM Oracle Signing Service
 * 
 * Provides secure signing using AWS KMS or HashiCorp Vault HSM integration.
 * The private keys never leave the HSM - only signatures are returned.
 * 
 * Features:
 * - AWS KMS SECP256K1 signing (EIP-191 compatible)
 * - HashiCorp Vault Transit engine support
 * - Multi-oracle signature aggregation
 * - Nonce management to prevent replay
 * - Signature expiry timestamps
 */

const { ethers } = require('ethers');
const crypto = require('crypto');

// AWS SDK v3
let KMSClient, SignCommand;
try {
    const kms = require('@aws-sdk/client-kms');
    KMSClient = kms.KMSClient;
    SignCommand = kms.SignCommand;
} catch (e) {
    console.warn('AWS SDK not installed - AWS KMS signing unavailable');
}

// HashiCorp Vault (optional)
let vault;
try {
    vault = require('node-vault');
} catch (e) {
    console.warn('node-vault not installed - Vault signing unavailable');
}

/**
 * Oracle Signer Configuration
 */
const CONFIG = {
    // Signature validity window (5 minutes)
    SIGNATURE_VALIDITY_SECONDS: 300,
    
    // AWS KMS Configuration
    aws: {
        region: process.env.AWS_REGION || 'eu-west-1',
        keyIds: [
            process.env.ORACLE_KMS_KEY_1,
            process.env.ORACLE_KMS_KEY_2,
            process.env.ORACLE_KMS_KEY_3,
        ].filter(Boolean),
    },
    
    // HashiCorp Vault Configuration
    vault: {
        endpoint: process.env.VAULT_ADDR || 'http://127.0.0.1:8200',
        token: process.env.VAULT_TOKEN,
        transitMount: process.env.VAULT_TRANSIT_MOUNT || 'transit',
        keyNames: [
            process.env.ORACLE_VAULT_KEY_1 || 'amttp-oracle-1',
            process.env.ORACLE_VAULT_KEY_2 || 'amttp-oracle-2',
            process.env.ORACLE_VAULT_KEY_3 || 'amttp-oracle-3',
        ],
    },
    
    // Required threshold (2-of-3)
    threshold: parseInt(process.env.ORACLE_THRESHOLD || '2'),
};

/**
 * Nonce Manager - Tracks used nonces to prevent replay
 */
class NonceManager {
    constructor() {
        this.usedNonces = new Map(); // user -> Set of used nonces
        this.userNonceCounters = new Map(); // user -> current nonce counter
    }
    
    /**
     * Generate next nonce for a user
     */
    getNextNonce(userAddress) {
        const addr = userAddress.toLowerCase();
        const current = this.userNonceCounters.get(addr) || 0;
        const next = current + 1;
        this.userNonceCounters.set(addr, next);
        return next;
    }
    
    /**
     * Mark a nonce as used
     */
    markUsed(userAddress, nonce) {
        const addr = userAddress.toLowerCase();
        if (!this.usedNonces.has(addr)) {
            this.usedNonces.set(addr, new Set());
        }
        this.usedNonces.get(addr).add(nonce);
    }
    
    /**
     * Check if nonce was already used
     */
    isUsed(userAddress, nonce) {
        const addr = userAddress.toLowerCase();
        return this.usedNonces.has(addr) && this.usedNonces.get(addr).has(nonce);
    }
}

const nonceManager = new NonceManager();

/**
 * AWS KMS Signing Class
 * Uses SECP256K1 key for Ethereum-compatible signatures
 */
class AWSKMSSigner {
    constructor(keyId, region = CONFIG.aws.region) {
        this.keyId = keyId;
        this.client = new KMSClient({ region });
        this.publicKey = null;
        this.address = null;
    }
    
    /**
     * Get Ethereum address from KMS public key
     */
    async getAddress() {
        if (this.address) return this.address;
        
        const { GetPublicKeyCommand } = require('@aws-sdk/client-kms');
        const response = await this.client.send(new GetPublicKeyCommand({
            KeyId: this.keyId,
        }));
        
        // Parse the DER-encoded public key
        const publicKeyDer = Buffer.from(response.PublicKey);
        
        // SECP256K1 public key is 65 bytes (04 + x + y)
        // DER encoding adds header bytes
        // Skip DER header to get raw public key
        const publicKeyRaw = publicKeyDer.slice(-64); // Last 64 bytes are x || y
        
        // Ethereum address = keccak256(public_key)[12:]
        const hash = ethers.keccak256('0x' + publicKeyRaw.toString('hex'));
        this.address = '0x' + hash.slice(-40);
        
        return this.address;
    }
    
    /**
     * Sign message hash using KMS
     */
    async signHash(messageHash) {
        // Remove 0x prefix if present
        const hashBytes = Buffer.from(messageHash.replace('0x', ''), 'hex');
        
        const response = await this.client.send(new SignCommand({
            KeyId: this.keyId,
            Message: hashBytes,
            MessageType: 'DIGEST',
            SigningAlgorithm: 'ECDSA_SHA_256',
        }));
        
        // Parse DER signature to get r, s values
        const signature = Buffer.from(response.Signature);
        const { r, s } = this._parseDerSignature(signature);
        
        // Recover v value by trying both 27 and 28
        const messageHashFull = ethers.keccak256(
            ethers.solidityPacked(['string', 'bytes32'], ['\x19Ethereum Signed Message:\n32', messageHash])
        );
        
        let v = 27;
        const address = await this.getAddress();
        
        for (let testV = 27; testV <= 28; testV++) {
            try {
                const recovered = ethers.recoverAddress(messageHashFull, {
                    r: '0x' + r.toString('hex').padStart(64, '0'),
                    s: '0x' + s.toString('hex').padStart(64, '0'),
                    v: testV,
                });
                if (recovered.toLowerCase() === address.toLowerCase()) {
                    v = testV;
                    break;
                }
            } catch (e) {
                continue;
            }
        }
        
        // Construct signature
        return ethers.concat([
            '0x' + r.toString('hex').padStart(64, '0'),
            '0x' + s.toString('hex').padStart(64, '0'),
            '0x' + (v).toString(16).padStart(2, '0'),
        ]);
    }
    
    /**
     * Parse DER-encoded ECDSA signature
     */
    _parseDerSignature(derSig) {
        // DER format: 0x30 [total-length] 0x02 [r-length] [r] 0x02 [s-length] [s]
        let offset = 2; // Skip 0x30 and total length
        
        // Parse r
        if (derSig[offset] !== 0x02) throw new Error('Invalid DER: expected 0x02 for r');
        const rLen = derSig[offset + 1];
        offset += 2;
        let r = derSig.slice(offset, offset + rLen);
        offset += rLen;
        
        // Parse s
        if (derSig[offset] !== 0x02) throw new Error('Invalid DER: expected 0x02 for s');
        const sLen = derSig[offset + 1];
        offset += 2;
        let s = derSig.slice(offset, offset + sLen);
        
        // Remove leading zeros (DER uses signed integers)
        if (r[0] === 0x00 && r.length > 32) r = r.slice(1);
        if (s[0] === 0x00 && s.length > 32) s = s.slice(1);
        
        // Pad to 32 bytes
        r = Buffer.concat([Buffer.alloc(32 - r.length), r]);
        s = Buffer.concat([Buffer.alloc(32 - s.length), s]);
        
        return { r, s };
    }
}

/**
 * HashiCorp Vault Transit Signer
 * Uses Vault's Transit secrets engine with ECDSA-P256 key
 */
class VaultTransitSigner {
    constructor(keyName) {
        this.keyName = keyName;
        this.client = vault({
            endpoint: CONFIG.vault.endpoint,
            token: CONFIG.vault.token,
        });
        this.address = null;
    }
    
    /**
     * Get Ethereum address from Vault key
     */
    async getAddress() {
        if (this.address) return this.address;
        
        const result = await this.client.read(`${CONFIG.vault.transitMount}/keys/${this.keyName}`);
        const publicKey = result.data.keys['1'].public_key;
        
        // Parse PEM public key and derive address
        // Note: Vault uses P-256 by default, for SECP256K1 use custom plugin
        const keyData = Buffer.from(publicKey.replace(/-----.*-----/g, '').replace(/\s/g, ''), 'base64');
        const publicKeyRaw = keyData.slice(-64);
        
        const hash = ethers.keccak256('0x' + publicKeyRaw.toString('hex'));
        this.address = '0x' + hash.slice(-40);
        
        return this.address;
    }
    
    /**
     * Sign message hash using Vault Transit
     */
    async signHash(messageHash) {
        const hashBytes = Buffer.from(messageHash.replace('0x', ''), 'hex');
        const hashBase64 = hashBytes.toString('base64');
        
        const result = await this.client.write(`${CONFIG.vault.transitMount}/sign/${this.keyName}`, {
            input: hashBase64,
            prehashed: true,
            signature_algorithm: 'pkcs1v15',
        });
        
        const signature = result.data.signature;
        // Parse vault:v1:base64signature format
        const sigData = Buffer.from(signature.split(':')[2], 'base64');
        
        // Convert to Ethereum signature format
        return this._toEthSignature(sigData, messageHash);
    }
    
    async _toEthSignature(sigData, messageHash) {
        const r = sigData.slice(0, 32);
        const s = sigData.slice(32, 64);
        
        const address = await this.getAddress();
        let v = 27;
        
        for (let testV = 27; testV <= 28; testV++) {
            try {
                const recovered = ethers.recoverAddress(messageHash, {
                    r: '0x' + r.toString('hex'),
                    s: '0x' + s.toString('hex'),
                    v: testV,
                });
                if (recovered.toLowerCase() === address.toLowerCase()) {
                    v = testV;
                    break;
                }
            } catch (e) {
                continue;
            }
        }
        
        return ethers.concat([
            '0x' + r.toString('hex'),
            '0x' + s.toString('hex'),
            '0x' + v.toString(16),
        ]);
    }
}

/**
 * Local Development Signer (for testing only!)
 * Uses in-memory private keys - NEVER use in production
 */
class LocalDevSigner {
    constructor(privateKey) {
        this.wallet = new ethers.Wallet(privateKey);
    }
    
    async getAddress() {
        return this.wallet.address;
    }
    
    async signHash(messageHash) {
        const ethSignedHash = ethers.keccak256(
            ethers.solidityPacked(['string', 'bytes32'], ['\x19Ethereum Signed Message:\n32', messageHash])
        );
        return this.wallet.signingKey.sign(ethSignedHash).serialized;
    }
}

/**
 * Multi-Oracle Signature Aggregator
 * Collects signatures from multiple oracle HSMs
 */
class OracleSignatureAggregator {
    constructor(signers = []) {
        this.signers = signers;
        this.threshold = CONFIG.threshold;
    }
    
    /**
     * Add an oracle signer
     */
    addSigner(signer) {
        this.signers.push(signer);
    }
    
    /**
     * Get all oracle addresses
     */
    async getOracleAddresses() {
        return Promise.all(this.signers.map(s => s.getAddress()));
    }
    
    /**
     * Generate multi-oracle signatures for a swap
     * @returns {signatures, nonce, timestamp}
     */
    async signSwapData(buyer, seller, amount, riskScore, kycHash) {
        // Generate nonce and timestamp
        const nonce = nonceManager.getNextNonce(buyer);
        const timestamp = Math.floor(Date.now() / 1000);
        
        // Create the message hash (matches contract)
        const messageHash = ethers.keccak256(
            ethers.solidityPacked(
                ['address', 'address', 'uint256', 'uint256', 'bytes32', 'uint256', 'uint256'],
                [buyer, seller, amount, riskScore, kycHash, nonce, timestamp]
            )
        );
        
        // Collect signatures from threshold oracles
        const signatures = [];
        const errors = [];
        
        for (let i = 0; i < this.signers.length && signatures.length < this.threshold; i++) {
            try {
                const sig = await this.signers[i].signHash(messageHash);
                signatures.push(sig);
                console.log(`Oracle ${i + 1} signed successfully`);
            } catch (e) {
                errors.push({ oracle: i + 1, error: e.message });
                console.error(`Oracle ${i + 1} failed:`, e.message);
            }
        }
        
        if (signatures.length < this.threshold) {
            throw new Error(
                `Failed to collect ${this.threshold} signatures. Got ${signatures.length}. Errors: ${JSON.stringify(errors)}`
            );
        }
        
        // Mark nonce as used
        nonceManager.markUsed(buyer, nonce);
        
        return {
            signatures,
            nonce,
            timestamp,
            expiresAt: timestamp + CONFIG.SIGNATURE_VALIDITY_SECONDS,
            messageHash,
        };
    }
}

/**
 * Create oracle signers based on environment
 */
function createOracleSigners() {
    const signers = [];
    const env = process.env.NODE_ENV || 'development';
    
    if (env === 'production') {
        // Production: Use AWS KMS
        if (CONFIG.aws.keyIds.length > 0) {
            for (const keyId of CONFIG.aws.keyIds) {
                signers.push(new AWSKMSSigner(keyId));
            }
            console.log(`Created ${signers.length} AWS KMS oracle signers`);
        }
        // Or use HashiCorp Vault
        else if (CONFIG.vault.token) {
            for (const keyName of CONFIG.vault.keyNames) {
                signers.push(new VaultTransitSigner(keyName));
            }
            console.log(`Created ${signers.length} Vault Transit oracle signers`);
        }
        
        if (signers.length < CONFIG.threshold) {
            throw new Error(
                `Production requires at least ${CONFIG.threshold} oracle signers. Found ${signers.length}`
            );
        }
    } else {
        // Development: Use local signers (DO NOT USE IN PRODUCTION)
        console.warn('⚠️  DEVELOPMENT MODE: Using local signers. NOT FOR PRODUCTION!');
        
        // Generate deterministic test keys
        const testKeys = [
            '0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
            '0xfedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210',
            '0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789',
        ];
        
        for (const key of testKeys) {
            signers.push(new LocalDevSigner(key));
        }
        console.log(`Created ${signers.length} local development oracle signers`);
    }
    
    return signers;
}

/**
 * Oracle Signing Service - Main API
 */
class OracleSigningService {
    constructor() {
        const signers = createOracleSigners();
        this.aggregator = new OracleSignatureAggregator(signers);
    }
    
    /**
     * Generate risk assessment and signatures for a swap
     */
    async assessAndSign(buyer, seller, amount, kycHash) {
        // In production, this would call ML model
        // For now, return a mock risk score
        const riskScore = await this._assessRisk(buyer, seller, amount);
        
        // Get multi-oracle signatures
        const signatureData = await this.aggregator.signSwapData(
            buyer,
            seller,
            amount,
            riskScore,
            kycHash
        );
        
        return {
            riskScore,
            modelVersion: 'DQN-v1.0',
            ...signatureData,
        };
    }
    
    /**
     * Mock risk assessment (replace with ML model in production)
     */
    async _assessRisk(buyer, seller, amount) {
        // Placeholder: In production, call ML model service
        // Example factors: transaction history, amount, counterparty risk
        const baseRisk = 200;
        const amountRisk = Math.min(amount / 1e18 * 10, 300); // 10 risk per ETH
        return Math.floor(baseRisk + amountRisk);
    }
    
    /**
     * Get oracle addresses for contract setup
     */
    async getOracleAddresses() {
        return this.aggregator.getOracleAddresses();
    }
    
    /**
     * Get service configuration
     */
    getConfig() {
        return {
            threshold: CONFIG.threshold,
            signatureValiditySeconds: CONFIG.SIGNATURE_VALIDITY_SECONDS,
            environment: process.env.NODE_ENV || 'development',
        };
    }
}

// Export for use
module.exports = {
    OracleSigningService,
    OracleSignatureAggregator,
    AWSKMSSigner,
    VaultTransitSigner,
    LocalDevSigner,
    NonceManager,
    CONFIG,
};

// CLI test
if (require.main === module) {
    (async () => {
        console.log('Testing Oracle Signing Service...\n');
        
        const service = new OracleSigningService();
        console.log('Config:', service.getConfig());
        
        const addresses = await service.getOracleAddresses();
        console.log('Oracle Addresses:', addresses);
        
        const testBuyer = '0x1234567890123456789012345678901234567890';
        const testSeller = '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd';
        const testAmount = ethers.parseEther('1.0');
        const testKycHash = ethers.keccak256(ethers.toUtf8Bytes('test-kyc'));
        
        console.log('\nGenerating signatures for test swap...');
        const result = await service.assessAndSign(testBuyer, testSeller, testAmount, testKycHash);
        
        console.log('\nResult:');
        console.log('  Risk Score:', result.riskScore);
        console.log('  Model Version:', result.modelVersion);
        console.log('  Nonce:', result.nonce);
        console.log('  Timestamp:', result.timestamp);
        console.log('  Expires At:', new Date(result.expiresAt * 1000).toISOString());
        console.log('  Signatures Count:', result.signatures.length);
        console.log('  Message Hash:', result.messageHash);
        
        console.log('\n✅ Oracle Signing Service test complete');
    })().catch(console.error);
}
