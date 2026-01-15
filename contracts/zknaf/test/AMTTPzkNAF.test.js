const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");

/**
 * AMTTPzkNAF Hardhat Tests
 * Tests for the zkNAF Groth16 verifier contract
 */
describe("AMTTPzkNAF", function () {
    let zknaf;
    let owner;
    let user1;
    let user2;
    let oracle;

    // Sample test verification key values
    const testAlpha1 = [
        "0x2260e724844bca5251829f9e8f2d2f2b8b9dc3e6b3b3c7a7e6f8d8d8d8d8d8d8",
        "0x1260e724844bca5251829f9e8f2d2f2b8b9dc3e6b3b3c7a7e6f8d8d8d8d8d8d8"
    ];

    const testBeta2 = [
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"]
    ];

    const testGamma2 = [
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"]
    ];

    const testDelta2 = [
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"],
        ["0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
         "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"]
    ];

    const testIC = [
        ["0x0000000000000000000000000000000000000000000000000000000000000001",
         "0x0000000000000000000000000000000000000000000000000000000000000002"],
        ["0x0000000000000000000000000000000000000000000000000000000000000003",
         "0x0000000000000000000000000000000000000000000000000000000000000004"]
    ];

    // ProofType enum values
    const ProofType = {
        SANCTIONS: 0,
        RISK_LOW: 1,
        RISK_MEDIUM: 2,
        KYC_VERIFIED: 3
    };

    beforeEach(async function () {
        [owner, user1, user2, oracle] = await ethers.getSigners();

        const AMTTPzkNAF = await ethers.getContractFactory("AMTTPzkNAF");
        zknaf = await upgrades.deployProxy(AMTTPzkNAF, [], { initializer: 'initialize' });
        await zknaf.waitForDeployment();
    });

    describe("Initialization", function () {
        it("should initialize with correct owner", async function () {
            expect(await zknaf.owner()).to.equal(owner.address);
        });

        it("should not be paused on deployment", async function () {
            expect(await zknaf.paused()).to.be.false;
        });

        it("should not allow re-initialization", async function () {
            await expect(zknaf.initialize()).to.be.reverted;
        });
    });

    describe("Verification Key Management", function () {
        it("should allow owner to set verification key", async function () {
            await expect(
                zknaf.setVerificationKey(
                    ProofType.SANCTIONS,
                    testAlpha1,
                    testBeta2,
                    testGamma2,
                    testDelta2,
                    testIC
                )
            ).to.emit(zknaf, "VerificationKeyUpdated");
        });

        it("should store verification key correctly", async function () {
            await zknaf.setVerificationKey(
                ProofType.SANCTIONS,
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                testIC
            );

            const key = await zknaf.getVerifyingKey(ProofType.SANCTIONS);
            expect(key.alpha1[0]).to.equal(testAlpha1[0]);
            expect(key.alpha1[1]).to.equal(testAlpha1[1]);
        });

        it("should reject verification key from non-owner", async function () {
            await expect(
                zknaf.connect(user1).setVerificationKey(
                    ProofType.SANCTIONS,
                    testAlpha1,
                    testBeta2,
                    testGamma2,
                    testDelta2,
                    testIC
                )
            ).to.be.reverted;
        });

        it("should allow setting keys for all proof types", async function () {
            for (const [name, value] of Object.entries(ProofType)) {
                await zknaf.setVerificationKey(
                    value,
                    testAlpha1,
                    testBeta2,
                    testGamma2,
                    testDelta2,
                    testIC
                );

                const key = await zknaf.getVerifyingKey(value);
                expect(key.alpha1[0]).to.equal(testAlpha1[0]);
            }
        });
    });

    describe("Proof Validity", function () {
        it("should return false for non-existent proof", async function () {
            expect(await zknaf.isProofValid(user1.address, ProofType.SANCTIONS)).to.be.false;
        });

        it("should allow owner to set proof validity period", async function () {
            const oneYear = 365 * 24 * 60 * 60;
            await zknaf.setProofValidity(ProofType.SANCTIONS, oneYear);
            expect(await zknaf.proofValidity(ProofType.SANCTIONS)).to.equal(oneYear);
        });

        it("should reject validity period change from non-owner", async function () {
            await expect(
                zknaf.connect(user1).setProofValidity(ProofType.SANCTIONS, 3600)
            ).to.be.reverted;
        });
    });

    describe("Proof Record Management", function () {
        it("should return empty record for user without proof", async function () {
            const record = await zknaf.getProofRecord(user1.address, ProofType.SANCTIONS);
            expect(record.timestamp).to.equal(0);
            expect(record.isValid).to.be.false;
        });

        it("should allow owner to revoke proof", async function () {
            await zknaf.revokeProof(user1.address, ProofType.SANCTIONS);
            const record = await zknaf.getProofRecord(user1.address, ProofType.SANCTIONS);
            expect(record.isValid).to.be.false;
        });

        it("should reject proof revocation from non-owner", async function () {
            await expect(
                zknaf.connect(user1).revokeProof(user2.address, ProofType.SANCTIONS)
            ).to.be.reverted;
        });
    });

    describe("Pausable", function () {
        it("should allow owner to pause", async function () {
            await zknaf.pause();
            expect(await zknaf.paused()).to.be.true;
        });

        it("should allow owner to unpause", async function () {
            await zknaf.pause();
            await zknaf.unpause();
            expect(await zknaf.paused()).to.be.false;
        });

        it("should reject pause from non-owner", async function () {
            await expect(zknaf.connect(user1).pause()).to.be.reverted;
        });
    });

    describe("Gas Estimation", function () {
        it("should consume reasonable gas for setVerificationKey", async function () {
            const tx = await zknaf.setVerificationKey(
                ProofType.SANCTIONS,
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                testIC
            );

            const receipt = await tx.wait();
            const gasUsed = receipt.gasUsed;

            console.log(`   Gas used for setVerificationKey: ${gasUsed}`);
            expect(gasUsed).to.be.lessThan(500000);
        });

        it("should consume reasonable gas for getVerifyingKey", async function () {
            await zknaf.setVerificationKey(
                ProofType.SANCTIONS,
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                testIC
            );

            // Estimate gas for view function call
            const gasEstimate = await zknaf.getVerifyingKey.estimateGas(ProofType.SANCTIONS);
            console.log(`   Gas estimate for getVerifyingKey: ${gasEstimate}`);
            expect(gasEstimate).to.be.lessThan(50000);
        });
    });

    describe("Edge Cases", function () {
        it("should handle maximum IC array size", async function () {
            // Create large IC array (max reasonable for our circuits)
            const largeIC = [];
            for (let i = 0; i < 10; i++) {
                largeIC.push([
                    ethers.zeroPadValue(ethers.toBeHex(i * 2 + 1), 32),
                    ethers.zeroPadValue(ethers.toBeHex(i * 2 + 2), 32)
                ]);
            }

            await zknaf.setVerificationKey(
                ProofType.SANCTIONS,
                testAlpha1,
                testBeta2,
                testGamma2,
                testDelta2,
                largeIC
            );

            const key = await zknaf.getVerifyingKey(ProofType.SANCTIONS);
            expect(key.ic.length).to.equal(10);
        });

        it("should handle zero proof validity", async function () {
            await zknaf.setProofValidity(ProofType.SANCTIONS, 0);
            expect(await zknaf.proofValidity(ProofType.SANCTIONS)).to.equal(0);
        });
    });
});
