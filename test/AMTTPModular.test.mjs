import { expect } from 'chai';
import hre from 'hardhat';
const { ethers, upgrades } = hre;

describe('AMTTP Modular Architecture', function () {
    let amttp, policyManager, policyEngine;
    let owner, user1, user2, oracle;
    
    beforeEach(async function () {
        [owner, user1, user2, oracle] = await ethers.getSigners();
        
        const PolicyManager = await ethers.getContractFactory('AMTTPPolicyManager');
        policyManager = await upgrades.deployProxy(PolicyManager, [], { initializer: 'initialize', kind: 'uups' });
        await policyManager.waitForDeployment();
        
        const AMTTPCore = await ethers.getContractFactory('AMTTPCore');
        amttp = await upgrades.deployProxy(AMTTPCore, [oracle.address], { initializer: 'initialize', kind: 'uups' });
        await amttp.waitForDeployment();
        
        const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');
        policyEngine = await upgrades.deployProxy(PolicyEngine, [await amttp.getAddress(), oracle.address], { initializer: 'initialize', kind: 'uups' });
        await policyEngine.waitForDeployment();
        
        await amttp.setPolicyEngine(await policyEngine.getAddress());
        await policyManager.setPolicyEngine(await policyEngine.getAddress());
    });
    
    describe('Contract Deployment', function () {
        it('Should deploy all contracts successfully', async function () {
            expect(await amttp.getAddress()).to.not.equal(ethers.ZeroAddress);
            expect(await policyManager.getAddress()).to.not.equal(ethers.ZeroAddress);
            expect(await policyEngine.getAddress()).to.not.equal(ethers.ZeroAddress);
        });
        
        it('Should verify policy engine connection', async function () {
            const policyEngineAddr = await amttp.policyEngine();
            expect(policyEngineAddr).to.equal(await policyEngine.getAddress());
        });
    });
    
    describe('Policy Engine Integration', function () {
        it('Should set transaction policies', async function () {
            await policyEngine.connect(user1).setTransactionPolicy(user1.address, ethers.parseEther("10"), ethers.parseEther("50"), ethers.parseEther("200"), ethers.parseEther("500"), 700, true, 3600);
            const policy = await policyEngine.getUserPolicy(user1.address);
            expect(policy.maxAmount).to.equal(ethers.parseEther("10"));
        });
        
        it('Should check transaction allowed', async function () {
            const [allowed] = await policyEngine.isTransactionAllowed(user1.address, user2.address, ethers.parseEther("1"), 300);
            expect(allowed).to.be.true;
        });
    });
    
    describe('Emergency Controls', function () {
        it('Should handle pause', async function () {
            await policyEngine.setEmergencyPause(true);
            const [allowed, reason] = await policyEngine.isTransactionAllowed(user1.address, user2.address, ethers.parseEther("1"), 300);
            expect(allowed).to.be.false;
            expect(reason).to.equal("System paused");
        });
    });
});
