/**
 * Authentication Types
 * 
 * Real authentication system for AMTTP
 * Supports wallet-based auth and traditional email/password
 */

import { Role, AppMode } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// AUTH METHODS
// ═══════════════════════════════════════════════════════════════════════════════

export enum AuthMethod {
  WALLET = 'WALLET',           // Web3 wallet (MetaMask, WalletConnect, etc.)
  EMAIL = 'EMAIL',             // Traditional email/password
  SSO = 'SSO',                 // Enterprise SSO (OAuth/OIDC)
  PASSKEY = 'PASSKEY',         // WebAuthn/Passkeys
}

export enum WalletType {
  METAMASK = 'METAMASK',
  WALLET_CONNECT = 'WALLET_CONNECT',
  COINBASE = 'COINBASE',
  INJECTED = 'INJECTED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// USER TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface User {
  id: string;
  
  // Identity
  walletAddress?: string;
  email?: string;
  displayName?: string;
  avatarUrl?: string;
  
  // RBAC
  role: Role;
  permissions: string[];
  defaultMode: AppMode;
  
  // KYC/Compliance
  kycLevel: KYCLevel;
  kycVerifiedAt?: string;
  complianceStatus: ComplianceStatus;
  
  // Account
  createdAt: string;
  lastLoginAt?: string;
  isActive: boolean;
  
  // Settings
  preferences: UserPreferences;
}

export enum KYCLevel {
  NONE = 'NONE',
  BASIC = 'BASIC',           // Email verified
  STANDARD = 'STANDARD',     // ID verified
  ENHANCED = 'ENHANCED',     // Full KYC + AML
}

export enum ComplianceStatus {
  PENDING = 'PENDING',
  APPROVED = 'APPROVED',
  RESTRICTED = 'RESTRICTED',
  BLOCKED = 'BLOCKED',
}

export interface UserPreferences {
  theme: 'dark' | 'light' | 'system';
  notifications: {
    email: boolean;
    push: boolean;
    alerts: boolean;
  };
  defaultCurrency: string;
  language: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// REGISTRATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface RegistrationData {
  // Required
  authMethod: AuthMethod;
  
  // Wallet auth
  walletAddress?: string;
  walletType?: WalletType;
  signature?: string;
  signedMessage?: string;
  
  // Email auth
  email?: string;
  password?: string;
  
  // Profile
  displayName?: string;
  
  // Terms
  acceptedTerms: boolean;
  acceptedPrivacy: boolean;
  
  // Optional
  referralCode?: string;
  institutionId?: string;
}

export interface RegistrationResult {
  success: boolean;
  user?: User;
  sessionToken?: string;
  error?: RegistrationError;
  requiresVerification?: boolean;
  verificationMethod?: 'email' | 'sms' | 'none';
}

export enum RegistrationError {
  WALLET_ALREADY_REGISTERED = 'WALLET_ALREADY_REGISTERED',
  EMAIL_ALREADY_REGISTERED = 'EMAIL_ALREADY_REGISTERED',
  INVALID_SIGNATURE = 'INVALID_SIGNATURE',
  INVALID_EMAIL = 'INVALID_EMAIL',
  WEAK_PASSWORD = 'WEAK_PASSWORD',
  TERMS_NOT_ACCEPTED = 'TERMS_NOT_ACCEPTED',
  BLOCKED_REGION = 'BLOCKED_REGION',
  RATE_LIMITED = 'RATE_LIMITED',
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}

// ═══════════════════════════════════════════════════════════════════════════════
// LOGIN
// ═══════════════════════════════════════════════════════════════════════════════

export interface LoginCredentials {
  authMethod: AuthMethod;
  
  // Wallet
  walletAddress?: string;
  signature?: string;
  signedMessage?: string;
  nonce?: string;
  
  // Email
  email?: string;
  password?: string;
  
  // 2FA
  twoFactorCode?: string;
}

export interface LoginResult {
  success: boolean;
  user?: User;
  sessionToken?: string;
  refreshToken?: string;
  expiresAt?: string;
  error?: LoginError;
  requires2FA?: boolean;
}

