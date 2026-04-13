/**
 * AMTTP Full Stack Deployment
 * 
 * Deploys ALL contracts in the correct order:
 * 1. AMTTPPolicyManager (UUPS proxy)
 * 2. AMTTPStreamlined/AMTTP token (UUPS proxy)
 * 3. AMTTPPolicyEngine (UUPS proxy)
 * 4. MockArbitrator + AMTTPDisputeResolver
 * 5. MockLayerZeroEndpoint + AMTTPCrossChain (UUPS proxy) 
 * 6. AMTTPRiskRouter (UUPS proxy)
 * 7. ZkNAF Verifiers (Sanctions, Risk, KYC)
 * 8. ZkNAFVerifierRouter
 * 9. MockZkNAF (for demo mode testing)
 * 
 * Usage: npx hardhat run scripts/deploy-full-stack.cjs --network localhost
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

async function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║         AMTTP FULL STACK DEPLOYMENT                          ║
╚══════════════════════════════════════════════════════════════╝
`);

  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Network:  ${network}`);
  console.log(`Balance:  ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  const addresses = {};

  // ═══════════════════════════════════════════════════════════
  // 1. Deploy AMTTPPolicyManager
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 1: AMTTPPolicyManager ──');
  const PolicyManager = await hre.ethers.getContractFactory('AMTTPPolicyManager');
  const policyManager = await hre.upgrades.deployProxy(PolicyManager, [], {
    initializer: 'initialize',
    kind: 'uups'
  });
  await policyManager.waitForDeployment();
  addresses.policyManager = await policyManager.getAddress();
  console.log(`  ✅ AMTTPPolicyManager: ${addresses.policyManager}\n`);

  // ═══════════════════════════════════════════════════════════
  // 2. Deploy AMTTPStreamlined (AMTTP token)
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 2: AMTTP Token (Streamlined) ──');
  const AMTTP = await hre.ethers.getContractFactory('contracts/AMTTPStreamlined.sol:AMTTP');
  const amttp = await hre.upgrades.deployProxy(
    AMTTP,
    ['Anti-Money Transfer Transfer Protocol', 'AMTTP', hre.ethers.parseEther('1000000')],
    { initializer: 'initialize', kind: 'uups' }
  );
  await amttp.waitForDeployment();
  addresses.amttp = await amttp.getAddress();
  console.log(`  ✅ AMTTP Token: ${addresses.amttp}`);

  // Link AMTTP → PolicyManager
  await amttp.setPolicyManager(addresses.policyManager);
  console.log(`  ✅ AMTTP → PolicyManager linked\n`);

  // ═══════════════════════════════════════════════════════════
  // 3. Deploy AMTTPPolicyEngine
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 3: AMTTPPolicyEngine ──');
  const PolicyEngine = await hre.ethers.getContractFactory('contracts/AMTTPPolicyEngine.sol:AMTTPPolicyEngine');
  const policyEngine = await hre.upgrades.deployProxy(
    PolicyEngine,
    [hre.ethers.ZeroAddress, deployer.address],
    { initializer: 'initialize', kind: 'uups' }
  );
  await policyEngine.waitForDeployment();
  addresses.policyEngine = await policyEngine.getAddress();
  console.log(`  ✅ AMTTPPolicyEngine: ${addresses.policyEngine}`);

  // Link PolicyManager → PolicyEngine
  await policyManager.setPolicyEngine(addresses.policyEngine);
  console.log(`  ✅ PolicyManager → PolicyEngine linked\n`);

  // ═══════════════════════════════════════════════════════════
  // 4. Deploy MockArbitrator + AMTTPDisputeResolver
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 4: Dispute Resolution (Kleros Mock) ──');
  const MockArbitrator = await hre.ethers.getContractFactory('MockArbitrator');
  const mockArbitrator = await MockArbitrator.deploy();
  await mockArbitrator.waitForDeployment();
  addresses.mockArbitrator = await mockArbitrator.getAddress();
  console.log(`  ✅ MockArbitrator: ${addresses.mockArbitrator}`);

  const DisputeResolver = await hre.ethers.getContractFactory('contracts/AMTTPDisputeResolver.sol:AMTTPDisputeResolver');
  const metaEvidence = 'ipfs://amttp-dispute-rules';
  const disputeResolver = await DisputeResolver.deploy(
    addresses.mockArbitrator,
    metaEvidence
  );
  await disputeResolver.waitForDeployment();
  addresses.disputeResolver = await disputeResolver.getAddress();
  console.log(`  ✅ AMTTPDisputeResolver: ${addresses.disputeResolver}\n`);

  // ═══════════════════════════════════════════════════════════
  // 5. Deploy MockLayerZeroEndpoint + AMTTPCrossChain
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 5: Cross-Chain (LayerZero Mock) ──');
  const MockLZ = await hre.ethers.getContractFactory('MockLayerZeroEndpoint');
  // LayerZero uses uint16 chain IDs — use LZ Sepolia endpoint ID (10161)
  const lzChainId = network === 'sepolia' ? 10161 : network === 'localhost' ? 31337 : 10161;
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

  // ═══════════════════════════════════════════════════════════
  // 6. Deploy AMTTPRiskRouter
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 6: AI Risk Router ──');
  const RiskRouter = await hre.ethers.getContractFactory('AMTTPRiskRouter');
  const riskRouter = await hre.upgrades.deployProxy(
    RiskRouter,
    [deployer.address, 'DQN-v2.0-local'],
    { initializer: 'initialize', kind: 'uups' }
  );
  await riskRouter.waitForDeployment();
  addresses.riskRouter = await riskRouter.getAddress();
  console.log(`  ✅ AMTTPRiskRouter: ${addresses.riskRouter}\n`);

  // ═══════════════════════════════════════════════════════════
  // 7. Deploy ZkNAF Groth16 Verifiers
  // ═══════════════════════════════════════════════════════════
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

  // ═══════════════════════════════════════════════════════════
  // 8. Deploy ZkNAFVerifierRouter
  // ═══════════════════════════════════════════════════════════
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

  // ═══════════════════════════════════════════════════════════
  // 9. Deploy MockZkNAF (demo/testing mode)
  // ═══════════════════════════════════════════════════════════
  console.log('── Step 9: MockZkNAF ──');
  const MockZkNAF = await hre.ethers.getContractFactory('MockZkNAF');
  const mockZkNAF = await MockZkNAF.deploy();
  await mockZkNAF.waitForDeployment();
  addresses.mockZkNAF = await mockZkNAF.getAddress();
  console.log(`  ✅ MockZkNAF: ${addresses.mockZkNAF}\n`);

  // ═══════════════════════════════════════════════════════════
  // Set Oracle on PolicyEngine (deployer acts as oracle)
  // ═══════════════════════════════════════════════════════════
  console.log('── Final Linking ──');
  try {
    await policyEngine.setOracle(deployer.address);
    console.log(`  ✅ Oracle set to deployer: ${deployer.address}`);
  } catch (e) {
    console.log(`  ⚠️  setOracle skipped: ${e.message}`);
  }

  // ═══════════════════════════════════════════════════════════
  // Save deployment
  // ═══════════════════════════════════════════════════════════
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

  // Also save zkNAF verifier addresses for the router script
  const zkNAFDeployment = {
    network,
    deployedAt: new Date().toISOString(),
    contracts: {
      sanctionsVerifier: addresses.sanctionsVerifier,
      riskVerifier: addresses.riskVerifier,
      kycVerifier: addresses.kycVerifier,
      router: addresses.zkNAFRouter,
    }
  };
  const zkNAFFile = path.join(deployDir, `zknaf-verifiers-${network}.json`);
  fs.writeFileSync(zkNAFFile, JSON.stringify(zkNAFDeployment, null, 2));
  console.log(`  📄 zkNAF addresses saved: ${zkNAFFile}`);

  // Print summary
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║         DEPLOYMENT COMPLETE                                  ║
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

  Oracle (deployer):    ${deployer.address}
  
  PRIVATE_KEY:          0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
  RPC_URL:              http://127.0.0.1:8545
  AMTTP_ADDRESS:        ${addresses.amttp}
  
╚══════════════════════════════════════════════════════════════╝
`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
