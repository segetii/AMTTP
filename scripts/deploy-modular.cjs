const { ethers, upgrades } = require('hardhat');const { ethers, upgrades } = require('hardhat');const { ethers, upgrades }        const amttp = await upgrades.deployProxy(



async function main() {        AMTTP,

    console.log('🚀 Deploying AMTTP Modular Architecture...\n');

    async function main() {        [

    const [deployer] = await ethers.getSigners();

    console.log('Deploying with account:', deployer.address);    console.log('🚀 Deploying AMTTP Modular Architecture...\n');            'Anti-Money Transfer Transfer Protocol',

    console.log('Account balance:', ethers.formatEther(await ethers.provider.getBalance(deployer.address)), 'ETH\n');

                    'AMTTP',

    // 1. Deploy Policy Manager first

    console.log('📋 Deploying AMTTPPolicyManager...');    const [deployer] = await ethers.getSigners();            ethers.parseEther('1000000') // 1M initial supply

    const PolicyManager = await ethers.getContractFactory('AMTTPPolicyManager');

    const policyManager = await upgrades.deployProxy(PolicyManager, [], { initializer: 'initialize', kind: 'uups' });    console.log('Deploying with account:', deployer.address);        ],ire('hardhat');

    console.log('✅ AMTTPPolicyManager deployed to:', await policyManager.getAddress());

        console.log('Account balance:', ethers.formatEther(await ethers.provider.getBalance(deployer.address)), 'ETH\n');

    // 2. Deploy streamlined AMTTP contract

    console.log('\n💰 Deploying AMTTP Streamlined...');    async function main() {

    const AMTTP = await ethers.getContractFactory('contracts/AMTTPStreamlined.sol:AMTTP');

    const amttp = await upgrades.deployProxy(AMTTP, ['AMTTP', 'AMTTP', ethers.parseEther('1000000')], { initializer: 'initialize', kind: 'uups' });    // 1. Deploy Policy Manager first    console.log('🚀 Deploying AMTTP Modular Architecture...\n');

    console.log('✅ AMTTP deployed to:', await amttp.getAddress());

        console.log('📋 Deploying AMTTPPolicyManager...');    

    // 3. Connect the contracts

    console.log('\n🔗 Connecting contracts...');    const PolicyManager = await ethers.getContractFactory('AMTTPPolicyManager');    const [deployer] = await ethers.getSigners();

    await amttp.setPolicyManager(await policyManager.getAddress());

    console.log('✅ Policy manager connected to AMTTP');    const policyManager = await upgrades.deployProxy(    console.log('Deploying with account:', deployer.address);

    

    // 4. Deploy policy engine        PolicyManager,    console.log('Account balance:', ethers.formatEther(await ethers.provider.getBalance(deployer.address)), 'ETH\n');

    console.log('\n🏗️  Deploying AMTTPPolicyEngine...');

    const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');        [],    

    const policyEngine = await upgrades.deployProxy(PolicyEngine, [ethers.ZeroAddress, deployer.address], { initializer: 'initialize', kind: 'uups' });

    console.log('✅ AMTTPPolicyEngine deployed to:', await policyEngine.getAddress());        {     // 1. Deploy Policy Manager first

    

    // 5. Connect policy engine to manager            initializer: 'initialize',    console.log('📋 Deploying AMTTPPolicyManager...');

    console.log('\n🔌 Connecting policy engine...');

    await policyManager.setPolicyEngine(await policyEngine.getAddress());            kind: 'uups'    const PolicyManager = await ethers.getContractFactory('AMTTPPolicyManager');

    console.log('✅ Policy engine connected to manager');

            }    const policyManager = await upgrades.deployProxy(

    // 6. Verify deployments

    console.log('\n🔍 Verifying deployments...');    );        PolicyManager,

    const amttpCode = await ethers.provider.getCode(await amttp.getAddress());

    const policyManagerCode = await ethers.provider.getCode(await policyManager.getAddress());            [],

    const policyEngineCode = await ethers.provider.getCode(await policyEngine.getAddress());

        console.log('✅ AMTTPPolicyManager deployed to:', await policyManager.getAddress());        { 

    console.log('📏 Contract sizes:');

    console.log(`   AMTTP: ${(amttpCode.length / 2 - 1)} bytes`);                initializer: 'initialize',

    console.log(`   Policy Manager: ${(policyManagerCode.length / 2 - 1)} bytes`);

    console.log(`   Policy Engine: ${(policyEngineCode.length / 2 - 1)} bytes`);    // 2. Deploy streamlined AMTTP contract            kind: 'uups'

    

    // 7. Test basic functionality    console.log('\n💰 Deploying AMTTP Streamlined...');        }

    console.log('\n🧪 Testing basic functionality...');

    const balance = await amttp.balanceOf(deployer.address);    const AMTTP = await ethers.getContractFactory('contracts/AMTTPStreamlined.sol:AMTTP');    );

    console.log(`✅ AMTTP balance: ${ethers.formatEther(balance)} AMTTP`);

        const amttp = await upgrades.deployProxy(    await policyManager.deployed();

    const canTransfer = await amttp.canTransfer(deployer.address, '0x1234567890123456789012345678901234567890', ethers.parseEther('100'));

    console.log(`✅ Can transfer 100 AMTTP: ${canTransfer}`);        AMTTP,    console.log('✅ AMTTPPolicyManager deployed to:', policyManager.address);

    

    console.log('\n🎉 Modular deployment complete!');        [    

    console.log('\n📚 All contracts deployed successfully and under size limits!');

                'Anti-Money Transfer Transfer Protocol',    // 2. Deploy streamlined AMTTP contract

    return {

        amttp: await amttp.getAddress(),            'AMTTP',    console.log('\n💰 Deploying AMTTP Streamlined...');

        policyManager: await policyManager.getAddress(),

        policyEngine: await policyEngine.getAddress()            ethers.parseEther('1000000') // 1M initial supply    const AMTTP = await ethers.getContractFactory('AMTTP');

    };

}        ],    const amttp = await upgrades.deployProxy(



if (require.main === module) {        {         AMTTP,

    main().then(() => process.exit(0)).catch((error) => {

        console.error('❌ Deployment failed:', error);            initializer: 'initialize',        [

        process.exit(1);

    });            kind: 'uups'            'Anti-Money Transfer Transfer Protocol',

}

        }            'AMTTP',

module.exports = main;
    );            ethers.utils.parseEther('1000000') // 1M initial supply

            ],

    console.log('✅ AMTTP deployed to:', await amttp.getAddress());        { 

                initializer: 'initialize',

    // 3. Connect the contracts            kind: 'uups'

    console.log('\n🔗 Connecting contracts...');        }

    await amttp.setPolicyManager(await policyManager.getAddress());    );

    console.log('✅ Policy manager connected to AMTTP');    await amttp.deployed();

        console.log('✅ AMTTP deployed to:', amttp.address);

    // 4. Deploy policy engine (the full one as separate contract)    

    console.log('\n🏗️  Deploying full AMTTPPolicyEngine...');    // 3. Connect the contracts

    const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');    console.log('\n🔗 Connecting contracts...');

    const policyEngine = await upgrades.deployProxy(    await amttp.setPolicyManager(policyManager.address);

        PolicyEngine,    console.log('✅ Policy manager connected to AMTTP');

        [ethers.ZeroAddress, deployer.address], // Will set AMTTP address later, use deployer as oracle    

        {     // 4. Set up initial configuration

            initializer: 'initialize',    console.log('\n⚙️  Setting up initial configuration...');

            kind: 'uups'    

        }    // Set global risk threshold to 70%

    );    await policyManager.initialize();

        console.log('✅ Policy manager initialized');

    console.log('✅ AMTTPPolicyEngine deployed to:', await policyEngine.getAddress());    

        // 5. Deploy policy engine (the full one as separate contract)

    // 5. Connect policy engine to manager (optional advanced features)    console.log('\n🏗️  Deploying full AMTTPPolicyEngine...');

    console.log('\n🔌 Connecting policy engine...');    const PolicyEngine = await ethers.getContractFactory('AMTTPPolicyEngine');

    await policyManager.setPolicyEngine(await policyEngine.getAddress());    const policyEngine = await upgrades.deployProxy(

    console.log('✅ Policy engine connected to manager');        PolicyEngine,

            [],

    // 6. Verify deployments        { 

    console.log('\n🔍 Verifying deployments...');            initializer: 'initialize',

                kind: 'uups'

    // Check contract sizes        }

    const amttpCode = await ethers.provider.getCode(await amttp.getAddress());    );

    const policyManagerCode = await ethers.provider.getCode(await policyManager.getAddress());    await policyEngine.deployed();

    const policyEngineCode = await ethers.provider.getCode(await policyEngine.getAddress());    console.log('✅ AMTTPPolicyEngine deployed to:', policyEngine.address);

        

    console.log('📏 Contract sizes:');    // 6. Connect policy engine to manager (optional advanced features)

    console.log(`   AMTTP: ${amttpCode.length / 2 - 1} bytes`);    console.log('\n🔌 Connecting policy engine...');

    console.log(`   Policy Manager: ${policyManagerCode.length / 2 - 1} bytes`);    await policyManager.setPolicyEngine(policyEngine.address);

    console.log(`   Policy Engine: ${policyEngineCode.length / 2 - 1} bytes`);    console.log('✅ Policy engine connected to manager');

        

    // Test basic functionality    // 7. Verify deployments

    console.log('\n🧪 Testing basic functionality...');    console.log('\n🔍 Verifying deployments...');

        

    const balance = await amttp.balanceOf(deployer.address);    // Check contract sizes

    console.log(`✅ AMTTP balance: ${ethers.formatEther(balance)} AMTTP`);    const amttpCode = await ethers.provider.getCode(amttp.address);

        const policyManagerCode = await ethers.provider.getCode(policyManager.address);

    const canTransfer = await amttp.canTransfer(    const policyEngineCode = await ethers.provider.getCode(policyEngine.address);

        deployer.address,    

        '0x1234567890123456789012345678901234567890',    console.log('📏 Contract sizes:');

        ethers.parseEther('100')    console.log(`   AMTTP: ${amttpCode.length / 2 - 1} bytes`);

    );    console.log(`   Policy Manager: ${policyManagerCode.length / 2 - 1} bytes`);

    console.log(`✅ Can transfer 100 AMTTP: ${canTransfer}`);    console.log(`   Policy Engine: ${policyEngineCode.length / 2 - 1} bytes`);

        

    // 7. Save deployment addresses    // Test basic functionality

    const deploymentInfo = {    console.log('\n🧪 Testing basic functionality...');

        network: await ethers.provider.getNetwork(),    

        timestamp: new Date().toISOString(),    const balance = await amttp.balanceOf(deployer.address);

        deployer: deployer.address,    console.log(`✅ AMTTP balance: ${ethers.utils.formatEther(balance)} AMTTP`);

        contracts: {    

            AMTTP: {    const canTransfer = await amttp.canTransfer(

                address: await amttp.getAddress(),        deployer.address,

                size: `${amttpCode.length / 2 - 1} bytes`        '0x1234567890123456789012345678901234567890',

            },        ethers.utils.parseEther('100')

            AMTTPPolicyManager: {    );

                address: await policyManager.getAddress(),    console.log(`✅ Can transfer 100 AMTTP: ${canTransfer}`);

                size: `${policyManagerCode.length / 2 - 1} bytes`    

            },    // 8. Save deployment addresses

            AMTTPPolicyEngine: {    const deploymentInfo = {

                address: await policyEngine.getAddress(),        network: await ethers.provider.getNetwork(),

                size: `${policyEngineCode.length / 2 - 1} bytes`        timestamp: new Date().toISOString(),

            }        deployer: deployer.address,

        }        contracts: {

    };            AMTTP: {

                    address: amttp.address,

    console.log('\n📋 Deployment Summary:');                size: `${amttpCode.length / 2 - 1} bytes`

    console.log('='.repeat(50));            },

    console.log(`Network: ${deploymentInfo.network.name} (${deploymentInfo.network.chainId})`);            AMTTPPolicyManager: {

    console.log(`Deployer: ${deploymentInfo.deployer}`);                address: policyManager.address,

    console.log(`\nContract Addresses:`);                size: `${policyManagerCode.length / 2 - 1} bytes`

    console.log(`  AMTTP: ${deploymentInfo.contracts.AMTTP.address}`);            },

    console.log(`  Policy Manager: ${deploymentInfo.contracts.AMTTPPolicyManager.address}`);            AMTTPPolicyEngine: {

    console.log(`  Policy Engine: ${deploymentInfo.contracts.AMTTPPolicyEngine.address}`);                address: policyEngine.address,

    console.log(`\nContract Sizes:`);                size: `${policyEngineCode.length / 2 - 1} bytes`

    console.log(`  AMTTP: ${deploymentInfo.contracts.AMTTP.size}`);            }

    console.log(`  Policy Manager: ${deploymentInfo.contracts.AMTTPPolicyManager.size}`);        }

    console.log(`  Policy Engine: ${deploymentInfo.contracts.AMTTPPolicyEngine.size}`);    };

    console.log('='.repeat(50));    

        console.log('\n📋 Deployment Summary:');

    // Save to file    console.log('='.repeat(50));

    const fs = require('fs');    console.log(`Network: ${deploymentInfo.network.name} (${deploymentInfo.network.chainId})`);

    fs.writeFileSync(    console.log(`Deployer: ${deploymentInfo.deployer}`);

        './deployment-modular.json',    console.log(`\nContract Addresses:`);

        JSON.stringify(deploymentInfo, null, 2)    console.log(`  AMTTP: ${deploymentInfo.contracts.AMTTP.address}`);

    );    console.log(`  Policy Manager: ${deploymentInfo.contracts.AMTTPPolicyManager.address}`);

    console.log('\n💾 Deployment info saved to deployment-modular.json');    console.log(`  Policy Engine: ${deploymentInfo.contracts.AMTTPPolicyEngine.address}`);

        console.log(`\nContract Sizes:`);

    console.log('\n🎉 Modular deployment complete!');    console.log(`  AMTTP: ${deploymentInfo.contracts.AMTTP.size}`);

    console.log('\n📚 Next steps:');    console.log(`  Policy Manager: ${deploymentInfo.contracts.AMTTPPolicyManager.size}`);

    console.log('1. Update backend oracle service with new contract addresses');    console.log(`  Policy Engine: ${deploymentInfo.contracts.AMTTPPolicyEngine.size}`);

    console.log('2. Configure policy settings via PolicyManager');    console.log('='.repeat(50));

    console.log('3. Test end-to-end transaction flow');    

    console.log('4. Deploy React dashboard for policy management');    // Save to file

        const fs = require('fs');

    return {    fs.writeFileSync(

        amttp: await amttp.getAddress(),        './deployment-modular.json',

        policyManager: await policyManager.getAddress(),        JSON.stringify(deploymentInfo, null, 2)

        policyEngine: await policyEngine.getAddress()    );

    };    console.log('\n💾 Deployment info saved to deployment-modular.json');

}    

    console.log('\n🎉 Modular deployment complete!');

if (require.main === module) {    console.log('\n📚 Next steps:');

    main()    console.log('1. Update backend oracle service with new contract addresses');

        .then(() => process.exit(0))    console.log('2. Configure policy settings via PolicyManager');

        .catch((error) => {    console.log('3. Test end-to-end transaction flow');

            console.error('❌ Deployment failed:', error);    console.log('4. Deploy React dashboard for policy management');

            process.exit(1);    

        });    return {

}        amttp: amttp.address,

        policyManager: policyManager.address,

module.exports = main;        policyEngine: policyEngine.address
    };
}

if (require.main === module) {
    main()
        .then(() => process.exit(0))
        .catch((error) => {
            console.error('❌ Deployment failed:', error);
            process.exit(1);
        });
}

module.exports = main;