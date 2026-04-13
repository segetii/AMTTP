/**
 * Continue Base Sepolia deployment from step 3 (after PM + PE already deployed)
 * Usage: npx hardhat run scripts/deploy-l2-base-continue.cjs --network baseSepolia
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

const LZ_CHAIN_ID = 10245; // Base Sepolia LZ ID

// Already deployed in first run:
const EXISTING = {
  policyManager: '0x520393A448543FF55f02ddA1218881a8E5851CEc',
  policyEngine: '0xc8d887665411ecB4760435fb3d20586C1111bc37',
};

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   AMTTP Base Sepolia — Continue Deploy       ║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance:  ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  const addresses = { ...EXISTING };

  // Link PM → PE (may have failed last time)
  console.log('── Link PolicyManager → PolicyEngine ──');
  try {
    const pm = await hre.ethers.getContractAt('AMTTPPolicyManager', EXISTING.policyManager);
    const tx = await pm.setPolicyEngine(EXISTING.policyEngine);
    await tx.wait();
    console.log(`  ✅ Linked`);
  } catch (e) {
    console.log(`  ⚠️  Already linked or error: ${e.message.slice(0, 80)}`);
  }
  await wait(5000);

  // 3. MockLayerZero + CrossChain
  console.log('── CrossChain ──');
  const MockLZ = await hre.ethers.getContractFactory('MockLayerZeroEndpoint');
  const lz = await MockLZ.deploy(LZ_CHAIN_ID);
  await lz.waitForDeployment();
  addresses.mockLayerZero = await lz.getAddress();
  console.log(`  ✅ MockLZ: ${addresses.mockLayerZero}`);
  await wait(5000);

  const CrossChain = await hre.ethers.getContractFactory('contracts/AMTTPCrossChain.sol:AMTTPCrossChain');
  const cc = await hre.upgrades.deployProxy(CrossChain, [addresses.mockLayerZero, LZ_CHAIN_ID, EXISTING.policyEngine], { initializer: 'initialize', kind: 'uups' });
  await cc.waitForDeployment();
  addresses.crossChain = await cc.getAddress();
  console.log(`  ✅ CrossChain: ${addresses.crossChain}`);
  await wait(5000);

  // 4. RiskRouter
  console.log('── RiskRouter ──');
  const RiskRouter = await hre.ethers.getContractFactory('AMTTPRiskRouter');
  const rr = await hre.upgrades.deployProxy(RiskRouter, [deployer.address, 'DQN-v2.0-baseSepolia'], { initializer: 'initialize', kind: 'uups' });
  await rr.waitForDeployment();
  addresses.riskRouter = await rr.getAddress();
  console.log(`  ✅ ${addresses.riskRouter}`);
  await wait(5000);

  // 5. ZkNAF Verifiers
  console.log('── ZkNAF Verifiers ──');
  const sv = await (await hre.ethers.getContractFactory('contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier')).deploy();
  await sv.waitForDeployment();
  addresses.sanctionsVerifier = await sv.getAddress();
  console.log(`  ✅ Sanctions: ${addresses.sanctionsVerifier}`);
  await wait(5000);

  const rv = await (await hre.ethers.getContractFactory('contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier')).deploy();
  await rv.waitForDeployment();
  addresses.riskVerifier = await rv.getAddress();
  console.log(`  ✅ Risk: ${addresses.riskVerifier}`);
  await wait(5000);

  const kv = await (await hre.ethers.getContractFactory('contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier')).deploy();
  await kv.waitForDeployment();
  addresses.kycVerifier = await kv.getAddress();
  console.log(`  ✅ KYC: ${addresses.kycVerifier}`);
  await wait(5000);

  // 6. ZkNAF Router
  console.log('── ZkNAF Router ──');
  const zkr = await (await hre.ethers.getContractFactory('ZkNAFVerifierRouter')).deploy(addresses.sanctionsVerifier, addresses.riskVerifier, addresses.kycVerifier);
  await zkr.waitForDeployment();
  addresses.zkNAFRouter = await zkr.getAddress();
  console.log(`  ✅ ${addresses.zkNAFRouter}`);

  // Save
  const deployment = { network, deployer: deployer.address, lzChainId: LZ_CHAIN_ID, deployedAt: new Date().toISOString(), contracts: addresses };
  const deployDir = path.join(__dirname, '..', 'deployments');
  if (!fs.existsSync(deployDir)) fs.mkdirSync(deployDir, { recursive: true });
  const file = path.join(deployDir, `l2-baseSepolia-${Date.now()}.json`);
  fs.writeFileSync(file, JSON.stringify(deployment, null, 2));

  const remaining = await hre.ethers.provider.getBalance(deployer.address);

  console.log(`
╔══════════════════════════════════════════════════════════╗
║   BASE SEPOLIA DEPLOYMENT COMPLETE                       
╠══════════════════════════════════════════════════════════╣
  PolicyManager:      ${addresses.policyManager}
  PolicyEngine:       ${addresses.policyEngine}
  CrossChain:         ${addresses.crossChain}
  RiskRouter:         ${addresses.riskRouter}
  SanctionsVerifier:  ${addresses.sanctionsVerifier}
  RiskVerifier:       ${addresses.riskVerifier}
  KYCVerifier:        ${addresses.kycVerifier}
  ZkNAFRouter:        ${addresses.zkNAFRouter}
  
  Balance remaining:  ${hre.ethers.formatEther(remaining)} ETH
  Saved: ${file}
╚══════════════════════════════════════════════════════════╝
`);
}

main().catch(console.error);
