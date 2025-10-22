const { expect } = require('chai');
const { ethers, upgrades } = require('hardhat');

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
        
        // Deploy AMTTP
        const AMTTP = await ethers.getContractFactory('contracts/AMTTPStreamlined.sol:AMTTP');
        amttp = await upgrades.deployProxy(
            AMTTP,
            ['Test AMTTP', 'TAMTTP', ethers.parseEther('1000000')],
            { initializer: 'initialize', kind: 'uups' }
        );
        
        // Deploy Policy Engine  
        const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');
        policyEngine = await upgrades.deployProxy(
            PolicyEngine,
            [ethers.ZeroAddress, owner.address], // _amttpContract will be set later, use owner as oracle
            { initializer: 'initialize', kind: 'uups' }
        );
        
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
            const amttpCode = await ethers.provider.getCode(await amttp.getAddress());
            const policyManagerCode = await ethers.provider.getCode(await policyManager.getAddress());
            
            console.log(`AMTTP size: ${amttpCode.length / 2 - 1} bytes`);
            console.log(`Policy Manager size: ${policyManagerCode.length / 2 - 1} bytes`);
            
            // Should be under Ethereum contract size limit
            expect(amttpCode.length / 2 - 1).to.be.lessThan(24576);
            expect(policyManagerCode.length / 2 - 1).to.be.lessThan(24576);
        });
        
        it('Should connect contracts properly', async function () {
            expect(await amttp.policyManager()).to.equal(await policyManager.getAddress());
            expect(await amttp.policyValidationEnabled()).to.be.true;
            expect(await policyManager.policyEngine()).to.equal(await policyEngine.getAddress());
            expect(await policyManager.policyEngineEnabled()).to.be.true;
        });
    });
    
    describe('Basic Transfer Functionality', function () {
        it('Should allow secure transfer initiation', async function () {
            const amount = ethers.parseEther('100');
            const dataHash = ethers.keccak256(ethers.toUtf8Bytes('test-data'));
            
            const tx = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            
            const receipt = await tx.wait();
            const event = receipt.logs.find(log => {
                try {
                    const parsed = amttp.interface.parseLog(log);
                    return parsed && parsed.name === 'TransactionInitiated';
                } catch (e) {
                    return false;
                }
            });
            
            expect(event).to.not.be.undefined;
            const parsedEvent = amttp.interface.parseLog(event);
            expect(parsedEvent.args.from).to.equal(user1.address);
            expect(parsedEvent.args.to).to.equal(user2.address);
            expect(parsedEvent.args.amount).to.equal(amount);
            
            const txId = parsedEvent.args.txId;
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.from).to.equal(user1.address);
            expect(transaction.to).to.equal(user2.address);
            expect(transaction.amount).to.equal(amount);
            expect(transaction.status).to.equal(0); // pending
        });
        
        it('Should handle low risk transactions automatically', async function () {
            const amount = ethers.parseEther('10');
            const dataHash = ethers.keccak256(ethers.toUtf8Bytes('low-risk'));
            
            // Initiate transfer
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const event1 = receipt1.logs.find(log => {
                try {
                    const parsed = amttp.interface.parseLog(log);
                    return parsed && parsed.name === 'TransactionInitiated';
                } catch (e) {
                    return false;
                }
            });
            const txId = amttp.interface.parseLog(event1).args.txId;
            
            // Submit low risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 200); // 20% risk
            const receipt2 = await tx2.wait();
            
            // Check transaction was approved
            const approvedEvent = receipt2.logs.find(log => {
                try {
                    const parsed = amttp.interface.parseLog(log);
                    return parsed && parsed.name === 'TransactionApproved';
                } catch (e) {
                    return false;
                }
            });
            expect(approvedEvent).to.not.be.undefined;
            
            const transaction = await amttp.getTransaction(txId);
            expect(transaction.status).to.equal(1); // approved
            
            // Check balances
            const user1Balance = await amttp.balanceOf(user1.address);
            const user2Balance = await amttp.balanceOf(user2.address);
            expect(user1Balance).to.equal(ethers.parseEther('990'));
            expect(user2Balance).to.equal(ethers.parseEther('1010'));
        });
    });
    
    describe('Policy Management', function () {
        it('Should allow setting user policies', async function () {
            const maxAmount = ethers.parseEther('500');
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
            const maxAmount = ethers.parseEther('50');
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                maxAmount,
                500 // 50% risk threshold
            );
            
            // Try to transfer above limit
            const amount = ethers.parseEther('100');
            const dataHash = ethers.keccak256(ethers.toUtf8Bytes('test'));
            
            const tx1 = await amttp.connect(user1).secureTransfer(
                user2.address,
                amount,
                dataHash
            );
            const receipt1 = await tx1.wait();
            const event1 = receipt1.logs.find(log => {
                try {
                    const parsed = amttp.interface.parseLog(log);
                    return parsed && parsed.name === 'TransactionInitiated';
                } catch (e) {
                    return false;
                }
            });
            const txId = amttp.interface.parseLog(event1).args.txId;
            
            // Submit risk score
            const tx2 = await amttp.connect(oracle).submitRiskScore(txId, 300);
            const receipt2 = await tx2.wait();
            
            // Should be rejected due to amount limit
            const rejectEvent = receipt2.logs.find(log => {
                try {
                    const parsed = amttp.interface.parseLog(log);
                    return parsed && parsed.name === 'TransactionRejected';
                } catch (e) {
                    return false;
                }
            });
            expect(rejectEvent).to.not.be.undefined;
            const parsedReject = amttp.interface.parseLog(rejectEvent);
            expect(parsedReject.args.reason).to.include('Exceeds user limit');
        });
    });
    
    describe('Integration Tests', function () {
        it('Should validate transfer capability check', async function () {
            // Set restrictive policy
            await policyManager.connect(user1).setUserPolicy(
                user1.address,
                ethers.parseEther('10'), // Low limit
                300 // Low risk threshold
            );
            
            // Check if large transfer is allowed
            const canTransferLarge = await amttp.canTransfer(
                user1.address,
                user2.address,
                ethers.parseEther('100')
            );
            expect(canTransferLarge).to.be.false;
            
            // Check if small transfer is allowed
            const canTransferSmall = await amttp.canTransfer(
                user1.address,
                user2.address,
                ethers.parseEther('5')
            );
            expect(canTransferSmall).to.be.true;
        });
    });
});