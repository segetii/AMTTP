// scripts/deploy.js
import hre from "hardhat";
const { ethers, upgrades } = hre;

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("Deploying contracts with the account:", deployer.address);
  console.log("Account balance:", (await ethers.provider.getBalance(deployer.address)).toString());

  // Configuration
  const oracleAddress = deployer.address; // Use deployer as oracle for simplicity; change as needed
  const threshold = 1; // Minimum 1 approver for medium/high risk swaps

  // Deploy the upgradeable AMTTP contract via proxy
  const AMTTP = await ethers.getContractFactory("AMTTP");
  console.log("Deploying AMTTP...");

  // Change the second argument from [deployer.address] to an empty array []
  const amttp = await upgrades.deployProxy(AMTTP, [], { initializer: 'initialize' });

  await amttp.waitForDeployment();

  console.log("AMTTP Proxy deployed to:", await amttp.getAddress());
  console.log("Implementation address:", await upgrades.erc1967.getImplementationAddress(await amttp.getAddress()));
  console.log("Proxy admin address:", await upgrades.erc1967.getAdminAddress(await amttp.getAddress()));

  // Optional: Verify on Etherscan if on a supported network
  // await hre.run("verify:verify", {
  //   address: await amttp.getAddress(),
  //   constructorArguments: [],
  // });
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });