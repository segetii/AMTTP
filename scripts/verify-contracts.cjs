/**
 * AMTTP Contract Verification Script
 * ===================================
 * Verifies deployed contracts on Etherscan/block explorers
 * 
 * Prerequisites:
 * 1. Add ETHERSCAN_API_KEY to your .env file
 *    Get one free at: https://etherscan.io/myapikey
 * 
 * Usage:
 *   npx hardhat run scripts/verify-contracts.cjs --network sepolia
 * 
 * Or individually:
 *   npx hardhat verify --network sepolia <address> [constructor args]
 * 
 * To verify from deployment file:
 *   DEPLOYMENT_FILE=deployments/unified-sepolia-1766715756659.json npx hardhat run scripts/verify-contracts.cjs --network sepolia
 */

const { run } = require("hardhat");
const fs = require("fs");
const path = require("path");
require("dotenv").config();

// Load addresses from deployment file or use defaults
function loadContracts(network) {
  // Check if deployment file specified
  const deploymentFile = process.env.DEPLOYMENT_FILE;
  if (deploymentFile && fs.existsSync(deploymentFile)) {
    console.log(`📂 Loading addresses from: ${deploymentFile}`);
    const deployment = JSON.parse(fs.readFileSync(deploymentFile, "utf8"));
    
    return {
      AMTTPCore: {
        address: deployment.contracts.amttpCore,
        constructorArgs: []  // UUPS proxy - no constructor args for verification
      },
      AMTTPPolicyEngine: {
        address: deployment.contracts.policyEngine,
        constructorArgs: []
      },
      AMTTPDisputeResolver: {
        address: deployment.contracts.disputeResolver,
        constructorArgs: [
          "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8",  // Kleros Arbitrator (Sepolia)
          "ipfs://QmAMTTPMetaEvidence"                   // Meta evidence URI
        ]
      },
      AMTTPCrossChain: {
        address: deployment.contracts.crossChain,
        constructorArgs: [
          "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1",  // LayerZero Endpoint (Sepolia)
          deployment.contracts.policyEngine             // PolicyEngine address
        ]
      }
    };
  }
  
  // Fallback to default addresses
  return DEFAULT_CONTRACTS[network];
}

// Default deployed contract addresses from testnet deployment
const DEFAULT_CONTRACTS = {
  sepolia: {
    AMTTPCore: {
      address: "0x2cF0a1D4FB44C97E80c7935E136a181304A67923",
      constructorArgs: []
    },
    AMTTPPolicyEngine: {
      address: "0x520393A448543FF55f02ddA1218881a8E5851CEc",
      constructorArgs: []  // No constructor args for upgradeable proxy
    },
    AMTTPDisputeResolver: {
      address: "0x8452B7c7f5898B7D7D5c4384ED12dd6fb1235Ade",
      constructorArgs: [
        "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8",  // Kleros Arbitrator (Sepolia)
        "ipfs://QmAMTTPMetaEvidence"                   // Meta evidence URI
      ]
    },
    AMTTPCrossChain: {
      address: "0xc8d887665411ecB4760435fb3d20586C1111bc37",
      constructorArgs: [
        "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1",  // LayerZero Endpoint (Sepolia)
        "0x520393A448543FF55f02ddA1218881a8E5851CEc"   // PolicyEngine address
      ]
    }
  }
};

// For report generation - need to keep reference
let CONTRACTS = {};

async function verifyContract(name, address, constructorArgs) {
  console.log(`\n📋 Verifying ${name} at ${address}...`);
  console.log(`   Constructor args: ${constructorArgs.length === 0 ? 'None' : JSON.stringify(constructorArgs)}`);
  
  try {
    await run("verify:verify", {
      address: address,
      constructorArguments: constructorArgs,
    });
    console.log(`✅ ${name} verified successfully!`);
    return { name, address, status: "success" };
  } catch (error) {
    if (error.message.includes("Already Verified")) {
      console.log(`✅ ${name} is already verified`);
      return { name, address, status: "already-verified" };
    } else if (error.message.includes("API")) {
      console.log(`⚠️  ${name} - API error: ${error.message}`);
      return { name, address, status: "api-error", error: error.message };
    } else {
      console.log(`❌ ${name} verification failed: ${error.message}`);
      return { name, address, status: "failed", error: error.message };
    }
  }
}

