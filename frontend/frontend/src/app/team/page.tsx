'use client';

import React, { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

function TeamContent() {
  const { profile } = useProfile();

  if (!profile || !['INSTITUTIONAL', 'VASP'].includes(profile.entity_type)) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">Team management is only available for INSTITUTIONAL and VASP accounts.</p>
      </div>
    );
  }

  const [team] = useState<{ name: string; email: string; role: string; status: string }[]>([]);
  const [loading] = useState(false);
  const [error] = useState<string | null>('No team management API configured');

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">👥 Team Management</h1>
      <p className="text-gray-400 mb-6">Manage team members and approval workflows</p>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">
          ⚠ Backend unavailable: {error}
        </div>
      )}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}

      {/* Add Member */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Add Team Member</h2>
        <div className="grid grid-cols-4 gap-4">
          <input
            type="text"
            placeholder="Name"
            className="bg-gray-700 border border-gray-600 rounded px-4 py-2"
          />
          <input
            type="email"
            placeholder="Email"
            className="bg-gray-700 border border-gray-600 rounded px-4 py-2"
          />
          <select className="bg-gray-700 border border-gray-600 rounded px-4 py-2">
            <option>Viewer</option>
            <option>Analyst</option>
            <option>Admin</option>
          </select>
          <button className="bg-blue-600 hover:bg-blue-700 rounded font-medium">
            + Add Member
          </button>
        </div>
      </div>

      {/* Team List */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Team Members</h2>
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 text-sm border-b border-gray-700">
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Email</th>
              <th className="text-left p-3">Role</th>
              <th className="text-center p-3">Status</th>
              <th className="text-center p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {team.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center text-gray-500 py-8">
                  No team members found. Add a member above to get started.
                </td>
              </tr>
            )}
            {team.map((member, i) => (
              <tr key={i} className="border-b border-gray-700">
                <td className="p-3">{member.name}</td>
                <td className="p-3 text-gray-400">{member.email}</td>
                <td className="p-3">{member.role}</td>
                <td className="p-3 text-center">
                  <span className="px-2 py-0.5 rounded text-xs bg-green-500/20 text-green-400">
                    {member.status}
                  </span>
                </td>
                <td className="p-3 text-center text-gray-500">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Approval Rules */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Approval Rules</h2>
        <div className="space-y-3">
          <div className="flex items-center justify-between bg-gray-700 rounded p-3">
            <span>Transactions &lt; 100 ETH</span>
            <span className="text-green-400">Auto-approve if clean</span>
          </div>
          <div className="flex items-center justify-between bg-gray-700 rounded p-3">
            <span>Transactions 100-500 ETH</span>
            <span className="text-blue-400">1 Approver required</span>
          </div>
          <div className="flex items-center justify-between bg-gray-700 rounded p-3">
            <span>Transactions &gt; 500 ETH</span>
            <span className="text-purple-400">2 Approvers + Compliance</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TeamPage() {
  return (
    <AppLayout>
      <TeamContent />
    </AppLayout>
  );
}
