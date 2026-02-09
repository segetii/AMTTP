/**
 * AMTTP zkNAF Verifier Deployment Script
 * 
 * Deploys Groth16 verifier contracts for:
 * - Sanctions Non-Membership Proof
 * - Risk Score Range Proof  
 * - KYC Credential Proof
 * 
 * These verifiers enable on-chain verification of ZK proofs
 * for FCA-compliant privacy-preserving compliance checks.
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

// Deployment configuration
const DEPLOYMENT_CONFIG = {
  gasLimit: 5000000,
  confirmations: 2,
};

async function main() {
  console.log(`
╔══════════════════════════════════════════════════════════════════════╗
║           AMTTP zkNAF Verifier Deployment                            ║
╠══════════════════════════════════════════════════════════════════════╣
║  Deploying Groth16 verifiers for on-chain proof verification         ║
╚══════════════════════════════════════════════════════════════════════╝
`);

  const [deployer] = await hre.ethers.getSigners();
  console.log(`Deployer: ${deployer.address}`);
  
  const balance = await hre.ethers.provider.getBalance(deployer.address);
  console.log(`Balance: ${hre.ethers.formatEther(balance)} ETH\n`);

  const network = hre.network.name;
  console.log(`Network: ${network}\n`);

  const deployments = {};

  // ═══════════════════════════════════════════════════════════════════════════
  // Deploy Sanctions Verifier
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('─'.repeat(70));
  console.log('Deploying: SanctionsNonMembershipVerifier');
  console.log('─'.repeat(70));
  
  try {
    const SanctionsVerifier = await hre.ethers.getContractFactory('contracts/zknaf/sanctions_non_membership_verifier.sol:Groth16Verifier');
    const sanctionsVerifier = await SanctionsVerifier.deploy({
      gasLimit: DEPLOYMENT_CONFIG.gasLimit,
    });
    await sanctionsVerifier.waitForDeployment();
    const sanctionsAddress = await sanctionsVerifier.getAddress();
    
    console.log(`  ✅ Deployed at: ${sanctionsAddress}`);
    deployments.sanctionsVerifier = sanctionsAddress;
  } catch (error) {
    console.error(`  ❌ Failed: ${error.message}`);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Deploy Risk Verifier
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '─'.repeat(70));
  console.log('Deploying: RiskRangeProofVerifier');
  console.log('─'.repeat(70));
  
  try {
    const RiskVerifier = await hre.ethers.getContractFactory('contracts/zknaf/risk_range_proof_verifier.sol:Groth16Verifier');
    const riskVerifier = await RiskVerifier.deploy({
      gasLimit: DEPLOYMENT_CONFIG.gasLimit,
    });
    await riskVerifier.waitForDeployment();
    const riskAddress = await riskVerifier.getAddress();
    
    console.log(`  ✅ Deployed at: ${riskAddress}`);
    deployments.riskVerifier = riskAddress;
  } catch (error) {
    console.error(`  ❌ Failed: ${error.message}`);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Deploy KYC Verifier
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '─'.repeat(70));
  console.log('Deploying: KYCCredentialVerifier');
  console.log('─'.repeat(70));
  
  try {
    const KYCVerifier = await hre.ethers.getContractFactory('contracts/zknaf/kyc_credential_verifier.sol:Groth16Verifier');
    const kycVerifier = await KYCVerifier.deploy({
      gasLimit: DEPLOYMENT_CONFIG.gasLimit,
    });
    await kycVerifier.waitForDeployment();
    const kycAddress = await kycVerifier.getAddress();
    
    console.log(`  ✅ Deployed at: ${kycAddress}`);
    deployments.kycVerifier = kycAddress;
  } catch (error) {
    console.error(`  ❌ Failed: ${error.message}`);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Save Deployment Info
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '═'.repeat(70));
  console.log('DEPLOYMENT SUMMARY');
  console.log('═'.repeat(70));
  
  const deploymentInfo = {
    network,
    deployer: deployer.address,
    timestamp: new Date().toISOString(),
    contracts: deployments,
  };
  
  const deploymentPath = path.join(__dirname, '..', 'deployments', `zknaf-verifiers-${network}.json`);
  
  // Ensure deployments directory exists
  const deploymentsDir = path.dirname(deploymentPath);
  if (!fs.existsSync(deploymentsDir)) {
    fs.mkdirSync(deploymentsDir, { recursive: true });
  }
  
  fs.writeFileSync(deploymentPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\nDeployment info saved to: ${deploymentPath}`);
  
  console.log('\nVerifier Addresses:');
  console.log(`  Sanctions: ${deployments.sanctionsVerifier || 'NOT DEPLOYED'}`);
  console.log(`  Risk:      ${deployments.riskVerifier || 'NOT DEPLOYED'}`);
  console.log(`  KYC:       ${deployments.kycVerifier || 'NOT DEPLOYED'}`);
  
  // ═══════════════════════════════════════════════════════════════════════════
  // Generate Integration Code
  // ═══════════════════════════════════════════════════════════════════════════
  console.log('\n' + '─'.repeat(70));
  console.log('Integration Code (add to AMTTPCoreZkNAF.sol):');
  console.log('─'.repeat(70));
  
  console.log(`
// Verifier addresses for ${network}
address constant SANCTIONS_VERIFIER = ${deployments.sanctionsVerifier ? `address(${deployments.sanctionsVerifier})` : '0x0'};
address constant RISK_VERIFIER = ${deployments.riskVerifier ? `address(${deployments.riskVerifier})` : '0x0'};
address constant KYC_VERIFIER = ${deployments.kycVerifier ? `address(${deployments.kycVerifier})` : '0x0'};
`);

  console.log('\n✅ Deployment complete!\n');
  
  return deployments;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