async function main() {
  const network = process.env.HARDHAT_NETWORK || "sepolia";
  
  console.log("╔═══════════════════════════════════════════════════════════════╗");
  console.log("║         AMTTP Contract Verification                           ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log(`║  Network: ${network.padEnd(52)}║`);
  console.log("╚═══════════════════════════════════════════════════════════════╝");
  
  // Check for API key
  if (!process.env.ETHERSCAN_API_KEY) {
    console.log("\n⚠️  WARNING: ETHERSCAN_API_KEY not found in environment");
    console.log("   To get an API key:");
    console.log("   1. Go to https://etherscan.io/myapikey");
    console.log("   2. Create a free account and generate an API key");
    console.log("   3. Add to your .env file: ETHERSCAN_API_KEY=your_key_here");
    console.log("\n   Attempting verification anyway (may fail)...\n");
  }
  
  // Load contracts from deployment file or defaults
  const contracts = loadContracts(network);
  CONTRACTS[network] = contracts; // Store for report generation
  
  if (!contracts) {
    console.error(`❌ No contracts configured for network: ${network}`);
    console.log("   Available networks: sepolia");
    console.log("   Or specify DEPLOYMENT_FILE=path/to/deployment.json");
    process.exit(1);
  }
  
  const results = [];
  
  for (const [name, { address, constructorArgs }] of Object.entries(contracts)) {
    const result = await verifyContract(name, address, constructorArgs);
    results.push(result);
    
    // Wait between verifications to avoid rate limiting
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
  
  // Print summary
  console.log("\n╔═══════════════════════════════════════════════════════════════╗");
  console.log("║                    VERIFICATION SUMMARY                        ║");
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  
  const successful = results.filter(r => r.status === "success" || r.status === "already-verified");
  const failed = results.filter(r => r.status === "failed" || r.status === "api-error");
  
  console.log(`║  ✅ Verified: ${successful.length}/${results.length} contracts`.padEnd(64) + "║");
  
  if (failed.length > 0) {
    console.log(`║  ❌ Failed: ${failed.length} contracts`.padEnd(64) + "║");
  }
  
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  
  for (const result of results) {
    const icon = result.status === "success" || result.status === "already-verified" ? "✅" : "❌";
    console.log(`║  ${icon} ${result.name}`.padEnd(64) + "║");
    console.log(`║     ${result.address}`.padEnd(64) + "║");
  }
  
  console.log("╠═══════════════════════════════════════════════════════════════╣");
  console.log("║  View on Etherscan:                                           ║");
  
  for (const result of results) {
    if (result.status === "success" || result.status === "already-verified") {
      const url = `https://${network === "sepolia" ? "sepolia." : ""}etherscan.io/address/${result.address}`;
      console.log(`║  🔗 ${url}`.padEnd(64) + "║");
    }
  }
  
  console.log("╚═══════════════════════════════════════════════════════════════╝");
  
  // Generate Markdown report
  const report = generateReport(network, results);
  const fs = require("fs");
  const reportPath = `deployments/verification-${network}-${Date.now()}.md`;
  fs.writeFileSync(reportPath, report);
  console.log(`\n📝 Report saved to: ${reportPath}`);
}

function generateReport(network, results) {
  const timestamp = new Date().toISOString();
  const explorerBase = network === "sepolia" ? "https://sepolia.etherscan.io" : "https://etherscan.io";
  
  let md = `# AMTTP Contract Verification Report

**Network:** ${network}  
**Date:** ${timestamp}  
**Status:** ${results.filter(r => r.status === "success" || r.status === "already-verified").length}/${results.length} verified

## Verified Contracts

| Contract | Address | Status | Etherscan |
|----------|---------|--------|-----------|
`;

  for (const r of results) {
    const statusIcon = r.status === "success" || r.status === "already-verified" ? "✅" : "❌";
    const link = `[View](${explorerBase}/address/${r.address}#code)`;
    md += `| ${r.name} | \`${r.address}\` | ${statusIcon} ${r.status} | ${link} |\n`;
  }

  md += `
## Contract Details

### AMTTPCore
- **Purpose:** Core swap logic with security features, HTLC implementation
- **Type:** UUPS Upgradeable Proxy
- **Address:** \`${CONTRACTS[network].AMTTPCore?.address || 'Not deployed'}\`

### AMTTPPolicyEngine
- **Purpose:** Risk policy management, transaction thresholds, compliance rules
- **Type:** UUPS Upgradeable Proxy
- **Address:** \`${CONTRACTS[network].AMTTPPolicyEngine.address}\`

### AMTTPDisputeResolver  
- **Purpose:** Kleros integration for dispute arbitration
- **Arbitrator:** \`0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8\` (Kleros Sepolia)
- **Address:** \`${CONTRACTS[network].AMTTPDisputeResolver.address}\`

### AMTTPCrossChain
- **Purpose:** LayerZero cross-chain policy synchronization
- **LayerZero Endpoint:** \`0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1\`
- **Chain ID:** 10161 (Sepolia)
- **Address:** \`${CONTRACTS[network].AMTTPCrossChain.address}\`

## Next Steps

${results.some(r => r.status === "failed" || r.status === "api-error") ? `
### Failed Verifications
Some contracts failed to verify. Try:
1. Ensure ETHERSCAN_API_KEY is set in .env
2. Wait and retry (rate limiting)
3. Verify manually at ${explorerBase}/verifyContract
` : "All contracts verified successfully! ✅"}

## Manual Verification Commands

\`\`\`bash
# AMTTPCore (UUPS proxy - no constructor args)
npx hardhat verify --network ${network} ${CONTRACTS[network].AMTTPCore?.address || '<CORE_ADDRESS>'}

# PolicyEngine (no constructor args)
npx hardhat verify --network ${network} ${CONTRACTS[network].AMTTPPolicyEngine.address}

# DisputeResolver
npx hardhat verify --network ${network} ${CONTRACTS[network].AMTTPDisputeResolver.address} \\
  "0x90992fB4e15cE0C59AEfFb376460FDc4d1fDD2f8" "ipfs://QmAMTTPMetaEvidence"

# CrossChain
npx hardhat verify --network ${network} ${CONTRACTS[network].AMTTPCrossChain.address} \\
  "0xae92d5aD7583AD66E49A0c67BAd18F6ba52dDDc1" "${CONTRACTS[network].AMTTPPolicyEngine.address}"
\`\`\`
`;

  return md;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Script failed:", error);
    process.exit(1);
  });
