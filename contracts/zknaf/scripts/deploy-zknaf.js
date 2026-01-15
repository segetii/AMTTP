/**
 * AMTTPzkNAF Deployment Script
 * 
 * Deploys the zkNAF Groth16 verifier contract to the specified network
 * and sets up verification keys from generated files
 */

const { ethers, upgrades, network } = require("hardhat");
const fs = require('fs');
const path = require('path');

// ProofType enum values matching the contract
const ProofType = {
    SANCTIONS: 0,
    RISK_LOW: 1,
    RISK_MEDIUM: 2,
    KYC_VERIFIED: 3
};

async function loadVerificationKeys() {
    const keysPath = path.join(__dirname, '..', 'generated', 'verification_keys.json');
    
    if (!fs.existsSync(keysPath)) {
        console.log('⚠️  Verification keys not found. Run npm run build first.');
        return null;
    }
    
    return JSON.parse(fs.readFileSync(keysPath, 'utf8'));
}

function formatG1Point(point) {
    return [
        BigInt(point[0]).toString(),
        BigInt(point[1]).toString()
    ];
}

function formatG2Point(point) {
    return [
        [BigInt(point[0][0]).toString(), BigInt(point[0][1]).toString()],
        [BigInt(point[1][0]).toString(), BigInt(point[1][1]).toString()]
    ];
}

function formatICPoints(ic) {
    return ic.map(point => [
        BigInt(point[0]).toString(),
        BigInt(point[1]).toString()
    ]);
}

async function main() {
    console.log('═══════════════════════════════════════════════════════════════');
    console.log('                AMTTPzkNAF Deployment');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`Network: ${network.name}`);
    console.log(`Chain ID: ${(await ethers.provider.getNetwork()).chainId}`);
    
    const [deployer] = await ethers.getSigners();
    console.log(`Deployer: ${deployer.address}`);
    console.log(`Balance: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);
    
    // Deploy the contract
    console.log('\n📦 Deploying AMTTPzkNAF...');
    
    const AMTTPzkNAF = await ethers.getContractFactory("AMTTPzkNAF");
    const zknaf = await upgrades.deployProxy(AMTTPzkNAF, [], {
        initializer: 'initialize',
        kind: 'uups'
    });
    
    await zknaf.waitForDeployment();
    const contractAddress = await zknaf.getAddress();
    
    console.log(`✅ AMTTPzkNAF deployed to: ${contractAddress}`);
    
    // Get implementation address for verification
    const implAddress = await upgrades.erc1967.getImplementationAddress(contractAddress);
    console.log(`   Implementation: ${implAddress}`);
    
    // Load and set verification keys
    console.log('\n🔑 Setting up verification keys...');
    const verificationKeys = await loadVerificationKeys();
    
    if (verificationKeys) {
        const circuitToProofType = {
            'sanctions_non_membership': ProofType.SANCTIONS,
            'risk_range_proof': ProofType.RISK_LOW, // Default to LOW, MEDIUM uses same circuit
            'kyc_credential': ProofType.KYC_VERIFIED
        };
        
        for (const [circuit, proofType] of Object.entries(circuitToProofType)) {
            if (verificationKeys[circuit]) {
                const vkey = verificationKeys[circuit];
                
                console.log(`   Setting key for ${circuit}...`);
                
                try {
                    const tx = await zknaf.setVerificationKey(
                        proofType,
                        formatG1Point(vkey.alpha1),
                        formatG2Point(vkey.beta2),
                        formatG2Point(vkey.gamma2),
                        formatG2Point(vkey.delta2),
                        formatICPoints(vkey.ic)
                    );
                    
                    await tx.wait();
                    console.log(`   ✅ ${circuit} key set (tx: ${tx.hash})`);
                } catch (err) {
                    console.error(`   ❌ Error setting ${circuit} key:`, err.message);
                }
            }
        }
    } else {
        console.log('   ⚠️  No verification keys to set. Run circuit build first.');
    }
    
    // Set default proof validity periods
    console.log('\n⏱️  Setting proof validity periods...');
    
    const validityPeriods = {
        [ProofType.SANCTIONS]: 7 * 24 * 60 * 60,      // 7 days
        [ProofType.RISK_LOW]: 30 * 24 * 60 * 60,     // 30 days
        [ProofType.RISK_MEDIUM]: 14 * 24 * 60 * 60,  // 14 days
        [ProofType.KYC_VERIFIED]: 365 * 24 * 60 * 60 // 1 year
    };
    
    for (const [proofType, validity] of Object.entries(validityPeriods)) {
        try {
            const tx = await zknaf.setProofValidity(proofType, validity);
            await tx.wait();
            console.log(`   ✅ ProofType ${proofType}: ${validity / (24 * 60 * 60)} days`);
        } catch (err) {
            console.error(`   ❌ Error setting validity for ${proofType}:`, err.message);
        }
    }
    
    // Save deployment info
    const deploymentInfo = {
        network: network.name,
        chainId: (await ethers.provider.getNetwork()).chainId.toString(),
        deployer: deployer.address,
        contractAddress: contractAddress,
        implementationAddress: implAddress,
        deploymentTimestamp: new Date().toISOString(),
        proofTypes: {
            SANCTIONS: 0,
            RISK_LOW: 1,
            RISK_MEDIUM: 2,
            KYC_VERIFIED: 3
        },
        validityPeriods: validityPeriods
    };
    
    const deploymentDir = path.join(__dirname, '..', '..', '..', 'deployments', network.name);
    fs.mkdirSync(deploymentDir, { recursive: true });
    
    const deploymentPath = path.join(deploymentDir, 'AMTTPzkNAF.json');
    fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
    console.log(`\n📄 Deployment info saved: ${deploymentPath}`);
    
    // Print summary
    console.log('\n═══════════════════════════════════════════════════════════════');
    console.log('                    Deployment Complete');
    console.log('═══════════════════════════════════════════════════════════════');
    console.log(`
Contract Address: ${contractAddress}
Implementation:   ${implAddress}
Network:          ${network.name}

To verify on Etherscan:
npx hardhat verify --network ${network.name} ${implAddress}

To interact with the contract:
const AMTTPzkNAF = await ethers.getContractFactory("AMTTPzkNAF");
const zknaf = AMTTPzkNAF.attach("${contractAddress}");
`);
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
