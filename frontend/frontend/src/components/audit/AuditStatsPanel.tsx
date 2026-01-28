'use client';

/**
 * AuditStatsPanel Component
 * 
 * Statistics and metrics from audit events
 * 
 * Ground Truth Reference:
 * - At-a-glance compliance metrics
 * - Category and severity breakdowns
 */

import React from 'react';
import {
  AuditStats,
  AuditCategory,
  AuditSeverity,
  getSeverityColor,
  getCategoryIcon,
} from '@/types/audit';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AuditStatsPanelProps {
  stats: AuditStats | null;
  isLoading?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STAT CARD
// ═══════════════════════════════════════════════════════════════════════════════

function StatCard({ label, value, color = 'white' }: { label: string; value: string | number; color?: string }) {
  const colorClasses: Record<string, string> = {
    white: 'text-white',
    green: 'text-green-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    cyan: 'text-cyan-400',
  };
  
  return (
    <div className="bg-slate-900/50 rounded-lg p-3 text-center">
      <p className={`text-xl font-bold ${colorClasses[color]}`}>{value}</p>
      <p className="text-xs text-slate-500">{label}</p>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AuditStatsPanel({ stats, isLoading = false }: AuditStatsPanelProps) {
  if (isLoading || !stats) {
    return (
      <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-4 animate-pulse">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bg-slate-900/50 rounded-lg p-3">
              <div className="h-6 bg-slate-700 rounded mb-2" />
              <div className="h-4 bg-slate-700 rounded w-1/2 mx-auto" />
            </div>
          ))}
        </div>
      </div>
    );
  }
  
  // Get top categories
  const topCategories = Object.entries(stats.byCategory)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);
  
  // Get severity distribution
  const severities = Object.values(AuditSeverity);
  
  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <StatCard label="Total Events" value={stats.totalEvents.toLocaleString()} />
        <StatCard label="Success" value={stats.successCount.toLocaleString()} color="green" />
        <StatCard label="Failures" value={stats.failureCount.toLocaleString()} color="red" />
        <StatCard label="Unique Actors" value={stats.uniqueActors} color="cyan" />
        <StatCard label="Resources" value={stats.uniqueResources} />
        <StatCard 
          label="Success Rate" 
          value={`${stats.totalEvents > 0 ? ((stats.successCount / stats.totalEvents) * 100).toFixed(1) : 0}%`}
          color={stats.successCount / stats.totalEvents > 0.95 ? 'green' : 'yellow'}
        />
      </div>
      
      {/* Category & Severity Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* By Category */}
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-3">By Category</h3>
          <div className="space-y-2">
            {topCategories.map(([category, count]) => (
              <div key={category} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span>{getCategoryIcon(category as AuditCategory)}</span>
                  <span className="text-sm text-slate-300">{category}</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-cyan-500"
                      style={{ width: `${(count / stats.totalEvents) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-slate-400 w-10 text-right">{count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
        
        {/* By Severity */}
        <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
          <h3 className="text-sm font-medium text-slate-400 mb-3">By Severity</h3>
          <div className="space-y-2">
            {severities.map((severity) => {
              const count = stats.bySeverity[severity] || 0;
              const color = getSeverityColor(severity);
              const barColors: Record<string, string> = {
                gray: 'bg-gray-500',
                blue: 'bg-blue-500',
                cyan: 'bg-cyan-500',
                yellow: 'bg-yellow-500',
                orange: 'bg-orange-500',
                red: 'bg-red-500',
              };
              
              return (
                <div key={severity} className="flex items-center justify-between">
                  <span className="text-sm text-slate-300">{severity}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className={`h-full ${barColors[color]}`}
                        style={{ width: `${stats.totalEvents > 0 ? (count / stats.totalEvents) * 100 : 0}%` }}
                      />
                    </div>
                    <span className="text-sm text-slate-400 w-10 text-right">{count}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
