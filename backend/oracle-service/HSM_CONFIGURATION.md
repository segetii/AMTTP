# AMTTP Oracle HSM Configuration Guide

## Overview

This guide covers configuring Hardware Security Module (HSM) integration for production oracle signing. The oracle private keys should **NEVER** exist outside of an HSM in production.

## Supported HSM Backends

| Backend | Key Type | Status | Use Case |
|---------|----------|--------|----------|
| AWS KMS | SECP256K1 | ✅ Production Ready | AWS-native deployments |
| HashiCorp Vault | Transit Engine | ✅ Production Ready | Multi-cloud / On-prem |
| Local Signer | In-memory | ⚠️ Dev Only | Local testing |

---

## Option 1: AWS KMS Configuration

### Step 1: Create SECP256K1 Keys in AWS KMS

```bash
# Create 3 oracle signing keys (for 2-of-3 threshold)
aws kms create-key \
  --key-spec ECC_SECG_P256K1 \
  --key-usage SIGN_VERIFY \
  --description "AMTTP Oracle Key 1" \
  --tags Key=Environment,Value=production Key=Service,Value=amttp-oracle

aws kms create-key \
  --key-spec ECC_SECG_P256K1 \
  --key-usage SIGN_VERIFY \
  --description "AMTTP Oracle Key 2" \
  --tags Key=Environment,Value=production Key=Service,Value=amttp-oracle

aws kms create-key \
  --key-spec ECC_SECG_P256K1 \
  --key-usage SIGN_VERIFY \
  --description "AMTTP Oracle Key 3" \
  --tags Key=Environment,Value=production Key=Service,Value=amttp-oracle
```

### Step 2: Set Key Policies

Create a key policy that only allows the oracle service IAM role to sign:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Allow Oracle Service to Sign",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::ACCOUNT_ID:role/amttp-oracle-service"
      },
      "Action": [
        "kms:Sign",
        "kms:GetPublicKey"
      ],
      "Resource": "*"
    }
  ]
}
```

### Step 3: Configure Environment Variables

```bash
# .env.production
NODE_ENV=production

# AWS Configuration
AWS_REGION=eu-west-1

# Oracle KMS Keys (from Step 1)
ORACLE_KMS_KEY_1=arn:aws:kms:eu-west-1:123456789012:key/abc123-def456
ORACLE_KMS_KEY_2=arn:aws:kms:eu-west-1:123456789012:key/ghi789-jkl012
ORACLE_KMS_KEY_3=arn:aws:kms:eu-west-1:123456789012:key/mno345-pqr678

# Threshold (2-of-3 recommended)
ORACLE_THRESHOLD=2
```

### Step 4: IAM Role for EC2/ECS

If running on EC2 or ECS, attach this IAM policy to the instance/task role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "kms:Sign",
        "kms:GetPublicKey"
      ],
      "Resource": [
        "arn:aws:kms:eu-west-1:123456789012:key/abc123-def456",
        "arn:aws:kms:eu-west-1:123456789012:key/ghi789-jkl012",
        "arn:aws:kms:eu-west-1:123456789012:key/mno345-pqr678"
      ]
    }
  ]
}
```

---

## Option 2: HashiCorp Vault Configuration

### Step 1: Enable Transit Engine

```bash
vault secrets enable transit
```

### Step 2: Create Oracle Signing Keys

```bash
# Create 3 oracle keys with ECDSA-P256 (or use secp256k1 plugin)
vault write transit/keys/amttp-oracle-1 type=ecdsa-p256
vault write transit/keys/amttp-oracle-2 type=ecdsa-p256
vault write transit/keys/amttp-oracle-3 type=ecdsa-p256
```

### Step 3: Create Policy

```hcl
# amttp-oracle-policy.hcl
path "transit/sign/amttp-oracle-*" {
  capabilities = ["update"]
}

path "transit/keys/amttp-oracle-*" {
  capabilities = ["read"]
}
```

Apply the policy:

```bash
vault policy write amttp-oracle amttp-oracle-policy.hcl
```

### Step 4: Create AppRole for Service

```bash
vault auth enable approle

vault write auth/approle/role/amttp-oracle \
  token_policies="amttp-oracle" \
  token_ttl=1h \
  token_max_ttl=4h \
  secret_id_ttl=24h

# Get Role ID
vault read auth/approle/role/amttp-oracle/role-id

# Generate Secret ID
vault write -f auth/approle/role/amttp-oracle/secret-id
```

### Step 5: Configure Environment Variables

