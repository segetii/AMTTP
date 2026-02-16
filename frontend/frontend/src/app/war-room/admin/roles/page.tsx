'use client';

/**
 * Role Management Page
 * 
 * Admin interface for managing user roles and permissions
 * Only accessible by R5+ roles (Platform Admin, Super Admin)
 */

import React, { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRoleManagement } from '@/lib/role-management-service';
import { Role, ROLE_LABELS } from '@/types/rbac';
import { 
  ManagedUser, 
  UserStatus,
  RoleAuditAction,
  getAssignableRoles,
  getRoleDisplayInfo,
} from '@/types/role-management';
import WarRoomShell from '@/components/shells/WarRoomShell';

// ═══════════════════════════════════════════════════════════════════════════════
// USER TABLE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function UserTable({ 
  users, 
  onEditRole, 
  onSuspend, 
  onReactivate,
  currentUserRole,
}: {
  users: ManagedUser[];
  onEditRole: (user: ManagedUser) => void;
  onSuspend: (userId: string) => void;
  onReactivate: (userId: string) => void;
  currentUserRole: Role;
}) {
  const getStatusBadge = (status: UserStatus) => {
    const styles: Record<UserStatus, string> = {
      [UserStatus.ACTIVE]: 'bg-green-500/20 text-green-400',
      [UserStatus.PENDING_VERIFICATION]: 'bg-yellow-500/20 text-yellow-400',
      [UserStatus.SUSPENDED]: 'bg-red-500/20 text-red-400',
      [UserStatus.DEACTIVATED]: 'bg-slate-500/20 text-mutedText',
    };
    return styles[status];
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-borderSubtle">
            <th className="text-left py-3 px-4 text-sm font-medium text-mutedText">User</th>
            <th className="text-left py-3 px-4 text-sm font-medium text-mutedText">Role</th>
            <th className="text-left py-3 px-4 text-sm font-medium text-mutedText">Institution</th>
            <th className="text-left py-3 px-4 text-sm font-medium text-mutedText">Status</th>
            <th className="text-left py-3 px-4 text-sm font-medium text-mutedText">Last Login</th>
            <th className="text-right py-3 px-4 text-sm font-medium text-mutedText">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => {
            const roleInfo = getRoleDisplayInfo(user.role);
            return (
              <tr key={user.id} className="border-b border-borderSubtle/50 hover:bg-surface/50">
                <td className="py-3 px-4">
                  <div>
                    <div className="font-medium text-text">{user.displayName}</div>
                    <div className="text-sm text-mutedText">{user.email || user.walletAddress?.slice(0, 10) + '...'}</div>
                  </div>
                </td>
                <td className="py-3 px-4">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${roleInfo.color} bg-opacity-20 text-text`}>
                    <span className={`w-2 h-2 rounded-full ${roleInfo.color}`}></span>
                    {roleInfo.label}
                  </span>
                </td>
                <td className="py-3 px-4 text-slate-300">
                  {user.institutionName || '-'}
                </td>
                <td className="py-3 px-4">
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusBadge(user.status)}`}>
                    {user.status.replace('_', ' ')}
                  </span>
                </td>
                <td className="py-3 px-4 text-mutedText text-sm">
                  {user.lastLoginAt 
                    ? new Date(user.lastLoginAt).toLocaleDateString()
                    : 'Never'
                  }
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => onEditRole(user)}
                      className="px-3 py-1 text-sm text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 rounded transition-colors"
                    >
                      Edit Role
                    </button>
                    {user.status === UserStatus.ACTIVE ? (
                      <button
                        onClick={() => onSuspend(user.id)}
                        className="px-3 py-1 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded transition-colors"
                      >
                        Suspend
                      </button>
                    ) : user.status === UserStatus.SUSPENDED ? (
                      <button
                        onClick={() => onReactivate(user.id)}
                        className="px-3 py-1 text-sm text-green-400 hover:text-green-300 hover:bg-green-500/10 rounded transition-colors"
                      >
                        Reactivate
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROLE EDIT MODAL
// ═══════════════════════════════════════════════════════════════════════════════

function RoleEditModal({
  user,
  currentUserRole,
  onSave,
  onClose,
}: {
  user: ManagedUser;
  currentUserRole: Role;
  onSave: (userId: string, newRole: Role, reason: string) => void;
  onClose: () => void;
}) {
  const [selectedRole, setSelectedRole] = useState<Role>(user.role);
  const [reason, setReason] = useState('');
  const assignableRoles = getAssignableRoles(currentUserRole);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface rounded-xl border border-borderSubtle p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold text-text mb-4">
          Edit Role for {user.displayName}
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Current Role
            </label>
            <div className="text-mutedText">{getRoleDisplayInfo(user.role).label}</div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              New Role
            </label>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value as Role)}
              className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500"
            >
              {assignableRoles.map((role) => {
                const info = getRoleDisplayInfo(role);
                return (
                  <option key={role} value={role}>
                    {info.label} - {info.description}
                  </option>
                );
              })}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Reason for Change
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500 resize-none"
              rows={3}
              placeholder="Provide a reason for this role change..."
            />
          </div>
        </div>
        
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-mutedText hover:text-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(user.id, selectedRole, reason)}
            disabled={selectedRole === user.role || !reason}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-text rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// CREATE USER MODAL
// ═══════════════════════════════════════════════════════════════════════════════

function CreateUserModal({
  institutions,
  currentUserRole,
  onSave,
  onClose,
}: {
  institutions: { id: string; name: string }[];
  currentUserRole: Role;
  onSave: (data: { displayName: string; email: string; role: Role; institutionId?: string }) => void;
  onClose: () => void;
}) {
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [selectedRole, setSelectedRole] = useState<Role>(Role.R1_END_USER);
  const [institutionId, setInstitutionId] = useState<string>('');
  const assignableRoles = getAssignableRoles(currentUserRole);

  const needsInstitution = [Role.R3_INSTITUTION_OPS, Role.R4_INSTITUTION_COMPLIANCE].includes(selectedRole);

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-surface rounded-xl border border-borderSubtle p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold text-text mb-4">
          Create New User
        </h3>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Display Name
            </label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500"
              placeholder="John Doe"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500"
              placeholder="john@company.com"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Role
            </label>
            <select
              value={selectedRole}
              onChange={(e) => setSelectedRole(e.target.value as Role)}
              className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500"
            >
              {assignableRoles.map((role) => {
                const info = getRoleDisplayInfo(role);
                return (
                  <option key={role} value={role}>
                    {info.label}
                  </option>
                );
              })}
            </select>
          </div>
          
          {needsInstitution && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Institution
              </label>
              <select
                value={institutionId}
                onChange={(e) => setInstitutionId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">Select Institution...</option>
                {institutions.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        
        <div className="flex justify-end gap-3 mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 text-mutedText hover:text-text transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave({ displayName, email, role: selectedRole, institutionId: institutionId || undefined })}
            disabled={!displayName || !email || (needsInstitution && !institutionId)}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-text rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Create User
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function RoleManagementContent() {
  const { role: currentUserRole } = useAuth();
  const {
    users,
    institutions,
    auditLogs,
    isLoading,
    error,
    assignRole,
    createUser,
    suspendUser,
    reactivateUser,
    getAuditLogs,
  } = useRoleManagement(currentUserRole || Role.R1_END_USER);

  const [activeTab, setActiveTab] = useState<'users' | 'audit'>('users');
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [filterInstitution, setFilterInstitution] = useState<string>('all');

  // Check access
  if (!currentUserRole || ![Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN].includes(currentUserRole)) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
            <svg className="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-text mb-2">Access Denied</h2>
          <p className="text-mutedText">You need Compliance Officer (R4) or higher role to access this page.</p>
        </div>
      </div>
    );
  }

  const filteredUsers = filterInstitution === 'all' 
    ? users 
    : users.filter(u => u.institutionId === filterInstitution);

  const handleRoleSave = async (userId: string, newRole: Role, reason: string) => {
    const result = await assignRole(userId, newRole, undefined, reason);
    if (result.success) {
      setEditingUser(null);
    }
  };

  const handleCreateUser = async (data: { displayName: string; email: string; role: Role; institutionId?: string }) => {
    const result = await createUser(data);
    if (result.success) {
      setShowCreateModal(false);
    }
  };

  const handleSuspend = async (userId: string) => {
    if (confirm('Are you sure you want to suspend this user?')) {
      await suspendUser(userId, 'Suspended by admin');
    }
  };

  const handleReactivate = async (userId: string) => {
    await reactivateUser(userId, 'Reactivated by admin');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text">Role Management</h1>
          <p className="text-mutedText mt-1">Manage user roles and permissions across institutions</p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-text rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Create User
        </button>
      </div>

      {/* Current Role Badge */}
      <div className="flex items-center gap-3 p-4 bg-surface/50 rounded-lg border border-borderSubtle">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-red-500 to-rose-600 flex items-center justify-center">
          <svg className="w-5 h-5 text-text" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        </div>
        <div>
          <div className="text-sm text-mutedText">Your Role</div>
          <div className="font-semibold text-text">{currentUserRole ? getRoleDisplayInfo(currentUserRole).label : 'Unknown'}</div>
        </div>
        <div className="ml-auto text-sm text-mutedText">
          Can assign roles: {getAssignableRoles(currentUserRole || Role.R1_END_USER).map(r => getRoleDisplayInfo(r).label).join(', ')}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 border-b border-borderSubtle">
        <button
          onClick={() => setActiveTab('users')}
          className={`pb-3 px-1 text-sm font-medium transition-colors ${
            activeTab === 'users'
              ? 'text-indigo-400 border-b-2 border-indigo-400'
              : 'text-mutedText hover:text-text'
          }`}
        >
          Users ({users.length})
        </button>
        <button
          onClick={() => setActiveTab('audit')}
          className={`pb-3 px-1 text-sm font-medium transition-colors ${
            activeTab === 'audit'
              ? 'text-indigo-400 border-b-2 border-indigo-400'
              : 'text-mutedText hover:text-text'
          }`}
        >
          Audit Log ({auditLogs.length})
        </button>
      </div>

      {/* Content */}
      {activeTab === 'users' && (
        <div className="bg-surface/50 rounded-xl border border-borderSubtle">
          {/* Filter */}
          <div className="p-4 border-b border-borderSubtle">
            <select
              value={filterInstitution}
              onChange={(e) => setFilterInstitution(e.target.value)}
              className="px-3 py-2 bg-slate-700 border border-borderSubtle rounded-lg text-text text-sm"
            >
              <option value="all">All Institutions</option>
              {institutions.map(inst => (
                <option key={inst.id} value={inst.id}>{inst.name}</option>
              ))}
              <option value="">No Institution (End Users)</option>
            </select>
          </div>
          
          <UserTable
            users={filteredUsers}
            onEditRole={setEditingUser}
            onSuspend={handleSuspend}
            onReactivate={handleReactivate}
            currentUserRole={currentUserRole || Role.R1_END_USER}
          />
        </div>
      )}

      {activeTab === 'audit' && (
        <div className="bg-surface/50 rounded-xl border border-borderSubtle">
          <div className="divide-y divide-slate-700">
            {auditLogs.map((log) => (
              <div key={log.id} className="p-4 hover:bg-slate-700/30">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-text">
                        {log.action.replace(/_/g, ' ')}
                      </span>
                      {log.newRole && (
                        <span className={`px-2 py-0.5 rounded-full text-xs ${getRoleDisplayInfo(log.newRole).color} bg-opacity-20 text-text`}>
                          {getRoleDisplayInfo(log.newRole).label}
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-mutedText mt-1">
                      Target: {log.targetUserId} • By: {log.performedBy}
                    </div>
                    {log.reason && (
                      <div className="text-sm text-mutedText mt-1">
                        Reason: {log.reason}
                      </div>
                    )}
                  </div>
                  <div className="text-sm text-mutedText">
                    {new Date(log.performedAt).toLocaleString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modals */}
      {editingUser && (
        <RoleEditModal
          user={editingUser}
          currentUserRole={currentUserRole || Role.R1_END_USER}
          onSave={handleRoleSave}
          onClose={() => setEditingUser(null)}
        />
      )}

      {showCreateModal && (
        <CreateUserModal
          institutions={institutions}
          currentUserRole={currentUserRole || Role.R1_END_USER}
          onSave={handleCreateUser}
          onClose={() => setShowCreateModal(false)}
        />
      )}
    </div>
  );
}

export default function RoleManagementPage() {
  return (
    <WarRoomShell>
      <RoleManagementContent />
    </WarRoomShell>
  );
}
