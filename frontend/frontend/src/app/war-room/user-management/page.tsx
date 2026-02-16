'use client';

import { useState, useEffect } from 'react';
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

const roles = [
  { id: 'super_admin', name: 'Super Admin', description: 'Full system access', color: 'bg-red-500/20 text-red-400' },
  { id: 'admin', name: 'Admin', description: 'Administrative access', color: 'bg-orange-500/20 text-orange-400' },
  { id: 'compliance', name: 'Compliance Officer', description: 'Compliance and enforcement', color: 'bg-purple-500/20 text-purple-400' },
  { id: 'analyst', name: 'Analyst', description: 'View and analyze data', color: 'bg-blue-500/20 text-blue-400' },
  { id: 'approver', name: 'Approver', description: 'Approve transactions', color: 'bg-green-500/20 text-green-400' },
  { id: 'viewer', name: 'Viewer', description: 'Read-only access', color: 'bg-slate-500/20 text-mutedText' },
];

export default function UserManagementPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showInvite, setShowInvite] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    fetch('http://127.0.0.1:8007/profiles')
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(data => setUsers(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filteredUsers = users.filter(u => 
    u.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    u.email?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getRoleInfo = (roleId: string) => roles.find(r => r.id === roleId);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'bg-green-500/20 text-green-400';
      case 'inactive': return 'bg-slate-500/20 text-mutedText';
      case 'suspended': return 'bg-red-500/20 text-red-400';
      default: return 'bg-slate-500/20 text-mutedText';
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
    <div className="space-y-6">
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">User Management</h1>
          <p className="text-mutedText mt-1">Manage team members and their access permissions</p>
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
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold">{users.length}</div>
          <div className="text-mutedText text-sm">Total Users</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-green-400">{users.filter(u => u.status === 'active').length}</div>
          <div className="text-mutedText text-sm">Active</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-purple-400">{users.filter(u => u.role === 'compliance').length}</div>
          <div className="text-mutedText text-sm">Compliance Officers</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-red-400">{users.filter(u => u.status === 'suspended').length}</div>
          <div className="text-mutedText text-sm">Suspended</div>
        </div>
      </div>

      {/* Search */}
      <div className="mb-6">
        <input
          type="text"
          placeholder="Search users by name or email..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="w-full max-w-md bg-surface border border-borderSubtle rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
        />
      </div>

      {/* Users Table */}
      <div className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
        <table className="w-full">
          <thead className="bg-slate-700/50">
            <tr>
              <th className="text-left p-4 text-mutedText font-medium">User</th>
              <th className="text-left p-4 text-mutedText font-medium">Role</th>
              <th className="text-left p-4 text-mutedText font-medium">Status</th>
              <th className="text-left p-4 text-mutedText font-medium">Last Login</th>
              <th className="text-left p-4 text-mutedText font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredUsers.map(user => {
              const roleInfo = getRoleInfo(user.role);
              return (
                <tr key={user.id} className="border-t border-borderSubtle hover:bg-slate-700/30">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-indigo-600 rounded-full flex items-center justify-center font-semibold">
                        {user.name.split(' ').map(n => n[0]).join('')}
                      </div>
                      <div>
                        <div className="font-medium">{user.name}</div>
                        <div className="text-sm text-mutedText">{user.email}</div>
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
                  <td className="p-4 text-mutedText text-sm">{user.lastLogin}</td>
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
          <div className="bg-surface rounded-xl p-6 max-w-lg w-full mx-4 border border-borderSubtle" onClick={e => e.stopPropagation()}>
            <h2 className="text-xl font-bold mb-4">Invite New User</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-mutedText mb-1">Email Address</label>
                <input 
                  type="email"
                  placeholder="user@company.com"
                  className="w-full bg-slate-700 border border-borderSubtle rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500"
                />
              </div>
              <div>
                <label className="block text-sm text-mutedText mb-1">Role</label>
                <select className="w-full bg-slate-700 border border-borderSubtle rounded-lg px-4 py-2 focus:outline-none focus:border-indigo-500">
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
