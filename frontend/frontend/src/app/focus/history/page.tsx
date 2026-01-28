'use client';

/**
 * Focus Mode - History Page
 * 
 * Transaction history for end users
 * Simple list view, no charts or analytics
 */

import React, { useState } from 'react';
import FocusModeShell from '@/components/shells/FocusModeShell';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface Transaction {
  id: string;
  type: 'sent' | 'received';
  address: string;
  amount: string;
  currency: string;
  status: 'completed' | 'pending' | 'escrow' | 'cancelled';
  timestamp: string;
  date: string;
  trustVerdict?: 'passed' | 'caution';
}

type FilterType = 'all' | 'sent' | 'received' | 'escrow';

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

const MOCK_TRANSACTIONS: Transaction[] = [
  {
    id: '1',
    type: 'sent',
    address: '0x1234567890abcdef1234567890abcdef12345678',
    amount: '0.5',
    currency: 'ETH',
    status: 'completed',
    timestamp: '2 hours ago',
    date: 'Today',
    trustVerdict: 'passed',
  },
  {
    id: '2',
    type: 'received',
    address: '0xabcdef1234567890abcdef1234567890abcdef12',
    amount: '1,000',
    currency: 'USDC',
    status: 'completed',
    timestamp: '5 hours ago',
    date: 'Today',
    trustVerdict: 'passed',
  },
  {
    id: '3',
    type: 'sent',
    address: '0x9876543210fedcba9876543210fedcba98765432',
    amount: '0.25',
    currency: 'ETH',
    status: 'escrow',
    timestamp: '1 day ago',
    date: 'Yesterday',
    trustVerdict: 'caution',
  },
  {
    id: '4',
    type: 'received',
    address: '0xfedcba9876543210fedcba9876543210fedcba98',
    amount: '500',
    currency: 'USDC',
    status: 'completed',
    timestamp: '2 days ago',
    date: 'Dec 15',
    trustVerdict: 'passed',
  },
  {
    id: '5',
    type: 'sent',
    address: '0x111122223333444455556666777788889999aaaa',
    amount: '0.1',
    currency: 'ETH',
    status: 'cancelled',
    timestamp: '3 days ago',
    date: 'Dec 14',
    trustVerdict: 'caution',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function TransactionCard({ tx }: { tx: Transaction }) {
  const statusConfig = {
    completed: { label: 'Completed', color: 'text-green-700', bg: 'bg-green-100' },
    pending: { label: 'Pending', color: 'text-amber-700', bg: 'bg-amber-100' },
    escrow: { label: 'In Escrow', color: 'text-blue-700', bg: 'bg-blue-100' },
    cancelled: { label: 'Cancelled', color: 'text-gray-500', bg: 'bg-gray-100' },
  };
  
  const status = statusConfig[tx.status];
  
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
            tx.type === 'sent' ? 'bg-red-100' : 'bg-green-100'
          }`}>
            {tx.type === 'sent' ? (
              <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
            )}
          </div>
          <div>
            <div className="font-medium text-gray-900">
              {tx.type === 'sent' ? 'Sent to' : 'Received from'}
            </div>
            <div className="font-mono text-sm text-gray-500">
              {tx.address.slice(0, 8)}...{tx.address.slice(-6)}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className={`font-semibold ${tx.type === 'sent' ? 'text-red-600' : 'text-green-600'}`}>
            {tx.type === 'sent' ? '-' : '+'}{tx.amount} {tx.currency}
          </div>
          <span className={`text-xs px-2 py-0.5 rounded-full ${status.bg} ${status.color}`}>
            {status.label}
          </span>
        </div>
      </div>
      
      <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between text-sm">
        <span className="text-gray-500">{tx.timestamp}</span>
        {tx.trustVerdict && (
          <span className={`flex items-center gap-1 ${
            tx.trustVerdict === 'passed' ? 'text-green-600' : 'text-amber-600'
          }`}>
            {tx.trustVerdict === 'passed' ? (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Trust verified
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                Used escrow
              </>
            )}
          </span>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function FocusHistoryPage() {
  const [filter, setFilter] = useState<FilterType>('all');
  
  const filteredTransactions = MOCK_TRANSACTIONS.filter(tx => {
    if (filter === 'all') return true;
    if (filter === 'sent') return tx.type === 'sent';
    if (filter === 'received') return tx.type === 'received';
    if (filter === 'escrow') return tx.status === 'escrow';
    return true;
  });
  
  // Group by date
  const groupedByDate: Record<string, Transaction[]> = {};
  filteredTransactions.forEach(tx => {
    if (!groupedByDate[tx.date]) {
      groupedByDate[tx.date] = [];
    }
    groupedByDate[tx.date].push(tx);
  });
  
  const filterButtons: { key: FilterType; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'sent', label: 'Sent' },
    { key: 'received', label: 'Received' },
    { key: 'escrow', label: 'Escrow' },
  ];
  
  return (
    <FocusModeShell>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Transaction History</h1>
          <p className="text-gray-500 mt-1">Your recent activity</p>
        </div>
        
        {/* Filters */}
        <div className="flex gap-2 overflow-x-auto pb-2">
          {filterButtons.map((btn) => (
            <button
              key={btn.key}
              onClick={() => setFilter(btn.key)}
              className={`
                px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-colors
                ${filter === btn.key 
                  ? 'bg-indigo-600 text-white' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }
              `}
            >
              {btn.label}
            </button>
          ))}
        </div>
        
        {/* Transaction Groups */}
        {Object.entries(groupedByDate).length > 0 ? (
          <div className="space-y-6">
            {Object.entries(groupedByDate).map(([date, transactions]) => (
              <div key={date}>
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
                  {date}
                </h2>
                <div className="space-y-3">
                  {transactions.map((tx) => (
                    <TransactionCard key={tx.id} tx={tx} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-gray-50 rounded-xl p-8 text-center text-gray-500">
            <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
            <p>No transactions found</p>
            {filter !== 'all' && (
              <button
                onClick={() => setFilter('all')}
                className="mt-2 text-indigo-600 hover:text-indigo-700 text-sm"
              >
                Show all transactions
              </button>
            )}
          </div>
        )}
      </div>
    </FocusModeShell>
  );
}
