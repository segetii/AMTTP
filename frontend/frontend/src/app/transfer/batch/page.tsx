'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

interface BatchTx {
  id: number;
  to_address: string;
  value_eth: string;
  status: 'pending' | 'checking' | 'approved' | 'blocked' | 'escrow';
  decision?: {
    action: string;
    risk_score: number;
    reasons: string[];
  };
}

function BatchTransferContent() {
  const { profile, address } = useProfile();
  const [transactions, setTransactions] = useState<BatchTx[]>([
    { id: 1, to_address: '', value_eth: '', status: 'pending' }
  ]);
  const [processing, setProcessing] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);

  const addRow = () => {
    setTransactions([
      ...transactions,
      { id: Date.now(), to_address: '', value_eth: '', status: 'pending' }
    ]);
  };

  const removeRow = (id: number) => {
    if (transactions.length > 1) {
      setTransactions(transactions.filter(tx => tx.id !== id));
    }
  };

  const updateRow = (id: number, field: 'to_address' | 'value_eth', value: string) => {
    setTransactions(transactions.map(tx => 
      tx.id === id ? { ...tx, [field]: value } : tx
    ));
  };

  const processBatch = async () => {
    setProcessing(true);
    
    for (let i = 0; i < transactions.length; i++) {
      const tx = transactions[i];
      if (!tx.to_address || !tx.value_eth) continue;
      
      setCurrentIdx(i);
      setTransactions(prev => prev.map((t, idx) => 
        idx === i ? { ...t, status: 'checking' } : t
      ));

      try {
        const res = await fetch(`${ORCHESTRATOR_API}/evaluate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_address: address,
            to_address: tx.to_address,
            value_eth: parseFloat(tx.value_eth)
          })
        });
        const decision = await res.json();
        
        let status: BatchTx['status'] = 'pending';
        if (decision.action === 'APPROVE') status = 'approved';
        else if (decision.action === 'BLOCK') status = 'blocked';
        else if (decision.action === 'ESCROW') status = 'escrow';

        setTransactions(prev => prev.map((t, idx) => 
          idx === i ? { 
            ...t, 
            status,
            decision: {
              action: decision.action,
              risk_score: decision.risk_score,
              reasons: decision.reasons
            }
          } : t
        ));
      } catch (e) {
        console.error('Batch check failed:', e);
      }

      // Small delay between checks
      await new Promise(r => setTimeout(r, 200));
    }

    setProcessing(false);
    setCurrentIdx(-1);
  };

  const getStatusColor = (status: BatchTx['status']) => {
    switch (status) {
      case 'approved': return 'text-green-400';
      case 'blocked': return 'text-red-400';
      case 'escrow': return 'text-yellow-400';
      case 'checking': return 'text-blue-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusIcon = (status: BatchTx['status']) => {
    switch (status) {
      case 'approved': return '✓';
      case 'blocked': return '✗';
      case 'escrow': return '⏳';
      case 'checking': return '⟳';
      default: return '○';
    }
  };

  // Access check
  if (!profile || !['INSTITUTIONAL', 'VASP'].includes(profile.entity_type)) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">
          Batch transfers are only available for INSTITUTIONAL and VASP accounts.
        </p>
        <p className="text-gray-500 text-sm mt-2">
          Current profile: {profile?.entity_type || 'Not connected'}
        </p>
      </div>
    );
  }

  const totalValue = transactions.reduce((sum, tx) => sum + (parseFloat(tx.value_eth) || 0), 0);
  const approvedCount = transactions.filter(tx => tx.status === 'approved').length;
  const blockedCount = transactions.filter(tx => tx.status === 'blocked').length;

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">📦 Batch Transfer</h1>
      <p className="text-gray-400 mb-6">Process multiple transfers with compliance checks</p>

      {/* Summary */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-2xl font-bold">{transactions.length}</p>
          <p className="text-sm text-gray-500">Transactions</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-2xl font-bold">{totalValue.toFixed(4)} ETH</p>
          <p className="text-sm text-gray-500">Total Value</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-2xl font-bold text-green-400">{approvedCount}</p>
          <p className="text-sm text-gray-500">Approved</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4">
          <p className="text-2xl font-bold text-red-400">{blockedCount}</p>
          <p className="text-sm text-gray-500">Blocked</p>
        </div>
      </div>

      {/* Batch Table */}
      <div className="bg-gray-800 rounded-lg p-6">
        <table className="w-full">
          <thead>
            <tr className="text-gray-500 text-sm border-b border-gray-700">
              <th className="text-left py-2 w-8">#</th>
              <th className="text-left py-2">Recipient Address</th>
              <th className="text-left py-2 w-32">Amount (ETH)</th>
              <th className="text-center py-2 w-24">Status</th>
              <th className="text-center py-2 w-20">Risk</th>
              <th className="text-center py-2 w-16">Action</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx, idx) => (
              <tr key={tx.id} className={`border-b border-gray-700/50 ${currentIdx === idx ? 'bg-blue-900/30' : ''}`}>
                <td className="py-2 text-gray-500">{idx + 1}</td>
                <td className="py-2">
                  <input
                    type="text"
                    placeholder="0x..."
                    value={tx.to_address}
                    onChange={(e) => updateRow(tx.id, 'to_address', e.target.value)}
                    disabled={processing}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm disabled:opacity-50"
                  />
                </td>
                <td className="py-2">
                  <input
                    type="number"
                    step="0.001"
                    placeholder="0.00"
                    value={tx.value_eth}
                    onChange={(e) => updateRow(tx.id, 'value_eth', e.target.value)}
                    disabled={processing}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm disabled:opacity-50"
                  />
                </td>
                <td className={`py-2 text-center ${getStatusColor(tx.status)}`}>
                  <span className="text-lg">{getStatusIcon(tx.status)}</span>
                  <span className="ml-1 text-xs">{tx.status}</span>
                </td>
                <td className="py-2 text-center">
                  {tx.decision && (
                    <span className={tx.decision.risk_score > 50 ? 'text-red-400' : 'text-green-400'}>
                      {tx.decision.risk_score.toFixed(0)}%
                    </span>
                  )}
                </td>
                <td className="py-2 text-center">
                  <button
                    onClick={() => removeRow(tx.id)}
                    disabled={processing || transactions.length === 1}
                    className="text-red-400 hover:text-red-300 disabled:opacity-30"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="flex justify-between mt-4">
          <button
            onClick={addRow}
            disabled={processing}
            className="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            + Add Row
          </button>

          <div className="flex gap-2">
            <button
              onClick={() => setTransactions([{ id: 1, to_address: '', value_eth: '', status: 'pending' }])}
              disabled={processing}
              className="bg-gray-600 hover:bg-gray-500 px-4 py-2 rounded text-sm disabled:opacity-50"
            >
              Clear All
            </button>
            <button
              onClick={processBatch}
              disabled={processing || transactions.every(tx => !tx.to_address || !tx.value_eth)}
              className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded font-medium disabled:opacity-50"
            >
              {processing ? `Processing ${currentIdx + 1}/${transactions.length}...` : '🔍 Check All'}
            </button>
          </div>
        </div>
      </div>

      {/* Blocked Transactions Details */}
      {blockedCount > 0 && (
        <div className="mt-6 bg-red-900/30 rounded-lg p-4">
          <h3 className="font-medium text-red-400 mb-2">⚠️ Blocked Transactions</h3>
          {transactions.filter(tx => tx.status === 'blocked').map((tx, idx) => (
            <div key={tx.id} className="text-sm text-gray-300 mb-1">
              <span className="font-mono">{tx.to_address.slice(0, 10)}...</span>
              <span className="mx-2">→</span>
              {tx.decision?.reasons.map((r, i) => (
                <span key={i} className="text-red-300">{r}</span>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Submit Approved */}
      {approvedCount > 0 && !processing && (
        <div className="mt-6 flex justify-end">
          <button className="bg-green-600 hover:bg-green-700 px-6 py-3 rounded font-medium">
            ✓ Submit {approvedCount} Approved Transaction{approvedCount > 1 ? 's' : ''}
          </button>
        </div>
      )}
    </div>
  );
}

export default function BatchTransferPage() {
  return (
    <AppLayout>
      <BatchTransferContent />
    </AppLayout>
  );
}
