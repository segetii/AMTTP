// test/AMTTP1.test.mjs
import { expect } from "chai";
import pkg from "hardhat";
const { ethers, upgrades } = pkg;

describe("AMTTP", function () {
  let amttp;
  let mockERC20;
  let mockERC721;
  let owner;
  let buyer;
  let seller;
  let approver;
  let oracle;

  // Helper to get blockchain timestamp
  async function getBlockTimestamp() {
    const blockNum = await ethers.provider.getBlockNumber();
    const block = await ethers.provider.getBlock(blockNum);
    return block.timestamp;
  }

  beforeEach(async function () {
    [owner, buyer, seller, approver, oracle] = await ethers.getSigners();

    const MockERC20 = await ethers.getContractFactory("MockERC20");
    mockERC20 = await MockERC20.deploy("Mock Token", "MOCK");
    await mockERC20.waitForDeployment();
    await mockERC20.connect(owner).mint(buyer.address, ethers.parseEther("10000"));
    await mockERC20.connect(owner).mint(seller.address, ethers.parseEther("10000"));

    const MockERC721 = await ethers.getContractFactory("MockERC721");
    mockERC721 = await MockERC721.deploy("Mock NFT", "MNFT");
    await mockERC721.waitForDeployment();
    await mockERC721.connect(owner).mint(buyer.address);
    await mockERC721.connect(owner).mint(seller.address);


    const AMTTP = await ethers.getContractFactory("AMTTP");
    amttp = await upgrades.deployProxy(AMTTP, [oracle.address, 1], {
      initializer: "initialize",
    });
    await amttp.waitForDeployment();

    await amttp.connect(owner).addApprover(approver.address);
  });

  describe("Initialization", function () {
    it("should set oracle and threshold correctly", async function () {
      expect(await amttp.oracle()).to.equal(oracle.address);
      expect(await amttp.threshold()).to.equal(1);
      expect(await amttp.owner()).to.equal(owner.address);
    });

    it("should allow owner to add/remove approvers", async function () {
      expect(await amttp.isApprover(approver.address)).to.be.true;
      await expect(amttp.connect(owner).removeApprover(approver.address))
        .to.emit(amttp, "ApproverRemoved")
        .withArgs(approver.address);
      expect(await amttp.isApprover(approver.address)).to.be.false;
    });

    it("should allow owner to set threshold and oracle", async function () {
      const anotherApprover = (await ethers.getSigners())[5];
      await amttp.connect(owner).addApprover(anotherApprover.address);
      
      await amttp.connect(owner).setThreshold(2);
      expect(await amttp.threshold()).to.equal(2);

      const newOracle = seller;
      await amttp.connect(owner).setOracle(newOracle.address);
      expect(await amttp.oracle()).to.equal(newOracle.address);
    });
  });

  describe("ETH Swaps", function () {
    const amount = ethers.parseEther("1");
    const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-data"));
    const riskNone = 0;
    const riskMedium = 2;
    const riskHigh = 3;

    it("should complete low-risk ETH swap without approval", async function () {
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;

        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwap(seller.address, hashlock, timelock, riskNone, kycHash, oracleSig, { value: amount });
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await expect(amttp.connect(seller).completeSwap(swapId, preimage)).to.emit(amttp, "SwapCompleted").withArgs(swapId, seller.address);
        expect((await amttp.swaps(swapId)).completed).to.be.true;
    });

    it("should complete medium-risk ETH swap with approval", async function () {
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;

        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskMedium, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwap(seller.address, hashlock, timelock, riskMedium, kycHash, oracleSig, { value: amount });
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await amttp.connect(approver).approveSwap(swapId);
        await expect(amttp.connect(seller).completeSwap(swapId, preimage)).to.emit(amttp, "SwapCompleted");
    });

    it("should revert complete if not enough approvals for high risk", async function () {
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;
        
        // FIX: Add a second approver before setting the threshold to 2
        const anotherApprover = (await ethers.getSigners())[5];
        await amttp.connect(owner).addApprover(anotherApprover.address);
        await amttp.connect(owner).setThreshold(2);

        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskHigh, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwap(seller.address, hashlock, timelock, riskHigh, kycHash, oracleSig, { value: amount });
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);
        
        // Only one approver approves
        await amttp.connect(approver).approveSwap(swapId);
        
        // Should revert because threshold is 2, but only 1 approved
        await expect(amttp.connect(seller).completeSwap(swapId, preimage)).to.be.revertedWith("Not enough approvals");
    });

    it("should refund ETH swap after timelock", async function () {
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;

        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwap(seller.address, hashlock, timelock, riskNone, kycHash, oracleSig, { value: amount });
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await ethers.provider.send("evm_increaseTime", [3601]);
        await ethers.provider.send("evm_mine");

        await expect(amttp.connect(buyer).refundSwap(swapId)).to.emit(amttp, "SwapRefunded").withArgs(swapId, buyer.address);
        expect((await amttp.swaps(swapId)).refunded).to.be.true;
    });
  });

  describe("ERC20 Swaps", function () {
    it("should complete ERC20 swap", async function () {
        const amount = ethers.parseEther("100");
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;
        const riskNone = 0;
        const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-data"));

        await mockERC20.connect(buyer).approve(amttp.target, amount);
        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwapERC20(seller.address, mockERC20.target, amount, hashlock, timelock, riskNone, kycHash, oracleSig);
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await expect(amttp.connect(seller).completeSwap(swapId, preimage)).to.emit(amttp, "SwapCompleted");
        expect(await mockERC20.balanceOf(seller.address)).to.be.gt(ethers.parseEther("10000"));
    });

    it("should refund ERC20 swap after timelock", async function () {
        const amount = ethers.parseEther("100");
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;
        const riskNone = 0;
        const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-data"));

        await mockERC20.connect(buyer).approve(amttp.target, amount);
        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwapERC20(seller.address, mockERC20.target, amount, hashlock, timelock, riskNone, kycHash, oracleSig);
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await ethers.provider.send("evm_increaseTime", [3601]);
        await ethers.provider.send("evm_mine");

        const balanceBefore = await mockERC20.balanceOf(buyer.address);
        await amttp.connect(buyer).refundSwap(swapId);
        const balanceAfter = await mockERC20.balanceOf(buyer.address);
        // FIX: Use standard bigint arithmetic
        expect(balanceAfter).to.equal(balanceBefore + amount);
    });
  });

  describe("ERC721 Swaps", function () {
    // ... ERC721 tests can be structured similarly ...
    it("should complete ERC721 swap", async function () {
        const tokenId = 1;
        const preimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;
        const riskNone = 0;
        const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-data"));

        await mockERC721.connect(buyer).approve(amttp.target, tokenId);
        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, 1, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwapERC721(seller.address, mockERC721.target, tokenId, hashlock, timelock, riskNone, kycHash, oracleSig);
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await expect(amttp.connect(seller).completeSwap(swapId, preimage)).to.emit(amttp, "SwapCompleted");
        expect(await mockERC721.ownerOf(tokenId)).to.equal(seller.address);
    });
  });

  describe("Security and Edge Cases", function () {
    it("should revert complete with wrong preimage", async function () {
        const amount = ethers.parseEther("1");
        const preimage = ethers.randomBytes(32);
        // FIX: Use a different, but still valid, 32-byte value
        const wrongPreimage = ethers.randomBytes(32);
        const hashlock = ethers.keccak256(preimage);
        const timelock = (await getBlockTimestamp()) + 3600;
        const riskNone = 0;
        const kycHash = ethers.keccak256(ethers.toUtf8Bytes("kyc-data"));

        const digest = ethers.keccak256(ethers.AbiCoder.defaultAbiCoder().encode(["address", "address", "uint256", "uint8", "bytes32"], [buyer.address, seller.address, amount, riskNone, kycHash]));
        const oracleSig = await oracle.signMessage(ethers.getBytes(digest));

        await amttp.connect(buyer).initiateSwap(seller.address, hashlock, timelock, riskNone, kycHash, oracleSig, { value: amount });
        const swapId = ethers.solidityPackedKeccak256(["address", "address", "bytes32", "uint256"], [buyer.address, seller.address, hashlock, timelock]);

        await expect(amttp.connect(seller).completeSwap(swapId, wrongPreimage)).to.be.revertedWith("Invalid preimage");
    });
    
    // ... other security tests ...
  });
});