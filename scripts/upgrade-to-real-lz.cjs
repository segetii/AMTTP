/**
 * Upgrade CrossChain proxies on all 3 chains to V2 (with setEndpoint),
 * then swap from MockLayerZero to real LZ V1 endpoints.
 * 
 * Usage: npx hardhat run scripts/upgrade-to-real-lz.cjs --network sepolia
 *        npx hardhat run scripts/upgrade-to-real-lz.cjs --network baseSepolia
 *        npx hardhat run scripts/upgrade-to-real-lz.cjs --network arbitrumSepolia
 */

const hre = require('hardhat');

// Real LayerZero V1 endpoint addresses (verified on-chain)
const REAL_LZ_ENDPOINTS = {
  sepolia:         '0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1',
  baseSepolia:     '0x6EDCE65403992e310A62460808c4b910D972f10f',
  arbitrumSepolia: '0x6EDCE65403992e310A62460808c4b910D972f10f',
};

// CrossChain proxy addresses (already deployed)
const CROSS_CHAIN_PROXIES = {
  sepolia:         '0x4f21b16D56e67c8Fa6AB0e3457deAB2805432953',
  baseSepolia:     '0x2cF0a1D4FB44C97E80c7935E136a181304A67923',
  arbitrumSepolia: '0xeD749700e531a19eDcB5A709c13d967bbF0fea2f',
};

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  const proxyAddr = CROSS_CHAIN_PROXIES[network];
  const realLzAddr = REAL_LZ_ENDPOINTS[network];

  if (!proxyAddr || !realLzAddr) {
    console.error(`No config for network: ${network}`);
    process.exit(1);
  }

  console.log(`\n╔══════════════════════════════════════════════════╗`);
  console.log(`║   Upgrade CrossChain to Real LZ — ${network.padEnd(15)}║`);
  console.log(`╚══════════════════════════════════════════════════╝\n`);
  console.log(`Deployer:     ${deployer.address}`);
  console.log(`Proxy:        ${proxyAddr}`);
  console.log(`Real LZ:      ${realLzAddr}`);
  console.log(`Balance:      ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH\n`);

  // Step 1: Upgrade the proxy to new implementation (with setEndpoint)
  console.log('── Step 1: Upgrade proxy implementation ──');
  const CrossChainV2 = await hre.ethers.getContractFactory('contracts/AMTTPCrossChain.sol:AMTTPCrossChain');
  
  // Force import existing proxy so OZ plugin knows about it
  try {
    await hre.upgrades.forceImport(proxyAddr, CrossChainV2, { kind: 'uups' });
    console.log('  Imported existing proxy');
  } catch (e) {
    console.log('  Proxy already known');
  }

  const upgraded = await hre.upgrades.upgradeProxy(proxyAddr, CrossChainV2, { kind: 'uups' });
  await upgraded.waitForDeployment();
  console.log(`  ✅ Proxy upgraded`);

  // Add delay for L2 block propagation
  await new Promise(r => setTimeout(r, 5000));

  // Step 2: Read current endpoint
  const cc = await hre.ethers.getContractAt('contracts/AMTTPCrossChain.sol:AMTTPCrossChain', proxyAddr);
  const oldEndpoint = await cc.lzEndpoint();
  console.log(`\n── Step 2: Swap endpoint ──`);
  console.log(`  Old endpoint: ${oldEndpoint}`);
  console.log(`  New endpoint: ${realLzAddr}`);

  // Step 3: Call setEndpoint to swap to real LZ
  const tx = await cc.setEndpoint(realLzAddr);
  await tx.wait();
  console.log(`  ✅ Endpoint swapped! tx: ${tx.hash}`);

  // Step 4: Verify
  await new Promise(r => setTimeout(r, 3000));
  const newEndpoint = await cc.lzEndpoint();
  const owner = await cc.owner();
  const localChainId = await cc.localChainId();

  console.log(`
╔══════════════════════════════════════════════════════════╗
║   ${network} UPGRADE COMPLETE                              
╠══════════════════════════════════════════════════════════╣
  Proxy:            ${proxyAddr}
  LZ Endpoint:      ${newEndpoint}
  Owner:            ${owner}  
  Local Chain ID:   ${localChainId}
  Real LZ:          ${newEndpoint === realLzAddr ? '✅ YES' : '❌ MISMATCH'}
  Balance:          ${hre.ethers.formatEther(await hre.ethers.provider.getBalance(deployer.address))} ETH
╚══════════════════════════════════════════════════════════╝
`);
}

main().catch(console.error);
