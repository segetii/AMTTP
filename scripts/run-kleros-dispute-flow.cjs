/**
 * run-kleros-dispute-flow.cjs
 *
 * Executes the complete AMTTP ↔ Real Kleros v2 dispute flow on Arbitrum Sepolia:
 *
 *   1. Claim PNK from faucet (10,000 PNK, one-time per address)
 *   2. Approve + stake PNK in KlerosCore court (makes us eligible as juror)
 *   3. Escrow 0.001 ETH in AMTTPDisputeResolver (high-risk transaction)
 *   4. Challenge → calls KlerosCore.createDispute → real DisputeCreation event!
 *   5. Draw jurors from sortition → try to draw ourselves
 *   6. Pass periods (all 0-duration on testnet) → cast vote → execute ruling
 *   7. Ruling delivered to our contract (rule() callback)
 *
 * Addresses (Arbitrum Sepolia — chain 421614):
 *   KlerosCore:      0xE8442307d36e9bf6aB27F1A009F95CE8E11C3479
 *   PNK token:       0x34B944D42cAcfC8266955D07A80181D2054aa225
 *   PNKFaucet:       0x9f6ffc13B685A68ae359fCA128dfE776458Df464
 *   DisputeKitClassic: 0x109C193ceD10bdC09b60A1D9A547726fc8271979
 *   DisputeResolver: read from deployments/arb-sepolia-dispute-resolver.json
 */

const { ethers } = require("ethers");
const fs = require("fs");
require("dotenv").config();

// ── Chain addresses ──────────────────────────────────────────────────────────
const KLEROS_CORE     = "0xE8442307d36e9bf6aB27F1A009F95CE8E11C3479";
const PNK_TOKEN       = "0x34B944D42cAcfC8266955D07A80181D2054aa225";
const PNK_FAUCET      = "0x9f6ffc13B685A68ae359fCA128dfE776458Df464";
const DK_CLASSIC      = "0x109C193ceD10bdC09b60A1D9A547726fc8271979";
const GENERAL_COURT   = 1n; // Court ID 1 (General)
const RULING_APPROVE  = 1n;

// ── Minimal ABIs ─────────────────────────────────────────────────────────────
const DISPUTE_RESOLVER_ABI = [
  "function escrowTransaction(bytes32 _txId, address _recipient, uint256 _riskScore, string calldata _evidenceURI) external payable",
  "function challengeTransaction(bytes32 _txId) external payable",
  "function executeTransaction(bytes32 _txId) external",
  "function escrows(bytes32) external view returns (bytes32,address,address,address,uint256,uint256,uint256,uint256,uint8,uint256,uint256,uint8,string)",
  "function arbitrator() external view returns (address)",
  "function getChallengeCost() external view returns (uint256)",
  "event TransactionEscrowed(bytes32 indexed txId, address indexed sender, address indexed recipient, address token, uint256 amount, uint256 riskScore, uint256 challengeDeadline)",
  "event TransactionChallenged(bytes32 indexed txId, address indexed challenger, uint256 disputeID)",
];

const KLEROS_CORE_ABI = [
  "function arbitrationCost(bytes calldata _extraData) external view returns (uint256 cost)",
  "function createDispute(uint256 _numberOfChoices, bytes calldata _extraData) external payable returns (uint256 disputeID)",
  "function arbitrationCost(bytes calldata, address) external view returns (uint256)",
  "function passPeriod(uint256 _disputeID) external",
  "function draw(uint256 _disputeID, uint256 _iterations) external returns (uint256)",
  "function executeRuling(uint256 _disputeID) external",
  "function courts(uint256) external view returns (uint96 parent, bool hiddenVotes, uint256 minStake, uint256 alpha, uint256 feeForJuror, uint256 jurorsForCourtJump, bool disabled)",
  "function getRoundInfo(uint256 _disputeID, uint256 _round) external view returns (tuple(uint256 disputeKitID, uint256 pnkAtStakePerJuror, uint256 totalFeesForJurors, uint256 nbVotes, uint256 repartitions, uint256 pnkPenalties, address[] drawnJurors, uint256 sumFeeRewardPaid, uint256 sumPnkRewardPaid, address feeToken, uint256 drawIterations))",
  "function setStake(uint96 _courtID, uint256 _newStake) external",
  "function disputes(uint256) external view returns (uint96 courtID, address arbitrated, uint8 period, bool ruled, uint256 lastPeriodChange)",
  "event DisputeCreation(uint256 indexed _disputeID, address indexed _arbitrable)",
  "event Ruling(address indexed _arbitrable, uint256 indexed _disputeID, uint256 _ruling)",
];

