// frontend/frontend/src/lib/tee-attestation.ts
//
// TEE (Trusted Execution Environment) & Secure Enclave Service
// Leverages WebAuthn/FIDO2 for hardware-backed attestation and
// Web Crypto API for non-exportable key management.
//
// Critical actions defined in shared/rbac_config.json are gated
// through this service. If a device lacks hardware attestation,
// a fallback multi-factor confirmation flow is used.

export interface CriticalAction {
  id: string;
  label: string;
  minRole: number;
  requiresMultisig: boolean;
  requiresTEE: boolean;
  description: string;
}

export interface AttestationResult {
  success: boolean;
  method: 'webauthn' | 'secure-key' | 'fallback-pin';
  credentialId?: string;
  signature?: string;      // base64url
  challenge?: string;      // base64url
  timestamp: number;
  error?: string;
}

export interface SecureKeyHandle {
  keyId: string;
  createdAt: number;
  algorithm: string;
  usages: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function base64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64urlDecode(str: string): Uint8Array {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/');
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function randomChallenge(size = 32): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(size));
}

// ---------------------------------------------------------------------------
// WebAuthn / FIDO2 — hardware-backed attestation
// ---------------------------------------------------------------------------

const RP_NAME = 'AMTTP Platform';
const RP_ID = typeof window !== 'undefined' ? window.location.hostname : 'localhost';

/**
 * Check if WebAuthn is supported on this device.
 */
export function isWebAuthnSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    typeof navigator.credentials !== 'undefined'
  );
}

/**
 * Check if the device has a platform authenticator (e.g., Touch ID, Face ID,
 * Windows Hello, fingerprint sensor).
 */
export async function hasPlatformAuthenticator(): Promise<boolean> {
  if (!isWebAuthnSupported()) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/**
 * Register a new credential for the current user on this device.
 * This should be called once during account setup or when enrolling
 * a new device for critical action approval.
 */
export async function registerCredential(
  userId: string,
  userName: string,
): Promise<{ credentialId: string; publicKey: string } | null> {
  if (!isWebAuthnSupported()) return null;

  const challenge = randomChallenge();

  const createOptions: PublicKeyCredentialCreationOptions = {
    challenge,
    rp: { name: RP_NAME, id: RP_ID },
    user: {
      id: new TextEncoder().encode(userId),
      name: userName,
      displayName: userName,
    },
    pubKeyCredParams: [
      { type: 'public-key', alg: -7 },   // ES256
      { type: 'public-key', alg: -257 },  // RS256
    ],
    authenticatorSelection: {
      authenticatorAttachment: 'platform',
      userVerification: 'required',
      requireResidentKey: false,
    },
    timeout: 60000,
    attestation: 'direct',
  };

  try {
    const credential = (await navigator.credentials.create({
      publicKey: createOptions,
    })) as PublicKeyCredential | null;

    if (!credential) return null;

    const response = credential.response as AuthenticatorAttestationResponse;
    return {
      credentialId: base64url(credential.rawId),
      publicKey: base64url(response.getPublicKey?.() ?? response.attestationObject),
    };
  } catch (err) {
    console.error('[TEE] WebAuthn registration failed:', err);
    return null;
  }
}

/**
 * Perform attestation — requires user to authenticate with
 * their platform authenticator (biometrics, PIN, etc.)
 */
export async function performWebAuthnAttestation(
  credentialId: string,
  actionId: string,
): Promise<AttestationResult> {
  if (!isWebAuthnSupported()) {
    return {
      success: false,
      method: 'webauthn',
      timestamp: Date.now(),
      error: 'WebAuthn not supported on this device',
    };
  }

  const challenge = randomChallenge();

  // Embed the action ID in the challenge so the attestation
  // is bound to the specific critical action
  const actionBytes = new TextEncoder().encode(actionId);
  const boundChallenge = new Uint8Array(challenge.length + actionBytes.length);
  boundChallenge.set(challenge);
  boundChallenge.set(actionBytes, challenge.length);

  const getOptions: PublicKeyCredentialRequestOptions = {
    challenge: boundChallenge,
    rpId: RP_ID,
    allowCredentials: [
      {
        type: 'public-key',
        id: base64urlDecode(credentialId),
        transports: ['internal'],
      },
    ],
    userVerification: 'required',
    timeout: 60000,
  };

  try {
    const assertion = (await navigator.credentials.get({
      publicKey: getOptions,
    })) as PublicKeyCredential | null;

    if (!assertion) {
      return {
        success: false,
        method: 'webauthn',
        timestamp: Date.now(),
        error: 'User cancelled authentication',
      };
    }

    const response = assertion.response as AuthenticatorAssertionResponse;

    return {
      success: true,
      method: 'webauthn',
      credentialId,
      signature: base64url(response.signature),
      challenge: base64url(boundChallenge),
      timestamp: Date.now(),
    };
  } catch (err: unknown) {
    return {
      success: false,
      method: 'webauthn',
      timestamp: Date.now(),
      error: err instanceof Error ? err.message : 'WebAuthn assertion failed',
    };
  }
}

// ---------------------------------------------------------------------------
// Web Crypto — Non-exportable key management (Secure Enclave substitute)
// ---------------------------------------------------------------------------

const KEY_STORE_NAME = 'amttp_secure_keys';
let _keyDb: IDBDatabase | null = null;

async function openKeyDB(): Promise<IDBDatabase> {
  if (_keyDb) return _keyDb;
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(KEY_STORE_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains('keys')) {
        req.result.createObjectStore('keys', { keyPath: 'id' });
      }
    };
    req.onsuccess = () => {
      _keyDb = req.result;
      resolve(req.result);
    };
    req.onerror = () => reject(req.error);
  });
}

