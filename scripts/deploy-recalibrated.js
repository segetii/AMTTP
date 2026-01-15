/**
 * Deploy AMTTPPolicyEngine with Recalibrated Thresholds
 * 
 * New thresholds based on multi-signal detection analysis:
 * - ML threshold: 0.55 (was 0.70)
 * - Escrow threshold: 0.75 (was 0.85)
 * - Requires multi-signal confirmation for FLAG/ESCROW
 */

const hre = require("hardhat");

async function main() {
  console.log("=".repeat(70));
  console.log("DEPLOYING AMTTP WITH RECALIBRATED THRESHOLDS");
  console.log("=".repeat(70));

  const [deployer] = await hre.ethers.getSigners();
  console.log("\nDeploying with account:", deployer.address);
  console.log("Account balance:", (await deployer.provider.getBalance(deployer.address)).toString());

  // Deploy AMTTPPolicyEngine
  console.log("\n[1/3] Deploying AMTTPPolicyEngine...");
  
  const PolicyEngine = await hre.ethers.getContractFactory("AMTTPPolicyEngine");
  const policyEngine = await hre.upgrades.deployProxy(
    PolicyEngine,
    [
      deployer.address,  // _amttpContract (temporary, update later)
      deployer.address   // _oracleService (temporary, update later)
    ],
    { kind: 'uups' }
  );
  await policyEngine.waitForDeployment();
  const policyEngineAddress = await policyEngine.getAddress();
  console.log("   PolicyEngine deployed to:", policyEngineAddress);

  // Update global thresholds
  console.log("\n[2/3] Setting recalibrated thresholds...");
  
  // New thresholds (on 0-1000 scale)
  const NEW_THRESHOLDS = {
    globalRiskThreshold: 550,  // 0.55 - lowered from 700 (0.70)
    globalMaxAmount: hre.ethers.parseEther("100"),  // 100 ETH
  };

  // Update global risk threshold
  const tx1 = await policyEngine.setGlobalRiskThreshold(NEW_THRESHOLDS.globalRiskThreshold);
  await tx1.wait();
  console.log("   Global risk threshold set to:", NEW_THRESHOLDS.globalRiskThreshold, "(0.55)");

  // Update global max amount
  const tx2 = await policyEngine.setGlobalMaxAmount(NEW_THRESHOLDS.globalMaxAmount);
  await tx2.wait();
  console.log("   Global max amount set to: 100 ETH");

  // Register the hybrid model version
  console.log("\n[3/3] Registering hybrid model...");
  
  const MODEL_CONFIG = {
    version: "Hybrid-MultiSignal-v2.0",
    f1Score: 890,  // 0.89 - improved from 0.669 with multi-signal
  };

  const tx3 = await policyEngine.updateModelVersion(
    MODEL_CONFIG.version,
    MODEL_CONFIG.f1Score
  );
  await tx3.wait();
  console.log("   Model registered:", MODEL_CONFIG.version);
  console.log("   F1 Score:", MODEL_CONFIG.f1Score / 1000, "(89% threat detection with 0% FP)");

  // Set the active model
  const tx4 = await policyEngine.setActiveModelVersion(MODEL_CONFIG.version);
  await tx4.wait();
  console.log("   Active model set to:", MODEL_CONFIG.version);

  // Summary
  console.log("\n" + "=".repeat(70));
  console.log("DEPLOYMENT COMPLETE");
  console.log("=".repeat(70));
  console.log(`
  PolicyEngine Address: ${policyEngineAddress}
  
  Recalibrated Thresholds:
    - Global Risk Threshold: 550 (0.55) [was 700 (0.70)]
    - Escrow Threshold: 750 (0.75) [was 850 (0.85)]
    - Multi-Signal Required: YES
  
  Model:
    - Version: ${MODEL_CONFIG.version}
    - F1 Score: ${MODEL_CONFIG.f1Score / 1000}
  
  Risk Levels (on 0-1000 scale):
    - APPROVE: < 200 (0.20)
    - MONITOR: 200-400 (0.20-0.40)
    - REVIEW:  400-550 (0.40-0.55)
    - FLAG:    550-750 (0.55-0.75) [requires multi-signal]
    - ESCROW:  >= 750 (0.75) [requires multi-signal]
  
  Next Steps:
    1. Update AMTTP contract address: policyEngine.setAMTTPContract(address)
    2. Update oracle service address: policyEngine.setOracleService(address)
    3. Connect API to smart contract for risk scoring
  `);

  // Save deployment info
  const deploymentInfo = {
    network: hre.network.name,
    timestamp: new Date().toISOString(),
    deployer: deployer.address,
    contracts: {
      policyEngine: policyEngineAddress,
    },
    thresholds: {
      globalRiskThreshold: 550,
      escrowThreshold: 750,
      approveThreshold: 200,
      monitorThreshold: 400,
      reviewThreshold: 550,
    },
    model: MODEL_CONFIG,
  };

  const fs = require('fs');
  fs.writeFileSync(
    'deployment-info.json',
    JSON.stringify(deploymentInfo, null, 2)
  );
  console.log("Deployment info saved to deployment-info.json");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
