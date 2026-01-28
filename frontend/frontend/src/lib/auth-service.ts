/**
 * Authentication Service
 * 
 * Real authentication implementation for AMTTP
 * Supports wallet-based auth and traditional email/password
 */

import { useState, useCallback, useEffect } from 'react';
import {
  User,
  AuthMethod,
  WalletType,
  RegistrationData,
  RegistrationResult,
  RegistrationError,
  LoginCredentials,
  LoginResult,
  LoginError,
  Session,
  SignInMessage,
  KYCLevel,
  ComplianceStatus,
  createSignInMessage,
  formatSignInMessage,
  generateNonce,
  getDefaultRole,
  getDefaultMode,
  validateEmail,
  validatePassword,
} from '@/types/auth';
import { Role, AppMode } from '@/types/rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// STORAGE KEYS
// ═══════════════════════════════════════════════════════════════════════════════

const STORAGE_KEYS = {
  SESSION_TOKEN: 'amttp_session_token',
  REFRESH_TOKEN: 'amttp_refresh_token',
  USER: 'amttp_user',
  NONCE: 'amttp_auth_nonce',
};

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK USER DATABASE (Replace with real API calls)
// ═══════════════════════════════════════════════════════════════════════════════

const mockUsers: Map<string, User & { passwordHash?: string }> = new Map();

