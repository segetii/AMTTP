/**
 * AMTTP LayerZero Cross-Chain Deployment Script
 * 
 * Deploys:
 * - MockLayerZeroEndpoint (for local testing)
 * - AMTTPCrossChain contract
 * - Links with existing PolicyEngine
 * 
 * Usage:
 *   npx hardhat run scripts/deploy-layerzero.cjs --network localhost
 *   npx hardhat run scripts/deploy-layerzero.cjs --network polygon
 *   npx hardhat run scripts/deploy-layerzero.cjs --network arbitrum
 */

const { ethers, upgrades } = require("hardhat");
const fs = require("fs");
const path = require("path");

// LayerZero Chain IDs
const LZ_CHAIN_IDS = {
  ethereum: 101,
  polygon: 109,
  arbitrum: 110,
  optimism: 111,
  base: 184,
  bsc: 102,
  avalanche: 106,
  localhost: 31337 // Local testing
};

// LayerZero Endpoint addresses (mainnet)
const LZ_ENDPOINTS = {
  ethereum: "0x66A71Dcef29A0fFBDBE3c6a460a3B5BC225Cd675",
  polygon: "0x3c2269811836af69497E5F486A85D7316753cf62",
  arbitrum: "0x3c2269811836af69497E5F486A85D7316753cf62",
  optimism: "0x3c2269811836af69497E5F486A85D7316753cf62",
  base: "0xb6319cC6c8c27A8F5dAF0dD3DF91EA35C4720dd7",
  bsc: "0x3c2269811836af69497E5F486A85D7316753cf62",
  avalanche: "0x3c2269811836af69497E5F486A85D7316753cf62"
};

