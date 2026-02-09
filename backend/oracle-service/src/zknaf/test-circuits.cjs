#!/usr/bin/env node
/**
 * ZK Proof Generation Test Script
 * 
 * Tests the production-ready ZK circuits by generating proofs
 * and verifying them using snarkjs.
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

const BUILD_DIR = path.join(__dirname, '..', '..', 'build');
const circuits = ['sanctions', 'risk', 'kyc'];

async function testCircuit(circuitName) {
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`Testing: ${circuitName}`);
  console.log(`${'═'.repeat(60)}`);
  
  const circuitDir = circuitName === 'sanctions' ? 'sanctions' 
    : circuitName === 'risk' ? 'risk' 
    : 'kyc';
  
  const fullName = circuitName === 'sanctions' ? 'sanctions_non_membership'
    : circuitName === 'risk' ? 'risk_range_proof'
    : 'kyc_credential';
  
  const wasmPath = path.join(BUILD_DIR, circuitDir, `${fullName}_js`, `${fullName}.wasm`);
  const zkeyPath = path.join(BUILD_DIR, circuitDir, `${fullName}_final.zkey`);
  const vkeyPath = path.join(BUILD_DIR, circuitDir, `${fullName}_verification_key.json`);
  
  // Check files exist
  if (!fs.existsSync(wasmPath)) {
    console.log(`  ❌ WASM not found: ${wasmPath}`);
    return false;
  }
  if (!fs.existsSync(zkeyPath)) {
    console.log(`  ❌ zkey not found: ${zkeyPath}`);
    return false;
  }
  if (!fs.existsSync(vkeyPath)) {
    console.log(`  ❌ vkey not found: ${vkeyPath}`);
    return false;
  }
  
  console.log(`  ✅ WASM: ${path.basename(wasmPath)}`);
  console.log(`  ✅ zkey: ${path.basename(zkeyPath)}`);
  console.log(`  ✅ vkey: ${path.basename(vkeyPath)}`);
  
  // Load verification key
  const vkey = JSON.parse(fs.readFileSync(vkeyPath, 'utf8'));
  console.log(`  ✅ Protocol: ${vkey.protocol}`);
  console.log(`  ✅ Curve: ${vkey.curve}`);
  
  // Generate sample input based on circuit type
  // Signal names must match exactly what's defined in the .circom files
  let input;
  const now = Math.floor(Date.now() / 1000);
  
  if (circuitName === 'sanctions') {
    // SanctionsNonMembership(20) circuit signals:
    // Public: sanctionsListRoot, currentTimestamp  
    // Private: addressToCheck, leftNeighbor, rightNeighbor, leftProof[20], rightProof[20], leftPathIndices[20], rightPathIndices[20]
    input = {
      sanctionsListRoot: "12345678901234567890",
      currentTimestamp: now.toString(),
      addressToCheck: "15000000000000000000",
      leftNeighbor: "10000000000000000000",
      rightNeighbor: "20000000000000000000",
      leftProof: new Array(20).fill("0"),
      rightProof: new Array(20).fill("0"),
      leftPathIndices: new Array(20).fill("0"),
      rightPathIndices: new Array(20).fill("0"),
    };
  } else if (circuitName === 'risk') {
    // RiskScoreRangeProof circuit signals:
    // Public: signatureCommitment, userAddressHash, minScore, maxScore, currentTimestamp
    // Private: riskScore, userAddress, scoreTimestamp, oracleSecret
    const userAddress = "123456789";
    const riskScore = "35";
    const scoreTimestamp = now.toString();
    const oracleSecret = "999888777666";
    
    // Compute commitment (simplified - in production would use proper poseidon)
    const signatureCommitment = "12345678901234567890123456789012";
    const userAddressHash = "98765432109876543210987654321098";
    
    input = {
      signatureCommitment: signatureCommitment,
      userAddressHash: userAddressHash,
      minScore: "0",
      maxScore: "40",
      currentTimestamp: now.toString(),
      riskScore: riskScore,
      userAddress: userAddress,
      scoreTimestamp: scoreTimestamp,
      oracleSecret: oracleSecret,
    };
  } else {
    // KYCCredentialProof circuit signals:
    // Public: providerCommitment, userAddressHash, currentTimestamp, minAgeSeconds
    // Private: userAddress, birthTimestamp, kycCompletedAt, kycExpiresAt, isPEP, providerSignature, providerSecret, kycDataHash
    const userAddress = "123456789";
    const birthTimestamp = (now - 25 * 365 * 24 * 60 * 60).toString(); // 25 years ago
    const kycCompletedAt = (now - 30 * 24 * 60 * 60).toString(); // 30 days ago
    const kycExpiresAt = (now + 335 * 24 * 60 * 60).toString(); // expires in 335 days
    
    input = {
      providerCommitment: "11111111111111111111111111111111",
      userAddressHash: "22222222222222222222222222222222",
      currentTimestamp: now.toString(),
      minAgeSeconds: (18 * 365 * 24 * 60 * 60).toString(),
      userAddress: userAddress,
      birthTimestamp: birthTimestamp,
      kycCompletedAt: kycCompletedAt,
      kycExpiresAt: kycExpiresAt,
      isPEP: "0",
      providerSignature: "33333333333333333333333333333333",
      providerSecret: "44444444444444444444444444444444",
      kycDataHash: "55555555555555555555555555555555",
    };
  }
  
  console.log(`\n  📊 Generating proof...`);
  const startTime = Date.now();
  
  try {
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
      input,
      wasmPath,
      zkeyPath
    );
    
    const proofTime = Date.now() - startTime;
    console.log(`  ✅ Proof generated in ${proofTime}ms`);
    console.log(`  📌 Public signals: ${publicSignals.length}`);
    
    // Verify proof
    console.log(`\n  🔍 Verifying proof...`);
    const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);
    
    if (isValid) {
      console.log(`  ✅ Proof VALID`);
    } else {
      console.log(`  ❌ Proof INVALID`);
      return false;
    }
    
    // Export calldata for on-chain verification
    const calldata = await snarkjs.groth16.exportSolidityCallData(proof, publicSignals);
    console.log(`  📄 Solidity calldata ready (${calldata.length} chars)`);
    
    return true;
  } catch (error) {
    console.log(`  ❌ Error: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════════╗
║      AMTTP zkNAF - Production Circuit Test                       ║
╠══════════════════════════════════════════════════════════════════╣
║  Testing compiled circuits with sample inputs                    ║
╚══════════════════════════════════════════════════════════════════╝
`);

  console.log(`Build directory: ${BUILD_DIR}`);
  
  // Check if build directory exists
  if (!fs.existsSync(BUILD_DIR)) {
    console.log(`\n❌ Build directory not found: ${BUILD_DIR}`);
    console.log(`Run 'docker run --rm -v "$(pwd)/build:/circuits/build" zknaf-circuit-builder' first.`);
    process.exit(1);
  }
  
  const results = {};
  
  for (const circuit of circuits) {
    results[circuit] = await testCircuit(circuit);
  }
  
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`SUMMARY`);
  console.log(`${'═'.repeat(60)}`);
  
  let allPassed = true;
  for (const [circuit, passed] of Object.entries(results)) {
    console.log(`  ${passed ? '✅' : '❌'} ${circuit}: ${passed ? 'PASSED' : 'FAILED'}`);
    if (!passed) allPassed = false;
  }
  
  console.log(`\n${allPassed ? '🎉 All tests passed!' : '⚠️  Some tests failed'}`);
  process.exit(allPassed ? 0 : 1);
}

main().catch(console.error);
