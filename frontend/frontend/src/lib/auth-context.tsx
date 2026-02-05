/**
 * AMTTP Auth Context
 * 
 * Provides RBAC-locked mode switching and role-based access control
 * Mode is determined by role, NOT user preference
 */

'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import {
  Role,
  AppMode,
  UserSession,
  RoleCapabilities,
  getRoleMode,
  getRoleCapabilities,
  canAccessRoute,
  ROLE_LABELS,
  ROLE_COLORS,
} from '@/types/rbac';

const ORCHESTRATOR_API = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  session: UserSession | null;
  error: string | null;
}

interface AuthContextType extends AuthState {
  // Auth actions
  login: (address: string) => Promise<void>;
  logout: () => void;
  
  // Role helpers
  role: Role | null;
  mode: AppMode | null;
  capabilities: RoleCapabilities | null;
  
  // Access control
  canAccess: (route: string) => boolean;
  isEndUser: boolean;
  isInstitutional: boolean;
  canEnforce: boolean;
  
  // Display helpers
  roleLabel: string;
  roleColor: string;
  modeLabel: string;
  
  // Demo role switching (for development only)
  switchRole: (role: Role) => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONTEXT
// ═══════════════════════════════════════════════════════════════════════════════

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ═══════════════════════════════════════════════════════════════════════════════
// PROVIDER
// ═══════════════════════════════════════════════════════════════════════════════

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    session: null,
    error: null,
  });

  // Check for existing session on mount
  useEffect(() => {
    const checkSession = async () => {
      try {
        // Check localStorage for existing session
        const storedSession = localStorage.getItem('amttp_session');
        if (storedSession) {
          const session = JSON.parse(storedSession) as UserSession;
          setState({
            isAuthenticated: true,
            isLoading: false,
            session,
            error: null,
          });
          return;
        }
      } catch (e) {
        console.error('Failed to restore session:', e);
      }
      
      setState(prev => ({ ...prev, isLoading: false }));
    };
    
    checkSession();
  }, []);

  // Login with wallet address
  const login = useCallback(async (address: string) => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));
    
    try {
      // Map of demo addresses to roles (for demo mode)
      const demoRoles: Record<string, Role> = {
        '0x742d35cc6634c0532925a3b844bc9e7595f1c7d8': Role.R1_END_USER,
        '0x2222222222222222222222222222222222222222': Role.R2_END_USER_PEP,
        '0x3333333333333333333333333333333333333333': Role.R3_INSTITUTION_OPS,
        '0x4444444444444444444444444444444444444444': Role.R4_INSTITUTION_COMPLIANCE,
        '0x5555555555555555555555555555555555555555': Role.R5_PLATFORM_ADMIN,
        '0x6666666666666666666666666666666666666666': Role.R6_SUPER_ADMIN,
      };
      
      // Display names for demo users
      const demoNames: Record<string, string> = {
        '0x742d35cc6634c0532925a3b844bc9e7595f1c7d8': 'Demo User (R1)',
        '0x2222222222222222222222222222222222222222': 'PEP User (R2)',
        '0x3333333333333333333333333333333333333333': 'Ops Analyst (R3)',
        '0x4444444444444444444444444444444444444444': 'Compliance Officer (R4)',
        '0x5555555555555555555555555555555555555555': 'Platform Admin (R5)',
        '0x6666666666666666666666666666666666666666': 'Super Admin (R6)',
      };
      
      let role: Role;
      let displayName: string;
      let institutionId: string | undefined;
      let institutionName: string | undefined;
      
      // Check if this is a demo address
      const normalizedAddress = address.toLowerCase();
      if (demoRoles[normalizedAddress]) {
        role = demoRoles[normalizedAddress];
        displayName = demoNames[normalizedAddress] || `${address.slice(0, 6)}...${address.slice(-4)}`;
        
        // Set institution for R3+ roles
        if ([Role.R3_INSTITUTION_OPS, Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN].includes(role)) {
          institutionId = 'inst_demo';
          institutionName = 'AMTTP Demo Institution';
        }
      } else {
        // Try to fetch from backend
        try {
          const response = await fetch(`${ORCHESTRATOR_API}/auth/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ address }),
          });
          
          if (response.ok) {
            const data = await response.json();
            role = data.role as Role;
            displayName = data.displayName || `${address.slice(0, 6)}...${address.slice(-4)}`;
            institutionId = data.institutionId;
            institutionName = data.institutionName;
          } else {
            // Default to R3 for Next.js (institutional users only)
            role = Role.R3_INSTITUTION_OPS;
            displayName = `${address.slice(0, 6)}...${address.slice(-4)}`;
          }
        } catch {
          // Backend not available, default to R3 for Next.js (institutional users only)
          role = Role.R3_INSTITUTION_OPS;
          displayName = `${address.slice(0, 6)}...${address.slice(-4)}`;
        }
      }
      
      // Mode is RBAC-locked based on role
      const mode = getRoleMode(role);
      const capabilities = getRoleCapabilities(role);
      
      const session: UserSession = {
        userId: `user_${address.slice(2, 10)}`,
        address,
        displayName,
        role,
        mode,
        capabilities,
        institutionId,
        institutionName,
      };
      
      // Store session
      localStorage.setItem('amttp_session', JSON.stringify(session));
      
      setState({
        isAuthenticated: true,
        isLoading: false,
        session,
        error: null,
      });
    } catch (e) {
      console.error('Login failed:', e);
      
      // Fallback: create local session as R3 (institutional user) for Next.js
      const role = Role.R3_INSTITUTION_OPS;
      const session: UserSession = {
        userId: `user_${address.slice(2, 10)}`,
        address,
        displayName: `${address.slice(0, 6)}...${address.slice(-4)}`,
        role,
        mode: getRoleMode(role),
        capabilities: getRoleCapabilities(role),
      };
      
      localStorage.setItem('amttp_session', JSON.stringify(session));
      
      setState({
        isAuthenticated: true,
        isLoading: false,
        session,
        error: null,
      });
    }
  }, []);

  // Logout
  const logout = useCallback(() => {
    localStorage.removeItem('amttp_session');
    setState({
      isAuthenticated: false,
      isLoading: false,
      session: null,
      error: null,
    });
  }, []);

  // Demo role switching (development only)
  const switchRole = useCallback((role: Role) => {
    if (!state.session) return;
    
    const mode = getRoleMode(role);
    const capabilities = getRoleCapabilities(role);
    
    const newSession: UserSession = {
      ...state.session,
      role,
      mode,
      capabilities,
    };
    
    localStorage.setItem('amttp_session', JSON.stringify(newSession));
    
    setState(prev => ({
      ...prev,
      session: newSession,
    }));
  }, [state.session]);

  // Computed values
  const role = state.session?.role ?? null;
  const mode = state.session?.mode ?? null;
  const capabilities = state.session?.capabilities ?? null;
  
  const canAccess = useCallback((route: string) => {
    if (!role) return false;
    return canAccessRoute(role, route);
  }, [role]);
  
  const isEndUser = role === Role.R1_END_USER || role === Role.R2_END_USER_PEP;
  const isInstitutional = role === Role.R3_INSTITUTION_OPS || role === Role.R4_INSTITUTION_COMPLIANCE;
  const canEnforceAction = role === Role.R4_INSTITUTION_COMPLIANCE;
  
  const roleLabel = role ? ROLE_LABELS[role] : '';
  const roleColor = role ? ROLE_COLORS[role] : '#6B7280';
  const modeLabel = mode === AppMode.FOCUS ? 'Focus Mode' : mode === AppMode.WAR_ROOM ? 'War Room' : '';

  const contextValue: AuthContextType = {
    ...state,
    login,
    logout,
    role,
    mode,
    capabilities,
    canAccess,
    isEndUser,
    isInstitutional,
    canEnforce: canEnforceAction,
    roleLabel,
    roleColor,
    modeLabel,
    switchRole,
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// ═══════════════════════════════════════════════════════════════════════════════
// GUARD COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

interface RoleGuardProps {
  children: ReactNode;
  allowedRoles?: Role[];
  allowedModes?: AppMode[];
  fallback?: ReactNode;
}

export function RoleGuard({ children, allowedRoles, allowedModes, fallback }: RoleGuardProps) {
  const { role, mode, isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }
  
  if (!isAuthenticated || !role || !mode) {
    return fallback ?? null;
  }
  
  // Check role access
  if (allowedRoles && !allowedRoles.includes(role)) {
    return fallback ?? (
      <div className="flex items-center justify-center min-h-screen bg-gray-950 text-white">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Access Denied</h1>
          <p className="text-gray-400">Your role does not have access to this area.</p>
        </div>
      </div>
    );
  }
  
  // Check mode access
  if (allowedModes && !allowedModes.includes(mode)) {
    return fallback ?? (
      <div className="flex items-center justify-center min-h-screen bg-gray-950 text-white">
        <div className="text-center">
          <h1 className="text-2xl font-bold mb-2">Wrong Mode</h1>
          <p className="text-gray-400">This area is not available in your current mode.</p>
        </div>
      </div>
    );
  }
  
  return <>{children}</>;
}
