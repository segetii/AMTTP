#!/usr/bin/env node
/**
 * Test Production ZK Proof Generation with Poseidon Hashes
 * 
 * This script tests that the proof generator correctly computes
 * Poseidon hashes that match the circuit constraints.
 */

const { buildPoseidon } = require('circomlibjs');
const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');

const BUILD_DIR = path.join(__dirname, '..', '..', 'build');

async function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════════════╗
║      AMTTP zkNAF - Poseidon Hash & Proof Generation Test             ║
╠══════════════════════════════════════════════════════════════════════╣
║  Testing production proof generation with proper Poseidon hashes     ║
╚══════════════════════════════════════════════════════════════════════╝
`);

  // Initialize Poseidon
  console.log('Initializing Poseidon hasher...');
  const poseidon = await buildPoseidon();
  const F = poseidon.F;
  
  function poseidonHash(inputs) {
    const hash = poseidon(inputs.map(i => BigInt(i)));
    return F.toObject(hash);
  }
  
  console.log('✅ Poseidon hasher ready\n');

  let passed = 0;
  let failed = 0;

  // ═══════════════════════════════════════════════════════════════════════════
  // Test 1: Risk Range Proof
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('═'.repeat(70));
  console.log('TEST 1: Risk Range Proof');
  console.log('═'.repeat(70));
  
  try {
    const riskWasm = path.join(BUILD_DIR, 'risk', 'risk_range_proof_js', 'risk_range_proof.wasm');
    const riskZkey = path.join(BUILD_DIR, 'risk', 'risk_range_proof_final.zkey');
    const riskVkey = path.join(BUILD_DIR, 'risk', 'risk_range_proof_verification_key.json');
    
    if (!fs.existsSync(riskWasm)) {
      throw new Error('Risk circuit artifacts not found');
    }
    
    const vkey = JSON.parse(fs.readFileSync(riskVkey, 'utf8'));
    
    // Test inputs
    const riskScore = 35n;
    const userAddress = 123456789n;
    const scoreTimestamp = BigInt(Math.floor(Date.now() / 1000));
    const currentTimestamp = scoreTimestamp;
    const oracleSecret = 999888777666n;
    const minScore = 0n;
    const maxScore = 40n;
    
    // Compute Poseidon hashes (must match circuit constraints)
    const userAddressHash = poseidonHash([userAddress]);
    const signatureCommitment = poseidonHash([riskScore, userAddress, scoreTimestamp, oracleSecret]);
    
    console.log(`  Risk Score: ${riskScore}`);
    console.log(`  User Address: ${userAddress}`);
    console.log(`  User Address Hash (Poseidon): ${userAddressHash}`);
    console.log(`  Signature Commitment (Poseidon): ${signatureCommitment}`);
    console.log(`  Range: [${minScore}, ${maxScore}]`);
    
    const input = {
      signatureCommitment: signatureCommitment.toString(),
      userAddressHash: userAddressHash.toString(),
      minScore: minScore.toString(),
      maxScore: maxScore.toString(),
      currentTimestamp: currentTimestamp.toString(),
      riskScore: riskScore.toString(),
      userAddress: userAddress.toString(),
      scoreTimestamp: scoreTimestamp.toString(),
      oracleSecret: oracleSecret.toString(),
    };
    
    console.log('\n  Generating proof...');
    const startTime = Date.now();
    
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, riskWasm, riskZkey);
    
    console.log(`  ✅ Proof generated in ${Date.now() - startTime}ms`);
    console.log(`  Public Signals: ${publicSignals.length}`);
    
    // Verify proof
    console.log('  Verifying proof...');
    const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);
    
    if (isValid) {
      console.log('  ✅ PROOF VALID');
      passed++;
    } else {
      console.log('  ❌ PROOF INVALID');
      failed++;
    }
    
    // Export calldata
    const calldata = await snarkjs.groth16.exportSolidityCallData(proof, publicSignals);
    console.log(`  Solidity calldata: ${calldata.length} chars`);
    
  } catch (error) {
    console.log(`  ❌ ERROR: ${error.message}`);
    failed++;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Test 2: KYC Credential Proof
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '═'.repeat(70));
  console.log('TEST 2: KYC Credential Proof');
  console.log('═'.repeat(70));
  
  try {
    const kycWasm = path.join(BUILD_DIR, 'kyc', 'kyc_credential_js', 'kyc_credential.wasm');
    const kycZkey = path.join(BUILD_DIR, 'kyc', 'kyc_credential_final.zkey');
    const kycVkey = path.join(BUILD_DIR, 'kyc', 'kyc_credential_verification_key.json');
    
    if (!fs.existsSync(kycWasm)) {
      throw new Error('KYC circuit artifacts not found');
    }
    
    const vkey = JSON.parse(fs.readFileSync(kycVkey, 'utf8'));
    
    // Test inputs
    const userAddress = 987654321n;
    const currentTimestamp = BigInt(Math.floor(Date.now() / 1000));
    const birthTimestamp = currentTimestamp - (25n * 365n * 24n * 60n * 60n); // 25 years ago
    const kycCompletedAt = currentTimestamp - (30n * 24n * 60n * 60n); // 30 days ago
    const kycExpiresAt = currentTimestamp + (335n * 24n * 60n * 60n); // expires in 335 days
    const minAgeSeconds = 18n * 365n * 24n * 60n * 60n; // 18 years
    const isPEP = 0n;
    const providerSecret = 111222333444n;
    
    // Compute Poseidon hashes
    const userAddressHash = poseidonHash([userAddress]);
    const kycDataHash = poseidonHash([userAddress, kycCompletedAt, kycExpiresAt]);
    const providerSignature = poseidonHash([kycDataHash, providerSecret]);
    const providerCommitment = poseidonHash([kycDataHash, providerSecret, providerSignature]);
    
    console.log(`  User Address: ${userAddress}`);
    console.log(`  User Address Hash (Poseidon): ${userAddressHash}`);
    console.log(`  KYC Data Hash: ${kycDataHash}`);
    console.log(`  Provider Commitment: ${providerCommitment}`);
    console.log(`  Age: ~25 years (min: 18)`);
    
    const input = {
      providerCommitment: providerCommitment.toString(),
      userAddressHash: userAddressHash.toString(),
      currentTimestamp: currentTimestamp.toString(),
      minAgeSeconds: minAgeSeconds.toString(),
      userAddress: userAddress.toString(),
      birthTimestamp: birthTimestamp.toString(),
      kycCompletedAt: kycCompletedAt.toString(),
      kycExpiresAt: kycExpiresAt.toString(),
      isPEP: isPEP.toString(),
      providerSignature: providerSignature.toString(),
      providerSecret: providerSecret.toString(),
      kycDataHash: kycDataHash.toString(),
    };
    
    console.log('\n  Generating proof...');
    const startTime = Date.now();
    
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, kycWasm, kycZkey);
    
    console.log(`  ✅ Proof generated in ${Date.now() - startTime}ms`);
    console.log(`  Public Signals: ${publicSignals.length}`);
    
    // Verify proof
    console.log('  Verifying proof...');
    const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);
    
    if (isValid) {
      console.log('  ✅ PROOF VALID');
      passed++;
    } else {
      console.log('  ❌ PROOF INVALID');
      failed++;
    }
    
  } catch (error) {
    console.log(`  ❌ ERROR: ${error.message}`);
    failed++;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Summary
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '═'.repeat(70));
  console.log('SUMMARY');
  console.log('═'.repeat(70));
  console.log(`  Passed: ${passed}`);
  console.log(`  Failed: ${failed}`);
  
  if (failed === 0) {
    console.log('\n✅ ALL TESTS PASSED - Production ZK proofs working correctly!');
    process.exit(0);
  } else {
    console.log('\n❌ Some tests failed');
    process.exit(1);
  }
}

main().catch(console.error);
