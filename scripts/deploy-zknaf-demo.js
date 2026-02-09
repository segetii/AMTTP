/**
 * Deploy MockZkNAF Demo Contracts
 * 
 * Usage:
 *   npx hardhat run scripts/deploy-zknaf-demo.js --network localhost
 *   npx hardhat run scripts/deploy-zknaf-demo.js --network sepolia
 */

const { ethers, network } = require("hardhat");
const fs = require('fs');
const path = require('path');

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('           MockZkNAF Demo Deployment');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`Network: ${network.name}`);
    
    const chainId = (await ethers.provider.getNetwork()).chainId;
    console.log(`Chain ID: ${chainId}`);
    
    const [deployer] = await ethers.getSigners();
    console.log(`Deployer: ${deployer.address}`);
    
    const balance = await ethers.provider.getBalance(deployer.address);
    console.log(`Balance: ${ethers.formatEther(balance)} ETH`);
    
    // Deploy MockZkNAF
    console.log('\n📦 Deploying MockZkNAF...');
    const MockZkNAF = await ethers.getContractFactory("MockZkNAF");
    const mockZkNAF = await MockZkNAF.deploy();
    await mockZkNAF.waitForDeployment();
    const mockZkNAFAddress = await mockZkNAF.getAddress();
    console.log(`✅ MockZkNAF deployed to: ${mockZkNAFAddress}`);
    
    // Deploy MockZkNAFModule
    console.log('\n📦 Deploying MockZkNAFModule...');
    const MockZkNAFModule = await ethers.getContractFactory("MockZkNAFModule");
    const mockZkNAFModule = await MockZkNAFModule.deploy(mockZkNAFAddress);
    await mockZkNAFModule.waitForDeployment();
    const mockZkNAFModuleAddress = await mockZkNAFModule.getAddress();
    console.log(`✅ MockZkNAFModule deployed to: ${mockZkNAFModuleAddress}`);
    
    // Auto-approve deployer for demo
    console.log('\n🎭 Setting up demo approvals...');
    let tx = await mockZkNAF.setDemoApproval(deployer.address, true);
    await tx.wait();
    console.log(`   ✅ Deployer approved for demo mode`);
    
    // Check if AMTTPCore exists on this network
    const deploymentsDir = path.join(__dirname, '..', 'deployments');
    const networkDeploymentPattern = new RegExp(`.*${network.name}.*\\.json$`, 'i');
    
    let amttpCoreAddress = null;
    
    if (fs.existsSync(deploymentsDir)) {
        const files = fs.readdirSync(deploymentsDir);
        for (const file of files) {
            if (networkDeploymentPattern.test(file)) {
                const deployment = JSON.parse(fs.readFileSync(path.join(deploymentsDir, file)));
                if (deployment.contracts?.amttpCore) {
                    amttpCoreAddress = deployment.contracts.amttpCore;
                    console.log(`\n📍 Found AMTTPCore at: ${amttpCoreAddress}`);
                    break;
                }
            }
        }
    }
    
    // If AMTTPCore found, attempt to link
    if (amttpCoreAddress) {
        console.log('\n🔗 Attempting to link with AMTTPCore...');
        try {
            const AMTTPCore = await ethers.getContractFactory("AMTTPCore");
            const amttpCore = AMTTPCore.attach(amttpCoreAddress);
            
            // Check if caller is owner
            const owner = await amttpCore.owner();
            if (owner.toLowerCase() === deployer.address.toLowerCase()) {
                tx = await amttpCore.setZkNAFModule(mockZkNAFModuleAddress, true);
                await tx.wait();
                console.log(`   ✅ zkNAF module linked and enabled in AMTTPCore`);
            } else {
                console.log(`   ⚠️  Not owner of AMTTPCore. Manual linking required.`);
                console.log(`      Owner: ${owner}`);
            }
        } catch (err) {
            console.log(`   ⚠️  Could not link: ${err.message}`);
        }
    } else {
        console.log('\n⚠️  No AMTTPCore deployment found. Manual linking required.');
    }
    
    // Save deployment info
    const deploymentInfo = {
        network: network.name,
        chainId: chainId.toString(),
        deployer: deployer.address,
        timestamp: new Date().toISOString(),
        contracts: {
            mockZkNAF: mockZkNAFAddress,
            mockZkNAFModule: mockZkNAFModuleAddress
        },
        linkedAmttpCore: amttpCoreAddress,
        demoMode: true
    };
    
    const outputDir = path.join(__dirname, '..', 'deployments');
    fs.mkdirSync(outputDir, { recursive: true });
    
    const outputPath = path.join(outputDir, `zknaf-demo-${network.name}-${Date.now()}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(deploymentInfo, null, 2));
    console.log(`\n📄 Deployment saved: ${outputPath}`);
    
    // Print usage instructions
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Demo Setup Complete');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`
MockZkNAF:       ${mockZkNAFAddress}
MockZkNAFModule: ${mockZkNAFModuleAddress}

To generate demo proofs (in console):
  const MockZkNAF = await ethers.getContractFactory("MockZkNAF");
  const zknaf = MockZkNAF.attach("${mockZkNAFAddress}");
  await zknaf.generateAllProofs();  // Generates all 3 proofs

To link with existing AMTTPCore:
  const AMTTPCore = await ethers.getContractFactory("AMTTPCore");
  const core = AMTTPCore.attach("<AMTTP_CORE_ADDRESS>");
  await core.setZkNAFModule("${mockZkNAFModuleAddress}", true);

To check compliance:
  const status = await zknaf.isCompliant("<USER_ADDRESS>");
  console.log(status);
`);
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
