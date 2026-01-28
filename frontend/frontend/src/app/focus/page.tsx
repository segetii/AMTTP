'use client';

/**
 * Focus Mode - Home Page
 * 
 * Clean, minimal dashboard for end users (R1/R2)
 * 
 * Features:
 * - Quick actions (Send, Check Trust)
 * - Recent transactions (simple list, no charts)
 * - Trust status summary (qualitative)
 */

import React from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth-context';
import FocusModeShell from '@/components/shells/FocusModeShell';

// ═══════════════════════════════════════════════════════════════════════════════
// QUICK ACTION CARD
// ═══════════════════════════════════════════════════════════════════════════════

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  description: string;
  href: string;
  variant: 'primary' | 'secondary';
}

function QuickAction({ icon, label, description, href, variant }: QuickActionProps) {
  return (
    <Link
      href={href}
      className={`
        flex items-center gap-4 p-4 rounded-xl transition-all
        ${variant === 'primary' 
          ? 'bg-gradient-to-r from-indigo-500 to-purple-600 text-white hover:from-indigo-600 hover:to-purple-700 shadow-lg shadow-indigo-200' 
          : 'bg-white border border-gray-200 hover:border-indigo-300 hover:shadow-md'
        }
      `}
    >
      <div className={`
        w-12 h-12 rounded-lg flex items-center justify-center
        ${variant === 'primary' ? 'bg-white/20' : 'bg-indigo-50'}
      `}>
        {icon}
      </div>
      <div>
        <h3 className={`font-semibold ${variant === 'primary' ? 'text-white' : 'text-gray-900'}`}>
          {label}
        </h3>
        <p className={`text-sm ${variant === 'primary' ? 'text-white/80' : 'text-gray-500'}`}>
          {description}
        </p>
      </div>
    </Link>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// RECENT TRANSACTION ROW
// ═══════════════════════════════════════════════════════════════════════════════

interface Transaction {
  id: string;
  type: 'sent' | 'received';
  address: string;
  amount: string;
  currency: string;
  status: 'completed' | 'pending' | 'escrow';
  timestamp: string;
}

function TransactionRow({ tx }: { tx: Transaction }) {
  const statusColors = {
    completed: 'bg-green-100 text-green-700',
    pending: 'bg-amber-100 text-amber-700',
    escrow: 'bg-blue-100 text-blue-700',
  };
  
  const statusLabels = {
    completed: 'Completed',
    pending: 'Pending',
    escrow: 'In Escrow',
  };
  
  return (
    <div className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors">
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
            {tx.type === 'sent' ? 'Sent to' : 'Received from'} {tx.address.slice(0, 6)}...{tx.address.slice(-4)}
          </div>
          <div className="text-xs text-gray-500">{tx.timestamp}</div>
        </div>
      </div>
      <div className="text-right">
        <div className={`font-semibold ${tx.type === 'sent' ? 'text-red-600' : 'text-green-600'}`}>
          {tx.type === 'sent' ? '-' : '+'}{tx.amount} {tx.currency}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${statusColors[tx.status]}`}>
          {statusLabels[tx.status]}
        </span>
      </div>
    </div>
  );
}

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
  },
  {
    id: '2',
    type: 'received',
    address: '0xabcdef1234567890abcdef1234567890abcdef12',
    amount: '1,000',
    currency: 'USDC',
    status: 'completed',
    timestamp: 'Yesterday',
  },
  {
    id: '3',
    type: 'sent',
    address: '0x9876543210fedcba9876543210fedcba98765432',
    amount: '0.25',
    currency: 'ETH',
    status: 'escrow',
    timestamp: '3 days ago',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function FocusHomePage() {
  const { roleLabel, session } = useAuth();
  
  return (
    <FocusModeShell>
      <div className="space-y-6">
        {/* Welcome Section */}
        <div className="text-center py-4">
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome back
          </h1>
          <p className="text-gray-500 mt-1">
            Your transactions are protected by AMTTP
          </p>
        </div>
        
        {/* Trust Status Banner */}
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
              <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <div className="font-semibold text-green-800">Account Protected</div>
              <div className="text-sm text-green-600">All systems operational</div>
            </div>
          </div>
        </div>
        
        {/* Quick Actions */}
        <div className="space-y-3">
          <QuickAction
            icon={
              <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            }
            label="Send"
            description="Transfer funds securely"
            href="/focus/transfer"
            variant="primary"
          />
          
          <QuickAction
            icon={
              <svg className="w-6 h-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            }
            label="Check Address"
            description="Verify a counterparty before transacting"
            href="/focus/trust"
            variant="secondary"
          />
        </div>
        
        {/* Recent Transactions */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <h2 className="font-semibold text-gray-900">Recent Activity</h2>
            <Link href="/focus/history" className="text-sm text-indigo-600 hover:text-indigo-700">
              View all
            </Link>
          </div>
          
          <div className="divide-y divide-gray-100">
            {MOCK_TRANSACTIONS.map((tx) => (
              <TransactionRow key={tx.id} tx={tx} />
            ))}
          </div>
          
          {MOCK_TRANSACTIONS.length === 0 && (
            <div className="p-8 text-center text-gray-500">
              <svg className="w-12 h-12 mx-auto mb-3 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <p>No recent transactions</p>
            </div>
          )}
        </div>
        
        {/* Help Link */}
        <div className="text-center py-4">
          <a href="#" className="text-sm text-gray-500 hover:text-gray-700">
            Need help? Contact support
          </a>
        </div>
      </div>
    </FocusModeShell>
  );
}
