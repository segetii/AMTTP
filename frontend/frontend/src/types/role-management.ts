/**
 * Role Management Types
 * 
 * Types for institutional role management system
 */

import { Role } from './rbac';

// ═══════════════════════════════════════════════════════════════════════════════
// INSTITUTION TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface Institution {
  id: string;
  name: string;
  type: InstitutionType;
  status: InstitutionStatus;
  createdAt: string;
  updatedAt: string;
  settings: InstitutionSettings;
  metadata: Record<string, unknown>;
}

export enum InstitutionType {
  BANK = 'BANK',
  EXCHANGE = 'EXCHANGE',
  CUSTODIAN = 'CUSTODIAN',
  ASSET_MANAGER = 'ASSET_MANAGER',
  PAYMENT_PROVIDER = 'PAYMENT_PROVIDER',
  REGULATOR = 'REGULATOR',
  OTHER = 'OTHER',
}

export enum InstitutionStatus {
  ACTIVE = 'ACTIVE',
  PENDING = 'PENDING',
  SUSPENDED = 'SUSPENDED',
  INACTIVE = 'INACTIVE',
}

export interface InstitutionSettings {
  maxUsers: number;
  allowedRoles: Role[];
  requireMFA: boolean;
  ipWhitelist?: string[];
  customPolicies?: string[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// USER MANAGEMENT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface ManagedUser {
  id: string;
  email?: string;
  walletAddress?: string;
  displayName: string;
  role: Role;
  institutionId?: string;
  institutionName?: string;
  status: UserStatus;
  createdAt: string;
  updatedAt: string;
  lastLoginAt?: string;
  createdBy: string;
  permissions: UserPermissions;
}

export enum UserStatus {
  ACTIVE = 'ACTIVE',
  PENDING_VERIFICATION = 'PENDING_VERIFICATION',
  SUSPENDED = 'SUSPENDED',
  DEACTIVATED = 'DEACTIVATED',
}

export interface UserPermissions {
  canViewAllTransactions: boolean;
  canEditPolicies: boolean;
  canManageUsers: boolean;
  canAccessAuditLogs: boolean;
  canTriggerEnforcement: boolean;
  canEmergencyOverride: boolean;
  customPermissions?: string[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROLE ASSIGNMENT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface RoleAssignment {
  id: string;
  userId: string;
  role: Role;
  institutionId?: string;
  assignedBy: string;
  assignedAt: string;
  expiresAt?: string;
  reason?: string;
  isActive: boolean;
}

export interface RoleChangeRequest {
  id: string;
  userId: string;
  currentRole: Role;
  requestedRole: Role;
  requestedBy: string;
  requestedAt: string;
  status: RoleChangeStatus;
  approvedBy?: string;
  approvedAt?: string;
  reason: string;
  notes?: string;
}

export enum RoleChangeStatus {
  PENDING = 'PENDING',
  APPROVED = 'APPROVED',
  REJECTED = 'REJECTED',
  EXPIRED = 'EXPIRED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// INVITATION TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface UserInvitation {
  id: string;
  email: string;
  role: Role;
  institutionId?: string;
  invitedBy: string;
  invitedAt: string;
  expiresAt: string;
  status: InvitationStatus;
  acceptedAt?: string;
  token: string;
}

export enum InvitationStatus {
  PENDING = 'PENDING',
  ACCEPTED = 'ACCEPTED',
  EXPIRED = 'EXPIRED',
  REVOKED = 'REVOKED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface RoleAuditLog {
  id: string;
  action: RoleAuditAction;
  targetUserId: string;
  performedBy: string;
  performedAt: string;
  previousRole?: Role;
  newRole?: Role;
  institutionId?: string;
  reason?: string;
  ipAddress?: string;
  userAgent?: string;
}

export enum RoleAuditAction {
  ROLE_ASSIGNED = 'ROLE_ASSIGNED',
  ROLE_CHANGED = 'ROLE_CHANGED',
  ROLE_REVOKED = 'ROLE_REVOKED',
  USER_INVITED = 'USER_INVITED',
  USER_SUSPENDED = 'USER_SUSPENDED',
  USER_REACTIVATED = 'USER_REACTIVATED',
  PERMISSION_GRANTED = 'PERMISSION_GRANTED',
  PERMISSION_REVOKED = 'PERMISSION_REVOKED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function canAssignRole(assignerRole: Role, targetRole: Role): boolean {
  const roleHierarchy: Record<Role, number> = {
    [Role.R1_END_USER]: 1,
    [Role.R2_END_USER_PEP]: 2,
    [Role.R3_INSTITUTION_OPS]: 3,
    [Role.R4_INSTITUTION_COMPLIANCE]: 4,
    [Role.R5_PLATFORM_ADMIN]: 5,
    [Role.R6_SUPER_ADMIN]: 6,
  };
  
  // Super Admin can assign any role
  if (assignerRole === Role.R6_SUPER_ADMIN) {
    return true;
  }
  
  // Platform Admin can assign up to R4
  if (assignerRole === Role.R5_PLATFORM_ADMIN) {
    return roleHierarchy[targetRole] <= 4;
  }
  
  // Compliance can assign up to R3
  if (assignerRole === Role.R4_INSTITUTION_COMPLIANCE) {
    return roleHierarchy[targetRole] <= 3;
  }
  
  return false;
}

export function getAssignableRoles(assignerRole: Role): Role[] {
  const allRoles = [
    Role.R1_END_USER,
    Role.R2_END_USER_PEP,
    Role.R3_INSTITUTION_OPS,
    Role.R4_INSTITUTION_COMPLIANCE,
    Role.R5_PLATFORM_ADMIN,
    Role.R6_SUPER_ADMIN,
  ];
  
  return allRoles.filter(role => canAssignRole(assignerRole, role));
}

export function getRoleDisplayInfo(role: Role): { label: string; description: string; color: string } {
  const roleInfo: Record<Role, { label: string; description: string; color: string }> = {
    [Role.R1_END_USER]: {
      label: 'End User',
      description: 'Basic user with personal wallet access',
      color: 'bg-green-500',
    },
    [Role.R2_END_USER_PEP]: {
      label: 'Enhanced User (PEP)',
      description: 'User with enhanced monitoring requirements',
      color: 'bg-amber-500',
    },
    [Role.R3_INSTITUTION_OPS]: {
      label: 'Institution Ops',
      description: 'Operations team with view-only War Room access',
      color: 'bg-blue-500',
    },
    [Role.R4_INSTITUTION_COMPLIANCE]: {
      label: 'Compliance Officer',
      description: 'Full War Room access with enforcement capabilities',
      color: 'bg-purple-500',
    },
    [Role.R5_PLATFORM_ADMIN]: {
      label: 'Platform Admin',
      description: 'Platform administration and user management',
      color: 'bg-rose-500',
    },
    [Role.R6_SUPER_ADMIN]: {
      label: 'Super Admin',
      description: 'Full system access with emergency override',
      color: 'bg-red-600',
    },
  };
  
  return roleInfo[role];
}

export function getDefaultPermissions(role: Role): UserPermissions {
  const permissionsByRole: Record<Role, UserPermissions> = {
    [Role.R1_END_USER]: {
      canViewAllTransactions: false,
      canEditPolicies: false,
      canManageUsers: false,
      canAccessAuditLogs: false,
      canTriggerEnforcement: false,
      canEmergencyOverride: false,
    },
    [Role.R2_END_USER_PEP]: {
      canViewAllTransactions: false,
      canEditPolicies: false,
      canManageUsers: false,
      canAccessAuditLogs: false,
      canTriggerEnforcement: false,
      canEmergencyOverride: false,
    },
    [Role.R3_INSTITUTION_OPS]: {
      canViewAllTransactions: true,
      canEditPolicies: false,
      canManageUsers: false,
      canAccessAuditLogs: true,
      canTriggerEnforcement: false,
      canEmergencyOverride: false,
    },
    [Role.R4_INSTITUTION_COMPLIANCE]: {
      canViewAllTransactions: true,
      canEditPolicies: true,
      canManageUsers: true,
      canAccessAuditLogs: true,
      canTriggerEnforcement: true,
      canEmergencyOverride: false,
    },
    [Role.R5_PLATFORM_ADMIN]: {
      canViewAllTransactions: true,
      canEditPolicies: true,
      canManageUsers: true,
      canAccessAuditLogs: true,
      canTriggerEnforcement: true,
      canEmergencyOverride: false,
    },
    [Role.R6_SUPER_ADMIN]: {
      canViewAllTransactions: true,
      canEditPolicies: true,
      canManageUsers: true,
      canAccessAuditLogs: true,
      canTriggerEnforcement: true,
      canEmergencyOverride: true,
    },
  };
  
  return permissionsByRole[role];
}
