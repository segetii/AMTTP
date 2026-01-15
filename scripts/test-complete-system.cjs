/**
 * AMTTP Complete Unified System - Integration Test
 * 
 * Tests all 6 contracts working together:
 * - AMTTPRouter (unified entry point)
 * - AMTTPCore (ETH/ERC20 escrow)
 * - AMTTPNFT (ERC721 escrow)
 * - PolicyEngine (risk assessment)
 * - DisputeResolver (Kleros arbitration)
 * - CrossChain (LayerZero)
 * 
 * Usage: npx hardhat run scripts/test-complete-system.cjs --network sepolia
 */

const { ethers } = require("hardhat");

// All deployed contract addresses (Sepolia)
const CONTRACTS = {
    router: "0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3",
    core: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
    nft: "0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f",
    policyEngine: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
    disputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
    crossChain: "0xc8d887665411ecB4760435fb3d20586C1111bc37"
};

// Kleros Sepolia address
const KLEROS_ARBITRATOR = "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8";

async function main() {
    const [tester] = await ethers.getSigners();
    
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║      AMTTP COMPLETE SYSTEM - INTEGRATION TEST                 ║
╠═══════════════════════════════════════════════════════════════╣
║  Tester: ${tester.address}
║  Network: Sepolia                                             ║
╚═══════════════════════════════════════════════════════════════╝
`);

    let passed = 0;
    let failed = 0;

    // ════════════════════════════════════════════════════════════════
    // TEST 1: Router Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("─────────────────────────────────────────────────────────────────");
    console.log("TEST 1: AMTTPRouter Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const router = await ethers.getContractAt("AMTTPRouter", CONTRACTS.router);
        const [core, nft, policy, crossChain, dispute] = await router.getContractAddresses();
        
        console.log(`  Core:           ${core}`);
        console.log(`  NFT:            ${nft}`);
        console.log(`  PolicyEngine:   ${policy}`);
        console.log(`  CrossChain:     ${crossChain}`);
        console.log(`  Dispute:        ${dispute}`);

        const coreMatch = core.toLowerCase() === CONTRACTS.core.toLowerCase();
        const nftMatch = nft.toLowerCase() === CONTRACTS.nft.toLowerCase();
        const policyMatch = policy.toLowerCase() === CONTRACTS.policyEngine.toLowerCase();
        
        if (coreMatch && nftMatch && policyMatch) {
            console.log("\n  ✅ Router properly configured with all contracts");
            passed++;
        } else {
            console.log("\n  ❌ Router configuration mismatch");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 2: AMTTPNFT Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 2: AMTTPNFT Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const nft = await ethers.getContractAt("AMTTPNFT", CONTRACTS.nft);
        
        const routerAddr = await nft.router();
        const policyAddr = await nft.policyEngine();
        const oracleAddr = await nft.oracle();
        const threshold = await nft.globalRiskThreshold();
        const modelVersion = await nft.activeModelVersion();
        
        console.log(`  Router:          ${routerAddr}`);
        console.log(`  PolicyEngine:    ${policyAddr}`);
        console.log(`  Oracle:          ${oracleAddr}`);
        console.log(`  Risk Threshold:  ${threshold}`);
        console.log(`  Model Version:   ${modelVersion}`);

        const routerMatch = routerAddr.toLowerCase() === CONTRACTS.router.toLowerCase();
        const policyMatch = policyAddr.toLowerCase() === CONTRACTS.policyEngine.toLowerCase();
        
        if (routerMatch && policyMatch) {
            console.log("\n  ✅ AMTTPNFT properly configured");
            passed++;
        } else {
            console.log("\n  ❌ AMTTPNFT configuration mismatch");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 3: AMTTPCore Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 3: AMTTPCore Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const core = await ethers.getContractAt("AMTTPCore", CONTRACTS.core);
        const [policyAddr, disputeAddr, oracleAddr, policyEnabled, threshold, modelVersion] = 
            await core.getContractStatus();
        
        console.log(`  PolicyEngine:     ${policyAddr}`);
        console.log(`  DisputeResolver:  ${disputeAddr}`);
        console.log(`  Oracle:           ${oracleAddr}`);
        console.log(`  Policy Enabled:   ${policyEnabled}`);
        console.log(`  Risk Threshold:   ${threshold}`);
        console.log(`  Model Version:    ${modelVersion}`);

        if (policyAddr.toLowerCase() === CONTRACTS.policyEngine.toLowerCase() &&
            disputeAddr.toLowerCase() === CONTRACTS.disputeResolver.toLowerCase()) {
            console.log("\n  ✅ AMTTPCore properly configured");
            passed++;
        } else {
            console.log("\n  ❌ AMTTPCore configuration mismatch");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 4: PolicyEngine Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 4: PolicyEngine Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const policy = await ethers.getContractAt("AMTTPPolicyEngine", CONTRACTS.policyEngine);
        const owner = await policy.owner();
        const disputeResolver = await policy.disputeResolver();
        const threshold = await policy.globalRiskThreshold();
        
        console.log(`  Owner:            ${owner}`);
        console.log(`  DisputeResolver:  ${disputeResolver}`);
        console.log(`  Global Threshold: ${threshold}`);

        if (disputeResolver.toLowerCase() === CONTRACTS.disputeResolver.toLowerCase()) {
            console.log("\n  ✅ PolicyEngine properly configured");
            passed++;
        } else {
            console.log("\n  ❌ PolicyEngine configuration mismatch");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 5: DisputeResolver Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 5: DisputeResolver (Kleros) Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const dispute = await ethers.getContractAt("AMTTPDisputeResolver", CONTRACTS.disputeResolver);
        const arbitrator = await dispute.arbitrator();
        const owner = await dispute.owner();
        
        console.log(`  Owner:      ${owner}`);
        console.log(`  Arbitrator: ${arbitrator}`);
        console.log(`  (Kleros Sepolia: ${KLEROS_ARBITRATOR})`);

        if (arbitrator.toLowerCase() === KLEROS_ARBITRATOR.toLowerCase()) {
            console.log("\n  ✅ DisputeResolver connected to Kleros");
            passed++;
        } else {
            console.log("\n  ❌ DisputeResolver not connected to Kleros");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 6: CrossChain Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 6: CrossChain (LayerZero) Configuration");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const crossChain = await ethers.getContractAt("AMTTPCrossChain", CONTRACTS.crossChain);
        const owner = await crossChain.owner();
        const lzEndpoint = await crossChain.lzEndpoint();
        const policyEngine = await crossChain.policyEngine();
        
        console.log(`  Owner:         ${owner}`);
        console.log(`  LZ Endpoint:   ${lzEndpoint}`);
        console.log(`  PolicyEngine:  ${policyEngine}`);

        if (policyEngine.toLowerCase() === CONTRACTS.policyEngine.toLowerCase()) {
            console.log("\n  ✅ CrossChain connected to PolicyEngine");
            passed++;
        } else {
            console.log("\n  ❌ CrossChain not properly configured");
            failed++;
        }
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // TEST 7: Router Analytics
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("TEST 7: Router Analytics");
    console.log("─────────────────────────────────────────────────────────────────");

    try {
        const router = await ethers.getContractAt("AMTTPRouter", CONTRACTS.router);
        const [totalSwaps, completed, volumeETH, volumeERC20, nftSwaps] = 
            await router.getProtocolStats();
        
        console.log(`  Total Swaps:     ${totalSwaps}`);
        console.log(`  Completed:       ${completed}`);
        console.log(`  ETH Volume:      ${ethers.formatEther(volumeETH)} ETH`);
        console.log(`  ERC20 Volume:    ${volumeERC20}`);
        console.log(`  NFT Swaps:       ${nftSwaps}`);

        console.log("\n  ✅ Router analytics working");
        passed++;
    } catch (e) {
        console.log(`  ❌ Error: ${e.message}`);
        failed++;
    }

    // ════════════════════════════════════════════════════════════════
    // SUMMARY
    // ════════════════════════════════════════════════════════════════
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║                    TEST SUMMARY                                ║
╠═══════════════════════════════════════════════════════════════╣
║  ✅ Passed: ${passed}/7                                                   ║
║  ❌ Failed: ${failed}/7                                                   ║
╠═══════════════════════════════════════════════════════════════╣`);

    if (failed === 0) {
        console.log(`║  🎉 ALL TESTS PASSED - COMPLETE SYSTEM INTEGRATED! 🎉        ║`);
    } else {
        console.log(`║  ⚠️  Some tests failed - check configuration above           ║`);
    }
    
    console.log(`╚═══════════════════════════════════════════════════════════════╝`);

    // ════════════════════════════════════════════════════════════════
    // ARCHITECTURE DIAGRAM
    // ════════════════════════════════════════════════════════════════
    console.log(`

╔═══════════════════════════════════════════════════════════════╗
║           AMTTP COMPLETE UNIFIED ARCHITECTURE                  ║
╚═══════════════════════════════════════════════════════════════╝

                    ┌────────────────────────┐
                    │     User / Frontend    │
                    │     MetaMask Snap      │
                    └───────────┬────────────┘
                                │
                                ▼
        ┌───────────────────────────────────────────────────┐
        │                  AMTTPRouter                       │
        │        ${CONTRACTS.router}         │
        │   • Unified API (ETH, ERC20, NFT)                 │
        │   • Protocol Analytics                            │
        │   • Swap Type Routing                             │
        └───────────┬─────────────────────┬─────────────────┘
                    │                     │
        ┌───────────▼─────────┐  ┌────────▼────────────┐
        │     AMTTPCore       │  │      AMTTPNFT       │
        │     ETH/ERC20       │  │     ERC721/NFT      │
        │ ${CONTRACTS.core.slice(0,18)}... │  │ ${CONTRACTS.nft.slice(0,18)}... │
        │ • HTLC Escrow       │  │ • NFT-to-ETH Swaps  │
        │ • Oracle Sigs       │  │ • NFT-to-NFT Swaps  │
        │ • User Limits       │  │ • HTLC Escrow       │
        └───────────┬─────────┘  └────────┬────────────┘
                    │                     │
        ┌───────────▼─────────────────────▼─────────────────┐
        │                PolicyEngine                        │
        │        ${CONTRACTS.policyEngine}         │
        │   • ML Risk Assessment (DQN Model)                │
        │   • User Policies & KYC                           │
        │   • Transaction Validation                        │
        └───────────┬───────────────────────────────────────┘
                    │
        ┌───────────▼───────────────────────────────────────┐
        │            DisputeResolver (Kleros)                │
        │        ${CONTRACTS.disputeResolver}         │
        │   • Jury Arbitration                              │
        │   • Evidence Submission                           │
        │   • Ruling Execution                              │
        └───────────────────────────────────────────────────┘
                    │
        ┌───────────▼───────────────────────────────────────┐
        │           CrossChain (LayerZero)                   │
        │        ${CONTRACTS.crossChain}         │
        │   • 7-Chain Risk Sync                             │
        │   • Global Blocking                               │
        │   • Cross-Chain Messaging                         │
        └───────────────────────────────────────────────────┘


SUPPORTED OPERATIONS via Router:
────────────────────────────────
  router.swapETH()           - ETH escrow swap
  router.swapERC20()         - ERC20 token swap
  router.swapNFTforETH()     - Sell NFT for ETH
  router.swapNFTforNFT()     - NFT-to-NFT atomic swap
  router.completeSwap()      - Complete any swap type
  router.refundSwap()        - Refund any swap type
  router.approveSwap()       - Approve high-risk swap
  router.raiseDispute()      - Escalate to Kleros
  router.syncRiskToChain()   - Cross-chain risk sync
  router.getProtocolStats()  - View analytics
`);
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error("Error:", error);
        process.exit(1);
    });
