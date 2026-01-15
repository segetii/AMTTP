'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeft, Shield, AlertTriangle, Activity, Network,
  Clock, DollarSign, Hash, ExternalLink, Copy, Ban,
  Flag, Eye, CheckCircle, TrendingUp, Zap, Link2
} from 'lucide-react';
import { fetchEntityProfile, scoreAddress, performAction } from '@/lib/api';
import type { EntityProfile, Transaction } from '@/types/siem';

export function EntityInvestigation() {
  const params = useParams();
  const router = useRouter();
  const address = params?.address as string;
  
  const [entity, setEntity] = useState<EntityProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'transactions' | 'connections' | 'timeline'>('overview');
  const [scoring, setScoring] = useState(false);
  const [liveScore, setLiveScore] = useState<{
    hybrid_score: number;
    risk_level: string;
    ml_score: number;
    graph_score: number;
    patterns: string;
    signal_count: number;
  } | null>(null);

  useEffect(() => {
    if (address) {
      loadEntity();
      getLiveScore();
    }
  }, [address]);

  async function loadEntity() {
    setLoading(true);
    try {
      const data = await fetchEntityProfile(address);
      setEntity(data);
    } catch (error) {
      console.error('Failed to load entity:', error);
    }
    setLoading(false);
  }

  async function getLiveScore() {
    setScoring(true);
    try {
      const score = await scoreAddress(address);
      setLiveScore(score);
    } catch (error) {
      console.error('Failed to get live score:', error);
    }
    setScoring(false);
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'CRITICAL': return 'text-red-500 bg-red-500/10 border-red-500/30';
      case 'HIGH': return 'text-orange-500 bg-orange-500/10 border-orange-500/30';
      case 'MEDIUM': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/30';
      case 'LOW': return 'text-green-500 bg-green-500/10 border-green-500/30';
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/30';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">
        Entity not found
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.back()}
                className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-xl font-bold font-mono">
                    {address.slice(0, 10)}...{address.slice(-8)}
                  </h1>
                  <button
                    onClick={() => copyToClipboard(address)}
                    className="p-1.5 hover:bg-gray-800 rounded transition-colors"
                    title="Copy full address"
                  >
                    <Copy className="w-4 h-4 text-gray-400" />
                  </button>
                  <a
                    href={`https://etherscan.io/address/${address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1.5 hover:bg-gray-800 rounded transition-colors"
                    title="View on Etherscan"
                  >
                    <ExternalLink className="w-4 h-4 text-gray-400" />
                  </a>
                </div>
                <p className="text-sm text-gray-400">Entity Investigation</p>
              </div>
            </div>
            
            {/* Live Risk Badge */}
            <div className="flex items-center gap-4">
              {liveScore && (
                <div className={`px-4 py-2 rounded-lg border ${getRiskColor(liveScore.risk_level)}`}>
                  <div className="flex items-center gap-2">
                    <Shield className="w-5 h-5" />
                    <span className="font-bold">{liveScore.risk_level}</span>
                    <span className="text-sm opacity-75">
                      Score: {liveScore.hybrid_score.toFixed(1)}
                    </span>
                  </div>
                </div>
              )}
              
              {/* Action Buttons */}
              <div className="flex gap-2">
                <button 
                  onClick={() => performAction('temp', 'FLAG')}
                  className="px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <Flag className="w-4 h-4" /> Flag
                </button>
                <button 
                  onClick={() => performAction('temp', 'BLOCK')}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <Ban className="w-4 h-4" /> Block
                </button>
                <button 
                  onClick={() => performAction('temp', 'WATCHLIST')}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                >
                  <Eye className="w-4 h-4" /> Watchlist
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
          <StatCard
            icon={<Activity className="w-5 h-5" />}
            label="Total Transactions"
            value={entity.totalTransactions}
            color="blue"
          />
          <StatCard
            icon={<DollarSign className="w-5 h-5" />}
            label="Total Value (ETH)"
            value={entity.totalValueEth.toFixed(2)}
            color="green"
          />
          <StatCard
            icon={<Network className="w-5 h-5" />}
            label="Graph Connections"
            value={entity.graphConnections}
            color="purple"
          />
          <StatCard
            icon={<Zap className="w-5 h-5" />}
            label="Signal Count"
            value={liveScore?.signal_count ?? 0}
            color="yellow"
          />
          <StatCard
            icon={<TrendingUp className="w-5 h-5" />}
            label="ML Score"
            value={(liveScore?.ml_score ?? entity.mlScore).toFixed(2)}
            color="cyan"
          />
          <StatCard
            icon={<Link2 className="w-5 h-5" />}
            label="Graph Score"
            value={(liveScore?.graph_score ?? entity.graphScore).toFixed(1)}
            color="orange"
          />
        </div>

        {/* Detected Patterns */}
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-orange-400" />
            Detected Patterns
          </h2>
          <div className="flex flex-wrap gap-2">
            {(liveScore?.patterns?.split(', ') || entity.patterns || []).filter(Boolean).map((pattern) => (
              <PatternBadge key={pattern} pattern={pattern} />
            ))}
            {!liveScore?.patterns && entity.patterns.length === 0 && (
              <span className="text-gray-500">No patterns detected</span>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-800">
          <div className="flex gap-4">
            {(['overview', 'transactions', 'connections', 'timeline'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-gray-400 hover:text-white'
                }`}
              >
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Recent Alerts */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4">Recent Alerts</h3>
              <div className="space-y-3">
                {entity.alerts.slice(0, 5).map((alert) => (
                  <div
                    key={alert.id}
                    className="flex items-center justify-between p-3 bg-gray-800/50 rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                        alert.riskLevel === 'CRITICAL' ? 'bg-red-600' :
                        alert.riskLevel === 'HIGH' ? 'bg-orange-600' :
                        alert.riskLevel === 'MEDIUM' ? 'bg-yellow-600 text-black' :
                        'bg-green-600'
                      }`}>
                        {alert.riskLevel}
                      </span>
                      <span className="text-sm text-gray-300">
                        {alert.patterns.join(', ')}
                      </span>
                    </div>
                    <span className="text-xs text-gray-500">
                      {new Date(alert.timestamp).toLocaleDateString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Activity Summary */}
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
              <h3 className="text-lg font-semibold mb-4">Activity Summary</h3>
              <div className="space-y-4">
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">First Seen</span>
                  <span className="font-mono text-sm">
                    {new Date(entity.firstSeen).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Last Seen</span>
                  <span className="font-mono text-sm">
                    {new Date(entity.lastSeen).toLocaleDateString()}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Active Days</span>
                  <span className="font-mono text-sm">
                    {Math.ceil((new Date(entity.lastSeen).getTime() - new Date(entity.firstSeen).getTime()) / (1000 * 60 * 60 * 24))}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400">Avg TX Value</span>
                  <span className="font-mono text-sm">
                    {(entity.totalValueEth / entity.totalTransactions).toFixed(4)} ETH
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'transactions' && (
          <TransactionsTab transactions={entity.transactions} />
        )}

        {activeTab === 'connections' && (
          <ConnectionsTab connections={entity.connectedAddresses} onNavigate={(addr) => router.push(`/investigate/${addr}`)} />
        )}

        {activeTab === 'timeline' && (
          <TimelineTab entity={entity} />
        )}
      </main>
    </div>
  );
}

// Helper Components
function StatCard({ icon, label, value, color }: { 
  icon: React.ReactNode; 
  label: string; 
  value: string | number;
  color: 'blue' | 'green' | 'purple' | 'yellow' | 'cyan' | 'orange';
}) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    green: 'bg-green-500/10 text-green-400 border-green-500/20',
    purple: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    cyan: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20',
    orange: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
  };

  return (
    <div className={`p-4 rounded-xl border ${colorClasses[color]}`}>
      <div className="flex items-center gap-2 mb-2">
        {icon}
      </div>
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
    </div>
  );
}

function PatternBadge({ pattern }: { pattern: string }) {
  const colors: Record<string, string> = {
    SMURFING: 'bg-red-500/20 text-red-400 border-red-500/30',
    LAYERING: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    FAN_OUT: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    FAN_IN: 'bg-purple-500/20 text-purple-400 border-purple-500/30',
    ROUND_TRIP: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    RAPID_MOVEMENT: 'bg-pink-500/20 text-pink-400 border-pink-500/30',
  };

  return (
    <span className={`px-3 py-1.5 rounded-lg border text-sm font-medium ${colors[pattern] || 'bg-gray-500/20 text-gray-400 border-gray-500/30'}`}>
      {pattern}
    </span>
  );
}

function TransactionsTab({ transactions }: { transactions: Transaction[] }) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="text-left text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
            <th className="px-4 py-3">Time</th>
            <th className="px-4 py-3">Hash</th>
            <th className="px-4 py-3">Direction</th>
            <th className="px-4 py-3">Counterparty</th>
            <th className="px-4 py-3">Value (ETH)</th>
            <th className="px-4 py-3">Risk</th>
            <th className="px-4 py-3">Flagged</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {transactions.map((tx) => (
            <tr key={tx.hash} className="hover:bg-gray-800/50">
              <td className="px-4 py-3 text-sm text-gray-400">
                {new Date(tx.timestamp).toLocaleTimeString()}
              </td>
              <td className="px-4 py-3">
                <a
                  href={`https://etherscan.io/tx/${tx.hash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-mono text-blue-400 hover:underline"
                >
                  {tx.hash.slice(0, 10)}...
                </a>
              </td>
              <td className="px-4 py-3">
                <span className={`text-xs font-medium ${
                  tx.from.toLowerCase() === transactions[0]?.from?.toLowerCase()
                    ? 'text-red-400'
                    : 'text-green-400'
                }`}>
                  {tx.from.toLowerCase() === transactions[0]?.from?.toLowerCase() ? 'SENT' : 'RECEIVED'}
                </span>
              </td>
              <td className="px-4 py-3 font-mono text-sm text-gray-300">
                {tx.from.toLowerCase() === transactions[0]?.from?.toLowerCase()
                  ? `${tx.to.slice(0, 8)}...`
                  : `${tx.from.slice(0, 8)}...`
                }
              </td>
              <td className="px-4 py-3 text-sm">{tx.valueEth.toFixed(4)}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="w-12 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        tx.riskScore >= 70 ? 'bg-red-500' :
                        tx.riskScore >= 50 ? 'bg-orange-500' :
                        tx.riskScore >= 30 ? 'bg-yellow-500' :
                        'bg-green-500'
                      }`}
                      style={{ width: `${tx.riskScore}%` }}
                    />
                  </div>
                  <span className="text-xs text-gray-400">{tx.riskScore.toFixed(0)}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                {tx.flagged && (
                  <Flag className="w-4 h-4 text-red-400" />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConnectionsTab({ connections, onNavigate }: { 
  connections: EntityProfile['connectedAddresses']; 
  onNavigate: (addr: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {connections.map((conn) => (
        <div
          key={conn.address}
          onClick={() => onNavigate(conn.address)}
          className="p-4 bg-gray-900 rounded-xl border border-gray-800 hover:border-gray-700 cursor-pointer transition-colors"
        >
          <div className="flex items-center justify-between mb-3">
            <code className="text-sm font-mono text-blue-400">
              {conn.address.slice(0, 10)}...{conn.address.slice(-6)}
            </code>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              conn.riskLevel === 'HIGH' ? 'bg-red-500/20 text-red-400' :
              conn.riskLevel === 'MEDIUM' ? 'bg-yellow-500/20 text-yellow-400' :
              'bg-green-500/20 text-green-400'
            }`}>
              {conn.riskLevel}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400">
            <span className={`${
              conn.relationship === 'SENT_TO' ? 'text-red-400' :
              conn.relationship === 'RECEIVED_FROM' ? 'text-green-400' :
              'text-purple-400'
            }`}>
              {conn.relationship.replace('_', ' ')}
            </span>
            <span>{conn.transactionCount} txs</span>
            <span>{conn.totalValue.toFixed(2)} ETH</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function TimelineTab({ entity }: { entity: EntityProfile }) {
  const events = [
    ...entity.alerts.map(a => ({ type: 'alert' as const, data: a, timestamp: a.timestamp })),
    ...entity.transactions.slice(0, 10).map(t => ({ type: 'tx' as const, data: t, timestamp: t.timestamp }))
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return (
    <div className="relative">
      <div className="absolute left-8 top-0 bottom-0 w-0.5 bg-gray-800" />
      <div className="space-y-4">
        {events.map((event, i) => (
          <div key={i} className="flex gap-4 relative">
            <div className={`w-4 h-4 rounded-full z-10 ${
              event.type === 'alert' ? 'bg-red-500' : 'bg-blue-500'
            }`} style={{ marginLeft: '24px' }} />
            <div className="flex-1 bg-gray-900 rounded-lg border border-gray-800 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-medium ${
                  event.type === 'alert' ? 'text-red-400' : 'text-blue-400'
                }`}>
                  {event.type === 'alert' ? 'ALERT' : 'TRANSACTION'}
                </span>
                <span className="text-xs text-gray-500">
                  {new Date(event.timestamp).toLocaleString()}
                </span>
              </div>
              {event.type === 'alert' ? (
                <div className="text-sm text-gray-300">
                  {(event.data as typeof entity.alerts[0]).riskLevel} - {(event.data as typeof entity.alerts[0]).patterns.join(', ')}
                </div>
              ) : (
                <div className="text-sm text-gray-300">
                  {(event.data as Transaction).valueEth.toFixed(4)} ETH
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
