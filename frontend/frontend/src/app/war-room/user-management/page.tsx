'use client';

import { useState } from 'react';
import Link from 'next/link';

interface User {
  id: string;
  email: string;
  name: string;
  role: 'super_admin' | 'admin' | 'compliance' | 'analyst' | 'approver' | 'viewer';
  status: 'active' | 'inactive' | 'suspended';
  lastLogin: string;
  createdAt: string;
  permissions: string[];
}

const mockUsers: User[] = [
  {
    id: '1',
    email: 'alice@exchange.com',
    name: 'Alice Johnson',
    role: 'super_admin',
    status: 'active',
    lastLogin: '2026-01-31 14:30:00',
    createdAt: '2025-06-01',
    permissions: ['all'],
  },
  {
    id: '2',
    email: 'bob@exchange.com',
    name: 'Bob Smith',
    role: 'compliance',
    status: 'active',
    lastLogin: '2026-01-31 13:00:00',
    createdAt: '2025-07-15',
    permissions: ['view_transactions', 'approve_transfers', 'manage_policies', 'enforcement'],
  },
  {
    id: '3',
    email: 'carol@exchange.com',
    name: 'Carol Williams',
    role: 'analyst',
    status: 'active',
    lastLogin: '2026-01-31 10:00:00',
    createdAt: '2025-09-01',
    permissions: ['view_transactions', 'view_reports', 'view_analytics'],
  },
  {
    id: '4',
    email: 'dave@exchange.com',
    name: 'Dave Brown',
    role: 'approver',
    status: 'active',
    lastLogin: '2026-01-30 16:00:00',
    createdAt: '2025-10-01',
    permissions: ['view_transactions', 'approve_transfers'],
  },
  {
    id: '5',
    email: 'eve@exchange.com',
    name: 'Eve Davis',
    role: 'viewer',
    status: 'suspended',
    lastLogin: '2026-01-15 09:00:00',
    createdAt: '2025-11-01',
    permissions: ['view_transactions'],
  },
];

const roles = [
  { id: 'super_admin', name: 'Super Admin', description: 'Full system access', color: 'bg-red-500/20 text-red-400' },
  { id: 'admin', name: 'Admin', description: 'Administrative access', color: 'bg-orange-500/20 text-orange-400' },
  { id: 'compliance', name: 'Compliance Officer', description: 'Compliance and enforcement', color: 'bg-purple-500/20 text-purple-400' },
  { id: 'analyst', name: 'Analyst', description: 'View and analyze data', color: 'bg-blue-500/20 text-blue-400' },
  { id: 'approver', name: 'Approver', description: 'Approve transactions', color: 'bg-green-500/20 text-green-400' },
  { id: 'viewer', name: 'Viewer', description: 'Read-only access', color: 'bg-slate-500/20 text-slate-400' },
];

export default function UserManagementPage() {
  const [users, setUsers] = useState(mockUsers);
  const [showInvite, setShowInvite] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredUsers = users.filter(u => 
    u.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getRoleInfo = (roleId: string) => roles.find(r => r.id === roleId);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-400';
      case 'inactive': return 'bg-slate-500/20 text-slate-400';
      case 'suspended': return 'bg-red-500/20 text-red-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  const toggleStatus = (id: string) => {
    setUsers(prev => prev.map(u => {
      if (u.id === id) {
        return { ...u, status: u.status === 'active' ? 'suspended' : 'active' };
      }
      return u;
    }));
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-slate-400 hover:text-white">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">User Management</h1>
          <p className="text-slate-400 mt-1">Manage team members and their access permissions</p>
        </div>
        <button 
          onClick={() => setShowInvite(true)}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2"
        >
          <span>+ Invite User</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold">{users.length}</div>
          <div className="text-slate-400 text-sm">Total Users</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-green-400">{users.filter(u => u.status === 'active').length}</div>
          <div className="text-slate-400 text-sm">Active</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-purple-400">{users.filter(u => u.role === 'compliance').length}</div>
          <div className="text-slate-400 text-sm">Compliance Officers</div>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="text-2xl font-bold text-red-400">{users.filter(u => u.status === 'suspended').length}</div>
          <div className="text-slate-400 text-sm">Suspended</div>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Search users by name or email..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="w-full max-w-md bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {/* Users Table */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-700/50">
            <tr>
              <th className="text-left p-4 text-slate-400 font-medium">User</th>
              <th className="text-left p-4 text-slate-400 font-medium">Role</th>
              <th className="text-left p-4 text-slate-400 font-medium">Status</th>
              <th className="text-left p-4 text-slate-400 font-medium">Last Login</th>
              <th className="text-left p-4 text-slate-400 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map(user => {
              const roleInfo = getRoleInfo(user.role);
              return (
                <tr key={user.id} className="border-t border-slate-700 hover:bg-slate-700/30">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-indigo-600 rounded-full flex items-center justify-center font-semibold">
                        {user.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div>
                        <div className="font-medium">{user.name}</div>
                        <div className="text-sm text-slate-400">{user.email}</div>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${roleInfo?.color}`}>
                      {roleInfo?.name}
                    </span>
                  </td>
                  <td className="p-4">
                    <span className={`px-2 py-1 rounded text-xs font-medium capitalize ${getStatusColor(user.status)}`}>
                      {user.status}
                    </span>
                  </td>
                  <td className="p-4 text-slate-400 text-sm">{user.lastLogin}</td>
                  <td className="p-4">
                    <div className="flex gap-2">
                      <button 
                        onClick={() => setSelectedUser(user)}
                        className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-sm"
                      >
                        Edit
                      </button>
                      <button 
                        onClick={() => toggleStatus(user.id)}
                        className={`px-3 py-1 rounded text-sm ${
                          user.status === 'active' 
                            ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30'
                            : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
                        }`}
                      >
                        {user.status === 'active' ? 'Suspend' : 'Activate'}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Invite Modal */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setShowInvite(false)}>
          <div className="bg-slate-800 rounded-xl p-6 max-w-lg w-full mx-4 border border-slate-700" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold mb-4">Invite New User</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-400 mb-1">Email Address</label>
                <input 
                  type="email"
                  placeholder="user@company.com"
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-400 mb-1">Role</label>
                <select className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500">
                  {roles.map(role => (
                    <option key={role.id} value={role.id}>{role.name} - {role.description}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-3 justify-end mt-6">
              <button onClick={() => setShowInvite(false)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">
                Cancel
              </button>
              <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg">
                Send Invite
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
