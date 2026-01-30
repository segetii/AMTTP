/**
 * Shared Auth Utilities
 * 
 * Provides unified session management across Flutter and Next.js apps
 * Uses localStorage with shared keys for cross-app authentication
 */

// Shared keys - MUST match Flutter's SharedAuthService
export const AUTH_TOKEN_KEY = 'amttp_auth_token';
export const SESSION_KEY = 'amttp_session';

// App URLs
export const WALLET_APP_URL = process.env.NEXT_PUBLIC_WALLET_URL || 'http://localhost:3010';
export const WAR_ROOM_URL = process.env.NEXT_PUBLIC_WAR_ROOM_URL || '/war-room';

/**
 * Shared session structure - matches Flutter's SharedSession class
 */
export interface SharedSession {
  address: string;
  role: string;
  mode: 'focus' | 'war-room';
  expiresAt: string; // ISO date string
  displayName?: string;
}

/**
 * Get shared session from localStorage
 */
export function getSharedSession(): SharedSession | null {
  if (typeof window === 'undefined') return null;
  
  try {
    const sessionJson = localStorage.getItem(SESSION_KEY);
    if (!sessionJson) return null;
    
    const session = JSON.parse(sessionJson) as SharedSession;
    
    // Check expiration
    if (new Date(session.expiresAt) < new Date()) {
      clearSharedSession();
      return null;
    }
    
    return session;
  } catch (e) {
    console.error('Failed to read shared session:', e);
    return null;
  }
}

/**
 * Save shared session to localStorage
 */
export function saveSharedSession(session: SharedSession): void {
  if (typeof window === 'undefined') return;
  
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch (e) {
    console.error('Failed to save shared session:', e);
  }
}

/**
 * Clear shared session from localStorage
 */
export function clearSharedSession(): void {
  if (typeof window === 'undefined') return;
  
  try {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem(AUTH_TOKEN_KEY);
  } catch (e) {
    console.error('Failed to clear shared session:', e);
  }
}

/**
 * Create a demo session (for demo mode login)
 */
export function createDemoSession(
  address: string,
  role: string,
  displayName?: string
): SharedSession {
  const mode = ['R1', 'R2'].includes(role) ? 'focus' : 'war-room';
  const expiresAt = new Date();
  expiresAt.setHours(expiresAt.getHours() + 24);
  
  return {
    address,
    role,
    mode,
    expiresAt: expiresAt.toISOString(),
    displayName,
  };
}

/**
 * Check if session is for end user (R1/R2) or institutional (R3-R6)
 */
export function isEndUser(session: SharedSession | null): boolean {
  if (!session) return false;
  return ['R1', 'R2'].includes(session.role);
}

export function isInstitutional(session: SharedSession | null): boolean {
  if (!session) return false;
  return ['R3', 'R4', 'R5', 'R6'].includes(session.role);
}

/**
 * Get URL for the appropriate app based on role
 */
export function getAppUrlForRole(role: string): string {
  const isEndUserRole = ['R1', 'R2'].includes(role);
  return isEndUserRole ? WALLET_APP_URL : WAR_ROOM_URL;
}

/**
 * Format address for display (0x1234...5678)
 */
export function formatAddress(address: string): string {
  if (!address || address.length < 10) return address;
  return `${address.substring(0, 6)}...${address.substring(address.length - 4)}`;
}
