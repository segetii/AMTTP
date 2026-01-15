/**
 * AMTTP Mainnet Deployment Preparation
 * Production deployment configuration, multi-sig setup, and deployment scripts
 * 
 * IMPORTANT: This script prepares mainnet deployment but does NOT execute it.
 * Actual mainnet deployment requires:
 * 1. Security audit completion
 * 2. Multi-sig wallet setup
 * 3. Manual review of all parameters
 * 4. Team approval
 */

const hre = require("hardhat");
const fs = require("fs");
const path = require("path");

// ═══════════════════════════════════════════════════════════════════════════════
// MAINNET CONFIGURATIONS
// ═══════════════════════════════════════════════════════════════════════════════

const MAINNET_CONFIGS = {
  ethereum: {
    name: "Ethereum Mainnet",
    chainId: 1,
    rpcUrl: process.env.ETH_MAINNET_RPC || "https://eth.llamarpc.com",
    explorer: "https://etherscan.io",
    layerZeroEndpoint: "0x66A71Dcef29A0fFBDBE3c6a460a3B5BC225Cd675",
    lzChainId: 101,
    gasPrice: "auto", // Use network gas price
    contracts: {
      policyEngine: null,
      disputeResolver: null,
      crossChain: null,
      riskRouter: null
    },
    multisig: {
      required: true,
      threshold: 3, // 3-of-5 signatures required
      owners: [
        // Add your multisig owners here
        // "0x...",
      ]
    }
  },
  polygon: {
    name: "Polygon Mainnet",
    chainId: 137,
    rpcUrl: process.env.POLYGON_RPC || "https://polygon-rpc.com",
    explorer: "https://polygonscan.com",
    layerZeroEndpoint: "0x3c2269811836af69497E5F486A85D7316753cf62",
    lzChainId: 109,
    gasPrice: "auto",
    contracts: {
      riskRouter: null
    },
    multisig: {
      required: true,
      threshold: 2,
      owners: []
    }
  },
  arbitrum: {
    name: "Arbitrum One",
    chainId: 42161,
    rpcUrl: process.env.ARBITRUM_RPC || "https://arb1.arbitrum.io/rpc",
    explorer: "https://arbiscan.io",
    layerZeroEndpoint: "0x3c2269811836af69497E5F486A85D7316753cf62",
    lzChainId: 110,
    gasPrice: "auto",
    contracts: {
      riskRouter: null
    },
    multisig: {
      required: true,
      threshold: 2,
      owners: []
    }
  },
  optimism: {
    name: "Optimism",
    chainId: 10,
    rpcUrl: process.env.OPTIMISM_RPC || "https://mainnet.optimism.io",
    explorer: "https://optimistic.etherscan.io",
    layerZeroEndpoint: "0x3c2269811836af69497E5F486A85D7316753cf62",
    lzChainId: 111,
    gasPrice: "auto",
    contracts: {
      riskRouter: null
    },
    multisig: {
      required: true,
      threshold: 2,
      owners: []
    }
  },
  base: {
    name: "Base",
    chainId: 8453,
    rpcUrl: process.env.BASE_RPC || "https://mainnet.base.org",
    explorer: "https://basescan.org",
    layerZeroEndpoint: "0xb6319cC6c8c27A8F5dAF0dD3DF91EA35C4720dd7",
    lzChainId: 184,
    gasPrice: "auto",
    contracts: {
      riskRouter: null
    },
    multisig: {
      required: true,
      threshold: 2,
      owners: []
    }
  }
};

// ═══════════════════════════════════════════════════════════════════════════════
// DEPLOYMENT CHECKLIST
// ═══════════════════════════════════════════════════════════════════════════════

const DEPLOYMENT_CHECKLIST = {
  preDeployment: [
    { id: "audit", name: "Security Audit Completed", required: true, status: "pending" },
    { id: "audit_fixes", name: "All Audit Findings Fixed", required: true, status: "pending" },
    { id: "multisig", name: "Multi-sig Wallet Created", required: true, status: "pending" },
    { id: "multisig_owners", name: "Multi-sig Owners Configured", required: true, status: "pending" },
    { id: "env_vars", name: "Environment Variables Set", required: true, status: "pending" },
    { id: "gas_estimate", name: "Gas Cost Estimated", required: false, status: "pending" },
    { id: "eth_funded", name: "Deployer Wallet Funded", required: true, status: "pending" },
    { id: "backup_keys", name: "Backup Keys Secured", required: true, status: "pending" }
  ],
  deployment: [
    { id: "deploy_policy", name: "Deploy PolicyEngine", required: true, status: "pending" },
    { id: "deploy_dispute", name: "Deploy DisputeResolver", required: true, status: "pending" },
    { id: "deploy_crosschain", name: "Deploy CrossChain", required: true, status: "pending" },
    { id: "deploy_router", name: "Deploy RiskRouter (L2s)", required: true, status: "pending" },
    { id: "verify_contracts", name: "Verify All Contracts", required: true, status: "pending" }
  ],
  postDeployment: [
    { id: "transfer_ownership", name: "Transfer Ownership to Multi-sig", required: true, status: "pending" },
    { id: "configure_policies", name: "Configure Default Policies", required: true, status: "pending" },
    { id: "set_oracles", name: "Configure Oracle Addresses", required: true, status: "pending" },
    { id: "lz_trusted_remotes", name: "Set LayerZero Trusted Remotes", required: true, status: "pending" },
    { id: "test_transactions", name: "Execute Test Transactions", required: true, status: "pending" },
    { id: "monitoring", name: "Set Up Monitoring Alerts", required: true, status: "pending" },
    { id: "documentation", name: "Update Documentation", required: false, status: "pending" }
  ]
};

