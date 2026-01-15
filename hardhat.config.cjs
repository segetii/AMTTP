require("@nomicfoundation/hardhat-toolbox");
require("@openzeppelin/hardhat-upgrades");
const dotenv = require("dotenv");

dotenv.config();

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { 
        enabled: true, 
        runs: 50  // Reduced from 200 for smaller bytecode (saves ~5-10% deployment gas)
      },
      viaIR: true
    }
  },
  networks: {
    hardhat: {},
    localhost: {
      url: "http://127.0.0.1:8545"
    },
    sepolia: {
      url: process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com",
      accounts: process.env.PRIVATE_KEY ? [`0x${process.env.PRIVATE_KEY.replace('0x', '')}`] : [],
      timeout: 120000,
      gasPrice: "auto"
    },
    polygonAmoy: {
      url: process.env.POLYGON_AMOY_RPC || "https://rpc-amoy.polygon.technology",
      accounts: process.env.PRIVATE_KEY ? [`0x${process.env.PRIVATE_KEY.replace('0x', '')}`] : [],
      timeout: 120000
    },
    arbitrumSepolia: {
      url: process.env.ARBITRUM_SEPOLIA_RPC || "https://sepolia-rollup.arbitrum.io/rpc",
      accounts: process.env.PRIVATE_KEY ? [`0x${process.env.PRIVATE_KEY.replace('0x', '')}`] : [],
      timeout: 120000
    },
    baseSepolia: {
      url: process.env.BASE_SEPOLIA_RPC || "https://sepolia.base.org",
      accounts: process.env.PRIVATE_KEY ? [`0x${process.env.PRIVATE_KEY.replace('0x', '')}`] : [],
      timeout: 120000
    }
  },
  etherscan: {
    // Using Etherscan API V2 format (single key for all EVM chains)
    apiKey: process.env.ETHERSCAN_API_KEY || ""
  },
  gasReporter: {
    enabled: process.env.REPORT_GAS === "true",
    outputFile: "gas-report.txt",
    noColors: true,  // Avoids ANSI codes in file output
    currency: "USD",
    excludeContracts: ["mocks/"]
  }
};