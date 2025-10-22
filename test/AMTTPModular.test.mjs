import { expect } from 'chai';
import hre from 'hardhat'        it('Should have correct contract sizes', async function () {
            const amttpCode = await ethers.provider.getCode(await amttp.getAddress());
            const policyManagerCode = await ethers.provider.getCode(await policyManager.getAddress());
            
            console.log(`AMTTP size: ${amttpCode.length / 2 - 1} bytes`);
            console.log(`Policy Manager size: ${policyManagerCode.length / 2 - 1} bytes`);
            
            // Should be under Ethereum contract size limit
            expect(amttpCode.length / 2 - 1).to.be.lessThan(24576);
            expect(policyManagerCode.length / 2 - 1).to.be.lessThan(24576);
        });ethers, upgrades } = hre;

describe('AMTTP Modular Architecture', function () {
    let amttp, policyManager, policyEngine;
    let owner, user1, user2, oracle;
    
    beforeEach(async function () {
        [owner, user1, user2, oracle] = await ethers.getSigners();
        
        // Deploy Policy Manager
        const PolicyManager = await ethers.getContractFactory('AMTTPPolicyManager');
        policyManager = await upgrades.deployProxy(
            PolicyManager,
            [],
            { initializer: 'initialize', kind: 'uups' }
        );
        await policyManager.waitForDeployment();
        
        // Deploy AMTTP
        const AMTTP = await ethers.getContractFactory('AMTTP');
        amttp = await upgrades.deployProxy(
            AMTTP,
            ['Test AMTTP', 'TAMTTP', ethers.parseEther('1000000')],
            { initializer: 'initialize', kind: 'uups' }
        );
        await amttp.waitForDeployment();
        
        // Deploy Policy Engine
        const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');
        policyEngine = await upgrades.deployProxy(
            PolicyEngine,
            [],
            { initializer: 'initialize', kind: 'uups' }
        );
        await policyEngine.waitForDeployment();
        
        // Connect contracts
        await amttp.setPolicyManager(await policyManager.getAddress());
        await policyManager.setPolicyEngine(await policyEngine.getAddress());
        
        // Set up oracle
        await amttp.setOracle(oracle.address, true);
        
        // Transfer tokens to users
        await amttp.transfer(user1.address, ethers.parseEther('1000'));
        await amttp.transfer(user2.address, ethers.parseEther('1000'));
    });
    
    describe('Contract Deployment', function () {
        it('Should deploy all contracts successfully', async function () {
            expect(await amttp.getAddress()).to.not.equal(ethers.ZeroAddress);
            expect(await policyManager.getAddress()).to.not.equal(ethers.ZeroAddress);
            expect(await policyEngine.getAddress()).to.not.equal(ethers.ZeroAddress);
        });
        
        it('Should have correct contract sizes', async function () {
            const amttpCode = await ethers.provider.getCode(amttp.address);
            const policyManagerCode = await ethers.provider.getCode(policyManager.address);
            
            console.log(`AMTTP size: ${amttpCode.length / 2 - 1} bytes`);
            console.log(`Policy Manager size: ${policyManagerCode.length / 2 - 1} bytes`);
            
            // Should be under Ethereum contract size limit
            expect(amttpCode.length / 2 - 1).to.be.lessThan(24576);
            expect(policyManagerCode.length / 2 - 1).to.be.lessThan(24576);
        });
        
        it('Should connect contracts properly', async function () {
            expect(await amttp.policyManager()).to.equal(policyManager.address);
            expect(await amttp.policyValidationEnabled()).to.be.true;
            expect(await policyManager.policyEngine()).to.equal(policyEngine.address);
            expect(await policyManager.policyEngineEnabled()).to.be.true;
        });
    });
    
    describe('Basic Transfer Functionality', function () {
        it('Should allow secure transfer initiation', async function () {
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('test-data'));
            
            const tx = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            
            const receipt = await tx.wait();
            const event = receipt.events.find(e => e.event === 'TransactionInitiated');
            
            expect(event).to.not.be.undefined;
            expect(event.args.from).to.equal(user1.address);
            expect(event.args.to).to.equal(user2.address);
            expect(event.args.amount).to.equal(amount);
            
            const txId = event.args.txId;
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.from).to.equal(user1.address);
            expect(transaction.to).to.equal(user2.address);
            expect(transaction.amount).to.equal(amount);
            expect(transaction.status).to.equal(0); // pending
        });
        
        it('Should handle low risk transactions automatically', async function () {
            const amount = ethers.utils.parseEther('10');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('low-risk'));
            
            // Initiate transfer
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // Submit low risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 200); // 20% risk
            const receipt2 = await tx2.wait();
            
            // Check transaction was approved
            const approvedEvent = receipt2.events.find(e => e.event === 'TransactionApproved');
            expect(approvedEvent).to.not.be.undefined;
            expect(approvedEvent.args.txId).to.equal(txId);
            
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.status).to.equal(1); // approved
            
            // Check balances
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.utils.parseEther('990'));
            expect(user2Balance).to.equal(ethers.utils.parseEther('1010'));
        });
        
        it('Should escrow high risk transactions', async function () {
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('high-risk'));
            
            // Initiate transfer
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // Submit high risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 750); // 75% risk
            const receipt2 = await tx2.wait();
            
            // Check transaction was escrowed
            const escrowEvent = receipt2.events.find(e => e.event === 'TransactionEscrowed');
            expect(escrowEvent).to.not.be.undefined;
            
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.status).to.equal(3); // escrowed
            
            // Check funds are escrowed
            const contractBalance = await amttp.balanceOf(amttp.address);
            expect(contractBalance).to.equal(amount);
        });
        
        it('Should reject very high risk transactions', async function () {
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('very-high-risk'));
            
            // Initiate transfer
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // Submit very high risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 850); // 85% risk
            const receipt2 = await tx2.wait();
            
            // Check transaction was rejected
            const rejectEvent = receipt2.events.find(e => e.event === 'TransactionRejected');
            expect(rejectEvent).to.not.be.undefined;
            
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.status).to.equal(2); // rejected
            
            // Check balances unchanged
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.utils.parseEther('1000'));
            expect(user2Balance).to.equal(ethers.utils.parseEther('1000'));
        });
    });
    
    describe('Policy Management', function () {
        it('Should allow setting user policies', async function () {
            const maxAmount = ethers.utils.parseEther('500');
            const riskThreshold = 600; // 60%
            
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                maxAmount,
                riskThreshold
            );
            
            const policy = await policyManager.getUserPolicy(user1.address);
            expect(policy.maxAmount).to.equal(maxAmount);
            expect(policy.riskThreshold).to.equal(riskThreshold);
            expect(policy.trusted).to.be.false;
        });
        
        it('Should enforce user amount limits', async function () {
            // Set user limit
            const maxAmount = ethers.utils.parseEther('50');
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                maxAmount,
                500 // 50% risk threshold
            );
            
            // Try to transfer above limit
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('test'));
            
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // Submit risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 300);
            const receipt2 = await tx2.wait();
            
            // Should be rejected due to amount limit
            const rejectEvent = receipt2.events.find(e => e.event === 'TransactionRejected');
            expect(rejectEvent).to.not.be.undefined;
            expect(rejectEvent.args.reason).to.include('Exceeds user limit');
        });
        
        it('Should allow trusted users higher risk tolerance', async function () {
            // Set user as trusted with custom threshold
            await policyManager.setTrustedUser(user1.address, true);
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                ethers.utils.parseEther('1000'),
                750 // 75% threshold
            );
            
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('trusted-test'));
            
            // Initiate transfer
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // Submit moderately high risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 720); // 72% risk
            const receipt2 = await tx2.wait();
            
            // Should be approved for trusted user
            const approvedEvent = receipt2.events.find(e => e.event === 'TransactionApproved');
            expect(approvedEvent).to.not.be.undefined;
        });
    });
    
    describe('Escrow Management', function () {
        it('Should allow oracle to release escrowed funds', async function () {
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('escrow-test'));
            
            // Create escrowed transaction
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            await amttp.connect(oracle).submitRiskScore(txId, 750);
            
            // Release escrow (approve)
            const tx3 = await amttp.connect(oracle).releaseEscrow(txId, true);
            const receipt3 = await tx3.wait();
            
            const approvedEvent = receipt3.events.find(e => e.event === 'TransactionApproved');
            expect(approvedEvent).to.not.be.undefined;
            
            // Check final balances
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.utils.parseEther('900'));
            expect(user2Balance).to.equal(ethers.utils.parseEther('1100'));
        });
        
        it('Should allow oracle to reject escrowed funds', async function () {
            const amount = ethers.utils.parseEther('100');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('reject-test'));
            
            // Create escrowed transaction
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            await amttp.connect(oracle).submitRiskScore(txId, 750);
            
            // Release escrow (reject)
            const tx3 = await amttp.connect(oracle).releaseEscrow(txId, false);
            const receipt3 = await tx3.wait();
            
            const rejectEvent = receipt3.events.find(e => e.event === 'TransactionRejected');
            expect(rejectEvent).to.not.be.undefined;
            
            // Check balances - should be back to original
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.utils.parseEther('1000'));
            expect(user2Balance).to.equal(ethers.utils.parseEther('1000'));
        });
    });
    
    describe('User Profiles', function () {
        it('Should update user profiles after transactions', async function () {
            const amount = ethers.utils.parseEther('50');
            const dataHash = ethers.utils.keccak256(ethers.utils.toUtf8Bytes('profile-test'));
            
            // Execute a transaction
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            await amttp.connect(oracle).submitRiskScore(txId, 200);
            
            // Check user profiles
            const user1Profile = await amttp.getUserProfile(user1.address);
            const user2Profile = await amttp.getUserProfile(user2.address);
            
            expect(user1Profile.totalTransactions).to.equal(1);
            expect(user1Profile.totalVolume).to.equal(amount);
            expect(user1Profile.reputationScore).to.equal(50); // New user score
            expect(user1Profile.isActive).to.be.true;
            
            expect(user2Profile.totalTransactions).to.equal(1);
            expect(user2Profile.totalVolume).to.equal(amount);
            expect(user2Profile.reputationScore).to.equal(50);
            expect(user2Profile.isActive).to.be.true;
        });
    });
    
    describe('Integration Tests', function () {
        it('Should handle complete transaction lifecycle', async function () {
            // 1. Set up user policy
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                ethers.utils.parseEther('1000'),
                600
            );
            
            // 2. Initiate transaction
            const amount = ethers.utils.parseEther('75');
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                ethers.utils.keccak256(ethers.utils.toUtf8Bytes('lifecycle-test'))
            );
            const receipt1 = await tx1.wait();
            const txId = receipt1.events.find(e => e.event === 'TransactionInitiated').args.txId;
            
            // 3. Submit risk score
            await amttp.connect(oracle).submitRiskScore(txId, 550); // 55% risk
            
            // 4. Verify completion
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.status).to.equal(1); // approved
            
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.utils.parseEther('925'));
            expect(user2Balance).to.equal(ethers.utils.parseEther('1075'));
        });
        
        it('Should validate transfer capability check', async function () {
            // Set restrictive policy
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                ethers.utils.parseEther('10'), // Low limit
                300 // Low risk threshold
            );
            
            // Check if large transfer is allowed
            const canTransferLarge = await amttp.canTransfer(
                user1.address,
                user2.address,
                ethers.utils.parseEther('100')
            );
            expect(canTransferLarge).to.be.false;
            
            // Check if small transfer is allowed
            const canTransferSmall = await amttp.canTransfer(
                user1.address,
                user2.address,
                ethers.utils.parseEther('5')
            );
            expect(canTransferSmall).to.be.true;
        });
    });
});