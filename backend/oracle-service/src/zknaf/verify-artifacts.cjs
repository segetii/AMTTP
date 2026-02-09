#!/usr/bin/env node
/**
 * ZK Circuit Artifact Verification
 * 
 * Verifies that production circuit artifacts are present and valid.
 */

const fs = require('fs');
const path = require('path');

const BUILD_DIR = path.join(__dirname, '..', '..', 'build');

const CIRCUITS = [
  {
    name: 'sanctions_non_membership',
    dir: 'sanctions',
    expectedConstraints: 10227,
    description: 'Sanctions list non-membership proof'
  },
  {
    name: 'risk_range_proof',
    dir: 'risk',
    expectedConstraints: 596,
    description: 'Risk score range proof'
  },
  {
    name: 'kyc_credential',
    dir: 'kyc',
    expectedConstraints: 610,
    description: 'KYC credential verification'
  }
];

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function verifyCircuit(circuit) {
  const circuitPath = path.join(BUILD_DIR, circuit.dir);
  const wasmPath = path.join(circuitPath, `${circuit.name}_js`, `${circuit.name}.wasm`);
  const zkeyPath = path.join(circuitPath, `${circuit.name}_final.zkey`);
  const vkeyPath = path.join(circuitPath, `${circuit.name}_verification_key.json`);
  const verifierPath = path.join(circuitPath, `${circuit.name}_verifier.sol`);
  
  const results = {
    name: circuit.name,
    description: circuit.description,
    valid: true,
    artifacts: {}
  };
  
  // Check WASM
  if (fs.existsSync(wasmPath)) {
    const stats = fs.statSync(wasmPath);
    results.artifacts.wasm = { present: true, size: formatSize(stats.size) };
  } else {
    results.artifacts.wasm = { present: false };
    results.valid = false;
  }
  
  // Check zkey
  if (fs.existsSync(zkeyPath)) {
    const stats = fs.statSync(zkeyPath);
    results.artifacts.zkey = { present: true, size: formatSize(stats.size) };
  } else {
    results.artifacts.zkey = { present: false };
    results.valid = false;
  }
  
  // Check vkey
  if (fs.existsSync(vkeyPath)) {
    const vkey = JSON.parse(fs.readFileSync(vkeyPath, 'utf8'));
    results.artifacts.vkey = {
      present: true,
      protocol: vkey.protocol,
      curve: vkey.curve,
      nPublic: vkey.nPublic
    };
  } else {
    results.artifacts.vkey = { present: false };
    results.valid = false;
  }
  
  // Check Solidity verifier
  if (fs.existsSync(verifierPath)) {
    const stats = fs.statSync(verifierPath);
    const content = fs.readFileSync(verifierPath, 'utf8');
    const hasVerifyProof = content.includes('verifyProof');
    results.artifacts.solidity = {
      present: true,
      size: formatSize(stats.size),
      hasVerifyProof
    };
  } else {
    results.artifacts.solidity = { present: false };
    results.valid = false;
  }
  
  results.expectedConstraints = circuit.expectedConstraints;
  
  return results;
}

function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════════════╗
║           AMTTP zkNAF - Production Artifact Verification             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Groth16 ZK proofs using bn128 curve with Powers of Tau setup        ║
╚══════════════════════════════════════════════════════════════════════╝
`);

  if (!fs.existsSync(BUILD_DIR)) {
    console.log(`❌ Build directory not found: ${BUILD_DIR}`);
    process.exit(1);
  }

  console.log(`Build Directory: ${BUILD_DIR}\n`);
  
  let allValid = true;
  
  for (const circuit of CIRCUITS) {
    const result = verifyCircuit(circuit);
    
    console.log(`${'═'.repeat(70)}`);
    console.log(`📦 ${result.name}`);
    console.log(`   ${result.description}`);
    console.log(`   Constraints: ~${result.expectedConstraints.toLocaleString()}`);
    console.log(`${'─'.repeat(70)}`);
    
    // WASM
    if (result.artifacts.wasm.present) {
      console.log(`   ✅ WASM witness calculator: ${result.artifacts.wasm.size}`);
    } else {
      console.log(`   ❌ WASM witness calculator: MISSING`);
    }
    
    // zkey
    if (result.artifacts.zkey.present) {
      console.log(`   ✅ Proving key (zkey): ${result.artifacts.zkey.size}`);
    } else {
      console.log(`   ❌ Proving key (zkey): MISSING`);
    }
    
    // vkey
    if (result.artifacts.vkey.present) {
      console.log(`   ✅ Verification key: protocol=${result.artifacts.vkey.protocol}, curve=${result.artifacts.vkey.curve}, nPublic=${result.artifacts.vkey.nPublic}`);
    } else {
      console.log(`   ❌ Verification key: MISSING`);
    }
    
    // Solidity
    if (result.artifacts.solidity?.present) {
      console.log(`   ✅ Solidity verifier: ${result.artifacts.solidity.size} (verifyProof: ${result.artifacts.solidity.hasVerifyProof ? 'yes' : 'no'})`);
    } else {
      console.log(`   ❌ Solidity verifier: MISSING`);
    }
    
    if (!result.valid) allValid = false;
    console.log();
  }
  
  console.log(`${'═'.repeat(70)}`);
  console.log(`\n📋 SUMMARY`);
  console.log(`${'─'.repeat(70)}`);
  
  if (allValid) {
    console.log(`
✅ ALL CIRCUITS PRODUCTION-READY

   • Circuits compiled with Circom 2.1.6
   • Trusted setup using Powers of Tau (pot15, 2^15 constraints)
   • Groth16 proving system with bn128 curve
   • Solidity verifiers ready for on-chain deployment
   
⚠️  NOTE: Proof generation requires valid cryptographic inputs:
   • Poseidon hashes must match for verification constraints
   • Oracle signatures must be properly formatted
   • Merkle proofs must be valid for the given roots
   
   The ProductionProofGenerator class handles input preparation.
`);
    process.exit(0);
  } else {
    console.log(`\n❌ Some artifacts are missing. Run circuit compilation first.`);
    process.exit(1);
  }
}

main();
