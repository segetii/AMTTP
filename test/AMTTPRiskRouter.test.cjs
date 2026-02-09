/**
 * AMTTP Risk Router Tests
 * 
 * Comprehensive test suite for the L2 AI Risk Router
 * Tests batch processing, thresholds, circuit breaker, and emergency controls
 */

const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");
const { loadFixture } = require("@nomicfoundation/hardhat-network-helpers");

describe("AMTTPRiskRouter", function () {
    // Test fixtures for gas-efficient test setup
    async function deployRiskRouterFixture() {
        const [owner, oracle, operator, user1, user2, attacker] = await ethers.getSigners();

        // Deploy the Risk Router as an upgradeable proxy
        const AMTTPRiskRouter = await ethers.getContractFactory("AMTTPRiskRouter");
        const riskRouter = await upgrades.deployProxy(
            AMTTPRiskRouter,
            [oracle.address],
            { initializer: "initialize" }
        );
        await riskRouter.waitForDeployment();

        // Grant operator role
        const OPERATOR_ROLE = await riskRouter.OPERATOR_ROLE();
        await riskRouter.grantRole(OPERATOR_ROLE, operator.address);

        return {
            riskRouter,
            owner,
            oracle,
            operator,
            user1,
            user2,
            attacker,
            OPERATOR_ROLE
        };
    }

    // ═══════════════════════════════════════════════════════════════════════════
    // DEPLOYMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Deployment", function () {
        it("Should deploy with correct initial state", async function () {
            const { riskRouter, oracle } = await loadFixture(deployRiskRouterFixture);

            expect(await riskRouter.oracle()).to.equal(oracle.address);
            expect(await riskRouter.paused()).to.be.false;
        });

        it("Should set default thresholds correctly", async function () {
            const { riskRouter } = await loadFixture(deployRiskRouterFixture);

            // Default thresholds: low=25, medium=50, high=75
            const [low, medium, high] = await riskRouter.getThresholds();
            expect(low).to.equal(25);
            expect(medium).to.equal(50);
            expect(high).to.equal(75);
        });

        it("Should grant admin role to deployer", async function () {
            const { riskRouter, owner } = await loadFixture(deployRiskRouterFixture);

            const DEFAULT_ADMIN_ROLE = await riskRouter.DEFAULT_ADMIN_ROLE();
            expect(await riskRouter.hasRole(DEFAULT_ADMIN_ROLE, owner.address)).to.be.true;
        });

        it("Should not allow zero address oracle", async function () {
            const AMTTPRiskRouter = await ethers.getContractFactory("AMTTPRiskRouter");
            
            await expect(
                upgrades.deployProxy(
                    AMTTPRiskRouter,
                    [ethers.ZeroAddress],
                    { initializer: "initialize" }
                )
            ).to.be.revertedWith("Invalid oracle");
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // RISK ASSESSMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Risk Assessment", function () {
        it("Should assess minimal risk correctly (score 0-25)", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const tx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                15 // Low risk score
            );

            await expect(tx)
                .to.emit(riskRouter, "RiskAssessed")
                .withArgs(user1.address, user2.address, 15, 0); // Action 0 = APPROVE
        });

        it("Should assess low risk correctly (score 26-50)", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const tx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                40 // Low-medium risk score
            );

            await expect(tx)
                .to.emit(riskRouter, "RiskAssessed")
                .withArgs(user1.address, user2.address, 40, 1); // Action 1 = REVIEW
        });

        it("Should assess medium risk correctly (score 51-75)", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const tx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                60 // Medium risk score
            );

            await expect(tx)
                .to.emit(riskRouter, "RiskAssessed")
                .withArgs(user1.address, user2.address, 60, 2); // Action 2 = ESCROW
        });

        it("Should assess high risk correctly (score 76-100)", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const tx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                85 // High risk score
            );

            await expect(tx)
                .to.emit(riskRouter, "RiskAssessed")
                .withArgs(user1.address, user2.address, 85, 3); // Action 3 = BLOCK
        });

        it("Should reject risk scores above 100", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(oracle).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    101
                )
            ).to.be.revertedWith("Invalid risk score");
        });

        it("Should only allow oracle to assess risk", async function () {
            const { riskRouter, user1, user2, attacker } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(attacker).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    50
                )
            ).to.be.revertedWith("Only oracle");
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // BATCH PROCESSING TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Batch Processing", function () {
        it("Should process batch assessments successfully", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const senders = [user1.address, user1.address, user2.address];
            const recipients = [user2.address, user2.address, user1.address];
            const amounts = [
                ethers.parseEther("100"),
                ethers.parseEther("200"),
                ethers.parseEther("50")
            ];
            const scores = [10, 45, 80];

            const tx = await riskRouter.connect(oracle).batchAssessRisk(
                senders,
                recipients,
                amounts,
                scores
            );

            await expect(tx).to.emit(riskRouter, "BatchProcessed").withArgs(3);
        });

        it("Should reject mismatched batch arrays", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const senders = [user1.address, user1.address];
            const recipients = [user2.address]; // Mismatched length
            const amounts = [ethers.parseEther("100"), ethers.parseEther("200")];
            const scores = [10, 45];

            await expect(
                riskRouter.connect(oracle).batchAssessRisk(
                    senders,
                    recipients,
                    amounts,
                    scores
                )
            ).to.be.revertedWith("Array length mismatch");
        });

        it("Should reject empty batch", async function () {
            const { riskRouter, oracle } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(oracle).batchAssessRisk([], [], [], [])
            ).to.be.revertedWith("Empty batch");
        });

        it("Should enforce max batch size", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            // Create arrays larger than max batch size (100)
            const count = 101;
            const senders = Array(count).fill(user1.address);
            const recipients = Array(count).fill(user2.address);
            const amounts = Array(count).fill(ethers.parseEther("10"));
            const scores = Array(count).fill(25);

            await expect(
                riskRouter.connect(oracle).batchAssessRisk(
                    senders,
                    recipients,
                    amounts,
                    scores
                )
            ).to.be.revertedWith("Batch too large");
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // THRESHOLD CONFIGURATION TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Threshold Configuration", function () {
        it("Should allow operator to update thresholds", async function () {
            const { riskRouter, operator } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(operator).setThresholds(30, 60, 80);

            const [low, medium, high] = await riskRouter.getThresholds();
            expect(low).to.equal(30);
            expect(medium).to.equal(60);
            expect(high).to.equal(80);
        });

        it("Should emit event on threshold update", async function () {
            const { riskRouter, operator } = await loadFixture(deployRiskRouterFixture);

            await expect(riskRouter.connect(operator).setThresholds(30, 60, 80))
                .to.emit(riskRouter, "ThresholdsUpdated")
                .withArgs(30, 60, 80);
        });

        it("Should reject invalid threshold order", async function () {
            const { riskRouter, operator } = await loadFixture(deployRiskRouterFixture);

            // Low > Medium
            await expect(
                riskRouter.connect(operator).setThresholds(60, 50, 80)
            ).to.be.revertedWith("Invalid thresholds");

            // Medium > High
            await expect(
                riskRouter.connect(operator).setThresholds(30, 85, 80)
            ).to.be.revertedWith("Invalid thresholds");
        });

        it("Should reject thresholds above 100", async function () {
            const { riskRouter, operator } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(operator).setThresholds(30, 60, 101)
            ).to.be.revertedWith("Invalid thresholds");
        });

        it("Should not allow non-operator to update thresholds", async function () {
            const { riskRouter, attacker } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(attacker).setThresholds(30, 60, 80)
            ).to.be.reverted;
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // CIRCUIT BREAKER TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Circuit Breaker", function () {
        it("Should trigger circuit breaker after consecutive high-risk", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            // Simulate consecutive high-risk transactions
            for (let i = 0; i < 10; i++) {
                await riskRouter.connect(oracle).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    90 // High risk
                );
            }

            expect(await riskRouter.circuitBreakerActive()).to.be.true;
        });

        it("Should block all transactions when circuit breaker is active", async function () {
            const { riskRouter, user1, user2, oracle, operator } = await loadFixture(deployRiskRouterFixture);

            // Manually activate circuit breaker
            await riskRouter.connect(operator).activateCircuitBreaker();

            await expect(
                riskRouter.connect(oracle).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    10 // Even low risk should be blocked
                )
            ).to.be.revertedWith("Circuit breaker active");
        });

        it("Should allow operator to deactivate circuit breaker", async function () {
            const { riskRouter, user1, user2, oracle, operator } = await loadFixture(deployRiskRouterFixture);

            // Activate then deactivate
            await riskRouter.connect(operator).activateCircuitBreaker();
            expect(await riskRouter.circuitBreakerActive()).to.be.true;

            await riskRouter.connect(operator).deactivateCircuitBreaker();
            expect(await riskRouter.circuitBreakerActive()).to.be.false;

            // Should work again
            await expect(
                riskRouter.connect(oracle).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    10
                )
            ).to.not.be.reverted;
        });

        it("Should emit event on circuit breaker activation", async function () {
            const { riskRouter, operator } = await loadFixture(deployRiskRouterFixture);

            await expect(riskRouter.connect(operator).activateCircuitBreaker())
                .to.emit(riskRouter, "CircuitBreakerActivated");
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // PAUSE/UNPAUSE TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Emergency Controls", function () {
        it("Should allow admin to pause", async function () {
            const { riskRouter, owner } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(owner).pause();
            expect(await riskRouter.paused()).to.be.true;
        });

        it("Should block operations when paused", async function () {
            const { riskRouter, owner, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(owner).pause();

            await expect(
                riskRouter.connect(oracle).assessRisk(
                    user1.address,
                    user2.address,
                    ethers.parseEther("100"),
                    50
                )
            ).to.be.reverted;
        });

        it("Should allow admin to unpause", async function () {
            const { riskRouter, owner } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(owner).pause();
            await riskRouter.connect(owner).unpause();
            expect(await riskRouter.paused()).to.be.false;
        });

        it("Should not allow non-admin to pause", async function () {
            const { riskRouter, attacker } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(attacker).pause()
            ).to.be.reverted;
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // ORACLE MANAGEMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Oracle Management", function () {
        it("Should allow admin to update oracle", async function () {
            const { riskRouter, owner, user1 } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(owner).setOracle(user1.address);
            expect(await riskRouter.oracle()).to.equal(user1.address);
        });

        it("Should emit event on oracle update", async function () {
            const { riskRouter, owner, oracle, user1 } = await loadFixture(deployRiskRouterFixture);

            await expect(riskRouter.connect(owner).setOracle(user1.address))
                .to.emit(riskRouter, "OracleUpdated")
                .withArgs(oracle.address, user1.address);
        });

        it("Should not allow zero address oracle", async function () {
            const { riskRouter, owner } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(owner).setOracle(ethers.ZeroAddress)
            ).to.be.revertedWith("Invalid oracle");
        });

        it("Should not allow non-admin to update oracle", async function () {
            const { riskRouter, attacker, user1 } = await loadFixture(deployRiskRouterFixture);

            await expect(
                riskRouter.connect(attacker).setOracle(user1.address)
            ).to.be.reverted;
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // STATISTICS & QUERIES
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Statistics & Queries", function () {
        it("Should track assessment counts correctly", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            // Assess a few transactions with different scores
            await riskRouter.connect(oracle).assessRisk(user1.address, user2.address, ethers.parseEther("100"), 10);
            await riskRouter.connect(oracle).assessRisk(user1.address, user2.address, ethers.parseEther("100"), 40);
            await riskRouter.connect(oracle).assessRisk(user1.address, user2.address, ethers.parseEther("100"), 60);
            await riskRouter.connect(oracle).assessRisk(user1.address, user2.address, ethers.parseEther("100"), 90);

            const stats = await riskRouter.getStatistics();
            expect(stats.totalAssessments).to.equal(4);
            expect(stats.approvedCount).to.equal(1);
            expect(stats.reviewCount).to.equal(1);
            expect(stats.escrowCount).to.equal(1);
            expect(stats.blockedCount).to.equal(1);
        });

        it("Should return last assessment for address pair", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                42
            );

            const result = await riskRouter.getLastAssessment(user1.address, user2.address);
            expect(result.riskScore).to.equal(42);
            expect(result.action).to.equal(1); // REVIEW
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // GAS OPTIMIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Gas Optimization", function () {
        it("Should be gas efficient for single assessment", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            const tx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                50
            );

            const receipt = await tx.wait();
            // L2 optimized - should be under 100k gas for single assessment
            expect(receipt.gasUsed).to.be.lessThan(100000);
        });

        it("Should be more efficient per-tx in batch mode", async function () {
            const { riskRouter, user1, user2, oracle } = await loadFixture(deployRiskRouterFixture);

            // Measure single tx gas
            const singleTx = await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                50
            );
            const singleReceipt = await singleTx.wait();
            const singleGas = singleReceipt.gasUsed;

            // Measure batch tx gas (10 transactions)
            const count = 10;
            const senders = Array(count).fill(user1.address);
            const recipients = Array(count).fill(user2.address);
            const amounts = Array(count).fill(ethers.parseEther("10"));
            const scores = Array(count).fill(25);

            const batchTx = await riskRouter.connect(oracle).batchAssessRisk(
                senders,
                recipients,
                amounts,
                scores
            );
            const batchReceipt = await batchTx.wait();
            const batchGasPerTx = batchReceipt.gasUsed / BigInt(count);

            // Batch should be at least 20% more efficient per transaction
            expect(batchGasPerTx).to.be.lessThan((singleGas * BigInt(80)) / BigInt(100));
        });
    });

    // ═══════════════════════════════════════════════════════════════════════════
    // UPGRADEABILITY TESTS
    // ═══════════════════════════════════════════════════════════════════════════

    describe("Upgradeability", function () {
        it("Should preserve state after upgrade", async function () {
            const { riskRouter, user1, user2, oracle, owner } = await loadFixture(deployRiskRouterFixture);

            // Make some state changes
            await riskRouter.connect(oracle).assessRisk(
                user1.address,
                user2.address,
                ethers.parseEther("100"),
                42
            );

            const statsBefore = await riskRouter.getStatistics();

            // Deploy V2 (same contract for this test)
            const AMTTPRiskRouterV2 = await ethers.getContractFactory("AMTTPRiskRouter");
            const upgraded = await upgrades.upgradeProxy(
                await riskRouter.getAddress(),
                AMTTPRiskRouterV2
            );

            // Verify state preserved
            const statsAfter = await upgraded.getStatistics();
            expect(statsAfter.totalAssessments).to.equal(statsBefore.totalAssessments);
        });

        it("Should only allow admin to upgrade", async function () {
            const { riskRouter, attacker } = await loadFixture(deployRiskRouterFixture);

            const AMTTPRiskRouterV2 = await ethers.getContractFactory("AMTTPRiskRouter", attacker);
            
            await expect(
                upgrades.upgradeProxy(await riskRouter.getAddress(), AMTTPRiskRouterV2)
            ).to.be.reverted;
        });
    });
});
