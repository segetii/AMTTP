/**
 * Cross-App Auth Bridge — Next.js Side
 *
 * Reads the HMAC-signed session token that Flutter writes to a cookie.
 * This allows Next.js to trust the Flutter session without its own
 * separate localStorage auth system when users navigate to War Room.
 *
 * Cookie name: amttp_xauth
 * Token format: base64url(payload).base64url(hmac-sha256)
 *
 * The HMAC key MUST match Flutter's AUTH_BRIDGE_KEY dart-define.
 */

// Key must match Flutter's --dart-define=AUTH_BRIDGE_KEY value
const BRIDGE_KEY = process.env.AUTH_BRIDGE_KEY || 'amttp-dev-bridge-key-change-in-production-2026';
const COOKIE_NAME = 'amttp_xauth';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface BridgeTokenPayload {
  sub: string;     // userId
  email: string;
  role: string;    // e.g. "R3_INSTITUTION_OPS"
  mode: string;    // "FOCUS" or "WAR_ROOM"
  name: string;    // displayName
  iat: number;     // issued-at (epoch seconds)
  exp: number;     // expiry (epoch seconds)
}

// ═══════════════════════════════════════════════════════════════════════════════
// HMAC UTILITIES (Web Crypto API — works in both Node.js and browser)
// ═══════════════════════════════════════════════════════════════════════════════

function base64UrlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  bytes.forEach(b => binary += String.fromCharCode(b));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function base64UrlDecode(str: string): Uint8Array {
  // Restore standard base64
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) base64 += '=';
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function hmacSign(data: string): Promise<string> {
  const enc = new TextEncoder();
  const keyData = enc.encode(BRIDGE_KEY);
  const msgData = enc.encode(data);

  const cryptoKey = await crypto.subtle.importKey(
    'raw', keyData, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, msgData);
  return base64UrlEncode(sig);
}

async function hmacVerify(data: string, signature: string): Promise<boolean> {
  const expected = await hmacSign(data);
  // Constant-time comparison
  if (expected.length !== signature.length) return false;
  let result = 0;
  for (let i = 0; i < expected.length; i++) {
    result |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
  }
  return result === 0;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TOKEN OPERATIONS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Verify and decode a bridge token.
 * Returns the payload if valid, null if invalid/expired/tampered.
 */
export async function verifyBridgeToken(token: string): Promise<BridgeTokenPayload | null> {
  try {
    const parts = token.split('.');
    if (parts.length !== 2) return null;

    const [payloadB64, sig] = parts;

    // Verify HMAC
    const valid = await hmacVerify(payloadB64, sig);
    if (!valid) {
      console.warn('[CrossAppAuth] HMAC verification failed — possible tampering');
      return null;
    }

    // Decode payload
    const payloadBytes = base64UrlDecode(payloadB64);
    const payloadStr = new TextDecoder().decode(payloadBytes);
    const payload = JSON.parse(payloadStr) as BridgeTokenPayload;

    // Check expiry
    const now = Math.floor(Date.now() / 1000);
    if (now > payload.exp) {
      console.warn('[CrossAppAuth] Token expired');
      return null;
    }

    return payload;
  } catch (e) {
    console.error('[CrossAppAuth] Token verification error:', e);
    return null;
  }
}

/**
 * Create a bridge token (for testing or Next.js-initiated sessions).
 */
export async function createBridgeToken(payload: Omit<BridgeTokenPayload, 'iat' | 'exp'>): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const full: BridgeTokenPayload = {
    ...payload,
    iat: now,
    exp: now + 86400, // 24 hours
  };

  const enc = new TextEncoder();
  const payloadB64 = base64UrlEncode(enc.encode(JSON.stringify(full)));
  const sig = await hmacSign(payloadB64);
  return `${payloadB64}.${sig}`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COOKIE READING (Client-side)
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Read the bridge token from cookie (client-side).
 */
export function readBridgeTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const cookies = document.cookie.split(';');
  for (const cookie of cookies) {
    const [name, ...valueParts] = cookie.trim().split('=');
    if (name === COOKIE_NAME) {
      return valueParts.join('=');
    }
  }
  return null;
}

/**
 * Read bridge token from localStorage fallback.
 */
export function readBridgeTokenFromStorage(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem('amttp_bridge_token');
}

/**
 * Read bridge token — tries cookie first, then localStorage.
 */
export function readBridgeToken(): string | null {
  return readBridgeTokenFromCookie() || readBridgeTokenFromStorage();
}

/**
 * Get verified session from the bridge token.
 * Returns null if no token, invalid, or expired.
 */
export async function getBridgeSession(): Promise<BridgeTokenPayload | null> {
  const token = readBridgeToken();
  if (!token) return null;
  return verifyBridgeToken(token);
}

/**
 * Check if a bridge session exists and is valid.
 */
export async function hasBridgeSession(): Promise<boolean> {
  const session = await getBridgeSession();
  return session !== null;
}

/**
 * Clear bridge session (logout).
 */
export function clearBridgeSession(): void {
  if (typeof document !== 'undefined') {
    document.cookie = `${COOKIE_NAME}=; path=/; SameSite=Strict; max-age=0`;
  }
  if (typeof localStorage !== 'undefined') {
    localStorage.removeItem('amttp_bridge_token');
  }
}
