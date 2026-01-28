'use client';

/**
 * AuditEventList Component
 * 
 * Display and filter audit events
 * 
 * Ground Truth Reference:
 * - Full transparency of all logged events
 * - Searchable and filterable for compliance
 */

import React, { useState } from 'react';
import {
  AuditEvent,
  AuditCategory,
  AuditAction,
  AuditSeverity,
  getSeverityColor,
  getCategoryIcon,
  formatAuditTimestamp,
} from '@/types/audit';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AuditEventListProps {
  events: AuditEvent[];
  onEventSelect?: (event: AuditEvent) => void;
  selectedEventId?: string;
  isLoading?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SEVERITY BADGE
// ═══════════════════════════════════════════════════════════════════════════════

function SeverityBadge({ severity }: { severity: AuditSeverity }) {
  const color = getSeverityColor(severity);
  const colorClasses: Record<string, string> = {
    gray: 'bg-gray-900/30 text-gray-400 border-gray-600/30',
    blue: 'bg-blue-900/30 text-blue-400 border-blue-600/30',
    cyan: 'bg-cyan-900/30 text-cyan-400 border-cyan-600/30',
    yellow: 'bg-yellow-900/30 text-yellow-400 border-yellow-600/30',
    orange: 'bg-orange-900/30 text-orange-400 border-orange-600/30',
    red: 'bg-red-900/30 text-red-400 border-red-600/30',
  };
  
  return (
    <span className={`px-2 py-0.5 text-xs font-medium rounded border ${colorClasses[color]}`}>
      {severity}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVENT ROW
// ═══════════════════════════════════════════════════════════════════════════════

function EventRow({
  event,
  isSelected,
  onSelect,
}: {
  event: AuditEvent;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const timeAgo = (timestamp: number) => {
    const seconds = Math.floor((Date.now() - timestamp) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    return new Date(timestamp).toLocaleDateString();
  };
  
  return (
    <div
      onClick={onSelect}
      className={`bg-slate-800/50 rounded-lg border p-3 cursor-pointer transition-all
                ${isSelected 
                  ? 'border-cyan-500 bg-slate-800' 
                  : 'border-slate-700 hover:border-slate-600'}`}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: Icon & Content */}
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <span className="text-xl flex-shrink-0">{getCategoryIcon(event.category)}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-medium text-white truncate">{event.description}</span>
              {!event.success && (
                <span className="px-1.5 py-0.5 text-xs bg-red-900/30 text-red-400 rounded">Failed</span>
              )}
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>{event.category}</span>
              <span>•</span>
              <span>{event.action}</span>
              {event.resourceName && (
                <>
                  <span>•</span>
                  <span className="text-slate-400">{event.resourceName}</span>
                </>
              )}
            </div>
          </div>
        </div>
        
        {/* Right: Severity & Time */}
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <SeverityBadge severity={event.severity} />
          <span className="text-xs text-slate-500">{timeAgo(event.timestamp)}</span>
        </div>
      </div>
      
      {/* Actor info */}
      <div className="mt-2 pt-2 border-t border-slate-700/50 flex items-center justify-between text-xs text-slate-500">
        <span>
          {event.actorType === 'USER' 
            ? `${event.actorRole || 'User'} ${event.actorWallet ? `(${event.actorWallet.slice(0, 8)}...)` : ''}`
            : event.actorType}
        </span>
        <span className="text-slate-600">{event.id}</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AuditEventList({
  events,
  onEventSelect,
  selectedEventId,
  isLoading = false,
}: AuditEventListProps) {
  const [filter, setFilter] = useState({
    category: '' as string,
    severity: '' as string,
    search: '',
  });
  
  // Apply filters
  let filteredEvents = [...events];
  
  if (filter.category) {
    filteredEvents = filteredEvents.filter(e => e.category === filter.category);
  }
  if (filter.severity) {
    filteredEvents = filteredEvents.filter(e => e.severity === filter.severity);
  }
  if (filter.search) {
    const searchLower = filter.search.toLowerCase();
    filteredEvents = filteredEvents.filter(e =>
      e.description.toLowerCase().includes(searchLower) ||
      e.resourceId.toLowerCase().includes(searchLower) ||
      e.resourceName?.toLowerCase().includes(searchLower)
    );
  }
  
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="bg-slate-800/50 rounded-lg border border-slate-700 p-3 animate-pulse">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-slate-700 rounded" />
              <div className="flex-1">
                <div className="h-4 bg-slate-700 rounded w-3/4 mb-2" />
                <div className="h-3 bg-slate-700 rounded w-1/2" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }
  
  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          value={filter.search}
          onChange={(e) => setFilter(prev => ({ ...prev, search: e.target.value }))}
          placeholder="Search events..."
          className="flex-1 min-w-[200px] px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
        />
        <select
          value={filter.category}
          onChange={(e) => setFilter(prev => ({ ...prev, category: e.target.value }))}
          className="px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
        >
          <option value="">All Categories</option>
          {Object.values(AuditCategory).map((cat) => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>
        <select
          value={filter.severity}
          onChange={(e) => setFilter(prev => ({ ...prev, severity: e.target.value }))}
          className="px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
        >
          <option value="">All Severities</option>
          {Object.values(AuditSeverity).map((sev) => (
            <option key={sev} value={sev}>{sev}</option>
          ))}
        </select>
      </div>
      
      {/* Results count */}
      <div className="text-sm text-slate-500">
        Showing {filteredEvents.length} of {events.length} events
      </div>
      
      {/* Event list */}
      {filteredEvents.length === 0 ? (
        <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
          <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="text-lg font-medium text-slate-300 mb-2">No Events Found</h3>
          <p className="text-sm text-slate-500">
            {filter.search || filter.category || filter.severity 
              ? 'Try adjusting your filters'
              : 'No audit events have been recorded'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredEvents.map((event) => (
            <EventRow
              key={event.id}
              event={event}
              isSelected={selectedEventId === event.id}
              onSelect={() => onEventSelect?.(event)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
