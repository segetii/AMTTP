/**
 * AMTTP Sepolia Deployment — CONTINUATION
 * Steps 5–9 (CrossChain, RiskRouter, ZkNAF verifiers, Router, MockZkNAF)
 * 
 * Steps 1–4 already deployed:
 *   PolicyManager:   0x4eECb1348988A041B89acA4Aa9348F6e1DD9BcD3
 *   AMTTP Token:     0x05687FBb0f8921ff502BdEbC180b24Ed2B14b612
 *   PolicyEngine:    0xe774E01CbFC63cfb64a0ec054821fDb5A61d8703
 *   MockArbitrator:  0x86832c8EF025805B2B246c89D6B22b806075A7d1
 *   DisputeResolver: 0x9EB935E68DEa685B6feAa9DAB51a46Dcd4da53D7
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

async function main() {
  console.log('\n╔══════════════════════════════════════════════════════════╗');
  console.log('║   AMTTP SEPOLIA DEPLOYMENT — CONTINUATION (Steps 5–9)   ║');
  console.log('╚══════════════════════════════════════════════════════════╝\n');

  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Network:  ${network}`);
  console.log(`Balance:  ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  // Already deployed
  const addresses = {
    policyManager:   '0x4eECb1348988A041B89acA4Aa9348F6e1DD9BcD3',
    amttp:           '0x05687FBb0f8921ff502BdEbC180b24Ed2B14b612',
    policyEngine:    '0xe774E01CbFC63cfb64a0ec054821fDb5A61d8703',
    mockArbitrator:  '0x86832c8EF025805B2B246c89D6B22b806075A7d1',
    disputeResolver: '0x9EB935E68DEa685B6feAa9DAB51a46Dcd4da53D7',
  };

  // ── Step 5: Cross-Chain (LayerZero Mock) ──
  console.log('── Step 5: Cross-Chain (LayerZero Mock) ──');
  const MockLZ = await hre.ethers.getContractFactory('MockLayerZeroEndpoint');
  const lzChainId = 10161; // LayerZero Sepolia endpoint ID (uint16-safe)
  const mockLZ = await MockLZ.deploy(lzChainId);
  await mockLZ.waitForDeployment();
  addresses.mockLayerZero = await mockLZ.getAddress();
  console.log(`  ✅ MockLayerZeroEndpoint: ${addresses.mockLayerZero}`);

  const CrossChain = await hre.ethers.getContractFactory('contracts/AMTTPCrossChain.sol:AMTTPCrossChain');
  const crossChain = await hre.upgrades.deployProxy(
    CrossChain,
    [addresses.mockLayerZero, lzChainId, addresses.policyEngine],
    { initializer: 'initialize', kind: 'uups' }
  );
  await crossChain.waitForDeployment();
  addresses.crossChain = await crossChain.getAddress();
  console.log(`  ✅ AMTTPCrossChain: ${addresses.crossChain}\n`);

  // ── Step 6: AI Risk Router ──
  console.log('── Step 6: AI Risk Router ──');
  const RiskRouter = await hre.ethers.getContractFactory('AMTTPRiskRouter');
  const riskRouter = await hre.upgrades.deployProxy(
    RiskRouter,
    [deployer.address, 'DQN-v2.0-sepolia'],
    { initializer: 'initialize', kind: 'uups' }
  );
  await riskRouter.waitForDeployment();
  addresses.riskRouter = await riskRouter.getAddress();
  console.log(`  ✅ AMTTPRiskRouter: ${addresses.riskRouter}\n`);

  // ── Step 7: ZkNAF Groth16 Verifiers ──
  console.log('── Step 7: ZkNAF Groth16 Verifiers ──');

  const SanctionsVerifier = await hre.ethers.getContractFactory(
    'contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier'
  );
  const sanctionsVerifier = await SanctionsVerifier.deploy();
  await sanctionsVerifier.waitForDeployment();
  addresses.sanctionsVerifier = await sanctionsVerifier.getAddress();
  console.log(`  ✅ SanctionsVerifier: ${addresses.sanctionsVerifier}`);

  const RiskVerifier = await hre.ethers.getContractFactory(
    'contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier'
  );
  const riskVerifier = await RiskVerifier.deploy();
  await riskVerifier.waitForDeployment();
  addresses.riskVerifier = await riskVerifier.getAddress();
  console.log(`  ✅ RiskVerifier:      ${addresses.riskVerifier}`);

  const KYCVerifier = await hre.ethers.getContractFactory(
    'contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier'
  );
  const kycVerifier = await KYCVerifier.deploy();
  await kycVerifier.waitForDeployment();
  addresses.kycVerifier = await kycVerifier.getAddress();
  console.log(`  ✅ KYCVerifier:       ${addresses.kycVerifier}\n`);

  // ── Step 8: ZkNAF Verifier Router ──
  console.log('── Step 8: ZkNAF Verifier Router ──');
  const ZkRouter = await hre.ethers.getContractFactory('ZkNAFVerifierRouter');
  const zkRouter = await ZkRouter.deploy(
    addresses.sanctionsVerifier,
    addresses.riskVerifier,
    addresses.kycVerifier
  );
  await zkRouter.waitForDeployment();
  addresses.zkNAFRouter = await zkRouter.getAddress();
  console.log(`  ✅ ZkNAFVerifierRouter: ${addresses.zkNAFRouter}\n`);

  // ── Step 9: MockZkNAF ──
  console.log('── Step 9: MockZkNAF ──');
  const MockZkNAF = await hre.ethers.getContractFactory('MockZkNAF');
  const mockZkNAF = await MockZkNAF.deploy();
  await mockZkNAF.waitForDeployment();
  addresses.mockZkNAF = await mockZkNAF.getAddress();
  console.log(`  ✅ MockZkNAF: ${addresses.mockZkNAF}\n`);

  // ── Set Oracle on PolicyEngine ──
  console.log('── Final Linking ──');
  try {
    const policyEngine = await hre.ethers.getContractAt(
      'contracts/AMTTPPolicyEngine.sol:AMTTPPolicyEngine',
      addresses.policyEngine
    );
    await policyEngine.setOracle(deployer.address);
    console.log(`  ✅ Oracle set to deployer: ${deployer.address}`);
  } catch (e) {
    console.log(`  ⚠️  setOracle skipped: ${e.message.slice(0, 100)}`);
  }

  // Save deployment
  const deployment = {
    network,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    contracts: addresses,
  };

  const deployDir = path.join(__dirname, '..', 'deployments');
  if (!fs.existsSync(deployDir)) fs.mkdirSync(deployDir, { recursive: true });

  const deployFile = path.join(deployDir, `full-stack-${network}-${Date.now()}.json`);
  fs.writeFileSync(deployFile, JSON.stringify(deployment, null, 2));
  console.log(`\n  📄 Deployment saved: ${deployFile}`);

  const remaining = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`\n  Balance remaining: ${hre.ethers.formatEther(remaining)} ETH`);

  console.log(`
╔══════════════════════════════════════════════════════════════╗
║         SEPOLIA DEPLOYMENT COMPLETE                          ║
╠══════════════════════════════════════════════════════════════╣

  AMTTP Token:          ${addresses.amttp}
  PolicyManager:        ${addresses.policyManager}
  PolicyEngine:         ${addresses.policyEngine}
  DisputeResolver:      ${addresses.disputeResolver}
  CrossChain:           ${addresses.crossChain}
  RiskRouter:           ${addresses.riskRouter}
  
  SanctionsVerifier:    ${addresses.sanctionsVerifier}
  RiskVerifier:         ${addresses.riskVerifier}
  KYCVerifier:          ${addresses.kycVerifier}
  ZkNAFVerifierRouter:  ${addresses.zkNAFRouter}
  MockZkNAF:            ${addresses.mockZkNAF}

╚══════════════════════════════════════════════════════════════╝
`);
}

main().catch(console.error);
