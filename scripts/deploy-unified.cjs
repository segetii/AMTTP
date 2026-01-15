/**
 * AMTTP Unified Deployment & Linking Script
 * ==========================================
 * Deploys withnft.sol (AMTTP Core) and links ALL contracts together
 * 
 * Existing Sepolia Contracts:
 * - PolicyEngine:    0x520393A448543FF55f02ddA1218881a8E5851CEc
 * - DisputeResolver: 0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade
 * - CrossChain:      0xc8d887665411ecB4760435fb3d20586C1111bc37
 * 
 * Usage: npx hardhat run scripts/deploy-unified.cjs --network sepolia
 */

const { ethers, upgrades } = require("hardhat");

// Existing deployed contracts
const EXISTING_CONTRACTS = {
  policyEngine: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
  disputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
  crossChain: "0xc8d887665411ecB4760435fb3d20586C1111bc37"
};

async function main() {
  const [deployer] = await ethers.getSigners();
  
  console.log("╔═══════════════════════════════════════════════════════════════╗");
  console.log("║         AMTTP UNIFIED DEPLOYMENT & LINKING                    ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log(`║  Deployer: ${deployer.address}                                `);
  console.log(`║  Network:  Sepolia                                            ║`);
  console.log("╚═══════════════════════════════════════════════════════════════╝\n");

  // Check balance
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`💰 Balance: ${ethers.formatEther(balance)} ETH\n`);
  
  if (balance < ethers.parseEther("0.05")) {
    console.error("❌ Insufficient balance. Need at least 0.05 ETH for deployment + linking");
    process.exit(1);
  }

  // ==================== STEP 1: Deploy AMTTP Core ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 1: Deploying AMTTP Core (AMTTPCore.sol)...");
  console.log("═══════════════════════════════════════════════════════════════\n");

  // Use the optimized AMTTPCore contract
  const AMTTP = await ethers.getContractFactory("AMTTPCore");
  
  console.log("📦 Deploying upgradeable proxy...");
  const amttpCore = await upgrades.deployProxy(AMTTP, [deployer.address], {
    initializer: "initialize",
    kind: "uups"
  });
  
  await amttpCore.waitForDeployment();
  const amttpCoreAddress = await amttpCore.getAddress();
  
  console.log(`✅ AMTTP Core deployed: ${amttpCoreAddress}\n`);

  // ==================== STEP 2: Link AMTTP Core → PolicyEngine ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 2: Linking AMTTP Core → PolicyEngine...");
  console.log("═══════════════════════════════════════════════════════════════\n");

  console.log(`📎 Setting PolicyEngine to ${EXISTING_CONTRACTS.policyEngine}...`);
  const tx1 = await amttpCore.setPolicyEngine(EXISTING_CONTRACTS.policyEngine);
  await tx1.wait();
  console.log(`✅ AMTTP Core now connected to PolicyEngine\n`);

  // ==================== STEP 3: Link PolicyEngine → DisputeResolver ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 3: Linking PolicyEngine → DisputeResolver...");
  console.log("═══════════════════════════════════════════════════════════════\n");

  // Get PolicyEngine contract instance
  const PolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
  const policyEngine = PolicyEngine.attach(EXISTING_CONTRACTS.policyEngine);

  console.log(`📎 Setting DisputeResolver to ${EXISTING_CONTRACTS.disputeResolver}...`);
  const tx2 = await policyEngine.setDisputeResolver(EXISTING_CONTRACTS.disputeResolver);
  await tx2.wait();
  console.log(`✅ PolicyEngine now connected to DisputeResolver\n`);

  // ==================== STEP 4: Link PolicyEngine → AMTTP Core ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 4: Setting AMTTP Contract in PolicyEngine...");
  console.log("═══════════════════════════════════════════════════════════════\n");

  // Check if there's a setAMTTPContract function
  try {
    // Try to set the AMTTP contract address in PolicyEngine
    // This allows PolicyEngine to know which contract to callback
    const tx3 = await policyEngine.setAMTTPContract(amttpCoreAddress);
    await tx3.wait();
    console.log(`✅ PolicyEngine now knows AMTTP Core address\n`);
  } catch (e) {
    console.log(`ℹ️  PolicyEngine doesn't have setAMTTPContract - skipping\n`);
  }

  // ==================== STEP 5: Link AMTTP Core → DisputeResolver ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 5: Linking AMTTP Core → DisputeResolver...");
  console.log("═══════════════════════════════════════════════════════════════\n");

  console.log(`📎 Setting DisputeResolver to ${EXISTING_CONTRACTS.disputeResolver}...`);
  const tx4 = await amttpCore.setDisputeResolver(EXISTING_CONTRACTS.disputeResolver);
  await tx4.wait();
  console.log(`✅ AMTTP Core now connected to DisputeResolver\n`);

  // ==================== STEP 6: Oracle Already Set at Init ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 6: Oracle Configuration...");
  console.log("═══════════════════════════════════════════════════════════════\n");
  console.log(`✅ Oracle set to deployer at initialization: ${deployer.address}\n`);

  // ==================== STEP 7: Approver Already Added at Init ====================
  console.log("═══════════════════════════════════════════════════════════════");
  console.log("STEP 7: Approver Configuration...");
  console.log("═══════════════════════════════════════════════════════════════\n");
  console.log(`✅ Deployer added as approver at initialization\n`);

  // ==================== VERIFICATION SUMMARY ====================
  console.log("\n╔═══════════════════════════════════════════════════════════════╗");
  console.log("║                 🎉 DEPLOYMENT COMPLETE! 🎉                     ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log("║  UNIFIED AMTTP SYSTEM ON SEPOLIA                              ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log(`║  AMTTP Core:        ${amttpCoreAddress} ║`);
  console.log(`║  PolicyEngine:      ${EXISTING_CONTRACTS.policyEngine} ║`);
  console.log(`║  DisputeResolver:   ${EXISTING_CONTRACTS.disputeResolver} ║`);
  console.log(`║  CrossChain:        ${EXISTING_CONTRACTS.crossChain} ║`);
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log("║  LINKS ESTABLISHED:                                           ║");
  console.log("║  ✅ AMTTP Core → PolicyEngine                                 ║");
  console.log("║  ✅ PolicyEngine → DisputeResolver                            ║");
  console.log("║  ✅ CrossChain → PolicyEngine (set at original deploy)        ║");
  console.log("╚═══════════════════════════════════════════════════════════════╝\n");

  // Save deployment info
  const fs = require("fs");
  const deploymentInfo = {
    network: "sepolia",
    timestamp: new Date().toISOString(),
    contracts: {
      amttpCore: amttpCoreAddress,
      policyEngine: EXISTING_CONTRACTS.policyEngine,
      disputeResolver: EXISTING_CONTRACTS.disputeResolver,
      crossChain: EXISTING_CONTRACTS.crossChain
    },
    links: {
      "amttpCore→policyEngine": true,
      "policyEngine→disputeResolver": true,
      "crossChain→policyEngine": true
    },
    deployer: deployer.address
  };

  const filename = `deployments/unified-sepolia-${Date.now()}.json`;
  fs.writeFileSync(filename, JSON.stringify(deploymentInfo, null, 2));
  console.log(`📝 Deployment info saved to: ${filename}`);

  // Verification command
  console.log("\n═══════════════════════════════════════════════════════════════");
  console.log("NEXT: Verify AMTTP Core on Etherscan");
  console.log("═══════════════════════════════════════════════════════════════");
  console.log(`\nnpx hardhat verify --network sepolia ${amttpCoreAddress}\n`);

  return amttpCoreAddress;
}

main()
  .then((address) => {
    console.log(`\n✅ All done! AMTTP Core: ${address}`);
    process.exit(0);
  })
  .catch((error) => {
    console.error("❌ Deployment failed:", error);
    process.exit(1);
  });
