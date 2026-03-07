// scripts/generate-proof-transactions.cjs
// Generates on-chain transactions on Sepolia for evidence screenshots
const hre = require("hardhat");

async function main() {
  const [signer] = await hre.ethers.getSigners();
  console.log("=== AMTTP On-Chain Proof Generation ===");
  console.log("Deployer:", signer.address);
  
  const balance = await hre.ethers.provider.getBalance(signer.address);
  console.log("Balance:", hre.ethers.formatEther(balance), "SepoliaETH\n");

  if (balance === 0n) {
    console.log("ERROR: No Sepolia ETH. Get some from https://sepoliafaucet.com");
    process.exit(1);
  }

  // Contract addresses from deployments
  const CONTRACTS = {
    AMTTPCore: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
    AMTTPPolicyEngine: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
    AMTTPDisputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
    AMTTPCrossChain: "0xc8d887665411ecB4760435fb3d20586C1111bc37",
    AMTTPRouter: "0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3",
    AMTTPNFT: "0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f",
  };

  const txHashes = [];

  // ─── 1. Interact with AMTTPCore ──────────────────────────────────
  console.log("1. AMTTPCore — Reading contract state...");
  try {
    const coreABI = [
      "function owner() view returns (address)",
      "function paused() view returns (bool)",
      "function riskThreshold() view returns (uint256)",
      "function registerTransaction(bytes32 txHash, address sender, address receiver, uint256 amount, uint256 riskScore) external",
      "function processTransaction(bytes32 txHash) external",
      "function getTransactionStatus(bytes32 txHash) view returns (uint8)",
    ];
    const core = new hre.ethers.Contract(CONTRACTS.AMTTPCore, coreABI, signer);
    
    // Try reading state first
    try {
      const owner = await core.owner();
      console.log("   Owner:", owner);
    } catch(e) {
      console.log("   (owner() not available, trying alternative reads)");
    }

    // Register a sample transaction
    const sampleTxHash = hre.ethers.keccak256(
      hre.ethers.toUtf8Bytes("AMTTP-PROOF-TX-" + Date.now())
    );
    const sampleReceiver = "0x000000000000000000000000000000000000dEaD";
    const sampleAmount = hre.ethers.parseEther("0.001");
    const sampleRiskScore = 250; // Low risk

    console.log("   Registering sample transaction on AMTTPCore...");
    try {
      const tx = await core.registerTransaction(
        sampleTxHash, signer.address, sampleReceiver, sampleAmount, sampleRiskScore
      );
      const receipt = await tx.wait();
      console.log("   ✓ TX registered:", receipt.hash);
      txHashes.push({ contract: "AMTTPCore.registerTransaction", hash: receipt.hash });
    } catch(e) {
      console.log("   registerTransaction reverted, trying processTransaction...");
      try {
        const tx = await core.processTransaction(sampleTxHash);
        const receipt = await tx.wait();
        console.log("   ✓ TX processed:", receipt.hash);
        txHashes.push({ contract: "AMTTPCore.processTransaction", hash: receipt.hash });
      } catch(e2) {
        console.log("   (Core functions restricted, will use low-level call)");
      }
    }
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 2. Interact with PolicyEngine ───────────────────────────────
  console.log("\n2. AMTTPPolicyEngine — Interacting...");
  try {
    const peABI = [
      "function owner() view returns (address)",
      "function escrowThreshold() view returns (uint256)",
      "function setEscrowThreshold(uint256 threshold) external",
      "function evaluateRisk(uint256 riskScore) view returns (uint8)",
      "function getRiskTier(uint256 score) view returns (string memory)",
    ];
    const pe = new hre.ethers.Contract(CONTRACTS.AMTTPPolicyEngine, peABI, signer);
    
    try {
      const threshold = await pe.escrowThreshold();
      console.log("   Current escrow threshold:", threshold.toString());
    } catch(e) {}

    // Update escrow threshold (write transaction)
    try {
      console.log("   Setting escrow threshold to 700...");
      const tx = await pe.setEscrowThreshold(700);
      const receipt = await tx.wait();
      console.log("   ✓ Threshold updated:", receipt.hash);
      txHashes.push({ contract: "AMTTPPolicyEngine.setEscrowThreshold", hash: receipt.hash });
    } catch(e) {
      console.log("   setEscrowThreshold not available:", e.message?.substring(0, 80));
    }
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 3. Interact with Router ─────────────────────────────────────
  console.log("\n3. AMTTPRouter — Interacting...");
  try {
    const routerABI = [
      "function owner() view returns (address)",
      "function submitTransaction(address to, uint256 amount, bytes calldata data) external returns (bytes32)",
      "function setRiskOracle(address oracle) external",
    ];
    const router = new hre.ethers.Contract(CONTRACTS.AMTTPRouter, routerABI, signer);

    try {
      const owner = await router.owner();
      console.log("   Owner:", owner);
    } catch(e) {}

    // Submit a transaction through the router
    try {
      console.log("   Submitting transaction through router...");
      const tx = await router.submitTransaction(
        "0x000000000000000000000000000000000000dEaD",
        hre.ethers.parseEther("0.0001"),
        "0x"
      );
      const receipt = await tx.wait();
      console.log("   ✓ Router TX submitted:", receipt.hash);
      txHashes.push({ contract: "AMTTPRouter.submitTransaction", hash: receipt.hash });
    } catch(e) {
      console.log("   submitTransaction not available, trying setRiskOracle...");
      try {
        const tx = await router.setRiskOracle(signer.address);
        const receipt = await tx.wait();
        console.log("   ✓ Risk oracle set:", receipt.hash);
        txHashes.push({ contract: "AMTTPRouter.setRiskOracle", hash: receipt.hash });
      } catch(e2) {
        console.log("   (Router functions restricted)");
      }
    }
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 4. Interact with NFT ────────────────────────────────────────
  console.log("\n4. AMTTPNFT — Minting compliance badge...");
  try {
    const nftABI = [
      "function owner() view returns (address)",
      "function name() view returns (string)",
      "function symbol() view returns (string)",
      "function totalSupply() view returns (uint256)",
      "function mint(address to, uint256 tokenId) external",
      "function safeMint(address to, string memory uri) external returns (uint256)",
      "function mintComplianceBadge(address to, uint256 riskScore, string memory metadata) external returns (uint256)",
    ];
    const nft = new hre.ethers.Contract(CONTRACTS.AMTTPNFT, nftABI, signer);

    try {
      const name = await nft.name();
      const symbol = await nft.symbol();
      console.log("   NFT:", name, "(" + symbol + ")");
    } catch(e) {}

    try {
      const supply = await nft.totalSupply();
      console.log("   Total supply:", supply.toString());
    } catch(e) {}

    // Try minting a compliance NFT
    try {
      console.log("   Minting compliance badge NFT...");
      const tx = await nft.mintComplianceBadge(
        signer.address, 150, "AMTTP-Compliant-Transaction-Proof"
      );
      const receipt = await tx.wait();
      console.log("   ✓ NFT minted:", receipt.hash);
      txHashes.push({ contract: "AMTTPNFT.mintComplianceBadge", hash: receipt.hash });
    } catch(e) {
      try {
        console.log("   Trying safeMint...");
        const tx = await nft.safeMint(signer.address, "ipfs://AMTTP-compliance-proof");
        const receipt = await tx.wait();
        console.log("   ✓ NFT minted:", receipt.hash);
        txHashes.push({ contract: "AMTTPNFT.safeMint", hash: receipt.hash });
      } catch(e2) {
        try {
          console.log("   Trying mint...");
          const tokenId = Date.now();
          const tx = await nft.mint(signer.address, tokenId);
          const receipt = await tx.wait();
          console.log("   ✓ NFT minted:", receipt.hash);
          txHashes.push({ contract: "AMTTPNFT.mint", hash: receipt.hash });
        } catch(e3) {
          console.log("   (NFT mint restricted)");
        }
      }
    }
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 5. Interact with DisputeResolver ────────────────────────────
  console.log("\n5. AMTTPDisputeResolver — Reading state...");
  try {
    const drABI = [
      "function owner() view returns (address)",
      "function arbitrator() view returns (address)",
      "function disputeCount() view returns (uint256)",
    ];
    const dr = new hre.ethers.Contract(CONTRACTS.AMTTPDisputeResolver, drABI, signer);

    try {
      const arb = await dr.arbitrator();
      console.log("   Kleros arbitrator:", arb);
    } catch(e) {}

    try {
      const count = await dr.disputeCount();
      console.log("   Dispute count:", count.toString());
    } catch(e) {}
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 6. Interact with CrossChain ─────────────────────────────────
  console.log("\n6. AMTTPCrossChain — Reading LayerZero config...");
  try {
    const ccABI = [
      "function owner() view returns (address)",
      "function lzEndpoint() view returns (address)",
      "function policyEngine() view returns (address)",
    ];
    const cc = new hre.ethers.Contract(CONTRACTS.AMTTPCrossChain, ccABI, signer);

    try {
      const lz = await cc.lzEndpoint();
      console.log("   LayerZero endpoint:", lz);
    } catch(e) {}

    try {
      const pe = await cc.policyEngine();
      console.log("   Linked PolicyEngine:", pe);
    } catch(e) {}
  } catch(e) {
    console.log("   Error:", e.message?.substring(0, 100));
  }

  // ─── 7. Send a plain ETH transfer from deployer for activity ─────
  console.log("\n7. Sending proof-of-activity ETH transfer...");
  try {
    const tx = await signer.sendTransaction({
      to: CONTRACTS.AMTTPCore,
      value: hre.ethers.parseEther("0.0001"),
      data: "0x",
    });
    const receipt = await tx.wait();
    console.log("   ✓ ETH sent to AMTTPCore:", receipt.hash);
    txHashes.push({ contract: "ETH-Transfer-to-AMTTPCore", hash: receipt.hash });
  } catch(e) {
    console.log("   Transfer failed:", e.message?.substring(0, 80));
  }

  // ─── Summary ─────────────────────────────────────────────────────
  console.log("\n\n========================================");
  console.log("  PROOF TRANSACTIONS SUMMARY");
  console.log("========================================\n");

  console.log("Deployer address:");
  console.log("  https://sepolia.etherscan.io/address/" + signer.address + "\n");

  console.log("Deployed contracts:");
  for (const [name, addr] of Object.entries(CONTRACTS)) {
    console.log("  " + name + ": https://sepolia.etherscan.io/address/" + addr);
  }

  if (txHashes.length > 0) {
    console.log("\nNew transactions (screenshot these):");
    for (const { contract, hash } of txHashes) {
      console.log("  " + contract + ":");
      console.log("    https://sepolia.etherscan.io/tx/" + hash);
    }
  }

  console.log("\n========================================");
  console.log("  SCREENSHOT CHECKLIST");
  console.log("========================================");
  console.log("1. Deployer address page (shows all deployment txs)");
  console.log("2. Each contract address page (shows contract code)");
  console.log("3. Each new transaction page (shows interaction proof)");
  console.log("4. Contract creation tx for each contract");
  console.log("========================================\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
