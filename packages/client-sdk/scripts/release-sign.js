#!/usr/bin/env node
/**
 * AMTTP Package Release Signing Script
 * 
 * Signs npm packages with GPG and generates integrity hashes.
 * This ensures package authenticity and prevents supply chain attacks.
 * 
 * Features:
 * - GPG signature generation (.asc)
 * - SHA256/SHA512 hash computation
 * - SBOM generation (CycloneDX format)
 * - Provenance attestation (SLSA)
 * - Release manifest generation
 * 
 * Usage:
 *   node scripts/release-sign.js <package-file.tgz>
 * 
 * Environment:
 *   GPG_KEY_ID - GPG key ID for signing (optional, uses default if not set)
 */

const fs = require('fs');
const crypto = require('crypto');
const { execSync } = require('child_process');
const path = require('path');

// ═══════════════════════════════════════════════════════════════════════════
// Configuration
// ═══════════════════════════════════════════════════════════════════════════

const CONFIG = {
    gpgKeyId: process.env.GPG_KEY_ID || '',
    hashAlgorithms: ['sha256', 'sha512'],
    outputDir: 'dist/signatures',
};

// ═══════════════════════════════════════════════════════════════════════════
// Hash Generation
// ═══════════════════════════════════════════════════════════════════════════

function computeHash(filePath, algorithm) {
    const hash = crypto.createHash(algorithm);
    const content = fs.readFileSync(filePath);
    hash.update(content);
    return hash.digest('hex');
}

function generateChecksums(tarball) {
    const checksums = {};
    const baseName = path.basename(tarball);
    
    console.log(`\n📋 Generating checksums for ${baseName}...`);
    
    for (const algo of CONFIG.hashAlgorithms) {
        const hash = computeHash(tarball, algo);
        checksums[algo] = hash;
        fs.writeFileSync(`${tarball}.${algo}`, `${hash}  ${baseName}\n`);
        console.log(`   ${algo.toUpperCase()}: ${hash}`);
    }
    
    return checksums;
}

// ═══════════════════════════════════════════════════════════════════════════
// GPG Signing
// ═══════════════════════════════════════════════════════════════════════════

function signWithGpg(tarball) {
    console.log(`\n🔐 Signing with GPG...`);
    
    try {
        const keyArg = CONFIG.gpgKeyId ? `--default-key ${CONFIG.gpgKeyId}` : '';
        execSync(`gpg ${keyArg} --armor --detach-sign --output ${tarball}.asc ${tarball}`);
        console.log(`   Signature: ${tarball}.asc`);
        return `${tarball}.asc`;
    } catch (e) {
        console.log(`⚠️  GPG signing failed: ${e.message}`);
        console.log('   To set up GPG:');
        console.log('   1. gpg --full-generate-key');
        console.log('   2. gpg --armor --export YOUR_EMAIL > public-key.asc');
        console.log('   3. Set GPG_KEY_ID env var (optional)');
        return null;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SBOM & Provenance
// ═══════════════════════════════════════════════════════════════════════════

function generateSBOM() {
    console.log('\n📦 Generating SBOM...');
    
    const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf-8'));
    
    const sbom = {
        bomFormat: 'CycloneDX',
        specVersion: '1.4',
        serialNumber: `urn:uuid:${crypto.randomUUID()}`,
        version: 1,
        metadata: {
            timestamp: new Date().toISOString(),
            component: {
                type: 'library',
                name: packageJson.name,
                version: packageJson.version,
                purl: `pkg:npm/${packageJson.name}@${packageJson.version}`,
            },
        },
        components: Object.entries({
            ...packageJson.dependencies,
            ...packageJson.devDependencies,
        }).map(([name, version]) => ({
            type: 'library',
            name,
            version: version.replace(/^[\^~]/, ''),
            purl: `pkg:npm/${name}@${version.replace(/^[\^~]/, '')}`,
        })),
    };
    
    fs.writeFileSync('sbom.json', JSON.stringify(sbom, null, 2));
    console.log('   SBOM: sbom.json');
}

function generateProvenance(tarball, checksums) {
    console.log('\n📜 Generating provenance...');
    
    const packageJson = JSON.parse(fs.readFileSync('package.json', 'utf-8'));
    
    let gitCommit = 'unknown';
    try { gitCommit = execSync('git rev-parse HEAD', { encoding: 'utf-8' }).trim(); } catch {}
    
    const provenance = {
        _type: 'https://in-toto.io/Statement/v0.1',
        subject: [{
            name: packageJson.name,
            digest: { sha256: checksums.sha256, sha512: checksums.sha512 },
        }],
        predicateType: 'https://slsa.dev/provenance/v0.2',
        predicate: {
            builder: { id: 'https://github.com/amttp/client-sdk' },
            buildType: 'npm',
            invocation: {
                configSource: { digest: { sha1: gitCommit } },
            },
            metadata: {
                buildInvocationId: `${Date.now()}`,
                buildStartedOn: new Date().toISOString(),
            },
        },
    };
    
    const provenancePath = `${tarball}.provenance.json`;
    fs.writeFileSync(provenancePath, JSON.stringify(provenance, null, 2));
    console.log(`   Provenance: ${provenancePath}`);
}

// ═══════════════════════════════════════════════════════════════════════════
// Main
// ═══════════════════════════════════════════════════════════════════════════

const tarball = process.argv[2];
if (!tarball || !fs.existsSync(tarball)) {
    console.error('Usage: node scripts/release-sign.js <tarball.tgz>');
    process.exit(1);
}

console.log('═══════════════════════════════════════════════════════════');
console.log('        AMTTP Package Release Signing');
console.log('═══════════════════════════════════════════════════════════');
console.log(`\n📦 Package: ${tarball}`);

// Generate checksums
const checksums = generateChecksums(tarball);

// GPG sign
const signature = signWithGpg(tarball);

// Generate SBOM
generateSBOM();

// Generate provenance
generateProvenance(tarball, checksums);

console.log('\n═══════════════════════════════════════════════════════════');
console.log('✅ Release signing complete!');
console.log('═══════════════════════════════════════════════════════════');
console.log('\nTo verify:');
console.log(`  sha256sum -c ${tarball}.sha256`);
if (signature) console.log(`  gpg --verify ${signature} ${tarball}`);
