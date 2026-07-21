/**
 * deploy-dispute-resolver-arb-sepolia.cjs
 *
 * Deploys AMTTPDisputeResolver on Arbitrum Sepolia pointing to the REAL
 * KlerosCore v2 arbitrator (not a mock).
 *
 * Real KlerosCore on Arbitrum Sepolia:
 *   https://sepolia.arbiscan.io/address/0xE8442307d36e9bf6aB27F1A009F95CE8E11C3479
 *
 * Usage:
 *   npx hardhat run scripts/deploy-dispute-resolver-arb-sepolia.cjs --network arbitrumSepolia
 */

const hre = require("hardhat");
require("dotenv").config();

// Real Kleros v2 KlerosCore on Arbitrum Sepolia
// Source: https://github.com/kleros/kleros-v2/blob/dev/contracts/deployments/arbitrumSepolia/KlerosCore.json
const KLEROS_CORE_ARB_SEPOLIA = "0xE8442307d36e9bf6aB27F1A009F95CE8E11C3479";

// IPFS meta-evidence URI describing the AMTTP dispute resolution rules
const META_EVIDENCE_URI =
  "ipfs://bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi/amttp-meta-evidence.json";

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  const balance = await hre.ethers.provider.getBalance(deployer.address);

  console.log("=".repeat(60));
  console.log("AMTTP DisputeResolver — Arbitrum Sepolia (Real Kleros)");
  console.log("=".repeat(60));
  console.log(`Deployer:    ${deployer.address}`);
  console.log(`Balance:     ${hre.ethers.formatEther(balance)} ETH`);
  console.log(`Network:     ${hre.network.name}`);
  console.log(`KlerosCore:  ${KLEROS_CORE_ARB_SEPOLIA}`);
  console.log("");

  if (balance < hre.ethers.parseEther("0.005")) {
    throw new Error("Insufficient balance — need at least 0.005 ETH");
  }

  console.log("Deploying AMTTPDisputeResolver...");
  const Factory = await hre.ethers.getContractFactory("contracts/AMTTPDisputeResolver.sol:AMTTPDisputeResolver");
  const contract = await Factory.deploy(KLEROS_CORE_ARB_SEPOLIA, META_EVIDENCE_URI);
  await contract.waitForDeployment();

  const addr = await contract.getAddress();
  console.log(`\n✅ Deployed at: ${addr}`);
  console.log(`   Arbiscan:    https://sepolia.arbiscan.io/address/${addr}`);
  console.log(`   KlerosCore:  https://sepolia.arbiscan.io/address/${KLEROS_CORE_ARB_SEPOLIA}`);

  // Verify arbitrator is set correctly
  const storedArbitrator = await contract.arbitrator();
  console.log(`\n   arbitrator() = ${storedArbitrator}`);
  if (storedArbitrator.toLowerCase() !== KLEROS_CORE_ARB_SEPOLIA.toLowerCase()) {
    throw new Error("Arbitrator mismatch!");
  }
  console.log("   ✅ Arbitrator verified = real KlerosCore v2");

  // Save deployment info
  const fs = require("fs");
  const deployInfo = {
    network: "arbitrumSepolia",
    chainId: 421614,
    disputeResolver: addr,
    klerosCore: KLEROS_CORE_ARB_SEPOLIA,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    arbiscan: `https://sepolia.arbiscan.io/address/${addr}`,
  };
  fs.writeFileSync(
    "deployments/arb-sepolia-dispute-resolver.json",
    JSON.stringify(deployInfo, null, 2)
  );
  console.log("\n📄 Deployment info saved to deployments/arb-sepolia-dispute-resolver.json");

  console.log("\nNext step:");
  console.log(`  node scripts/run-kleros-dispute-flow.cjs`);
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
