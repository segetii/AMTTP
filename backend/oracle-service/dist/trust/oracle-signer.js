/**
 * AMTTP Oracle Trust Model
 * Signed responses with (decision, score, explanation_hash, signature)
 * IPFS integration for immutable audit trail
 */
import { createHash, createSign, createVerify, generateKeyPairSync } from 'crypto';
import { ethers } from 'ethers';
// ═══════════════════════════════════════════════════════════════════════════
// ORACLE SIGNER CLASS
// ═══════════════════════════════════════════════════════════════════════════
export class OracleSigner {
    wallet = null;
    rsaKeyPair = null;
    signatureType;
    oracleContractAddress;
    chainId;
    responseTTL; // seconds
    constructor(config) {
        this.signatureType = config.signatureType || 'ECDSA';
        this.oracleContractAddress = config.oracleContractAddress || '0x0000000000000000000000000000000000000000';
        this.chainId = config.chainId || 31337;
        this.responseTTL = config.responseTTL || 300; // 5 minutes default
        if (this.signatureType === 'ECDSA') {
            const pk = config.privateKey || process.env.ORACLE_PRIVATE_KEY;
            if (pk) {
                this.wallet = new ethers.Wallet(pk);
            }
            else {
                // Generate ephemeral key for development
                this.wallet = ethers.Wallet.createRandom();
                console.warn('Using ephemeral oracle key. Set ORACLE_PRIVATE_KEY in production.');
            }
        }
        else if (this.signatureType === 'RSA') {
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
    getSignerAddress() {
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
    async signResponse(request, decision, explanation, policyVersion, modelVersion) {
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
    verifySignature(response) {
        const { signature, signerAddress, signatureType, ...payload } = response;
        if (signatureType === 'ECDSA') {
            return this.verifyECDSA(payload, signature, signerAddress);
        }
        else if (signatureType === 'RSA' && this.rsaKeyPair) {
            return this.verifyRSA(payload, signature);
        }
        return false;
    }
    async sign(payload) {
        const message = JSON.stringify(payload);
        const messageHash = createHash('sha256').update(message).digest('hex');
        if (this.signatureType === 'ECDSA' && this.wallet) {
            // EIP-191 style signing for on-chain verification
            return await this.wallet.signMessage(messageHash);
        }
        else if (this.signatureType === 'RSA' && this.rsaKeyPair) {
            const sign = createSign('SHA256');
            sign.update(message);
            return sign.sign(this.rsaKeyPair.privateKey, 'hex');
        }
        throw new Error('No signing method available');
    }
    verifyECDSA(payload, signature, expectedAddress) {
        try {
            const message = JSON.stringify(payload);
            const messageHash = createHash('sha256').update(message).digest('hex');
            const recoveredAddress = ethers.verifyMessage(messageHash, signature);
            return recoveredAddress.toLowerCase() === expectedAddress.toLowerCase();
        }
        catch {
            return false;
        }
    }
    verifyRSA(payload, signature) {
        if (!this.rsaKeyPair)
            return false;
        try {
            const verify = createVerify('SHA256');
            verify.update(JSON.stringify(payload));
            return verify.verify(this.rsaKeyPair.publicKey, signature, 'hex');
        }
        catch {
            return false;
        }
    }
    computeRequestId(request) {
        const data = `${request.from}:${request.to}:${request.amount}:${request.nonce}:${request.timestamp.toISOString()}`;
        return createHash('sha256').update(data).digest('hex').substring(0, 32);
    }
    computeExplanationHash(explanation) {
        return createHash('sha256').update(JSON.stringify(explanation)).digest('hex');
    }
    /**
     * Create EIP-712 typed data for on-chain verification
     */
    createTypedData(response) {
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
    decisionToUint(decision) {
        const mapping = { ALLOW: 0, REVIEW: 1, ESCALATE: 2, BLOCK: 3 };
        return mapping[decision];
    }
}
// ═══════════════════════════════════════════════════════════════════════════
// IPFS INTEGRATION (Mock for now, replace with actual IPFS client)
// ═══════════════════════════════════════════════════════════════════════════
export class ExplanationStore {
    storage = new Map();
    /**
     * Store explanation and return CID (mock IPFS)
     */
    async store(explanation) {
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
    async retrieve(cid) {
        return this.storage.get(cid) || null;
    }
    /**
     * Verify explanation matches hash
     */
    verify(explanation, expectedHash) {
        const actualHash = createHash('sha256').update(JSON.stringify(explanation)).digest('hex');
        return actualHash === expectedHash;
    }
}
// Singleton instances
let signerInstance = null;
let storeInstance = null;
export function getOracleSigner() {
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
export function getExplanationStore() {
    if (!storeInstance) {
        storeInstance = new ExplanationStore();
    }
    return storeInstance;
}
export default { OracleSigner, ExplanationStore, getOracleSigner, getExplanationStore };
