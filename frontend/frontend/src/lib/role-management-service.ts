/**
 * Role Management Service
 * 
 * Service for managing user roles in institutional contexts
 */

'use client';

import { useState, useCallback } from 'react';
import { Role } from '@/types/rbac';
import {
  ManagedUser,
  UserStatus,
  Institution,
  InstitutionType,
  InstitutionStatus,
  RoleAssignment,
  RoleChangeRequest,
  RoleChangeStatus,
  UserInvitation,
  InvitationStatus,
  RoleAuditLog,
  RoleAuditAction,
  UserPermissions,
  getDefaultPermissions,
  canAssignRole,
} from '@/types/role-management';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_INSTITUTIONS: Institution[] = [
  {
    id: 'inst_001',
    name: 'Acme Bank',
    type: InstitutionType.BANK,
    status: InstitutionStatus.ACTIVE,
    createdAt: '2024-01-15T10:00:00Z',
    updatedAt: '2024-06-20T14:30:00Z',
    settings: {
      maxUsers: 100,
      allowedRoles: [Role.R3_INSTITUTION_OPS, Role.R4_INSTITUTION_COMPLIANCE],
      requireMFA: true,
    },
    metadata: {},
  },
  {
    id: 'inst_002',
    name: 'CryptoExchange Pro',
    type: InstitutionType.EXCHANGE,
    status: InstitutionStatus.ACTIVE,
    createdAt: '2024-03-01T09:00:00Z',
    updatedAt: '2024-07-15T11:00:00Z',
    settings: {
      maxUsers: 50,
      allowedRoles: [Role.R3_INSTITUTION_OPS, Role.R4_INSTITUTION_COMPLIANCE],
      requireMFA: true,
    },
    metadata: {},
  },
];

const MOCK_USERS: ManagedUser[] = [
  {
    id: 'user_001',
    email: 'alice@acmebank.com',
    walletAddress: '0x1234567890abcdef1234567890abcdef12345678',
    displayName: 'Alice Johnson',
    role: Role.R4_INSTITUTION_COMPLIANCE,
    institutionId: 'inst_001',
    institutionName: 'Acme Bank',
    status: UserStatus.ACTIVE,
    createdAt: '2024-02-10T08:00:00Z',
    updatedAt: '2024-06-15T16:00:00Z',
    lastLoginAt: '2024-07-20T09:30:00Z',
    createdBy: 'admin_001',
    permissions: getDefaultPermissions(Role.R4_INSTITUTION_COMPLIANCE),
  },
  {
    id: 'user_002',
    email: 'bob@acmebank.com',
    walletAddress: '0xabcdef1234567890abcdef1234567890abcdef12',
    displayName: 'Bob Smith',
    role: Role.R3_INSTITUTION_OPS,
    institutionId: 'inst_001',
    institutionName: 'Acme Bank',
    status: UserStatus.ACTIVE,
    createdAt: '2024-03-05T10:00:00Z',
    updatedAt: '2024-05-20T14:00:00Z',
    lastLoginAt: '2024-07-19T14:45:00Z',
    createdBy: 'user_001',
    permissions: getDefaultPermissions(Role.R3_INSTITUTION_OPS),
  },
  {
    id: 'user_003',
    email: 'carol@cryptoexchange.io',
    walletAddress: '0x9876543210fedcba9876543210fedcba98765432',
    displayName: 'Carol Davis',
    role: Role.R4_INSTITUTION_COMPLIANCE,
    institutionId: 'inst_002',
    institutionName: 'CryptoExchange Pro',
    status: UserStatus.ACTIVE,
    createdAt: '2024-04-12T11:00:00Z',
    updatedAt: '2024-07-01T09:00:00Z',
    lastLoginAt: '2024-07-21T08:00:00Z',
    createdBy: 'admin_001',
    permissions: getDefaultPermissions(Role.R4_INSTITUTION_COMPLIANCE),
  },
  {
    id: 'user_004',
    email: 'david@personal.com',
    walletAddress: '0xfedcba9876543210fedcba9876543210fedcba98',
    displayName: 'David Wilson',
    role: Role.R1_END_USER,
    status: UserStatus.ACTIVE,
    createdAt: '2024-05-01T15:00:00Z',
    updatedAt: '2024-05-01T15:00:00Z',
    lastLoginAt: '2024-07-18T20:00:00Z',
    createdBy: 'self',
    permissions: getDefaultPermissions(Role.R1_END_USER),
  },
];

