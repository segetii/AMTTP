'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

function VaultContent() {
  const { profile } = useProfile();
  const [selectedTx, setSelectedTx] = useState<string | null>(null);

  if (!profile || profile.entity_type !== 'HIGH_NET_WORTH') {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">Vault access is exclusive to HIGH_NET_WORTH accounts.</p>
      </div>
    );
  }

  const pendingApprovals = [
    { id: 'tx_001', type: 'Transfer', amount: '150 ETH', to: '0x742d...5f3e', required: 3, approved: 2 },
    { id: 'tx_002', type: 'Transfer', amount: '75 ETH', to: '0x8f2a...1c4b', required: 3, approved: 1 },
  ];

  const signers = [
    { address: '0x1234...abcd', name: 'Primary Owner', status: 'Online' },
    { address: '0x5678...efgh', name: 'Family Office', status: 'Offline' },
    { address: '0x9abc...ijkl', name: 'Legal Counsel', status: 'Online' },
    { address: '0xdef0...mnop', name: 'Trust Manager', status: 'Online' },
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">🔐 Multi-Sig Vault</h1>
      <p className="text-gray-400 mb-6">Secure cold storage with multi-signature protection</p>

      {/* Vault Overview */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-gradient-to-br from-yellow-900/50 to-orange-900/50 border border-yellow-700/50 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-yellow-400">1,250 ETH</p>
          <p className="text-sm text-gray-400">Vault Balance</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-blue-400">3 of 4</p>
          <p className="text-sm text-gray-400">Required Signatures</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-green-400">4</p>
          <p className="text-sm text-gray-400">Active Signers</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-purple-400">2</p>
          <p className="text-sm text-gray-400">Pending Approvals</p>
        </div>
      </div>

      {/* Cold Storage Status */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">❄️ Cold Storage Status</h2>
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
              <span className="font-medium">Hardware Wallet A</span>
            </div>
            <p className="text-sm text-gray-400">Ledger Nano X</p>
            <p className="text-lg font-bold text-green-400 mt-2">500 ETH</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
              <span className="font-medium">Hardware Wallet B</span>
            </div>
            <p className="text-sm text-gray-400">Trezor Model T</p>
            <p className="text-lg font-bold text-green-400 mt-2">400 ETH</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-3 h-3 bg-blue-500 rounded-full"></span>
              <span className="font-medium">Bank Safe Deposit</span>
            </div>
            <p className="text-sm text-gray-400">Steel Backup</p>
            <p className="text-lg font-bold text-blue-400 mt-2">350 ETH</p>
          </div>
        </div>
      </div>

      {/* Pending Multi-Sig Transactions */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">⏳ Pending Approvals</h2>
        <div className="space-y-4">
          {pendingApprovals.map(tx => (
            <div
              key={tx.id}
              className={`bg-gray-700 rounded-lg p-4 cursor-pointer border-2 transition-colors ${
                selectedTx === tx.id ? 'border-blue-500' : 'border-transparent'
              }`}
              onClick={() => setSelectedTx(tx.id)}
            >
              <div className="flex justify-between items-center">
                <div>
                  <p className="font-medium">{tx.type}: {tx.amount}</p>
                  <p className="text-sm text-gray-400">To: {tx.to}</p>
                </div>
                <div className="text-right">
                  <p className="text-lg font-bold">
                    <span className={tx.approved >= tx.required ? 'text-green-400' : 'text-yellow-400'}>
                      {tx.approved}
                    </span>
                    <span className="text-gray-500"> / {tx.required}</span>
                  </p>
                  <p className="text-sm text-gray-400">Approvals</p>
                </div>
              </div>
              {selectedTx === tx.id && (
                <div className="mt-4 pt-4 border-t border-gray-600 flex gap-4">
                  <button className="flex-1 bg-green-600 hover:bg-green-700 py-2 rounded font-medium">
                    ✓ Sign & Approve
                  </button>
                  <button className="flex-1 bg-red-600 hover:bg-red-700 py-2 rounded font-medium">
                    ✗ Reject
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Signers */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">👥 Authorized Signers</h2>
          <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
            + Add Signer
          </button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {signers.map(signer => (
            <div key={signer.address} className="bg-gray-700 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="font-medium">{signer.name}</p>
                <p className="text-sm text-gray-400 font-mono">{signer.address}</p>
              </div>
              <span className={`px-2 py-1 rounded text-xs ${
                signer.status === 'Online' ? 'bg-green-900 text-green-300' : 'bg-gray-600 text-gray-400'
              }`}>
                {signer.status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* New Transaction */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">📤 Initiate Vault Transaction</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Recipient Address</label>
            <input
              type="text"
              placeholder="0x..."
              className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Amount (ETH)</label>
            <input
              type="number"
              placeholder="0.0"
              className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
            />
          </div>
        </div>
        <div className="mt-4">
          <label className="block text-sm text-gray-400 mb-1">Transaction Note</label>
          <input
            type="text"
            placeholder="Purpose of this transaction..."
            className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
          />
        </div>
        <div className="mt-4 flex justify-end gap-4">
          <button className="bg-gray-600 hover:bg-gray-500 px-6 py-2 rounded">Cancel</button>
          <button className="bg-yellow-600 hover:bg-yellow-700 px-6 py-2 rounded font-medium">
            🔐 Create Multi-Sig Transaction
          </button>
        </div>
      </div>
    </div>
  );
}

export default function VaultPage() {
  return (
    <AppLayout>
      <VaultContent />
    </AppLayout>
  );
}
