/**
 * Deploy ZkNAFVerifierRouter
 * 
 * Deploys the router contract that unifies all three ZK verifiers.
 */

const hre = require('hardhat');
const fs = require('fs');
const path = require('path');

async function main() {
  console.log('\nDeploying ZkNAFVerifierRouter...\n');

  const [deployer] = await hre.ethers.getSigners();
  const network = hre.network.name;
  
  // Load verifier addresses
  const verifiersPath = path.join(__dirname, '..', 'deployments', `zknaf-verifiers-${network}.json`);
  if (!fs.existsSync(verifiersPath)) {
    throw new Error(`Verifier deployment not found: ${verifiersPath}`);
  }
  
  const verifiers = JSON.parse(fs.readFileSync(verifiersPath, 'utf8'));
  console.log('Loaded verifier addresses:');
  console.log(`  Sanctions: ${verifiers.contracts.sanctionsVerifier}`);
  console.log(`  Risk:      ${verifiers.contracts.riskVerifier}`);
  console.log(`  KYC:       ${verifiers.contracts.kycVerifier}`);
  
  // Deploy router
  const Router = await hre.ethers.getContractFactory('ZkNAFVerifierRouter');
  const router = await Router.deploy(
    verifiers.contracts.sanctionsVerifier,
    verifiers.contracts.riskVerifier,
    verifiers.contracts.kycVerifier
  );
  await router.waitForDeployment();
  const routerAddress = await router.getAddress();
  
  console.log(`\n✅ ZkNAFVerifierRouter deployed at: ${routerAddress}`);
  
  // Update deployment file
  verifiers.contracts.router = routerAddress;
  verifiers.routerDeployedAt = new Date().toISOString();
  fs.writeFileSync(verifiersPath, JSON.stringify(verifiers, null, 2));
  
  console.log(`\nDeployment info updated: ${verifiersPath}`);
  
  console.log(`
═══════════════════════════════════════════════════════════════════════
FULL zkNAF DEPLOYMENT COMPLETE
═══════════════════════════════════════════════════════════════════════

Network: ${network}

Contract Addresses:
  Sanctions Verifier: ${verifiers.contracts.sanctionsVerifier}
  Risk Verifier:      ${verifiers.contracts.riskVerifier}
  KYC Verifier:       ${verifiers.contracts.kycVerifier}
  Router:             ${routerAddress}

The router contract provides unified access to all verifiers with:
  - verifySanctionsProof()
  - verifyRiskProof()
  - verifyKYCProof()
  - verifyFullCompliance() - all three in one transaction
`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
