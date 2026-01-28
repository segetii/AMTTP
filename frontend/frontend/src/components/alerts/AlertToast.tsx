'use client';

/**
 * AlertToast Component
 * 
 * Toast notifications for real-time alerts
 * 
 * Ground Truth Reference:
 * - Non-blocking notification display
 * - Priority-based styling
 * - Quick dismiss/action capability
 */

import React from 'react';
import {
  Alert,
  AlertPriority,
  getPriorityColor,
  getCategoryIcon,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AlertToastProps {
  alert: Alert;
  onDismiss: () => void;
  onAcknowledge?: () => void;
  onView?: () => void;
}

interface AlertToastContainerProps {
  toasts: Alert[];
  onDismiss: (alertId: string) => void;
  onAcknowledge?: (alertId: string) => void;
  onView?: (alert: Alert) => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SINGLE TOAST
// ═══════════════════════════════════════════════════════════════════════════════

function AlertToast({ alert, onDismiss, onAcknowledge, onView }: AlertToastProps) {
  const color = getPriorityColor(alert.priority);
  
  const bgColors: Record<string, string> = {
    blue: 'bg-blue-900/90 border-blue-600',
    yellow: 'bg-yellow-900/90 border-yellow-600',
    orange: 'bg-orange-900/90 border-orange-600',
    red: 'bg-red-900/90 border-red-600',
  };
  
  const iconColors: Record<string, string> = {
    blue: 'text-blue-400',
    yellow: 'text-yellow-400',
    orange: 'text-orange-400',
    red: 'text-red-400',
  };
  
  return (
    <div
      className={`w-96 rounded-lg border shadow-lg backdrop-blur-sm animate-slide-in-right
                ${bgColors[color]}`}
    >
      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <span className={`text-xl flex-shrink-0 ${iconColors[color]}`}>
          {getCategoryIcon(alert.category)}
        </span>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h4 className="font-medium text-white">{alert.title}</h4>
              <p className="text-xs text-slate-400">{alert.category} • {alert.priority}</p>
            </div>
            <button
              onClick={onDismiss}
              className="text-slate-400 hover:text-white flex-shrink-0"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          <p className="text-sm text-slate-300 mt-1 line-clamp-2">{alert.message}</p>
        </div>
      </div>
      
      {/* Actions */}
      <div className="flex border-t border-slate-700/50">
        {onView && (
          <button
            onClick={onView}
            className="flex-1 px-4 py-2 text-sm text-cyan-400 hover:bg-slate-800/50 transition-colors"
          >
            View Details
          </button>
        )}
        {onAcknowledge && (
          <button
            onClick={onAcknowledge}
            className="flex-1 px-4 py-2 text-sm text-white hover:bg-slate-800/50 transition-colors border-l border-slate-700/50"
          >
            Acknowledge
          </button>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TOAST CONTAINER
// ═══════════════════════════════════════════════════════════════════════════════

export default function AlertToastContainer({
  toasts,
  onDismiss,
  onAcknowledge,
  onView,
}: AlertToastContainerProps) {
  if (toasts.length === 0) return null;
  
  return (
    <div className="fixed top-4 right-4 z-50 space-y-3">
      {toasts.map((toast) => (
        <AlertToast
          key={toast.id}
          alert={toast}
          onDismiss={() => onDismiss(toast.id)}
          onAcknowledge={onAcknowledge ? () => onAcknowledge(toast.id) : undefined}
          onView={onView ? () => onView(toast) : undefined}
        />
      ))}
    </div>
  );
}

// Add animation styles to global CSS or use Tailwind plugin
// @keyframes slide-in-right {
//   from { transform: translateX(100%); opacity: 0; }
//   to { transform: translateX(0); opacity: 1; }
// }
// .animate-slide-in-right { animation: slide-in-right 0.3s ease-out; }
