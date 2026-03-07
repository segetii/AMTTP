// scripts/proof-transactions.mjs
// Direct ethers.js script — no Hardhat dependency
// Generates on-chain transactions on Sepolia for evidence screenshots

import { ethers } from "ethers";
import { config } from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname, "..", ".env") });

const PRIVATE_KEY = process.env.PRIVATE_KEY;
if (!PRIVATE_KEY) { console.error("PRIVATE_KEY not set in .env"); process.exit(1); }

const RPC_URL = process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com";
const provider = new ethers.JsonRpcProvider(RPC_URL);
const wallet = new ethers.Wallet(PRIVATE_KEY.replace(/^0x/, ""), provider);

// Contract addresses from deployments
const CONTRACTS = {
  AMTTPCore:            "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
  AMTTPPolicyEngine:    "0x520393A448543FF55f02ddA1218881a8E5851CEc",
  AMTTPDisputeResolver: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
  AMTTPCrossChain:      "0xc8d887665411ecB4760435fb3d20586C1111bc37",
  AMTTPRouter:          "0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3",
  AMTTPNFT:             "0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f",
};

const txHashes = [];

async function main() {
  console.log("=== AMTTP On-Chain Proof Generation ===\n");
  console.log("Deployer:", wallet.address);
  const balance = await provider.getBalance(wallet.address);
  console.log("Balance:", ethers.formatEther(balance), "SepoliaETH\n");

  if (balance === 0n) {
    console.log("ERROR: No Sepolia ETH. Get some from https://sepoliafaucet.com");
    process.exit(1);
  }

  // ─── 1. Check contract bytecode exists ────────────────────────────
  console.log("--- Checking deployed contracts ---");
  for (const [name, addr] of Object.entries(CONTRACTS)) {
    const code = await provider.getCode(addr);
    const hasCode = code !== "0x" && code.length > 2;
    console.log(`  ${name} (${addr}): ${hasCode ? "✓ Contract exists (" + code.length + " bytes)" : "✗ No code"}`);
  }

  // ─── 2. Read AMTTPCore state ──────────────────────────────────────
  console.log("\n--- 1. AMTTPCore ---");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function owner() view returns (address)",
      "function riskThreshold() view returns (uint256)",
      "function transactionCount() view returns (uint256)",
    ], wallet);

    try { console.log("  owner():", await core.owner()); } catch(e) { console.log("  owner(): not exposed"); }
    try { console.log("  riskThreshold():", (await core.riskThreshold()).toString()); } catch(e) { console.log("  riskThreshold(): not exposed"); }
    try { console.log("  transactionCount():", (await core.transactionCount()).toString()); } catch(e) { console.log("  transactionCount(): not exposed"); }
  } catch(e) {
    console.log("  Error reading Core:", e.message?.substring(0, 100));
  }

  // ─── 3. Read AMTTPPolicyEngine state ──────────────────────────────
  console.log("\n--- 2. AMTTPPolicyEngine ---");
  try {
    const pe = new ethers.Contract(CONTRACTS.AMTTPPolicyEngine, [
      "function owner() view returns (address)",
      "function escrowThreshold() view returns (uint256)",
      "function paused() view returns (bool)",
    ], wallet);

    try { console.log("  owner():", await pe.owner()); } catch(e) { console.log("  owner(): not exposed"); }
    try { console.log("  escrowThreshold():", (await pe.escrowThreshold()).toString()); } catch(e) { console.log("  escrowThreshold(): not exposed"); }
    try { console.log("  paused():", await pe.paused()); } catch(e) { console.log("  paused(): not exposed"); }
  } catch(e) {
    console.log("  Error reading PE:", e.message?.substring(0, 100));
  }

  // ─── 4. Read AMTTPDisputeResolver ─────────────────────────────────
  console.log("\n--- 3. AMTTPDisputeResolver ---");
  try {
    const dr = new ethers.Contract(CONTRACTS.AMTTPDisputeResolver, [
      "function owner() view returns (address)",
      "function arbitrator() view returns (address)",
      "function disputeCount() view returns (uint256)",
      "function metaEvidence() view returns (string)",
    ], wallet);

    try { console.log("  owner():", await dr.owner()); } catch(e) { console.log("  owner(): not exposed"); }
    try { console.log("  arbitrator():", await dr.arbitrator()); } catch(e) { console.log("  arbitrator(): not exposed"); }
    try { console.log("  disputeCount():", (await dr.disputeCount()).toString()); } catch(e) { console.log("  disputeCount(): not exposed"); }
  } catch(e) {
    console.log("  Error:", e.message?.substring(0, 100));
  }

  // ─── 5. Read AMTTPCrossChain ──────────────────────────────────────
  console.log("\n--- 4. AMTTPCrossChain ---");
  try {
    const cc = new ethers.Contract(CONTRACTS.AMTTPCrossChain, [
      "function owner() view returns (address)",
      "function lzEndpoint() view returns (address)",
      "function policyEngine() view returns (address)",
    ], wallet);

    try { console.log("  owner():", await cc.owner()); } catch(e) { console.log("  owner(): not exposed"); }
    try { console.log("  lzEndpoint():", await cc.lzEndpoint()); } catch(e) { console.log("  lzEndpoint(): not exposed"); }
    try { console.log("  policyEngine():", await cc.policyEngine()); } catch(e) { console.log("  policyEngine(): not exposed"); }
  } catch(e) {
    console.log("  Error:", e.message?.substring(0, 100));
  }

  // ─── 6. Read AMTTPNFT ────────────────────────────────────────────
  console.log("\n--- 5. AMTTPNFT ---");
  try {
    const nft = new ethers.Contract(CONTRACTS.AMTTPNFT, [
      "function name() view returns (string)",
      "function symbol() view returns (string)",
      "function totalSupply() view returns (uint256)",
      "function owner() view returns (address)",
    ], wallet);

    try { console.log("  name():", await nft.name()); } catch(e) { console.log("  name(): not exposed"); }
    try { console.log("  symbol():", await nft.symbol()); } catch(e) { console.log("  symbol(): not exposed"); }
    try { console.log("  totalSupply():", (await nft.totalSupply()).toString()); } catch(e) { console.log("  totalSupply(): not exposed"); }
    try { console.log("  owner():", await nft.owner()); } catch(e) { console.log("  owner(): not exposed"); }
  } catch(e) {
    console.log("  Error:", e.message?.substring(0, 100));
  }

  // ─── 7. Read AMTTPRouter ──────────────────────────────────────────
  console.log("\n--- 6. AMTTPRouter ---");
  try {
    const router = new ethers.Contract(CONTRACTS.AMTTPRouter, [
      "function owner() view returns (address)",
      "function amttpCore() view returns (address)",
      "function policyEngine() view returns (address)",
    ], wallet);

    try { console.log("  owner():", await router.owner()); } catch(e) { console.log("  owner(): not exposed"); }
    try { console.log("  amttpCore():", await router.amttpCore()); } catch(e) { console.log("  amttpCore(): not exposed"); }
    try { console.log("  policyEngine():", await router.policyEngine()); } catch(e) { console.log("  policyEngine(): not exposed"); }
  } catch(e) {
    console.log("  Error:", e.message?.substring(0, 100));
  }

  // ─── 8. Try write transactions ────────────────────────────────────
  console.log("\n\n=== GENERATING WRITE TRANSACTIONS ===\n");

  // 8a. Send small ETH to AMTTPCore (proves deployer owns the system)
  console.log("TX1: ETH transfer to AMTTPCore...");
  try {
    const tx = await wallet.sendTransaction({
      to: CONTRACTS.AMTTPCore,
      value: ethers.parseEther("0.0001"),
    });
    console.log("  Submitted:", tx.hash);
    const receipt = await tx.wait();
    console.log("  ✓ Confirmed in block", receipt.blockNumber);
    txHashes.push({ label: "ETH→AMTTPCore", hash: tx.hash });
  } catch(e) {
    console.log("  ✗ Failed:", e.message?.substring(0, 120));
  }

  // 8b. Call a function on PolicyEngine
  console.log("\nTX2: PolicyEngine.setEscrowThreshold(700)...");
  try {
    const pe = new ethers.Contract(CONTRACTS.AMTTPPolicyEngine, [
      "function setEscrowThreshold(uint256) external",
      "function updateThreshold(uint256) external",
    ], wallet);
    try {
      const tx = await pe.setEscrowThreshold(700);
      console.log("  Submitted:", tx.hash);
      const receipt = await tx.wait();
      console.log("  ✓ Confirmed in block", receipt.blockNumber);
      txHashes.push({ label: "PolicyEngine.setEscrowThreshold", hash: tx.hash });
    } catch(e) {
      const tx = await pe.updateThreshold(700);
      console.log("  Submitted:", tx.hash);
      const receipt = await tx.wait();
      console.log("  ✓ Confirmed in block", receipt.blockNumber);
      txHashes.push({ label: "PolicyEngine.updateThreshold", hash: tx.hash });
    }
  } catch(e) {
    console.log("  ✗ Failed:", e.message?.substring(0, 120));
  }

  // 8c. Try registerTransaction on Core
  console.log("\nTX3: AMTTPCore.registerTransaction(...)...");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function registerTransaction(bytes32,address,address,uint256,uint256) external",
      "function submitTransaction(bytes32,uint256) external",
    ], wallet);
    const txId = ethers.keccak256(ethers.toUtf8Bytes("AMTTP-PROOF-" + Date.now()));
    try {
      const tx = await core.registerTransaction(
        txId, wallet.address, "0x000000000000000000000000000000000000dEaD",
        ethers.parseEther("0.001"), 250
      );
      console.log("  Submitted:", tx.hash);
      const receipt = await tx.wait();
      console.log("  ✓ Confirmed in block", receipt.blockNumber);
      txHashes.push({ label: "Core.registerTransaction", hash: tx.hash });
    } catch(e1) {
      try {
        const tx = await core.submitTransaction(txId, 250);
        console.log("  Submitted:", tx.hash);
        const receipt = await tx.wait();
        console.log("  ✓ Confirmed in block", receipt.blockNumber);
        txHashes.push({ label: "Core.submitTransaction", hash: tx.hash });
      } catch(e2) {
        console.log("  ✗ Failed:", e2.message?.substring(0, 120));
      }
    }
  } catch(e) {
    console.log("  ✗ Failed:", e.message?.substring(0, 120));
  }

  // 8d. Try minting an NFT
  console.log("\nTX4: AMTTPNFT.mint(...)...");
  try {
    const nft = new ethers.Contract(CONTRACTS.AMTTPNFT, [
      "function mint(address,uint256) external",
      "function safeMint(address,string) external returns (uint256)",
      "function mintComplianceBadge(address,uint256,string) external returns (uint256)",
    ], wallet);
    const tokenId = BigInt(Date.now());
    try {
      const tx = await nft.mintComplianceBadge(wallet.address, 150, "AMTTP-Proof-of-Compliance");
      console.log("  Submitted:", tx.hash);
      const receipt = await tx.wait();
      console.log("  ✓ Confirmed in block", receipt.blockNumber);
      txHashes.push({ label: "NFT.mintComplianceBadge", hash: tx.hash });
    } catch(e1) {
      try {
        const tx = await nft.safeMint(wallet.address, "ipfs://AMTTP-compliance");
        console.log("  Submitted:", tx.hash);
        const receipt = await tx.wait();
        console.log("  ✓ Confirmed in block", receipt.blockNumber);
        txHashes.push({ label: "NFT.safeMint", hash: tx.hash });
      } catch(e2) {
        try {
          const tx = await nft.mint(wallet.address, tokenId);
          console.log("  Submitted:", tx.hash);
          const receipt = await tx.wait();
          console.log("  ✓ Confirmed in block", receipt.blockNumber);
          txHashes.push({ label: "NFT.mint", hash: tx.hash });
        } catch(e3) {
          console.log("  ✗ Failed:", e3.message?.substring(0, 120));
        }
      }
    }
  } catch(e) {
    console.log("  ✗ Failed:", e.message?.substring(0, 120));
  }

  // 8e. Send ETH to Router
  console.log("\nTX5: ETH transfer to AMTTPRouter...");
  try {
    const tx = await wallet.sendTransaction({
      to: CONTRACTS.AMTTPRouter,
      value: ethers.parseEther("0.0001"),
    });
    console.log("  Submitted:", tx.hash);
    const receipt = await tx.wait();
    console.log("  ✓ Confirmed in block", receipt.blockNumber);
    txHashes.push({ label: "ETH→AMTTPRouter", hash: tx.hash });
  } catch(e) {
    console.log("  ✗ Failed:", e.message?.substring(0, 120));
  }

  // ─── Summary ─────────────────────────────────────────────────────
  console.log("\n\n========================================");
  console.log("  ETHERSCAN LINKS FOR SCREENSHOTS");
  console.log("========================================\n");

  console.log("DEPLOYER ADDRESS (shows ALL deployment + interaction txs):");
  console.log("  https://sepolia.etherscan.io/address/" + wallet.address + "\n");

  console.log("DEPLOYED CONTRACTS:");
  for (const [name, addr] of Object.entries(CONTRACTS)) {
    console.log("  " + name + ":");
    console.log("    https://sepolia.etherscan.io/address/" + addr);
  }

  if (txHashes.length > 0) {
    console.log("\nNEW TRANSACTIONS (just created — screenshot these):");
    for (const { label, hash } of txHashes) {
      console.log("  " + label + ":");
      console.log("    https://sepolia.etherscan.io/tx/" + hash);
    }
  }

  console.log("\n========================================");
  console.log("  SCREENSHOT CHECKLIST");
  console.log("========================================");
  console.log("1. Deployer address page → shows all deployment txs");
  console.log("2. Each contract page → shows contract bytecode");
  console.log("3. Each new TX page → shows your interaction proof");
  console.log("4. Contract creation TX for each → proves you deployed");
  console.log("========================================\n");
}

main().catch(console.error);
