/**
 * AMTTP Build-Time Integrity Hash Generator
 * 
 * Run this script during build/deployment to generate trusted hashes
 * for critical UI components. These hashes are registered with the
 * integrity service to detect runtime tampering.
 * 
 * Usage:
 *   npx ts-node scripts/generate-integrity-hashes.ts
 */

import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
// In Docker builds we run this script via ts-node in CommonJS mode.
// Avoid import.meta so it works consistently across Node/ts-node configurations.

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════════

const INTEGRITY_VERSION = "1.0.0";

// Components to hash
const CRITICAL_COMPONENTS = [
  {
    id: "secure-payment",
    files: [
      "src/components/SecurePayment.tsx",
      "src/lib/ui-integrity.ts",
    ],
  },
  {
    id: "transfer-page",
    files: [
      "src/app/transfer/page.tsx",
    ],
  },
  {
    id: "batch-page",
    files: [
      "src/app/batch/page.tsx",
    ],
  },
  {
    id: "wallet-connect",
    files: [
      "src/components/AppLayout.tsx",
    ],
  },
];

// Output paths
const OUTPUT_DIR = path.join(__dirname, "..", "public");
const HASHES_FILE = path.join(OUTPUT_DIR, "integrity-hashes.json");

// ═══════════════════════════════════════════════════════════════════════════════
// HASH GENERATION
// ═══════════════════════════════════════════════════════════════════════════════

interface ComponentHash {
  componentId: string;
  files: string[];
  fileHashes: Record<string, string>;
  combinedHash: string;
  version: string;
  generatedAt: string;
}

function sha256(content: string): string {
  return crypto.createHash("sha256").update(content).digest("hex");
}

function hashFile(filePath: string): string | null {
  try {
    const fullPath = path.join(__dirname, "..", filePath);
    const content = fs.readFileSync(fullPath, "utf-8");
    
    // Normalize content (remove comments, normalize whitespace)
    const normalized = content
      .replace(/\/\*[\s\S]*?\*\//g, "") // Remove block comments
      .replace(/\/\/.*$/gm, "")          // Remove line comments
      .replace(/\s+/g, " ")              // Normalize whitespace
      .trim();
    
    return sha256(normalized);
  } catch (error) {
    console.error(`Failed to hash file ${filePath}:`, error);
    return null;
  }
}

function generateComponentHash(component: typeof CRITICAL_COMPONENTS[0]): ComponentHash | null {
  const fileHashes: Record<string, string> = {};
  
  for (const file of component.files) {
    const hash = hashFile(file);
    if (hash === null) {
      console.warn(`Skipping component ${component.id}: missing file ${file}`);
      return null;
    }
    fileHashes[file] = hash;
  }
  
  // Combined hash of all file hashes
  const sortedHashes = Object.keys(fileHashes)
    .sort()
    .map(k => fileHashes[k])
    .join(":");
  
  const combinedHash = sha256(sortedHashes);
  
  return {
    componentId: component.id,
    files: component.files,
    fileHashes,
    combinedHash,
    version: INTEGRITY_VERSION,
    generatedAt: new Date().toISOString(),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// BUILD ARTIFACT
// ═══════════════════════════════════════════════════════════════════════════════

interface IntegrityManifest {
  version: string;
  generatedAt: string;
  components: ComponentHash[];
  buildHash: string;
}

function generateManifest(): IntegrityManifest {
  const components: ComponentHash[] = [];
  
  for (const component of CRITICAL_COMPONENTS) {
    const hash = generateComponentHash(component);
    if (hash) {
      components.push(hash);
      console.log(`✓ ${component.id}: ${hash.combinedHash.substring(0, 16)}...`);
    }
  }
  
  // Overall build hash
  const allHashes = components.map(c => c.combinedHash).sort().join(":");
  const buildHash = sha256(allHashes);
  
  return {
    version: INTEGRITY_VERSION,
    generatedAt: new Date().toISOString(),
    components,
    buildHash,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

function main() {
  console.log("═".repeat(60));
  console.log("  AMTTP Integrity Hash Generator");
  console.log("═".repeat(60));
  console.log(`Version: ${INTEGRITY_VERSION}`);
  console.log("");
  
  const manifest = generateManifest();
  
  console.log("");
  console.log(`Build Hash: ${manifest.buildHash}`);
  console.log(`Components: ${manifest.components.length}`);
  
  // Write manifest
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }
  
  fs.writeFileSync(HASHES_FILE, JSON.stringify(manifest, null, 2));
  console.log(`\nManifest written to: ${HASHES_FILE}`);
  
  // Generate registration script for integrity service
  const registrationScript = manifest.components.map(c => 
    `curl -X POST "http://localhost:8008/register-hash" \\
  -d "component_id=${c.componentId}" \\
  -d "hash_value=${c.combinedHash}" \\
  -d "version=${c.version}" \\
  -d "admin_key=\${INTEGRITY_ADMIN_KEY}"`
  ).join("\n\n");
  
  const scriptPath = path.join(OUTPUT_DIR, "register-hashes.sh");
  fs.writeFileSync(scriptPath, `#!/bin/bash\n# Auto-generated hash registration script\n\n${registrationScript}\n`);
  console.log(`Registration script: ${scriptPath}`);
  
  console.log("");
  console.log("═".repeat(60));
}

main();
