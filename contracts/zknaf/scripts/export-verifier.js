/**
 * Export Solidity Verifier from zKey
 * 
 * Generates a Groth16 verifier contract from the proving key
 * This can be used to compare against or replace AMTTPzkNAF.sol
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

const CIRCUITS = [
    'sanctions_non_membership',
    'risk_range_proof',
    'kyc_credential'
];

async function exportVerifier(circuitName) {
    console.log(`\n📤 Exporting verifier for ${circuitName}...`);
    
    const buildDir = path.join(__dirname, '..', 'build', circuitName);
    const outputDir = path.join(__dirname, '..', 'generated');
    
    if (!fs.existsSync(outputDir)) {
        fs.mkdirSync(outputDir, { recursive: true });
    }
    
    const zkeyPath = path.join(buildDir, `${circuitName}_final.zkey`);
    
    if (!fs.existsSync(zkeyPath)) {
        console.log(`⚠️  zKey not found for ${circuitName}, skipping...`);
        return null;
    }
    
    // Export verification key (JSON)
    const vkey = await snarkjs.zKey.exportVerificationKey(zkeyPath);
    const vkeyPath = path.join(outputDir, `${circuitName}_vkey.json`);
    fs.writeFileSync(vkeyPath, JSON.stringify(vkey, null, 2));
    console.log(`   ✅ Verification key exported: ${vkeyPath}`);
    
    // Export Solidity verifier
    const solidityCode = await snarkjs.zKey.exportSolidityVerifier(zkeyPath, {
        groth16: fs.readFileSync(
            path.join(require.resolve('snarkjs'), '..', 'templates', 'verifier_groth16.sol.ejs'),
            'utf8'
        )
    });
    
    // Rename contract to be circuit-specific
    const renamedCode = solidityCode
        .replace('contract Groth16Verifier', `contract ${toPascalCase(circuitName)}Verifier`)
        .replace('Pairing library', `Pairing library for ${circuitName}`);
    
    const solidityPath = path.join(outputDir, `${toPascalCase(circuitName)}Verifier.sol`);
    fs.writeFileSync(solidityPath, renamedCode);
    console.log(`   ✅ Solidity verifier exported: ${solidityPath}`);
    
    return { vkey, solidityPath };
}

function toPascalCase(str) {
    return str
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join('');
}

async function exportVerificationConstants() {
    console.log('\n📝 Generating verification constants for AMTTPzkNAF.sol...');
    
    const outputDir = path.join(__dirname, '..', 'generated');
    const constants = {};
    
    for (const circuit of CIRCUITS) {
        const vkeyPath = path.join(outputDir, `${circuit}_vkey.json`);
        
        if (!fs.existsSync(vkeyPath)) {
            console.log(`⚠️  Verification key not found for ${circuit}`);
            continue;
        }
        
        const vkey = JSON.parse(fs.readFileSync(vkeyPath, 'utf8'));
        
        // Extract the key components needed for on-chain verification
        constants[circuit] = {
            alpha1: vkey.vk_alpha_1,
            beta2: vkey.vk_beta_2,
            gamma2: vkey.vk_gamma_2,
            delta2: vkey.vk_delta_2,
            ic: vkey.IC
        };
    }
    
    // Generate a Solidity snippet for updating verification keys
    let soliditySnippet = `
// SPDX-License-Identifier: MIT
// Auto-generated verification key constants for AMTTPzkNAF.sol
// Generated at: ${new Date().toISOString()}

/*
 * Copy these constants into AMTTPzkNAF.sol's initialize() function
 * or use setVerificationKey() to update them after deployment
 */

`;
    
    for (const [circuit, vkey] of Object.entries(constants)) {
        const proofType = getProofType(circuit);
        
        soliditySnippet += `
// ${circuit.toUpperCase()} (ProofType.${proofType})
// verifyingKeys[ProofType.${proofType}] = VerifyingKey({
//     alpha1: [${formatG1Point(vkey.alpha1)}],
//     beta2: [${formatG2Point(vkey.beta2)}],
//     gamma2: [${formatG2Point(vkey.gamma2)}],
//     delta2: [${formatG2Point(vkey.delta2)}],
//     ic: [${formatICPoints(vkey.ic)}]
// });

`;
    }
    
    const snippetPath = path.join(outputDir, 'verification_constants.sol');
    fs.writeFileSync(snippetPath, soliditySnippet);
    console.log(`   ✅ Verification constants snippet: ${snippetPath}`);
    
    // Also save as JSON for SDK usage
    const jsonPath = path.join(outputDir, 'verification_keys.json');
    fs.writeFileSync(jsonPath, JSON.stringify(constants, null, 2));
    console.log(`   ✅ Verification keys JSON: ${jsonPath}`);
}

function getProofType(circuit) {
    const mapping = {
        'sanctions_non_membership': 'SANCTIONS',
        'risk_range_proof': 'RISK_LOW', // Default, actual type in proof
        'kyc_credential': 'KYC_VERIFIED'
    };
    return mapping[circuit] || 'UNKNOWN';
}

function formatG1Point(point) {
    return `uint256(${point[0]}), uint256(${point[1]})`;
}

function formatG2Point(point) {
    return `[uint256(${point[0][0]}), uint256(${point[0][1]})], [uint256(${point[1][0]}), uint256(${point[1][1]})]`;
}

function formatICPoints(ic) {
    return ic.map(point => `[uint256(${point[0]}), uint256(${point[1]})]`).join(', ');
}

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('                    zkNAF Verifier Export');
    console.log('═══════════════════════════════════════════════════════════════');
    
    // Export individual verifiers
    for (const circuit of CIRCUITS) {
        try {
            await exportVerifier(circuit);
        } catch (err) {
            console.error(`❌ Error exporting ${circuit}:`, err.message);
        }
    }
    
    // Generate constants for main contract
    try {
        await exportVerificationConstants();
    } catch (err) {
        console.error('❌ Error generating constants:', err.message);
    }
    
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Export Complete');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('\nGenerated files in contracts/zknaf/generated/');
    console.log('- *_vkey.json         : Verification keys for SDK');
    console.log('- *Verifier.sol       : Standalone Solidity verifiers');
    console.log('- verification_constants.sol : Constants for AMTTPzkNAF.sol');
    console.log('- verification_keys.json     : All keys in JSON format');
}

main().catch(console.error);
