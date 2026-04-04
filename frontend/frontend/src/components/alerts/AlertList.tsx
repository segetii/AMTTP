'use client';

/**
 * AlertList Component — Clean, minimal alert cards
 */

import React, { useState } from 'react';
import {
  Alert,
  AlertPriority,
  AlertCategory,
  AlertStatus,
  getCategoryIcon,
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
// COMPACT ALERT ROW
// ═══════════════════════════════════════════════════════════════════════════════

const priorityAccent: Record<AlertPriority, string> = {
  [AlertPriority.CRITICAL]: 'border-l-red-500',
  [AlertPriority.HIGH]:     'border-l-orange-400',
  [AlertPriority.MEDIUM]:   'border-l-amber-400',
  [AlertPriority.LOW]:      'border-l-sky-400',
};

const priorityDot: Record<AlertPriority, string> = {
  [AlertPriority.CRITICAL]: 'bg-red-500 shadow-red-500/40 shadow-[0_0_6px]',
  [AlertPriority.HIGH]:     'bg-orange-400',
  [AlertPriority.MEDIUM]:   'bg-amber-400',
  [AlertPriority.LOW]:      'bg-sky-400',
};

const statusLabel: Record<string, { text: string; cls: string }> = {
  NEW:          { text: 'New',          cls: 'text-cyan-400' },
  ACKNOWLEDGED: { text: 'Ack\'d',      cls: 'text-amber-400' },
  IN_PROGRESS:  { text: 'In Progress', cls: 'text-blue-400' },
  RESOLVED:     { text: 'Resolved',    cls: 'text-emerald-400' },
  DISMISSED:    { text: 'Dismissed',    cls: 'text-slate-500' },
  ESCALATED:    { text: 'Escalated',   cls: 'text-red-400' },
};

function AlertRow({
  alert,
  isSelected,
  onSelect,
  onAcknowledge,
}: {
  alert: Alert;
  isSelected: boolean;
  onSelect: () => void;
  onAcknowledge?: () => void;
}) {
  const m = alert.metadata || {};
  const riskScore = (m.riskScore as number) ?? 0;
  const st = statusLabel[alert.status] || statusLabel.NEW;

  return (
    <div
      onClick={onSelect}
      className={`
        group relative flex items-center gap-4 px-4 py-3.5
        border-l-[3px] border-b border-b-slate-800/60
        cursor-pointer transition-all duration-150
        ${priorityAccent[alert.priority]}
        ${isSelected
          ? 'bg-slate-800/80 border-b-slate-700'
          : 'bg-transparent hover:bg-slate-800/40'}
      `}
    >
      {/* Priority dot */}
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${priorityDot[alert.priority]}`} />

      {/* Icon */}
      <span className="text-base flex-shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
        {getCategoryIcon(alert.category)}
      </span>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <h3 className="text-[13px] font-medium text-slate-200 truncate">{alert.title}</h3>
          {riskScore > 0 && (
            <span className={`text-[11px] font-semibold tabular-nums flex-shrink-0 ${
              riskScore >= 80 ? 'text-red-400' : riskScore >= 60 ? 'text-orange-400' : 'text-amber-400'
            }`}>{riskScore.toFixed(0)}</span>
          )}
        </div>
        <p className="text-xs text-slate-500 truncate mt-0.5">{alert.message}</p>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3 flex-shrink-0">
        <span className={`text-[11px] font-medium ${st.cls}`}>{st.text}</span>
        <span className="text-[11px] text-slate-600 tabular-nums w-14 text-right">{formatAlertTime(alert.createdAt)}</span>

        {/* Quick ack */}
        {alert.status === AlertStatus.NEW && onAcknowledge && (
          <button
            onClick={(e) => { e.stopPropagation(); onAcknowledge(); }}
            className="opacity-0 group-hover:opacity-100 text-[11px] px-2 py-0.5 rounded
                       bg-slate-700/80 text-slate-300 hover:bg-slate-600 hover:text-white
                       transition-all duration-150"
          >
            Ack
          </button>
        )}

        {/* Chevron */}
        <svg className="w-4 h-4 text-slate-600 group-hover:text-slate-400 transition-colors flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5l7 7-7 7" />
        </svg>
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
    status: '' as string,
    search: '',
  });

  let filtered = [...alerts];
  if (filter.priority) filtered = filtered.filter(a => a.priority === filter.priority);
  if (filter.status) filtered = filtered.filter(a => a.status === filter.status);
  if (filter.search) {
    const q = filter.search.toLowerCase();
    filtered = filtered.filter(a =>
      a.title.toLowerCase().includes(q) || a.message.toLowerCase().includes(q)
    );
  }

  filtered.sort((a, b) => {
    const ord = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
    const p = ord[a.priority] - ord[b.priority];
    return p !== 0 ? p : b.createdAt - a.createdAt;
  });

  return (
    <div className="space-y-0">
      {/* Toolbar */}
      {showFilters && (
        <div className="flex items-center gap-2 px-1 pb-4">
          <div className="relative flex-1 max-w-xs">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={filter.search}
              onChange={(e) => setFilter(p => ({ ...p, search: e.target.value }))}
              placeholder="Search..."
              className="w-full pl-9 pr-3 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg
                         text-sm text-slate-300 placeholder-slate-600
                         focus:outline-none focus:border-slate-600 focus:bg-slate-800 transition-colors"
            />
          </div>
          <select
            value={filter.priority}
            onChange={(e) => setFilter(p => ({ ...p, priority: e.target.value }))}
            className="px-2.5 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg text-xs text-slate-400
                       focus:outline-none focus:border-slate-600 transition-colors"
          >
            <option value="">Priority</option>
            {Object.values(AlertPriority).map((p) => (
              <option key={p} value={p}>{p[0] + p.slice(1).toLowerCase()}</option>
            ))}
          </select>
          <select
            value={filter.status}
            onChange={(e) => setFilter(p => ({ ...p, status: e.target.value }))}
            className="px-2.5 py-1.5 bg-slate-800/60 border border-slate-700/60 rounded-lg text-xs text-slate-400
                       focus:outline-none focus:border-slate-600 transition-colors"
          >
            <option value="">Status</option>
            {Object.values(AlertStatus).map((s) => (
              <option key={s} value={s}>{s[0] + s.slice(1).toLowerCase().replace('_', ' ')}</option>
            ))}
          </select>
          <span className="text-[11px] text-slate-600 ml-auto tabular-nums">{filtered.length} / {alerts.length}</span>
        </div>
      )}

      {/* List */}
      {filtered.length === 0 ? (
        <div className="py-16 text-center">
          <div className="text-4xl mb-3 opacity-30">🔔</div>
          <p className="text-sm text-slate-500">
            {filter.search || filter.priority || filter.status
              ? 'No alerts match your filters'
              : 'All quiet — no alerts right now'}
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800/80 overflow-hidden divide-y divide-slate-800/40">
          {filtered.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              isSelected={selectedAlertId === alert.id}
              onSelect={() => onSelect?.(alert)}
              onAcknowledge={onAcknowledge ? () => onAcknowledge(alert.id) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
