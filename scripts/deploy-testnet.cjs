/**
 * AMTTP Testnet Deployment Script
 * 
 * Deploys the full AMTTP stack to testnets:
 * - AMTTPPolicyEngine (upgradeable)
 * - AMTTPDisputeResolver (Kleros integration)
 * - AMTTPCrossChain (LayerZero integration)
 * 
 * Usage:
 *   npx hardhat run scripts/deploy-testnet.cjs --network sepolia
 *   npx hardhat run scripts/deploy-testnet.cjs --network polygonAmoy
 *   npx hardhat run scripts/deploy-testnet.cjs --network arbitrumSepolia
 */

const { ethers, upgrades, network } = require("hardhat");
const fs = require("fs");
const path = require("path");

// LayerZero Testnet Endpoints
const LZ_TESTNET_ENDPOINTS = {
  sepolia: {
    endpoint: "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1",
    chainId: 10161
  },
  polygonAmoy: {
    endpoint: "0x55370E0fBB5f5b8dAeD978BA1c075a499eB107B8", 
    chainId: 10267
  },
  arbitrumSepolia: {
    endpoint: "0x6098e96a28E02f27B1e6BD381f870F1C8Bd169d3",
    chainId: 10231
  },
  baseSepolia: {
    endpoint: "0x55370E0fBB5f5b8dAeD978BA1c075a499eB107B8",
    chainId: 10245
  }
};

// Kleros Court addresses (testnet) - properly checksummed
const KLEROS_TESTNET = {
  sepolia: "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8", // Kleros Core on Sepolia
  arbitrumSepolia: "0x0000000000000000000000000000000000000000" // Not available
};

