'use client';

/**
 * Alerts Management Page
 * 
 * Sprint 10: Real-Time Alerts & Notifications
 * 
 * Ground Truth Reference:
 * - Alert monitoring dashboard
 * - Rule configuration
 * - Channel management
 */

import React, { useState } from 'react';
import { useAlerts, useNotificationToast } from '@/lib/alert-service';
import {
  Alert,
  AlertRule,
  AlertStatus,
  AlertPriority,
  DeliveryChannel,
} from '@/types/alert';
import AlertList from '@/components/alerts/AlertList';
import AlertToastContainer from '@/components/alerts/AlertToast';
import AlertRuleEditor from '@/components/alerts/AlertRuleEditor';
import AlertChannelConfig from '@/components/alerts/AlertChannelConfig';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

type TabType = 'alerts' | 'rules' | 'channels';

// UI-simplified channel type for channel config component
interface UIChannel {
  id: string;
  name: string;
  type: DeliveryChannel;
  enabled: boolean;
  config: Record<string, unknown>;
  createdAt: number;
}

// UI-simplified notification preferences
interface UIPreferences {
  soundEnabled: boolean;
  desktopNotifications: boolean;
  emailDigest: boolean;
  digestFrequency?: 'hourly' | 'daily' | 'weekly';
  quietHoursEnabled: boolean;
  quietHoursStart?: string;
  quietHoursEnd?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function AlertStats({ alerts }: { alerts: Alert[] }) {
  const activeCount = alerts.filter(a => a.status === AlertStatus.NEW).length;
  const criticalCount = alerts.filter(a => a.priority === AlertPriority.CRITICAL && a.status === AlertStatus.NEW).length;
  const acknowledgedCount = alerts.filter(a => a.status === AlertStatus.ACKNOWLEDGED).length;
  const resolvedToday = alerts.filter(a => {
    if (a.status !== AlertStatus.RESOLVED || !a.resolvedAt) return false;
    const today = new Date();
    const resolvedDate = new Date(a.resolvedAt);
    return resolvedDate.toDateString() === today.toDateString();
  }).length;
  
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Active Alerts</span>
          <span className="text-2xl">🔔</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-white">{activeCount}</span>
        </div>
      </div>
      
      <div className="bg-slate-800 rounded-lg p-4 border border-red-900/50">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Critical</span>
          <span className="text-2xl">🚨</span>
        </div>
        <div className="mt-2">
          <span className={`text-3xl font-bold ${criticalCount > 0 ? 'text-red-400' : 'text-white'}`}>
            {criticalCount}
          </span>
        </div>
      </div>
      
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Acknowledged</span>
          <span className="text-2xl">✋</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-yellow-400">{acknowledgedCount}</span>
        </div>
      </div>
      
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-sm">Resolved Today</span>
          <span className="text-2xl">✅</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-green-400">{resolvedToday}</span>
        </div>
      </div>
    </div>
  );
}

