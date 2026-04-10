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
import Link from 'next/link';
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
import ExplainabilityModal, { getRiskLevel, getRiskColor as getSharedRiskColor } from '@/components/shared/ExplainabilityModal';

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
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Active Alerts</span>
          <span className="text-2xl">🔔</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-text">{activeCount}</span>
        </div>
      </div>
      
      <div className="bg-surface rounded-lg p-4 border border-red-900/50">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Critical</span>
          <span className="text-2xl">🚨</span>
        </div>
        <div className="mt-2">
          <span className={`text-3xl font-bold ${criticalCount > 0 ? 'text-red-400' : 'text-text'}`}>
            {criticalCount}
          </span>
        </div>
      </div>
      
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Acknowledged</span>
          <span className="text-2xl">✋</span>
        </div>
        <div className="mt-2">
          <span className="text-3xl font-bold text-yellow-400">{acknowledgedCount}</span>
        </div>
      </div>
      
      <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
        <div className="flex items-center justify-between">
          <span className="text-mutedText text-sm">Resolved Today</span>
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
          className={`bg-surface rounded-lg p-4 border transition-all ${
            rule.enabled ? 'border-borderSubtle' : 'border-slate-800 opacity-60'
          }`}
        >
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h4 className="font-medium text-text">{rule.name}</h4>
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
                <p className="text-sm text-mutedText mt-1">{rule.description}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-xs text-mutedText">
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
                className="p-2 text-mutedText hover:text-text"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} 
                        d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              
              <button
                onClick={() => onDelete(rule.id)}
                className="p-2 text-mutedText hover:text-red-400"
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
        <div className="text-center py-12 text-mutedText">
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
  const [explainAlert, setExplainAlert] = useState<Alert | null>(null);
  
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
    <div className="space-y-6">
      {/* Toast Notifications */}
      <AlertToastContainer
        toasts={toasts}
        onDismiss={dismissToast}
        onAcknowledge={handleAcknowledge}
        onView={setSelectedAlert}
      />
      
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Link href="/war-room" className="text-mutedText hover:text-text text-sm">
            ← War Room
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-text">Alert Center</h1>
        <p className="text-mutedText">Monitor and manage system alerts in real-time</p>
      </div>
      
      {/* Stats */}
      <AlertStats alerts={alerts} />
      
      {/* Tabs */}
      <div className="flex gap-4 mb-6 border-b border-slate-800">
        {[
          { id: 'alerts' as TabType, label: 'Alerts' },
          { id: 'rules' as TabType, label: 'Rules' },
          { id: 'channels' as TabType, label: 'Channels' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium transition-colors border-b-2 -mb-px capitalize ${
              activeTab === tab.id
                ? 'text-cyan-400 border-cyan-400'
                : 'text-mutedText border-transparent hover:text-text'
            }`}
          >
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
            onSelect={setSelectedAlert}
            selectedAlertId={selectedAlert?.id}
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
                className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-text rounded-lg text-sm"
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
      
      {/* Alert Detail Panel */}
      {selectedAlert && (
        <AlertDetailModal
          alert={selectedAlert}
          onClose={() => setSelectedAlert(null)}
          onAcknowledge={() => { handleAcknowledge(selectedAlert.id); setSelectedAlert(null); }}
          onResolve={() => { handleResolve(selectedAlert.id); setSelectedAlert(null); }}
          onEscalate={() => { handleEscalate(selectedAlert.id); setSelectedAlert(null); }}
          onExplain={() => { setExplainAlert(selectedAlert); setSelectedAlert(null); }}
        />
      )}

      {/* Explainability Modal */}
      {explainAlert && (
        <ExplainabilityModal
          item={{
            id: explainAlert.id,
            address: (explainAlert.metadata?.address as string) || (explainAlert.metadata?.from as string) || '',
            riskScore: (explainAlert.metadata?.riskScore as number) || 0,
            riskLevel: (explainAlert.metadata?.riskLevel as string) || '',
            reason: explainAlert.message,
          }}
          onClose={() => setExplainAlert(null)}
          onInvestigate={() => {
            const addr = (explainAlert.metadata?.address as string) || (explainAlert.metadata?.from as string) || '';
            setExplainAlert(null);
            window.open(`/war-room/detection/graph?address=${addr}`, '_blank');
          }}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ALERT DETAIL MODAL
// ═══════════════════════════════════════════════════════════════════════════════

function AlertDetailModal({
  alert,
  onClose,
  onAcknowledge,
  onResolve,
  onEscalate,
  onExplain,
}: {
  alert: Alert;
  onClose: () => void;
  onAcknowledge: () => void;
  onResolve: () => void;
  onEscalate: () => void;
  onExplain: () => void;
}) {
  const m = alert.metadata || {};
  const riskScore = (m.riskScore as number) ?? 0;
  const riskLevel = (m.riskLevel as string) || getRiskLevel(riskScore);
  const from = (m.from as string) || '';
  const to = (m.to as string) || '';
  const address = (m.address as string) || from || '';
  const value = m.value != null ? String(m.value) : '';
  const txHash = alert.resourceId || '';

  const rc = getSharedRiskColor(riskLevel);
  const riskColor = { bar: rc.bg, text: rc.text, ring: rc.ring, bg: rc.bgSoft };

  const priorityDot: Record<string, string> = {
    CRITICAL: 'bg-red-500',
    HIGH:     'bg-orange-400',
    MEDIUM:   'bg-amber-400',
    LOW:      'bg-sky-400',
  };

  const MonoField = ({ label, val, full }: { label: string; val: string; full?: boolean }) => (
    <div className={full ? '' : ''}>
      <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{label}</div>
      <div className="font-mono text-[13px] text-slate-300 bg-slate-800/60 rounded-lg px-3 py-2 truncate select-all" title={val}>{val}</div>
    </div>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" />

      {/* Panel */}
      <div
        className="relative w-full max-w-xl mx-4 bg-[#0f1219] rounded-2xl border border-slate-800
                   shadow-[0_24px_80px_-12px_rgba(0,0,0,0.6)] max-h-[88vh] flex flex-col
                   animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ─── Header ─── */}
        <div className="flex items-start gap-4 px-6 pt-6 pb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${priorityDot[alert.priority] || 'bg-slate-500'}`} />
              <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{alert.priority} • {alert.category}</span>
            </div>
            <h2 className="text-lg font-semibold text-white leading-snug">{alert.title}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 -mt-1 -mr-1 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ─── Scrollable body ─── */}
        <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-5 scrollbar-thin">

          {/* Message */}
          <p className="text-[13px] text-slate-400 leading-relaxed">{alert.message}</p>

          {/* Risk score — compact inline bar */}
          {riskScore > 0 && (
            <div className={`flex items-center gap-4 px-4 py-3 rounded-xl ${riskColor.bg} ring-1 ${riskColor.ring}`}>
              <div className="flex-1">
                <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1.5">Risk Score</div>
                <div className="w-full h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${riskColor.bar} transition-all duration-500`} style={{ width: `${Math.min(riskScore, 100)}%` }} />
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <span className={`text-2xl font-bold tabular-nums ${riskColor.text}`}>{riskScore.toFixed(0)}</span>
                {riskLevel && <div className={`text-[11px] font-medium ${riskColor.text}`}>{riskLevel}</div>}
              </div>
            </div>
          )}

          {/* Transaction details — clean grid */}
          {(txHash || from || to || value) && (
            <div className="space-y-3">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">Transaction</div>
              {txHash && <MonoField label="Hash" val={txHash} full />}
              <div className="grid grid-cols-2 gap-3">
                {from && <MonoField label="From" val={from} />}
                {to && <MonoField label="To" val={to} />}
              </div>
              {(value || (address && address !== from)) && (
                <div className="grid grid-cols-2 gap-3">
                  {value && (
                    <div>
                      <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Amount</div>
                      <div className="text-lg font-semibold text-white tabular-nums">{value} <span className="text-sm font-normal text-slate-500">ETH</span></div>
                    </div>
                  )}
                  {address && address !== from && <MonoField label="Flagged Address" val={address} />}
                </div>
              )}
            </div>
          )}

          {/* Tags — minimal pills */}
          {alert.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {alert.tags.map((tag) => (
                <span key={tag} className="px-2.5 py-0.5 rounded-full bg-slate-800 text-[11px] text-slate-500 ring-1 ring-slate-700/60">{tag}</span>
              ))}
            </div>
          )}

          {/* Timeline — thin & compact */}
          <div className="pt-1">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-3">Activity</div>
            <div className="space-y-0 relative ml-1.5">
              <div className="absolute left-[3px] top-1 bottom-1 w-px bg-slate-800" />
              {[
                { time: alert.createdAt, label: 'Created', color: 'bg-slate-500' },
                ...(alert.acknowledgedAt ? [{ time: alert.acknowledgedAt, label: `Acknowledged${alert.acknowledgedBy ? ` by ${alert.acknowledgedBy}` : ''}`, color: 'bg-amber-400' }] : []),
                ...(alert.resolvedAt ? [{ time: alert.resolvedAt, label: `Resolved${alert.resolvedBy ? ` by ${alert.resolvedBy}` : ''}`, color: 'bg-emerald-400' }] : []),
              ].map((ev, i) => (
                <div key={i} className="flex items-center gap-3 py-1.5 relative">
                  <div className={`w-[7px] h-[7px] rounded-full ${ev.color} flex-shrink-0 z-10 ring-2 ring-[#0f1219]`} />
                  <span className="text-[12px] text-slate-400">{ev.label}</span>
                  <span className="text-[11px] text-slate-600 tabular-nums ml-auto">{new Date(ev.time).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ─── Actions bar ─── */}
        <div className="px-6 py-4 border-t border-slate-800/80 flex items-center gap-2">
          {alert.status === AlertStatus.NEW && (
            <>
              <button onClick={onAcknowledge}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20
                           hover:bg-amber-500/20 transition-colors">
                Acknowledge
              </button>
              <button onClick={onEscalate}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-red-500/10 text-red-400 ring-1 ring-red-500/20
                           hover:bg-red-500/20 transition-colors">
                Escalate
              </button>
              <button onClick={onResolve}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20
                           hover:bg-emerald-500/20 transition-colors">
                Resolve
              </button>
            </>
          )}
          {alert.status === AlertStatus.ACKNOWLEDGED && (
            <>
              <button onClick={onEscalate}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-red-500/10 text-red-400 ring-1 ring-red-500/20
                           hover:bg-red-500/20 transition-colors">
                Escalate
              </button>
              <button onClick={onResolve}
                className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                           bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20
                           hover:bg-emerald-500/20 transition-colors">
                Resolve
              </button>
            </>
          )}
          {alert.status === AlertStatus.ESCALATED && (
            <button onClick={onResolve}
              className="flex-1 px-3 py-2 rounded-lg text-[13px] font-medium
                         bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20
                         hover:bg-emerald-500/20 transition-colors">
              Resolve
            </button>
          )}
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg text-[13px] text-slate-500 hover:text-slate-300
                       hover:bg-slate-800 transition-colors">
            Close
          </button>
          <button onClick={onExplain}
            className="px-4 py-2 rounded-lg text-[13px] font-medium
                       bg-indigo-500/10 text-indigo-400 ring-1 ring-indigo-500/20
                       hover:bg-indigo-500/20 transition-colors flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Explainability
          </button>
        </div>
      </div>
    </div>
  );
}
