/**
 * Quick test: Generate a real Groth16 sanctions non-membership proof
 * using snarkjs and the compiled Circom circuit artifacts.
 * 
 * Builds a sparse Poseidon Merkle tree (only hashing along the path,
 * not all 2^20 leaves) so it runs fast while still producing valid proofs.
 */
import * as snarkjs from 'snarkjs';
import { buildPoseidon } from 'circomlibjs';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BUILD_DIR = path.join(__dirname, '..', '..', 'build');
const LEVELS = 20;

/**
 * Build a sparse Merkle tree with only a few leaves populated.
 * Computes empty subtree hashes once, then only hashes along populated paths.
 */
async function buildSparseTree(poseidon, leaves) {
  const F = poseidon.F;
  
  // Pre-compute empty subtree hashes: emptyHash[0] = hash of empty leaf (0)
  // emptyHash[i] = hash(emptyHash[i-1], emptyHash[i-1])
  const emptyHash = new Array(LEVELS + 1);
  emptyHash[0] = BigInt(0);
  for (let i = 1; i <= LEVELS; i++) {
    const h = poseidon([emptyHash[i - 1], emptyHash[i - 1]]);
    emptyHash[i] = F.toObject(h);
  }
  
  // Place leaves at their indices (sorted by value for the sanctions circuit)
  // For this test, leaf[0] = leftNeighbor, leaf[1] = rightNeighbor
  const tree = new Map(); // tree[level][index] = hash
  const setNode = (level, index, value) => {
    const key = `${level}-${index}`;
    tree.set(key, value);
  };
  const getNode = (level, index) => {
    const key = `${level}-${index}`;
    return tree.has(key) ? tree.get(key) : emptyHash[level];
  };
  
  // Set leaves (level 0)
  for (const [idx, val] of leaves.entries()) {
    setNode(0, idx, val);
  }
  
  // Build tree bottom-up, only computing nodes on paths to our leaves
  const leafIndices = [...leaves.keys()];
  let currentIndices = new Set(leafIndices);
  
  for (let level = 0; level < LEVELS; level++) {
    const parentIndices = new Set();
    for (const idx of currentIndices) {
      const parentIdx = Math.floor(idx / 2);
      parentIndices.add(parentIdx);
      
      const leftChild = getNode(level, parentIdx * 2);
      const rightChild = getNode(level, parentIdx * 2 + 1);
      const h = poseidon([leftChild, rightChild]);
      setNode(level + 1, parentIdx, F.toObject(h));
    }
    currentIndices = parentIndices;
  }
  
  const root = getNode(LEVELS, 0);
  
  // Extract Merkle proofs for specific leaf indices
  function getProof(leafIdx) {
    const elements = [];
    const indices = [];
    let idx = leafIdx;
    for (let level = 0; level < LEVELS; level++) {
      const siblingIdx = idx % 2 === 0 ? idx + 1 : idx - 1;
      elements.push(getNode(level, siblingIdx).toString());
      indices.push(idx % 2);
      idx = Math.floor(idx / 2);
    }
    return { elements, indices };
  }
  
  return { root: root.toString(), getProof, emptyHash };
}

