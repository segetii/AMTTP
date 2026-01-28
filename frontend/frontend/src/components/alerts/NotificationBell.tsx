'use client';

/**
 * NotificationBell Component
 * 
 * Header notification indicator with dropdown
 * 
 * Ground Truth Reference:
 * - Real-time alert count
 * - Quick alert preview
 * - Priority-based indicator
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Alert,
  AlertPriority,
  AlertStatus,
  getPriorityColor,
  getCategoryIcon,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface NotificationBellProps {
  alerts: Alert[];
  onView: (alert: Alert) => void;
  onViewAll: () => void;
  onAcknowledge: (alertId: string) => void;
  onClearAll: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function getHighestPriority(alerts: Alert[]): AlertPriority | null {
  const priorities: AlertPriority[] = [
    AlertPriority.CRITICAL,
    AlertPriority.HIGH,
    AlertPriority.MEDIUM,
    AlertPriority.LOW,
  ];
  for (const priority of priorities) {
    if (alerts.some(a => a.priority === priority && a.status === AlertStatus.NEW)) {
      return priority;
    }
  }
  return null;
}

function formatTimeAgo(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function NotificationBell({
  alerts,
  onView,
  onViewAll,
  onAcknowledge,
  onClearAll,
}: NotificationBellProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  
  const activeAlerts = alerts.filter(a => a.status === AlertStatus.NEW);
  const unreadCount = activeAlerts.length;
  const highestPriority = getHighestPriority(alerts);
  
  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  const badgeColor = highestPriority 
    ? {
        [AlertPriority.CRITICAL]: 'bg-red-500',
        [AlertPriority.HIGH]: 'bg-orange-500',
        [AlertPriority.MEDIUM]: 'bg-yellow-500',
        [AlertPriority.LOW]: 'bg-blue-500',
      }[highestPriority]
    : 'bg-slate-500';
  
  const bellAnimation = highestPriority === AlertPriority.CRITICAL ? 'animate-pulse' : '';
  
  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`relative p-2 rounded-lg hover:bg-slate-800 transition-colors ${bellAnimation}`}
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      >
        <svg 
          className={`w-6 h-6 ${highestPriority === 'CRITICAL' ? 'text-red-400' : 'text-slate-400'}`}
          fill="none" 
          viewBox="0 0 24 24" 
          stroke="currentColor"
        >
          <path 
            strokeLinecap="round" 
            strokeLinejoin="round" 
            strokeWidth={2} 
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" 
          />
        </svg>
        
        {/* Badge */}
        {unreadCount > 0 && (
          <span className={`absolute -top-1 -right-1 min-w-[20px] h-5 flex items-center justify-center
                         px-1.5 rounded-full text-xs font-bold text-white ${badgeColor}`}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>
      
      {/* Dropdown */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-96 bg-slate-900 rounded-xl border border-slate-700 
                      shadow-2xl overflow-hidden z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-slate-800 border-b border-slate-700">
            <h3 className="font-semibold text-white">Notifications</h3>
            <div className="flex gap-2">
              {unreadCount > 0 && (
                <button
                  onClick={onClearAll}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  Clear all
                </button>
              )}
              <button
                onClick={onViewAll}
                className="text-xs text-cyan-400 hover:text-cyan-300"
              >
                View all
              </button>
            </div>
          </div>
          
          {/* Alert List */}
          <div className="max-h-96 overflow-y-auto">
            {alerts.slice(0, 10).map((alert) => {
              const color = getPriorityColor(alert.priority);
              const borderColors: Record<string, string> = {
                blue: 'border-l-blue-500',
                yellow: 'border-l-yellow-500',
                orange: 'border-l-orange-500',
                red: 'border-l-red-500',
              };
              
              return (
                <div
                  key={alert.id}
                  className={`px-4 py-3 border-b border-slate-800 hover:bg-slate-800/50 cursor-pointer
                            border-l-4 ${borderColors[color]}
                            ${alert.status !== AlertStatus.NEW ? 'opacity-60' : ''}`}
                  onClick={() => onView(alert)}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-lg">{getCategoryIcon(alert.category)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <h4 className={`text-sm font-medium truncate ${
                          alert.status === AlertStatus.NEW ? 'text-white' : 'text-slate-400'
                        }`}>
                          {alert.title}
                        </h4>
                        <span className="text-xs text-slate-500 flex-shrink-0">
                          {formatTimeAgo(alert.createdAt)}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">
                        {alert.message}
                      </p>
                      
                      {alert.status === AlertStatus.NEW && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onAcknowledge(alert.id);
                          }}
                          className="mt-2 text-xs text-cyan-400 hover:text-cyan-300"
                        >
                          Acknowledge
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            
            {alerts.length === 0 && (
              <div className="py-12 text-center text-slate-400">
                <div className="text-3xl mb-2">🔔</div>
                <p className="text-sm">No notifications</p>
              </div>
            )}
          </div>
          
          {/* Footer */}
          {alerts.length > 10 && (
            <div className="px-4 py-2 bg-slate-800 border-t border-slate-700 text-center">
              <button
                onClick={onViewAll}
                className="text-sm text-cyan-400 hover:text-cyan-300"
              >
                View {alerts.length - 10} more notifications
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