// ═══════════════════════════════════════════════════════════════════════════════
// GAS ESTIMATION
// ═══════════════════════════════════════════════════════════════════════════════

async function estimateDeploymentCosts() {
  console.log("\n💰 Estimating Deployment Costs...\n");
  
  const estimates = {};
  
  // Get current gas prices
  const feeData = await hre.ethers.provider.getFeeData();
  const gasPrice = feeData.gasPrice;
  
  console.log(`Current Gas Price: ${hre.ethers.formatUnits(gasPrice, "gwei")} gwei\n`);
  
  // Estimate gas for each contract
  const contracts = [
    { name: "AMTTPPolicyEngine", factory: "AMTTPPolicyEngine" },
    { name: "AMTTPDisputeResolver", factory: "AMTTPDisputeResolver" },
    { name: "AMTTPCrossChain", factory: "AMTTPCrossChain" },
    { name: "AMTTPRiskRouter", factory: "AMTTPRiskRouter" }
  ];
  
  let totalGas = 0n;
  
  for (const contract of contracts) {
    try {
      const factory = await hre.ethers.getContractFactory(contract.factory);
      const deployTx = await factory.getDeployTransaction(
        "0x0000000000000000000000000000000000000001", // Placeholder arg
        "0x0000000000000000000000000000000000000002"  // Placeholder arg
      );
      
      const gasEstimate = await hre.ethers.provider.estimateGas({
        data: deployTx.data
      });
      
      estimates[contract.name] = {
        gasUnits: gasEstimate.toString(),
        costWei: (gasEstimate * gasPrice).toString(),
        costEth: hre.ethers.formatEther(gasEstimate * gasPrice)
      };
      
      totalGas += gasEstimate;
      
      console.log(`${contract.name}:`);
      console.log(`  Gas: ${gasEstimate.toString()} units`);
      console.log(`  Cost: ${hre.ethers.formatEther(gasEstimate * gasPrice)} ETH\n`);
    } catch (error) {
      console.log(`${contract.name}: Could not estimate (${error.message})\n`);
    }
  }
  
  console.log("═".repeat(50));
  console.log(`Total Estimated Gas: ${totalGas.toString()} units`);
  console.log(`Total Estimated Cost: ${hre.ethers.formatEther(totalGas * gasPrice)} ETH`);
  console.log(`Recommended Buffer (2x): ${hre.ethers.formatEther(totalGas * gasPrice * 2n)} ETH`);
  
  return estimates;
}

// ═══════════════════════════════════════════════════════════════════════════════
// GENERATE DEPLOYMENT PLAN
// ═══════════════════════════════════════════════════════════════════════════════