async function testSanctionsProof() {
  console.log('=== AMTTP zkNAF Real Proof Generation Test ===\n');

  // 1. Check artifacts exist
  const wasmPath = path.join(BUILD_DIR, 'sanctions', 'sanctions_non_membership_js', 'sanctions_non_membership.wasm');
  const zkeyPath = path.join(BUILD_DIR, 'sanctions', 'sanctions_non_membership_final.zkey');
  const vkeyPath = path.join(BUILD_DIR, 'sanctions', 'sanctions_non_membership_verification_key.json');

  for (const [label, p] of [['WASM', wasmPath], ['ZKEY', zkeyPath], ['VKEY', vkeyPath]]) {
    if (!fs.existsSync(p)) {
      console.error(`[FAIL] ${label} not found: ${p}`);
      process.exit(1);
    }
    const size = fs.statSync(p).size;
    console.log(`[OK] ${label}: ${(size / 1024).toFixed(1)} KB`);
  }

  // 2. Build sparse Poseidon Merkle tree
  console.log('\nBuilding sparse Poseidon Merkle tree (depth=20)...');
  const poseidon = await buildPoseidon();
  
  // Sanctioned addresses (sorted): place at leaf indices 0 and 1
  const leftNeighbor = BigInt(100);   // leaf index 0
  const rightNeighbor = BigInt(900);  // leaf index 1
  const addressToCheck = BigInt(500);  // NOT in the tree (100 < 500 < 900)

  const { root, getProof } = await buildSparseTree(poseidon, new Map([
    [0, leftNeighbor],
    [1, rightNeighbor],
  ]));

  const leftProof = getProof(0);
  const rightProof = getProof(1);
  
  console.log(`Merkle root: ${root.substring(0, 30)}...`);

  // 3. Construct circuit inputs
  const currentTimestamp = Math.floor(Date.now() / 1000);
  const input = {
    sanctionsListRoot: root,
    currentTimestamp: currentTimestamp.toString(),
    addressToCheck: addressToCheck.toString(),
    leftNeighbor: leftNeighbor.toString(),
    rightNeighbor: rightNeighbor.toString(),
    leftProof: leftProof.elements,
    rightProof: rightProof.elements,
    leftPathIndices: leftProof.indices,
    rightPathIndices: rightProof.indices,
  };

  // 4. Generate the real Groth16 proof
  console.log('Generating Groth16 proof with snarkjs.groth16.fullProve()...');
  const startTime = Date.now();

  try {
    const { proof, publicSignals } = await snarkjs.groth16.fullProve(
      input,
      wasmPath,
      zkeyPath
    );

    const elapsed = Date.now() - startTime;
    console.log(`\n[OK] Proof generated in ${elapsed}ms`);
    console.log(`     pi_a: [${proof.pi_a[0].substring(0, 20)}..., ${proof.pi_a[1].substring(0, 20)}...]`);
    console.log(`     pi_b: [[${proof.pi_b[0][0].substring(0, 15)}...], ...]`);
    console.log(`     pi_c: [${proof.pi_c[0].substring(0, 20)}..., ${proof.pi_c[1].substring(0, 20)}...]`);
    console.log(`     Public signals: ${publicSignals.length} values`);
    for (let i = 0; i < publicSignals.length; i++) {
      console.log(`       [${i}]: ${publicSignals[i]}`);
    }

    // 5. Verify the proof locally
    console.log('\nVerifying proof with snarkjs.groth16.verify()...');
    const vkey = JSON.parse(fs.readFileSync(vkeyPath, 'utf-8'));
    const isValid = await snarkjs.groth16.verify(vkey, publicSignals, proof);
    console.log(`[${isValid ? 'OK' : 'FAIL'}] Proof verification: ${isValid}`);

    // 6. Export Solidity calldata
    const calldata = await snarkjs.groth16.exportSolidityCallData(proof, publicSignals);
    console.log(`\n[OK] Solidity calldata generated (${calldata.length} chars)`);
    console.log(`     First 120 chars: ${calldata.substring(0, 120)}...`);

    if (isValid) {
      console.log('\n========================================');
      console.log('  ALL TESTS PASSED');
      console.log('========================================');
      console.log('zkNAF generates REAL Groth16 proofs:');
      console.log('  - snarkjs.groth16.fullProve() with compiled Circom WASM');
      console.log('  - Poseidon Merkle tree with depth 20 (supports 1M addresses)');
      console.log('  - Proof verified locally with verification key');
      console.log('  - Solidity calldata ready for on-chain verification');
      console.log('  - No demo stubs. Real zero-knowledge proofs on BN128 curve.');
    }

  } catch (error) {
    console.error(`[FAIL] Proof generation failed: ${error.message}`);
    console.error(error.stack);
    process.exit(1);
  }
}

testSanctionsProof().catch(console.error);
