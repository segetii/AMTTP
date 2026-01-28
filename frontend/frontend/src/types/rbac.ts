/**
 * AMTTP RBAC Type Definitions
 * 
 * Role-Based Access Control following Ground Truth v2.3
 * Roles are RBAC-locked, not user-toggleable
 */

// Core role enum matching backend
export enum Role {
  R1_END_USER = 'R1_END_USER',
  R2_END_USER_PEP = 'R2_END_USER_PEP',
  R3_INSTITUTION_OPS = 'R3_INSTITUTION_OPS',
  R4_INSTITUTION_COMPLIANCE = 'R4_INSTITUTION_COMPLIANCE',
  R5_PLATFORM_ADMIN = 'R5_PLATFORM_ADMIN',
  R6_SUPER_ADMIN = 'R6_SUPER_ADMIN',
}

// Application modes - mutually exclusive
export enum AppMode {
  FOCUS = 'FOCUS',       // End Users (R1/R2) - Informed autonomy
  WAR_ROOM = 'WAR_ROOM', // Institutions (R3/R4) - Investigate → Justify → Govern
}

// Role to mode mapping (RBAC-locked)
export const ROLE_MODE_MAP: Record<Role, AppMode> = {
  [Role.R1_END_USER]: AppMode.FOCUS,
  [Role.R2_END_USER_PEP]: AppMode.FOCUS,
  [Role.R3_INSTITUTION_OPS]: AppMode.WAR_ROOM,
  [Role.R4_INSTITUTION_COMPLIANCE]: AppMode.WAR_ROOM,
  [Role.R5_PLATFORM_ADMIN]: AppMode.WAR_ROOM,
  [Role.R6_SUPER_ADMIN]: AppMode.WAR_ROOM,
};

// Role capabilities matrix
export interface RoleCapabilities {
  canInitiateOwnTx: boolean;
  canAccessDetectionStudio: boolean;
  canEditPolicies: boolean;
  canTriggerEnforcement: boolean;
  canSignMultisig: boolean;
  canVerifyUISnapshot: 'none' | 'view' | 'full';
  canEmergencyOverride: boolean;
}

