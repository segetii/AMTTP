/**
 * AMTTP Unified System - Complete Deployment Script
 * 
 * Deploys AMTTPNFT + AMTTPRouter and links everything together:
 * - AMTTPCore (already deployed)
 * - AMTTPNFT (new - NFT escrow)
 * - AMTTPRouter (new - unified entry point)
 * - PolicyEngine (already deployed)
 * - DisputeResolver (already deployed)
 * - CrossChain (already deployed)
 * 
 * Usage: npx hardhat run scripts/deploy-router.cjs --network sepolia
 */

const { ethers, upgrades } = require("hardhat");

// Already deployed contract addresses (Sepolia)
const DEPLOYED = {
    core: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
    policyEngine: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
    disputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
    crossChain: "0xc8d887665411ecB4760435fb3d20586C1111bc37"
};

async function main() {
    const [deployer] = await ethers.getSigners();
    const balance = await ethers.provider.getBalance(deployer.address);
    
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║       AMTTP UNIFIED SYSTEM - ROUTER DEPLOYMENT                ║
╠═══════════════════════════════════════════════════════════════╣
║  Deployer: ${deployer.address}
║  Balance:  ${ethers.formatEther(balance)} ETH
║  Network:  Sepolia                                            ║
╚═══════════════════════════════════════════════════════════════╝
`);

    // ════════════════════════════════════════════════════════════════
    // STEP 1: Deploy AMTTPNFT
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("STEP 1: Deploying AMTTPNFT (ERC721 Escrow)...");
    console.log("─────────────────────────────────────────────────────────────────");

    const AMTTPNFT = await ethers.getContractFactory("AMTTPNFT");
    const nft = await upgrades.deployProxy(AMTTPNFT, [deployer.address], {
        initializer: "initialize",
        kind: "uups"
    });
    await nft.waitForDeployment();
    const nftAddress = await nft.getAddress();
    
    console.log(`  ✅ AMTTPNFT deployed to: ${nftAddress}`);

    // ════════════════════════════════════════════════════════════════
    // STEP 2: Deploy AMTTPRouter
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("STEP 2: Deploying AMTTPRouter (Unified Entry Point)...");
    console.log("─────────────────────────────────────────────────────────────────");

    const AMTTPRouter = await ethers.getContractFactory("AMTTPRouter");
    const router = await upgrades.deployProxy(AMTTPRouter, [
        DEPLOYED.core,           // Core contract
        nftAddress,              // NFT contract
        DEPLOYED.policyEngine,   // PolicyEngine
        DEPLOYED.crossChain,     // CrossChain
        DEPLOYED.disputeResolver // DisputeResolver
    ], {
        initializer: "initialize",
        kind: "uups"
    });
    await router.waitForDeployment();
    const routerAddress = await router.getAddress();
    
    console.log(`  ✅ AMTTPRouter deployed to: ${routerAddress}`);

    // ════════════════════════════════════════════════════════════════
    // STEP 3: Configure AMTTPNFT
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("STEP 3: Configuring AMTTPNFT...");
    console.log("─────────────────────────────────────────────────────────────────");

    // Set router
    console.log("  Setting router on AMTTPNFT...");
    const tx1 = await nft.setRouter(routerAddress);
    await tx1.wait();
    console.log("  ✅ Router set");

    // Set PolicyEngine
    console.log("  Setting PolicyEngine on AMTTPNFT...");
    const tx2 = await nft.setPolicyEngine(DEPLOYED.policyEngine);
    await tx2.wait();
    console.log("  ✅ PolicyEngine set");

    // Set DisputeResolver
    console.log("  Setting DisputeResolver on AMTTPNFT...");
    const tx3 = await nft.setDisputeResolver(DEPLOYED.disputeResolver);
    await tx3.wait();
    console.log("  ✅ DisputeResolver set");

    // ════════════════════════════════════════════════════════════════
    // STEP 4: Verify Configuration
    // ════════════════════════════════════════════════════════════════
    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("STEP 4: Verifying Configuration...");
    console.log("─────────────────────────────────────────────────────────────────");

    // Check router configuration
    const [core, nftAddr, policy, crossChain, dispute] = await router.getContractAddresses();
    console.log(`
  Router Contract Addresses:
  • Core:           ${core}
  • NFT:            ${nftAddr}
  • PolicyEngine:   ${policy}
  • CrossChain:     ${crossChain}
  • Dispute:        ${dispute}
`);

    // Check NFT configuration
    const nftRouter = await nft.router();
    const nftPolicy = await nft.policyEngine();
    console.log(`
  AMTTPNFT Configuration:
  • Router:         ${nftRouter}
  • PolicyEngine:   ${nftPolicy}
`);

    // ════════════════════════════════════════════════════════════════
    // DEPLOYMENT SUMMARY
    // ════════════════════════════════════════════════════════════════
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║                  DEPLOYMENT COMPLETE!                          ║
╠═══════════════════════════════════════════════════════════════╣
║                                                                ║
║  NEW CONTRACTS:                                                ║
║  • AMTTPNFT:    ${nftAddress}     ║
║  • AMTTPRouter: ${routerAddress}     ║
║                                                                ║
║  EXISTING CONTRACTS:                                           ║
║  • AMTTPCore:        ${DEPLOYED.core}     ║
║  • PolicyEngine:     ${DEPLOYED.policyEngine}     ║
║  • DisputeResolver:  ${DEPLOYED.disputeResolver}     ║
║  • CrossChain:       ${DEPLOYED.crossChain}     ║
║                                                                ║
╚═══════════════════════════════════════════════════════════════╝

╔═══════════════════════════════════════════════════════════════╗
║              UNIFIED AMTTP ARCHITECTURE                        ║
╚═══════════════════════════════════════════════════════════════╝

                      ┌──────────────────────┐
                      │    User / Frontend   │
                      └──────────┬───────────┘
                                 │
                                 ▼
              ┌─────────────────────────────────────┐
              │          AMTTPRouter                │
              │      ${routerAddress}   │
              │  • Unified API for all swap types   │
              │  • Protocol analytics               │
              │  • Cross-contract coordination      │
              └─────────┬───────────────┬───────────┘
                        │               │
            ┌───────────▼───┐   ┌───────▼───────────┐
            │   AMTTPCore   │   │     AMTTPNFT      │
            │   ETH/ERC20   │   │   ERC721/NFTs     │
            │   ${DEPLOYED.core.slice(0,10)}... │   │ ${nftAddress.slice(0,10)}...    │
            └───────────┬───┘   └───────┬───────────┘
                        │               │
            ┌───────────▼───────────────▼───────────┐
            │          PolicyEngine                 │
            │   ${DEPLOYED.policyEngine}   │
            │   Risk Assessment / ML Integration    │
            └───────────────────┬───────────────────┘
                                │
            ┌───────────────────▼───────────────────┐
            │       DisputeResolver (Kleros)        │
            │   ${DEPLOYED.disputeResolver}   │
            └───────────────────────────────────────┘

NEXT STEPS:
1. Verify contracts on Etherscan:
   npx hardhat verify --network sepolia ${nftAddress}
   npx hardhat verify --network sepolia ${routerAddress}

2. Update frontend with new addresses:
   AMTTP_NFT_ADDRESS=${nftAddress}
   AMTTP_ROUTER_ADDRESS=${routerAddress}

3. Use the Router as the main entry point for all swaps!
`);

    // Save deployment info
    const fs = require("fs");
    const deploymentInfo = {
        network: "sepolia",
        timestamp: new Date().toISOString(),
        deployer: deployer.address,
        contracts: {
            router: routerAddress,
            nft: nftAddress,
            core: DEPLOYED.core,
            policyEngine: DEPLOYED.policyEngine,
            disputeResolver: DEPLOYED.disputeResolver,
            crossChain: DEPLOYED.crossChain
        }
    };
    
    const filename = `deployments/router-sepolia-${Date.now()}.json`;
    fs.writeFileSync(filename, JSON.stringify(deploymentInfo, null, 2));
    console.log(`\n📁 Deployment info saved to: ${filename}`);
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error("❌ Deployment failed:", error);
        process.exit(1);
    });
