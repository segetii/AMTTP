'use client';

/**
 * ML Models & Detection Rules Page
 *
 * Two-tab layout:
 * Tab 1 — Model Selection: view loaded ML models, switch active ensemble, see performance metrics
 * Tab 2 — Manual Detection Rules: configure monitoring thresholds (structuring, velocity, clustering, etc.)
 *
 * Wired to:
 *  - ML Risk API (8000) /model/info, /health
 *  - Monitoring Engine (8005) /rules, /health
 *  - Policy Service (8003) /policies (for rule-action mapping)
 *
 * RBAC: R5+ (Admin / Super Admin)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  CpuChipIcon,
  ChartBarIcon,
  ShieldCheckIcon,
  Cog6ToothIcon,
  PlusIcon,
  TrashIcon,
  PencilSquareIcon,
  BoltIcon,
  AdjustmentsHorizontalIcon,
  ClockIcon,
  ArrowTrendingUpIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// API Base URLs
// ═══════════════════════════════════════════════════════════════════════════════

const ML_API = 'http://127.0.0.1:8000';
const MONITOR_API = 'http://127.0.0.1:8005';

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

interface ModelInfo {
  model_version: string;
  model_loaded: boolean;
  models_available: string[];
  optimal_threshold: number;
  has_preprocessors: boolean;
  has_metadata: boolean;
  last_updated: string;
  training_performance?: Record<string, Record<string, number>>;
  training_date?: string;
}

interface MLHealth {
  status: string;
  model_loaded: boolean;
  version: string;
  uptime_seconds: number;
}

interface DetectionRule {
  name: string;
  type: string;
  description: string;
}

interface Thresholds {
  structuring_window_hours: number;
  structuring_threshold_eth: number;
  structuring_min_transactions: number;
  structuring_max_individual_pct: number;
  roundtrip_window_hours: number;
  roundtrip_min_return_pct: number;
  roundtrip_max_hops: number;
  layering_window_hours: number;
  layering_min_hops: number;
  layering_value_decay_tolerance: number;
  velocity_window_hours: number;
  velocity_max_transactions: number;
  velocity_daily_max: number;
  clustering_threshold_eth: number;
  clustering_range_pct: number;
  [key: string]: number;
}

interface ManualRule {
  id: string;
  name: string;
  field: string;
  operator: 'gt' | 'lt' | 'eq' | 'gte' | 'lte' | 'between';
  value: number;
  valueTo?: number;
  action: 'FLAG' | 'REVIEW' | 'ESCROW' | 'BLOCK';
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  enabled: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Constants
// ═══════════════════════════════════════════════════════════════════════════════

const MODEL_DESCRIPTIONS: Record<string, { label: string; description: string; icon: string }> = {
  student_xgboost_v2: { label: 'XGBoost v2', description: 'Gradient boosted ensemble, 21 features, distilled from teacher model', icon: '🌲' },
  student_lightgbm: { label: 'LightGBM', description: 'Light gradient boosting, fast inference, leaf-wise tree growth', icon: '🍃' },
  'meta_learner(sklearn_from_cuml)': { label: 'Meta-Learner (Ensemble)', description: 'LogisticRegression stacking XGB + LGB probabilities', icon: '🧠' },
};

const FIELD_OPTIONS = [
  { value: 'value_eth', label: 'Transaction Value (ETH)' },
  { value: 'gas_price_gwei', label: 'Gas Price (Gwei)' },
  { value: 'nonce', label: 'Nonce' },
  { value: 'sender_total_transactions', label: 'Sender Total Transactions' },
  { value: 'sender_total_sent', label: 'Sender Total Sent (ETH)' },
  { value: 'sender_balance', label: 'Sender Balance (ETH)' },
  { value: 'sender_unique_receivers', label: 'Sender Unique Receivers' },
  { value: 'sender_active_duration_mins', label: 'Sender Active Duration (min)' },
];

const OPERATOR_OPTIONS = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
  { value: 'eq', label: '=' },
  { value: 'between', label: 'Between' },
];

const ACTION_COLORS: Record<string, string> = {
  FLAG: 'text-yellow-400 bg-yellow-900/40 border-yellow-700',
  REVIEW: 'text-orange-400 bg-orange-900/40 border-orange-700',
  ESCROW: 'text-blue-400 bg-blue-900/40 border-blue-700',
  BLOCK: 'text-red-400 bg-red-900/40 border-red-700',
};

const SEVERITY_COLORS: Record<string, string> = {
  LOW: 'text-green-400',
  MEDIUM: 'text-yellow-400',
  HIGH: 'text-orange-400',
  CRITICAL: 'text-red-400',
};

const MANUAL_RULES_STORAGE_KEY = 'amttp_manual_detection_rules';

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export default function MLModelsPage() {
  const [tab, setTab] = useState<'models' | 'rules'>('models');

  // ── Model state ──
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [health, setHealth] = useState<MLHealth | null>(null);
  const [activeModel, setActiveModel] = useState<string>('meta_learner(sklearn_from_cuml)');
  const [threshold, setThreshold] = useState<number>(0.595);
  const [mlLoading, setMlLoading] = useState(true);
  const [mlError, setMlError] = useState<string | null>(null);

  // ── Rules state ──
  const [detectionRules, setDetectionRules] = useState<DetectionRule[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds | null>(null);
  const [editingThresholds, setEditingThresholds] = useState<Thresholds | null>(null);
  const [manualRules, setManualRules] = useState<ManualRule[]>([]);
  const [editingManual, setEditingManual] = useState<Partial<ManualRule> | null>(null);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [savingThresholds, setSavingThresholds] = useState(false);

  const [toast, setToast] = useState<string | null>(null);
  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(null), 3000); };

  // ── Data fetching ──
  const fetchModelData = useCallback(async () => {
    setMlLoading(true);
    setMlError(null);
    try {
      const [infoRes, healthRes] = await Promise.all([
        fetch(`${ML_API}/model/info`).then(r => { if (!r.ok) throw new Error(`ML API ${r.status}`); return r.json(); }),
        fetch(`${ML_API}/health`).then(r => { if (!r.ok) throw new Error(`Health ${r.status}`); return r.json(); }),
      ]);
      setModelInfo(infoRes);
      setHealth(healthRes);
      setThreshold(infoRes.optimal_threshold ?? 0.595);
    } catch (e: any) {
      setMlError(e.message);
    } finally {
      setMlLoading(false);
    }
  }, []);

  const fetchRulesData = useCallback(async () => {
    setRulesLoading(true);
    setRulesError(null);
    try {
      const res = await fetch(`${MONITOR_API}/rules`);
      if (!res.ok) throw new Error(`Monitor API ${res.status}`);
      const data = await res.json();
      setDetectionRules(data.rules ?? []);
      setThresholds(data.thresholds ?? null);
    } catch (e: any) {
      setRulesError(e.message);
    } finally {
      setRulesLoading(false);
    }
  }, []);

  // Load manual rules from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem(MANUAL_RULES_STORAGE_KEY);
      if (stored) setManualRules(JSON.parse(stored));
    } catch { /* ignore */ }
  }, []);

  // Persist manual rules
  const persistManual = (rules: ManualRule[]) => {
    setManualRules(rules);
    localStorage.setItem(MANUAL_RULES_STORAGE_KEY, JSON.stringify(rules));
  };

  useEffect(() => { fetchModelData(); fetchRulesData(); }, [fetchModelData, fetchRulesData]);

  // ── Helpers ──
  const uptime = health ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m` : '—';

  const perfModels: Array<{ name: string; [key: string]: any }> = modelInfo?.training_performance
    ? Object.entries(modelInfo.training_performance).map(([name, metrics]) => ({ name, ...metrics }))
    : [];

  // ═════════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════════════════════════════════

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-green-900/90 border border-green-700 text-green-300 px-4 py-2 rounded-lg shadow-lg text-sm flex items-center gap-2">
          <CheckCircleIcon className="w-4 h-4" />
          {toast}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-text">Model Selection & Detection Rules</h1>
            <span className="px-2 py-1 bg-purple-900/50 text-purple-400 border border-purple-700 rounded text-xs font-medium flex items-center gap-1">
              <ShieldCheckIcon className="w-3 h-3" />
              ADMIN
            </span>
          </div>
          <p className="text-mutedText mt-1">Select active ML models and configure manual detection rules</p>
        </div>
        <button
          onClick={() => { fetchModelData(); fetchRulesData(); }}
          disabled={mlLoading || rulesLoading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-5 h-5 ${mlLoading || rulesLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 bg-surface border border-borderSubtle rounded-lg p-1">
        <button
          onClick={() => setTab('models')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
            tab === 'models' ? 'bg-blue-600 text-white' : 'text-mutedText hover:text-text hover:bg-white/5'
          }`}
        >
          <CpuChipIcon className="w-4 h-4" />
          ML Model Selection
        </button>
        <button
          onClick={() => setTab('rules')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
            tab === 'rules' ? 'bg-blue-600 text-white' : 'text-mutedText hover:text-text hover:bg-white/5'
          }`}
        >
          <AdjustmentsHorizontalIcon className="w-4 h-4" />
          Detection Rules & Thresholds
        </button>
      </div>

      {/* ═══════════ TAB 1: MODEL SELECTION ═══════════ */}
      {tab === 'models' && (
        <div className="space-y-6">
          {mlError && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 shrink-0" />
              ML Risk API unavailable: {mlError}
            </div>
          )}

          {/* Stats row */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
              <div className="flex items-center gap-2 text-mutedText text-sm">
                <CpuChipIcon className="w-4 h-4" />
                Engine Status
              </div>
              <p className={`text-lg font-bold mt-2 ${health?.model_loaded ? 'text-green-400' : 'text-red-400'}`}>
                {health?.model_loaded ? 'Loaded' : 'Not Loaded'}
              </p>
            </div>
            <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
              <div className="flex items-center gap-2 text-mutedText text-sm">
                <ChartBarIcon className="w-4 h-4" />
                Models Available
              </div>
              <p className="text-lg font-bold text-text mt-2">{modelInfo?.models_available?.length ?? 0}</p>
            </div>
            <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
              <div className="flex items-center gap-2 text-mutedText text-sm">
                <ClockIcon className="w-4 h-4" />
                Uptime
              </div>
              <p className="text-lg font-bold text-text mt-2">{uptime}</p>
            </div>
            <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
              <div className="flex items-center gap-2 text-mutedText text-sm">
                <ArrowTrendingUpIcon className="w-4 h-4 text-green-400" />
                Version
              </div>
              <p className="text-lg font-bold text-text mt-2 truncate">{modelInfo?.model_version ?? '—'}</p>
            </div>
          </div>

          {/* Active Model Selector */}
          <div className="bg-surface rounded-lg border border-borderSubtle">
            <div className="p-4 border-b border-borderSubtle">
              <h2 className="text-lg font-semibold text-text flex items-center gap-2">
                <BoltIcon className="w-5 h-5 text-yellow-400" />
                Active Detection Model
              </h2>
              <p className="text-mutedText text-sm mt-1">Select which model or ensemble is used for live transaction scoring</p>
            </div>
            <div className="p-4 space-y-3">
              {(modelInfo?.models_available ?? []).map((modelKey) => {
                const info = MODEL_DESCRIPTIONS[modelKey] ?? { label: modelKey, description: '', icon: '⚙️' };
                const isActive = activeModel === modelKey;
                return (
                  <div
                    key={modelKey}
                    onClick={() => { setActiveModel(modelKey); showToast(`Active model set to ${info.label}`); }}
                    className={`flex items-center gap-4 p-4 rounded-lg border cursor-pointer transition-all ${
                      isActive
                        ? 'border-blue-500 bg-blue-500/10 ring-1 ring-blue-500/30'
                        : 'border-borderSubtle hover:border-slate-600 hover:bg-white/[0.02]'
                    }`}
                  >
                    <span className="text-2xl">{info.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-text">{info.label}</span>
                        {isActive && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-green-900/50 text-green-400 border border-green-700">
                            ACTIVE
                          </span>
                        )}
                      </div>
                      <p className="text-mutedText text-sm truncate">{info.description}</p>
                    </div>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                      isActive ? 'border-blue-500' : 'border-slate-600'
                    }`}>
                      {isActive && <div className="w-2.5 h-2.5 rounded-full bg-blue-500" />}
                    </div>
                  </div>
                );
              })}
              {!modelInfo?.models_available?.length && !mlLoading && (
                <p className="text-mutedText text-sm text-center py-6">No models loaded. Start the ML Risk API on port 8000.</p>
              )}
            </div>
          </div>

          {/* Decision Threshold */}
          <div className="bg-surface rounded-lg border border-borderSubtle p-4">
            <h2 className="text-lg font-semibold text-text flex items-center gap-2">
              <Cog6ToothIcon className="w-5 h-5 text-slate-400" />
              Decision Threshold
            </h2>
            <p className="text-mutedText text-sm mt-1 mb-4">
              Fraud probability above this threshold triggers a positive detection. Lower = more sensitive (more false positives), higher = more specific.
            </p>
            <div className="flex items-center gap-4">
              <input
                type="range"
                min={0.1}
                max={0.95}
                step={0.005}
                value={threshold}
                onChange={(e) => setThreshold(parseFloat(e.target.value))}
                className="flex-1 accent-blue-500 h-2"
              />
              <div className="bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-text font-mono text-sm min-w-[80px] text-center">
                {threshold.toFixed(3)}
              </div>
            </div>
            <div className="flex justify-between text-xs text-mutedText mt-1">
              <span>Sensitive (0.1)</span>
              <span>Balanced</span>
              <span>Specific (0.95)</span>
            </div>
          </div>

          {/* Training Performance */}
          {perfModels.length > 0 && (
            <div className="bg-surface rounded-lg border border-borderSubtle">
              <div className="p-4 border-b border-borderSubtle">
                <h2 className="text-lg font-semibold text-text">Training Performance</h2>
                <p className="text-mutedText text-sm mt-1">Metrics from the latest training run{modelInfo?.training_date ? ` (${modelInfo.training_date})` : ''}</p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-mutedText text-xs uppercase border-b border-borderSubtle">
                      <th className="text-left p-3">Model</th>
                      <th className="text-right p-3">ROC-AUC</th>
                      <th className="text-right p-3">F1</th>
                      <th className="text-right p-3">Precision</th>
                      <th className="text-right p-3">Recall</th>
                      <th className="text-right p-3">Accuracy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {perfModels.map((m) => (
                      <tr key={m.name} className="border-b border-borderSubtle last:border-0 hover:bg-white/[0.02]">
                        <td className="p-3 text-text font-medium">{m.name}</td>
                        <td className="p-3 text-right font-mono text-green-400">{m.roc_auc != null ? (m.roc_auc * 100).toFixed(1) + '%' : '—'}</td>
                        <td className="p-3 text-right font-mono">{m.f1 != null ? (m.f1 * 100).toFixed(1) + '%' : '—'}</td>
                        <td className="p-3 text-right font-mono">{m.precision != null ? (m.precision * 100).toFixed(1) + '%' : '—'}</td>
                        <td className="p-3 text-right font-mono">{m.recall != null ? (m.recall * 100).toFixed(1) + '%' : '—'}</td>
                        <td className="p-3 text-right font-mono">{m.accuracy != null ? (m.accuracy * 100).toFixed(1) + '%' : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══════════ TAB 2: DETECTION RULES & THRESHOLDS ═══════════ */}
      {tab === 'rules' && (
        <div className="space-y-6">
          {rulesError && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm flex items-center gap-2">
              <ExclamationTriangleIcon className="w-4 h-4 shrink-0" />
              Monitoring Engine unavailable: {rulesError}
            </div>
          )}

          {/* Active Detection Rules */}
          <div className="bg-surface rounded-lg border border-borderSubtle">
            <div className="p-4 border-b border-borderSubtle">
              <h2 className="text-lg font-semibold text-text flex items-center gap-2">
                <ShieldCheckIcon className="w-5 h-5 text-blue-400" />
                Active Detection Rules (Engine)
              </h2>
              <p className="text-mutedText text-sm mt-1">Built-in AML pattern detection rules from the monitoring engine</p>
            </div>
            <div className="divide-y divide-borderSubtle">
              {detectionRules.map((rule) => (
                <div key={rule.name} className="p-4 flex items-start gap-3">
                  <CheckCircleIcon className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
                  <div>
                    <span className="text-text font-medium">{rule.type.replace(/_/g, ' ')}</span>
                    <p className="text-mutedText text-xs mt-0.5 line-clamp-2">{rule.description.split('\n').find(l => l.trim()) || rule.description}</p>
                  </div>
                </div>
              ))}
              {!detectionRules.length && !rulesLoading && (
                <p className="text-mutedText text-sm text-center py-6">No detection rules loaded. Start the Monitoring Engine on port 8005.</p>
              )}
            </div>
          </div>

          {/* Threshold Configuration */}
          {thresholds && (
            <div className="bg-surface rounded-lg border border-borderSubtle">
              <div className="p-4 border-b border-borderSubtle flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-text flex items-center gap-2">
                    <AdjustmentsHorizontalIcon className="w-5 h-5 text-orange-400" />
                    Detection Thresholds
                  </h2>
                  <p className="text-mutedText text-sm mt-1">Configure sensitivity thresholds for pattern detection</p>
                </div>
                {!editingThresholds ? (
                  <button
                    onClick={() => setEditingThresholds({ ...thresholds })}
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-sm flex items-center gap-1 transition-colors"
                  >
                    <PencilSquareIcon className="w-4 h-4" />
                    Edit
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setEditingThresholds(null)}
                      className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-sm transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        setThresholds(editingThresholds);
                        setEditingThresholds(null);
                        showToast('Thresholds updated');
                      }}
                      disabled={savingThresholds}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm flex items-center gap-1 transition-colors"
                    >
                      <CheckCircleIcon className="w-4 h-4" />
                      Save
                    </button>
                  </div>
                )}
              </div>

              <div className="p-4">
                {/* Group thresholds by category */}
                {[
                  {
                    title: 'Structuring Detection',
                    desc: 'Breaking up transactions to avoid reporting thresholds',
                    keys: ['structuring_window_hours', 'structuring_threshold_eth', 'structuring_min_transactions', 'structuring_max_individual_pct'],
                  },
                  {
                    title: 'Round-Trip Detection',
                    desc: 'Money returning to origin through intermediaries',
                    keys: ['roundtrip_window_hours', 'roundtrip_min_return_pct', 'roundtrip_max_hops'],
                  },
                  {
                    title: 'Layering Detection',
                    desc: 'Complex transaction chains to obscure origin',
                    keys: ['layering_window_hours', 'layering_min_hops', 'layering_value_decay_tolerance'],
                  },
                  {
                    title: 'Velocity Controls',
                    desc: 'Transaction frequency limits',
                    keys: ['velocity_window_hours', 'velocity_max_transactions', 'velocity_daily_max'],
                  },
                  {
                    title: 'Value Clustering',
                    desc: 'Transactions clustered near reporting thresholds',
                    keys: ['clustering_threshold_eth', 'clustering_range_pct'],
                  },
                ].map((group) => (
                  <div key={group.title} className="mb-6 last:mb-0">
                    <h3 className="text-sm font-semibold text-text mb-1">{group.title}</h3>
                    <p className="text-xs text-mutedText mb-3">{group.desc}</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {group.keys.map((key) => {
                        const label = key
                          .replace(/^(structuring_|roundtrip_|layering_|velocity_|clustering_)/, '')
                          .replace(/_/g, ' ')
                          .replace(/\b\w/g, c => c.toUpperCase());
                        const src = editingThresholds ?? thresholds;
                        const val = src[key];
                        return (
                          <div key={key} className="flex items-center gap-2">
                            <label className="text-mutedText text-xs min-w-[140px]">{label}</label>
                            {editingThresholds ? (
                              <input
                                type="number"
                                step={key.includes('pct') || key.includes('tolerance') ? 0.05 : 1}
                                value={editingThresholds[key]}
                                onChange={(e) => setEditingThresholds({ ...editingThresholds, [key]: parseFloat(e.target.value) || 0 })}
                                className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-text font-mono focus:outline-none focus:border-blue-500"
                              />
                            ) : (
                              <span className="text-text font-mono text-sm">{val}</span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Manual Rules */}
          <div className="bg-surface rounded-lg border border-borderSubtle">
            <div className="p-4 border-b border-borderSubtle flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-text flex items-center gap-2">
                  <PencilSquareIcon className="w-5 h-5 text-emerald-400" />
                  Manual Detection Rules
                </h2>
                <p className="text-mutedText text-sm mt-1">Custom rules for additional heuristic-based detection</p>
              </div>
              <button
                onClick={() => setEditingManual({
                  field: 'value_eth',
                  operator: 'gt',
                  value: 0,
                  action: 'FLAG',
                  severity: 'MEDIUM',
                  enabled: true,
                  name: '',
                })}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-sm flex items-center gap-1 transition-colors"
              >
                <PlusIcon className="w-4 h-4" />
                Add Rule
              </button>
            </div>

            {/* Manual rule form */}
            {editingManual && (
              <div className="p-4 border-b border-borderSubtle bg-slate-900/50">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-3">
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Rule Name</label>
                    <input
                      type="text"
                      value={editingManual.name ?? ''}
                      onChange={(e) => setEditingManual({ ...editingManual, name: e.target.value })}
                      placeholder="e.g. Large transfer alert"
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Field</label>
                    <select
                      value={editingManual.field ?? 'value_eth'}
                      onChange={(e) => setEditingManual({ ...editingManual, field: e.target.value })}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text focus:outline-none focus:border-blue-500"
                    >
                      {FIELD_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Operator</label>
                    <select
                      value={editingManual.operator ?? 'gt'}
                      onChange={(e) => setEditingManual({ ...editingManual, operator: e.target.value as ManualRule['operator'] })}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text focus:outline-none focus:border-blue-500"
                    >
                      {OPERATOR_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Value</label>
                    <input
                      type="number"
                      value={editingManual.value ?? 0}
                      onChange={(e) => setEditingManual({ ...editingManual, value: parseFloat(e.target.value) || 0 })}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text font-mono focus:outline-none focus:border-blue-500"
                    />
                  </div>
                  {editingManual.operator === 'between' && (
                    <div>
                      <label className="text-mutedText text-xs block mb-1">Value To</label>
                      <input
                        type="number"
                        value={editingManual.valueTo ?? 0}
                        onChange={(e) => setEditingManual({ ...editingManual, valueTo: parseFloat(e.target.value) || 0 })}
                        className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text font-mono focus:outline-none focus:border-blue-500"
                      />
                    </div>
                  )}
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Action</label>
                    <select
                      value={editingManual.action ?? 'FLAG'}
                      onChange={(e) => setEditingManual({ ...editingManual, action: e.target.value as ManualRule['action'] })}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text focus:outline-none focus:border-blue-500"
                    >
                      <option value="FLAG">Flag</option>
                      <option value="REVIEW">Review</option>
                      <option value="ESCROW">Escrow</option>
                      <option value="BLOCK">Block</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-mutedText text-xs block mb-1">Severity</label>
                    <select
                      value={editingManual.severity ?? 'MEDIUM'}
                      onChange={(e) => setEditingManual({ ...editingManual, severity: e.target.value as ManualRule['severity'] })}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-2.5 py-1.5 text-sm text-text focus:outline-none focus:border-blue-500"
                    >
                      <option value="LOW">Low</option>
                      <option value="MEDIUM">Medium</option>
                      <option value="HIGH">High</option>
                      <option value="CRITICAL">Critical</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => setEditingManual(null)}
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-sm transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => {
                      if (!editingManual.name?.trim()) { showToast('Rule name is required'); return; }
                      const id = editingManual.id ?? `rule-${Date.now()}`;
                      const rule: ManualRule = {
                        id,
                        name: editingManual.name!.trim(),
                        field: editingManual.field ?? 'value_eth',
                        operator: editingManual.operator ?? 'gt',
                        value: editingManual.value ?? 0,
                        valueTo: editingManual.valueTo,
                        action: editingManual.action ?? 'FLAG',
                        severity: editingManual.severity ?? 'MEDIUM',
                        enabled: editingManual.enabled ?? true,
                      };
                      const exists = manualRules.findIndex(r => r.id === id);
                      const updated = exists >= 0
                        ? manualRules.map(r => r.id === id ? rule : r)
                        : [...manualRules, rule];
                      persistManual(updated);
                      setEditingManual(null);
                      showToast(exists >= 0 ? 'Rule updated' : 'Rule created');
                    }}
                    className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 rounded text-sm flex items-center gap-1 transition-colors"
                  >
                    <CheckCircleIcon className="w-4 h-4" />
                    {editingManual.id ? 'Update' : 'Create'} Rule
                  </button>
                </div>
              </div>
            )}

            {/* Manual rules list */}
            <div className="divide-y divide-borderSubtle">
              {manualRules.length === 0 && !editingManual && (
                <p className="text-mutedText text-sm text-center py-8">No manual rules configured. Click "Add Rule" to create one.</p>
              )}
              {manualRules.map((rule) => {
                const fieldLabel = FIELD_OPTIONS.find(f => f.value === rule.field)?.label ?? rule.field;
                const opLabel = OPERATOR_OPTIONS.find(o => o.value === rule.operator)?.label ?? rule.operator;
                return (
                  <div key={rule.id} className={`p-4 flex items-center gap-4 ${rule.enabled ? '' : 'opacity-50'}`}>
                    <button
                      onClick={() => {
                        const updated = manualRules.map(r => r.id === rule.id ? { ...r, enabled: !r.enabled } : r);
                        persistManual(updated);
                        showToast(`Rule ${rule.enabled ? 'disabled' : 'enabled'}`);
                      }}
                      className={`w-10 h-5 rounded-full relative transition-colors ${
                        rule.enabled ? 'bg-green-600' : 'bg-slate-700'
                      }`}
                    >
                      <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                        rule.enabled ? 'left-5' : 'left-0.5'
                      }`} />
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-text font-medium text-sm">{rule.name}</span>
                        <span className={`text-xs ${SEVERITY_COLORS[rule.severity]}`}>{rule.severity}</span>
                      </div>
                      <p className="text-mutedText text-xs mt-0.5">
                        If <span className="text-text">{fieldLabel}</span>{' '}
                        <span className="text-blue-400">{opLabel}</span>{' '}
                        <span className="text-text font-mono">{rule.value}</span>
                        {rule.operator === 'between' && <> and <span className="text-text font-mono">{rule.valueTo}</span></>}
                        {' → '}
                        <span className={`px-1.5 py-0.5 rounded text-xs border ${ACTION_COLORS[rule.action]}`}>{rule.action}</span>
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <button
                        onClick={() => setEditingManual({ ...rule })}
                        className="p-1.5 hover:bg-slate-700 rounded transition-colors"
                        title="Edit"
                      >
                        <PencilSquareIcon className="w-4 h-4 text-mutedText" />
                      </button>
                      <button
                        onClick={() => {
                          persistManual(manualRules.filter(r => r.id !== rule.id));
                          showToast('Rule deleted');
                        }}
                        className="p-1.5 hover:bg-red-900/50 rounded transition-colors"
                        title="Delete"
                      >
                        <TrashIcon className="w-4 h-4 text-red-400" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