function generateDeploymentPlan(targetNetwork) {
  const config = MAINNET_CONFIGS[targetNetwork];
  if (!config) {
    console.error(`Unknown network: ${targetNetwork}`);
    return null;
  }
  
  const plan = {
    network: targetNetwork,
    config: config,
    timestamp: new Date().toISOString(),
    checklist: DEPLOYMENT_CHECKLIST,
    steps: [
      {
        order: 1,
        name: "Pre-flight Checks",
        commands: [
          `npx hardhat compile`,
          `npx hardhat test`,
          `npx hardhat run scripts/check-deployment-readiness.cjs --network ${targetNetwork}`
        ]
      },
      {
        order: 2,
        name: "Deploy Core Contracts (Ethereum)",
        commands: targetNetwork === "ethereum" ? [
          `npx hardhat run scripts/deploy-policyengine.cjs --network ${targetNetwork}`,
          `npx hardhat run scripts/deploy-disputeresolver.cjs --network ${targetNetwork}`,
          `npx hardhat run scripts/deploy-crosschain.cjs --network ${targetNetwork}`
        ] : ["Skip - not Ethereum mainnet"]
      },
      {
        order: 3,
        name: "Deploy RiskRouter",
        commands: [
          `npx hardhat run scripts/deploy-riskrouter.cjs --network ${targetNetwork}`
        ]
      },
      {
        order: 4,
        name: "Verify Contracts",
        commands: [
          `npx hardhat verify --network ${targetNetwork} <CONTRACT_ADDRESS> <CONSTRUCTOR_ARGS>`
        ]
      },
      {
        order: 5,
        name: "Configure Contracts",
        commands: [
          `npx hardhat run scripts/configure-mainnet.cjs --network ${targetNetwork}`
        ]
      },
      {
        order: 6,
        name: "Transfer Ownership",
        commands: [
          `npx hardhat run scripts/transfer-to-multisig.cjs --network ${targetNetwork}`
        ]
      }
    ]
  };
  
  return plan;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MULTI-SIG SETUP HELPER
// ═══════════════════════════════════════════════════════════════════════════════

function generateMultisigSetup(targetNetwork) {
  const config = MAINNET_CONFIGS[targetNetwork];
  
  return {
    network: targetNetwork,
    safeVersion: "1.3.0",
    threshold: config.multisig.threshold,
    suggestedOwners: [
      "Owner 1 - CEO/Founder (Hardware Wallet)",
      "Owner 2 - CTO (Hardware Wallet)",
      "Owner 3 - Security Lead (Hardware Wallet)",
      "Owner 4 - Operations Lead (Hardware Wallet)",
      "Owner 5 - Legal/Compliance (Hardware Wallet)"
    ],
    setupInstructions: [
      "1. Go to https://app.safe.global/",
      `2. Connect to ${config.name}`,
      "3. Click 'Create Safe'",
      `4. Add ${config.multisig.threshold + 2} owner addresses`,
      `5. Set threshold to ${config.multisig.threshold}`,
      "6. Review and create Safe",
      "7. Fund Safe with ETH for gas",
      "8. Update MAINNET_CONFIGS with Safe address"
    ],
    ownerRequirements: [
      "Each owner should use a hardware wallet (Ledger/Trezor)",
      "Owners should be geographically distributed",
      "At least 2 owners should be technical (can verify transactions)",
      "Backup access procedures documented offline"
    ]
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

async function main() {
  const command = process.argv[2];
  const targetNetwork = process.argv[3] || "ethereum";
  
  console.log("\n" + "═".repeat(60));
  console.log("   AMTTP Mainnet Deployment Preparation");
  console.log("═".repeat(60));
  
  switch (command) {
    case "estimate":
      await estimateDeploymentCosts();
      break;
      
    case "plan":
      const plan = generateDeploymentPlan(targetNetwork);
      console.log("\n📋 Deployment Plan:\n");
      console.log(JSON.stringify(plan, null, 2));
      
      // Save plan to file
      const planFile = path.join(__dirname, `../deployments/mainnet-plan-${targetNetwork}.json`);
      fs.mkdirSync(path.dirname(planFile), { recursive: true });
      fs.writeFileSync(planFile, JSON.stringify(plan, null, 2));
      console.log(`\n📁 Plan saved to ${planFile}`);
      break;
      
    case "multisig":
      const msSetup = generateMultisigSetup(targetNetwork);
      console.log("\n🔐 Multi-sig Setup Guide:\n");
      console.log(JSON.stringify(msSetup, null, 2));
      break;
      
    case "checklist":
      console.log("\n✅ Deployment Checklist:\n");
      for (const [phase, items] of Object.entries(DEPLOYMENT_CHECKLIST)) {
        console.log(`\n${phase.toUpperCase()}:`);
        for (const item of items) {
          const status = item.status === "completed" ? "✅" : "⬜";
          const required = item.required ? "(Required)" : "(Optional)";
          console.log(`  ${status} ${item.name} ${required}`);
        }
      }
      break;
      
    case "networks":
      console.log("\n🌐 Supported Mainnet Networks:\n");
      for (const [key, config] of Object.entries(MAINNET_CONFIGS)) {
        console.log(`  ${key}:`);
        console.log(`    Name: ${config.name}`);
        console.log(`    Chain ID: ${config.chainId}`);
        console.log(`    Explorer: ${config.explorer}`);
        console.log(`    LZ Chain ID: ${config.lzChainId}`);
        console.log();
      }
      break;
      
    default:
      console.log(`
Usage:
  npx hardhat run scripts/mainnet-prep.cjs -- estimate    - Estimate deployment costs
  npx hardhat run scripts/mainnet-prep.cjs -- plan [network]     - Generate deployment plan
  npx hardhat run scripts/mainnet-prep.cjs -- multisig [network] - Multi-sig setup guide
  npx hardhat run scripts/mainnet-prep.cjs -- checklist   - Show deployment checklist
  npx hardhat run scripts/mainnet-prep.cjs -- networks    - List supported networks

Networks: ethereum, polygon, arbitrum, optimism, base
      `);
  }
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });

module.exports = { MAINNET_CONFIGS, DEPLOYMENT_CHECKLIST };
