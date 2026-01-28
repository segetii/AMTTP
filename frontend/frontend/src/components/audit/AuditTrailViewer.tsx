'use client';

/**
 * AuditTrailViewer Component
 * 
 * View complete audit trail for a resource
 * 
 * Ground Truth Reference:
 * - Full chain of custody visible
 * - Hash-linked integrity verification
 */

import React from 'react';
import {
  AuditTrail,
  AuditEvent,
  getSeverityColor,
  getCategoryIcon,
} from '@/types/audit';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AuditTrailViewerProps {
  trail: AuditTrail | null;
  isLoading?: boolean;
  onClose?: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIMELINE EVENT
// ═══════════════════════════════════════════════════════════════════════════════

function TimelineEvent({ event, isFirst, isLast }: { event: AuditEvent; isFirst: boolean; isLast: boolean }) {
  const color = getSeverityColor(event.severity);
  const dotColors: Record<string, string> = {
    gray: 'bg-gray-500',
    blue: 'bg-blue-500',
    cyan: 'bg-cyan-500',
    yellow: 'bg-yellow-500',
    orange: 'bg-orange-500',
    red: 'bg-red-500',
  };
  
  return (
    <div className="flex gap-4">
      {/* Timeline line & dot */}
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full ${dotColors[color]} ${!event.success ? 'ring-2 ring-red-500' : ''}`} />
        {!isLast && <div className="w-0.5 flex-1 bg-slate-700 my-1" />}
      </div>
      
      {/* Content */}
      <div className="flex-1 pb-6">
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-3">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex items-center gap-2">
              <span className="text-lg">{getCategoryIcon(event.category)}</span>
              <div>
                <p className="font-medium text-white">{event.action}</p>
                <p className="text-xs text-slate-500">{event.category}</p>
              </div>
            </div>
            <span className="text-xs text-slate-500">
              {new Date(event.timestamp).toLocaleString()}
            </span>
          </div>
          
          <p className="text-sm text-slate-300 mb-2">{event.description}</p>
          
          {/* Metadata */}
          {Object.keys(event.metadata).length > 0 && (
            <div className="bg-slate-900/50 rounded p-2 text-xs font-mono">
              {Object.entries(event.metadata).map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <span className="text-slate-500">{key}:</span>
                  <span className="text-slate-300">{JSON.stringify(value)}</span>
                </div>
              ))}
            </div>
          )}
          
          {/* Error if failed */}
          {!event.success && event.errorMessage && (
            <div className="mt-2 p-2 bg-red-900/20 border border-red-600/30 rounded text-xs text-red-400">
              {event.errorCode && <span className="font-medium">[{event.errorCode}]</span>} {event.errorMessage}
            </div>
          )}
          
          {/* Actor & Hash */}
          <div className="mt-2 pt-2 border-t border-slate-700 flex items-center justify-between text-xs text-slate-500">
            <span>
              Actor: {event.actorType} {event.actorId !== 'system' ? `(${event.actorId})` : ''}
            </span>
            <span className="font-mono">Hash: {event.hash.slice(0, 8)}...</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AuditTrailViewer({
  trail,
  isLoading = false,
  onClose,
}: AuditTrailViewerProps) {
  if (isLoading) {
    return (
      <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-slate-700 rounded w-1/3" />
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-4">
                <div className="w-3 h-3 bg-slate-700 rounded-full" />
                <div className="flex-1 h-24 bg-slate-700 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  
  if (!trail) {
    return (
      <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-8 text-center">
        <svg className="w-12 h-12 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h3 className="text-lg font-medium text-slate-300 mb-2">No Audit Trail</h3>
        <p className="text-sm text-slate-500">
          Select a resource to view its audit trail
        </p>
      </div>
    );
  }
  
  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div>
          <h2 className="text-lg font-medium text-white">Audit Trail</h2>
          <p className="text-sm text-slate-400">
            {trail.resourceType}: {trail.resourceId}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm text-slate-500">
            {trail.eventCount} events
          </span>
          {onClose && (
            <button
              onClick={onClose}
              className="text-slate-500 hover:text-white"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
      
      {/* Timeline */}
      <div className="p-4">
        {trail.events.length === 0 ? (
          <div className="text-center py-8 text-slate-500">
            No events recorded for this resource
          </div>
        ) : (
          <div className="space-y-0">
            {trail.events.map((event, idx) => (
              <TimelineEvent
                key={event.id}
                event={event}
                isFirst={idx === 0}
                isLast={idx === trail.events.length - 1}
              />
            ))}
          </div>
        )}
      </div>
      
      {/* Footer with time range */}
      <div className="px-4 py-3 border-t border-slate-700 text-xs text-slate-500 flex items-center justify-between">
        <span>First: {trail.firstEvent ? new Date(trail.firstEvent).toLocaleString() : 'N/A'}</span>
        <span>Last: {trail.lastEvent ? new Date(trail.lastEvent).toLocaleString() : 'N/A'}</span>
      </div>
    </div>
  );
}
