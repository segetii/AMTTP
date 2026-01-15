/**
 * AMTTP Simple Oracle Signing Service (Self-Managed Key)
 *
 * WARNING: This is a development/PoC solution. For production, migrate to HSM-backed keys (AWS KMS, Vault, etc).
 *
 * Features:
 * - Stores private key encrypted on disk (AES-256-GCM)
 * - Signs messages for multi-oracle consensus
 * - Nonce management to prevent replay
 * - Easy migration path to HSM or Vault
 *
 * Migration Note: Replace this with HSM integration for production security.
 */

const { ethers } = require('ethers');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const ENCRYPTED_KEY_PATH = process.env.ORACLE_KEY_FILE || path.join(__dirname, 'oracle-key.enc');
const ENCRYPTION_PASSWORD = process.env.ORACLE_KEY_PASSWORD || 'changeme-please';

/**
 * Encrypt a private key using AES-256-GCM
 */
function encryptPrivateKey(privateKey, password) {
    const iv = crypto.randomBytes(12);
    const key = crypto.scryptSync(password, 'amttp-salt', 32);
    const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
    const encrypted = Buffer.concat([
        cipher.update(privateKey.replace(/^0x/, ''), 'hex'),
        cipher.final()
    ]);
    const tag = cipher.getAuthTag();
    return Buffer.concat([iv, tag, encrypted]).toString('base64');
}

/**
 * Decrypt a private key using AES-256-GCM
 */
function decryptPrivateKey(encrypted, password) {
    const data = Buffer.from(encrypted, 'base64');
    const iv = data.slice(0, 12);
    const tag = data.slice(12, 28);
    const encryptedKey = data.slice(28);
    const key = crypto.scryptSync(password, 'amttp-salt', 32);
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(tag);
    const decrypted = Buffer.concat([
        decipher.update(encryptedKey),
        decipher.final()
    ]);
    return '0x' + decrypted.toString('hex');
}

/**
 * Load or generate an encrypted private key
 */
function loadOrCreateKey() {
    if (fs.existsSync(ENCRYPTED_KEY_PATH)) {
        const encrypted = fs.readFileSync(ENCRYPTED_KEY_PATH, 'utf8');
        return decryptPrivateKey(encrypted, ENCRYPTION_PASSWORD);
    } else {
        const wallet = ethers.Wallet.createRandom();
        const encrypted = encryptPrivateKey(wallet.privateKey, ENCRYPTION_PASSWORD);
        fs.writeFileSync(ENCRYPTED_KEY_PATH, encrypted, 'utf8');
        console.log('🔑 New oracle key generated and encrypted at', ENCRYPTED_KEY_PATH);
        return wallet.privateKey;
    }
}

const privateKey = loadOrCreateKey();
const wallet = new ethers.Wallet(privateKey);

/**
 * Nonce Manager (in-memory for demo)
 */
class NonceManager {
    constructor() {
        this.usedNonces = new Set();
        this.counter = 0;
    }
    getNextNonce() {
        this.counter++;
        return this.counter;
    }
    markUsed(nonce) {
        this.usedNonces.add(nonce);
    }
    isUsed(nonce) {
        return this.usedNonces.has(nonce);
    }
}

const nonceManager = new NonceManager();

/**
 * Sign swap data for AMTTPCoreSecure
 */
async function signSwapData(buyer, seller, amount, riskScore, kycHash) {
    const nonce = nonceManager.getNextNonce();
    const timestamp = Math.floor(Date.now() / 1000);
    const messageHash = ethers.keccak256(
        ethers.solidityPacked(
            ['address', 'address', 'uint256', 'uint256', 'bytes32', 'uint256', 'uint256'],
            [buyer, seller, amount, riskScore, kycHash, nonce, timestamp]
        )
    );
    const signature = await wallet.signMessage(ethers.getBytes(messageHash));
    nonceManager.markUsed(nonce);
    return {
        signature,
        nonce,
        timestamp,
        messageHash,
        address: wallet.address,
    };
}

if (require.main === module) {
    (async () => {
        console.log('AMTTP Simple Oracle Signing Service');
        console.log('Oracle Address:', wallet.address);
        console.log('Encrypted key file:', ENCRYPTED_KEY_PATH);
        console.log('\nNOTE: For production, migrate to HSM-backed keys (AWS KMS, Vault, etc).');

        // Example usage
        const buyer = '0x1234567890123456789012345678901234567890';
        const seller = '0xabcdefabcdefabcdefabcdefabcdefabcdefabcd';
        const amount = ethers.parseEther('1.0');
        const kycHash = ethers.keccak256(ethers.toUtf8Bytes('test-kyc'));
        const riskScore = 200;
        const result = await signSwapData(buyer, seller, amount, riskScore, kycHash);
        console.log('\nSignature Result:', result);
    })();
}

module.exports = {
    signSwapData,
    wallet,
    nonceManager,
};
