'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

function ApiKeysContent() {
  const { profile } = useProfile();
  const [showSecret, setShowSecret] = useState<string | null>(null);

  if (!profile || !['INSTITUTIONAL', 'VASP'].includes(profile.entity_type)) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">API access is only available for INSTITUTIONAL and VASP accounts.</p>
      </div>
    );
  }

  const mockKeys = [
    { id: 'key_1', name: 'Production', key: 'amttp_live_k3y...', created: '2026-01-01', lastUsed: '2 hours ago', status: 'Active' },
    { id: 'key_2', name: 'Development', key: 'amttp_test_d3v...', created: '2026-01-05', lastUsed: '1 day ago', status: 'Active' },
    { id: 'key_3', name: 'CI/CD Pipeline', key: 'amttp_live_c1c...', created: '2026-01-07', lastUsed: 'Never', status: 'Inactive' },
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">🔑 API Keys</h1>
      <p className="text-gray-400 mb-6">Manage API keys for programmatic access</p>

      {/* Rate Limits */}
      <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Rate Limits</h2>
        <div className="grid grid-cols-4 gap-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-400">
              {profile.entity_type === 'VASP' ? '10,000' : '1,000'}
            </p>
            <p className="text-sm text-gray-400">Requests/minute</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-green-400">
              {profile.entity_type === 'VASP' ? '1,000,000' : '100,000'}
            </p>
            <p className="text-sm text-gray-400">Requests/day</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-purple-400">3</p>
            <p className="text-sm text-gray-400">Active Keys</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-yellow-400">10</p>
            <p className="text-sm text-gray-400">Max Keys</p>
          </div>
        </div>
      </div>

      {/* Create Key */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Create New API Key</h2>
        <div className="flex gap-4">
          <input
            type="text"
            placeholder="Key name (e.g., Production, Staging)"
            className="flex-1 bg-gray-700 border border-gray-600 rounded px-4 py-2"
          />
          <select className="bg-gray-700 border border-gray-600 rounded px-4 py-2">
            <option>Full Access</option>
            <option>Read Only</option>
            <option>Evaluate Only</option>
          </select>
          <button className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded font-medium">
            + Generate Key
          </button>
        </div>
      </div>

      {/* Keys List */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">API Keys</h2>
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 text-sm border-b border-gray-700">
              <th className="text-left p-3">Name</th>
              <th className="text-left p-3">Key</th>
              <th className="text-left p-3">Created</th>
              <th className="text-left p-3">Last Used</th>
              <th className="text-center p-3">Status</th>
              <th className="text-center p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {mockKeys.map(key => (
              <tr key={key.id} className="border-b border-gray-700/50">
                <td className="p-3 font-medium">{key.name}</td>
                <td className="p-3 font-mono text-sm">
                  {showSecret === key.id ? 'amttp_live_k3y_f8a9b2c1d4e5...' : key.key}
                  <button
                    onClick={() => setShowSecret(showSecret === key.id ? null : key.id)}
                    className="ml-2 text-gray-500 hover:text-white"
                  >
                    {showSecret === key.id ? '🙈' : '👁️'}
                  </button>
                </td>
                <td className="p-3 text-gray-400">{key.created}</td>
                <td className="p-3 text-gray-400">{key.lastUsed}</td>
                <td className="p-3 text-center">
                  <span className={key.status === 'Active' ? 'text-green-400' : 'text-gray-500'}>
                    {key.status}
                  </span>
                </td>
                <td className="p-3 text-center">
                  <button className="text-gray-400 hover:text-white mr-2">Rotate</button>
                  <button className="text-red-400 hover:text-red-300">Revoke</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* API Docs */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">📚 API Documentation</h2>
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-700 rounded p-4">
            <h3 className="font-medium mb-2">Evaluate Transaction</h3>
            <code className="text-xs text-green-400 block">POST /api/v1/evaluate</code>
            <p className="text-xs text-gray-400 mt-2">Pre-check a transaction for compliance</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <h3 className="font-medium mb-2">Get Profile</h3>
            <code className="text-xs text-green-400 block">GET /api/v1/profiles/:address</code>
            <p className="text-xs text-gray-400 mt-2">Retrieve entity profile and limits</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <h3 className="font-medium mb-2">List Decisions</h3>
            <code className="text-xs text-green-400 block">GET /api/v1/decisions</code>
            <p className="text-xs text-gray-400 mt-2">Query compliance decision history</p>
          </div>
          <div className="bg-gray-700 rounded p-4">
            <h3 className="font-medium mb-2">Webhook Events</h3>
            <code className="text-xs text-green-400 block">POST /api/v1/webhooks</code>
            <p className="text-xs text-gray-400 mt-2">Configure real-time event notifications</p>
          </div>
        </div>
        <div className="mt-4 text-center">
          <a href="#" className="text-blue-400 hover:underline">View Full API Documentation →</a>
        </div>
      </div>
    </div>
  );
}

export default function ApiKeysPage() {
  return (
    <AppLayout>
      <ApiKeysContent />
    </AppLayout>
  );
}
