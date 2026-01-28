// Improved Alerts Table with accessibility and React Query mutations
'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  ExternalLink, Copy, Ban, Flag, Eye, AlertTriangle,
  CheckCircle, XCircle, Clock, MoreHorizontal, Zap
} from 'lucide-react';
import type { Alert } from '@/types/siem';
import { useAlertAction } from '@/lib/hooks';
import { useToast } from '@/lib/toast';

interface AlertsTableProps {
  alerts: Alert[];
}

export function AlertsTableImproved({ alerts }: AlertsTableProps) {
  const router = useRouter();
  const { success } = useToast();
  const [selectedAlerts, setSelectedAlerts] = useState<Set<string>>(new Set());
  const [actionMenuOpen, setActionMenuOpen] = useState<string | null>(null);

  // React Query mutation for alert actions
  const alertAction = useAlertAction();

  const handleRowClick = useCallback((alert: Alert) => {
    router.push(`/investigate/${alert.address}`);
  }, [router]);

  const handleAction = useCallback(
    async (alertId: string, action: 'FLAG' | 'BLOCK' | 'ESCALATE' | 'RESOLVE' | 'FALSE_POSITIVE' | 'WATCHLIST') => {
      alertAction.mutate({ alertId, action });
      setActionMenuOpen(null);
    },
    [alertAction]
  );

  const copyAddress = useCallback((e: React.MouseEvent, address: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(address);
    success('Address copied', address);
  }, [success]);

  const handleSelectAll = useCallback((checked: boolean) => {
    if (checked) {
      setSelectedAlerts(new Set(alerts.map(a => a.id)));
    } else {
      setSelectedAlerts(new Set());
    }
  }, [alerts]);

  const handleSelectOne = useCallback((alertId: string, checked: boolean) => {
    setSelectedAlerts(prev => {
      const newSet = new Set(prev);
      if (checked) {
        newSet.add(alertId);
      } else {
        newSet.delete(alertId);
      }
      return newSet;
    });
  }, []);

  // Close menu when clicking outside
  const handleCloseMenu = useCallback(() => {
    setActionMenuOpen(null);
  }, []);

  if (alerts.length === 0) {
    return (
      <div className="p-12 text-center text-gray-500" role="status">
        <AlertTriangle className="w-12 h-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
        <p>No alerts match your filters</p>
      </div>
    );
  }

  return (
    <>
      {/* Click outside to close menu */}
      {actionMenuOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={handleCloseMenu}
          aria-hidden="true"
        />
      )}

      <div className="overflow-x-auto">
        <table className="w-full" role="grid" aria-label="Security alerts">
          <thead>
            <tr className="text-left text-xs text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3 w-8" scope="col">
                <label className="sr-only">Select all alerts</label>
                <input
                  type="checkbox"
                  checked={selectedAlerts.size === alerts.length && alerts.length > 0}
                  onChange={(e) => handleSelectAll(e.target.checked)}
                  className="rounded bg-gray-800 border-gray-600 focus:ring-2 focus:ring-blue-500"
                  aria-label="Select all alerts"
                />
              </th>
              <th className="px-4 py-3" scope="col">Time</th>
              <th className="px-4 py-3" scope="col">Address</th>
              <th className="px-4 py-3" scope="col">Risk</th>
              <th className="px-4 py-3" scope="col">Score</th>
              <th className="px-4 py-3" scope="col">Signals</th>
              <th className="px-4 py-3" scope="col">Patterns</th>
              <th className="px-4 py-3" scope="col">Action</th>
              <th className="px-4 py-3" scope="col">Status</th>
              <th className="px-4 py-3 w-12" scope="col">
                <span className="sr-only">Actions menu</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {alerts.map((alert) => (
              <AlertRow
                key={alert.id}
                alert={alert}
                isSelected={selectedAlerts.has(alert.id)}
                onSelect={handleSelectOne}
                onRowClick={handleRowClick}
                onCopyAddress={copyAddress}
                onAction={handleAction}
                isMenuOpen={actionMenuOpen === alert.id}
                onToggleMenu={(id) => setActionMenuOpen(actionMenuOpen === id ? null : id)}
                isProcessing={alertAction.isPending && alertAction.variables?.alertId === alert.id}
              />
            ))}
          </tbody>
        </table>

        {/* Bulk Actions Bar */}
        {selectedAlerts.size > 0 && (
          <div
            className="sticky bottom-0 bg-gray-800 border-t border-gray-700 p-4 flex items-center justify-between"
            role="toolbar"
            aria-label="Bulk actions"
          >
            <span className="text-sm text-gray-400">
              {selectedAlerts.size} alert{selectedAlerts.size > 1 ? 's' : ''} selected
            </span>
            <div className="flex gap-2">
              <button
                className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 text-white text-sm rounded transition-colors focus:ring-2 focus:ring-yellow-500"
                aria-label={`Flag ${selectedAlerts.size} selected alerts`}
              >
                Flag All
              </button>
              <button
                className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm rounded transition-colors focus:ring-2 focus:ring-red-500"
                aria-label={`Block ${selectedAlerts.size} selected alerts`}
              >
                Block All
              </button>
              <button
                className="px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white text-sm rounded transition-colors focus:ring-2 focus:ring-green-500"
                aria-label={`Resolve ${selectedAlerts.size} selected alerts`}
              >
                Resolve All
              </button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// Individual alert row component
interface AlertRowProps {
  alert: Alert;
  isSelected: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onRowClick: (alert: Alert) => void;
  onCopyAddress: (e: React.MouseEvent, address: string) => void;
  onAction: (id: string, action: 'FLAG' | 'BLOCK' | 'ESCALATE' | 'RESOLVE' | 'FALSE_POSITIVE' | 'WATCHLIST') => void;
  isMenuOpen: boolean;
  onToggleMenu: (id: string) => void;
  isProcessing: boolean;
}

function AlertRow({
  alert,
  isSelected,
  onSelect,
  onRowClick,
  onCopyAddress,
  onAction,
  isMenuOpen,
  onToggleMenu,
  isProcessing,
}: AlertRowProps) {
  const router = useRouter();

  const getRiskBadgeClass = (level: string) => {
    switch (level) {
      case 'CRITICAL': return 'bg-red-600 text-white';
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

  // Normalize potentially missing fields from backend
  const patterns = Array.isArray(alert.patterns) ? alert.patterns : [];
  const patternDisplay = patterns.slice(0, 2);
  const extraPatternCount = Math.max(0, patterns.length - 2);
  const signalCount = typeof alert.signalCount === 'number'
    ? alert.signalCount
    : Array.isArray((alert as any).signals)
      ? (alert as any).signals.length
      : 0;
  const status = typeof alert.status === 'string' && alert.status.length > 0
    ? alert.status
    : 'UNKNOWN';
  const statusLabel = status.replace('_', ' ');

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

  return (
    <tr
      onClick={() => onRowClick(alert)}
      className="hover:bg-gray-800/50 cursor-pointer transition-colors group"
      role="row"
      aria-selected={isSelected}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onRowClick(alert);
        }
      }}
    >
      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={isSelected}
          onChange={(e) => onSelect(alert.id, e.target.checked)}
          className="rounded bg-gray-800 border-gray-600 focus:ring-2 focus:ring-blue-500"
          aria-label={`Select alert for ${alert.address}`}
        />
      </td>
      <td className="px-4 py-3">
        <div className="text-sm text-gray-300">{formatTimeAgo(alert.timestamp)}</div>
        <div className="text-xs text-gray-500">
          <time dateTime={alert.timestamp}>
            {new Date(alert.timestamp).toLocaleTimeString()}
          </time>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <code className="text-sm font-mono text-blue-400 group-hover:text-blue-300">
            {alert.address.slice(0, 10)}...{alert.address.slice(-8)}
          </code>
          <button
            onClick={(e) => onCopyAddress(e, alert.address)}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-gray-700 rounded focus:opacity-100 focus:ring-2 focus:ring-blue-500"
            aria-label={`Copy address ${alert.address}`}
            title="Copy address"
          >
            <Copy className="w-3 h-3 text-gray-400" aria-hidden="true" />
          </button>
        </div>
      </td>
      <td className="px-4 py-3">
        <span
          className={`px-2 py-1 rounded text-xs font-bold ${getRiskBadgeClass(alert.riskLevel)} ${
            alert.riskLevel === 'CRITICAL' ? 'animate-pulse' : ''
          }`}
          role="status"
          aria-label={`Risk level: ${alert.riskLevel}`}
        >
          {alert.riskLevel}
        </span>
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <div
            className="w-16 h-2 bg-gray-700 rounded-full overflow-hidden"
            role="progressbar"
            aria-valuenow={alert.riskScore}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Risk score ${alert.riskScore.toFixed(1)} out of 100`}
          >
            <div
              className={`h-full rounded-full transition-all ${
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
        <div className="flex items-center gap-1" aria-label={`${signalCount} risk signals detected`}>
          <Zap className="w-4 h-4 text-yellow-400" aria-hidden="true" />
          <span className="text-sm font-medium">{signalCount}</span>
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1 max-w-[200px]">
          {patternDisplay.map((pattern) => (
            <span
              key={pattern}
              className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full"
              title={`Detected pattern: ${pattern}`}
            >
              {pattern}
            </span>
          ))}
          {extraPatternCount > 0 && (
            <span
              className="px-2 py-0.5 bg-gray-700 text-gray-400 text-xs rounded-full"
              title={`${extraPatternCount} more patterns: ${patterns.slice(2).join(', ')}`}
            >
              +{extraPatternCount}
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
        <span className={`px-2 py-1 rounded-full text-xs ${getStatusBadgeClass(status)}`}>
          {statusLabel}
        </span>
      </td>
      <td className="px-4 py-3 relative" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={() => onToggleMenu(alert.id)}
          className="p-1.5 hover:bg-gray-700 rounded transition-colors focus:ring-2 focus:ring-blue-500"
          aria-label="Open actions menu"
          aria-expanded={isMenuOpen}
          aria-haspopup="menu"
        >
          <MoreHorizontal className="w-4 h-4 text-gray-400" aria-hidden="true" />
        </button>

        {/* Action Menu */}
        {isMenuOpen && (
          <div
            className="absolute right-0 top-full mt-1 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50"
            role="menu"
            aria-label="Alert actions"
          >
            <div className="p-1">
              <ActionButton
                icon={<Eye className="w-4 h-4" />}
                label="Investigate"
                onClick={() => router.push(`/investigate/${alert.address}`)}
              />
              <ActionButton
                icon={<Flag className="w-4 h-4" />}
                label="Flag for Review"
                onClick={() => onAction(alert.id, 'FLAG')}
                loading={isProcessing}
              />
              <ActionButton
                icon={<Ban className="w-4 h-4" />}
                label="Block Address"
                onClick={() => onAction(alert.id, 'BLOCK')}
                loading={isProcessing}
                danger
              />
              <ActionButton
                icon={<AlertTriangle className="w-4 h-4" />}
                label="Escalate"
                onClick={() => onAction(alert.id, 'ESCALATE')}
                loading={isProcessing}
              />
              <div className="border-t border-gray-700 my-1" role="separator" />
              <ActionButton
                icon={<CheckCircle className="w-4 h-4" />}
                label="Mark Resolved"
                onClick={() => onAction(alert.id, 'RESOLVE')}
                loading={isProcessing}
              />
              <ActionButton
                icon={<XCircle className="w-4 h-4" />}
                label="False Positive"
                onClick={() => onAction(alert.id, 'FALSE_POSITIVE')}
                loading={isProcessing}
              />
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}

// Action button in dropdown menu
function ActionButton({
  icon,
  label,
  onClick,
  danger = false,
  loading = false,
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
      role="menuitem"
      className={`w-full flex items-center gap-2 px-3 py-2 text-sm rounded transition-colors focus:ring-2 focus:ring-blue-500 ${
        danger
          ? 'text-red-400 hover:bg-red-500/20'
          : 'text-gray-300 hover:bg-gray-700'
      } disabled:opacity-50`}
    >
      {loading ? (
        <div
          className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"
          aria-hidden="true"
        />
      ) : (
        <span aria-hidden="true">{icon}</span>
      )}
      {label}
    </button>
  );
}
