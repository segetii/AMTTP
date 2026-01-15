const { ethers } = require("hardhat");

async function main() {
  // Get the deployer from private key
  const [deployer] = await ethers.getSigners();
  const network = await ethers.provider.getNetwork();
  
  console.log("=".repeat(50));
  console.log("DEPLOYER WALLET INFO");
  console.log("=".repeat(50));
  console.log("Network:", network.name, `(chainId: ${network.chainId})`);
  console.log("Address:", deployer.address);
  
  const balance = await ethers.provider.getBalance(deployer.address);
  console.log("Balance:", ethers.formatEther(balance), "native tokens");
  console.log("=".repeat(50));
  
  if (balance < ethers.parseEther("0.01")) {
    console.log("\n⚠️  Low balance! You need native tokens for deployment.");
    if (network.chainId === 421614n) {
      console.log("\nGet Arbitrum Sepolia ETH from:");
      console.log("  - https://faucet.quicknode.com/arbitrum/sepolia");
      console.log("  - https://www.alchemy.com/faucets/arbitrum-sepolia");
    } else if (network.chainId === 80002n) {
      console.log("\nGet Polygon Amoy MATIC from:");
      console.log("  - https://faucet.polygon.technology/");
      console.log("  - https://www.alchemy.com/faucets/polygon-amoy");
    }
  } else {
    console.log("\n✅ Balance sufficient for deployment!");
  }
}

main().catch(console.error);