// Pre-seed demo users for ALL roles (R1-R6)
// R1: End User
mockUsers.set('0x742d35cc6634c0532925a3b844bc9e7595f1c7d8', {
  id: 'user-001',
  walletAddress: '0x742d35Cc6634C0532925a3b844Bc9e7595f1c7D8',
  displayName: 'Demo User (R1)',
  role: Role.R1_END_USER,
  permissions: ['transfer.initiate', 'trust.view'],
  defaultMode: AppMode.FOCUS,
  kycLevel: KYCLevel.STANDARD,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// R2: End User PEP (Politically Exposed Person)
mockUsers.set('0x2222222222222222222222222222222222222222', {
  id: 'user-002',
  walletAddress: '0x2222222222222222222222222222222222222222',
  displayName: 'PEP User (R2)',
  role: Role.R2_END_USER_PEP,
  permissions: ['transfer.initiate', 'trust.view', 'enhanced.reporting'],
  defaultMode: AppMode.FOCUS,
  kycLevel: KYCLevel.ENHANCED,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// R3: Institution Ops
mockUsers.set('0x3333333333333333333333333333333333333333', {
  id: 'user-003',
  walletAddress: '0x3333333333333333333333333333333333333333',
  displayName: 'Ops Analyst (R3)',
  role: Role.R3_INSTITUTION_OPS,
  permissions: ['transfer.initiate', 'trust.view', 'detection.access', 'analytics.view'],
  defaultMode: AppMode.WAR_ROOM,
  kycLevel: KYCLevel.ENHANCED,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// R4: Institution Compliance
mockUsers.set('0x4444444444444444444444444444444444444444', {
  id: 'user-004',
  walletAddress: '0x4444444444444444444444444444444444444444',
  displayName: 'Compliance Officer (R4)',
  role: Role.R4_INSTITUTION_COMPLIANCE,
  permissions: ['transfer.initiate', 'trust.view', 'detection.access', 'analytics.view', 'policy.edit', 'compliance.full', 'multisig.sign'],
  defaultMode: AppMode.WAR_ROOM,
  kycLevel: KYCLevel.ENHANCED,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// R5: Platform Admin
mockUsers.set('0x5555555555555555555555555555555555555555', {
  id: 'user-005',
  walletAddress: '0x5555555555555555555555555555555555555555',
  displayName: 'Platform Admin (R5)',
  role: Role.R5_PLATFORM_ADMIN,
  permissions: ['transfer.initiate', 'trust.view', 'detection.access', 'analytics.view', 'policy.edit', 'compliance.full', 'multisig.sign', 'admin.users', 'admin.system'],
  defaultMode: AppMode.WAR_ROOM,
  kycLevel: KYCLevel.ENHANCED,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// R6: Super Admin
mockUsers.set('0x6666666666666666666666666666666666666666', {
  id: 'user-006',
  walletAddress: '0x6666666666666666666666666666666666666666',
  displayName: 'Super Admin (R6)',
  role: Role.R6_SUPER_ADMIN,
  permissions: ['*'], // Full access
  defaultMode: AppMode.WAR_ROOM,
  kycLevel: KYCLevel.ENHANCED,
  complianceStatus: ComplianceStatus.APPROVED,
  createdAt: '2024-01-15T10:00:00Z',
  isActive: true,
  preferences: {
    theme: 'dark',
    notifications: { email: true, push: true, alerts: true },
    defaultCurrency: 'USD',
    language: 'en',
  },
});

// ═══════════════════════════════════════════════════════════════════════════════
// WALLET DETECTION
// ═══════════════════════════════════════════════════════════════════════════════

// Type for ethereum provider (compatible with MetaMask, Coinbase, etc.)
interface EthereumProvider {
  isMetaMask?: boolean;
  isCoinbaseWallet?: boolean;
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
  on?: (event: string, callback: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, callback: (...args: unknown[]) => void) => void;
}

function getEthereumProvider(): EthereumProvider | undefined {
  if (typeof window === 'undefined') return undefined;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (window as any).ethereum as EthereumProvider | undefined;
}

export function detectWallet(): WalletType | null {
  const ethereum = getEthereumProvider();
  if (!ethereum) {
    return null;
  }
  
  if (ethereum.isMetaMask) {
    return WalletType.METAMASK;
  }
  if (ethereum.isCoinbaseWallet) {
    return WalletType.COINBASE;
  }
  
  return WalletType.INJECTED;
}

export function isWalletConnected(): boolean {
  return !!getEthereumProvider();
}

// ═══════════════════════════════════════════════════════════════════════════════
// WALLET OPERATIONS
// ═══════════════════════════════════════════════════════════════════════════════

export async function connectWallet(): Promise<{ address: string; chainId: number } | null> {
  const ethereum = getEthereumProvider();
  if (!ethereum) {
    throw new Error('No wallet detected. Please install MetaMask or another Web3 wallet.');
  }
  
  try {
    // Request account access
    const accounts = await ethereum.request({
      method: 'eth_requestAccounts',
    }) as string[];
    
    if (!accounts || accounts.length === 0) {
      return null;
    }
    
    // Get chain ID
    const chainIdHex = await ethereum.request({
      method: 'eth_chainId',
    }) as string;
    
    const chainId = parseInt(chainIdHex, 16);
    
    return {
      address: accounts[0],
      chainId,
    };
  } catch (error) {
    console.error('Failed to connect wallet:', error);
    throw error;
  }
}

export async function signMessage(message: string): Promise<string> {
  const ethereum = getEthereumProvider();
  if (!ethereum) {
    throw new Error('No wallet detected');
  }
  
  const accounts = await ethereum.request({
    method: 'eth_accounts',
  }) as string[];
  
  if (!accounts || accounts.length === 0) {
    throw new Error('No account connected');
  }
  
  const signature = await ethereum.request({
    method: 'personal_sign',
    params: [message, accounts[0]],
  }) as string;
  
  return signature;
}

export async function getConnectedAccount(): Promise<string | null> {
  const ethereum = getEthereumProvider();
  if (!ethereum) return null;
  
  try {
    const accounts = await ethereum.request({
      method: 'eth_accounts',
    }) as string[];
    
    return accounts?.[0] || null;
  } catch {
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUTHENTICATION SERVICE
// ═══════════════════════════════════════════════════════════════════════════════

export async function registerUser(data: RegistrationData): Promise<RegistrationResult> {
  // Validate terms acceptance
  if (!data.acceptedTerms || !data.acceptedPrivacy) {
    return {
      success: false,
      error: RegistrationError.TERMS_NOT_ACCEPTED,
    };
  }
  
  // Handle wallet registration
  if (data.authMethod === AuthMethod.WALLET) {
    if (!data.walletAddress || !data.signature || !data.signedMessage) {
      return {
        success: false,
        error: RegistrationError.INVALID_SIGNATURE,
      };
    }
    
    // Check if wallet already registered
    const existingUser = mockUsers.get(data.walletAddress.toLowerCase());
    if (existingUser) {
      return {
        success: false,
        error: RegistrationError.WALLET_ALREADY_REGISTERED,
      };
    }
    
    // TODO: Verify signature on backend
    // For now, we'll trust the signature
    
    // Create new user
    const newUser: User = {
      id: `user-${Date.now()}`,
      walletAddress: data.walletAddress,
      displayName: data.displayName || `User ${data.walletAddress.slice(0, 6)}`,
      role: Role.R1_END_USER,
      permissions: ['transfer.initiate', 'trust.view'],
      defaultMode: AppMode.FOCUS,
      kycLevel: KYCLevel.NONE,
      complianceStatus: ComplianceStatus.PENDING,
      createdAt: new Date().toISOString(),
      isActive: true,
      preferences: {
        theme: 'dark',
        notifications: { email: true, push: true, alerts: true },
        defaultCurrency: 'USD',
        language: 'en',
      },
    };
    
    // Save to "database"
    mockUsers.set(data.walletAddress.toLowerCase(), newUser);
    
    // Generate session
    const sessionToken = generateNonce();
    
    // Store session
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.SESSION_TOKEN, sessionToken);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(newUser));
    }
    
    return {
      success: true,
      user: newUser,
      sessionToken,
      requiresVerification: false,
    };
  }
  
  // Handle email registration
  if (data.authMethod === AuthMethod.EMAIL) {
    if (!data.email || !data.password) {
      return {
        success: false,
        error: RegistrationError.INVALID_EMAIL,
      };
    }
    
    if (!validateEmail(data.email)) {
      return {
        success: false,
        error: RegistrationError.INVALID_EMAIL,
      };
    }
    
    const passwordValidation = validatePassword(data.password);
    if (!passwordValidation.valid) {
      return {
        success: false,
        error: RegistrationError.WEAK_PASSWORD,
      };
    }
    
    // Check if email already registered
    const existingUser = Array.from(mockUsers.values()).find(u => u.email === data.email);
    if (existingUser) {
      return {
        success: false,
        error: RegistrationError.EMAIL_ALREADY_REGISTERED,
      };
    }
    
    // Create new user
    const newUser: User & { passwordHash: string } = {
      id: `user-${Date.now()}`,
      email: data.email,
      displayName: data.displayName || data.email.split('@')[0],
      role: Role.R1_END_USER,
      permissions: ['transfer.initiate', 'trust.view'],
      defaultMode: AppMode.FOCUS,
      kycLevel: KYCLevel.NONE,
      complianceStatus: ComplianceStatus.PENDING,
      createdAt: new Date().toISOString(),
      isActive: true,
      preferences: {
        theme: 'dark',
        notifications: { email: true, push: true, alerts: true },
        defaultCurrency: 'USD',
        language: 'en',
      },
      passwordHash: data.password, // TODO: Hash password properly
    };
    
    // Save to "database"
    mockUsers.set(data.email.toLowerCase(), newUser);
    
    return {
      success: true,
      user: newUser,
      requiresVerification: true,
      verificationMethod: 'email',
    };
  }
  
  return {
    success: false,
    error: RegistrationError.UNKNOWN_ERROR,
  };
}

export async function loginUser(credentials: LoginCredentials): Promise<LoginResult> {
  // Handle wallet login
  if (credentials.authMethod === AuthMethod.WALLET) {
    if (!credentials.walletAddress || !credentials.signature || !credentials.signedMessage) {
      return {
        success: false,
        error: LoginError.INVALID_SIGNATURE,
      };
    }
    
    // Find user
    const user = mockUsers.get(credentials.walletAddress.toLowerCase());
    if (!user) {
      return {
        success: false,
        error: LoginError.WALLET_NOT_FOUND,
      };
    }
    
    if (!user.isActive) {
      return {
        success: false,
        error: LoginError.ACCOUNT_DISABLED,
      };
    }
    
    // TODO: Verify signature on backend
    
    // Generate session
    const sessionToken = generateNonce();
    const refreshToken = generateNonce();
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(); // 24 hours
    
    // Update last login
    user.lastLoginAt = new Date().toISOString();
    
    // Store session
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.SESSION_TOKEN, sessionToken);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(user));
    }
    
    return {
      success: true,
      user,
      sessionToken,
      refreshToken,
      expiresAt,
    };
  }
  
  // Handle email login
  if (credentials.authMethod === AuthMethod.EMAIL) {
    if (!credentials.email || !credentials.password) {
      return {
        success: false,
        error: LoginError.INVALID_CREDENTIALS,
      };
    }
    
    // Find user
    const user = mockUsers.get(credentials.email.toLowerCase()) as (User & { passwordHash?: string }) | undefined;
    if (!user || user.passwordHash !== credentials.password) {
      return {
        success: false,
        error: LoginError.INVALID_CREDENTIALS,
      };
    }
    
    if (!user.isActive) {
      return {
        success: false,
        error: LoginError.ACCOUNT_DISABLED,
      };
    }
    
    // Generate session
    const sessionToken = generateNonce();
    const refreshToken = generateNonce();
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    
    // Update last login
    user.lastLoginAt = new Date().toISOString();
    
    // Store session
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.SESSION_TOKEN, sessionToken);
      localStorage.setItem(STORAGE_KEYS.REFRESH_TOKEN, refreshToken);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(user));
    }
    
    // Remove password hash from returned user
    const { passwordHash, ...safeUser } = user;
    
    return {
      success: true,
      user: safeUser,
      sessionToken,
      refreshToken,
      expiresAt,
    };
  }
  
  return {
    success: false,
    error: LoginError.UNKNOWN_ERROR,
  };
}

export function logoutUser(): void {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(STORAGE_KEYS.SESSION_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.REFRESH_TOKEN);
    localStorage.removeItem(STORAGE_KEYS.USER);
    localStorage.removeItem(STORAGE_KEYS.NONCE);
  }
}

export function getCurrentUser(): User | null {
  if (typeof window === 'undefined') return null;
  
  const userJson = localStorage.getItem(STORAGE_KEYS.USER);
  if (!userJson) return null;
  
  try {
    return JSON.parse(userJson) as User;
  } catch {
    return null;
  }
}

export function getSessionToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(STORAGE_KEYS.SESSION_TOKEN);
}

export function isAuthenticated(): boolean {
  return !!getSessionToken() && !!getCurrentUser();
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useAuthService() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [walletConnected, setWalletConnected] = useState(false);
  const [walletAddress, setWalletAddress] = useState<string | null>(null);
  const [walletType, setWalletType] = useState<WalletType | null>(null);
  
  // Initialize on mount
  useEffect(() => {
    const initAuth = async () => {
      // Check for existing session
      const currentUser = getCurrentUser();
      if (currentUser) {
        setUser(currentUser);
      }
      
      // Check wallet connection
      const address = await getConnectedAccount();
      if (address) {
        setWalletConnected(true);
        setWalletAddress(address);
        setWalletType(detectWallet());
      }
      
      setIsLoading(false);
    };
    
    initAuth();
    
    // Listen for wallet events
    const ethereum = getEthereumProvider();
    if (ethereum && ethereum.on) {
      const handleAccountsChanged = (accounts: unknown) => {
        const accts = accounts as string[];
        if (accts.length === 0) {
          setWalletConnected(false);
          setWalletAddress(null);
        } else {
          setWalletAddress(accts[0]);
          setWalletConnected(true);
        }
      };
      
      ethereum.on('accountsChanged', handleAccountsChanged);
      
      return () => {
        if (ethereum.removeListener) {
          ethereum.removeListener('accountsChanged', handleAccountsChanged);
        }
      };
    }
  }, []);
  
  const connect = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await connectWallet();
      if (result) {
        setWalletConnected(true);
        setWalletAddress(result.address);
        setWalletType(detectWallet());
        return result;
      }
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  const register = useCallback(async (data: Omit<RegistrationData, 'walletAddress' | 'signature' | 'signedMessage'> & { walletAddress?: string }) => {
    setIsLoading(true);
    try {
      if (data.authMethod === AuthMethod.WALLET) {
        // Generate nonce and message
        const nonce = generateNonce();
        const address = data.walletAddress || walletAddress;
        
        if (!address) {
          throw new Error('No wallet connected');
        }
        
        const message = createSignInMessage({ address, nonce });
        const formattedMessage = formatSignInMessage(message);
        
        // Sign message
        const signature = await signMessage(formattedMessage);
        
        // Register
        const result = await registerUser({
          ...data,
          walletAddress: address,
          signature,
          signedMessage: formattedMessage,
        });
        
        if (result.success && result.user) {
          setUser(result.user);
        }
        
        return result;
      }
      
      // Email registration
      const result = await registerUser(data as RegistrationData);
      if (result.success && result.user) {
        setUser(result.user);
      }
      
      return result;
    } finally {
      setIsLoading(false);
    }
  }, [walletAddress]);
  
  const login = useCallback(async (credentials: Omit<LoginCredentials, 'walletAddress' | 'signature' | 'signedMessage'>) => {
    setIsLoading(true);
    try {
      if (credentials.authMethod === AuthMethod.WALLET) {
        // Generate nonce and message
        const nonce = generateNonce();
        const address = walletAddress;
        
        if (!address) {
          throw new Error('No wallet connected');
        }
        
        const message = createSignInMessage({ address, nonce });
        const formattedMessage = formatSignInMessage(message);
        
        // Sign message
        const signature = await signMessage(formattedMessage);
        
        // Login
        const result = await loginUser({
          ...credentials,
          walletAddress: address,
          signature,
          signedMessage: formattedMessage,
          nonce,
        });
        
        if (result.success && result.user) {
          setUser(result.user);
        }
        
        return result;
      }
      
      // Email login
      const result = await loginUser(credentials as LoginCredentials);
      if (result.success && result.user) {
        setUser(result.user);
      }
      
      return result;
    } finally {
      setIsLoading(false);
    }
  }, [walletAddress]);
  
  const logout = useCallback(() => {
    logoutUser();
    setUser(null);
  }, []);
  
  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    walletConnected,
    walletAddress,
    walletType,
    connect,
    register,
    login,
    logout,
  };
}
