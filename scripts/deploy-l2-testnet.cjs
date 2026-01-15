/**
 * AMTTP L2 Testnet Deployment Script
 * Deploy RiskRouter to Polygon Amoy and Arbitrum Sepolia
 * 
 * Prerequisites:
 * - Polygon Amoy: ~0.5 MATIC (get from https://faucet.polygon.technology/)
 * - Arbitrum Sepolia: ~0.05 ETH (get from https://faucet.quicknode.com/arbitrum/sepolia)
 */

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// Network configurations
const NETWORKS = {
  polygonAmoy: {
    name: "Polygon Amoy",
    chainId: 80002,
    rpcUrl: process.env.POLYGON_AMOY_RPC || "https://rpc-amoy.polygon.technology",
    explorer: "https://amoy.polygonscan.com",
    faucet: "https://faucet.polygon.technology/",
    requiredBalance: "0.5", // MATIC
    layerZeroEndpoint: "0x6EDCE65403992e310A62460808c4b910D972f10f", // LZ Amoy endpoint
    lzChainId: 10267
  },
  arbitrumSepolia: {
    name: "Arbitrum Sepolia",
    chainId: 421614,
    rpcUrl: process.env.ARBITRUM_SEPOLIA_RPC || "https://sepolia-rollup.arbitrum.io/rpc",
    explorer: "https://sepolia.arbiscan.io",
    faucet: "https://faucet.quicknode.com/arbitrum/sepolia",
    requiredBalance: "0.05", // ETH
    layerZeroEndpoint: "0x6EDCE65403992e310A62460808c4b910D972f10f", // LZ Arbitrum Sepolia
    lzChainId: 10231
  }
};

// Deployment results file
const DEPLOYMENTS_FILE = path.join(__dirname, "../deployments/l2-testnet.json");

async function getBalance(address, provider) {
  const balance = await provider.getBalance(address);
  return hre.ethers.formatEther(balance);
}

async function checkPrerequisites(network, signer) {
  console.log(`\n📋 Checking prerequisites for ${network.name}...`);
  
  const address = await signer.getAddress();
  const balance = await getBalance(address, signer.provider);
  
  console.log(`   Deployer address: ${address}`);
  console.log(`   Current balance: ${balance} native token`);
  
  const required = parseFloat(network.requiredBalance);
  const current = parseFloat(balance);
  
  if (current < required) {
    console.log(`\n   ❌ Insufficient balance!`);
    console.log(`   Required: ${required}`);
    console.log(`   Current: ${current}`);
    console.log(`   Get tokens from: ${network.faucet}`);
    return false;
  }
  
  console.log(`   ✅ Sufficient balance`);
  return true;
}

async function deployRiskRouter(network, signer) {
  console.log(`\n🚀 Deploying AMTTPRiskRouter to ${network.name}...`);
  
  // Get contract factory
  const RiskRouter = await hre.ethers.getContractFactory("AMTTPRiskRouter", signer);
  
  // Deploy
  console.log("   Deploying contract...");
  const riskRouter = await RiskRouter.deploy(
    network.layerZeroEndpoint,
    await signer.getAddress() // Oracle address (deployer for now)
  );
  
  await riskRouter.waitForDeployment();
  const address = await riskRouter.getAddress();
  
  console.log(`   ✅ Deployed at: ${address}`);
  console.log(`   Explorer: ${network.explorer}/address/${address}`);
  
  return {
    address,
    txHash: riskRouter.deploymentTransaction().hash,
    blockNumber: (await riskRouter.deploymentTransaction().wait()).blockNumber
  };
}

async function configureRiskRouter(contract, config, signer) {
  console.log("\n⚙️ Configuring RiskRouter...");
  
  // Set default thresholds
  const tx1 = await contract.setDefaultThresholds(
    25,  // lowRiskMax
    50,  // mediumRiskMax  
    75   // highRiskMax
  );
  await tx1.wait();
  console.log("   ✅ Default thresholds set");
  
  // Set escrow parameters
  const tx2 = await contract.setEscrowParams(
    24 * 60 * 60,  // 24 hour escrow duration
    hre.ethers.parseEther("1")  // 1 ETH min escrow
  );
  await tx2.wait();
  console.log("   ✅ Escrow parameters set");
  
  console.log("   ✅ Configuration complete");
}

async function saveDeployment(networkName, deployment) {
  let deployments = {};
  
  if (fs.existsSync(DEPLOYMENTS_FILE)) {
    deployments = JSON.parse(fs.readFileSync(DEPLOYMENTS_FILE, "utf8"));
  }
  
  deployments[networkName] = {
    ...deployment,
    deployedAt: new Date().toISOString()
  };
  
  fs.mkdirSync(path.dirname(DEPLOYMENTS_FILE), { recursive: true });
  fs.writeFileSync(DEPLOYMENTS_FILE, JSON.stringify(deployments, null, 2));
  
  console.log(`\n📁 Deployment saved to ${DEPLOYMENTS_FILE}`);
}

async function deployToNetwork(networkName) {
  const network = NETWORKS[networkName];
  if (!network) {
    console.error(`Unknown network: ${networkName}`);
    return null;
  }
  
  console.log(`\n${"═".repeat(60)}`);
  console.log(`   Deploying to ${network.name}`);
  console.log(`${"═".repeat(60)}`);
  
  // Get signer
  const [signer] = await hre.ethers.getSigners();
  
  // Check prerequisites
  const ready = await checkPrerequisites(network, signer);
  if (!ready) {
    return null;
  }
  
  // Deploy
  const deployment = await deployRiskRouter(network, signer);
  
  // Get contract instance for configuration
  const RiskRouter = await hre.ethers.getContractFactory("AMTTPRiskRouter", signer);
  const contract = RiskRouter.attach(deployment.address);
  
  // Configure
  await configureRiskRouter(contract, network, signer);
  
  // Save deployment
  const fullDeployment = {
    ...deployment,
    network: networkName,
    chainId: network.chainId,
    layerZeroEndpoint: network.layerZeroEndpoint,
    lzChainId: network.lzChainId,
    explorer: `${network.explorer}/address/${deployment.address}`
  };
  
  await saveDeployment(networkName, fullDeployment);
  
  return fullDeployment;
}

async function main() {
  const networkArg = process.argv[2];
  
  if (!networkArg || networkArg === "all") {
    // Deploy to all L2 testnets
    console.log("🌐 Deploying to all L2 testnets...\n");
    
    const results = {};
    
    for (const networkName of Object.keys(NETWORKS)) {
      try {
        const result = await deployToNetwork(networkName);
        if (result) {
          results[networkName] = result;
        }
      } catch (error) {
        console.error(`\n❌ Failed to deploy to ${networkName}:`, error.message);
      }
    }
    
    // Summary
    console.log("\n" + "═".repeat(60));
    console.log("   DEPLOYMENT SUMMARY");
    console.log("═".repeat(60));
    
    for (const [network, deployment] of Object.entries(results)) {
      console.log(`\n   ${NETWORKS[network].name}:`);
      console.log(`   Address: ${deployment.address}`);
      console.log(`   Explorer: ${deployment.explorer}`);
    }
    
    if (Object.keys(results).length === 0) {
      console.log("\n   ⚠️ No successful deployments. Check your wallet balance and try again.");
    }
    
  } else {
    // Deploy to specific network
    await deployToNetwork(networkArg);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });

// Export for testing
module.exports = { NETWORKS, deployToNetwork };
