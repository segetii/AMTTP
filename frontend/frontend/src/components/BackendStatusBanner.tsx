'use client';

import React, { useEffect, useState, useCallback } from 'react';
import {
  BackendHealthState,
  ServiceStatus,
  getBackendHealthMonitor,
} from '@/lib/backend-health-monitor';

/**
 * React hook for backend health monitoring.
 * Starts monitoring on mount, cleans up on unmount.
 */
export function useBackendHealth() {
  const [state, setState] = useState<BackendHealthState | null>(null);

  useEffect(() => {
    const monitor = getBackendHealthMonitor();
    monitor.start();
    setState(monitor.state);
    const unsub = monitor.subscribe((s) => setState({ ...s }));
    return () => {
      unsub();
      // Don't stop — other components may still use it
    };
  }, []);

  const monitor = getBackendHealthMonitor();

  return {
    state,
    hasOutage: monitor.hasOutage,
    isFullyHealthy: monitor.isFullyHealthy,
    summary: monitor.summary,
    refresh: useCallback(() => monitor.checkNow(), [monitor]),
  };
}

const statusColors: Record<ServiceStatus, string> = {
  online: '#10B981',
  degraded: '#F59E0B',
  offline: '#DC2626',
  unknown: '#6B7280',
};

/**
 * Visual banner showing backend health status.
 * Hidden when all services are online.
 */
export function BackendStatusBanner() {
  const { state, hasOutage, isFullyHealthy, summary, refresh } = useBackendHealth();
  const [expanded, setExpanded] = useState(false);

  if (!state || isFullyHealthy) return null;

  const bannerColor = hasOutage ? '#DC2626' : '#F59E0B';

  return (
    <div
      style={{
        background: `${bannerColor}18`,
        borderBottom: `1px solid ${bannerColor}40`,
        padding: '8px 16px',
        fontFamily: 'system-ui, -apple-system, sans-serif',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          cursor: 'pointer',
        }}
        onClick={() => setExpanded(!expanded)}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
      >
        <span style={{ fontSize: 16 }}>{hasOutage ? '⚠️' : '⏳'}</span>
        <span
          style={{
            flex: 1,
            color: bannerColor,
            fontWeight: 600,
            fontSize: 13,
          }}
        >
          {summary}
        </span>
        {hasOutage && (
          <span
            style={{
              background: `${bannerColor}30`,
              color: bannerColor,
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
            }}
          >
            DATA MAY BE STALE
          </span>
        )}
        <span style={{ color: `${bannerColor}80`, fontSize: 12 }}>
          {expanded ? '▲' : '▼'}
        </span>
      </div>

      {expanded && (
        <div style={{ marginTop: 8, paddingLeft: 24 }}>
          {Object.entries(state.services).map(([key, svc]) => (
            <div
              key={key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '4px 0',
              }}
            >
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: statusColors[svc.status],
                  display: 'inline-block',
                }}
              />
              <span style={{ flex: 1, color: '#D1D5DB', fontSize: 13 }}>
                {svc.name}
              </span>
              <span
                style={{
                  color: statusColors[svc.status],
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                {svc.status === 'online'
                  ? 'Online'
                  : svc.status === 'degraded'
                  ? 'Slow'
                  : svc.status === 'offline'
                  ? 'Offline'
                  : 'Unknown'}
              </span>
              {svc.latencyMs != null && (
                <span style={{ color: '#6B7280', fontSize: 11 }}>
                  {svc.latencyMs}ms
                </span>
              )}
            </div>
          ))}
          <button
            onClick={(e) => {
              e.stopPropagation();
              refresh();
            }}
            style={{
              marginTop: 8,
              background: 'transparent',
              border: `1px solid ${bannerColor}40`,
              color: bannerColor,
              padding: '4px 12px',
              borderRadius: 4,
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            Refresh Status
          </button>
        </div>
      )}
    </div>
  );
}
