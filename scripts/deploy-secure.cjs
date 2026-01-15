/**
 * Deploy AMTTPCoreSecure - Security-Enhanced AMTTP Contract
 * 
 * Features:
 * - Multi-oracle consensus (2-of-3 threshold)
 * - Nonce-based replay protection
 * - Timelock for admin operations (2 day delay)
 * - Storage gaps for safe upgrades
 * - HSM-compatible signature verification
 */

const { ethers, upgrades } = require('hardhat');
const fs = require('fs');
const path = require('path');

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('       Deploying AMTTPCoreSecure (Security Enhanced)');
    console.log('═══════════════════════════════════════════════════════════════\n');

    const [deployer, oracle1, oracle2, oracle3] = await ethers.getSigners();
    
    console.log('Deployer:', deployer.address);
    console.log('Balance:', ethers.formatEther(await ethers.provider.getBalance(deployer.address)), 'ETH\n');

    // Use deployer as first oracle in testnet, real HSM-backed addresses in production
    const initialOracle = oracle1?.address || deployer.address;
    console.log('Initial Oracle:', initialOracle);

    // Deploy AMTTPCoreSecure
    console.log('\n📦 Deploying AMTTPCoreSecure...');
    const AMTTPCoreSecure = await ethers.getContractFactory('AMTTPCoreSecure');
    const core = await upgrades.deployProxy(AMTTPCoreSecure, [initialOracle], {
        kind: 'uups',
        initializer: 'initialize',
    });
    await core.waitForDeployment();
    const coreAddress = await core.getAddress();
    console.log('✅ AMTTPCoreSecure deployed to:', coreAddress);

    // Add additional oracles if available (for 2-of-3 setup)
    if (oracle2) {
        console.log('\n🔑 Adding Oracle 2:', oracle2.address);
        await core.addOracle(oracle2.address);
    }
    if (oracle3) {
        console.log('🔑 Adding Oracle 3:', oracle3.address);
        await core.addOracle(oracle3.address);
    }

    // Get oracle setup
    const [oracles, oracleCount, oracleThreshold] = await core.getOracles();
    console.log('\n📊 Oracle Configuration:');
    console.log('  Count:', oracleCount.toString());
    console.log('  Threshold:', oracleThreshold.toString());
    for (let i = 0; i < oracleCount; i++) {
        console.log(`  Oracle ${i + 1}:`, oracles[i]);
    }

    // Set to 2-of-3 if we have 3 oracles
    if (oracleCount >= 3n) {
        console.log('\n🔒 Setting oracle threshold to 2-of-3...');
        await core.setOracleThreshold(2);
        console.log('✅ Threshold set to 2-of-3 consensus');
    }

    // Display security features
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Security Features Enabled');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('✅ 1. Nonce-based replay protection');
    console.log('✅ 2. Signature expiry (5 minutes)');
    console.log('✅ 3. Multi-oracle consensus (threshold signatures)');
    console.log('✅ 4. Timelock for admin operations (2 days)');
    console.log('✅ 5. Storage gaps for safe upgrades');
    console.log('✅ 6. HSM-compatible EIP-191 signatures');

    // Display constants
    const signatureValidity = await core.SIGNATURE_VALIDITY();
    const timelockDelay = await core.TIMELOCK_DELAY();
    const maxOracles = await core.MAX_ORACLES();
    
    console.log('\n📋 Security Constants:');
    console.log(`  SIGNATURE_VALIDITY: ${signatureValidity / 60n} minutes`);
    console.log(`  TIMELOCK_DELAY: ${timelockDelay / 86400n} days`);
    console.log(`  MAX_ORACLES: ${maxOracles}`);

    // Save deployment info
    const deployment = {
        network: (await ethers.provider.getNetwork()).name,
        chainId: (await ethers.provider.getNetwork()).chainId.toString(),
        timestamp: new Date().toISOString(),
        contracts: {
            AMTTPCoreSecure: {
                address: coreAddress,
                implementation: await upgrades.erc1967.getImplementationAddress(coreAddress),
            },
        },
        oracles: oracles.slice(0, Number(oracleCount)),
        oracleThreshold: oracleThreshold.toString(),
        securityFeatures: {
            nonceProtection: true,
            signatureExpiry: signatureValidity.toString(),
            timelockDelay: timelockDelay.toString(),
            multiOracleConsensus: true,
            storageGaps: true,
        },
    };

    const deploymentPath = path.join(__dirname, '..', 'deployments', 
        `secure-${deployment.network}-${Date.now()}.json`);
    fs.mkdirSync(path.dirname(deploymentPath), { recursive: true });
    fs.writeFileSync(deploymentPath, JSON.stringify(deployment, null, 2));
    console.log('\n📁 Deployment saved to:', deploymentPath);

    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Deployment Complete!');
    console.log('═══════════════════════════════════════════════════════════════');

    return deployment;
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error('Deployment failed:', error);
        process.exit(1);
    });
