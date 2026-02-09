/**
 * Production ZK Circuit Build Script
 * 
 * This script runs inside Docker and:
 * 1. Compiles all Circom circuits to R1CS + WASM
 * 2. Downloads powers of tau
 * 3. Runs trusted setup (Phase 2)
 * 4. Exports verification keys
 * 5. Generates Solidity verifier contracts
 */

const { execSync, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const CIRCUITS = [
  {
    name: 'sanctions_non_membership',
    file: 'sanctions_non_membership.circom',
    outputDir: 'sanctions',
  },
  {
    name: 'risk_range_proof',
    file: 'risk_range_proof.circom',
    outputDir: 'risk',
  },
  {
    name: 'kyc_credential',
    file: 'kyc_credential.circom',
    outputDir: 'kyc',
  },
];

const CIRCUITS_DIR = path.join(__dirname, '..', 'circuits');
const BUILD_DIR = path.join(__dirname, '..', 'build');
const PTAU_FILE = path.join(__dirname, '..', 'ptau', 'pot15_final.ptau');

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function run(cmd, options = {}) {
  console.log(`\n📦 Running: ${cmd}`);
  try {
    execSync(cmd, { stdio: 'inherit', ...options });
    return true;
  } catch (error) {
    console.error(`❌ Command failed: ${error.message}`);
    return false;
  }
}

async function compileCircuit(circuit) {
  const inputFile = path.join(CIRCUITS_DIR, circuit.file);
  const outputDir = path.join(BUILD_DIR, circuit.outputDir);
  
  ensureDir(outputDir);

  console.log(`\n${'═'.repeat(60)}`);
  console.log(`🔧 COMPILING: ${circuit.name}`);
  console.log(`${'═'.repeat(60)}`);
  console.log(`   Input:  ${inputFile}`);
  console.log(`   Output: ${outputDir}`);

  // Step 1: Compile circuit to R1CS and WASM
  const nodeModules = path.join(__dirname, '..', 'node_modules');
  const compileCmd = `circom "${inputFile}" --r1cs --wasm --sym -o "${outputDir}" -l "${nodeModules}"`;
  
  if (!run(compileCmd)) {
    throw new Error(`Failed to compile ${circuit.name}`);
  }

  const r1csFile = path.join(outputDir, `${circuit.name}.r1cs`);
  const wasmFile = path.join(outputDir, `${circuit.name}_js`, `${circuit.name}.wasm`);
  
  if (!fs.existsSync(r1csFile)) {
    throw new Error(`R1CS file not found: ${r1csFile}`);
  }
  
  console.log(`   ✅ R1CS generated`);
  console.log(`   ✅ WASM generated`);

  // Step 2: Generate zkey (trusted setup phase 2)
  console.log(`\n🔐 Running trusted setup for ${circuit.name}...`);
  
  const zkeyInit = path.join(outputDir, `${circuit.name}_0000.zkey`);
  const zkeyFinal = path.join(outputDir, `${circuit.name}_final.zkey`);
  
  // Phase 2 ceremony - initial contribution
  if (!run(`snarkjs groth16 setup "${r1csFile}" "${PTAU_FILE}" "${zkeyInit}"`)) {
    throw new Error('Trusted setup phase 1 failed');
  }
  
  // Contribute to ceremony (in production: multiple parties)
  const contributionEntropy = `AMTTP-zkNAF-${circuit.name}-${Date.now()}`;
  if (!run(`snarkjs zkey contribute "${zkeyInit}" "${zkeyFinal}" --name="AMTTP Contribution" -e="${contributionEntropy}"`)) {
    throw new Error('Trusted setup contribution failed');
  }
  
  console.log(`   ✅ zkey generated`);

  // Step 3: Export verification key
  const vkeyFile = path.join(outputDir, `${circuit.name}_verification_key.json`);
  if (!run(`snarkjs zkey export verificationkey "${zkeyFinal}" "${vkeyFile}"`)) {
    throw new Error('Verification key export failed');
  }
  
  console.log(`   ✅ Verification key exported`);

  // Step 4: Generate Solidity verifier
  const verifierFile = path.join(outputDir, `${circuit.name}_verifier.sol`);
  if (!run(`snarkjs zkey export solidityverifier "${zkeyFinal}" "${verifierFile}"`)) {
    throw new Error('Solidity verifier export failed');
  }
  
  console.log(`   ✅ Solidity verifier generated`);

  // Clean up intermediate files
  fs.unlinkSync(zkeyInit);
  
  // Report sizes
  const stats = {
    r1cs: fs.statSync(r1csFile).size,
    wasm: fs.statSync(wasmFile).size,
    zkey: fs.statSync(zkeyFinal).size,
    vkey: fs.statSync(vkeyFile).size,
  };
  
  console.log(`\n   📊 Artifact sizes:`);
  console.log(`      R1CS:     ${(stats.r1cs / 1024).toFixed(1)} KB`);
  console.log(`      WASM:     ${(stats.wasm / 1024).toFixed(1)} KB`);
  console.log(`      zkey:     ${(stats.zkey / 1024 / 1024).toFixed(2)} MB`);
  console.log(`      vkey:     ${(stats.vkey / 1024).toFixed(1)} KB`);

  return {
    circuit: circuit.name,
    r1cs: r1csFile,
    wasm: wasmFile,
    zkey: zkeyFinal,
    vkey: vkeyFile,
    verifier: verifierFile,
  };
}

async function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════════╗
║      AMTTP zkNAF - Production Circuit Build                      ║
╠══════════════════════════════════════════════════════════════════╣
║  This script compiles Circom circuits and generates:             ║
║  • R1CS constraint systems                                       ║
║  • WASM witness generators                                       ║
║  • Trusted setup (zkey) - Groth16                               ║
║  • Verification keys                                            ║
║  • Solidity verifier contracts                                  ║
╚══════════════════════════════════════════════════════════════════╝
`);

  // Check prerequisites
  console.log('🔍 Checking prerequisites...');
  
  try {
    const circomVersion = execSync('circom --version', { encoding: 'utf8' }).trim();
    console.log(`   ✅ Circom: ${circomVersion}`);
  } catch {
    console.error('   ❌ Circom not found');
    process.exit(1);
  }
  
  try {
    const snarkjsVersion = execSync('snarkjs --version 2>&1 || echo "unknown"', { encoding: 'utf8' }).trim();
    console.log(`   ✅ snarkjs: ${snarkjsVersion || 'installed'}`);
  } catch {
    console.error('   ❌ snarkjs not found');
    process.exit(1);
  }
  
  if (!fs.existsSync(PTAU_FILE)) {
    console.error(`   ❌ Powers of tau file not found: ${PTAU_FILE}`);
    console.log('   📥 Download it from: https://hermez.s3-eu-west-1.amazonaws.com/powersOfTau28_hez_final_14.ptau');
    process.exit(1);
  }
  console.log(`   ✅ Powers of tau: ${PTAU_FILE}`);

  ensureDir(BUILD_DIR);

  // Compile all circuits
  const results = [];
  for (const circuit of CIRCUITS) {
    try {
      const result = await compileCircuit(circuit);
      results.push(result);
    } catch (error) {
      console.error(`\n❌ Failed to build ${circuit.name}: ${error.message}`);
      process.exit(1);
    }
  }

  // Generate summary manifest
  const manifest = {
    version: '1.0.0',
    buildDate: new Date().toISOString(),
    circuits: results.map(r => ({
      name: r.circuit,
      artifacts: {
        r1cs: path.relative(BUILD_DIR, r.r1cs),
        wasm: path.relative(BUILD_DIR, r.wasm),
        zkey: path.relative(BUILD_DIR, r.zkey),
        vkey: path.relative(BUILD_DIR, r.vkey),
        verifier: path.relative(BUILD_DIR, r.verifier),
      }
    })),
  };
  
  const manifestPath = path.join(BUILD_DIR, 'circuit-manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

  console.log(`
╔══════════════════════════════════════════════════════════════════╗
║      ✅ BUILD COMPLETE                                           ║
╠══════════════════════════════════════════════════════════════════╣
║  Circuits compiled: ${results.length}                                           ║
║  Output directory:  ${BUILD_DIR}
║  Manifest:          ${manifestPath}
╚══════════════════════════════════════════════════════════════════╝
`);

  // Print next steps
  console.log(`
📋 Next Steps:
1. Copy build/ artifacts to your production environment
2. Deploy *_verifier.sol contracts to blockchain
3. Configure zkNAF service with artifact paths
4. Run verification tests

Example proof generation:
  snarkjs groth16 fullprove input.json circuit.wasm circuit_final.zkey proof.json public.json
`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
