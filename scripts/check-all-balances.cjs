const { ethers } = require("hardhat");

async function main() {
  console.log("=".repeat(60));
  console.log("CHECKING ALL PROJECT WALLET BALANCES ON SEPOLIA");
  console.log("=".repeat(60));
  
  const wallets = [
    { name: "Deployer (from .env private key)", address: "0xBc270F0ce5bbE8Ed8489f11262eF1a1527CaF23F" },
    { name: "Target wallet (sent 0.2 ETH to)", address: "0xb0a12251652988777B80856C9F961Ce1d93640A2" },
    { name: "AMTTPCore Contract", address: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923" },
    { name: "PolicyEngine Contract", address: "0x520393A448543FF55f02ddA1218881a8E5851CEc" },
    { name: "DisputeResolver Contract", address: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade" },
    { name: "CrossChain Contract", address: "0xc8d887665411ecB4760435fb3d20586C1111bc37" },
    { name: "Router Contract", address: "0xbe6EC386ECDa39F3B7c120d9E239e1fBC78d52e3" },
    { name: "NFT Contract", address: "0x49Acc645E22c69263fCf7eFC165B6c3018d5Db5f" },
  ];

  let totalBalance = 0n;
  
  for (const wallet of wallets) {
    try {
      const balance = await ethers.provider.getBalance(wallet.address);
      const ethBalance = ethers.formatEther(balance);
      totalBalance += balance;
      
      console.log(`\n${wallet.name}:`);
      console.log(`  Address: ${wallet.address}`);
      console.log(`  Balance: ${ethBalance} ETH`);
    } catch (e) {
      console.log(`\n${wallet.name}:`);
      console.log(`  Address: ${wallet.address}`);
      console.log(`  Error: ${e.message}`);
    }
  }
  
  console.log("\n" + "=".repeat(60));
  console.log(`TOTAL: ${ethers.formatEther(totalBalance)} ETH`);
  console.log("=".repeat(60));
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
