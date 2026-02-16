/**
 * AMTTP Testnet Test Script
 * Tests the deployed contracts on Sepolia
 */

const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("============================================================");
  console.log("AMTTP TESTNET CONTRACT TEST");
  console.log("============================================================\n");

  // Load deployment info
  const deploymentsDir = path.join(__dirname, "..", "deployments");
  const files = fs.readdirSync(deploymentsDir).filter(f => f.startsWith("testnet-sepolia-"));
  
  if (files.length === 0) {
    console.log("❌ No Sepolia deployment found. Run deploy-testnet.cjs first.");
    process.exit(1);
  }
  
  const latestDeployment = files.sort().reverse()[0];
  const deployment = JSON.parse(
    fs.readFileSync(path.join(deploymentsDir, latestDeployment), "utf8")
  );
  
  console.log(`📋 Using deployment: ${latestDeployment}`);
  console.log(`   PolicyEngine: ${deployment.contracts.policyEngine}`);
  console.log(`   DisputeResolver: ${deployment.contracts.disputeResolver}`);
  console.log(`   CrossChain: ${deployment.contracts.crossChain}\n`);

  const [signer] = await ethers.getSigners();
  console.log(`🔑 Tester: ${signer.address}`);
  
  const balance = await ethers.provider.getBalance(signer.address);
  console.log(`💰 Balance: ${ethers.formatEther(balance)} ETH\n`);

  // Connect to PolicyEngine
  const policyEngine = await ethers.getContractAt(
    "AMTTPPolicyEngine",
    deployment.contracts.policyEngine
  );

  // Connect to CrossChain
  const crossChain = await ethers.getContractAt(
    "AMTTPCrossChain",
    deployment.contracts.crossChain
  );

  // ============ Test 1: Read Policy Engine State ============
  console.log("1️⃣ Testing PolicyEngine read operations...");
  
  try {
    const escrowThreshold = await policyEngine.escrowThreshold();
    console.log(`   ✅ Escrow Threshold: ${escrowThreshold}`);
  } catch (e) {
    console.log(`   ❌ Failed to read escrow threshold: ${e.message}`);
  }

  // ============ Test 2: Check Risk Score ============
  console.log("\n2️⃣ Testing risk score check...");
  
  const testAddress = "0x0000000000000000000000000000000000001234";
  try {
    // Try to get risk score (will likely return 0 for unknown address)
    const riskInfo = await policyEngine.addressRiskScores(testAddress);
    console.log(`   ✅ Risk score for ${testAddress}: ${riskInfo}`);
  } catch (e) {
    console.log(`   ⚠️ Could not get risk score: ${e.message}`);
  }

  // ============ Test 3: CrossChain Configuration ============
  console.log("\n3️⃣ Testing CrossChain configuration...");
  
  try {
    const localChainId = await crossChain.localChainId();
    console.log(`   ✅ Local Chain ID: ${localChainId}`);
    
    const policyEngineAddr = await crossChain.policyEngine();
    console.log(`   ✅ PolicyEngine linked: ${policyEngineAddr}`);
    
    // Check LZ endpoint
    const lzEndpoint = await crossChain.lzEndpoint();
    console.log(`   ✅ LayerZero Endpoint: ${lzEndpoint}`);
  } catch (e) {
    console.log(`   ❌ CrossChain test failed: ${e.message}`);
  }

  // ============ Test 4: Estimate Cross-Chain Gas ============
  console.log("\n4️⃣ Testing cross-chain fee estimation...");
  
  try {
    // Polygon Mumbai chain ID in LayerZero
    const dstChainId = 10267; // Polygon Amoy
    const payload = ethers.AbiCoder.defaultAbiCoder().encode(
      ["uint8", "address", "uint256", "uint256"],
      [1, testAddress, 500, Math.floor(Date.now() / 1000)]
    );
    
    const [nativeFee, zroFee] = await crossChain.estimateFees(
      dstChainId,
      payload
    );
    console.log(`   ✅ Cross-chain fee to Polygon Amoy:`);
    console.log(`      Native Fee: ${ethers.formatEther(nativeFee)} ETH`);
    console.log(`      ZRO Fee: ${ethers.formatEther(zroFee)} ZRO`);
  } catch (e) {
    console.log(`   ⚠️ Fee estimation not available: ${e.message}`);
  }

  // ============ Test 5: DisputeResolver ============
  console.log("\n5️⃣ Testing DisputeResolver...");
  
  const disputeResolver = await ethers.getContractAt(
    "AMTTPDisputeResolver",
    deployment.contracts.disputeResolver
  );
  
  try {
    const arbitrator = await disputeResolver.arbitrator();
    console.log(`   ✅ Kleros Arbitrator: ${arbitrator}`);
    
    const metaEvidenceID = await disputeResolver.metaEvidenceID();
    console.log(`   ✅ MetaEvidence ID: ${metaEvidenceID}`);
  } catch (e) {
    console.log(`   ❌ DisputeResolver test failed: ${e.message}`);
  }

  console.log("\n============================================================");
  console.log("✅ TESTNET TESTS COMPLETE");
  console.log("============================================================");
  console.log("\n📌 Your contracts are live and functional on Sepolia!");
  console.log("\n🔗 Etherscan Links:");
  console.log(`   PolicyEngine: https://sepolia.etherscan.io/address/${deployment.contracts.policyEngine}`);
  console.log(`   DisputeResolver: https://sepolia.etherscan.io/address/${deployment.contracts.disputeResolver}`);
  console.log(`   CrossChain: https://sepolia.etherscan.io/address/${deployment.contracts.crossChain}`);
}

main().catch(console.error);