const MOCK_AUDIT_LOGS: RoleAuditLog[] = [
  {
    id: 'audit_001',
    action: RoleAuditAction.ROLE_ASSIGNED,
    targetUserId: 'user_001',
    performedBy: 'admin_001',
    performedAt: '2024-02-10T08:00:00Z',
    newRole: Role.R4_INSTITUTION_COMPLIANCE,
    institutionId: 'inst_001',
    reason: 'Initial role assignment for compliance officer',
  },
  {
    id: 'audit_002',
    action: RoleAuditAction.USER_INVITED,
    targetUserId: 'user_002',
    performedBy: 'user_001',
    performedAt: '2024-03-05T10:00:00Z',
    newRole: Role.R3_INSTITUTION_OPS,
    institutionId: 'inst_001',
    reason: 'Invited as operations team member',
  },
  {
    id: 'audit_003',
    action: RoleAuditAction.ROLE_CHANGED,
    targetUserId: 'user_002',
    performedBy: 'user_001',
    performedAt: '2024-05-20T14:00:00Z',
    previousRole: Role.R1_END_USER,
    newRole: Role.R3_INSTITUTION_OPS,
    institutionId: 'inst_001',
    reason: 'Promoted to operations team',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useRoleManagement(currentUserRole: Role) {
  const [users, setUsers] = useState<ManagedUser[]>(MOCK_USERS);
  const [institutions, setInstitutions] = useState<Institution[]>(MOCK_INSTITUTIONS);
  const [auditLogs, setAuditLogs] = useState<RoleAuditLog[]>(MOCK_AUDIT_LOGS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Get users for a specific institution
  const getUsersByInstitution = useCallback((institutionId: string) => {
    return users.filter(u => u.institutionId === institutionId);
  }, [users]);

  // Get all users (for super admin)
  const getAllUsers = useCallback(() => {
    return users;
  }, [users]);

  // Get user by ID
  const getUserById = useCallback((userId: string) => {
    return users.find(u => u.id === userId);
  }, [users]);

  // Assign role to user
  const assignRole = useCallback(async (
    userId: string,
    newRole: Role,
    institutionId?: string,
    reason?: string
  ): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);
    setError(null);

    try {
      // Check if current user can assign this role
      if (!canAssignRole(currentUserRole, newRole)) {
        throw new Error('You do not have permission to assign this role');
      }

      const user = users.find(u => u.id === userId);
      if (!user) {
        throw new Error('User not found');
      }

      const previousRole = user.role;

      // Update user
      setUsers(prev => prev.map(u => {
        if (u.id === userId) {
          return {
            ...u,
            role: newRole,
            institutionId: institutionId || u.institutionId,
            permissions: getDefaultPermissions(newRole),
            updatedAt: new Date().toISOString(),
          };
        }
        return u;
      }));

      // Add audit log
      const auditEntry: RoleAuditLog = {
        id: `audit_${Date.now()}`,
        action: previousRole ? RoleAuditAction.ROLE_CHANGED : RoleAuditAction.ROLE_ASSIGNED,
        targetUserId: userId,
        performedBy: 'current_user', // Would be actual user ID
        performedAt: new Date().toISOString(),
        previousRole,
        newRole,
        institutionId,
        reason,
      };
      setAuditLogs(prev => [auditEntry, ...prev]);

      setIsLoading(false);
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to assign role';
      setError(message);
      setIsLoading(false);
      return { success: false, error: message };
    }
  }, [currentUserRole, users]);

  // Create new user
  const createUser = useCallback(async (
    userData: {
      email?: string;
      walletAddress?: string;
      displayName: string;
      role: Role;
      institutionId?: string;
    }
  ): Promise<{ success: boolean; user?: ManagedUser; error?: string }> => {
    setIsLoading(true);
    setError(null);

    try {
      // Check if current user can assign this role
      if (!canAssignRole(currentUserRole, userData.role)) {
        throw new Error('You do not have permission to create a user with this role');
      }

      const institution = userData.institutionId 
        ? institutions.find(i => i.id === userData.institutionId)
        : undefined;

      const newUser: ManagedUser = {
        id: `user_${Date.now()}`,
        email: userData.email,
        walletAddress: userData.walletAddress,
        displayName: userData.displayName,
        role: userData.role,
        institutionId: userData.institutionId,
        institutionName: institution?.name,
        status: UserStatus.ACTIVE,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        createdBy: 'current_user',
        permissions: getDefaultPermissions(userData.role),
      };

      setUsers(prev => [...prev, newUser]);

      // Add audit log
      const auditEntry: RoleAuditLog = {
        id: `audit_${Date.now()}`,
        action: RoleAuditAction.ROLE_ASSIGNED,
        targetUserId: newUser.id,
        performedBy: 'current_user',
        performedAt: new Date().toISOString(),
        newRole: userData.role,
        institutionId: userData.institutionId,
        reason: 'New user created',
      };
      setAuditLogs(prev => [auditEntry, ...prev]);

      setIsLoading(false);
      return { success: true, user: newUser };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create user';
      setError(message);
      setIsLoading(false);
      return { success: false, error: message };
    }
  }, [currentUserRole, institutions]);

  // Suspend user
  const suspendUser = useCallback(async (
    userId: string,
    reason?: string
  ): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);

    try {
      setUsers(prev => prev.map(u => {
        if (u.id === userId) {
          return { ...u, status: UserStatus.SUSPENDED, updatedAt: new Date().toISOString() };
        }
        return u;
      }));

      const auditEntry: RoleAuditLog = {
        id: `audit_${Date.now()}`,
        action: RoleAuditAction.USER_SUSPENDED,
        targetUserId: userId,
        performedBy: 'current_user',
        performedAt: new Date().toISOString(),
        reason,
      };
      setAuditLogs(prev => [auditEntry, ...prev]);

      setIsLoading(false);
      return { success: true };
    } catch (err) {
      setIsLoading(false);
      return { success: false, error: 'Failed to suspend user' };
    }
  }, []);

  // Reactivate user
  const reactivateUser = useCallback(async (
    userId: string,
    reason?: string
  ): Promise<{ success: boolean; error?: string }> => {
    setIsLoading(true);

    try {
      setUsers(prev => prev.map(u => {
        if (u.id === userId) {
          return { ...u, status: UserStatus.ACTIVE, updatedAt: new Date().toISOString() };
        }
        return u;
      }));

      const auditEntry: RoleAuditLog = {
        id: `audit_${Date.now()}`,
        action: RoleAuditAction.USER_REACTIVATED,
        targetUserId: userId,
        performedBy: 'current_user',
        performedAt: new Date().toISOString(),
        reason,
      };
      setAuditLogs(prev => [auditEntry, ...prev]);

      setIsLoading(false);
      return { success: true };
    } catch (err) {
      setIsLoading(false);
      return { success: false, error: 'Failed to reactivate user' };
    }
  }, []);

  // Get audit logs
  const getAuditLogs = useCallback((filters?: {
    userId?: string;
    institutionId?: string;
    action?: RoleAuditAction;
  }) => {
    let filtered = auditLogs;
    
    if (filters?.userId) {
      filtered = filtered.filter(l => l.targetUserId === filters.userId);
    }
    if (filters?.institutionId) {
      filtered = filtered.filter(l => l.institutionId === filters.institutionId);
    }
    if (filters?.action) {
      filtered = filtered.filter(l => l.action === filters.action);
    }
    
    return filtered;
  }, [auditLogs]);

  return {
    users,
    institutions,
    auditLogs,
    isLoading,
    error,
    getUsersByInstitution,
    getAllUsers,
    getUserById,
    assignRole,
    createUser,
    suspendUser,
    reactivateUser,
    getAuditLogs,
  };
}