async function main() {
  console.log("============================================================");
  console.log("AMTTP TESTNET DEPLOYMENT");
  console.log("============================================================\n");

  const [deployer] = await ethers.getSigners();
  const networkName = network.name;
  
  console.log(`Network: ${networkName}`);
  console.log(`Deployer: ${deployer.address}`);
  
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${ethers.formatEther(balance)} ETH\n`);

  if (balance === 0n) {
    console.log("❌ ERROR: No ETH in wallet!");
    console.log("\nGet testnet ETH from:");
    console.log("  Sepolia: https://sepoliafaucet.com");
    console.log("  Polygon Amoy: https://faucet.polygon.technology/");
    console.log("  Arbitrum Sepolia: https://faucet.arbitrum.io/");
    console.log("  Base Sepolia: https://www.coinbase.com/faucets/base-ethereum-goerli-faucet");
    process.exit(1);
  }

  const lzConfig = LZ_TESTNET_ENDPOINTS[networkName];
  if (!lzConfig) {
    console.log(`⚠️  LayerZero not configured for ${networkName}, using mock`);
  }

  // ============ Deploy DisputeResolver First (needed for oracle address) ============
  console.log("1️⃣ Deploying AMTTPDisputeResolver...");
  
  // Use Kleros on Sepolia, mock on others
  let arbitratorAddress;
  if (KLEROS_TESTNET[networkName] && KLEROS_TESTNET[networkName] !== "0x0000000000000000000000000000000000000000") {
    arbitratorAddress = KLEROS_TESTNET[networkName];
    console.log(`   Using Kleros Arbitrator: ${arbitratorAddress}`);
  } else {
    // Deploy mock arbitrator
    console.log("   Deploying Mock Arbitrator...");
    const MockArbitrator = await ethers.getContractFactory("MockArbitrator");
    const mockArbitrator = await MockArbitrator.deploy();
    await mockArbitrator.waitForDeployment();
    arbitratorAddress = await mockArbitrator.getAddress();
    console.log(`   ✅ Mock Arbitrator: ${arbitratorAddress}`);
  }

  // DisputeResolver uses regular constructor (not upgradeable)
  const DisputeResolver = await ethers.getContractFactory("AMTTPDisputeResolver");
  const disputeResolver = await DisputeResolver.deploy(
    arbitratorAddress,
    "ipfs://QmAMTTPMetaEvidence"
  );
  await disputeResolver.waitForDeployment();
  
  const disputeResolverAddress = await disputeResolver.getAddress();
  console.log(`   ✅ DisputeResolver: ${disputeResolverAddress}`);

  // ============ Deploy PolicyEngine ============
  console.log("\n2️⃣ Deploying AMTTPPolicyEngine...");
  
  // PolicyEngine.initialize requires (amttpContract, oracleService)
  // Use deployer as AMTTP contract and DisputeResolver as oracle for now
  const PolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
  const policyEngine = await upgrades.deployProxy(
    PolicyEngine, 
    [deployer.address, disputeResolverAddress],  // amttpContract, oracleService
    {
      initializer: "initialize",
      timeout: 300000
    }
  );
  await policyEngine.waitForDeployment();
  
  const policyEngineAddress = await policyEngine.getAddress();
  console.log(`   ✅ PolicyEngine: ${policyEngineAddress}`);

  // ============ Deploy CrossChain ============
  console.log("\n3️⃣ Deploying AMTTPCrossChain...");
  
  let lzEndpointAddress;
  let lzChainId;
  
  if (lzConfig) {
    lzEndpointAddress = lzConfig.endpoint;
    lzChainId = lzConfig.chainId;
    console.log(`   Using LayerZero Endpoint: ${lzEndpointAddress}`);
    console.log(`   LayerZero Chain ID: ${lzChainId}`);
  } else {
    // Deploy mock LZ endpoint
    console.log("   Deploying Mock LayerZero Endpoint...");
    const MockLZEndpoint = await ethers.getContractFactory("MockLayerZeroEndpoint");
    const mockLZ = await MockLZEndpoint.deploy(31337);
    await mockLZ.waitForDeployment();
    lzEndpointAddress = await mockLZ.getAddress();
    lzChainId = 31337;
    console.log(`   ✅ Mock LZ Endpoint: ${lzEndpointAddress}`);
  }

  const CrossChain = await ethers.getContractFactory("AMTTPCrossChain");
  const crossChain = await upgrades.deployProxy(
    CrossChain,
    [lzEndpointAddress, lzChainId, policyEngineAddress],
    { initializer: "initialize", timeout: 300000 }
  );
  await crossChain.waitForDeployment();
  
  const crossChainAddress = await crossChain.getAddress();
  console.log(`   ✅ CrossChain: ${crossChainAddress}`);

  // ============ Configure Contracts ============
  console.log("\n4️⃣ Configuring contracts...");

  // Link PolicyEngine to DisputeResolver
  console.log("   Setting DisputeResolver on PolicyEngine...");
  let tx = await policyEngine.setDisputeResolver(disputeResolverAddress);
  await tx.wait();
  console.log("   ✅ DisputeResolver linked");

  // Set escrow threshold
  console.log("   Setting escrow threshold...");
  tx = await policyEngine.setEscrowThreshold(700);
  await tx.wait();
  console.log("   ✅ Escrow threshold set to 700");

  // ============ Save Deployment ============
  const deployment = {
    network: networkName,
    chainId: (await ethers.provider.getNetwork()).chainId.toString(),
    timestamp: new Date().toISOString(),
    deployer: deployer.address,
    contracts: {
      policyEngine: policyEngineAddress,
      disputeResolver: disputeResolverAddress,
      crossChain: crossChainAddress,
      arbitrator: arbitratorAddress,
      lzEndpoint: lzEndpointAddress
    },
    layerZero: {
      chainId: lzChainId,
      endpoint: lzEndpointAddress
    },
    configuration: {
      escrowThreshold: 700,
      klerosCourt: arbitratorAddress
    },
    explorerUrls: {
      policyEngine: getExplorerUrl(networkName, policyEngineAddress),
      disputeResolver: getExplorerUrl(networkName, disputeResolverAddress),
      crossChain: getExplorerUrl(networkName, crossChainAddress)
    }
  };

  const deploymentsDir = path.join(__dirname, "../deployments");
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }

  const filename = `testnet-${networkName}-${Date.now()}.json`;
  fs.writeFileSync(
    path.join(deploymentsDir, filename),
    JSON.stringify(deployment, null, 2)
  );

  // ============ Print Summary ============
  console.log("\n============================================================");
  console.log("✅ TESTNET DEPLOYMENT COMPLETE");
  console.log("============================================================\n");

  console.log("📋 Contract Addresses:");
  console.log(`   PolicyEngine:     ${policyEngineAddress}`);
  console.log(`   DisputeResolver:  ${disputeResolverAddress}`);
  console.log(`   CrossChain:       ${crossChainAddress}`);
  console.log(`   Arbitrator:       ${arbitratorAddress}`);
  console.log(`   LZ Endpoint:      ${lzEndpointAddress}`);

  console.log("\n🔗 Block Explorer Links:");
  console.log(`   PolicyEngine:     ${getExplorerUrl(networkName, policyEngineAddress)}`);
  console.log(`   DisputeResolver:  ${getExplorerUrl(networkName, disputeResolverAddress)}`);
  console.log(`   CrossChain:       ${getExplorerUrl(networkName, crossChainAddress)}`);

  console.log("\n📁 Deployment saved to:", `deployments/${filename}`);

  console.log("\n============================================================");
  console.log("NEXT STEPS");
  console.log("============================================================");
  console.log("1. Verify contracts on block explorer:");
  console.log(`   npx hardhat verify --network ${networkName} ${policyEngineAddress}`);
  console.log("");
  console.log("2. Update frontend with new addresses:");
  console.log(`   NEXT_PUBLIC_POLICY_ENGINE=${policyEngineAddress}`);
  console.log(`   NEXT_PUBLIC_CROSS_CHAIN=${crossChainAddress}`);
  console.log("");
  console.log("3. Test a transaction:");
  console.log(`   npx hardhat run scripts/test-testnet.cjs --network ${networkName}`);
}

function getExplorerUrl(network, address) {
  const explorers = {
    sepolia: `https://sepolia.etherscan.io/address/${address}`,
    polygonAmoy: `https://amoy.polygonscan.com/address/${address}`,
    arbitrumSepolia: `https://sepolia.arbiscan.io/address/${address}`,
    baseSepolia: `https://sepolia.basescan.org/address/${address}`
  };
  return explorers[network] || `Unknown network: ${network}`;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