```bash
# .env.production
NODE_ENV=production

# Vault Configuration
VAULT_ADDR=https://vault.internal.amttp.io:8200
VAULT_ROLE_ID=abc123-def456-ghi789
VAULT_SECRET_ID=jkl012-mno345-pqr678

# Or use token auth (less secure)
# VAULT_TOKEN=hvs.xxxxxxxxxxxxx

# Transit mount point (default: transit)
VAULT_TRANSIT_MOUNT=transit

# Key names (must match Step 2)
ORACLE_VAULT_KEY_1=amttp-oracle-1
ORACLE_VAULT_KEY_2=amttp-oracle-2
ORACLE_VAULT_KEY_3=amttp-oracle-3

# Threshold
ORACLE_THRESHOLD=2
```

---

## Key Rotation Procedure

### Every 90 Days (Required)

1. **Generate new key** in HSM
2. **Register new oracle** on smart contract:
   ```solidity
   await amttpCore.addOracle(newOracleAddress);
   ```
3. **Update environment** with new key ID
4. **Test signing** with new key
5. **Remove old oracle** from contract:
   ```solidity
   await amttpCore.removeOracle(oldOracleAddress);
   ```
6. **Disable/Delete old key** in HSM after grace period

### Rotation Script

```bash
#!/bin/bash
# rotate-oracle-key.sh

NEW_KEY_ID=$(aws kms create-key \
  --key-spec ECC_SECG_P256K1 \
  --key-usage SIGN_VERIFY \
  --output text --query KeyMetadata.KeyId)

echo "New Key ID: $NEW_KEY_ID"
echo "Update ORACLE_KMS_KEY_X in .env.production"
echo "Then redeploy and register on contract"
```

---

## Testing HSM Connection

```bash
# Test the HSM connection
cd backend/oracle-service
NODE_ENV=production node hsm-signer.js
```

Expected output:
```
Created 3 AWS KMS oracle signers
Config: { threshold: 2, signatureValiditySeconds: 300, environment: 'production' }
Oracle Addresses: [ '0x...', '0x...', '0x...' ]
```

---

## Registering Oracles on Smart Contract

After HSM setup, register the oracle addresses on the AMTTP contract:

```javascript
const { ethers } = require('ethers');
const { OracleSigningService } = require('./hsm-signer');

async function registerOracles() {
    const service = new OracleSigningService();
    const addresses = await service.getOracleAddresses();
    
    const provider = new ethers.JsonRpcProvider(process.env.RPC_URL);
    const wallet = new ethers.Wallet(process.env.ADMIN_PRIVATE_KEY, provider);
    
    const amttp = new ethers.Contract(
        process.env.AMTTP_ADDRESS,
        ['function addOracle(address oracle)', 'function setOracleThreshold(uint256 threshold)'],
        wallet
    );
    
    // Add each oracle
    for (const addr of addresses) {
        console.log(`Adding oracle: ${addr}`);
        await amttp.addOracle(addr);
    }
    
    // Set threshold
    console.log(`Setting threshold to ${service.getConfig().threshold}`);
    await amttp.setOracleThreshold(service.getConfig().threshold);
    
    console.log('✅ Oracles registered!');
}

registerOracles().catch(console.error);
```

---

## Security Checklist

- [ ] HSM keys created with SECP256K1 curve
- [ ] IAM/Policy restricts access to oracle service only
- [ ] 2-of-3 (or higher) threshold configured
- [ ] Key rotation schedule documented (90 days)
- [ ] Separate keys for testnet vs mainnet
- [ ] Oracle addresses registered on smart contract
- [ ] Monitoring alerts for signing failures
- [ ] Backup keys stored in separate HSM/region
- [ ] Incident response plan for key compromise

---

## Troubleshooting

### "Production requires at least 2 oracle signers"
Ensure all `ORACLE_KMS_KEY_*` or `ORACLE_VAULT_KEY_*` environment variables are set.

### "KMSClient is undefined"
Install AWS SDK: `npm install @aws-sdk/client-kms`

### "Vault authentication failed"
Check `VAULT_ADDR` is reachable and `VAULT_TOKEN` or AppRole credentials are valid.

### "Invalid signature recovered"
Ensure the KMS key is `ECC_SECG_P256K1` (not P-256). Ethereum uses secp256k1.

---

## Related Files

- `hsm-signer.js` - HSM signing implementation
- `src/oracle/oracle.service.ts` - Oracle API integration
- `contracts/AMTTPCoreSecure.sol` - Multi-oracle verification on-chain
- `docs/SECURITY_REQUIREMENTS.md` - Security requirements

---

*Last Updated: January 2026*
*Status: Production Ready*
