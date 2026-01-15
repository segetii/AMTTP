/**
 * AMTTP zkNAF - Trusted Setup (Phase 2)
 * 
 * This script performs the circuit-specific trusted setup for Groth16.
 * For production, run with multiple contributors.
 * 
 * Usage:
 *   node trusted-setup.js           # Setup all circuits
 *   node trusted-setup.js sanctions # Setup specific circuit
 */

const snarkjs = require('snarkjs');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CIRCUITS = {
  sanctions: {
    name: 'sanctions_non_membership',
    r1cs: 'build/sanctions/sanctions_non_membership.r1cs',
  },
  risk: {
    name: 'risk_range_proof',
    r1cs: 'build/risk/risk_range_proof.r1cs',
  },
  kyc: {
    name: 'kyc_credential',
    r1cs: 'build/kyc/kyc_credential.r1cs',
  },
};

const BASE_DIR = path.join(__dirname, '..');
const SETUP_DIR = path.join(BASE_DIR, 'trusted-setup');
const PTAU_FILE = path.join(SETUP_DIR, 'pot16_final.ptau');

// Number of contributions (for demo, use 1; for production, use many)
const NUM_CONTRIBUTIONS = 3;

async function setupCircuit(circuitKey) {
  const circuit = CIRCUITS[circuitKey];
  if (!circuit) {
    throw new Error(`Unknown circuit: ${circuitKey}`);
  }

  console.log(`\n🔐 Setting up ${circuit.name}...`);

  const r1csPath = path.join(BASE_DIR, circuit.r1cs);
  const zkeyPath = path.join(SETUP_DIR, `${circuit.name}.zkey`);
  const vkeyPath = path.join(SETUP_DIR, `${circuit.name}_verification_key.json`);

  // Check R1CS exists
  if (!fs.existsSync(r1csPath)) {
    throw new Error(`R1CS not found: ${r1csPath}\nRun 'npm run compile:all' first.`);
  }

  // Check PTAU exists
  if (!fs.existsSync(PTAU_FILE)) {
    throw new Error(`PTAU not found: ${PTAU_FILE}\nRun 'npm run download:ptau' first.`);
  }

  // Get circuit info
  console.log('   📊 Reading circuit info...');
  const r1csInfo = await snarkjs.r1cs.info(r1csPath);
  console.log(`   Constraints: ${r1csInfo.nConstraints}`);
  console.log(`   Private inputs: ${r1csInfo.nPrvInputs}`);
  console.log(`   Public inputs: ${r1csInfo.nPubInputs}`);
  console.log(`   Outputs: ${r1csInfo.nOutputs}`);

  // Phase 2: Initial setup
  console.log('\n   🔧 Phase 2: Initial setup...');
  const zkey0Path = path.join(SETUP_DIR, `${circuit.name}_0000.zkey`);
  
  await snarkjs.zKey.newZKey(r1csPath, PTAU_FILE, zkey0Path);
  console.log('   ✅ Initial zkey created');

  // Contributions
  let currentZkey = zkey0Path;
  for (let i = 1; i <= NUM_CONTRIBUTIONS; i++) {
    const newZkey = path.join(SETUP_DIR, `${circuit.name}_${String(i).padStart(4, '0')}.zkey`);
    const contributorName = `AMTTP_Contributor_${i}`;
    const entropy = crypto.randomBytes(64).toString('hex');

    console.log(`\n   🎲 Contribution ${i}/${NUM_CONTRIBUTIONS}: ${contributorName}`);
    
    await snarkjs.zKey.contribute(currentZkey, newZkey, contributorName, entropy);
    
    console.log(`   ✅ Contribution ${i} complete`);

    // Clean up previous zkey (except initial for verification)
    if (i > 1) {
      fs.unlinkSync(currentZkey);
    }
    currentZkey = newZkey;
  }

  // Rename final zkey
  fs.renameSync(currentZkey, zkeyPath);
  console.log(`\n   📦 Final zkey: ${zkeyPath}`);

  // Export verification key
  console.log('   📤 Exporting verification key...');
  const vkey = await snarkjs.zKey.exportVerificationKey(zkeyPath);
  fs.writeFileSync(vkeyPath, JSON.stringify(vkey, null, 2));
  console.log(`   ✅ Verification key: ${vkeyPath}`);

  // Verify the setup
  console.log('   🔍 Verifying setup...');
  const isValid = await snarkjs.zKey.verifyFromR1cs(r1csPath, PTAU_FILE, zkeyPath);
  
  if (isValid) {
    console.log('   ✅ Setup verified successfully!');
  } else {
    console.log('   ❌ Setup verification failed!');
    throw new Error('Setup verification failed');
  }

  // Cleanup intermediate files
  const zkey0 = path.join(SETUP_DIR, `${circuit.name}_0000.zkey`);
  if (fs.existsSync(zkey0)) {
    fs.unlinkSync(zkey0);
  }

  return {
    circuit: circuit.name,
    constraints: r1csInfo.nConstraints,
    zkeyPath,
    vkeyPath,
  };
}

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║         AMTTP zkNAF - Trusted Setup (Phase 2)              ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  // Ensure setup directory exists
  if (!fs.existsSync(SETUP_DIR)) {
    fs.mkdirSync(SETUP_DIR, { recursive: true });
  }

  // Determine which circuits to setup
  const targetCircuit = process.argv[2];
  const circuitsToSetup = targetCircuit 
    ? [targetCircuit] 
    : Object.keys(CIRCUITS);

  console.log(`\n📋 Circuits to setup: ${circuitsToSetup.join(', ')}`);
  console.log(`📊 Contributions per circuit: ${NUM_CONTRIBUTIONS}`);

  const results = [];

  for (const circuitKey of circuitsToSetup) {
    try {
      const result = await setupCircuit(circuitKey);
      results.push({ ...result, status: 'success' });
    } catch (error) {
      console.error(`\n❌ Failed to setup ${circuitKey}: ${error.message}`);
      results.push({ circuit: circuitKey, status: 'failed', error: error.message });
    }
  }

  // Summary
  console.log('\n════════════════════════════════════════════════════════════');
  console.log('📊 Setup Summary:');
  console.log('────────────────────────────────────────────────────────────');
  
  for (const result of results) {
    if (result.status === 'success') {
      console.log(`   ✅ ${result.circuit}: ${result.constraints} constraints`);
    } else {
      console.log(`   ❌ ${result.circuit}: ${result.error}`);
    }
  }

  const successCount = results.filter(r => r.status === 'success').length;
  const failCount = results.filter(r => r.status === 'failed').length;

  console.log('────────────────────────────────────────────────────────────');
  console.log(`   Total: ${successCount} succeeded, ${failCount} failed`);

  if (failCount === 0) {
    console.log('\n✅ All setups complete!');
    console.log('\n📋 Next steps:');
    console.log('   1. Run: npm run test');
    console.log('   2. Run: npm run export:verifier');
    console.log('   3. Deploy the verifier contract\n');
  } else {
    console.log('\n❌ Some setups failed. Check errors above.\n');
    process.exit(1);
  }
}

main().catch(console.error);
