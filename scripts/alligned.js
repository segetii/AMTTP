// scripts/deploy.js
const { ethers, upgrades } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("Deploying contracts with the account:", deployer.address);
  console.log("Account balance:", (await deployer.getBalance()).toString());

  // Configuration
  const oracleAddress = deployer.address; // Use deployer as oracle for simplicity; change as needed
  const threshold = 1; // Minimum 1 approver for medium/high risk swaps

  // Deploy the upgradeable AMTTP contract via proxy
  const AMTTP = await ethers.getContractFactory("AMTTP");
  const amttpProxy = await upgrades.deployProxy(AMTTP, [oracleAddress, threshold], {
    initializer: "initialize",
    kind: "uups", // Use UUPS proxy for upgradeability
  });

  await amttpProxy.waitForDeployment();

  console.log("AMTTP Proxy deployed to:", await amttpProxy.getAddress());
  console.log("Implementation address:", await upgrades.erc1967.getImplementationAddress(await amttpProxy.getAddress()));
  console.log("Proxy admin address:", await upgrades.erc1967.getAdminAddress(await amttpProxy.getAddress()));

  // Optional: Verify on Etherscan if on a supported network
  // await hre.run("verify:verify", {
  //   address: await amttpProxy.getAddress(),
  //   constructorArguments: [],
  // });
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });