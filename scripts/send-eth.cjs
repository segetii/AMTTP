/**
 * Send Sepolia ETH to target address
 */
const { ethers } = require("hardhat");

async function main() {
  const [signer] = await ethers.getSigners();
  
  console.log("============================================");
  console.log("SENDING SEPOLIA ETH");
  console.log("============================================");
  console.log("From:", signer.address);
  
  const balance = await ethers.provider.getBalance(signer.address);
  console.log("Balance:", ethers.formatEther(balance), "ETH");
  
  const recipient = "0xb0a12251652988777B80856C9F961Ce1d93640A2";
  const amount = "0.2";
  
  console.log("\nSending", amount, "ETH to:", recipient);
  
  const tx = await signer.sendTransaction({
    to: recipient,
    value: ethers.parseEther(amount)
  });
  
  console.log("TX Hash:", tx.hash);
  console.log("Waiting for confirmation...");
  
  const receipt = await tx.wait();
  console.log("\n✅ CONFIRMED!");
  console.log("Block:", receipt.blockNumber);
  console.log("Gas Used:", receipt.gasUsed.toString());
  console.log("\nView on Etherscan:");
  console.log(`https://sepolia.etherscan.io/tx/${tx.hash}`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Error:", error.message);
    process.exit(1);
  });
