/**
 * Generate Example Proofs for Testing
 * 
 * Creates sample proofs using test inputs for integration testing
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// Poseidon hash placeholder - in production, use circomlibjs
function poseidonHash(inputs) {
    // Simplified hash for testing - replace with actual Poseidon in production
    const hash = crypto.createHash('sha256');
    inputs.forEach(input => hash.update(Buffer.from(input.toString())));
    return BigInt('0x' + hash.digest('hex')) % BigInt('21888242871839275222246405745257275088548364400416034343698204186575808495617');
}

async function generateSanctionsProof() {
    console.log('\n🔐 Generating Sanctions Non-Membership Proof...');
    
    const buildDir = path.join(__dirname, '..', 'build', 'sanctions_non_membership');
    const wasmPath = path.join(buildDir, 'sanctions_non_membership_js', 'sanctions_non_membership.wasm');
    const zkeyPath = path.join(buildDir, 'sanctions_non_membership_final.zkey');
    
    if (!fs.existsSync(wasmPath) || !fs.existsSync(zkeyPath)) {
        console.log('⚠️  Build artifacts not found. Run npm run build first.');
        return null;
    }
    
    // Generate test inputs
    // User address hash (simulated)
    const userAddressHash = poseidonHash(['0x1234567890abcdef1234567890abcdef12345678']);
    
    // Generate a simple Merkle tree for testing (depth 20)
    const treeDepth = 20;
    const siblings = [];
    const pathIndices = [];
    
    // Generate random siblings (in production, these come from the actual tree)
    for (let i = 0; i < treeDepth; i++) {
        siblings.push(poseidonHash([Math.floor(Math.random() * 1000000).toString()]).toString());
        pathIndices.push(Math.random() > 0.5 ? 1 : 0);
    }
    
    // Calculate expected root (simplified)
    let currentHash = userAddressHash;
    for (let i = 0; i < treeDepth; i++) {
        if (pathIndices[i] === 0) {
            currentHash = poseidonHash([currentHash.toString(), siblings[i]]);
        } else {
            currentHash = poseidonHash([siblings[i], currentHash.toString()]);
        }
    }
    
    const input = {
        userAddressHash: userAddressHash.toString(),
        sanctionsRoot: currentHash.toString(),
        pathElements: siblings,
        pathIndices: pathIndices,
        timestamp: Math.floor(Date.now() / 1000)
    };
    
    const inputPath = path.join(__dirname, '..', 'test', 'inputs', 'sanctions_input.json');
    fs.mkdirSync(path.dirname(inputPath), { recursive: true });
    fs.writeFileSync(inputPath, JSON.stringify(input, null, 2));
    
    try {
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            wasmPath,
            zkeyPath
        );
        
        const proofPath = path.join(__dirname, '..', 'test', 'proofs', 'sanctions_proof.json');
        const signalsPath = path.join(__dirname, '..', 'test', 'proofs', 'sanctions_public.json');
        
        fs.mkdirSync(path.dirname(proofPath), { recursive: true });
        fs.writeFileSync(proofPath, JSON.stringify(proof, null, 2));
        fs.writeFileSync(signalsPath, JSON.stringify(publicSignals, null, 2));
        
        console.log('   ✅ Proof generated:', proofPath);
        console.log('   ✅ Public signals:', signalsPath);
        
        return { proof, publicSignals };
    } catch (err) {
        console.error('   ❌ Error:', err.message);
        return null;
    }
}

async function generateRiskRangeProof() {
    console.log('\n🔐 Generating Risk Range Proof...');
    
    const buildDir = path.join(__dirname, '..', 'build', 'risk_range_proof');
    const wasmPath = path.join(buildDir, 'risk_range_proof_js', 'risk_range_proof.wasm');
    const zkeyPath = path.join(buildDir, 'risk_range_proof_final.zkey');
    
    if (!fs.existsSync(wasmPath) || !fs.existsSync(zkeyPath)) {
        console.log('⚠️  Build artifacts not found. Run npm run build first.');
        return null;
    }
    
    // Test with LOW risk (score 25, range 0-50)
    const input = {
        riskScore: "25",
        rangeMin: "0",
        rangeMax: "50",
        oracleCommitment: poseidonHash(['oracle_commitment_seed']).toString(),
        timestamp: Math.floor(Date.now() / 1000)
    };
    
    const inputPath = path.join(__dirname, '..', 'test', 'inputs', 'risk_range_input.json');
    fs.mkdirSync(path.dirname(inputPath), { recursive: true });
    fs.writeFileSync(inputPath, JSON.stringify(input, null, 2));
    
    try {
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            wasmPath,
            zkeyPath
        );
        
        const proofPath = path.join(__dirname, '..', 'test', 'proofs', 'risk_range_proof.json');
        const signalsPath = path.join(__dirname, '..', 'test', 'proofs', 'risk_range_public.json');
        
        fs.mkdirSync(path.dirname(proofPath), { recursive: true });
        fs.writeFileSync(proofPath, JSON.stringify(proof, null, 2));
        fs.writeFileSync(signalsPath, JSON.stringify(publicSignals, null, 2));
        
        console.log('   ✅ Proof generated:', proofPath);
        console.log('   ✅ Public signals:', signalsPath);
        
        return { proof, publicSignals };
    } catch (err) {
        console.error('   ❌ Error:', err.message);
        return null;
    }
}

async function generateKYCProof() {
    console.log('\n🔐 Generating KYC Credential Proof...');
    
    const buildDir = path.join(__dirname, '..', 'build', 'kyc_credential');
    const wasmPath = path.join(buildDir, 'kyc_credential_js', 'kyc_credential.wasm');
    const zkeyPath = path.join(buildDir, 'kyc_credential_final.zkey');
    
    if (!fs.existsSync(wasmPath) || !fs.existsSync(zkeyPath)) {
        console.log('⚠️  Build artifacts not found. Run npm run build first.');
        return null;
    }
    
    // Simulate EdDSA signature (in production, use actual signature)
    const providerPublicKey = [
        poseidonHash(['provider_pubkey_x']).toString(),
        poseidonHash(['provider_pubkey_y']).toString()
    ];
    
    const signatureR8 = [
        poseidonHash(['sig_r8_x']).toString(),
        poseidonHash(['sig_r8_y']).toString()
    ];
    
    const signatureS = poseidonHash(['sig_s']).toString();
    
    const currentTime = Math.floor(Date.now() / 1000);
    const oneYearFromNow = currentTime + 365 * 24 * 60 * 60;
    
    const input = {
        kycLevel: "3", // Full KYC
        expirationDate: oneYearFromNow.toString(),
        providerPublicKey: providerPublicKey,
        signatureR8: signatureR8,
        signatureS: signatureS,
        userIdentityHash: poseidonHash(['user_identity_data']).toString(),
        currentTimestamp: currentTime.toString()
    };
    
    const inputPath = path.join(__dirname, '..', 'test', 'inputs', 'kyc_credential_input.json');
    fs.mkdirSync(path.dirname(inputPath), { recursive: true });
    fs.writeFileSync(inputPath, JSON.stringify(input, null, 2));
    
    try {
        const { proof, publicSignals } = await snarkjs.groth16.fullProve(
            input,
            wasmPath,
            zkeyPath
        );
        
        const proofPath = path.join(__dirname, '..', 'test', 'proofs', 'kyc_credential_proof.json');
        const signalsPath = path.join(__dirname, '..', 'test', 'proofs', 'kyc_credential_public.json');
        
        fs.mkdirSync(path.dirname(proofPath), { recursive: true });
        fs.writeFileSync(proofPath, JSON.stringify(proof, null, 2));
        fs.writeFileSync(signalsPath, JSON.stringify(publicSignals, null, 2));
        
        console.log('   ✅ Proof generated:', proofPath);
        console.log('   ✅ Public signals:', signalsPath);
        
        return { proof, publicSignals };
    } catch (err) {
        console.error('   ❌ Error:', err.message);
        return null;
    }
}

async function verifyAllProofs() {
    console.log('\n🔍 Verifying Generated Proofs...');
    
    const circuits = [
        'sanctions_non_membership',
        'risk_range_proof',
        'kyc_credential'
    ];
    
    for (const circuit of circuits) {
        const proofPath = path.join(__dirname, '..', 'test', 'proofs', `${circuit.replace('_non_membership', '').replace('_proof', '')}_proof.json`);
        const signalsPath = path.join(__dirname, '..', 'test', 'proofs', `${circuit.replace('_non_membership', '').replace('_proof', '')}_public.json`);
        const vkeyPath = path.join(__dirname, '..', 'generated', `${circuit}_vkey.json`);
        
        if (!fs.existsSync(proofPath) || !fs.existsSync(vkeyPath)) {
            console.log(`   ⚠️  Skipping ${circuit} - files not found`);
            continue;
        }
        
        try {
            const proof = JSON.parse(fs.readFileSync(proofPath, 'utf8'));
            const publicSignals = JSON.parse(fs.readFileSync(signalsPath, 'utf8'));
            const vkey = JSON.parse(fs.readFileSync(vkeyPath, 'utf8'));
            
            const valid = await snarkjs.groth16.verify(vkey, publicSignals, proof);
            
            if (valid) {
                console.log(`   ✅ ${circuit}: VALID`);
            } else {
                console.log(`   ❌ ${circuit}: INVALID`);
            }
        } catch (err) {
            console.error(`   ❌ ${circuit}: Error - ${err.message}`);
        }
    }
}

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('                 zkNAF Proof Generation');
    console.log('═══════════════════════════════════════════════════════════════');
    
    await generateSanctionsProof();
    await generateRiskRangeProof();
    await generateKYCProof();
    
    await verifyAllProofs();
    
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                 Generation Complete');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('\nTest files in contracts/zknaf/test/');
    console.log('- inputs/  : Input JSON files');
    console.log('- proofs/  : Generated proofs and public signals');
}

main().catch(console.error);
