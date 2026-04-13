/**
 * Link Trusted Remotes across all 3 chains
 * 
 * Sets up bidirectional trusted remote paths between:
 *   Sepolia ↔ Base Sepolia ↔ Arbitrum Sepolia
 * 
 * Usage: npx hardhat run scripts/link-trusted-remotes.cjs --network sepolia
 *   (then repeat for baseSepolia, arbitrumSepolia)
 * 
 * OR run all 3 at once:
 *   node scripts/link-trusted-remotes.cjs --all
 */

const hre = require('hardhat');
const { ethers } = require('ethers');

// CrossChain addresses per chain
const CROSS_CHAIN = {
  sepolia:         '0x4f21b16D56e67c8Fa6AB0e3457deAB2805432953',
  baseSepolia:     '0x2cF0a1D4FB44C97E80c7935E136a181304A67923',
  arbitrumSepolia: '0xeD749700e531a19eDcB5A709c13d967bbF0fea2f',
};

// LZ chain IDs
const LZ_IDS = {
  sepolia:         10161,
  baseSepolia:     10245,
  arbitrumSepolia: 10231,
};

// RPC endpoints
const RPC = {
  sepolia:         'https://sepolia.infura.io/v3/17e45820418f4461a48ceb80774afecb',
  baseSepolia:     'https://sepolia.base.org',
  arbitrumSepolia: 'https://arb-sepolia.g.alchemy.com/v2/89pxLpYGB_qLyt6T-mVQC',
};

const PRIVATE_KEY = '0x22a0cc52bb4ff29439ac891e7b22ea4af36cbcddd91e8a37e441b6546c44f4ea';

const ABI = [
  'function setTrustedRemote(uint16 _chainId, bytes calldata _remoteAddress) external',
  'function setTrustedRemotePath(uint16 _chainId, bytes calldata _path) external',
  'function trustedRemotes(uint16) view returns (bytes)',
  'function owner() view returns (address)',
];

async function linkChain(chainName) {
  const provider = new ethers.JsonRpcProvider(RPC[chainName]);
  const wallet = new ethers.Wallet(PRIVATE_KEY, provider);
  const cc = new ethers.Contract(CROSS_CHAIN[chainName], ABI, wallet);

  console.log(`\n── ${chainName} (${CROSS_CHAIN[chainName]}) ──`);

  const otherChains = Object.keys(CROSS_CHAIN).filter(c => c !== chainName);

  for (const remote of otherChains) {
    const remoteLzId = LZ_IDS[remote];
    const remoteAddr = CROSS_CHAIN[remote];
    const localAddr = CROSS_CHAIN[chainName];

    // Pack as: remoteAddress + localAddress (20 bytes each)
    const path = ethers.solidityPacked(
      ['address', 'address'],
      [remoteAddr, localAddr]
    );

    console.log(`  → ${remote} (LZ ${remoteLzId}): ${path.slice(0, 22)}...${path.slice(-8)}`);

    try {
      const tx = await cc.setTrustedRemotePath(remoteLzId, path);
      const receipt = await tx.wait();
      console.log(`    ✅ tx: ${receipt.hash}`);
    } catch (e) {
      console.log(`    ❌ ${e.message.slice(0, 100)}`);
    }

    // Small delay between txs
    await new Promise(r => setTimeout(r, 3000));
  }

  // Verify
  console.log(`  Verifying...`);
  for (const remote of otherChains) {
    const stored = await cc.trustedRemotes(LZ_IDS[remote]);
    console.log(`    ${remote}: ${stored ? stored.slice(0, 22) + '...' : 'NOT SET'}`);
  }
}

async function main() {
  console.log(`╔══════════════════════════════════════════════╗`);
  console.log(`║   AMTTP — Link Trusted Remotes (3 chains)   ║`);
  console.log(`╚══════════════════════════════════════════════╝`);

  // If running via Hardhat, only do that network
  if (hre && hre.network && hre.network.name !== 'hardhat') {
    await linkChain(hre.network.name);
  } else {
    // Do all 3 chains
    for (const chain of ['sepolia', 'baseSepolia', 'arbitrumSepolia']) {
      await linkChain(chain);
    }
  }

  console.log(`\n✅ All trusted remotes linked!`);
}

main().catch(console.error);
