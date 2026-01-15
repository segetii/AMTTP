// scripts/deploy-with-kleros.cjs
// Deploy AMTTP with Kleros dispute resolution

const hre = require("hardhat");

// Kleros Arbitrator addresses by network
const KLEROS_ARBITRATORS = {
  // Mainnet
  mainnet: "0x988b3A538b618C7A603e1c11Ab82Cd16dbE28069",
  // Sepolia testnet
  sepolia: "0x90992fb4E15ce0C59aEFfb376460Fdc4Bfa6E1f6",
  // Arbitrum
  arbitrum: "0x991d2df165670b9cac3b022e0b1e5A6C9275905F",
  // Gnosis Chain (xDAI)
  gnosis: "0x9C1dA9A04925bDfDedf0f6421bC7EEa8305F9002",
  // For local testing - will deploy mock
  localhost: null,
  hardhat: null,
};

// MetaEvidence IPFS URI (describes dispute rules)
// After running `node scripts/upload-meta-evidence.cjs`, this will be updated automatically
// Or set via environment variable: AMTTP_META_EVIDENCE_URI
const META_EVIDENCE_URI = process.env.AMTTP_META_EVIDENCE_URI || "ipfs://bafybeiexamplehash123"; // Run upload-meta-evidence.cjs to set

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  
  console.log("=".repeat(60));
  console.log("AMTTP + KLEROS DEPLOYMENT");
  console.log("=".repeat(60));
  console.log(`Network: ${network}`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance: ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH`);
  console.log("");

  let klerosArbitrator = KLEROS_ARBITRATORS[network];
  
  // For local testing, deploy a mock arbitrator
  if (!klerosArbitrator) {
    console.log("📋 Deploying Mock Kleros Arbitrator for testing...");
    const MockArbitrator = await hre.ethers.getContractFactory("MockArbitrator");
    const mockArbitrator = await MockArbitrator.deploy();
    await mockArbitrator.waitForDeployment();
    klerosArbitrator = await mockArbitrator.getAddress();
    console.log(`   Mock Arbitrator: ${klerosArbitrator}`);
    console.log("");
  }
  
  // 1. Deploy AMTTPDisputeResolver
  console.log("1️⃣ Deploying AMTTPDisputeResolver...");
  const DisputeResolver = await hre.ethers.getContractFactory("AMTTPDisputeResolver");
  const disputeResolver = await DisputeResolver.deploy(
    klerosArbitrator,
    META_EVIDENCE_URI
  );
  await disputeResolver.waitForDeployment();
  const disputeResolverAddr = await disputeResolver.getAddress();
  console.log(`   ✅ AMTTPDisputeResolver: ${disputeResolverAddr}`);
  console.log("");
  
  // 2. Deploy AMTTPPolicyEngine (upgradeable)
  console.log("2️⃣ Deploying AMTTPPolicyEngine...");
  const PolicyEngine = await hre.ethers.getContractFactory("AMTTPPolicyEngine");
  const policyEngine = await hre.upgrades.deployProxy(
    PolicyEngine,
    [deployer.address, deployer.address], // amttpContract, oracleService
    { initializer: "initialize", kind: "uups" }
  );
  await policyEngine.waitForDeployment();
  const policyEngineAddr = await policyEngine.getAddress();
  console.log(`   ✅ AMTTPPolicyEngine: ${policyEngineAddr}`);
  console.log("");
  
  // 3. Configure PolicyEngine with DisputeResolver
  console.log("3️⃣ Configuring Kleros integration...");
  await policyEngine.setDisputeResolver(disputeResolverAddr);
  console.log(`   ✅ Dispute Resolver linked`);
  
  // Set escrow threshold (700 = 70% risk score)
  await policyEngine.setEscrowThreshold(700);
  console.log(`   ✅ Escrow threshold set to 700 (70% risk)`);
  console.log("");
  
  // 4. Verify configuration
  console.log("4️⃣ Verifying configuration...");
  const linkedResolver = await policyEngine.getDisputeResolver();
  const threshold = await policyEngine.escrowThreshold();
  console.log(`   Linked Resolver: ${linkedResolver}`);
  console.log(`   Escrow Threshold: ${threshold}`);
  console.log("");
  
  // Summary
  console.log("=".repeat(60));
  console.log("✅ DEPLOYMENT COMPLETE");
  console.log("=".repeat(60));
  console.log("");
  console.log("📋 Contract Addresses:");
  console.log(`   Kleros Arbitrator:      ${klerosArbitrator}`);
  console.log(`   AMTTPDisputeResolver:   ${disputeResolverAddr}`);
  console.log(`   AMTTPPolicyEngine:      ${policyEngineAddr}`);
  console.log("");
  console.log("🔗 Integration Flow:");
  console.log("   1. ML API scores transaction → risk score");
  console.log("   2. PolicyEngine.shouldRouteToKleros(riskScore)");
  console.log("   3. If true → routeToKlerosEscrow()");
  console.log("   4. DisputeResolver holds funds in escrow");
  console.log("   5. 24h challenge window");
  console.log("   6. If challenged → Kleros jurors vote");
  console.log("   7. Ruling executed (approve/reject)");
  console.log("");
  
  // Save deployment info
  const deploymentInfo = {
    network,
    timestamp: new Date().toISOString(),
    deployer: deployer.address,
    contracts: {
      klerosArbitrator,
      disputeResolver: disputeResolverAddr,
      policyEngine: policyEngineAddr,
    },
    configuration: {
      escrowThreshold: threshold.toString(),
      challengeWindow: "24 hours",
      metaEvidenceURI: META_EVIDENCE_URI,
    },
  };
  
  const fs = require("fs");
  fs.writeFileSync(
    `./deployments/kleros-${network}-${Date.now()}.json`,
    JSON.stringify(deploymentInfo, null, 2)
  );
  console.log(`📁 Deployment info saved to ./deployments/`);
  
  return deploymentInfo;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
