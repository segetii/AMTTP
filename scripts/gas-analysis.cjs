/**
 * AMTTP Gas Usage Analysis & Optimization Report
 * 
 * Analyzes contract bytecode sizes and estimates deployment gas costs
 * 
 * Usage: npx hardhat run scripts/gas-analysis.cjs
 */

const { ethers } = require("hardhat");
const fs = require("fs");
const path = require("path");

// Contract list
const CONTRACTS = [
    "AMTTPCore",
    "AMTTPNFT", 
    "AMTTPRouter",
    "AMTTPPolicyEngine",
    "AMTTPDisputeResolver",
    "AMTTPCrossChain",
    "AMTTPSafeModule",
    "AMTTPBiconomyModule"
];

// EVM limit
const MAX_CONTRACT_SIZE = 24576; // 24KB in bytes

async function main() {
    console.log(`
╔═══════════════════════════════════════════════════════════════╗
║              AMTTP GAS USAGE ANALYSIS                          ║
╚═══════════════════════════════════════════════════════════════╝
`);

    const results = [];
    let totalDeploymentGas = 0n;
    
    console.log("─────────────────────────────────────────────────────────────────");
    console.log("CONTRACT SIZE ANALYSIS");
    console.log("─────────────────────────────────────────────────────────────────\n");
    
    console.log("Contract                    Size (bytes)   % of Limit    Status");
    console.log("─────────────────────────── ────────────── ───────────── ──────────");

    for (const contractName of CONTRACTS) {
        try {
            const factory = await ethers.getContractFactory(contractName);
            const bytecode = factory.bytecode;
            const sizeBytes = (bytecode.length - 2) / 2; // Remove 0x and divide by 2
            const percentage = ((sizeBytes / MAX_CONTRACT_SIZE) * 100).toFixed(1);
            const status = sizeBytes > MAX_CONTRACT_SIZE ? "❌ EXCEEDS" : 
                          sizeBytes > MAX_CONTRACT_SIZE * 0.9 ? "⚠️  WARNING" : "✅ OK";
            
            // Estimate deployment gas (approximately 200 gas per byte + 32000 base)
            const deployGas = BigInt(32000 + sizeBytes * 200);
            totalDeploymentGas += deployGas;
            
            results.push({
                name: contractName,
                size: sizeBytes,
                percentage: parseFloat(percentage),
                deployGas: deployGas,
                status: status
            });
            
            const paddedName = contractName.padEnd(27);
            const paddedSize = sizeBytes.toString().padStart(10);
            const paddedPct = (percentage + "%").padStart(10);
            
            console.log(`${paddedName} ${paddedSize}      ${paddedPct}     ${status}`);
        } catch (e) {
            console.log(`${contractName.padEnd(27)} (not found or error)`);
        }
    }

    console.log("\n─────────────────────────────────────────────────────────────────");
    console.log("DEPLOYMENT GAS ESTIMATES");
    console.log("─────────────────────────────────────────────────────────────────\n");

    console.log("Contract                    Est. Deploy Gas    Est. Cost (@ 20 gwei)");
    console.log("─────────────────────────── ─────────────────── ─────────────────────");

    for (const r of results) {
        const ethCost = ethers.formatEther(r.deployGas * 20000000000n);
        const paddedName = r.name.padEnd(27);
        const paddedGas = r.deployGas.toString().padStart(15);
        
        console.log(`${paddedName} ${paddedGas}       ${parseFloat(ethCost).toFixed(4)} ETH`);
    }

    const totalEthCost = ethers.formatEther(totalDeploymentGas * 20000000000n);
    console.log("─────────────────────────────────────────────────────────────────");
    console.log(`TOTAL                       ${totalDeploymentGas.toString().padStart(15)}       ${parseFloat(totalEthCost).toFixed(4)} ETH`);

    // Optimization recommendations
    console.log(`

╔═══════════════════════════════════════════════════════════════╗
║              OPTIMIZATION RECOMMENDATIONS                      ║
╚═══════════════════════════════════════════════════════════════╝

1. COMPILER SETTINGS (Current: runs=200, viaIR=true)
   ─────────────────────────────────────────────────
   Current settings are good for moderate optimization.
   
   For SMALLER bytecode (lower deployment cost):
   • Set runs: 1 (prioritizes deployment over runtime)
   • Keep viaIR: true (better optimization)
   
   For CHEAPER runtime (lower function call cost):
   • Set runs: 10000 (prioritizes runtime over deployment)
   • Add optimizer.details.yul: true

2. CODE OPTIMIZATIONS
   ─────────────────────────────────────────────────
`);

    // Check for common gas optimizations
    const optimizations = await analyzeCodeOptimizations();
    for (const opt of optimizations) {
        console.log(`   ${opt}`);
    }

    console.log(`
3. STORAGE OPTIMIZATIONS
   ─────────────────────────────────────────────────
   • Pack structs: Put smaller types together (uint8, bool, address)
   • Use mappings over arrays for large datasets
   • Use events instead of storage for historical data
   • Consider using SSTORE2 for large immutable data

4. FUNCTION OPTIMIZATIONS
   ─────────────────────────────────────────────────
   • Use external instead of public where possible
   • Use calldata instead of memory for readonly params
   • Batch operations to save on base transaction costs
   • Use unchecked blocks for safe arithmetic
   • Short-circuit conditions (cheap checks first)

5. PROXY PATTERN BENEFITS (Already using UUPS)
   ─────────────────────────────────────────────────
   ✅ UUPS is most gas-efficient upgrade pattern
   • Implementation cost paid once
   • Proxy only ~300 bytes
   • Upgrade logic in implementation saves proxy size
`);

    // Write optimization report
    const report = {
        timestamp: new Date().toISOString(),
        contracts: results,
        totalDeploymentGas: totalDeploymentGas.toString(),
        recommendations: {
            compilerSettings: {
                current: { runs: 200, viaIR: true },
                forSmaller: { runs: 1, viaIR: true },
                forCheaperRuntime: { runs: 10000, viaIR: true }
            }
        }
    };
    
    const reportPath = "reports/gas-analysis.json";
    fs.mkdirSync(path.dirname(reportPath), { recursive: true });
    fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
    console.log(`\n📁 Report saved to: ${reportPath}`);
}