export const ROLE_CAPABILITIES: Record<Role, RoleCapabilities> = {
  [Role.R1_END_USER]: {
    canInitiateOwnTx: true,
    canAccessDetectionStudio: false,
    canEditPolicies: false,
    canTriggerEnforcement: false,
    canSignMultisig: false,
    canVerifyUISnapshot: 'view',
    canEmergencyOverride: false,
  },
  [Role.R2_END_USER_PEP]: {
    canInitiateOwnTx: true,
    canAccessDetectionStudio: false,
    canEditPolicies: false,
    canTriggerEnforcement: false,
    canSignMultisig: false,
    canVerifyUISnapshot: 'view',
    canEmergencyOverride: false,
  },
  [Role.R3_INSTITUTION_OPS]: {
    canInitiateOwnTx: false,
    canAccessDetectionStudio: true,
    canEditPolicies: false,
    canTriggerEnforcement: false,
    canSignMultisig: false,
    canVerifyUISnapshot: 'view',
    canEmergencyOverride: false,
  },
  [Role.R4_INSTITUTION_COMPLIANCE]: {
    canInitiateOwnTx: false,
    canAccessDetectionStudio: true, // view only
    canEditPolicies: true,
    canTriggerEnforcement: true,
    canSignMultisig: true,
    canVerifyUISnapshot: 'full',
    canEmergencyOverride: false,
  },
  [Role.R5_PLATFORM_ADMIN]: {
    canInitiateOwnTx: false,
    canAccessDetectionStudio: false,
    canEditPolicies: false,
    canTriggerEnforcement: false,
    canSignMultisig: false,
    canVerifyUISnapshot: 'full',
    canEmergencyOverride: false,
  },
  [Role.R6_SUPER_ADMIN]: {
    canInitiateOwnTx: false,
    canAccessDetectionStudio: false,
    canEditPolicies: false,
    canTriggerEnforcement: false,
    canSignMultisig: false,
    canVerifyUISnapshot: 'full',
    canEmergencyOverride: true,
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// TRUST PILLARS - For Focus Mode Counterparty Checks
// ═══════════════════════════════════════════════════════════════════════════════

// Trust pillar categories
export enum TrustPillar {
  SANCTIONS = 'SANCTIONS',
  NETWORK_BEHAVIOR = 'NETWORK_BEHAVIOR',
  GEOGRAPHIC = 'GEOGRAPHIC',
  COUNTERPARTY = 'COUNTERPARTY',
  TRANSACTION_PATTERN = 'TRANSACTION_PATTERN',
}

// Qualitative verdicts (no numeric scores shown to end users)
export enum TrustVerdict {
  PASS = 'PASS',
  REVIEW = 'REVIEW',
  FAIL = 'FAIL',
  UNKNOWN = 'UNKNOWN',
}

// Pillar definition for display
export interface TrustPillarDefinition {
  label: string;
  description: string;
  sources: string[];
}

export const TRUST_PILLARS: Record<TrustPillar, TrustPillarDefinition> = {
  [TrustPillar.SANCTIONS]: {
    label: 'Sanctions Check',
    description: 'Verified against OFAC, EU, UN sanctions lists',
    sources: ['OFAC SDN', 'EU Consolidated', 'UN Security Council'],
  },
  [TrustPillar.NETWORK_BEHAVIOR]: {
    label: 'Network Behavior',
    description: 'On-chain transaction patterns and relationships',
    sources: ['GraphSAGE ML', 'On-chain analysis'],
  },
  [TrustPillar.GEOGRAPHIC]: {
    label: 'Geographic Risk',
    description: 'Jurisdiction and geo-location assessment',
    sources: ['IP Analysis', 'Jurisdiction mapping'],
  },
  [TrustPillar.COUNTERPARTY]: {
    label: 'Counterparty History',
    description: 'Past interactions and dispute record',
    sources: ['AMTTP Records', 'Dispute history'],
  },
  [TrustPillar.TRANSACTION_PATTERN]: {
    label: 'Transaction Pattern',
    description: 'Timing, amounts, and frequency analysis',
    sources: ['LightGBM ML', 'Statistical analysis'],
  },
};

// Trust pillars for counterparty check (qualitative, not numeric)
export type TrustLevel = 'verified' | 'partial' | 'limited' | 'unknown' | 'suspicious';

export interface TrustPillars {
  identityConfidence: TrustLevel;
  transactionHistory: TrustLevel;
  disputeRecord: TrustLevel;
  networkProximity: TrustLevel;
  behavioralSignals: TrustLevel;
}

// Counterparty trust check result
export interface CounterpartyTrustResult {
  address: string;
  overallConfidence: number; // 0-100, but NOT shown to R1/R2
  trustPillars: TrustPillars;
  requiresInterstitial: boolean; // true if confidence < 100
  recommendations: ('continue' | 'escrow' | 'cancel')[];
  integrityHash: string;
}

// User session with role
export interface UserSession {
  userId: string;
  address: string;
  displayName?: string;
  role: Role;
  mode: AppMode;
  capabilities: RoleCapabilities;
  institutionId?: string;
  institutionName?: string;
}

// Helper functions
export function getRoleMode(role: Role): AppMode {
  return ROLE_MODE_MAP[role];
}

export function getRoleCapabilities(role: Role): RoleCapabilities {
  return ROLE_CAPABILITIES[role];
}

export function canAccessRoute(role: Role, route: string): boolean {
  const mode = getRoleMode(role);
  const capabilities = getRoleCapabilities(role);
  
  // Focus mode routes
  const focusRoutes = ['/', '/transfer', '/history', '/escrow', '/disputes', '/settings'];
  
  // War room routes
  const warRoomRoutes = [
    '/war-room',
    '/detection-studio',
    '/compliance-studio',
    '/multisig',
    '/policies',
    '/analytics',
    '/audit-logs',
  ];
  
  // Compliance-only routes (R4)
  const complianceOnlyRoutes = ['/compliance-studio', '/policies', '/multisig'];
  
  if (mode === AppMode.FOCUS) {
    return focusRoutes.some(r => route.startsWith(r));
  }
  
  if (mode === AppMode.WAR_ROOM) {
    // R3 cannot access compliance-only routes
    if (role === Role.R3_INSTITUTION_OPS && complianceOnlyRoutes.some(r => route.startsWith(r))) {
      return false;
    }
    return warRoomRoutes.some(r => route.startsWith(r)) || route === '/';
  }
  
  return false;
}

export function isEndUser(role: Role): boolean {
  return role === Role.R1_END_USER || role === Role.R2_END_USER_PEP;
}

export function isInstitutional(role: Role): boolean {
  return role === Role.R3_INSTITUTION_OPS || role === Role.R4_INSTITUTION_COMPLIANCE;
}

export function canEnforce(role: Role): boolean {
  return role === Role.R4_INSTITUTION_COMPLIANCE;
}

// Role display helpers
export const ROLE_LABELS: Record<Role, string> = {
  [Role.R1_END_USER]: 'End User',
  [Role.R2_END_USER_PEP]: 'End User (Enhanced)',
  [Role.R3_INSTITUTION_OPS]: 'Operations',
  [Role.R4_INSTITUTION_COMPLIANCE]: 'Compliance',
  [Role.R5_PLATFORM_ADMIN]: 'Platform Admin',
  [Role.R6_SUPER_ADMIN]: 'Super Admin',
};

export const ROLE_COLORS: Record<Role, string> = {
  [Role.R1_END_USER]: '#3FB950',      // Green
  [Role.R2_END_USER_PEP]: '#F5A524',  // Amber
  [Role.R3_INSTITUTION_OPS]: '#1A73E8', // Blue
  [Role.R4_INSTITUTION_COMPLIANCE]: '#7C3AED', // Purple
  [Role.R5_PLATFORM_ADMIN]: '#6B7280', // Gray
  [Role.R6_SUPER_ADMIN]: '#E5484D',   // Red
};

export const MODE_LABELS: Record<AppMode, string> = {
  [AppMode.FOCUS]: 'Focus Mode',
  [AppMode.WAR_ROOM]: 'War Room',
};
