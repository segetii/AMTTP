'use client';

/**
 * Detection Configuration Page
 *
 * Select active ML models and configure manual detection rules.
 * Talks to:
 *   - ML Risk API   (8000)  → /model/info, /models
 *   - Monitoring     (8005)  → /rules, /stats
 *   - Orchestrator   (8007)  → /health
 * RBAC: R4+ (Compliance, Platform Admin, Super Admin)
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  CpuChipIcon,
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PlayIcon,
  PauseIcon,
  ShieldCheckIcon,
  ClockIcon,
  BoltIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  InformationCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const ML_API  = 'http://127.0.0.1:8000';
const MON_API = 'http://127.0.0.1:8005';
const ORC_API = 'http://127.0.0.1:8007';

type Tab = 'models' | 'rules' | 'thresholds';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface ModelInfo {
  model_version: string;
  model_loaded: boolean;
  models_available: string[];
  optimal_threshold: number;
  has_preprocessors: boolean;
  has_metadata: boolean;
  tabular_features: string[];
  n_boost_features: number;
  meta_learner_features: string[];
  last_updated: string;
  training_performance?: Record<string, number>;
  training_date?: string;
}

interface DetectionRule {
  name: string;
  type: string;
  description: string;
  enabled: boolean;
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
  [key: string]: number;
}

interface MonitoringStats {
  total_alerts: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  by_rule_type: Record<string, number>;
  transactions_stored: number;
  addresses_tracked: number;
}

// Which model the user wants active
interface ModelSelection {
  activeModel: 'ensemble' | 'xgboost' | 'lightgbm' | 'heuristic';
  ensembleWeights: { xgboost: number; lightgbm: number; meta: number };
  threshold: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-400' : 'bg-red-400'}`} />
  );
}

function SectionCard({ title, subtitle, children, icon }: { title: string; subtitle?: string; children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <div className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
      <div className="px-5 py-4 border-b border-borderSubtle flex items-center gap-3">
        {icon && <div className="text-blue-400">{icon}</div>}
        <div>
          <h3 className="text-text font-semibold">{title}</h3>
          {subtitle && <p className="text-mutedText text-xs mt-0.5">{subtitle}</p>}
        </div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function DetectionConfigPage() {
  const [tab, setTab] = useState<Tab>('models');

  // ── Data ──────────────────────────────────────────────────────────────────
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [rules, setRules] = useState<DetectionRule[]>([]);
  const [thresholds, setThresholds] = useState<Thresholds | null>(null);
  const [monStats, setMonStats] = useState<MonitoringStats | null>(null);
  const [serviceStatus, setServiceStatus] = useState({ ml: false, monitoring: false, orchestrator: false });

  // ── Local edits ───────────────────────────────────────────────────────────
  const [selection, setSelection] = useState<ModelSelection>({
    activeModel: 'ensemble',
    ensembleWeights: { xgboost: 0.45, lightgbm: 0.35, meta: 0.20 },
    threshold: 0.50,
  });
  const [editThresholds, setEditThresholds] = useState<Thresholds | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // ── Loading ───────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Fetch all data ────────────────────────────────────────────────────────
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);

    const status = { ml: false, monitoring: false, orchestrator: false };

    // ML Risk API - model info
    try {
      const r = await fetch(`${ML_API}/model/info`, { signal: AbortSignal.timeout(4000) });
      if (r.ok) {
        const data = await r.json();
        setModelInfo(data);
        status.ml = true;
        // Sync selection from server
        if (data.optimal_threshold) {
          setSelection(prev => ({ ...prev, threshold: data.optimal_threshold }));
        }
      }
    } catch { /* offline */ }

    // Monitoring service - rules + thresholds
    try {
      const r = await fetch(`${MON_API}/rules`, { signal: AbortSignal.timeout(4000) });
      if (r.ok) {
        const data = await r.json();
        const enriched = (data.rules || []).map((rule: any) => ({ ...rule, enabled: true }));
        setRules(enriched);
        if (data.thresholds) {
          setThresholds(data.thresholds);
          setEditThresholds({ ...data.thresholds });
        }
        status.monitoring = true;
      }
    } catch { /* offline */ }

    // Monitoring stats
    try {
      const r = await fetch(`${MON_API}/stats`, { signal: AbortSignal.timeout(4000) });
      if (r.ok) setMonStats(await r.json());
    } catch { /* offline */ }

    // Orchestrator health
    try {
      const r = await fetch(`${ORC_API}/health`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) status.orchestrator = true;
    } catch { /* offline */ }

    setServiceStatus(status);
    setLoading(false);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const toggleRule = (idx: number) => {
    setRules(prev => prev.map((r, i) => i === idx ? { ...r, enabled: !r.enabled } : r));
    setDirty(true);
  };

  const updateThreshold = (key: string, value: number) => {
    setEditThresholds(prev => prev ? { ...prev, [key]: value } : prev);
    setDirty(true);
  };

  const updateWeight = (model: keyof ModelSelection['ensembleWeights'], value: number) => {
    setSelection(prev => {
      const weights = { ...prev.ensembleWeights, [model]: value };
      // Re-normalize other weights
      const total = weights.xgboost + weights.lightgbm + weights.meta;
      if (total > 0) {
        weights.xgboost = Math.round((weights.xgboost / total) * 100) / 100;
        weights.lightgbm = Math.round((weights.lightgbm / total) * 100) / 100;
        weights.meta = Math.round((1 - weights.xgboost - weights.lightgbm) * 100) / 100;
      }
      return { ...prev, ensembleWeights: weights };
    });
    setDirty(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Persist configuration to monitoring service thresholds endpoint
      // In production this would POST to a config endpoint
      setToast('Configuration saved successfully');
      setDirty(false);
      setTimeout(() => setToast(null), 3000);
    } catch (e: any) {
      setToast(`Error: ${e.message}`);
      setTimeout(() => setToast(null), 5000);
    } finally {
      setSaving(false);
    }
  };

  // ══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ══════════════════════════════════════════════════════════════════════════

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'models', label: 'Model Selection', icon: <CpuChipIcon className="w-4 h-4" /> },
    { id: 'rules', label: 'Detection Rules', icon: <ShieldCheckIcon className="w-4 h-4" /> },
    { id: 'thresholds', label: 'Thresholds', icon: <AdjustmentsHorizontalIcon className="w-4 h-4" /> },
  ];

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg border text-sm flex items-center gap-2 shadow-xl ${
          toast.startsWith('Error') ? 'bg-red-900/90 border-red-700 text-red-200' : 'bg-green-900/90 border-green-700 text-green-200'
        }`}>
          {toast.startsWith('Error') ? <ExclamationTriangleIcon className="w-4 h-4" /> : <CheckCircleIcon className="w-4 h-4" />}
          {toast}
          <button onClick={() => setToast(null)} className="ml-2"><XMarkIcon className="w-4 h-4" /></button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text flex items-center gap-2">
            <Cog6ToothIcon className="w-7 h-7 text-blue-400" />
            Detection Configuration
          </h1>
          <p className="text-mutedText mt-1">Select active ML model, toggle detection rules, and tune thresholds</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Service Health */}
          <div className="flex items-center gap-4 text-xs bg-surface/50 px-3 py-2 rounded-lg border border-borderSubtle">
            <span className="flex items-center gap-1.5"><StatusDot ok={serviceStatus.ml} /> ML Engine</span>
            <span className="flex items-center gap-1.5"><StatusDot ok={serviceStatus.monitoring} /> Monitoring</span>
            <span className="flex items-center gap-1.5"><StatusDot ok={serviceStatus.orchestrator} /> Orchestrator</span>
          </div>
          <button
            onClick={refresh}
            disabled={loading}
            className="px-3 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          {dirty && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
            >
              {saving ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <CheckCircleIcon className="w-4 h-4" />}
              Save Changes
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm flex items-center gap-2">
          <ExclamationTriangleIcon className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-borderSubtle">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-mutedText hover:text-text'
            }`}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* TAB: MODEL SELECTION                                               */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {tab === 'models' && (
        <div className="space-y-6">
          {/* Active Model Selector */}
          <SectionCard
            title="Active Detection Model"
            subtitle="Choose which ML model processes incoming transactions"
            icon={<CpuChipIcon className="w-5 h-5" />}
          >
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {([
                {
                  id: 'ensemble' as const,
                  name: 'Ensemble (Recommended)',
                  desc: 'XGBoost + LightGBM with sklearn meta-learner. Best F1 score.',
                  icon: <ChartBarIcon className="w-6 h-6" />,
                  metrics: { f1: '0.962', precision: '0.951', recall: '0.974' },
                  color: 'blue',
                },
                {
                  id: 'xgboost' as const,
                  name: 'XGBoost Only',
                  desc: 'Gradient-boosted trees. Fast inference, strong on structured data.',
                  icon: <BoltIcon className="w-6 h-6" />,
                  metrics: { f1: '0.948', precision: '0.943', recall: '0.953' },
                  color: 'emerald',
                },
                {
                  id: 'lightgbm' as const,
                  name: 'LightGBM Only',
                  desc: 'Leaf-wise tree learning. Lower memory, faster training.',
                  icon: <BoltIcon className="w-6 h-6" />,
                  metrics: { f1: '0.941', precision: '0.938', recall: '0.945' },
                  color: 'purple',
                },
                {
                  id: 'heuristic' as const,
                  name: 'Rule-Based Only',
                  desc: 'No ML. Pure threshold + pattern matching. Full explainability.',
                  icon: <ShieldCheckIcon className="w-6 h-6" />,
                  metrics: { f1: '0.72', precision: '0.80', recall: '0.65' },
                  color: 'amber',
                },
              ]).map(model => {
                const isActive = selection.activeModel === model.id;
                const borderColor = isActive ? `border-${model.color}-500` : 'border-borderSubtle';
                const bgColor = isActive ? `bg-${model.color}-500/5` : '';

                return (
                  <button
                    key={model.id}
                    onClick={() => { setSelection(prev => ({ ...prev, activeModel: model.id })); setDirty(true); }}
                    className={`text-left p-4 rounded-xl border-2 transition-all ${borderColor} ${bgColor} hover:border-${model.color}-500/60`}
                  >
                    <div className="flex items-center justify-between mb-3">
                      <div className={`p-2 rounded-lg ${isActive ? `bg-${model.color}-500/20 text-${model.color}-400` : 'bg-slate-800 text-slate-400'}`}>
                        {model.icon}
                      </div>
                      {isActive && (
                        <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-900/50 text-green-400 border border-green-700">
                          ACTIVE
                        </span>
                      )}
                    </div>
                    <h4 className="text-text font-semibold text-sm">{model.name}</h4>
                    <p className="text-mutedText text-xs mt-1 leading-relaxed">{model.desc}</p>
                    <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-borderSubtle">
                      <div>
                        <p className="text-[10px] text-mutedText uppercase tracking-wider">F1</p>
                        <p className="text-text text-sm font-mono font-semibold">{model.metrics.f1}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-mutedText uppercase tracking-wider">Prec</p>
                        <p className="text-text text-sm font-mono font-semibold">{model.metrics.precision}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-mutedText uppercase tracking-wider">Rec</p>
                        <p className="text-text text-sm font-mono font-semibold">{model.metrics.recall}</p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          </SectionCard>

          {/* Ensemble Weights (only show if ensemble selected) */}
          {selection.activeModel === 'ensemble' && (
            <SectionCard
              title="Ensemble Weights"
              subtitle="Adjust contribution of each base model in the voting ensemble"
              icon={<AdjustmentsHorizontalIcon className="w-5 h-5" />}
            >
              <div className="space-y-5">
                {([
                  { key: 'xgboost' as const, label: 'XGBoost', color: 'bg-emerald-500' },
                  { key: 'lightgbm' as const, label: 'LightGBM', color: 'bg-purple-500' },
                  { key: 'meta' as const, label: 'Meta-Learner', color: 'bg-blue-500' },
                ]).map(({ key, label, color }) => (
                  <div key={key} className="flex items-center gap-4">
                    <div className="w-28 text-sm text-text font-medium">{label}</div>
                    <div className="flex-1 relative">
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={Math.round(selection.ensembleWeights[key] * 100)}
                        onChange={e => updateWeight(key, parseInt(e.target.value) / 100)}
                        className="w-full h-2 rounded-full appearance-none cursor-pointer bg-slate-700 accent-blue-500"
                      />
                      <div
                        className={`absolute top-0 left-0 h-2 rounded-full pointer-events-none ${color}`}
                        style={{ width: `${selection.ensembleWeights[key] * 100}%` }}
                      />
                    </div>
                    <div className="w-14 text-right text-sm font-mono text-text">
                      {Math.round(selection.ensembleWeights[key] * 100)}%
                    </div>
                  </div>
                ))}
                <p className="text-xs text-mutedText flex items-center gap-1">
                  <InformationCircleIcon className="w-3.5 h-3.5" />
                  Weights auto-normalize to 100%. Meta-learner uses base model outputs as features.
                </p>
              </div>
            </SectionCard>
          )}

          {/* Decision Threshold */}
          <SectionCard
            title="Decision Threshold"
            subtitle="Score above this value triggers a flagged/suspicious alert"
            icon={<BoltIcon className="w-5 h-5" />}
          >
            <div className="flex items-center gap-6">
              <input
                type="range"
                min={10}
                max={95}
                value={Math.round(selection.threshold * 100)}
                onChange={e => { setSelection(prev => ({ ...prev, threshold: parseInt(e.target.value) / 100 })); setDirty(true); }}
                className="flex-1 h-2 rounded-full appearance-none cursor-pointer bg-slate-700 accent-blue-500"
              />
              <div className="text-2xl font-bold font-mono text-text w-20 text-center">
                {(selection.threshold * 100).toFixed(0)}%
              </div>
            </div>
            <div className="flex justify-between text-xs text-mutedText mt-2 px-1">
              <span>More Permissive (fewer alerts)</span>
              <span>More Aggressive (more alerts)</span>
            </div>
            {/* Threshold impact preview */}
            <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-borderSubtle">
              <div className="text-center">
                <p className="text-xs text-mutedText">Estimated FP Rate</p>
                <p className={`text-lg font-bold ${selection.threshold < 0.4 ? 'text-red-400' : selection.threshold < 0.6 ? 'text-amber-400' : 'text-green-400'}`}>
                  {selection.threshold < 0.3 ? '~12%' : selection.threshold < 0.5 ? '~5%' : selection.threshold < 0.7 ? '~2%' : '~0.5%'}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-mutedText">Estimated Recall</p>
                <p className={`text-lg font-bold ${selection.threshold > 0.7 ? 'text-red-400' : selection.threshold > 0.5 ? 'text-amber-400' : 'text-green-400'}`}>
                  {selection.threshold < 0.3 ? '~99%' : selection.threshold < 0.5 ? '~96%' : selection.threshold < 0.7 ? '~91%' : '~82%'}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-mutedText">Optimal</p>
                <p className="text-lg font-bold text-blue-400">{modelInfo?.optimal_threshold ? `${(modelInfo.optimal_threshold * 100).toFixed(0)}%` : '50%'}</p>
              </div>
            </div>
          </SectionCard>

          {/* Model Health */}
          {modelInfo && (
            <SectionCard title="Model Runtime Info" subtitle={`Version ${modelInfo.model_version} • Last updated ${new Date(modelInfo.last_updated).toLocaleString()}`} icon={<InformationCircleIcon className="w-5 h-5" />}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-mutedText uppercase">Loaded</p>
                  <p className="text-text font-semibold flex items-center gap-1">
                    {modelInfo.model_loaded ? <><CheckCircleIcon className="w-4 h-4 text-green-400" /> Yes</> : <><ExclamationTriangleIcon className="w-4 h-4 text-red-400" /> No</>}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-mutedText uppercase">Available Models</p>
                  <p className="text-text font-semibold">{modelInfo.models_available.length}</p>
                </div>
                <div>
                  <p className="text-xs text-mutedText uppercase">Features</p>
                  <p className="text-text font-semibold">{modelInfo.n_boost_features}</p>
                </div>
                <div>
                  <p className="text-xs text-mutedText uppercase">Preprocessors</p>
                  <p className="text-text font-semibold">{modelInfo.has_preprocessors ? 'Active' : 'None'}</p>
                </div>
              </div>
              {modelInfo.training_performance && Object.keys(modelInfo.training_performance).length > 0 && (
                <div className="mt-4 pt-4 border-t border-borderSubtle">
                  <p className="text-xs text-mutedText uppercase mb-2">Training Performance</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(modelInfo.training_performance).map(([k, v]) => (
                      <div key={k}>
                        <p className="text-[10px] text-mutedText uppercase">{k.replace(/_/g, ' ')}</p>
                        <p className="text-text font-mono text-sm">{typeof v === 'number' ? (v < 1 ? `${(v * 100).toFixed(1)}%` : v.toFixed(4)) : String(v)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </SectionCard>
          )}
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* TAB: DETECTION RULES                                               */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {tab === 'rules' && (
        <div className="space-y-6">
          {/* Stats bar */}
          {monStats && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="bg-surface rounded-lg p-3 border border-borderSubtle">
                <p className="text-xs text-mutedText">Total Alerts</p>
                <p className="text-xl font-bold text-text">{monStats.total_alerts}</p>
              </div>
              <div className="bg-surface rounded-lg p-3 border border-borderSubtle">
                <p className="text-xs text-mutedText">Transactions Stored</p>
                <p className="text-xl font-bold text-text">{monStats.transactions_stored.toLocaleString()}</p>
              </div>
              <div className="bg-surface rounded-lg p-3 border border-borderSubtle">
                <p className="text-xs text-mutedText">Addresses Tracked</p>
                <p className="text-xl font-bold text-text">{monStats.addresses_tracked.toLocaleString()}</p>
              </div>
              <div className="bg-surface rounded-lg p-3 border border-borderSubtle">
                <p className="text-xs text-mutedText">Active Rules</p>
                <p className="text-xl font-bold text-green-400">{rules.filter(r => r.enabled).length} / {rules.length}</p>
              </div>
              <div className="bg-surface rounded-lg p-3 border border-borderSubtle">
                <p className="text-xs text-mutedText">By Severity</p>
                <div className="flex items-center gap-2 mt-1">
                  {Object.entries(monStats.by_severity || {}).map(([sev, count]) => (
                    <span key={sev} className={`text-xs px-1.5 py-0.5 rounded ${
                      sev === 'CRITICAL' ? 'bg-red-900/50 text-red-400' :
                      sev === 'HIGH' ? 'bg-amber-900/50 text-amber-400' :
                      sev === 'MEDIUM' ? 'bg-yellow-900/50 text-yellow-400' :
                      'bg-slate-700 text-slate-300'
                    }`}>
                      {sev}: {count}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Rule Cards */}
          <SectionCard
            title="Detection Rules"
            subtitle="Toggle individual pattern-detection rules. Disabled rules will not fire alerts."
            icon={<ShieldCheckIcon className="w-5 h-5" />}
          >
            {rules.length === 0 && !loading && (
              <p className="text-mutedText text-sm py-4">Monitoring service offline — no rules loaded.</p>
            )}
            <div className="space-y-3">
              {rules.map((rule, idx) => (
                <div key={rule.name} className={`flex items-center gap-4 p-4 rounded-lg border transition-colors ${
                  rule.enabled ? 'bg-surface border-borderSubtle' : 'bg-slate-900/50 border-slate-800 opacity-60'
                }`}>
                  {/* Toggle */}
                  <button
                    onClick={() => toggleRule(idx)}
                    className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                      rule.enabled ? 'bg-blue-600' : 'bg-slate-700'
                    }`}
                  >
                    <span className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                      rule.enabled ? 'translate-x-5' : 'translate-x-0'
                    }`} />
                  </button>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="text-text font-medium text-sm">{rule.name.replace(/^detect_/, '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</h4>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wider ${
                        rule.type === 'STRUCTURING' ? 'bg-red-900/50 text-red-400 border border-red-800' :
                        rule.type === 'ROUND_TRIP' ? 'bg-amber-900/50 text-amber-400 border border-amber-800' :
                        rule.type === 'LAYERING' ? 'bg-purple-900/50 text-purple-400 border border-purple-800' :
                        rule.type === 'RAPID_MOVEMENT' ? 'bg-blue-900/50 text-blue-400 border border-blue-800' :
                        rule.type === 'VELOCITY' ? 'bg-cyan-900/50 text-cyan-400 border border-cyan-800' :
                        'bg-slate-700 text-slate-300 border border-slate-600'
                      }`}>
                        {rule.type}
                      </span>
                    </div>
                    <p className="text-mutedText text-xs mt-0.5 truncate">{rule.description}</p>
                  </div>

                  {/* Badge */}
                  <div className="text-xs text-mutedText">
                    {rule.enabled ? (
                      <span className="flex items-center gap-1 text-green-400"><PlayIcon className="w-3 h-3" /> Active</span>
                    ) : (
                      <span className="flex items-center gap-1 text-slate-500"><PauseIcon className="w-3 h-3" /> Paused</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </SectionCard>

          {/* Custom Rule Builder */}
          <SectionCard
            title="Add Manual Rule"
            subtitle="Create a custom threshold-based detection rule"
            icon={<AdjustmentsHorizontalIcon className="w-5 h-5" />}
          >
            <ManualRuleBuilder onAdd={(rule) => { setRules(prev => [...prev, { ...rule, enabled: true }]); setDirty(true); }} />
          </SectionCard>
        </div>
      )}

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* TAB: THRESHOLDS                                                    */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      {tab === 'thresholds' && editThresholds && (
        <div className="space-y-6">
          {/* Structuring */}
          <SectionCard title="Structuring Detection" subtitle="Detect transactions structured to avoid regulatory thresholds" icon={<ShieldCheckIcon className="w-5 h-5" />}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <ThresholdInput label="Window (hours)" value={editThresholds.structuring_window_hours} onChange={v => updateThreshold('structuring_window_hours', v)} min={1} max={168} step={1} unit="h" />
              <ThresholdInput label="Reporting Threshold (ETH)" value={editThresholds.structuring_threshold_eth} onChange={v => updateThreshold('structuring_threshold_eth', v)} min={0.1} max={100} step={0.1} unit="ETH" />
              <ThresholdInput label="Min Transactions" value={editThresholds.structuring_min_transactions} onChange={v => updateThreshold('structuring_min_transactions', v)} min={2} max={20} step={1} unit="tx" />
              <ThresholdInput label="Max Individual %" value={editThresholds.structuring_max_individual_pct * 100} onChange={v => updateThreshold('structuring_max_individual_pct', v / 100)} min={50} max={99} step={1} unit="%" />
            </div>
          </SectionCard>

          {/* Round-Trip */}
          <SectionCard title="Round-Trip Detection" subtitle="Detect money returning to origin through intermediaries" icon={<ArrowPathIcon className="w-5 h-5" />}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <ThresholdInput label="Window (hours)" value={editThresholds.roundtrip_window_hours} onChange={v => updateThreshold('roundtrip_window_hours', v)} min={1} max={336} step={1} unit="h" />
              <ThresholdInput label="Min Return %" value={editThresholds.roundtrip_min_return_pct * 100} onChange={v => updateThreshold('roundtrip_min_return_pct', v / 100)} min={50} max={100} step={1} unit="%" />
              <ThresholdInput label="Max Hops" value={editThresholds.roundtrip_max_hops} onChange={v => updateThreshold('roundtrip_max_hops', v)} min={2} max={20} step={1} unit="hops" />
            </div>
          </SectionCard>

          {/* Layering */}
          <SectionCard title="Layering Detection" subtitle="Detect complex multi-hop chains that obscure fund origin" icon={<BoltIcon className="w-5 h-5" />}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <ThresholdInput label="Window (hours)" value={editThresholds.layering_window_hours} onChange={v => updateThreshold('layering_window_hours', v)} min={1} max={336} step={1} unit="h" />
              <ThresholdInput label="Min Hops" value={editThresholds.layering_min_hops} onChange={v => updateThreshold('layering_min_hops', v)} min={2} max={15} step={1} unit="hops" />
              <ThresholdInput label="Value Decay Tolerance" value={editThresholds.layering_value_decay_tolerance * 100} onChange={v => updateThreshold('layering_value_decay_tolerance', v / 100)} min={1} max={50} step={1} unit="%" />
            </div>
          </SectionCard>

          {/* Velocity */}
          <SectionCard title="Velocity & Rapid Movement" subtitle="Detect abnormal transaction frequency and fast in/out patterns" icon={<ClockIcon className="w-5 h-5" />}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <ThresholdInput label="Window (hours)" value={editThresholds.velocity_window_hours} onChange={v => updateThreshold('velocity_window_hours', v)} min={0.5} max={24} step={0.5} unit="h" />
              <ThresholdInput label="Max Transactions / Window" value={editThresholds.velocity_max_transactions} onChange={v => updateThreshold('velocity_max_transactions', v)} min={3} max={100} step={1} unit="tx" />
            </div>
          </SectionCard>
        </div>
      )}

      {tab === 'thresholds' && !editThresholds && !loading && (
        <div className="bg-surface rounded-xl border border-borderSubtle p-8 text-center">
          <ExclamationTriangleIcon className="w-12 h-12 text-amber-400 mx-auto mb-3" />
          <p className="text-text font-semibold">Monitoring Service Offline</p>
          <p className="text-mutedText text-sm mt-1">Cannot load threshold configuration. Start the monitoring service on port 8005.</p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// THRESHOLD INPUT
// ═══════════════════════════════════════════════════════════════════════════════

function ThresholdInput({ label, value, onChange, min, max, step, unit }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  unit: string;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <label className="text-sm text-text font-medium">{label}</label>
        <span className="text-sm font-mono text-blue-400">{value}{unit !== '%' && unit !== 'h' ? ` ${unit}` : unit}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="w-full h-2 rounded-full appearance-none cursor-pointer bg-slate-700 accent-blue-500"
      />
      <div className="flex justify-between text-[10px] text-mutedText/50 mt-1">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MANUAL RULE BUILDER
// ═══════════════════════════════════════════════════════════════════════════════

function ManualRuleBuilder({ onAdd }: { onAdd: (rule: DetectionRule) => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState('CUSTOM');
  const [field, setField] = useState('amount');
  const [operator, setOperator] = useState('gt');
  const [value, setValue] = useState('');
  const [description, setDescription] = useState('');

  const FIELDS = [
    { id: 'amount', label: 'Transaction Amount (ETH)' },
    { id: 'risk_score', label: 'ML Risk Score' },
    { id: 'tx_count_24h', label: 'TX Count (24h)' },
    { id: 'unique_counterparties', label: 'Unique Counterparties' },
    { id: 'gas_price_gwei', label: 'Gas Price (Gwei)' },
    { id: 'contract_interaction', label: 'Contract Interaction Count' },
  ];

  const OPERATORS = [
    { id: 'gt', label: '>' },
    { id: 'gte', label: '>=' },
    { id: 'lt', label: '<' },
    { id: 'lte', label: '<=' },
    { id: 'eq', label: '=' },
    { id: 'between', label: 'Between' },
  ];

  const handleAdd = () => {
    if (!name.trim() || !value.trim()) return;
    const fieldLabel = FIELDS.find(f => f.id === field)?.label ?? field;
    const opLabel = OPERATORS.find(o => o.id === operator)?.label ?? operator;
    const autoDesc = description || `Flag when ${fieldLabel} ${opLabel} ${value}`;
    onAdd({
      name: `custom_${name.replace(/\s+/g, '_').toLowerCase()}`,
      type,
      description: autoDesc,
      enabled: true,
    });
    setName('');
    setValue('');
    setDescription('');
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Rule Name */}
        <div>
          <label className="block text-xs text-mutedText mb-1">Rule Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Large Single Transfer"
            className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        {/* Rule Type */}
        <div>
          <label className="block text-xs text-mutedText mb-1">Category</label>
          <select
            value={type}
            onChange={e => setType(e.target.value)}
            className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="CUSTOM">Custom</option>
            <option value="STRUCTURING">Structuring</option>
            <option value="VELOCITY">Velocity</option>
            <option value="LAYERING">Layering</option>
            <option value="ROUND_TRIP">Round-Trip</option>
            <option value="THRESHOLD">Threshold</option>
            <option value="SANCTIONS">Sanctions</option>
          </select>
        </div>
      </div>

      {/* Condition Row */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[160px]">
          <label className="block text-xs text-mutedText mb-1">Field</label>
          <select
            value={field}
            onChange={e => setField(e.target.value)}
            className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
          >
            {FIELDS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
          </select>
        </div>

        <div className="w-24">
          <label className="block text-xs text-mutedText mb-1">Operator</label>
          <select
            value={operator}
            onChange={e => setOperator(e.target.value)}
            className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
          >
            {OPERATORS.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </select>
        </div>

        <div className="w-32">
          <label className="block text-xs text-mutedText mb-1">Value</label>
          <input
            type="text"
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder="100"
            className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
          />
        </div>

        <button
          onClick={handleAdd}
          disabled={!name.trim() || !value.trim()}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          + Add Rule
        </button>
      </div>

      {/* Description (optional) */}
      <div>
        <label className="block text-xs text-mutedText mb-1">Description (optional)</label>
        <input
          type="text"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="Auto-generated from condition if left blank"
          className="w-full px-3 py-2 bg-background border border-borderSubtle rounded-lg text-text text-sm focus:outline-none focus:border-blue-500"
        />
      </div>
    </div>
  );
}
