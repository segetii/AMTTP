'use client';

/**
 * Investigation Hub Page
 * Main entry point for address and transaction investigations
 */

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function InvestigatePage() {
  const router = useRouter();
  const [searchAddress, setSearchAddress] = useState('');
  const [searchType, setSearchType] = useState<'address' | 'transaction'>('address');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchAddress.trim()) {
      if (searchType === 'address') {
        router.push(`/investigate/${searchAddress.trim()}`);
      } else {
        // For transaction search, could go to a different route
        router.push(`/investigate/${searchAddress.trim()}`);
      }
    }
  };

  // Recent investigations (mock data)
  const recentInvestigations = [
    { address: '0x1234...5678', risk: 'high', date: '2026-01-22', status: 'Open' },
    { address: '0xabcd...ef01', risk: 'medium', date: '2026-01-21', status: 'Resolved' },
    { address: '0x9876...5432', risk: 'low', date: '2026-01-20', status: 'Monitoring' },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-slate-400 hover:text-white transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
            </Link>
            <h1 className="text-xl font-semibold text-white">Investigation Hub</h1>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 text-sm">
              War Room
            </span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Search Section */}
        <div className="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-6 mb-8">
          <h2 className="text-lg font-semibold text-white mb-4">Search Entity</h2>
          
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="flex gap-4">
              <button
                type="button"
                onClick={() => setSearchType('address')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  searchType === 'address'
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                Address
              </button>
              <button
                type="button"
                onClick={() => setSearchType('transaction')}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  searchType === 'transaction'
                    ? 'bg-indigo-500 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                Transaction
              </button>
            </div>

            <div className="flex gap-4">
              <input
                type="text"
                value={searchAddress}
                onChange={(e) => setSearchAddress(e.target.value)}
                placeholder={searchType === 'address' ? 'Enter wallet address (0x...)' : 'Enter transaction hash (0x...)'}
                className="flex-1 px-4 py-3 rounded-xl bg-slate-700/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                type="submit"
                className="px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-semibold shadow-lg shadow-indigo-500/30 transition-all"
              >
                Investigate
              </button>
            </div>
          </form>
        </div>

        {/* Quick Actions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-5 hover:bg-slate-800/70 transition-colors cursor-pointer">
            <div className="w-12 h-12 rounded-lg bg-red-500/20 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="text-white font-semibold mb-1">High Risk Alerts</h3>
            <p className="text-slate-400 text-sm">3 addresses flagged</p>
          </div>

          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-5 hover:bg-slate-800/70 transition-colors cursor-pointer">
            <div className="w-12 h-12 rounded-lg bg-amber-500/20 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
            </div>
            <h3 className="text-white font-semibold mb-1">Under Monitoring</h3>
            <p className="text-slate-400 text-sm">12 addresses tracked</p>
          </div>

          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-5 hover:bg-slate-800/70 transition-colors cursor-pointer">
            <div className="w-12 h-12 rounded-lg bg-green-500/20 flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3 className="text-white font-semibold mb-1">Resolved Cases</h3>
            <p className="text-slate-400 text-sm">45 cases this month</p>
          </div>
        </div>

        {/* Recent Investigations */}
        <div className="bg-slate-800/50 rounded-2xl border border-slate-700/50 p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Recent Investigations</h2>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-slate-400 text-sm border-b border-slate-700">
                  <th className="pb-3 font-medium">Address</th>
                  <th className="pb-3 font-medium">Risk Level</th>
                  <th className="pb-3 font-medium">Date</th>
                  <th className="pb-3 font-medium">Status</th>
                  <th className="pb-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {recentInvestigations.map((item, index) => (
                  <tr key={index} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-4">
                      <span className="font-mono text-white">{item.address}</span>
                    </td>
                    <td className="py-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        item.risk === 'high' ? 'bg-red-500/20 text-red-400' :
                        item.risk === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                        'bg-green-500/20 text-green-400'
                      }`}>
                        {item.risk.charAt(0).toUpperCase() + item.risk.slice(1)}
                      </span>
                    </td>
                    <td className="py-4 text-slate-300">{item.date}</td>
                    <td className="py-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        item.status === 'Open' ? 'bg-blue-500/20 text-blue-400' :
                        item.status === 'Resolved' ? 'bg-green-500/20 text-green-400' :
                        'bg-amber-500/20 text-amber-400'
                      }`}>
                        {item.status}
                      </span>
                    </td>
                    <td className="py-4">
                      <button className="text-indigo-400 hover:text-indigo-300 text-sm">
                        View Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}
