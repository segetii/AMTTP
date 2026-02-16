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

const MOCK_INSTITUTIONS: Institution[] = []; // MOCKS REMOVED

const MOCK_USERS: ManagedUser[] = []; // MOCKS REMOVED

const MOCK_AUDIT_LOGS: RoleAuditLog[] = []; // MOCKS REMOVED

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
