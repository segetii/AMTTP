# AMTTP Package Signing Guide

## Overview

This guide documents how to sign and verify AMTTP npm packages to ensure supply chain security and package authenticity.

## Why Package Signing?

- **Authenticity**: Verify packages come from trusted AMTTP maintainers
- **Integrity**: Detect tampering or corruption
- **Provenance**: Track build origin and reproducibility
- **Compliance**: Meet security audit requirements

## Signing Process

### 1. Setup GPG Key (One-Time)

```bash
# Generate a GPG key
gpg --full-generate-key

# Choose: RSA and RSA, 4096 bits, key does not expire
# Enter your name and email (use your @amttp.io email)

# List your keys
gpg --list-secret-keys --keyid-format LONG

# Export your public key (share this)
gpg --armor --export YOUR_EMAIL > amttp-signing-key.pub
```

### 2. Configure Environment

```bash
# Set your GPG key ID
export GPG_KEY_ID="ABCD1234EFGH5678"

# For CI, set in GitHub Secrets:
# - GPG_PRIVATE_KEY (base64 encoded)
# - GPG_PASSPHRASE
```

### 3. Sign a Release

```bash
cd packages/client-sdk

# Build the package
npm run build

# Create signed tarball
npm pack
node scripts/release-sign.js amttp-client-sdk-1.0.0.tgz
```

This generates:
- `*.tgz.sha256` - SHA256 checksum
- `*.tgz.sha512` - SHA512 checksum  
- `*.tgz.asc` - GPG signature
- `*.tgz.provenance.json` - SLSA provenance
- `sbom.json` - Software Bill of Materials

### 4. Publish with npm Provenance

```bash
# npm native provenance (npm 9.5+)
npm publish --provenance
```

## Verification Process

### Verify Checksum

```bash
# Verify SHA256
sha256sum -c amttp-client-sdk-1.0.0.tgz.sha256

# Or manually
echo "EXPECTED_HASH  amttp-client-sdk-1.0.0.tgz" | sha256sum -c
```

### Verify GPG Signature

```bash
# Import AMTTP public key (one-time)
curl -sL https://amttp.io/keys/signing-key.pub | gpg --import

# Verify signature
gpg --verify amttp-client-sdk-1.0.0.tgz.asc amttp-client-sdk-1.0.0.tgz
```

Expected output:
```
gpg: Signature made Mon Jan 01 12:00:00 2026 UTC
gpg: Good signature from "AMTTP Release Team <releases@amttp.io>"
```

### Verify npm Integrity

```bash
# Check npm package integrity
npm pack @amttp/client-sdk --dry-run

# Verify installed package
npm audit signatures
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/publish.yml
name: Publish Package

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write  # Required for npm provenance
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'
      
      # Import GPG key
      - name: Import GPG key
        run: |
          echo "${{ secrets.GPG_PRIVATE_KEY }}" | base64 -d | gpg --import
        
      - name: Build & Sign
        run: |
          cd packages/client-sdk
          npm ci
          npm run build
          npm pack
          node scripts/release-sign.js *.tgz
      
      - name: Publish with provenance
        run: npm publish --provenance
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
      
      - name: Upload signatures
        uses: actions/upload-artifact@v4
        with:
          name: package-signatures
          path: |
            packages/client-sdk/*.sha256
            packages/client-sdk/*.sha512
            packages/client-sdk/*.asc
            packages/client-sdk/*.provenance.json
            packages/client-sdk/sbom.json
```

## Public Keys

### Current Signing Key

```
Fingerprint: XXXX XXXX XXXX XXXX XXXX  XXXX XXXX XXXX XXXX XXXX
Key ID: ABCD1234EFGH5678
Created: 2026-01-01
Expires: Never
Email: releases@amttp.io
```

Download: https://amttp.io/keys/signing-key.pub

### Key Rotation Policy

- Signing keys are rotated annually
- Old keys remain valid for verification
- New keys are announced via:
  - GitHub releases
  - npm package README
  - Official blog

## SBOM (Software Bill of Materials)

Each release includes `sbom.json` in CycloneDX format listing all dependencies.

```bash
# View SBOM
cat sbom.json | jq '.components[] | {name, version}'
```

## Provenance Attestation

Provenance files (`.provenance.json`) follow SLSA v0.2 format and include:
- Build environment
- Git commit SHA
- Build timestamp
- Package digests

## Troubleshooting

### "GPG signing failed"

1. Ensure GPG is installed: `gpg --version`
2. Check key is available: `gpg --list-secret-keys`
3. Set key ID: `export GPG_KEY_ID=YOUR_KEY_ID`

### "Bad signature"

1. Ensure you have the correct public key
2. Check package wasn't modified after signing
3. Verify key hasn't been revoked

### "npm audit signatures failed"

1. Package may predate npm provenance
2. Check npm version (requires 9.5+)
3. Verify registry supports provenance

## Security Contacts

- Security issues: security@amttp.io
- Key questions: keys@amttp.io
- GPG key fingerprint verification: Call +44 XXXX XXXXXX

---

*Last updated: January 2026*
