// test/AMTTPPolicyEngine.test.mjs
import { expect } from "chai";
import pkg from "hardhat";
const { ethers, upgrades } = pkg;

describe("AMTTPPolicyEngine", function () {
  let policyEngine;
  let amttp;
  let owner;
  let user1;
  let user2;
  let oracle;

  beforeEach(async function () {
    [owner, user1, user2, oracle] = await ethers.getSigners();

    // Deploy mock AMTTP contract
    const AMTTP = await ethers.getContractFactory("AMTTP");
    amttp = await upgrades.deployProxy(AMTTP, [], {
      initializer: "initialize",
    });
    await amttp.waitForDeployment();

    // Deploy Policy Engine
    const AMTTPPolicyEngine = await ethers.getContractFactory("AMTTPPolicyEngine");
    policyEngine = await upgrades.deployProxy(
      AMTTPPolicyEngine,
      [await amttp.getAddress(), oracle.address],
      { initializer: "initialize" }
    );
    await policyEngine.waitForDeployment();

    // Connect policy engine to AMTTP
    await amttp.setPolicyEngine(await policyEngine.getAddress());
  });

  describe("Initialization", function () {
    it("should initialize with correct parameters", async function () {
      const status = await policyEngine.getPolicyEngineStatus();
      expect(status.policyEngineAddress).to.equal(await policyEngine.getAddress());
      expect(status.enabled).to.be.true;
      expect(status.globalThreshold).to.equal(700);
      expect(status.defaultModel).to.equal("DQN-v1.0-real-fraud");
    });

    it("should set correct model performance", async function () {
      const performance = await policyEngine.getModelPerformance("DQN-v1.0-real-fraud");
      expect(performance).to.equal(669); // F1 score of 0.669
    });
  });

  describe("Transaction Policy Management", function () {
    it("should set transaction policy", async function () {
      await policyEngine.connect(user1).setTransactionPolicy(
        user1.address,
        ethers.parseEther("5"), // maxAmount
        ethers.parseEther("20"), // dailyLimit
        ethers.parseEther("100"), // weeklyLimit
        ethers.parseEther("300"), // monthlyLimit
        600, // riskThreshold (0.60)
        true, // autoApprove
        1800 // cooldownPeriod (30 min)
      );

      const policy = await policyEngine.getUserPolicy(user1.address);
      expect(policy.maxAmount).to.equal(ethers.parseEther("5"));
      expect(policy.riskThreshold).to.equal(600);
      expect(policy.autoApprove).to.be.true;
    });

    it("should reject policy with excessive limits", async function () {
      await expect(
        policyEngine.connect(user1).setTransactionPolicy(
          user1.address,
          ethers.parseEther("200"), // Exceeds global limit
          ethers.parseEther("500"),
          ethers.parseEther("1000"),
          ethers.parseEther("2000"),
          700,
          true,
          3600
        )
      ).to.be.revertedWith("Exceeds global limit");
    });
  });

  describe("Risk Policy Management", function () {
    it("should set risk policy with DQN thresholds", async function () {
      const thresholds = [200, 400, 669, 850]; // Based on DQN model performance
      const actions = [0, 0, 1, 2]; // Approve, Approve, Review, Escrow

      await policyEngine.connect(user1).setRiskPolicy(
        user1.address,
        thresholds,
        actions,
        false
      );

      const riskPolicy = await policyEngine.getUserRiskPolicy(user1.address);
      expect(riskPolicy.lowThreshold).to.equal(400);
      expect(riskPolicy.mediumThreshold).to.equal(669); // F1 score threshold
      expect(riskPolicy.highThreshold).to.equal(850);
    });

    it("should reject invalid risk thresholds", async function () {
      const invalidThresholds = [400, 300, 500, 600]; // Not ascending
      const actions = [0, 0, 1, 2];

      await expect(
        policyEngine.connect(user1).setRiskPolicy(
          user1.address,
          invalidThresholds,
          actions,
          false
        )
      ).to.be.revertedWith("Invalid thresholds");
    });
  });

  describe("Transaction Validation with DQN Scores", function () {
    beforeEach(async function () {
      // Set up user policies
      await policyEngine.connect(user1).setTransactionPolicy(
        user1.address,
        ethers.parseEther("10"),
        ethers.parseEther("50"),
        ethers.parseEther("200"),
        ethers.parseEther("500"),
        700,
        true,
        3600
      );

      const thresholds = [200, 400, 700, 1000];
      const actions = [0, 0, 1, 2]; // Approve, Approve, Review, Escrow
      await policyEngine.connect(user1).setRiskPolicy(
        user1.address,
        thresholds,
        actions,
        false
      );
    });

    it("should approve low-risk DQN transaction", async function () {
      const result = await policyEngine.validateTransaction(
        user1.address,
        user2.address,
        ethers.parseEther("1"),
        300, // Low DQN risk score (0.30)
        "DQN-v1.0-real-fraud",
        ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
      );

      expect(result.action).to.equal(0); // PolicyAction.Approve
      expect(result.reason).to.contain("Auto-approved");
    });

    it("should require review for medium-risk DQN transaction", async function () {
      const result = await policyEngine.validateTransaction(
        user1.address,
        user2.address,
        ethers.parseEther("2"),
        650, // Medium DQN risk score (0.65)
        "DQN-v1.0-real-fraud",
        ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
      );

      expect(result.action).to.equal(1); // PolicyAction.Review
    });

    it("should require escrow for high-risk DQN transaction", async function () {
      const result = await policyEngine.validateTransaction(
        user1.address,
        user2.address,
        ethers.parseEther("3"),
        850, // High DQN risk score (0.85)
        "DQN-v1.0-real-fraud",
        ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
      );

      expect(result.action).to.equal(2); // PolicyAction.Escrow
    });

    it("should block transaction exceeding amount limit", async function () {
      await expect(
        policyEngine.validateTransaction(
          user1.address,
          user2.address,
          ethers.parseEther("15"), // Exceeds 10 ETH limit
          300,
          "DQN-v1.0-real-fraud",
          ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
        )
      ).to.be.revertedWith("Exceeds maximum amount");
    });

    it("should reject unverified DQN model", async function () {
      await expect(
        policyEngine.validateTransaction(
          user1.address,
          user2.address,
          ethers.parseEther("1"),
          300,
          "unverified-model-v1.0", // Not approved model
          ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
        )
      ).to.be.revertedWith("Model version not approved");
    });
  });

  describe("Velocity Limits", function () {
    it("should add velocity limit", async function () {
      await policyEngine.connect(user1).addVelocityLimit(
        user1.address,
        5, // max 5 transactions
        ethers.parseEther("25"), // max 25 ETH volume
        1 // VelocityWindow.Day
      );

      // This would require additional implementation to test velocity tracking
      // For now, just verify the function doesn't revert
    });
  });

  describe("Compliance Rules", function () {
    it("should set compliance rules", async function () {
      await policyEngine.connect(user1).setComplianceRules(
        user1.address,
        true, // requireKYC
        false, // requireApproval
        ethers.parseEther("5"), // approvalThreshold
        3600, // approvalTimeout
        false // geofencing
      );

      // Verify KYC requirement
      const result = await policyEngine.validateTransaction(
        user1.address,
        user2.address,
        ethers.parseEther("1"),
        300,
        "DQN-v1.0-real-fraud",
        "0x0000000000000000000000000000000000000000000000000000000000000000" // No KYC
      );

      expect(result.action).to.equal(3); // PolicyAction.Block
      expect(result.reason).to.contain("KYC required");
    });
  });

  describe("DQN Model Management", function () {
    it("should update model version", async function () {
      await policyEngine.connect(oracle).updateModelVersion(
        "DQN-v2.0-enhanced",
        750 // F1 score of 0.750
      );

      const performance = await policyEngine.getModelPerformance("DQN-v2.0-enhanced");
      expect(performance).to.equal(750);
    });

    it("should reject low-performance model", async function () {
      await expect(
        policyEngine.connect(oracle).updateModelVersion(
          "low-performance-model",
          500 // F1 score of 0.500 (below minimum of 0.669)
        )
      ).to.be.revertedWith("Model performance too low");
    });
  });

  describe("Trusted Users", function () {
    it("should add trusted user", async function () {
      await policyEngine.addTrustedUser(user1.address);
      expect(await policyEngine.isTrustedUser(user1.address)).to.be.true;
    });

    it("should remove trusted user", async function () {
      await policyEngine.addTrustedUser(user1.address);
      await policyEngine.removeTrustedUser(user1.address);
      expect(await policyEngine.isTrustedUser(user1.address)).to.be.false;
    });
  });

  describe("Emergency Controls", function () {
    it("should pause system", async function () {
      await policyEngine.setEmergencyPause(true);

      await expect(
        policyEngine.validateTransaction(
          user1.address,
          user2.address,
          ethers.parseEther("1"),
          300,
          "DQN-v1.0-real-fraud",
          ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
        )
      ).to.be.revertedWith("System paused");
    });

    it("should freeze and unfreeze account", async function () {
      await policyEngine.freezeAccount(user1.address, "Suspicious activity");

      await expect(
        policyEngine.validateTransaction(
          user1.address,
          user2.address,
          ethers.parseEther("1"),
          300,
          "DQN-v1.0-real-fraud",
          ethers.keccak256(ethers.toUtf8Bytes("kyc-data"))
        )
      ).to.be.revertedWith("Account frozen");

      await policyEngine.unfreezeAccount(user1.address);
      // Should not revert after unfreezing
    });
  });

  describe("Integration with AMTTP Contract", function () {
    it("should validate transaction through AMTTP", async function () {
      // This would require a full integration test with the AMTTP contract
      // The basic structure is in place for the integration
      const status = await policyEngine.getPolicyEngineStatus();
      expect(status.enabled).to.be.true;
    });
  });
});