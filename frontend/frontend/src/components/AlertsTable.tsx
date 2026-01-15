'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { 
  ExternalLink, Copy, Ban, Flag, Eye, AlertTriangle,
  CheckCircle, XCircle, Clock, MoreHorizontal, Zap
} from 'lucide-react';
import type { Alert } from '@/types/siem';
import { performAction } from '@/lib/api';

interface AlertsTableProps {
  alerts: Alert[];
  onRefresh: () => void;
}

export function AlertsTable({ alerts, onRefresh }: AlertsTableProps) {
  const router = useRouter();
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set());
  const [actionMenuOpen, setActionMenuOpen] = useState<string | null>(null);
  const [processing, setProcessing] = useState<string | null>(null);

  const handleRowClick = (alert: Alert) => {
    router.push(`/investigate/${alert.address}`);
  };

  const handleAction = async (alertId: string, action: 'FLAG' | 'BLOCK' | 'ESCALATE' | 'RESOLVE' | 'FALSE_POSITIVE' | 'WATCHLIST') => {
    setProcessing(alertId);
    try {
      await performAction(alertId, action);
      onRefresh();
    } catch (error) {
      console.error('Action failed:', error);
    }
    setProcessing(null);
    setActionMenuOpen(null);
  };

  const copyAddress = (e: React.MouseEvent, address: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(address);
  };

  const getRiskBadgeClass = (level: string) => {
    switch (level) {
      case 'CRITICAL': return 'bg-red-600 text-white animate-pulse';
      case 'HIGH': return 'bg-orange-600 text-white';
      case 'MEDIUM': return 'bg-yellow-600 text-black';
      case 'LOW': return 'bg-green-600 text-white';
      default: return 'bg-gray-600 text-white';
    }
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'NEW': return 'bg-blue-500/20 text-blue-400 border border-blue-500/30';
      case 'INVESTIGATING': return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30';
      case 'RESOLVED': return 'bg-green-500/20 text-green-400 border border-green-500/30';
      case 'FALSE_POSITIVE': return 'bg-gray-500/20 text-gray-400 border border-gray-500/30';
      default: return 'bg-gray-500/20 text-gray-400';
    }
  };

  const getActionBadgeClass = (action: string) => {
    switch (action) {
      case 'BLOCK': return 'text-red-400';
      case 'ESCROW': return 'text-orange-400';
      case 'FLAG': return 'text-yellow-400';
      case 'MONITOR': return 'text-blue-400';
      case 'APPROVE': return 'text-green-400';
      default: return 'text-gray-400';
    }
  };

  const formatTimeAgo = (timestamp: string) => {
    const diff = Date.now() - new Date(timestamp).getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return 'Just now';
  };

  if (alerts.length === 0) {
    return (
      <div className="p-12 text-center text-gray-500">
        <AlertTriangle className="w-12 h-12 mx-auto mb-4 opacity-50" />
        <p>No alerts match your filters</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
            <th className="px-4 py-3 w-8">
              <input
                type="checkbox"
                checked={selectedAlerts.size === alerts.length}
                onChange={(e) => {
                  if (e.target.checked) {
                    setSelectedAlerts(new Set(alerts.map(a => a.id)));
                  } else {
                    setSelectedAlerts(new Set());
                  }
                }}
                className="rounded bg-gray-800 border-gray-600"
              />
            </th>
            <th className="px-4 py-3">Time</th>
            <th className="px-4 py-3">Address</th>
            <th className="px-4 py-3">Risk</th>
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">Signals</th>
            <th className="px-4 py-3">Patterns</th>
            <th className="px-4 py-3">Action</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3 w-12"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {alerts.map((alert) => (
            <tr
              key={alert.id}
              onClick={() => handleRowClick(alert)}
              className="hover:bg-gray-800/50 cursor-pointer transition-colors group"
            >
              <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  checked={selectedAlerts.has(alert.id)}
                  onChange={(e) => {
                    const newSelected = new Set(selectedAlerts);
                    if (e.target.checked) {
                      newSelected.add(alert.id);
                    } else {
                      newSelected.delete(alert.id);
                    }
                    setSelectedAlerts(newSelected);
                  }}
                  className="rounded bg-gray-800 border-gray-600"
                />
              </td>
              <td className="px-4 py-3">
                <div className="text-sm text-gray-300">{formatTimeAgo(alert.timestamp)}</div>
                <div className="text-xs text-gray-500">
                  {new Date(alert.timestamp).toLocaleTimeString()}
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <code className="text-sm font-mono text-blue-400 group-hover:text-blue-300">
                    {alert.address.slice(0, 10)}...{alert.address.slice(-8)}
                  </code>
                  <button
                    onClick={(e) => copyAddress(e, alert.address)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-700 rounded"
                    title="Copy address"
                  >
                    <Copy className="w-3 h-3 text-gray-400" />
                  </button>
                </div>
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded text-xs font-bold ${getRiskBadgeClass(alert.riskLevel)}`}>
                  {alert.riskLevel}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <div className="w-16 h-2 bg-gray-700 rounded-full overflow-hidden">
                    <div 
                      className={`h-full rounded-full ${
                        alert.riskScore >= 80 ? 'bg-red-500' :
                        alert.riskScore >= 60 ? 'bg-orange-500' :
                        alert.riskScore >= 40 ? 'bg-yellow-500' :
                        'bg-green-500'
                      }`}
                      style={{ width: `${alert.riskScore}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-400">{alert.riskScore.toFixed(1)}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-1">
                  <Zap className="w-4 h-4 text-yellow-400" />
                  <span className="text-sm font-medium">{alert.signalCount}</span>
                </div>
              </td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1 max-w-[200px]">
                  {alert.patterns.slice(0, 2).map((pattern) => (
                    <span
                      key={pattern}
                      className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full"
                    >
                      {pattern}
                    </span>
                  ))}
                  {alert.patterns.length > 2 && (
                    <span className="px-2 py-0.5 bg-gray-700 text-gray-400 text-xs rounded-full">
                      +{alert.patterns.length - 2}
                    </span>
                  )}
                </div>
              </td>
              <td className="px-4 py-3">
                <span className={`text-sm font-medium ${getActionBadgeClass(alert.action)}`}>
                  {alert.action}
                </span>
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded-full text-xs ${getStatusBadgeClass(alert.status)}`}>
                  {alert.status.replace('_', ' ')}
                </span>
              </td>
              <td className="px-4 py-3 relative" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => setActionMenuOpen(actionMenuOpen === alert.id ? null : alert.id)}
                  className="p-1.5 hover:bg-gray-700 rounded transition-colors"
                >
                  <MoreHorizontal className="w-4 h-4 text-gray-400" />
                </button>
                
                {/* Action Menu */}
                {actionMenuOpen === alert.id && (
                  <div className="absolute right-0 top-full mt-1 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50">
                    <div className="p-1">
                      <ActionButton
                        icon={<Eye className="w-4 h-4" />}
                        label="Investigate"
                        onClick={() => router.push(`/investigate/${alert.address}`)}
                      />
                      <ActionButton
                        icon={<Flag className="w-4 h-4" />}
                        label="Flag for Review"
                        onClick={() => handleAction(alert.id, 'FLAG')}
                        loading={processing === alert.id}
                      />
                      <ActionButton
                        icon={<Ban className="w-4 h-4" />}
                        label="Block Address"
                        onClick={() => handleAction(alert.id, 'BLOCK')}
                        loading={processing === alert.id}
                        danger
                      />
                      <ActionButton
                        icon={<AlertTriangle className="w-4 h-4" />}
                        label="Escalate"
                        onClick={() => handleAction(alert.id, 'ESCALATE')}
                        loading={processing === alert.id}
                      />
                      <div className="border-t border-gray-700 my-1" />
                      <ActionButton
                        icon={<CheckCircle className="w-4 h-4" />}
                        label="Mark Resolved"
                        onClick={() => handleAction(alert.id, 'RESOLVE')}
                        loading={processing === alert.id}
                      />
                      <ActionButton
                        icon={<XCircle className="w-4 h-4" />}
                        label="False Positive"
                        onClick={() => handleAction(alert.id, 'FALSE_POSITIVE')}
                        loading={processing === alert.id}
                      />
                    </div>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      
      {/* Bulk Actions */}
      {selectedAlerts.size > 0 && (
        <div className="sticky bottom-0 bg-gray-800 border-t border-gray-700 p-4 flex items-center justify-between">
          <span className="text-sm text-gray-400">
            {selectedAlerts.size} alert{selectedAlerts.size > 1 ? 's' : ''} selected
          </span>
          <div className="flex gap-2">
            <button className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 text-white text-sm rounded transition-colors">
              Flag All
            </button>
            <button className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm rounded transition-colors">
              Block All
            </button>
            <button className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm rounded transition-colors">
              Resolve All
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ActionButton({ 
  icon, 
  label, 
  onClick, 
  danger = false,
  loading = false 
}: { 
  icon: React.ReactNode; 
  label: string; 
  onClick: () => void;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded transition-colors ${
        danger 
          ? 'text-red-400 hover:bg-red-500/20' 
          : 'text-gray-300 hover:bg-gray-700'
      } disabled:opacity-50`}
    >
      {loading ? (
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        icon
      )}
      {label}
    </button>
  );
}
