import { expect } from "chai";
import pkg from "hardhat";
const { ethers, upgrades } = pkg;

describe("AMTTPCore", function () {
  let amttp, owner, buyer, seller, oracle, approver;
  let defaultHashlock, preimage;
  
  async function getOracleSignature(buyerAddr, sellerAddr, amount, riskScore, kycHash) {
    const messageHash = ethers.solidityPackedKeccak256(
      ["address", "address", "uint256", "uint256", "bytes32"],
      [buyerAddr, sellerAddr, amount, riskScore, kycHash]
    );
    return await oracle.signMessage(ethers.getBytes(messageHash));
  }

  beforeEach(async function () {
    [owner, buyer, seller, oracle, approver] = await ethers.getSigners();
    
    const AMTTPCore = await ethers.getContractFactory("AMTTPCore");
    amttp = await upgrades.deployProxy(AMTTPCore, [oracle.address], { 
      initializer: "initialize",
      kind: "uups"
    });
    await amttp.waitForDeployment();
    
    preimage = ethers.encodeBytes32String("secret123");
    defaultHashlock = ethers.keccak256(ethers.solidityPacked(["bytes32"], [preimage]));
  });

  async function createSwap(buyerSigner, sellerAddr, amountEth, timelockOffset, riskScore) {
    const amount = ethers.parseEther(amountEth.toString());
    const timelock = Math.floor(Date.now() / 1000) + timelockOffset;
    const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-verified"));
    const signature = await getOracleSignature(buyerSigner.address, sellerAddr, amount, riskScore, kycHash);
    
    const tx = await amttp.connect(buyerSigner).initiateSwap(
      sellerAddr,
      defaultHashlock,
      timelock,
      riskScore,
      kycHash,
      signature,
      { value: amount }
    );
    
    const receipt = await tx.wait();
    const swapEvent = receipt.logs.find(log => {
      try {
        const parsed = amttp.interface.parseLog(log);
        return parsed && parsed.name === "SwapInitiated";
      } catch { return false; }
    });
    return amttp.interface.parseLog(swapEvent).args[0];
  }

  describe("Swap Initiation", function () {
    it("should initiate a swap with valid parameters", async function () {
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 100);
      expect(swapId).to.not.be.undefined;
      
      const swap = await amttp.swaps(swapId);
      expect(swap.buyer).to.equal(buyer.address);
      expect(swap.seller).to.equal(seller.address);
    });

    it("should reject swap with invalid seller address", async function () {
      const amount = ethers.parseEther("1");
      const timelock = Math.floor(Date.now() / 1000) + 3600;
      const riskScore = 100;
      const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-verified"));
      const signature = await getOracleSignature(buyer.address, ethers.ZeroAddress, amount, riskScore, kycHash);
      
      await expect(
        amttp.connect(buyer).initiateSwap(
          ethers.ZeroAddress,
          defaultHashlock,
          timelock,
          riskScore,
          kycHash,
          signature,
          { value: amount }
        )
      ).to.be.revertedWithCustomError(amttp, "InvalidSeller");
    });

    it("should reject swap with no ETH sent", async function () {
      const timelock = Math.floor(Date.now() / 1000) + 3600;
      const riskScore = 100;
      const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-verified"));
      const signature = await getOracleSignature(buyer.address, seller.address, 0, riskScore, kycHash);
      
      await expect(
        amttp.connect(buyer).initiateSwap(
          seller.address,
          defaultHashlock,
          timelock,
          riskScore,
          kycHash,
          signature,
          { value: 0 }
        )
      ).to.be.revertedWithCustomError(amttp, "NoETHSent");
    });

    it("should reject swap with past timelock", async function () {
      const amount = ethers.parseEther("1");
      const pastTimelock = Math.floor(Date.now() / 1000) - 3600;
      const riskScore = 100;
      const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-verified"));
      const signature = await getOracleSignature(buyer.address, seller.address, amount, riskScore, kycHash);
      
      await expect(
        amttp.connect(buyer).initiateSwap(
          seller.address,
          defaultHashlock,
          pastTimelock,
          riskScore,
          kycHash,
          signature,
          { value: amount }
        )
      ).to.be.revertedWithCustomError(amttp, "InvalidTimelock");
    });
  });

  describe("Swap Approval & Completion", function () {
    it("should approve a pending high-risk swap", async function () {
      // Use high risk score (>= 700) to create pending swap
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 750);
      
      let swap = await amttp.swaps(swapId);
      expect(swap.status).to.equal(0n); // Pending
      
      await amttp.connect(owner).approveSwap(swapId);
      
      swap = await amttp.swaps(swapId);
      expect(swap.status).to.equal(1n); // Approved
    });

    it("should auto-approve low-risk swaps", async function () {
      // Low risk score (< 700) gets auto-approved
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 100);
      
      const swap = await amttp.swaps(swapId);
      expect(swap.status).to.equal(1n); // Approved directly
    });

    it("should complete swap with valid preimage", async function () {
      // Low risk = auto-approved, can complete directly
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 100);
      
      const sellerBalBefore = await ethers.provider.getBalance(seller.address);
      await amttp.connect(seller).completeSwap(swapId, preimage);
      const sellerBalAfter = await ethers.provider.getBalance(seller.address);
      
      expect(sellerBalAfter).to.be.gt(sellerBalBefore);
      
      const swap = await amttp.swaps(swapId);
      expect(swap.status).to.equal(2n); // Completed
    });

    it("should reject completion with invalid preimage", async function () {
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 100);
      
      const wrongPreimage = ethers.encodeBytes32String("wrongsecret");
      await expect(
        amttp.connect(seller).completeSwap(swapId, wrongPreimage)
      ).to.be.revertedWithCustomError(amttp, "InvalidPreimage");
    });

    it("should reject completion of non-approved swap", async function () {
      // High risk score creates pending swap
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 750);
      
      await expect(
        amttp.connect(seller).completeSwap(swapId, preimage)
      ).to.be.revertedWithCustomError(amttp, "SwapNotApproved");
    });
  });

  describe("Swap Refund", function () {
    it("should refund expired swap", async function () {
      // Use a longer initial timelock that we can advance past
      const swapId = await createSwap(buyer, seller.address, 1, 60, 100);
      
      // Fast forward time past the timelock
      await ethers.provider.send("evm_increaseTime", [120]);
      await ethers.provider.send("evm_mine", []);
      
      await amttp.connect(buyer).refundSwap(swapId);
      
      const swap = await amttp.swaps(swapId);
      expect(swap.status).to.equal(3n); // Refunded
    });

    it("should reject refund of non-expired swap", async function () {
      const swapId = await createSwap(buyer, seller.address, 1, 3600, 100);
      
      await expect(
        amttp.connect(buyer).refundSwap(swapId)
      ).to.be.revertedWithCustomError(amttp, "SwapNotExpired");
    });
  });

  describe("Governance", function () {
    it("should allow owner to set approval threshold", async function () {
      await amttp.connect(owner).setApprovalThreshold(2);
      expect(await amttp.approvalThreshold()).to.equal(2n);
    });

    it("should allow owner to add approver", async function () {
      await amttp.connect(owner).addApprover(approver.address);
      expect(await amttp.isApprover(approver.address)).to.be.true;
    });

    it("should allow owner to remove approver", async function () {
      await amttp.connect(owner).addApprover(approver.address);
      await amttp.connect(owner).removeApprover(approver.address);
      expect(await amttp.isApprover(approver.address)).to.be.false;
    });

    it("should allow owner to set oracle", async function () {
      const newOracle = approver.address;
      await amttp.connect(owner).setOracle(newOracle);
      expect(await amttp.oracle()).to.equal(newOracle);
    });
  });
});
