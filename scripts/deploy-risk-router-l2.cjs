/**
 * AMTTPRiskRouter L2 Deployment Script
 * 
 * Deploys the AI Risk Router to Polygon or Arbitrum L2 networks
 * with network-specific optimizations and configurations
 */

const { ethers, upgrades, network } = require("hardhat");
const fs = require('fs');
const path = require('path');

// Network-specific configurations
const L2_CONFIGS = {
    polygon: {
        chainId: 137,
        name: "Polygon Mainnet",
        rpcUrl: process.env.POLYGON_RPC_URL,
        explorer: "https://polygonscan.com",
        gasPrice: "auto",
        confirmations: 5,
        modelVersion: "DQN-v2.0-polygon"
    },
    polygonAmoy: {
        chainId: 80002,
        name: "Polygon Amoy Testnet",
        rpcUrl: process.env.POLYGON_AMOY_RPC,
        explorer: "https://amoy.polygonscan.com",
        gasPrice: "auto",
        confirmations: 3,
        modelVersion: "DQN-v2.0-testnet"
    },
    arbitrum: {
        chainId: 42161,
        name: "Arbitrum One",
        rpcUrl: process.env.ARBITRUM_RPC_URL,
        explorer: "https://arbiscan.io",
        gasPrice: "auto",
        confirmations: 5,
        modelVersion: "DQN-v2.0-arbitrum"
    },
    arbitrumSepolia: {
        chainId: 421614,
        name: "Arbitrum Sepolia Testnet",
        rpcUrl: process.env.ARBITRUM_SEPOLIA_RPC,
        explorer: "https://sepolia.arbiscan.io",
        gasPrice: "auto",
        confirmations: 3,
        modelVersion: "DQN-v2.0-testnet"
    },
    localhost: {
        chainId: 31337,
        name: "Localhost",
        rpcUrl: "http://127.0.0.1:8545",
        explorer: "",
        gasPrice: "auto",
        confirmations: 1,
        modelVersion: "DQN-v2.0-local"
    }
};

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('              AMTTPRiskRouter L2 Deployment');
    console.log('═══════════════════════════════════════════════════════════════');
    
    // Get network configuration
    const networkName = network.name;
    const config = L2_CONFIGS[networkName];
    
    if (!config) {
        console.error(`❌ Unsupported network: ${networkName}`);
        console.log('Supported networks:', Object.keys(L2_CONFIGS).join(', '));
        process.exit(1);
    }
    
    console.log(`\nNetwork: ${config.name} (Chain ID: ${config.chainId})`);
    
    const [deployer] = await ethers.getSigners();
    const balance = await ethers.provider.getBalance(deployer.address);
    
    console.log(`Deployer: ${deployer.address}`);
    console.log(`Balance: ${ethers.formatEther(balance)} native tokens`);
    
    // Estimate deployment costs
    console.log('\n📊 Estimating deployment costs...');
    const AMTTPRiskRouter = await ethers.getContractFactory("AMTTPRiskRouter");
    
    // Deploy as upgradeable proxy
    console.log('\n📦 Deploying AMTTPRiskRouter...');
    
    const riskRouter = await upgrades.deployProxy(
        AMTTPRiskRouter,
        [deployer.address, config.modelVersion],
        {
            initializer: 'initialize',
            kind: 'uups'
        }
    );
    
    await riskRouter.waitForDeployment();
    const proxyAddress = await riskRouter.getAddress();
    
    console.log(`✅ Proxy deployed to: ${proxyAddress}`);
    
    // Wait for confirmations
    console.log(`\n⏳ Waiting for ${config.confirmations} confirmations...`);
    const deployTx = riskRouter.deploymentTransaction();
    if (deployTx) {
        await deployTx.wait(config.confirmations);
    }
    
    // Get implementation address
    const implAddress = await upgrades.erc1967.getImplementationAddress(proxyAddress);
    console.log(`   Implementation: ${implAddress}`);
    
    // Configure router with L2-optimized settings
    console.log('\n⚙️  Configuring L2 optimizations...');
    
    // Set thresholds (can be adjusted based on network)
    console.log('   Setting risk thresholds...');
    const txThresholds = await riskRouter.setThresholds(300, 600, 850);
    await txThresholds.wait(config.confirmations);
    console.log('   ✅ Thresholds set: LOW=30%, MEDIUM=60%, HIGH=85%');
    
    // Set anomaly threshold
    console.log('   Setting anomaly threshold...');
    const txAnomaly = await riskRouter.setAnomalyThreshold(15);
    await txAnomaly.wait(config.confirmations);
    console.log('   ✅ Anomaly threshold: 15 consecutive high-risk');
    
    // Verify contract on block explorer (if not localhost)
    if (networkName !== 'localhost' && process.env.ETHERSCAN_API_KEY) {
        console.log('\n🔍 Verifying contract on explorer...');
        try {
            await hre.run("verify:verify", {
                address: implAddress,
                constructorArguments: []
            });
            console.log('   ✅ Contract verified');
        } catch (err) {
            console.log('   ⚠️  Verification failed:', err.message);
        }
    }
    
    // Save deployment info
    const deploymentInfo = {
        network: networkName,
        chainId: config.chainId,
        networkName: config.name,
        deployer: deployer.address,
        proxyAddress: proxyAddress,
        implementationAddress: implAddress,
        modelVersion: config.modelVersion,
        deploymentTimestamp: new Date().toISOString(),
        thresholds: {
            low: 300,
            medium: 600,
            high: 850
        },
        explorer: config.explorer ? `${config.explorer}/address/${proxyAddress}` : null
    };
    
    const deploymentsDir = path.join(__dirname, '..', 'deployments', networkName);
    fs.mkdirSync(deploymentsDir, { recursive: true });
    
    const deploymentPath = path.join(deploymentsDir, 'AMTTPRiskRouter.json');
    fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
    console.log(`\n📄 Deployment info saved: ${deploymentPath}`);
    
    // Print summary
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Deployment Complete');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`
Network:          ${config.name}
Chain ID:         ${config.chainId}
Proxy Address:    ${proxyAddress}
Implementation:   ${implAddress}
Model Version:    ${config.modelVersion}

Explorer:         ${config.explorer ? `${config.explorer}/address/${proxyAddress}` : 'N/A'}

To interact with the router:
  const router = await ethers.getContractAt("AMTTPRiskRouter", "${proxyAddress}");
  
Example usage:
  // Quick risk check
  const action = await router.quickCheck(350); // Returns RiskAction.REVIEW
  
  // Full assessment with oracle signature
  const [action, txHash] = await router.assessRisk(
    sender, recipient, amount, riskScore, timestamp, signature
  );
`);
    
    // Generate environment variables
    const envVars = `
# AMTTPRiskRouter L2 Deployment - ${config.name}
RISK_ROUTER_${networkName.toUpperCase()}_PROXY=${proxyAddress}
RISK_ROUTER_${networkName.toUpperCase()}_IMPL=${implAddress}
`;
    
    const envPath = path.join(deploymentsDir, '.env.router');
    fs.writeFileSync(envPath, envVars);
    console.log(`Environment variables saved to: ${envPath}`);
}

// Deploy to specific network based on command line
main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
