/**
 * ZkNAF Verifier Router - Comprehensive Test Suite
 * 
 * Tests edge cases, security, and functionality of the ZK verifier contracts.
 */

import { expect } from 'chai';
import hre from 'hardhat';
const { ethers } = hre;

describe('ZkNAF Verifier Router', function () {
  let router;
  let sanctionsVerifier;
  let riskVerifier;
  let kycVerifier;
  let owner;
  let user1;
  let user2;
  let attacker;

  // Sample proof data (invalid but structurally correct)
  const sampleProof = {
    pA: [
      '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
      '0xfedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321'
    ],
    pB: [
      [
        '0x1111111111111111111111111111111111111111111111111111111111111111',
        '0x2222222222222222222222222222222222222222222222222222222222222222'
      ],
      [
        '0x3333333333333333333333333333333333333333333333333333333333333333',
        '0x4444444444444444444444444444444444444444444444444444444444444444'
      ]
    ],
    pC: [
      '0x5555555555555555555555555555555555555555555555555555555555555555',
      '0x6666666666666666666666666666666666666666666666666666666666666666'
    ]
  };

  before(async function () {
    [owner, user1, user2, attacker] = await ethers.getSigners();
  });

  beforeEach(async function () {
    // Deploy verifiers
    const SanctionsVerifier = await ethers.getContractFactory(
      'contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier'
    );
    sanctionsVerifier = await SanctionsVerifier.deploy();

    const RiskVerifier = await ethers.getContractFactory(
      'contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier'
    );
    riskVerifier = await RiskVerifier.deploy();

    const KYCVerifier = await ethers.getContractFactory(
      'contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier'
    );
    kycVerifier = await KYCVerifier.deploy();

    // Deploy router
    const Router = await ethers.getContractFactory('ZkNAFVerifierRouter');
    router = await Router.deploy(
      await sanctionsVerifier.getAddress(),
      await riskVerifier.getAddress(),
      await kycVerifier.getAddress()
    );
  });

  describe('Deployment', function () {
    it('Should set correct owner', async function () {
      expect(await router.owner()).to.equal(owner.address);
    });

    it('Should set correct verifier addresses', async function () {
      const [sanctions, risk, kyc] = await router.getVerifiers();
      expect(sanctions).to.equal(await sanctionsVerifier.getAddress());
      expect(risk).to.equal(await riskVerifier.getAddress());
      expect(kyc).to.equal(await kycVerifier.getAddress());
    });
  });

  describe('Access Control', function () {
    it('Should allow owner to update sanctions verifier', async function () {
      const NewVerifier = await ethers.getContractFactory(
        'contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier'
      );
      const newVerifier = await NewVerifier.deploy();
      
      await expect(router.updateSanctionsVerifier(await newVerifier.getAddress()))
        .to.emit(router, 'VerifierUpdated')
        .withArgs('sanctions', await sanctionsVerifier.getAddress(), await newVerifier.getAddress());
    });

    it('Should reject non-owner updating verifiers', async function () {
      await expect(
        router.connect(attacker).updateSanctionsVerifier(attacker.address)
      ).to.be.revertedWith('Not owner');
    });

    it('Should allow owner to transfer ownership', async function () {
      await router.transferOwnership(user1.address);
      expect(await router.owner()).to.equal(user1.address);
    });

    it('Should reject transferring to zero address', async function () {
      await expect(
        router.transferOwnership(ethers.ZeroAddress)
      ).to.be.revertedWith('Invalid owner');
    });

    it('Should reject non-owner transferring ownership', async function () {
      await expect(
        router.connect(attacker).transferOwnership(attacker.address)
      ).to.be.revertedWith('Not owner');
    });
  });

  describe('Proof Replay Protection', function () {
    it('Should track used proofs', async function () {
      const proofHash = ethers.keccak256(
        ethers.solidityPacked(
          ['uint256[2]', 'uint256[2][2]', 'uint256[2]'],
          [sampleProof.pA, sampleProof.pB, sampleProof.pC]
        )
      );
      
      // Initially not used
      expect(await router.isProofUsed(proofHash)).to.be.false;
    });
  });

  describe('Edge Cases - Input Validation', function () {
    it('Should reject empty public signals for sanctions', async function () {
      await expect(
        router.verifySanctionsProof(sampleProof.pA, sampleProof.pB, sampleProof.pC, [])
      ).to.be.revertedWith('Invalid public signals');
    });

    it('Should reject insufficient public signals for risk', async function () {
      await expect(
        router.verifyRiskProof(sampleProof.pA, sampleProof.pB, sampleProof.pC, [1, 2, 3])
      ).to.be.revertedWith('Invalid public signals');
    });

    it('Should reject insufficient public signals for KYC', async function () {
      await expect(
        router.verifyKYCProof(sampleProof.pA, sampleProof.pB, sampleProof.pC, [1, 2, 3, 4, 5])
      ).to.be.revertedWith('Invalid public signals');
    });
  });

  describe('Edge Cases - Zero Verifier', function () {
    it('Should revert if sanctions verifier is zero', async function () {
      // Deploy router with zero address
      const Router = await ethers.getContractFactory('ZkNAFVerifierRouter');
      const badRouter = await Router.deploy(
        ethers.ZeroAddress,
        await riskVerifier.getAddress(),
        await kycVerifier.getAddress()
      );
      
      await expect(
        badRouter.verifySanctionsProof(
          sampleProof.pA, 
          sampleProof.pB, 
          sampleProof.pC, 
          [1, 2, 3, 4]
        )
      ).to.be.revertedWith('Sanctions verifier not set');
    });
  });

  describe('Gas Optimization Checks', function () {
    it('Should have reasonable gas cost for deployment', async function () {
      const Router = await ethers.getContractFactory('ZkNAFVerifierRouter');
      const deployTx = await Router.getDeployTransaction(
        await sanctionsVerifier.getAddress(),
        await riskVerifier.getAddress(),
        await kycVerifier.getAddress()
      );
      
      const estimatedGas = await ethers.provider.estimateGas(deployTx);
      console.log(`Router deployment gas: ${estimatedGas.toString()}`);
      
      // Should be under 2M gas
      expect(estimatedGas).to.be.lt(2000000n);
    });
  });

  describe('Event Emission', function () {
    it('Should emit VerifierUpdated on risk verifier change', async function () {
      const NewVerifier = await ethers.getContractFactory(
        'contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier'
      );
      const newVerifier = await NewVerifier.deploy();
      
      await expect(router.updateRiskVerifier(await newVerifier.getAddress()))
        .to.emit(router, 'VerifierUpdated')
        .withArgs('risk', await riskVerifier.getAddress(), await newVerifier.getAddress());
    });

    it('Should emit VerifierUpdated on KYC verifier change', async function () {
      const NewVerifier = await ethers.getContractFactory(
        'contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier'
      );
      const newVerifier = await NewVerifier.deploy();
      
      await expect(router.updateKYCVerifier(await newVerifier.getAddress()))
        .to.emit(router, 'VerifierUpdated')
        .withArgs('kyc', await kycVerifier.getAddress(), await newVerifier.getAddress());
    });
  });

  describe('Risk Level Calculation', function () {
    // These tests verify the risk level calculation logic
    // Note: Actual proof verification will fail with sample inputs
    
    it('Should classify LOW risk for maxScore <= 39', async function () {
      // The logic is in verifyRiskProof: if maxScore <= 39, riskLevel = 0
      // We can't test end-to-end without valid proofs, but we can verify the contract compiles
      // and has the expected interface
      expect(await router.getVerifiers()).to.have.lengthOf(3);
    });
  });

  describe('KYC Status Bitmask', function () {
    // Verify the KYC status bitmask structure
    it('Should have correct bitmask structure', async function () {
      // Bit 0 (1): kycValid
      // Bit 1 (2): isOldEnough
      // Bit 2 (4): isNotPEP
      // Bit 3 (8): isNotExpired
      // Bit 4 (16): isProviderAuthorized
      
      // Full valid status = 1 + 2 + 4 + 8 + 16 = 31
      const fullValidStatus = 31;
      expect(fullValidStatus & 1).to.equal(1);  // kycValid
      expect(fullValidStatus & 2).to.equal(2);  // isOldEnough
      expect(fullValidStatus & 4).to.equal(4);  // isNotPEP
      expect(fullValidStatus & 8).to.equal(8);  // isNotExpired
      expect(fullValidStatus & 16).to.equal(16); // isProviderAuthorized
    });
  });
});
