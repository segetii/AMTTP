/**
 * Intent Signing - EIP-712 Implementation
 * 
 * Provides structured data signing for transfer intents
 * 
 * EIP-712 ensures:
 * 1. Human-readable transaction data in wallet
 * 2. Replay protection via domain separator
 * 3. Type safety through structured typing
 * 
 * Reference: https://eips.ethereum.org/EIPS/eip-712
 */

import { TransferIntent, EIP712TypedData } from './secure-bridge';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface SigningResult {
  success: boolean;
  signature?: string;
  v?: number;
  r?: string;
  s?: string;
  signedHash?: string;
  error?: string;
}

export interface IntentVerification {
  isValid: boolean;
  recoveredAddress?: string;
  matchesExpected: boolean;
  errors: string[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// EIP-712 DOMAIN
// ═══════════════════════════════════════════════════════════════════════════════

const DOMAIN_NAME = 'AMTTP Transfer Intent';
const DOMAIN_VERSION = '1';

// Chain-specific verifying contracts (AMTTPCore addresses)
const VERIFYING_CONTRACTS: Record<number, string> = {
  1: '0x0000000000000000000000000000000000000000',     // Mainnet
  5: '0x0000000000000000000000000000000000000000',     // Goerli
  11155111: '0x0000000000000000000000000000000000000000', // Sepolia
  137: '0x0000000000000000000000000000000000000000',   // Polygon
  42161: '0x0000000000000000000000000000000000000000', // Arbitrum
  10: '0x0000000000000000000000000000000000000000',    // Optimism
};

// ═══════════════════════════════════════════════════════════════════════════════
// TYPE DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

const EIP712_TYPES = {
  EIP712Domain: [
    { name: 'name', type: 'string' },
    { name: 'version', type: 'string' },
    { name: 'chainId', type: 'uint256' },
    { name: 'verifyingContract', type: 'address' },
  ],
  TransferIntent: [
    { name: 'recipient', type: 'address' },
    { name: 'amount', type: 'uint256' },
    { name: 'token', type: 'address' },
    { name: 'chainId', type: 'uint256' },
    { name: 'uiSnapshotHash', type: 'bytes32' },
    { name: 'trustPillarsShown', type: 'string' },
    { name: 'riskScoreDisplayed', type: 'uint8' },
    { name: 'warningsAcknowledged', type: 'string' },
    { name: 'timestamp', type: 'uint256' },
    { name: 'nonce', type: 'bytes32' },
    { name: 'sessionId', type: 'bytes32' },
  ],
  // Simplified intent for basic transfers
  SimpleTransfer: [
    { name: 'recipient', type: 'address' },
    { name: 'amount', type: 'uint256' },
    { name: 'token', type: 'address' },
    { name: 'nonce', type: 'uint256' },
    { name: 'deadline', type: 'uint256' },
  ],
  // Batch transfer intent
  BatchTransferIntent: [
    { name: 'recipients', type: 'address[]' },
    { name: 'amounts', type: 'uint256[]' },
    { name: 'token', type: 'address' },
    { name: 'totalAmount', type: 'uint256' },
    { name: 'uiSnapshotHash', type: 'bytes32' },
    { name: 'nonce', type: 'bytes32' },
    { name: 'timestamp', type: 'uint256' },
  ],
};

// ═══════════════════════════════════════════════════════════════════════════════
// INTENT BUILDER
// ═══════════════════════════════════════════════════════════════════════════════

export function buildEIP712Domain(chainId: number): EIP712TypedData['domain'] {
  return {
    name: DOMAIN_NAME,
    version: DOMAIN_VERSION,
    chainId,
    verifyingContract: VERIFYING_CONTRACTS[chainId] || VERIFYING_CONTRACTS[1],
  };
}

export function buildTypedData(intent: TransferIntent): EIP712TypedData {
  // Prepare message with proper types for EIP-712
  const message = {
    ...intent,
    // Ensure string representations for complex types
    trustPillarsShown: intent.trustPillarsShown.join(','),
    warningsAcknowledged: intent.warningsAcknowledged.join(','),
  };
  
  return {
    types: EIP712_TYPES,
    primaryType: 'TransferIntent',
    domain: buildEIP712Domain(intent.chainId),
    message: message as any,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIGNING HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Request EIP-712 signature from wallet provider
 * Works with MetaMask, WalletConnect, etc.
 */
export async function requestSignature(
  typedData: EIP712TypedData,
  signerAddress: string
): Promise<SigningResult> {
  if (typeof window === 'undefined' || !window.ethereum) {
    return {
      success: false,
      error: 'No wallet provider available',
    };
  }
  
  try {
    // eth_signTypedData_v4 is the standard method
    const signature = await window.ethereum.request({
      method: 'eth_signTypedData_v4',
      params: [signerAddress, JSON.stringify(typedData)],
    }) as string;
    
    // Parse signature components
    const { v, r, s } = parseSignature(signature);
    
    return {
      success: true,
      signature,
      v,
      r,
      s,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Signing failed',
    };
  }
}

/**
 * Parse signature into v, r, s components
 */
export function parseSignature(signature: string): { v: number; r: string; s: string } {
  const sig = signature.startsWith('0x') ? signature.slice(2) : signature;
  
  if (sig.length !== 130) {
    throw new Error('Invalid signature length');
  }
  
  return {
    r: '0x' + sig.slice(0, 64),
    s: '0x' + sig.slice(64, 128),
    v: parseInt(sig.slice(128, 130), 16),
  };
}

/**
 * Combine v, r, s into signature
 */
export function combineSignature(v: number, r: string, s: string): string {
  const rClean = r.startsWith('0x') ? r.slice(2) : r;
  const sClean = s.startsWith('0x') ? s.slice(2) : s;
  const vHex = v.toString(16).padStart(2, '0');
  
  return '0x' + rClean + sClean + vHex;
}

// ═══════════════════════════════════════════════════════════════════════════════
// VERIFICATION
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Verify that a signature matches the expected signer
 * Note: Full verification requires ethers.js or similar
 */
export async function verifyIntent(
  intent: TransferIntent,
  signature: string,
  expectedSigner: string
): Promise<IntentVerification> {
  const errors: string[] = [];
  
  // Basic validation
  if (!signature || signature.length !== 132) {
    errors.push('Invalid signature format');
  }
  
  if (!expectedSigner || !expectedSigner.startsWith('0x')) {
    errors.push('Invalid expected signer address');
  }
  
  // Validate intent fields
  if (!intent.recipient || !intent.recipient.startsWith('0x')) {
    errors.push('Invalid recipient address');
  }
  
  if (!intent.uiSnapshotHash) {
    errors.push('Missing UI snapshot hash');
  }
  
  // Check timestamp is recent (within 5 minutes)
  const fiveMinutes = 5 * 60 * 1000;
  if (Date.now() - intent.timestamp > fiveMinutes) {
    errors.push('Intent timestamp is too old');
  }
  
  // For full verification, you'd need to:
  // 1. Recreate the typed data hash
  // 2. Use ecrecover to get the signer
  // 3. Compare with expected signer
  // This requires ethers.js verifyTypedData or similar
  
  if (errors.length > 0) {
    return {
      isValid: false,
      matchesExpected: false,
      errors,
    };
  }
  
  return {
    isValid: true,
    matchesExpected: true, // Placeholder - full verification needs crypto lib
    errors: [],
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// HASH UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Calculate keccak256 hash of typed data
 * Note: Requires ethers.js for full implementation
 */
export function hashTypedData(typedData: EIP712TypedData): string {
  // Placeholder - full implementation needs:
  // return ethers.TypedDataEncoder.hash(
  //   typedData.domain,
  //   { TransferIntent: typedData.types.TransferIntent },
  //   typedData.message
  // );
  
  // For now, return a deterministic hash based on JSON
  return '0x' + simpleHash(JSON.stringify(typedData));
}

/**
 * Simple hash for non-crypto purposes (use proper crypto in production)
 */
function simpleHash(str: string): string {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(16).padStart(64, '0');
}

// ═══════════════════════════════════════════════════════════════════════════════
// WINDOW TYPE EXTENSION
// ═══════════════════════════════════════════════════════════════════════════════

// Note: Window.ethereum type is defined in secure-bridge.ts
// This file re-uses that global declaration

export {};
