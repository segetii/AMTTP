// test/GasAnalysis.test.mjs
// Comprehensive gas analysis for AMTTP contracts
import { expect } from "chai";
import pkg from "hardhat";
const { ethers, upgrades } = pkg;

describe("AMTTP Gas Analysis", function () {
  let coreSecure, disputeResolver, crossChain, mockArbitrator;
  let owner, oracle, user1, user2, approver;

  before(async function () {
    [owner, oracle, user1, user2, approver] = await ethers.getSigners();
    console.log("\n📊 AMTTP Gas Analysis Report\n");
  });

  describe("AMTTPCoreSecure Gas Costs", function () {
    beforeEach(async function () {
      const AMTTPCoreSecure = await ethers.getContractFactory("AMTTPCoreSecure");
      coreSecure = await upgrades.deployProxy(
        AMTTPCoreSecure,
        [oracle.address],
        { initializer: "initialize", kind: "uups" }
      );
      await coreSecure.waitForDeployment();
      
      // Setup approver
      await coreSecure.addApprover(approver.address);
    });

    it("measures deployment gas", async function () {
      const AMTTPCoreSecure = await ethers.getContractFactory("AMTTPCoreSecure");
      const tx = await AMTTPCoreSecure.deploy();
      const receipt = await tx.deploymentTransaction().wait();
      console.log(`  AMTTPCoreSecure deployment: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures addOracle gas", async function () {
      const tx = await coreSecure.addOracle(user1.address);
      const receipt = await tx.wait();
      console.log(`  addOracle: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures removeOracle gas", async function () {
      await coreSecure.addOracle(user1.address);
      const tx = await coreSecure.removeOracle(user1.address);
      const receipt = await tx.wait();
      console.log(`  removeOracle: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures setOracleThreshold gas", async function () {
      await coreSecure.addOracle(user1.address);
      await coreSecure.addOracle(user2.address);
      const tx = await coreSecure.setOracleThreshold(2);
      const receipt = await tx.wait();
      console.log(`  setOracleThreshold: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures pause/unpause gas", async function () {
      const pauseTx = await coreSecure.pause();
      const pauseReceipt = await pauseTx.wait();
      console.log(`  pause: ${pauseReceipt.gasUsed.toLocaleString()} gas`);

      const unpauseTx = await coreSecure.unpause();
      const unpauseReceipt = await unpauseTx.wait();
      console.log(`  unpause: ${unpauseReceipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures setUserPolicy gas", async function () {
      const tx = await coreSecure.connect(oracle).setUserPolicy(
        user1.address,
        ethers.parseEther("100"),  // dailyLimit
        ethers.parseEther("10"),   // singleTxLimit
        true,  // kycVerified
        false  // trusted
      );
      const receipt = await tx.wait();
      console.log(`  setUserPolicy: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures queueUpgrade gas", async function () {
      // Queue upgrade (will queue a new implementation address)
      const tx = await coreSecure.queueUpgrade(user1.address);
      const receipt = await tx.wait();
      console.log(`  queueUpgrade: ${receipt.gasUsed.toLocaleString()} gas`);
    });
  });

  describe("AMTTPDisputeResolver Gas Costs", function () {
    beforeEach(async function () {
      const MockArbitrator = await ethers.getContractFactory("MockArbitrator");
      mockArbitrator = await MockArbitrator.deploy();
      await mockArbitrator.waitForDeployment();

      const AMTTPDisputeResolver = await ethers.getContractFactory("AMTTPDisputeResolver");
      disputeResolver = await AMTTPDisputeResolver.deploy(
        await mockArbitrator.getAddress(),
        "ipfs://metaEvidence"
      );
      await disputeResolver.waitForDeployment();
    });

    it("measures escrowTransaction gas", async function () {
      const txId = ethers.keccak256(ethers.toUtf8Bytes("test-tx-1"));
      const tx = await disputeResolver.connect(user1).escrowTransaction(
        txId,
        user2.address,
        750,
        "ipfs://evidence",
        { value: ethers.parseEther("1") }
      );
      const receipt = await tx.wait();
      console.log(`  escrowTransaction: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures challengeTransaction gas", async function () {
      const txId = ethers.keccak256(ethers.toUtf8Bytes("test-tx-2"));
      await disputeResolver.connect(user1).escrowTransaction(
        txId,
        user2.address,
        750,
        "ipfs://evidence",
        { value: ethers.parseEther("1") }
      );

      const challengeCost = await disputeResolver.getChallengeCost();
      const tx = await disputeResolver.connect(user2).challengeTransaction(txId, {
        value: challengeCost
      });
      const receipt = await tx.wait();
      console.log(`  challengeTransaction: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures executeTransaction gas (after window)", async function () {
      const txId = ethers.keccak256(ethers.toUtf8Bytes("test-tx-3"));
      await disputeResolver.connect(user1).escrowTransaction(
        txId,
        user2.address,
        750,
        "ipfs://evidence",
        { value: ethers.parseEther("1") }
      );

      // Fast forward past challenge window
      const escrow = await disputeResolver.escrows(txId);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(escrow.challengeDeadline) + 1]);
      await ethers.provider.send("evm_mine");

      const tx = await disputeResolver.executeTransaction(txId);
      const receipt = await tx.wait();
      console.log(`  executeTransaction: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures emergencyWithdraw gas", async function () {
      const txId = ethers.keccak256(ethers.toUtf8Bytes("test-tx-4"));
      await disputeResolver.connect(user1).escrowTransaction(
        txId,
        user2.address,
        750,
        "ipfs://evidence",
        { value: ethers.parseEther("1") }
      );

      // Fast forward past 30 days
      const escrow = await disputeResolver.escrows(txId);
      await ethers.provider.send("evm_setNextBlockTimestamp", [Number(escrow.challengeDeadline) + 30 * 24 * 3600 + 1]);
      await ethers.provider.send("evm_mine");

      const tx = await disputeResolver.emergencyWithdraw(txId);
      const receipt = await tx.wait();
      console.log(`  emergencyWithdraw: ${receipt.gasUsed.toLocaleString()} gas`);
    });
  });

  describe("AMTTPCrossChain Gas Costs", function () {
    beforeEach(async function () {
      const MockLayerZeroEndpoint = await ethers.getContractFactory("MockLayerZeroEndpoint");
      const mockEndpoint = await MockLayerZeroEndpoint.deploy(101);  // Ethereum chain ID
      await mockEndpoint.waitForDeployment();

      const AMTTPCrossChain = await ethers.getContractFactory("AMTTPCrossChain");
      crossChain = await upgrades.deployProxy(
        AMTTPCrossChain,
        [await mockEndpoint.getAddress(), 101, owner.address],  // endpoint, chainId, policyEngine
        { initializer: "initialize", kind: "uups" }
      );
      await crossChain.waitForDeployment();
    });

    it("measures setTrustedRemote gas", async function () {
      const remoteAddress = ethers.solidityPacked(
        ["address", "address"],
        [user1.address, await crossChain.getAddress()]
      );
      const tx = await crossChain.setTrustedRemote(109, remoteAddress);  // Polygon
      const receipt = await tx.wait();
      console.log(`  setTrustedRemote: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures setChainRateLimit gas", async function () {
      const tx = await crossChain.setChainRateLimit(109, 10);  // Max 10 per block
      const receipt = await tx.wait();
      console.log(`  setChainRateLimit: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures pauseChain gas", async function () {
      const tx = await crossChain.pauseChain(109);  // Pause Polygon
      const receipt = await tx.wait();
      console.log(`  pauseChain: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures unpauseChain gas", async function () {
      await crossChain.pauseChain(109);
      const tx = await crossChain.unpauseChain(109);  // Unpause Polygon
      const receipt = await tx.wait();
      console.log(`  unpauseChain: ${receipt.gasUsed.toLocaleString()} gas`);
    });

    it("measures pause/unpause gas", async function () {
      const pauseTx = await crossChain.pause();
      const pauseReceipt = await pauseTx.wait();
      console.log(`  pause: ${pauseReceipt.gasUsed.toLocaleString()} gas`);

      const unpauseTx = await crossChain.unpause();
      const unpauseReceipt = await unpauseTx.wait();
      console.log(`  unpause: ${unpauseReceipt.gasUsed.toLocaleString()} gas`);
    });
  });

  after(function () {
    console.log("\n✅ Gas analysis complete\n");
  });
});