async function analyzeCodeOptimizations() {
    const recommendations = [];
    
    // Check AMTTPCore for common patterns
    try {
        const coreCode = fs.readFileSync("contracts/AMTTPCore.sol", "utf8");
        
        if (coreCode.includes("string memory") && !coreCode.includes("string calldata")) {
            recommendations.push("• Use 'calldata' instead of 'memory' for string params in external functions");
        }
        
        if (coreCode.includes("require(") && coreCode.split("require(").length > 10) {
            recommendations.push("• Consider custom errors instead of require strings (saves ~50 bytes each)");
        }
        
        if (!coreCode.includes("unchecked")) {
            recommendations.push("• Add 'unchecked' blocks for safe arithmetic (saves ~20 gas per operation)");
        }
        
        if (coreCode.includes("public") && !coreCode.includes("external")) {
            recommendations.push("• Change 'public' to 'external' for functions not called internally");
        }

        // Check for storage packing opportunities
        if (coreCode.includes("uint256") && coreCode.includes("bool") && coreCode.includes("address")) {
            recommendations.push("• Review struct packing: group uint8/bool/address together (32 byte slots)");
        }
        
    } catch (e) {
        recommendations.push("• Could not analyze source code");
    }

    // Check NFT contract
    try {
        const nftCode = fs.readFileSync("contracts/AMTTPNFT.sol", "utf8");
        
        if (nftCode.includes("keccak256(abi.encodePacked")) {
            recommendations.push("• Use abi.encode instead of abi.encodePacked for hashing (safer)");
        }
        
    } catch (e) {}

    if (recommendations.length === 0) {
        recommendations.push("✅ No obvious optimizations found - code looks good!");
    }

    return recommendations;
}

main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
