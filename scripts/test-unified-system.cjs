/**
 * AMTTP Unified System Integration Test
 * ======================================
 * Tests that all contracts are properly linked and functional
 * 
 * Usage: npx hardhat run scripts/test-unified-system.cjs --network sepolia
 */

const { ethers } = require("hardhat");

// Deployed contract addresses
const CONTRACTS = {
  amttpCore: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
  policyEngine: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
  disputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
  crossChain: "0xc8d887665411ecB4760435fb3d20586C1111bc37"
};

async function main() {
  const [deployer] = await ethers.getSigners();
  
  console.log("╔═══════════════════════════════════════════════════════════════╗");
  console.log("║         AMTTP UNIFIED SYSTEM - INTEGRATION TEST               ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log(`║  Tester: ${deployer.address}`);
  console.log(`║  Network: Sepolia                                             ║`);
  console.log("╚═══════════════════════════════════════════════════════════════╝\n");

  let passed = 0;
  let failed = 0;

  // ==================== Test 1: AMTTP Core Status ====================
  console.log("─────────────────────────────────────────────────────────────────");
  console.log("TEST 1: AMTTP Core Configuration");
  console.log("─────────────────────────────────────────────────────────────────");
  
  try {
    const AMTTPCore = await ethers.getContractFactory("AMTTPCore");
    const amttpCore = AMTTPCore.attach(CONTRACTS.amttpCore);
    
    const status = await amttpCore.getContractStatus();
    console.log(`  PolicyEngine:     ${status._policyEngine}`);
    console.log(`  DisputeResolver:  ${status._disputeResolver}`);
    console.log(`  Oracle:           ${status._oracle}`);
    console.log(`  Policy Enabled:   ${status._policyEnabled}`);
    console.log(`  Risk Threshold:   ${status._riskThreshold}`);
    console.log(`  Model Version:    ${status._modelVersion}`);
    
    // Verify links
    const policyEngineLinked = status._policyEngine.toLowerCase() === CONTRACTS.policyEngine.toLowerCase();
    const disputeResolverLinked = status._disputeResolver.toLowerCase() === CONTRACTS.disputeResolver.toLowerCase();
    
    if (policyEngineLinked && disputeResolverLinked) {
      console.log("\n  ✅ AMTTP Core properly configured");
      passed++;
    } else {
      console.log("\n  ❌ AMTTP Core links incorrect");
      failed++;
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    failed++;
  }

  // ==================== Test 2: PolicyEngine Status ====================
  console.log("\n─────────────────────────────────────────────────────────────────");
  console.log("TEST 2: PolicyEngine Configuration");
  console.log("─────────────────────────────────────────────────────────────────");
  
  try {
    const PolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
    const policyEngine = PolicyEngine.attach(CONTRACTS.policyEngine);
    
    const disputeResolver = await policyEngine.getDisputeResolver();
    const owner = await policyEngine.owner();
    const globalThreshold = await policyEngine.globalRiskThreshold();
    
    console.log(`  Owner:            ${owner}`);
    console.log(`  DisputeResolver:  ${disputeResolver}`);
    console.log(`  Global Threshold: ${globalThreshold}`);
    
    const disputeResolverLinked = disputeResolver.toLowerCase() === CONTRACTS.disputeResolver.toLowerCase();
    
    if (disputeResolverLinked) {
      console.log("\n  ✅ PolicyEngine properly configured");
      passed++;
    } else {
      console.log("\n  ❌ PolicyEngine DisputeResolver not linked");
      failed++;
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    failed++;
  }

  // ==================== Test 3: DisputeResolver Status ====================
  console.log("\n─────────────────────────────────────────────────────────────────");
  console.log("TEST 3: DisputeResolver Configuration");
  console.log("─────────────────────────────────────────────────────────────────");
  
  try {
    const DisputeResolver = await ethers.getContractFactory("AMTTPDisputeResolver");
    const disputeResolver = DisputeResolver.attach(CONTRACTS.disputeResolver);
    
    const arbitrator = await disputeResolver.arbitrator();
    const owner = await disputeResolver.owner();
    
    console.log(`  Owner:      ${owner}`);
    console.log(`  Arbitrator: ${arbitrator}`);
    console.log(`  (Kleros Sepolia: 0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8)`);
    
    if (arbitrator !== ethers.ZeroAddress) {
      console.log("\n  ✅ DisputeResolver connected to Kleros");
      passed++;
    } else {
      console.log("\n  ❌ Arbitrator not set");
      failed++;
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    failed++;
  }

  // ==================== Test 4: CrossChain Status ====================
  console.log("\n─────────────────────────────────────────────────────────────────");
  console.log("TEST 4: CrossChain Configuration");
  console.log("─────────────────────────────────────────────────────────────────");
  
  try {
    const CrossChain = await ethers.getContractFactory("AMTTPCrossChain");
    const crossChain = CrossChain.attach(CONTRACTS.crossChain);
    
    const lzEndpoint = await crossChain.lzEndpoint();
    const policyEngineAddr = await crossChain.policyEngine();
    const owner = await crossChain.owner();
    
    console.log(`  Owner:         ${owner}`);
    console.log(`  LZ Endpoint:   ${lzEndpoint}`);
    console.log(`  PolicyEngine:  ${policyEngineAddr}`);
    
    const policyEngineLinked = policyEngineAddr.toLowerCase() === CONTRACTS.policyEngine.toLowerCase();
    
    if (policyEngineLinked) {
      console.log("\n  ✅ CrossChain connected to PolicyEngine");
      passed++;
    } else {
      console.log("\n  ❌ CrossChain PolicyEngine not linked");
      failed++;
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    failed++;
  }

  // ==================== Test 5: Approver Configuration ====================
  console.log("\n─────────────────────────────────────────────────────────────────");
  console.log("TEST 5: Approver Configuration");
  console.log("─────────────────────────────────────────────────────────────────");
  
  try {
    const AMTTPCore = await ethers.getContractFactory("AMTTPCore");
    const amttpCore = AMTTPCore.attach(CONTRACTS.amttpCore);
    
    const approvers = await amttpCore.getApprovers();
    const threshold = await amttpCore.approvalThreshold();
    
    console.log(`  Approvers: ${approvers.length}`);
    for (const approver of approvers) {
      console.log(`    - ${approver}`);
    }
    console.log(`  Threshold: ${threshold}`);
    
    if (approvers.length > 0) {
      console.log("\n  ✅ Approvers configured");
      passed++;
    } else {
      console.log("\n  ❌ No approvers configured");
      failed++;
    }
  } catch (e) {
    console.log(`  ❌ Error: ${e.message}`);
    failed++;
  }

  // ==================== Summary ====================
  console.log("\n╔═══════════════════════════════════════════════════════════════╗");
  console.log("║                    TEST SUMMARY                                ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log(`║  ✅ Passed: ${passed}/5                                                   ║`);
  console.log(`║  ❌ Failed: ${failed}/5                                                   ║`);
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  
  if (failed === 0) {
    console.log("║  🎉 ALL TESTS PASSED - SYSTEM FULLY INTEGRATED! 🎉            ║");
  } else {
    console.log("║  ⚠️  SOME TESTS FAILED - CHECK CONFIGURATION                  ║");
  }
  
  console.log("╚═══════════════════════════════════════════════════════════════╝");

  // Print the unified architecture
  console.log("\n");
  console.log("╔═══════════════════════════════════════════════════════════════╗");
  console.log("║              AMTTP UNIFIED ARCHITECTURE                        ║");
  console.log("╚═══════════════════════════════════════════════════════════════╝");
  console.log("");
  console.log("                        ┌─────────────────┐");
  console.log("                        │    User/dApp    │");
  console.log("                        └────────┬────────┘");
  console.log("                                 │");
  console.log("                                 ▼");
  console.log("  ┌──────────────────────────────────────────────────────────┐");
  console.log("  │                    AMTTPCore (Escrow)                     │");
  console.log(`  │            ${CONTRACTS.amttpCore}             │`);
  console.log("  │  • ETH/ERC20 Escrow    • HTLC         • Oracle Sigs     │");
  console.log("  │  • Risk Assessment     • Approvals   • User Policies    │");
  console.log("  └─────────┬────────────────────┬───────────────────────────┘");
  console.log("            │                    │");
  console.log("            ▼                    ▼");
  console.log("  ┌─────────────────────┐  ┌─────────────────────┐");
  console.log("  │   PolicyEngine      │  │  DisputeResolver    │");
  console.log(`  │ ${CONTRACTS.policyEngine.slice(0, 20)}... │  │ ${CONTRACTS.disputeResolver.slice(0, 18)}... │`);
  console.log("  │ • Risk Thresholds   │  │ • Kleros Escrow     │");
  console.log("  │ • User Policies     │  │ • Jury Arbitration  │");
  console.log("  │ • DQN ML Model      │  │ • Evidence Submit   │");
  console.log("  └─────────┬───────────┘  └─────────────────────┘");
  console.log("            │");
  console.log("            ▼");
  console.log("  ┌─────────────────────┐");
  console.log("  │   CrossChain (LZ)   │");
  console.log(`  │ ${CONTRACTS.crossChain.slice(0, 20)}... │`);
  console.log("  │ • 7-Chain Support   │");
  console.log("  │ • Global Blocking   │");
  console.log("  │ • Risk Propagation  │");
  console.log("  └─────────────────────┘");
  console.log("");

  return { passed, failed };
}

main()
  .then(({ passed, failed }) => {
    process.exit(failed > 0 ? 1 : 0);
  })
  .catch((error) => {
    console.error("Test failed:", error);
    process.exit(1);
  });
