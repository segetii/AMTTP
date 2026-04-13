/**
 * AMTTP L2 Deployment — Base Sepolia / Arbitrum Sepolia
 * 
 * Deploys the core contracts needed for cross-chain:
 *   CrossChain, PolicyEngine, RiskRouter, ZkNAF verifiers
 * 
 * Usage: npx hardhat run scripts/deploy-l2.cjs --network baseSepolia
 *        npx hardhat run scripts/deploy-l2.cjs --network arbitrumSepolia
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

// LayerZero chain IDs (uint16)
const LZ_CHAIN_IDS = {
  sepolia: 10161,
  baseSepolia: 10245,
  arbitrumSepolia: 10231,
  localhost: 31337,
};

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  const lzChainId = LZ_CHAIN_IDS[network] || 10161;

  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   AMTTP L2 Deployment — ${network.padEnd(20)}║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Network:  ${network} (LZ chain ID: ${lzChainId})`);
  console.log(`Balance:  ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  const addresses = {};
  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  // 1. PolicyManager (UUPS)
  console.log('── PolicyManager ──');
  const PolicyManager = await hre.ethers.getContractFactory('AMTTPPolicyManager');
  const pm = await hre.upgrades.deployProxy(PolicyManager, [], { initializer: 'initialize', kind: 'uups' });
  await pm.waitForDeployment();
  addresses.policyManager = await pm.getAddress();
  console.log(`  ✅ ${addresses.policyManager}`);
  await wait(5000);

  // 2. PolicyEngine (UUPS)
  console.log('── PolicyEngine ──');
  const PolicyEngine = await hre.ethers.getContractFactory('contracts/AMTTPPolicyEngine.sol:AMTTPPolicyEngine');
  const pe = await hre.upgrades.deployProxy(PolicyEngine, [hre.ethers.ZeroAddress, deployer.address], { initializer: 'initialize', kind: 'uups' });
  await pe.waitForDeployment();
  addresses.policyEngine = await pe.getAddress();
  console.log(`  ✅ ${addresses.policyEngine}`);
  await wait(5000);

  // Link PM → PE
  const linkTx = await pm.setPolicyEngine(addresses.policyEngine);
  await linkTx.wait();
  console.log(`  ✅ PolicyManager → PolicyEngine linked`);
  await wait(3000);

  // 3. MockLayerZero + CrossChain (UUPS)
  console.log('── CrossChain ──');
  const MockLZ = await hre.ethers.getContractFactory('MockLayerZeroEndpoint');
  const lz = await MockLZ.deploy(lzChainId);
  await lz.waitForDeployment();
  addresses.mockLayerZero = await lz.getAddress();
  console.log(`  ✅ MockLZ: ${addresses.mockLayerZero}`);

  const CrossChain = await hre.ethers.getContractFactory('contracts/AMTTPCrossChain.sol:AMTTPCrossChain');
  const cc = await hre.upgrades.deployProxy(CrossChain, [addresses.mockLayerZero, lzChainId, addresses.policyEngine], { initializer: 'initialize', kind: 'uups' });
  await cc.waitForDeployment();
  addresses.crossChain = await cc.getAddress();
  console.log(`  ✅ CrossChain: ${addresses.crossChain}`);

  // 4. RiskRouter (UUPS)
  console.log('── RiskRouter ──');
  const RiskRouter = await hre.ethers.getContractFactory('AMTTPRiskRouter');
  const rr = await hre.upgrades.deployProxy(RiskRouter, [deployer.address, `DQN-v2.0-${network}`], { initializer: 'initialize', kind: 'uups' });
  await rr.waitForDeployment();
  addresses.riskRouter = await rr.getAddress();
  console.log(`  ✅ ${addresses.riskRouter}`);

  // 5. ZkNAF Verifiers
  console.log('── ZkNAF Verifiers ──');
  const sv = await (await hre.ethers.getContractFactory('contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier')).deploy();
  await sv.waitForDeployment();
  addresses.sanctionsVerifier = await sv.getAddress();
  console.log(`  ✅ Sanctions: ${addresses.sanctionsVerifier}`);

  const rv = await (await hre.ethers.getContractFactory('contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier')).deploy();
  await rv.waitForDeployment();
  addresses.riskVerifier = await rv.getAddress();
  console.log(`  ✅ Risk: ${addresses.riskVerifier}`);

  const kv = await (await hre.ethers.getContractFactory('contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier')).deploy();
  await kv.waitForDeployment();
  addresses.kycVerifier = await kv.getAddress();
  console.log(`  ✅ KYC: ${addresses.kycVerifier}`);

  // 6. ZkNAF Router
  console.log('── ZkNAF Router ──');
  const zkr = await (await hre.ethers.getContractFactory('ZkNAFVerifierRouter')).deploy(addresses.sanctionsVerifier, addresses.riskVerifier, addresses.kycVerifier);
  await zkr.waitForDeployment();
  addresses.zkNAFRouter = await zkr.getAddress();
  console.log(`  ✅ ${addresses.zkNAFRouter}`);

  // Save
  const deployment = { network, deployer: deployer.address, lzChainId, deployedAt: new Date().toISOString(), contracts: addresses };
  const deployDir = path.join(__dirname, '..', 'deployments');
  if (!fs.existsSync(deployDir)) fs.mkdirSync(deployDir, { recursive: true });
  const file = path.join(deployDir, `l2-${network}-${Date.now()}.json`);
  fs.writeFileSync(file, JSON.stringify(deployment, null, 2));

  const remaining = await hre.ethers.provider.getBalance(deployer.address);

  console.log(`
╔══════════════════════════════════════════════════════════╗
║   ${network} DEPLOYMENT COMPLETE                          
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
