// scripts/proof-transactions-v2.mjs
// Additional proof transactions using real contract ABI functions

import { ethers } from "ethers";
import { config } from "dotenv";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: join(__dirname, "..", ".env") });

const PRIVATE_KEY = process.env.PRIVATE_KEY;
const RPC_URL = process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com";
const provider = new ethers.JsonRpcProvider(RPC_URL);
const wallet = new ethers.Wallet(PRIVATE_KEY.replace(/^0x/, ""), provider);

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
  console.log("=== AMTTP Proof Transactions — Round 2 ===\n");
  console.log("Deployer:", wallet.address);
  const bal = await provider.getBalance(wallet.address);
  console.log("Balance:", ethers.formatEther(bal), "SepoliaETH\n");

  // ─── TX1: AMTTPCore.setGlobalRiskThreshold(750) ──────────────────
  console.log("TX1: AMTTPCore.setGlobalRiskThreshold(750)...");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function setGlobalRiskThreshold(uint256 _threshold) external",
      "function setActiveModelVersion(string _version) external",
      "function setOracle(address _oracle) external",
      "function getContractStatus() external view returns (address,address,address,uint256,string,bool)",
    ], wallet);
    const tx = await core.setGlobalRiskThreshold(750);
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "Core.setGlobalRiskThreshold(750)", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX2: AMTTPCore.setActiveModelVersion("AMTTP-v3-ensemble-2026") ──
  console.log("\nTX2: AMTTPCore.setActiveModelVersion(...)...");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function setActiveModelVersion(string _version) external",
    ], wallet);
    const tx = await core.setActiveModelVersion("AMTTP-v3-ensemble-2026-ROCAUC-0.9879");
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "Core.setActiveModelVersion", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX3: AMTTPCore.addApprover (add a compliance approver) ──────
  console.log("\nTX3: AMTTPCore.addApprover(...)...");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function addApprover(address _approver) external",
    ], wallet);
    // Use a deterministic address as compliance approver
    const approverAddr = "0x1111111111111111111111111111111111111111";
    const tx = await core.addApprover(approverAddr);
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "Core.addApprover", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX4: AMTTPPolicyEngine — update threshold again ─────────────
  console.log("\nTX4: AMTTPPolicyEngine.setEscrowThreshold(800)...");
  try {
    const pe = new ethers.Contract(CONTRACTS.AMTTPPolicyEngine, [
      "function setEscrowThreshold(uint256) external",
    ], wallet);
    const tx = await pe.setEscrowThreshold(800);
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "PolicyEngine.setEscrowThreshold(800)", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX5: Read AMTTPCore status (view call — for display) ────────
  console.log("\nReading AMTTPCore contract status...");
  try {
    const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
      "function getContractStatus() external view returns (address _owner, address _oracle, address _policyEngine, uint256 _riskThreshold, string memory _modelVersion, bool _paused)",
    ], wallet);
    const status = await core.getContractStatus();
    console.log("  Owner:", status._owner);
    console.log("  Oracle:", status._oracle);
    console.log("  PolicyEngine:", status._policyEngine);
    console.log("  Risk Threshold:", status._riskThreshold.toString());
    console.log("  Model Version:", status._modelVersion);
    console.log("  Paused:", status._paused);
  } catch(e) {
    console.log("  (getContractStatus reverted, reading individual fields)");
    try {
      const core = new ethers.Contract(CONTRACTS.AMTTPCore, [
        "function owner() view returns (address)",
        "function oracle() view returns (address)",
        "function policyEngine() view returns (address)",
        "function globalRiskThreshold() view returns (uint256)",
        "function activeModelVersion() view returns (string)",
      ], wallet);
      try { console.log("  owner:", await core.owner()); } catch(e) {}
      try { console.log("  oracle:", await core.oracle()); } catch(e) {}
      try { console.log("  policyEngine:", await core.policyEngine()); } catch(e) {}
      try { console.log("  globalRiskThreshold:", (await core.globalRiskThreshold()).toString()); } catch(e) {}
      try { console.log("  activeModelVersion:", await core.activeModelVersion()); } catch(e) {}
    } catch(e2) {}
  }

  // ─── TX6: AMTTPNFT — setRouter ──────────────────────────────────
  console.log("\nTX5: AMTTPNFT.setRouter(AMTTPRouter)...");
  try {
    const nft = new ethers.Contract(CONTRACTS.AMTTPNFT, [
      "function setRouter(address _router) external",
      "function setPolicyEngine(address _policyEngine) external",
    ], wallet);
    const tx = await nft.setRouter(CONTRACTS.AMTTPRouter);
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "NFT.setRouter(AMTTPRouter)", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX7: AMTTPNFT — setPolicyEngine ─────────────────────────────
  console.log("\nTX6: AMTTPNFT.setPolicyEngine(...)...");
  try {
    const nft = new ethers.Contract(CONTRACTS.AMTTPNFT, [
      "function setPolicyEngine(address _policyEngine) external",
    ], wallet);
    const tx = await nft.setPolicyEngine(CONTRACTS.AMTTPPolicyEngine);
    console.log("  Submitted:", tx.hash);
    const r = await tx.wait();
    console.log("  ✓ Confirmed block", r.blockNumber);
    txHashes.push({ label: "NFT.setPolicyEngine", hash: tx.hash });
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── TX8: AMTTPRouter — link policyEngine ────────────────────────
  console.log("\nTX7: AMTTPRouter — linking to PolicyEngine...");
  try {
    const router = new ethers.Contract(CONTRACTS.AMTTPRouter, [
      "function setPolicyEngine(address) external",
      "function setCore(address) external",
    ], wallet);
    try {
      const tx = await router.setPolicyEngine(CONTRACTS.AMTTPPolicyEngine);
      console.log("  Submitted:", tx.hash);
      const r = await tx.wait();
      console.log("  ✓ Confirmed block", r.blockNumber);
      txHashes.push({ label: "Router.setPolicyEngine", hash: tx.hash });
    } catch(e) {
      const tx = await router.setCore(CONTRACTS.AMTTPCore);
      console.log("  Submitted:", tx.hash);
      const r = await tx.wait();
      console.log("  ✓ Confirmed block", r.blockNumber);
      txHashes.push({ label: "Router.setCore", hash: tx.hash });
    }
  } catch(e) {
    console.log("  ✗", e.message?.substring(0, 120));
  }

  // ─── Summary ─────────────────────────────────────────────────────
  console.log("\n\n========================================");
  console.log("  ALL PROOF TRANSACTIONS (ROUND 2)");
  console.log("========================================\n");

  for (const { label, hash } of txHashes) {
    console.log(`${label}:`);
    console.log(`  https://sepolia.etherscan.io/tx/${hash}\n`);
  }

  console.log("DEPLOYER (all txs):");
  console.log(`  https://sepolia.etherscan.io/address/${wallet.address}\n`);

  console.log("CONTRACTS:");
  for (const [name, addr] of Object.entries(CONTRACTS)) {
    console.log(`  ${name}: https://sepolia.etherscan.io/address/${addr}`);
  }
  console.log("");
}

main().catch(console.error);
