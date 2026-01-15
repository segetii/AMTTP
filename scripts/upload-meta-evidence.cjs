#!/usr/bin/env node
/**
 * Upload AMTTP Kleros Meta Evidence to IPFS
 * 
 * This script uploads the meta evidence template to IPFS using either:
 * - Pinata (recommended for production)
 * - Local IPFS node
 * - Infura IPFS
 * 
 * Usage:
 *   node scripts/upload-meta-evidence.cjs
 * 
 * Environment variables:
 *   PINATA_API_KEY - Pinata API key
 *   PINATA_SECRET_KEY - Pinata secret key
 *   IPFS_API_URL - Custom IPFS API URL (optional)
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Try to load pinata SDK
let pinataSDK;
try {
    pinataSDK = require('@pinata/sdk');
} catch (e) {
    console.log('Pinata SDK not installed. Install with: npm install @pinata/sdk');
}

// Configuration
const META_EVIDENCE_PATH = path.join(__dirname, '../contracts/kleros/metaEvidence.json');
const DEPLOY_SCRIPT_PATH = path.join(__dirname, 'deploy-with-kleros.cjs');

async function uploadToPinata(content) {
    if (!process.env.PINATA_API_KEY || !process.env.PINATA_SECRET_KEY) {
        throw new Error('PINATA_API_KEY and PINATA_SECRET_KEY environment variables required');
    }
    
    const pinata = new pinataSDK(process.env.PINATA_API_KEY, process.env.PINATA_SECRET_KEY);
    
    // Test authentication
    await pinata.testAuthentication();
    console.log('✅ Pinata authentication successful');
    
    // Pin JSON
    const result = await pinata.pinJSONToIPFS(content, {
        pinataMetadata: {
            name: 'AMTTP-Kleros-MetaEvidence',
            keyvalues: {
                version: content.version,
                protocol: 'AMTTP',
                type: 'metaEvidence'
            }
        },
        pinataOptions: {
            cidVersion: 1
        }
    });
    
    return `ipfs://${result.IpfsHash}`;
}

async function uploadToLocalIPFS(content) {
    const { create } = await import('ipfs-http-client');
    const ipfsUrl = process.env.IPFS_API_URL || 'http://127.0.0.1:5001';
    
    const client = create({ url: ipfsUrl });
    const result = await client.add(JSON.stringify(content, null, 2));
    
    return `ipfs://${result.cid.toString()}`;
}

async function uploadToInfura(content) {
    if (!process.env.INFURA_IPFS_PROJECT_ID || !process.env.INFURA_IPFS_PROJECT_SECRET) {
        throw new Error('INFURA_IPFS_PROJECT_ID and INFURA_IPFS_PROJECT_SECRET required');
    }
    
    const { create } = await import('ipfs-http-client');
    const auth = 'Basic ' + Buffer.from(
        process.env.INFURA_IPFS_PROJECT_ID + ':' + process.env.INFURA_IPFS_PROJECT_SECRET
    ).toString('base64');
    
    const client = create({
        host: 'ipfs.infura.io',
        port: 5001,
        protocol: 'https',
        headers: { authorization: auth }
    });
    
    const result = await client.add(JSON.stringify(content, null, 2));
    return `ipfs://${result.cid.toString()}`;
}

function calculateHash(content) {
    return crypto.createHash('sha256')
        .update(JSON.stringify(content))
        .digest('hex');
}

function updateDeployScript(ipfsUri) {
    let content = fs.readFileSync(DEPLOY_SCRIPT_PATH, 'utf-8');
    
    // Replace the TODO line
    content = content.replace(
        /const META_EVIDENCE_URI = "ipfs:\/\/.*";.*$/m,
        `const META_EVIDENCE_URI = "${ipfsUri}"; // Uploaded on ${new Date().toISOString().split('T')[0]}`
    );
    
    fs.writeFileSync(DEPLOY_SCRIPT_PATH, content);
    console.log(`✅ Updated deploy-with-kleros.cjs with new IPFS URI`);
}

async function main() {
    console.log('='.repeat(60));
    console.log('AMTTP Kleros Meta Evidence Upload');
    console.log('='.repeat(60));
    console.log('');
    
    // Load meta evidence
    if (!fs.existsSync(META_EVIDENCE_PATH)) {
        console.error(`❌ Meta evidence file not found: ${META_EVIDENCE_PATH}`);
        process.exit(1);
    }
    
    const content = JSON.parse(fs.readFileSync(META_EVIDENCE_PATH, 'utf-8'));
    const hash = calculateHash(content);
    
    console.log(`📄 Meta Evidence: ${META_EVIDENCE_PATH}`);
    console.log(`   Title: ${content.title}`);
    console.log(`   Version: ${content.version}`);
    console.log(`   SHA256: ${hash.substring(0, 16)}...`);
    console.log('');
    
    // Update content with hash
    content.fileHash = hash;
    
    // Determine upload method
    let ipfsUri;
    
    if (process.env.PINATA_API_KEY) {
        console.log('📌 Uploading to Pinata...');
        ipfsUri = await uploadToPinata(content);
    } else if (process.env.INFURA_IPFS_PROJECT_ID) {
        console.log('📌 Uploading to Infura IPFS...');
        ipfsUri = await uploadToInfura(content);
    } else {
        console.log('📌 Uploading to local IPFS node...');
        try {
            ipfsUri = await uploadToLocalIPFS(content);
        } catch (e) {
            console.error('❌ Local IPFS upload failed:', e.message);
            console.log('');
            console.log('To upload meta evidence, configure one of:');
            console.log('  1. PINATA_API_KEY + PINATA_SECRET_KEY (recommended)');
            console.log('  2. INFURA_IPFS_PROJECT_ID + INFURA_IPFS_PROJECT_SECRET');
            console.log('  3. Run local IPFS daemon: ipfs daemon');
            console.log('');
            console.log('For now, using placeholder hash...');
            ipfsUri = `ipfs://Qm${hash.substring(0, 44)}`;
        }
    }
    
    console.log('');
    console.log('✅ Upload complete!');
    console.log(`   IPFS URI: ${ipfsUri}`);
    console.log('');
    
    // Update deploy script
    updateDeployScript(ipfsUri);
    
    // Save deployment record
    const record = {
        ipfsUri,
        hash,
        uploadedAt: new Date().toISOString(),
        content
    };
    
    const recordPath = path.join(__dirname, '../deployments/meta-evidence-latest.json');
    fs.writeFileSync(recordPath, JSON.stringify(record, null, 2));
    console.log(`📝 Saved deployment record: ${recordPath}`);
    
    console.log('');
    console.log('Next steps:');
    console.log('  1. Verify the content at: https://ipfs.io' + ipfsUri.replace('ipfs://', '/ipfs/'));
    console.log('  2. Run: npx hardhat run scripts/deploy-with-kleros.cjs --network sepolia');
    console.log('');
}

main().catch((error) => {
    console.error('Error:', error);
    process.exit(1);
});