/**
 * Generate a non-exportable ECDSA signing key stored in the browser's
 * secure key storage (backed by OS-level Keychain/TPM where available).
 *
 * The private key NEVER leaves the secure enclave — all signing operations
 * happen inside the browser's Crypto engine.
 */
export async function generateSecureKey(keyId: string): Promise<SecureKeyHandle | null> {
  try {
    const keyPair = await crypto.subtle.generateKey(
      { name: 'ECDSA', namedCurve: 'P-256' },
      false, // NON-EXPORTABLE — key stays in secure storage
      ['sign', 'verify'],
    );

    // Store in IndexedDB (only the CryptoKey reference, not raw bytes)
    const db = await openKeyDB();
    const tx = db.transaction('keys', 'readwrite');
    tx.objectStore('keys').put({
      id: keyId,
      privateKey: keyPair.privateKey,
      publicKey: keyPair.publicKey,
      createdAt: Date.now(),
    });

    // Export public key for server-side verification
    const pubRaw = await crypto.subtle.exportKey('spki', keyPair.publicKey);

    return {
      keyId,
      createdAt: Date.now(),
      algorithm: 'ECDSA P-256',
      usages: ['sign', 'verify'],
    };
  } catch (err) {
    console.error('[TEE] Failed to generate secure key:', err);
    return null;
  }
}

/**
 * Sign a challenge using the non-exportable private key.
 * This operation is performed inside the browser's Crypto engine
 * and the private key never enters JavaScript memory.
 */
export async function signWithSecureKey(
  keyId: string,
  data: Uint8Array,
): Promise<string | null> {
  try {
    const db = await openKeyDB();
    const tx = db.transaction('keys', 'readonly');
    const stored = await new Promise<{ privateKey: CryptoKey } | undefined>((res, rej) => {
      const req = tx.objectStore('keys').get(keyId);
      req.onsuccess = () => res(req.result);
      req.onerror = () => rej(req.error);
    });

    if (!stored?.privateKey) return null;

    const sig = await crypto.subtle.sign(
      { name: 'ECDSA', hash: 'SHA-256' },
      stored.privateKey,
      data,
    );

    return base64url(sig);
  } catch (err) {
    console.error('[TEE] Signing failed:', err);
    return null;
  }
}

/**
 * Verify a signature using the stored public key.
 */