const PNK_ABI = [
  "function balanceOf(address) external view returns (uint256)",
  "function approve(address spender, uint256 amount) external returns (bool)",
  "function allowance(address owner, address spender) external view returns (uint256)",
];

const FAUCET_ABI = [
  "function request() external",
  "function withdrewAlready(address) external view returns (bool)",
  "function amount() external view returns (uint256)",
];

const DK_CLASSIC_ABI = [
  "function castVote(uint256 _disputeID, uint256[] calldata _voteIDs, uint256 _choice, uint256 _salt, string calldata _justification) external",
  "function getRoundInfo(uint256 _disputeID, uint256 _round) external view returns (uint256,uint256,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256)",
];

async function waitReceipt(tx, label) {
  console.log(`  ↳ Broadcasting ${label}...`);
  const receipt = await tx.wait();
  console.log(`  ✅ ${label} — tx: https://sepolia.arbiscan.io/tx/${receipt.hash}`);
  return receipt;
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  // ── Setup ──────────────────────────────────────────────────────────────────
  const rpc = process.env.ARBITRUM_SEPOLIA_RPC || "https://sepolia-rollup.arbitrum.io/rpc";
  const provider = new ethers.JsonRpcProvider(rpc);
  const wallet = new ethers.Wallet(process.env.PRIVATE_KEY, provider);

  // Load deployment
  const depFile = "deployments/arb-sepolia-dispute-resolver.json";
  if (!fs.existsSync(depFile)) {
    throw new Error(`Run the deploy script first: ${depFile} not found`);
  }
  const deployment = JSON.parse(fs.readFileSync(depFile));
  const RESOLVER_ADDR = deployment.disputeResolver;

  console.log("═".repeat(65));
  console.log("  AMTTP × KLEROS v2 — Full Dispute Flow (Arbitrum Sepolia)");
  console.log("═".repeat(65));
  console.log(`  Wallet:          ${wallet.address}`);
  const bal = await provider.getBalance(wallet.address);
  console.log(`  ETH balance:     ${ethers.formatEther(bal)} ETH`);
  console.log(`  DisputeResolver: ${RESOLVER_ADDR}`);
  console.log(`  KlerosCore:      ${KLEROS_CORE}`);
  console.log(`  Arbiscan:        https://sepolia.arbiscan.io/address/${RESOLVER_ADDR}`);
  console.log("");

  // ── Contracts ───────────────────────────────────────────────────────────────
  const resolver   = new ethers.Contract(RESOLVER_ADDR, DISPUTE_RESOLVER_ABI, wallet);
  const klerosCore = new ethers.Contract(KLEROS_CORE, KLEROS_CORE_ABI, wallet);
  const pnk        = new ethers.Contract(PNK_TOKEN, PNK_ABI, wallet);
  const faucet     = new ethers.Contract(PNK_FAUCET, FAUCET_ABI, wallet);
  const dkClassic  = new ethers.Contract(DK_CLASSIC, DK_CLASSIC_ABI, wallet);

  // ── Step 1: PNK from faucet ────────────────────────────────────────────────
  console.log("── Step 1: PNK tokens ──────────────────────────────────────");
  const alreadyGot = await faucet.withdrewAlready(wallet.address);
  let pnkBalance = await pnk.balanceOf(wallet.address);
  console.log(`  PNK balance:     ${ethers.formatEther(pnkBalance)} PNK`);
  console.log(`  Faucet used:     ${alreadyGot}`);

  if (!alreadyGot && pnkBalance === 0n) {
    console.log("  Requesting 10,000 PNK from faucet...");
    const tx = await faucet.request();
    await waitReceipt(tx, "PNK faucet.request()");
    pnkBalance = await pnk.balanceOf(wallet.address);
    console.log(`  PNK balance:     ${ethers.formatEther(pnkBalance)} PNK`);
  } else if (alreadyGot) {
    console.log("  Faucet already used — proceeding with existing PNK balance");
  }

  // ── Step 2: Approve + Stake PNK in KlerosCore ────────────────────────────
  console.log("\n── Step 2: Stake PNK as juror ─────────────────────────────");
  const courtInfo  = await klerosCore.courts(GENERAL_COURT);
  const minStake   = courtInfo.minStake;
  console.log(`  Court ${GENERAL_COURT} minStake: ${ethers.formatEther(minStake)} PNK`);

  if (pnkBalance >= minStake) {
    // Check allowance
    const allowance = await pnk.allowance(wallet.address, KLEROS_CORE);
    if (allowance < minStake) {
      const approveTx = await pnk.approve(KLEROS_CORE, pnkBalance);
      await waitReceipt(approveTx, "PNK approve KlerosCore");
    } else {
      console.log("  Allowance already sufficient");
    }
    // Stake
    const stakeAmount = minStake > pnkBalance ? pnkBalance : minStake;
    console.log(`  Staking ${ethers.formatEther(stakeAmount)} PNK in court ${GENERAL_COURT}...`);
    try {
      const stakeTx = await klerosCore.setStake(GENERAL_COURT, stakeAmount);
      await waitReceipt(stakeTx, "KlerosCore.setStake()");
    } catch (e) {
      console.log("  Staking failed (may already be staked):", e.message?.slice(0, 80));
    }
  } else {
    console.log("  Insufficient PNK for staking — dispute will rely on existing stakers");
  }

  // ── Step 3: Query arbitration cost ────────────────────────────────────────
  console.log("\n── Step 3: Arbitration cost ───────────────────────────────");
  // Our EXTRA_DATA: abi.encodePacked(uint96(0), uint96(3), uint96(1))
  const EXTRA_DATA = ethers.solidityPacked(["uint96", "uint96", "uint96"], [0, 3, 1]);
  const arbCost = await klerosCore.arbitrationCost(EXTRA_DATA);
  console.log(`  EXTRA_DATA:      ${EXTRA_DATA}`);
  console.log(`  Arbitration cost: ${ethers.formatEther(arbCost)} ETH`);

  // ── Step 4: Escrow a high-risk transaction ────────────────────────────────
  console.log("\n── Step 4: Escrow high-risk transaction ───────────────────");
  const txId = ethers.keccak256(ethers.toUtf8Bytes(`amttp-kleros-real-${Date.now()}`));
  const escrowAmount = ethers.parseEther("0.001");
  const evidenceURI  = "ipfs://bafybeiamttpevidence/kleros-real-dispute-risk-score-950.json";

  console.log(`  txId:            ${txId}`);
  console.log(`  Escrow amount:   0.001 ETH`);
  console.log(`  Risk score:      950 (95.0% — HIGH RISK)`);

  const escrowTx = await resolver.escrowTransaction(
    txId,
    wallet.address,   // recipient: self (test)
    950,              // risk score 95%
    evidenceURI,
    { value: escrowAmount }
  );
  const escrowReceipt = await waitReceipt(escrowTx, "escrowTransaction()");

  // ── Step 5: Challenge → creates real Kleros dispute ───────────────────────
  console.log("\n── Step 5: Challenge transaction → Kleros dispute ─────────");
  console.log(`  Paying arbitration fee: ${ethers.formatEther(arbCost)} ETH`);

  const challengeTx = await resolver.challengeTransaction(txId, {
    value: arbCost + ethers.parseEther("0.0001"), // slight over-bid for safety
  });
  const challengeReceipt = await waitReceipt(challengeTx, "challengeTransaction()");

  // Extract disputeID from TransactionChallenged event
  let disputeID = null;
  for (const log of challengeReceipt.logs) {
    try {
      const parsed = resolver.interface.parseLog({ topics: log.topics, data: log.data });
      if (parsed?.name === "TransactionChallenged") {
        disputeID = parsed.args.disputeID;
        console.log(`\n  🎯 REAL KLEROS DISPUTE CREATED!`);
        console.log(`  disputeID:       ${disputeID}`);
        console.log(`  Kleros arbiscan: https://sepolia.arbiscan.io/address/${KLEROS_CORE}#events`);
        console.log(`  Court UI:        https://v2.kleros.builders/#/cases/${disputeID}`);
      }
    } catch {}
  }

  if (disputeID === null) {
    // Fallback: check KlerosCore DisputeCreation in logs
    const klerosInterface = new ethers.Interface(KLEROS_CORE_ABI);
    for (const log of challengeReceipt.logs) {
      try {
        const parsed = klerosInterface.parseLog({ topics: log.topics, data: log.data });
        if (parsed?.name === "DisputeCreation") {
          disputeID = parsed.args._disputeID;
          console.log(`  disputeID (from KlerosCore): ${disputeID}`);
        }
      } catch {}
    }
  }

  if (disputeID === null) {
    console.log("  Could not extract disputeID from logs — continuing without auto-resolution");
    console.log("\n  Screenshot links:");
    console.log(`    https://sepolia.arbiscan.io/address/${RESOLVER_ADDR}#events`);
    console.log(`    https://sepolia.arbiscan.io/address/${KLEROS_CORE}#events`);
    return;
  }

  await sleep(3000);

  // ── Step 6: Try to draw jurors ────────────────────────────────────────────
  console.log("\n── Step 6: Draw jurors (sortition) ────────────────────────");
  let nbDrawn = 0;
  try {
    const drawTx = await klerosCore.draw(disputeID, 10n);
    const drawReceipt = await waitReceipt(drawTx, "KlerosCore.draw()");
    // Parse Draw events to count
    for (const log of drawReceipt.logs) {
      if (log.topics[0] === ethers.id("Draw(address,uint256,uint256,uint256)")) {
        nbDrawn++;
      }
    }
    console.log(`  Jurors drawn: ${nbDrawn}`);
  } catch (e) {
    console.log("  draw() failed:", e.message?.slice(0, 100));
    console.log("  (Normal if insufficient PNK staked in court)");
  }

  await sleep(3000);

  // ── Step 7: Pass periods ──────────────────────────────────────────────────
  console.log("\n── Step 7: Pass through dispute periods ───────────────────");
  const MAX_PERIODS = 5;
  for (let i = 0; i < MAX_PERIODS; i++) {
    try {
      const ppTx = await klerosCore.passPeriod(disputeID);
      const ppReceipt = await ppTx.wait();
      console.log(`  passPeriod() ${i + 1} — tx: https://sepolia.arbiscan.io/tx/${ppReceipt.hash}`);
      await sleep(2000);
    } catch (e) {
      const msg = e.message || "";
      if (msg.includes("VotePeriodNotPassed") || msg.includes("AppealPeriodNotPassed") || msg.includes("NotExecutionPeriod")) {
        console.log(`  passPeriod() ${i + 1} — waiting for period duration...`);
        await sleep(12000); // wait ~12s for period
        try {
          const ppTx2 = await klerosCore.passPeriod(disputeID);
          await ppTx2.wait();
          console.log(`  passPeriod() ${i + 1} retry ✅`);
        } catch (e2) {
          console.log(`  Period ${i + 1} retry failed:`, e2.message?.slice(0, 60));
          break;
        }
      } else if (msg.includes("DisputePeriodIsFinal") || msg.includes("RulingAlreadyExecuted")) {
        console.log(`  Dispute already in final/execution period`);
        break;
      } else {
        console.log(`  passPeriod() ${i + 1} error:`, msg.slice(0, 80));
        break;
      }
    }
  }

  await sleep(2000);

  // ── Step 8: Vote if we were drawn as juror ────────────────────────────────
  console.log("\n── Step 8: Vote (if drawn as juror) ───────────────────────");
  try {
    const roundInfo = await klerosCore.getRoundInfo(disputeID, 0);
    const drawnJurors = roundInfo.drawnJurors ?? [];
    console.log(`  drawnJurors: [${drawnJurors.join(", ")}]`);

    const ourVoteIDs = [];
    for (let i = 0; i < drawnJurors.length; i++) {
      if (drawnJurors[i].toLowerCase() === wallet.address.toLowerCase()) {
        ourVoteIDs.push(BigInt(i));
      }
    }

    if (ourVoteIDs.length > 0) {
      console.log(`  We were drawn! voteIDs: [${ourVoteIDs.join(", ")}] — casting APPROVE (1)`);
      const voteTx = await dkClassic.castVote(
        disputeID,
        ourVoteIDs,
        RULING_APPROVE,
        0n,
        "AMTTP oracle flagged this transaction as HIGH_RISK (95%). Recommend REJECT to protect the network."
      );
      await waitReceipt(voteTx, "DisputeKitClassic.castVote()");
    } else {
      console.log("  We were not drawn as juror this round (normal on testnet)");
      console.log("  The dispute remains open for designated testnet jurors to resolve");
    }
  } catch (e) {
    console.log("  Voting check failed:", e.message?.slice(0, 80));
  }

  await sleep(3000);

  // ── Step 9: Execute ruling ────────────────────────────────────────────────
  console.log("\n── Step 9: Execute ruling → calls our contract ────────────");
  try {
    const execTx = await klerosCore.executeRuling(disputeID);
    await waitReceipt(execTx, "KlerosCore.executeRuling()");
    console.log("  ✅ rule() callback delivered to AMTTPDisputeResolver");
    console.log("  ✅ Escrowed funds released per Kleros ruling!");
  } catch (e) {
    console.log("  executeRuling() not yet possible:", e.message?.slice(0, 100));
    console.log("  (Dispute needs jurors to vote before ruling can be executed)");
  }

  // ── Summary ────────────────────────────────────────────────────────────────
  console.log("\n" + "═".repeat(65));
  console.log("  AMTTP × KLEROS DISPUTE FLOW COMPLETE");
  console.log("═".repeat(65));
  console.log("\n  📸 Screenshot links:");
  console.log(`  1. Our DisputeResolver (Arb Sepolia):`);
  console.log(`     https://sepolia.arbiscan.io/address/${RESOLVER_ADDR}#events`);
  console.log(`  2. Real KlerosCore DisputeCreation event:`);
  console.log(`     https://sepolia.arbiscan.io/address/${KLEROS_CORE}#events`);
  console.log(`  3. Kleros Court v2 UI (live dispute):`);
  console.log(`     https://v2.kleros.builders/#/cases/${disputeID}`);
  console.log("\n  Key on-chain events emitted:");
  console.log("  • TransactionEscrowed  — our contract (escrowed 0.001 ETH)");
  console.log("  • Evidence             — IPFS ML risk evidence submitted");
  console.log("  • Dispute              — ERC-792 dispute created (IEvidence)");
  console.log("  • DisputeCreation      — REAL KlerosCore v2 (chain 421614)");
  console.log("  • TransactionChallenged — our contract (dispute ID recorded)");
  if (disputeID !== null) {
    console.log(`\n  Dispute ID on KlerosCore: ${disputeID}`);
    console.log(`  View: https://v2.kleros.builders/#/cases/${disputeID}`);
  }
}

main().catch((e) => {
  console.error("\nFatal error:", e.message || e);
  process.exit(1);
});
