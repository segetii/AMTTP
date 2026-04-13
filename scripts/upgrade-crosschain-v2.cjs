/**
 * Upgrade CrossChain proxies to V2 and swap in real LayerZero endpoints
 * 
 * Usage:
 *   npx hardhat run scripts/upgrade-crosschain-v2.cjs --network sepolia
 *   npx hardhat run scripts/upgrade-crosschain-v2.cjs --network baseSepolia
 *   npx hardhat run scripts/upgrade-crosschain-v2.cjs --network arbitrumSepolia
 */

const hre = require('hardhat');

// Proxy addresses (deployed in previous steps)
const PROXIES = {
  sepolia:         '0x4f21b16D56e67c8Fa6AB0e3457deAB2805432953',
  baseSepolia:     '0x2cF0a1D4FB44C97E80c7935E136a181304A67923',
  arbitrumSepolia: '0xeD749700e531a19eDcB5A709c13d967bbF0fea2f',
};

// Real LayerZero V1 endpoints (testnet)
const REAL_LZ_ENDPOINTS = {
  sepolia:         '0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1',
  baseSepolia:     '0x6EDCE65403992e310A62460808c4b910D972f10f',
  arbitrumSepolia: '0x6EDCE65403992e310A62460808c4b910D972f10f',
};

async function main() {
  const network = hre.network.name;
  const [deployer] = await hre.ethers.getSigners();
  const proxyAddress = PROXIES[network];
  const realEndpoint = REAL_LZ_ENDPOINTS[network];

  if (!proxyAddress || !realEndpoint) {
    throw new Error(`No config for network: ${network}`);
  }

  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   CrossChain V2 Upgrade — ${network.padEnd(18)}║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);
  console.log(`  Deployer: ${deployer.address}`);
  console.log(`  Proxy:    ${proxyAddress}`);
  console.log(`  Real LZ:  ${realEndpoint}`);
  const bal = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`  Balance:  ${hre.ethers.formatEther(bal)} ETH\n`);

  // Step 1: Deploy new V2 implementation
  console.log('── Step 1: Deploy V2 Implementation ──');
  const V2Factory = await hre.ethers.getContractFactory('AMTTPCrossChainV2');
  const v2Impl = await V2Factory.deploy();
  await v2Impl.waitForDeployment();
  const v2ImplAddr = await v2Impl.getAddress();
  console.log(`  ✅ V2 impl deployed: ${v2ImplAddr}`);

  // Wait for deployment to settle
  await new Promise(r => setTimeout(r, 5000));

  // Step 2: Upgrade proxy to V2 via UUPS upgradeTo
  console.log('── Step 2: Upgrade Proxy → V2 ──');
  
  // Get the proxy as V1 (which has upgradeTo from UUPSUpgradeable)
  const proxyAsV1 = await hre.ethers.getContractAt('contracts/AMTTPCrossChain.sol:AMTTPCrossChain', proxyAddress);
  
  // Verify we own it
  const owner = await proxyAsV1.owner();
  console.log(`  Proxy owner: ${owner}`);
  if (owner.toLowerCase() !== deployer.address.toLowerCase()) {
    throw new Error(`Not the owner! Owner is ${owner}`);
  }

  // Read current endpoint before upgrade
  const currentEndpoint = await proxyAsV1.lzEndpoint();
  console.log(`  Current endpoint: ${currentEndpoint}`);

  // Call upgradeTo on the proxy (UUPS)
  const upgradeTx = await proxyAsV1.upgradeTo(v2ImplAddr);
  await upgradeTx.wait();
  console.log(`  ✅ Proxy upgraded to V2: ${upgradeTx.hash}`);

  await new Promise(r => setTimeout(r, 5000));

  // Step 3: Initialize V2 (call reinitializer)
  console.log('── Step 3: Initialize V2 ──');
  const proxyAsV2 = await hre.ethers.getContractAt('AMTTPCrossChainV2', proxyAddress);
  
  try {
    const initTx = await proxyAsV2.initializeV2(deployer.address);
    await initTx.wait();
    console.log(`  ✅ V2 initialized (guardian = deployer): ${initTx.hash}`);
  } catch (e) {
    console.log(`  ⚠️  initializeV2 skipped: ${e.message.slice(0, 80)}`);
  }

  await new Promise(r => setTimeout(r, 5000));

  // Step 4: Swap endpoint to real LZ
  console.log('── Step 4: Set Real LZ Endpoint ──');
  const setTx = await proxyAsV2.setEndpoint(realEndpoint);
  await setTx.wait();
  console.log(`  ✅ Endpoint set to real LZ: ${setTx.hash}`);

  await new Promise(r => setTimeout(r, 3000));

  // Step 5: Verify
  console.log('── Step 5: Verify ──');
  const newEndpoint = await proxyAsV2.lzEndpoint();
  const guardianAddr = await proxyAsV2.guardian();
  const version = await proxyAsV2.VERSION();
  
  console.log(`  Endpoint: ${newEndpoint} ${newEndpoint.toLowerCase() === realEndpoint.toLowerCase() ? '✅' : '❌'}`);
  console.log(`  Guardian: ${guardianAddr}`);
  console.log(`  Version:  ${version}`);

  // Verify trusted remotes still intact
  const LZ_IDS = { sepolia: 10161, baseSepolia: 10245, arbitrumSepolia: 10231 };
  for (const [chain, lzId] of Object.entries(LZ_IDS)) {
    if (chain === network) continue;
    const tr = await proxyAsV2.trustedRemotes(lzId);
    console.log(`  Trusted remote ${chain}: ${tr.length > 0 ? tr.slice(0, 22) + '...' : 'EMPTY ❌'}`);
  }

  const remaining = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`\n  Balance remaining: ${hre.ethers.formatEther(remaining)} ETH`);
  console.log(`\n✅ ${network} CrossChain upgraded to V2 with real LZ endpoint!\n`);
}

main().catch(console.error);