async function main() {
  console.log("============================================================");
  console.log("AMTTP LAYERZERO CROSS-CHAIN DEPLOYMENT");
  console.log("============================================================");

  const [deployer] = await ethers.getSigners();
  const network = hre.network.name;
  
  console.log(`Network: ${network}`);
  console.log(`Deployer: ${deployer.address}`);
  console.log(`Balance: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH\n`);

  let lzEndpointAddress;
  let lzChainId;
  let policyEngineAddress;

  // Determine LayerZero endpoint
  if (network === "localhost" || network === "hardhat") {
    console.log("📋 Deploying Mock LayerZero Endpoint for local testing...");
    
    const MockLZEndpoint = await ethers.getContractFactory("MockLayerZeroEndpoint");
    const mockEndpoint = await MockLZEndpoint.deploy(LZ_CHAIN_IDS.localhost);
    await mockEndpoint.waitForDeployment();
    
    lzEndpointAddress = await mockEndpoint.getAddress();
    lzChainId = LZ_CHAIN_IDS.localhost;
    
    console.log(`   ✅ Mock LZ Endpoint: ${lzEndpointAddress}\n`);
    
    // Load existing PolicyEngine from deployment
    const deploymentsDir = path.join(__dirname, "../deployments");
    const files = fs.readdirSync(deploymentsDir);
    const latestDeployment = files
      .filter(f => f.startsWith("kleros-localhost"))
      .sort()
      .pop();
    
    if (latestDeployment) {
      const deployment = JSON.parse(
        fs.readFileSync(path.join(deploymentsDir, latestDeployment), "utf8")
      );
      policyEngineAddress = deployment.contracts?.policyEngine || deployment.policyEngine;
      console.log(`   📋 Found PolicyEngine: ${policyEngineAddress}\n`);
    }
    
    if (!policyEngineAddress) {
      console.log("   ⚠️  No existing PolicyEngine found, deploying new one...");
      const PolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
      const policyEngine = await upgrades.deployProxy(PolicyEngine, [], {
        initializer: "initialize"
      });
      await policyEngine.waitForDeployment();
      policyEngineAddress = await policyEngine.getAddress();
      console.log(`   ✅ New PolicyEngine: ${policyEngineAddress}\n`);
    }
  } else {
    // Use real LayerZero endpoint
    lzEndpointAddress = LZ_ENDPOINTS[network];
    lzChainId = LZ_CHAIN_IDS[network];
    
    if (!lzEndpointAddress) {
      throw new Error(`No LayerZero endpoint configured for network: ${network}`);
    }
    
    console.log(`📋 Using LayerZero Endpoint: ${lzEndpointAddress}`);
    console.log(`   Chain ID: ${lzChainId}\n`);
    
    // For mainnet/testnet, PolicyEngine address should be provided
    policyEngineAddress = process.env.POLICY_ENGINE_ADDRESS || ethers.ZeroAddress;
    console.log(`   PolicyEngine: ${policyEngineAddress}\n`);
  }

  // Deploy AMTTPCrossChain
  console.log("1️⃣ Deploying AMTTPCrossChain...");
  
  const AMTTPCrossChain = await ethers.getContractFactory("AMTTPCrossChain");
  const crossChain = await upgrades.deployProxy(
    AMTTPCrossChain,
    [lzEndpointAddress, lzChainId, policyEngineAddress],
    { initializer: "initialize" }
  );
  await crossChain.waitForDeployment();
  
  const crossChainAddress = await crossChain.getAddress();
  console.log(`   ✅ AMTTPCrossChain: ${crossChainAddress}\n`);

  // Configure trusted remotes for cross-chain communication
  console.log("2️⃣ Configuring cross-chain settings...");
  
  if (network === "localhost" || network === "hardhat") {
    // For local testing, we set up a self-referential trusted remote
    // In production, you'd set trusted remotes for each chain
    const localPath = ethers.solidityPacked(
      ["address", "address"],
      [crossChainAddress, crossChainAddress]
    );
    
    await crossChain.setTrustedRemotePath(LZ_CHAIN_IDS.localhost, localPath);
    console.log(`   ✅ Set local trusted remote for testing\n`);
    
    // Set trusted remotes for "simulated" other chains
    console.log("   Setting up simulated cross-chain paths:");
    
    for (const [chain, chainId] of Object.entries(LZ_CHAIN_IDS)) {
      if (chain !== "localhost") {
        // In production, these would be the actual deployed addresses on each chain
        const remotePath = ethers.solidityPacked(
          ["address", "address"],
          [crossChainAddress, crossChainAddress] // Self-reference for testing
        );
        await crossChain.setTrustedRemotePath(chainId, remotePath);
        console.log(`   - ${chain} (${chainId}): configured`);
      }
    }
    console.log("");
  }

  // Verify configuration
  console.log("3️⃣ Verifying configuration...");
  
  const configuredEndpoint = await crossChain.lzEndpoint();
  const configuredChainId = await crossChain.localChainId();
  const configuredPolicyEngine = await crossChain.policyEngine();
  
  console.log(`   LZ Endpoint: ${configuredEndpoint}`);
  console.log(`   Local Chain ID: ${configuredChainId}`);
  console.log(`   Policy Engine: ${configuredPolicyEngine}\n`);

  // Save deployment info
  const deploymentInfo = {
    network,
    timestamp: new Date().toISOString(),
    deployer: deployer.address,
    contracts: {
      lzEndpoint: lzEndpointAddress,
      crossChain: crossChainAddress,
      policyEngine: policyEngineAddress
    },
    config: {
      lzChainId,
      supportedChains: Object.keys(LZ_CHAIN_IDS)
    }
  };

  const deploymentsDir = path.join(__dirname, "../deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const filename = `layerzero-${network}-${Date.now()}.json`;
  fs.writeFileSync(
    path.join(deploymentsDir, filename),
    JSON.stringify(deploymentInfo, null, 2)
  );

  console.log("============================================================");
  console.log("✅ LAYERZERO DEPLOYMENT COMPLETE");
  console.log("============================================================\n");

  console.log("📋 Contract Addresses:");
  console.log(`   LayerZero Endpoint:    ${lzEndpointAddress}`);
  console.log(`   AMTTPCrossChain:       ${crossChainAddress}`);
  console.log(`   PolicyEngine:          ${policyEngineAddress}\n`);

  console.log("🔗 Cross-Chain Capabilities:");
  console.log("   • Send risk scores to other chains");
  console.log("   • Block addresses globally across all chains");
  console.log("   • Propagate dispute results");
  console.log("   • Sync policy updates\n");

  console.log("🌐 Supported Chains:");
  for (const [chain, chainId] of Object.entries(LZ_CHAIN_IDS)) {
    if (chain !== "localhost") {
      console.log(`   - ${chain.charAt(0).toUpperCase() + chain.slice(1)}: Chain ID ${chainId}`);
    }
  }

  console.log(`\n📁 Deployment saved to: deployments/${filename}`);

  // Print example usage
  console.log("\n============================================================");
  console.log("EXAMPLE USAGE");
  console.log("============================================================\n");

  console.log("// Send risk score to Polygon:");
  console.log(`const crossChain = await ethers.getContractAt("AMTTPCrossChain", "${crossChainAddress}");`);
  console.log(`const fee = await crossChain.estimateRiskScoreFee(109, targetAddress, 850);`);
  console.log(`await crossChain.sendRiskScore(109, targetAddress, 850, "0x", { value: fee });`);
  
  console.log("\n// Block address globally (all chains):");
  console.log(`await crossChain.blockAddressGlobally([109, 110, 184], badActor, "Fraud detected", { value: totalFee });`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
