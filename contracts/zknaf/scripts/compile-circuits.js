/**
 * Compile all zkNAF Circom circuits
 * Generates R1CS, WASM, and symbol files for each circuit
 */

const { execSync } = require('child_process');
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

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function compileCircuit(circuit) {
  const inputFile = path.join(CIRCUITS_DIR, circuit.file);
  const outputDir = path.join(BUILD_DIR, circuit.outputDir);
  
  ensureDir(outputDir);

  console.log(`\n🔧 Compiling ${circuit.name}...`);
  console.log(`   Input: ${inputFile}`);
  console.log(`   Output: ${outputDir}`);

  try {
    // Check if circom is installed
    try {
      execSync('circom --version', { stdio: 'pipe' });
    } catch {
      console.log('\n⚠️  Circom not found. Installing globally...');
      execSync('npm install -g circom@2.1.6', { stdio: 'inherit' });
    }

    // Compile the circuit
    const cmd = `circom "${inputFile}" --r1cs --wasm --sym -o "${outputDir}" -l "${path.join(__dirname, '..', 'node_modules')}"`;
    
    console.log(`   Running: circom ${circuit.file} --r1cs --wasm --sym`);
    
    execSync(cmd, { 
      stdio: 'inherit',
      cwd: CIRCUITS_DIR,
    });

    // Check outputs
    const r1csFile = path.join(outputDir, `${circuit.name}.r1cs`);
    const wasmDir = path.join(outputDir, `${circuit.name}_js`);

    if (fs.existsSync(r1csFile)) {
      const stats = fs.statSync(r1csFile);
      console.log(`   ✅ R1CS: ${(stats.size / 1024).toFixed(1)}KB`);
    }

    if (fs.existsSync(wasmDir)) {
      console.log(`   ✅ WASM: ${wasmDir}`);
    }

    return true;
  } catch (error) {
    console.error(`   ❌ Failed: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║         AMTTP zkNAF - Circuit Compilation                  ║');
  console.log('╚════════════════════════════════════════════════════════════╝');

  // Ensure circomlib is installed
  const circomlibPath = path.join(__dirname, '..', 'node_modules', 'circomlib');
  if (!fs.existsSync(circomlibPath)) {
    console.log('\n📦 Installing dependencies...');
    execSync('npm install', { 
      cwd: path.join(__dirname, '..'),
      stdio: 'inherit' 
    });
  }

  ensureDir(BUILD_DIR);

  let success = 0;
  let failed = 0;

  for (const circuit of CIRCUITS) {
    if (compileCircuit(circuit)) {
      success++;
    } else {
      failed++;
    }
  }

  console.log('\n════════════════════════════════════════════════════════════');
  console.log(`📊 Results: ${success} succeeded, ${failed} failed`);
  
  if (failed === 0) {
    console.log('\n✅ All circuits compiled successfully!');
    console.log('\n📋 Next steps:');
    console.log('   1. Run: npm run download:ptau  (if not done)');
    console.log('   2. Run: npm run setup:all');
    console.log('   3. Run: npm run test\n');
  } else {
    console.log('\n❌ Some circuits failed to compile.');
    console.log('   Check the error messages above.\n');
    process.exit(1);
  }
}

main();
