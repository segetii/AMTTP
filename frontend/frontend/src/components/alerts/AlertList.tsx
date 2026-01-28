'use client';

/**
 * AlertList Component
 * 
 * Display and manage alerts
 * 
 * Ground Truth Reference:
 * - Priority-based visual hierarchy
 * - Quick actions for common operations
 */

import React, { useState } from 'react';
import {
  Alert,
  AlertPriority,
  AlertCategory,
  AlertStatus,
  getPriorityColor,
  getCategoryIcon,
  getStatusColor,
  formatAlertTime,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AlertListProps {
  alerts: Alert[];
  onAcknowledge?: (alertId: string) => void;
  onResolve?: (alertId: string) => void;
  onDismiss?: (alertId: string) => void;
  onEscalate?: (alertId: string) => void;
  onSelect?: (alert: Alert) => void;
  selectedAlertId?: string;
  showFilters?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PRIORITY BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function PriorityBadge({ priority }: { priority: AlertPriority }) {
  const color = getPriorityColor(priority);
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-900/30 text-blue-400 border-blue-600/30',
    yellow: 'bg-yellow-900/30 text-yellow-400 border-yellow-600/30',
    orange: 'bg-orange-900/30 text-orange-400 border-orange-600/30',
    red: 'bg-red-900/30 text-red-400 border-red-600/30 animate-pulse',
  };
  
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${colorClasses[color]}`}>
      {priority}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// STATUS BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function StatusBadge({ status }: { status: AlertStatus }) {
  const color = getStatusColor(status);
  const colorClasses: Record<string, string> = {
    cyan: 'bg-cyan-900/30 text-cyan-400',
    yellow: 'bg-yellow-900/30 text-yellow-400',
    blue: 'bg-blue-900/30 text-blue-400',
    green: 'bg-green-900/30 text-green-400',
    gray: 'bg-gray-900/30 text-gray-400',
    red: 'bg-red-900/30 text-red-400',
  };
  
  return (
    <span className={`px-2 py-0.5 text-xs rounded ${colorClasses[color]}`}>
      {status}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT CARD
// ═══════════════════════════════════════════════════════════════════════════════

function AlertCard({
  alert,
  isSelected,
  onSelect,
  onAcknowledge,
  onDismiss,
}: {
  alert: Alert;
  isSelected: boolean;
  onSelect: () => void;
  onAcknowledge?: () => void;
  onDismiss?: () => void;
}) {
  const priorityBorder: Record<AlertPriority, string> = {
    [AlertPriority.LOW]: 'border-l-blue-500',
    [AlertPriority.MEDIUM]: 'border-l-yellow-500',
    [AlertPriority.HIGH]: 'border-l-orange-500',
    [AlertPriority.CRITICAL]: 'border-l-red-500',
  };
  
  return (
    <div
      onClick={onSelect}
      className={`bg-slate-800/50 rounded-lg border-l-4 border border-slate-700 p-4 cursor-pointer transition-all
                ${priorityBorder[alert.priority]}
                ${isSelected ? 'ring-1 ring-cyan-500 bg-slate-800' : 'hover:bg-slate-800/70'}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{getCategoryIcon(alert.category)}</span>
          <div>
            <h3 className="font-medium text-white">{alert.title}</h3>
            <p className="text-xs text-slate-500">{alert.category}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <PriorityBadge priority={alert.priority} />
          <StatusBadge status={alert.status} />
        </div>
      </div>
      
      {/* Message */}
      <p className="text-sm text-slate-300 mb-3">{alert.message}</p>
      
      {/* Tags */}
      {alert.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {alert.tags.map((tag) => (
            <span key={tag} className="px-2 py-0.5 bg-slate-700 text-slate-400 text-xs rounded">
              {tag}
            </span>
          ))}
        </div>
      )}
      
      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{formatAlertTime(alert.createdAt)}</span>
        
        {/* Quick actions */}
        {alert.status === AlertStatus.NEW && (
          <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
            {onAcknowledge && (
              <button
                onClick={onAcknowledge}
                className="px-2 py-1 bg-cyan-600/20 text-cyan-400 rounded hover:bg-cyan-600/30"
              >
                Acknowledge
              </button>
            )}
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="px-2 py-1 bg-slate-600/20 text-slate-400 rounded hover:bg-slate-600/30"
              >
                Dismiss
              </button>
            )}
          </div>
        )}
        
        {alert.assignedTo && (
          <span className="text-slate-400">Assigned: {alert.assignedTo}</span>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AlertList({
  alerts,
  onAcknowledge,
  onResolve,
  onDismiss,
  onEscalate,
  onSelect,
  selectedAlertId,
  showFilters = true,
}: AlertListProps) {
  const [filter, setFilter] = useState({
    priority: '' as string,
    category: '' as string,
    status: '' as string,
    search: '',
  });
  
  // Apply filters
  let filtered = [...alerts];
  
  if (filter.priority) {
    filtered = filtered.filter(a => a.priority === filter.priority);
  }
  if (filter.category) {
    filtered = filtered.filter(a => a.category === filter.category);
  }
  if (filter.status) {
    filtered = filtered.filter(a => a.status === filter.status);
  }
  if (filter.search) {
    const searchLower = filter.search.toLowerCase();
    filtered = filtered.filter(a =>
      a.title.toLowerCase().includes(searchLower) ||
      a.message.toLowerCase().includes(searchLower)
    );
  }
  
  // Sort by priority then time
  filtered.sort((a, b) => {
    const priorityOrder = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    const pDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
    if (pDiff !== 0) return pDiff;
    return b.createdAt - a.createdAt;
  });
  
  return (
    <div className="space-y-4">
      {/* Filters */}
      {showFilters && (
        <div className="flex flex-wrap gap-3">
          <input
            type="text"
            value={filter.search}
            onChange={(e) => setFilter(prev => ({ ...prev, search: e.target.value }))}
            placeholder="Search alerts..."
            className="flex-1 min-w-[200px] px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
          />
          <select
            value={filter.priority}
            onChange={(e) => setFilter(prev => ({ ...prev, priority: e.target.value }))}
            className="px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
          >
            <option value="">All Priorities</option>
            {Object.values(AlertPriority).map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <select
            value={filter.status}
            onChange={(e) => setFilter(prev => ({ ...prev, status: e.target.value }))}
            className="px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
          >
            <option value="">All Statuses</option>
            {Object.values(AlertStatus).map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}
      
      {/* Results */}
      <div className="text-sm text-slate-500">
        Showing {filtered.length} of {alerts.length} alerts
      </div>
      
      {/* Alert list */}
      {filtered.length === 0 ? (
        <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
          <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
          <h3 className="text-lg font-medium text-slate-300 mb-2">No Alerts</h3>
          <p className="text-sm text-slate-500">
            {filter.search || filter.priority || filter.status
              ? 'No alerts match your filters'
              : 'All quiet - no alerts at this time'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              isSelected={selectedAlertId === alert.id}
              onSelect={() => onSelect?.(alert)}
              onAcknowledge={onAcknowledge ? () => onAcknowledge(alert.id) : undefined}
              onDismiss={onDismiss ? () => onDismiss(alert.id) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