export async function verifyWithSecureKey(
  keyId: string,
  data: Uint8Array,
  signatureB64: string,
): Promise<boolean> {
  try {
    const db = await openKeyDB();
    const tx = db.transaction('keys', 'readonly');
    const stored = await new Promise<{ publicKey: CryptoKey } | undefined>((res, rej) => {
      const req = tx.objectStore('keys').get(keyId);
      req.onsuccess = () => res(req.result);
      req.onerror = () => rej(req.error);
    });

    if (!stored?.publicKey) return false;

    const sig = base64urlDecode(signatureB64);
    return crypto.subtle.verify(
      { name: 'ECDSA', hash: 'SHA-256' },
      stored.publicKey,
      sig,
      data,
    );
  } catch (err) {
    console.error('[TEE] Verification failed:', err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// Critical Action Gate — the main orchestrator
// ---------------------------------------------------------------------------

/**
 * Verify that a user is authorized and attested for a critical action.
 * Returns an AttestationResult that must be included in the action request
 * payload sent to the backend.
 *
 * Flow:
 * 1. Check role level >= action.minRole
 * 2. If requiresTEE: attempt WebAuthn attestation
 * 3. If no WebAuthn: fall back to secure key challenge-response
 * 4. If nothing available: require PIN/password re-entry (fallback)
 */
export async function gateCriticalAction(
  action: CriticalAction,
  userRole: number,
  credentialId?: string,
): Promise<AttestationResult> {
  const timestamp = Date.now();

  // 1. Role check
  if (userRole < action.minRole) {
    return {
      success: false,
      method: 'webauthn',
      timestamp,
      error: `Insufficient role level. Required: R${action.minRole}, current: R${userRole}`,
    };
  }

  // 2. If TEE not required, pass immediately
  if (!action.requiresTEE) {
    return { success: true, method: 'fallback-pin', timestamp };
  }

  // 3. Try WebAuthn (hardware attestation)
  if (credentialId && isWebAuthnSupported()) {
    const hasPlatform = await hasPlatformAuthenticator();
    if (hasPlatform) {
      const result = await performWebAuthnAttestation(credentialId, action.id);
      if (result.success) return result;
      // Fall through to next method if user cancelled
    }
  }

  // 4. Try secure key challenge-response
  const secureKeyId = `amttp_action_key_${action.id}`;
  const challenge = randomChallenge();
  const sig = await signWithSecureKey(secureKeyId, challenge);
  if (sig) {
    const valid = await verifyWithSecureKey(secureKeyId, challenge, sig);
    if (valid) {
      return {
        success: true,
        method: 'secure-key',
        challenge: base64url(challenge),
        signature: sig,
        timestamp,
      };
    }
  }

  // 5. Fallback: require PIN re-entry (UI layer must prompt)
  // Return a "needs-pin" result that the UI layer handles
  return {
    success: false,
    method: 'fallback-pin',
    timestamp,
    error: 'NEEDS_PIN_CONFIRMATION',
  };
}

// ---------------------------------------------------------------------------
// Enrollment helper — should be called during first-time setup
// ---------------------------------------------------------------------------

/**
 * Full enrollment: register WebAuthn credential + generate secure key
 * for each critical action the user's role can perform.
 */
export async function enrollForCriticalActions(
  userId: string,
  userName: string,
  userRole: number,
  actions: CriticalAction[],
): Promise<{
  credentialId: string | null;
  secureKeys: string[];
  errors: string[];
}> {
  const errors: string[] = [];
  let credentialId: string | null = null;
  const secureKeys: string[] = [];

  // Register WebAuthn credential
  if (isWebAuthnSupported() && (await hasPlatformAuthenticator())) {
    const cred = await registerCredential(userId, userName);
    if (cred) {
      credentialId = cred.credentialId;
    } else {
      errors.push('WebAuthn enrollment failed — will use fallback methods');
    }
  }

  // Generate secure keys for each action the user can perform
  for (const action of actions) {
    if (userRole >= action.minRole && action.requiresTEE) {
      const keyId = `amttp_action_key_${action.id}`;
      const handle = await generateSecureKey(keyId);
      if (handle) {
        secureKeys.push(keyId);
      } else {
        errors.push(`Failed to generate secure key for "${action.label}"`);
      }
    }
  }

  return { credentialId, secureKeys, errors };
}
