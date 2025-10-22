// scripts/deploy-policy-engine.js
const { ethers, upgrades } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("Deploying Policy Engine with the account:", deployer.address);
  console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());

  // Deploy the AMTTP contract first (if not already deployed)
  const amttpAddress = process.env.AMTTP_ADDRESS || "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"; // Default hardhat address
  const oracleServiceAddress = process.env.ORACLE_SERVICE_ADDRESS || deployer.address; // Use deployer as fallback

  console.log("AMTTP Contract Address:", amttpAddress);
  console.log("Oracle Service Address:", oracleServiceAddress);

  // Deploy AMTTPPolicyEngine as upgradeable proxy
  const AMTTPPolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
  console.log("Deploying AMTTPPolicyEngine...");

  const policyEngine = await upgrades.deployProxy(
    AMTTPPolicyEngine,
    [amttpAddress, oracleServiceAddress],
    { 
      initializer: 'initialize',
      kind: 'uups'
    }
  );

  await policyEngine.waitForDeployment();

  const policyEngineAddress = await policyEngine.getAddress();
  console.log("AMTTPPolicyEngine Proxy deployed to:", policyEngineAddress);
  console.log("Implementation address:", await upgrades.erc1967.getImplementationAddress(policyEngineAddress));

  // Set up default policies for testing
  console.log("\nSetting up default policies...");
  
  // Set default risk policy with DQN model thresholds
  const defaultRiskPolicy = {
    thresholds: [200, 400, 700, 1000], // 0.20, 0.40, 0.70, 1.00
    actions: [0, 0, 1, 2], // Approve, Approve, Review, Escrow
    adaptiveThresholds: false
  };

  await policyEngine.setRiskPolicy(
    deployer.address,
    defaultRiskPolicy.thresholds,
    defaultRiskPolicy.actions,
    defaultRiskPolicy.adaptiveThresholds
  );

  // Set default transaction policy
  await policyEngine.setTransactionPolicy(
    deployer.address,
    ethers.parseEther("10"), // maxAmount: 10 ETH
    ethers.parseEther("50"), // dailyLimit: 50 ETH
    ethers.parseEther("200"), // weeklyLimit: 200 ETH
    ethers.parseEther("500"), // monthlyLimit: 500 ETH
    700, // riskThreshold: 0.70
    true, // autoApprove
    3600 // cooldownPeriod: 1 hour
  );

  // Set compliance rules
  await policyEngine.setComplianceRules(
    deployer.address,
    true, // requireKYC
    false, // requireApproval
    ethers.parseEther("5"), // approvalThreshold: 5 ETH
    3600, // approvalTimeout: 1 hour
    false // geofencing
  );

  // Add a velocity limit
  await policyEngine.addVelocityLimit(
    deployer.address,
    10, // maxTransactions per day
    ethers.parseEther("100"), // maxVolume per day
    1 // VelocityWindow.Day
  );

  console.log("✅ Default policies configured for deployer address");

  // If AMTTP contract exists, connect policy engine
  try {
    const amttp = await ethers.getContractAt("AMTTP", amttpAddress);
    const currentOwner = await amttp.owner();
    
    if (currentOwner.toLowerCase() === deployer.address.toLowerCase()) {
      console.log("\nConnecting Policy Engine to AMTTP contract...");
      await amttp.setPolicyEngine(policyEngineAddress);
      console.log("✅ Policy Engine connected to AMTTP contract");
    } else {
      console.log("⚠️ Cannot connect Policy Engine - deployer is not owner of AMTTP contract");
      console.log("Run this command as contract owner:");
      console.log(`amttp.setPolicyEngine("${policyEngineAddress}")`);
    }
  } catch (error) {
    console.log("⚠️ Could not connect to AMTTP contract:", error.message);
    console.log("Manually connect Policy Engine after AMTTP deployment:");
    console.log(`amttp.setPolicyEngine("${policyEngineAddress}")`);
  }

  // Display deployment summary
  console.log("\n" + "=".repeat(60));
  console.log("🎉 DEPLOYMENT COMPLETE!");
  console.log("=".repeat(60));
  console.log(`📋 AMTTPPolicyEngine: ${policyEngineAddress}`);
  console.log(`🔗 AMTTP Contract: ${amttpAddress}`);
  console.log(`🤖 Oracle Service: ${oracleServiceAddress}`);
  console.log(`⚡ Default Model: DQN-v1.0-real-fraud (F1=0.669+)`);
  console.log(`🎯 Global Risk Threshold: 0.70`);
  console.log(`📊 Policy Features: ✅ Risk Scoring ✅ Velocity Limits ✅ KYC ✅ Auto-Approval`);
  
  console.log("\n📋 Next Steps:");
  console.log("1. Update your oracle service to use Policy Engine validation");
  console.log("2. Configure user-specific policies via admin interface");
  console.log("3. Monitor transactions and risk scores");
  console.log("4. Integrate with your DQN model for real-time scoring");

  // Save deployment info
  const deploymentInfo = {
    network: (await ethers.provider.getNetwork()).name,
    policyEngine: policyEngineAddress,
    amttp: amttpAddress,
    oracleService: oracleServiceAddress,
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    features: {
      riskScoring: true,
      velocityLimits: true,
      kycIntegration: true,
      autoApproval: true,
      dqnModelVersion: "DQN-v1.0-real-fraud"
    }
  };

  const fs = require('fs');
  const deploymentPath = `./deployments/policy-engine-${Date.now()}.json`;
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n💾 Deployment info saved to: ${deploymentPath}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("❌ Deployment failed:", error);
    process.exit(1);
  });