export enum LoginError {
  INVALID_CREDENTIALS = 'INVALID_CREDENTIALS',
  INVALID_SIGNATURE = 'INVALID_SIGNATURE',
  WALLET_NOT_FOUND = 'WALLET_NOT_FOUND',
  ACCOUNT_LOCKED = 'ACCOUNT_LOCKED',
  ACCOUNT_DISABLED = 'ACCOUNT_DISABLED',
  REQUIRES_2FA = 'REQUIRES_2FA',
  INVALID_2FA = 'INVALID_2FA',
  SESSION_EXPIRED = 'SESSION_EXPIRED',
  RATE_LIMITED = 'RATE_LIMITED',
  UNKNOWN_ERROR = 'UNKNOWN_ERROR',
}

// ═══════════════════════════════════════════════════════════════════════════════
// SESSION
// ═══════════════════════════════════════════════════════════════════════════════

export interface Session {
  id: string;
  userId: string;
  token: string;
  refreshToken: string;
  
  createdAt: string;
  expiresAt: string;
  lastActivityAt: string;
  
  device: {
    userAgent: string;
    ip?: string;
    location?: string;
  };
  
  isValid: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// WALLET MESSAGE SIGNING
// ═══════════════════════════════════════════════════════════════════════════════

export interface SignInMessage {
  domain: string;
  address: string;
  statement: string;
  uri: string;
  version: string;
  chainId: number;
  nonce: string;
  issuedAt: string;
  expirationTime?: string;
}

export function createSignInMessage(params: {
  address: string;
  nonce: string;
  chainId?: number;
}): SignInMessage {
  const now = new Date();
  return {
    domain: typeof window !== 'undefined' ? window.location.host : 'amttp.io',
    address: params.address,
    statement: 'Sign in to AMTTP - Secure Transfer Protocol',
    uri: typeof window !== 'undefined' ? window.location.origin : 'https://amttp.io',
    version: '1',
    chainId: params.chainId || 1,
    nonce: params.nonce,
    issuedAt: now.toISOString(),
    expirationTime: new Date(now.getTime() + 10 * 60 * 1000).toISOString(), // 10 min
  };
}

export function formatSignInMessage(message: SignInMessage): string {
  return `${message.domain} wants you to sign in with your Ethereum account:
${message.address}

${message.statement}

URI: ${message.uri}
Version: ${message.version}
Chain ID: ${message.chainId}
Nonce: ${message.nonce}
Issued At: ${message.issuedAt}${message.expirationTime ? `\nExpiration Time: ${message.expirationTime}` : ''}`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getDefaultRole(kycLevel: KYCLevel): Role {
  switch (kycLevel) {
    case KYCLevel.ENHANCED:
      return Role.R2_END_USER_PEP;
    case KYCLevel.STANDARD:
    case KYCLevel.BASIC:
      return Role.R1_END_USER;
    default:
      return Role.R1_END_USER;
  }
}

export function getDefaultMode(role: Role): AppMode {
  switch (role) {
    case Role.R1_END_USER:
    case Role.R2_END_USER_PEP:
      return AppMode.FOCUS;
    default:
      return AppMode.WAR_ROOM;
  }
}

export function generateNonce(): string {
  const array = new Uint8Array(16);
  if (typeof window !== 'undefined' && window.crypto) {
    window.crypto.getRandomValues(array);
  } else {
    // Fallback for SSR
    for (let i = 0; i < array.length; i++) {
      array[i] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

export function validateEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

export function validatePassword(password: string): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  
  if (password.length < 8) {
    errors.push('Password must be at least 8 characters');
  }
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain an uppercase letter');
  }
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain a lowercase letter');
  }
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain a number');
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    errors.push('Password must contain a special character');
  }
  
  return { valid: errors.length === 0, errors };
}

export function truncateAddress(address: string, chars: number = 4): string {
  if (!address) return '';
  return `${address.slice(0, chars + 2)}...${address.slice(-chars)}`;
}