function RulesList({
  rules,
  onEdit,
  onToggle,
  onDelete,
}: {
  rules: AlertRule[];
  onEdit: (rule: AlertRule) => void;
  onToggle: (ruleId: string, enabled: boolean) => void;
  onDelete: (ruleId: string) => void;
}) {
  return (
    <div className="space-y-3">
      {rules.map((rule) => (
        <div
          key={rule.id}
          className={`bg-slate-800 rounded-lg p-4 border transition-all ${
            rule.enabled ? 'border-slate-700' : 'border-slate-800 opacity-60'
          }`}
        >
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h4 className="font-medium text-white">{rule.name}</h4>
                <span className={`px-2 py-0.5 rounded text-xs ${
                  rule.priority === AlertPriority.CRITICAL ? 'bg-red-900/50 text-red-300' :
                  rule.priority === AlertPriority.HIGH ? 'bg-orange-900/50 text-orange-300' :
                  rule.priority === AlertPriority.MEDIUM ? 'bg-yellow-900/50 text-yellow-300' :
                  'bg-slate-700 text-slate-300'
                }`}>
                  {rule.priority}
                </span>
                <span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                  {rule.category}
                </span>
              </div>
              {rule.description && (
                <p className="text-sm text-slate-400 mt-1">{rule.description}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
                <span>{rule.conditions.length} condition(s)</span>
                <span>Cooldown: {rule.cooldownMinutes}m</span>
              </div>
            </div>
            
            <div className="flex items-center gap-2">
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={rule.enabled}
                  onChange={(e) => onToggle(rule.id, e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer 
                              peer-checked:after:translate-x-full peer-checked:bg-cyan-600
                              after:content-[''] after:absolute after:top-[2px] after:left-[2px] 
                              after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all" />
              </label>
              
              <button
                onClick={() => onEdit(rule)}
                className="p-2 text-slate-400 hover:text-white"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              
              <button
                onClick={() => onDelete(rule.id)}
                className="p-2 text-slate-400 hover:text-red-400"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      ))}
      
      {rules.length === 0 && (
        <div className="text-center py-12 text-slate-400">
          <div className="text-4xl mb-2">📋</div>
          <p>No alert rules configured</p>
          <p className="text-sm mt-1">Create a rule to start monitoring</p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function AlertsPage() {
  const {
    alerts,
    rules,
    acknowledgeAlert,
    resolveAlert,
    escalateAlert,
    toggleRule,
  } = useAlerts();
  
  const { toasts, dismissToast } = useNotificationToast();
  
  const [activeTab, setActiveTab] = useState<TabType>('alerts');
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [showRuleEditor, setShowRuleEditor] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  
  // Mock channel data for UI
  const [channels, setChannels] = useState<UIChannel[]>([
    { id: 'ch-1', name: 'Slack Alerts', type: DeliveryChannel.SLACK, enabled: true, config: { webhookUrl: 'https://hooks.slack.com/...' }, createdAt: Date.now() - 86400000 },
    { id: 'ch-2', name: 'Email Notifications', type: DeliveryChannel.EMAIL, enabled: true, config: { recipients: ['admin@company.com'] }, createdAt: Date.now() - 172800000 },
  ]);
  
  const [preferences, setPreferences] = useState<UIPreferences>({
    soundEnabled: true,
    desktopNotifications: true,
    emailDigest: false,
    quietHoursEnabled: false,
    quietHoursStart: '22:00',
    quietHoursEnd: '08:00',
  });
  
  const currentUserId = 'user-001'; // Would come from auth context
  
  const handleAcknowledge = (alertId: string) => {
    acknowledgeAlert(alertId, currentUserId);
  };
  
  const handleResolve = (alertId: string) => {
    resolveAlert(alertId, currentUserId);
  };
  
  const handleEscalate = (alertId: string) => {
    escalateAlert(alertId, currentUserId);
  };
  
  const handleSaveRule = (ruleData: Omit<AlertRule, 'id' | 'createdAt' | 'updatedAt' | 'createdBy'>) => {
    // In real app, would call API to create/update rule
    console.log('Save rule:', ruleData);
    setShowRuleEditor(false);
    setEditingRule(null);
  };
  
  const handleEditRule = (rule: AlertRule) => {
    setEditingRule(rule);
    setShowRuleEditor(true);
  };
  
  const handleDeleteRule = (ruleId: string) => {
    // In real app, would call API to delete rule
    console.log('Delete rule:', ruleId);
  };
  
  const handleToggleChannel = (channelId: string, enabled: boolean) => {
    setChannels(channels.map(ch => ch.id === channelId ? { ...ch, enabled } : ch));
  };
  
  const handleAddChannel = (channel: Omit<UIChannel, 'id' | 'createdAt'>) => {
    setChannels([...channels, { ...channel, id: `ch-${Date.now()}`, createdAt: Date.now() }]);
  };
  
  const handleTestChannel = (channelId: string) => {
    console.log('Test channel:', channelId);
  };
  
  return (
    <div className="min-h-screen bg-slate-950 p-6">
      {/* Toast Notifications */}
      <AlertToastContainer
        toasts={toasts}
        onDismiss={dismissToast}
        onAcknowledge={handleAcknowledge}
        onView={setSelectedAlert}
      />
      
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Alert Center</h1>
        <p className="text-slate-400">Monitor and manage system alerts in real-time</p>
      </div>
      
      {/* Stats */}
      <AlertStats alerts={alerts} />
      
      {/* Tabs */}
      <div className="flex gap-4 mb-6 border-b border-slate-800">
        {[
          { id: 'alerts' as TabType, label: 'Active Alerts', icon: '🔔' },
          { id: 'rules' as TabType, label: 'Alert Rules', icon: '⚙️' },
          { id: 'channels' as TabType, label: 'Channels', icon: '📡' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? 'text-cyan-400 border-cyan-400'
                : 'text-slate-400 border-transparent hover:text-white'
            }`}
          >
            <span className="mr-2">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>
      
      {/* Content */}
      <div className="space-y-6">
        {activeTab === 'alerts' && (
          <AlertList
            alerts={alerts}
            onAcknowledge={handleAcknowledge}
            onResolve={handleResolve}
            onEscalate={handleEscalate}
          />
        )}
        
        {activeTab === 'rules' && (
          <>
            <div className="flex justify-end">
              <button
                onClick={() => {
                  setEditingRule(null);
                  setShowRuleEditor(true);
                }}
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm"
              >
                + Create Rule
              </button>
            </div>
            
            {showRuleEditor ? (
              <AlertRuleEditor
                rule={editingRule || undefined}
                onSave={handleSaveRule}
                onCancel={() => {
                  setShowRuleEditor(false);
                  setEditingRule(null);
                }}
              />
            ) : (
              <RulesList
                rules={rules}
                onEdit={handleEditRule}
                onToggle={toggleRule}
                onDelete={handleDeleteRule}
              />
            )}
          </>
        )}
        
        {activeTab === 'channels' && (
          <AlertChannelConfig
            channels={channels}
            preferences={preferences}
            onToggleChannel={handleToggleChannel}
            onUpdateChannel={(channel) => setChannels(channels.map(c => c.id === channel.id ? channel : c))}
            onAddChannel={handleAddChannel}
            onUpdatePreferences={setPreferences}
            onTestChannel={handleTestChannel}
          />
        )}
      </div>
      
      {/* Alert Detail Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-900 rounded-xl border border-slate-700 p-6 w-full max-w-lg">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h3 className="text-lg font-semibold text-white">{selectedAlert.title}</h3>
                <div className="flex gap-2 mt-1">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    selectedAlert.priority === AlertPriority.CRITICAL ? 'bg-red-900/50 text-red-300' :
                    selectedAlert.priority === AlertPriority.HIGH ? 'bg-orange-900/50 text-orange-300' :
                    'bg-slate-700 text-slate-300'
                  }`}>
                    {selectedAlert.priority}
                  </span>
                  <span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                    {selectedAlert.category}
                  </span>
                  <span className="px-2 py-0.5 rounded text-xs bg-slate-700 text-slate-300">
                    {selectedAlert.status}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="text-slate-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            
            <p className="text-slate-300 mb-4">{selectedAlert.message}</p>
            
            {selectedAlert.metadata && Object.keys(selectedAlert.metadata).length > 0 && (
              <div className="bg-slate-800 rounded-lg p-3 mb-4">
                <h4 className="text-sm font-medium text-slate-400 mb-2">Details</h4>
                <div className="space-y-1 text-sm">
                  {Object.entries(selectedAlert.metadata).map(([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-slate-500">{key}:</span>
                      <span className="text-white font-mono">{String(value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <div className="text-xs text-slate-500 mb-4">
              Created: {selectedAlert.createdAt.toLocaleString()}
              {selectedAlert.acknowledgedAt && (
                <> • Acknowledged: {new Date(selectedAlert.acknowledgedAt).toLocaleString()}</>
              )}
              {selectedAlert.resolvedAt && (
                <> • Resolved: {new Date(selectedAlert.resolvedAt).toLocaleString()}</>
              )}
            </div>
            
            <div className="flex gap-2">
              {selectedAlert.status === AlertStatus.NEW && (
                <>
                  <button
                    onClick={() => {
                      handleAcknowledge(selectedAlert.id);
                      setSelectedAlert(null);
                    }}
                    className="flex-1 px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg"
                  >
                    Acknowledge
                  </button>
                  <button
                    onClick={() => {
                      handleResolve(selectedAlert.id);
                      setSelectedAlert(null);
                    }}
                    className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg"
                  >
                    Resolve
                  </button>
                </>
              )}
              {selectedAlert.status === AlertStatus.ACKNOWLEDGED && (
                <button
                  onClick={() => {
                    handleResolve(selectedAlert.id);
                    setSelectedAlert(null);
                  }}
                  className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg"
                >
                  Resolve
                </button>
              )}
              <button
                onClick={() => setSelectedAlert(null)}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
