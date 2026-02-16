// test/AMTTPDisputeResolver.test.mjs
import { expect } from "chai";
import pkg from "hardhat";
const { ethers } = pkg;

describe("AMTTPDisputeResolver - Admin Stuck Funds Recovery", function () {
  let resolver, owner, user, recipient, arbitrator;
  const txId = ethers.keccak256(ethers.toUtf8Bytes("test-tx-1"));
  const amount = ethers.parseEther("1");

  beforeEach(async function () {
    [owner, user, recipient, arbitrator] = await ethers.getSigners();
    // Deploy mock arbitrator
    const MockArbitrator = await ethers.getContractFactory("MockArbitrator");
    const mockArb = await MockArbitrator.deploy();
    await mockArb.waitForDeployment();
    // Deploy resolver
    const AMTTPDisputeResolver = await ethers.getContractFactory("AMTTPDisputeResolver");
    resolver = await AMTTPDisputeResolver.deploy(
      await mockArb.getAddress(),
      "ipfs://metaEvidence"
    );
    await resolver.waitForDeployment();
  });

  it("allows admin to recover stuck funds after timeout", async function () {
    // User escrows funds
    await resolver.connect(user).escrowTransaction(
      txId,
      recipient.address,
      900,
      "ipfs://evidence",
      { value: amount }
    );
    // Fast forward past challenge window + 30 days
    const escrow = await resolver.escrows(txId);
    const challengeDeadline = escrow.challengeDeadline;
    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(challengeDeadline) + 30 * 24 * 3600 + 1]);
    await ethers.provider.send("evm_mine");
    // Admin triggers recovery - funds go to original sender (user), not owner
    // This is the correct security behavior: stuck funds return to sender
    await expect(resolver.connect(owner).emergencyWithdraw(txId))
      .to.changeEtherBalance(user, amount);
    // Status updated
    const escrowAfter = await resolver.escrows(txId);
    expect(escrowAfter.status).to.equal(4); // Executed
  });

  it("reverts if not enough time has passed", async function () {
    await resolver.connect(user).escrowTransaction(
      txId,
      recipient.address,
      900,
      "ipfs://evidence",
      { value: amount }
    );
    await expect(
      resolver.connect(owner).emergencyWithdraw(txId)
    ).to.be.revertedWith("Too early");
  });

  it("reverts if already executed", async function () {
    await resolver.connect(user).escrowTransaction(
      txId,
      recipient.address,
      900,
      "ipfs://evidence",
      { value: amount }
    );
    // Fast forward
    const escrow = await resolver.escrows(txId);
    const challengeDeadline = escrow.challengeDeadline;
    await ethers.provider.send("evm_setNextBlockTimestamp", [Number(challengeDeadline) + 30 * 24 * 3600 + 1]);
    await ethers.provider.send("evm_mine");
    await resolver.connect(owner).emergencyWithdraw(txId);
    await expect(
      resolver.connect(owner).emergencyWithdraw(txId)
    ).to.be.revertedWith("Already executed");
  });
});
