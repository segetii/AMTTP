'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';

const API = 'http://127.0.0.1:8003';

interface PolicyThresholds { lowRiskMax: number; mediumRiskMax: number; highRiskMax: number; }
interface PolicyLimits { maxTransactionAmount: string; dailyLimit: string; monthlyLimit: string; maxCounterparties: number; }
interface PolicyRules { blockSanctionedAddresses: boolean; requireKYCAboveThreshold: boolean; kycThresholdAmount: string; autoEscrowHighRisk: boolean; escrowDurationHours: number; allowedChainIds: number[]; blockedCountries: string[]; }
interface PolicyActions { onLowRisk: string; onMediumRisk: string; onHighRisk: string; onCriticalRisk: string; onSanctionedAddress: string; onUnknownAddress: string; }
interface PolicyStats { totalTransactions: number; approvedCount: number; reviewedCount: number; escrowedCount: number; blockedCount: number; lastTriggered: string | null; }

interface Policy {
  id: string;
  name: string;
  description: string;
  isActive: boolean;
  isDefault: boolean;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  thresholds: PolicyThresholds;
  limits: PolicyLimits;
  rules: PolicyRules;
  actions: PolicyActions;
  whitelist: string[];
  blacklist: string[];
  stats: PolicyStats;
  onChainId: number | null;
}

const DEFAULT_THRESHOLDS: PolicyThresholds = { lowRiskMax: 25, mediumRiskMax: 50, highRiskMax: 75 };
const DEFAULT_LIMITS: PolicyLimits = { maxTransactionAmount: '1000000000000000000000', dailyLimit: '10000000000000000000000', monthlyLimit: '100000000000000000000000', maxCounterparties: 100 };
const DEFAULT_RULES: PolicyRules = { blockSanctionedAddresses: true, requireKYCAboveThreshold: true, kycThresholdAmount: '10000000000000000000', autoEscrowHighRisk: true, escrowDurationHours: 24, allowedChainIds: [1, 137, 42161], blockedCountries: [] };
const DEFAULT_ACTIONS: PolicyActions = { onLowRisk: 'APPROVE', onMediumRisk: 'REVIEW', onHighRisk: 'ESCROW', onCriticalRisk: 'BLOCK', onSanctionedAddress: 'BLOCK', onUnknownAddress: 'REVIEW' };

const ACTION_OPTIONS = ['APPROVE', 'REVIEW', 'ESCROW', 'BLOCK'];
const ACTION_LABELS: Record<string, string> = { onLowRisk: 'Low Risk', onMediumRisk: 'Medium Risk', onHighRisk: 'High Risk', onCriticalRisk: 'Critical Risk', onSanctionedAddress: 'Sanctioned Address', onUnknownAddress: 'Unknown Address' };

function weiToEth(wei: string) {
  try { const n = BigInt(wei); return `${Number(n / BigInt(10 ** 14)) / 10000} ETH`; } catch { return wei; }
}

function ethToWei(eth: string) {
  try { return (BigInt(Math.round(parseFloat(eth) * 10000)) * BigInt(10 ** 14)).toString(); } catch { return '0'; }
}

function getActionColor(action: string) {
  switch (action) {
    case 'APPROVE': return 'text-green-400';
    case 'REVIEW': return 'text-yellow-400';
    case 'ESCROW': return 'text-orange-400';
    case 'BLOCK': return 'text-red-400';
    default: return 'text-slate-400';
  }
}

export default function PolicyEnginePage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPolicy, setSelectedPolicy] = useState<Policy | null>(null);
  const [editingPolicy, setEditingPolicy] = useState<Partial<Policy> | null>(null);
  const [saving, setSaving] = useState(false);
  const [toastMsg, setToastMsg] = useState<string | null>(null);

  const toast = (msg: string) => { setToastMsg(msg); setTimeout(() => setToastMsg(null), 3000); };

  const fetchPolicies = useCallback(() => {
    setLoading(true);
    fetch(`${API}/policies`)
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(data => { setPolicies(Array.isArray(data) ? data : []); setError(null); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchPolicies(); }, [fetchPolicies]);

  const toggleActive = async (policy: Policy) => {
    try {
      const r = await fetch(`${API}/policies/${policy.id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ isActive: !policy.isActive }),
      });
      if (!r.ok) throw new Error(`${r.status}`);
      setPolicies(prev => prev.map(p => p.id === policy.id ? { ...p, isActive: !p.isActive } : p));
      toast(`${policy.name} ${policy.isActive ? 'disabled' : 'enabled'}`);
    } catch (e: any) { toast(`Failed: ${e.message}`); }
  };

  const deletePolicy = async (id: string) => {
    if (!confirm('Delete this policy?')) return;
    try {
      const r = await fetch(`${API}/policies/${id}`, { method: 'DELETE' });
      if (!r.ok) throw new Error(`${r.status}`);
      setPolicies(prev => prev.filter(p => p.id !== id));
      setSelectedPolicy(null);
      toast('Policy deleted');
    } catch (e: any) { toast(`Failed: ${e.message}`); }
  };

  const savePolicy = async () => {
    if (!editingPolicy?.name?.trim()) { toast('Name is required'); return; }
    setSaving(true);
    try {
      const isNew = !editingPolicy.id;
      const url = isNew ? `${API}/policies` : `${API}/policies/${editingPolicy.id}`;
      const method = isNew ? 'POST' : 'PATCH';
      const body: any = {
        name: editingPolicy.name,
        description: editingPolicy.description || '',
        isActive: editingPolicy.isActive ?? true,
        thresholds: editingPolicy.thresholds ?? DEFAULT_THRESHOLDS,
        limits: editingPolicy.limits ?? DEFAULT_LIMITS,
        rules: editingPolicy.rules ?? DEFAULT_RULES,
        actions: editingPolicy.actions ?? DEFAULT_ACTIONS,
        whitelist: editingPolicy.whitelist ?? [],
        blacklist: editingPolicy.blacklist ?? [],
      };
      const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) { const t = await r.text(); throw new Error(t || `${r.status}`); }
      setEditingPolicy(null);
      fetchPolicies();
      toast(isNew ? 'Policy created' : 'Policy updated');
    } catch (e: any) { toast(`Save failed: ${e.message}`); }
    finally { setSaving(false); }
  };

  const openCreate = () => {
    setEditingPolicy({
      name: '', description: '', isActive: true,
      thresholds: { ...DEFAULT_THRESHOLDS }, limits: { ...DEFAULT_LIMITS },
      rules: { ...DEFAULT_RULES, allowedChainIds: [...DEFAULT_RULES.allowedChainIds], blockedCountries: [] },
      actions: { ...DEFAULT_ACTIONS }, whitelist: [], blacklist: [],
    });
  };

  const openEdit = (p: Policy) => {
    setEditingPolicy({ ...p, thresholds: { ...p.thresholds }, limits: { ...p.limits }, rules: { ...p.rules, allowedChainIds: [...(p.rules?.allowedChainIds ?? [])], blockedCountries: [...(p.rules?.blockedCountries ?? [])] }, actions: { ...p.actions }, whitelist: [...(p.whitelist ?? [])], blacklist: [...(p.blacklist ?? [])] });
    setSelectedPolicy(null);
  };

  const totalTx = policies.reduce((s, p) => s + (p.stats?.totalTransactions ?? 0), 0);
  const totalBlocked = policies.reduce((s, p) => s + (p.stats?.blockedCount ?? 0), 0);

  return (
    <div className="space-y-6">
      {/* Toast */}
      {toastMsg && <div className="fixed top-4 right-4 z-[60] bg-indigo-600 text-white px-4 py-2 rounded-lg shadow-lg text-sm animate-pulse">{toastMsg}</div>}

      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">⚠ Policy service unavailable — {error}</div>}
      {loading && <div className="text-zinc-500 text-sm">Loading policies...</div>}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">← War Room</Link>
          </div>
          <h1 className="text-3xl font-bold">Policy Engine</h1>
          <p className="text-mutedText mt-1">Configure transaction policies, risk thresholds, and compliance controls</p>
        </div>
        <button onClick={openCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg flex items-center gap-2 font-medium">
          <span>+ New Policy</span>
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold">{policies.length}</div>
          <div className="text-mutedText text-sm">Total Policies</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-green-400">{policies.filter(p => p.isActive).length}</div>
          <div className="text-mutedText text-sm">Active</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-blue-400">{totalTx.toLocaleString()}</div>
          <div className="text-mutedText text-sm">Total Evaluated</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-2xl font-bold text-red-400">{totalBlocked.toLocaleString()}</div>
          <div className="text-mutedText text-sm">Blocked</div>
        </div>
      </div>

      {/* Policy List */}
      <div className="space-y-4">
        {policies.map(policy => {
          const act = policy.actions ?? {} as PolicyActions;
          return (
            <div key={policy.id} className="bg-surface rounded-xl p-6 border border-borderSubtle hover:border-indigo-500/40 cursor-pointer transition-colors" onClick={() => setSelectedPolicy(policy)}>
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <h3 className="text-lg font-semibold">{policy.name}</h3>
                    {policy.isDefault && <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-500/20 text-indigo-400">DEFAULT</span>}
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${policy.isActive ? 'bg-green-500/20 text-green-400' : 'bg-slate-500/20 text-mutedText'}`}>
                      {policy.isActive ? 'Active' : 'Inactive'}
                    </span>
                    {policy.onChainId && <span className="px-2 py-0.5 rounded text-xs font-medium bg-purple-500/20 text-purple-400">On-chain</span>}
                  </div>
                  <p className="text-mutedText text-sm mb-3">{policy.description}</p>
                  <div className="flex gap-4 text-sm flex-wrap">
                    <span className="text-mutedText">Thresholds: <span className="text-green-400">{policy.thresholds?.lowRiskMax ?? '?'}</span> / <span className="text-yellow-400">{policy.thresholds?.mediumRiskMax ?? '?'}</span> / <span className="text-red-400">{policy.thresholds?.highRiskMax ?? '?'}</span></span>
                    <span className="text-mutedText">Actions: <span className={getActionColor(act.onHighRisk)}>High→{act.onHighRisk}</span></span>
                    <span className="text-mutedText">Evaluated: <span className="text-slate-300">{(policy.stats?.totalTransactions ?? 0).toLocaleString()}</span></span>
                    <span className="text-mutedText">Updated: <span className="text-slate-300">{new Date(policy.updatedAt).toLocaleDateString()}</span></span>
                  </div>
                </div>
                <div className="flex items-center gap-2 ml-4 shrink-0" onClick={e => e.stopPropagation()}>
                  <button onClick={() => toggleActive(policy)} className={`px-3 py-1 rounded text-sm ${policy.isActive ? 'bg-red-600/20 text-red-400 hover:bg-red-600/30' : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'}`}>
                    {policy.isActive ? 'Disable' : 'Enable'}
                  </button>
                  <button onClick={() => openEdit(policy)} className="px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-sm">Edit</button>
                  {!policy.isDefault && <button onClick={() => deletePolicy(policy.id)} className="px-3 py-1 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded text-sm">Delete</button>}
                </div>
              </div>
            </div>
          );
        })}
        {!loading && policies.length === 0 && !error && (
          <div className="bg-surface rounded-xl p-12 border border-borderSubtle text-center">
            <p className="text-mutedText mb-4">No policies configured yet</p>
            <button onClick={openCreate} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg">Create First Policy</button>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedPolicy && !editingPolicy && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setSelectedPolicy(null)}>
          <div className="bg-surface rounded-xl p-6 max-w-4xl w-full mx-4 border border-borderSubtle max-h-[85vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold">{selectedPolicy.name}</h2>
                {selectedPolicy.isDefault && <span className="px-2 py-1 rounded text-xs font-medium bg-indigo-500/20 text-indigo-400">DEFAULT</span>}
                <span className={`px-2 py-1 rounded text-xs font-medium ${selectedPolicy.isActive ? 'bg-green-500/20 text-green-400' : 'bg-slate-500/20 text-mutedText'}`}>
                  {selectedPolicy.isActive ? 'Active' : 'Inactive'}
                </span>
              </div>
              <button onClick={() => setSelectedPolicy(null)} className="text-mutedText hover:text-text text-xl">✕</button>
            </div>

            <p className="text-mutedText mb-6">{selectedPolicy.description}</p>

            {/* Thresholds */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Risk Thresholds</h3>
              <div className="bg-slate-700/50 rounded-lg p-4">
                <div className="flex gap-6">
                  <div className="flex-1 text-center"><div className="text-2xl font-bold text-green-400">{selectedPolicy.thresholds?.lowRiskMax ?? 25}</div><div className="text-xs text-mutedText">Low Risk Max</div></div>
                  <div className="flex-1 text-center"><div className="text-2xl font-bold text-yellow-400">{selectedPolicy.thresholds?.mediumRiskMax ?? 50}</div><div className="text-xs text-mutedText">Medium Risk Max</div></div>
                  <div className="flex-1 text-center"><div className="text-2xl font-bold text-red-400">{selectedPolicy.thresholds?.highRiskMax ?? 75}</div><div className="text-xs text-mutedText">High Risk Max</div></div>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Risk Actions</h3>
              <div className="bg-slate-700/50 rounded-lg p-4 grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.entries(selectedPolicy.actions ?? {}).map(([key, val]) => (
                  <div key={key} className="flex items-center justify-between bg-background rounded px-3 py-2">
                    <span className="text-sm text-mutedText">{ACTION_LABELS[key] ?? key}</span>
                    <span className={`text-sm font-medium ${getActionColor(val)}`}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Limits */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Transaction Limits</h3>
              <div className="bg-slate-700/50 rounded-lg p-4 grid grid-cols-2 gap-3">
                <div className="bg-background rounded px-3 py-2"><span className="text-xs text-mutedText block">Max Transaction</span><span className="text-sm font-medium">{weiToEth(selectedPolicy.limits?.maxTransactionAmount ?? '0')}</span></div>
                <div className="bg-background rounded px-3 py-2"><span className="text-xs text-mutedText block">Daily Limit</span><span className="text-sm font-medium">{weiToEth(selectedPolicy.limits?.dailyLimit ?? '0')}</span></div>
                <div className="bg-background rounded px-3 py-2"><span className="text-xs text-mutedText block">Monthly Limit</span><span className="text-sm font-medium">{weiToEth(selectedPolicy.limits?.monthlyLimit ?? '0')}</span></div>
                <div className="bg-background rounded px-3 py-2"><span className="text-xs text-mutedText block">Max Counterparties</span><span className="text-sm font-medium">{selectedPolicy.limits?.maxCounterparties ?? 100}</span></div>
              </div>
            </div>

            {/* Rules */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Rules</h3>
              <div className="bg-slate-700/50 rounded-lg p-4 space-y-2">
                {[
                  ['Block Sanctioned Addresses', selectedPolicy.rules?.blockSanctionedAddresses],
                  ['Require KYC Above Threshold', selectedPolicy.rules?.requireKYCAboveThreshold],
                  ['Auto-Escrow High Risk', selectedPolicy.rules?.autoEscrowHighRisk],
                ].map(([label, val]) => (
                  <div key={label as string} className="flex items-center justify-between">
                    <span className="text-sm">{label as string}</span>
                    <span className={`text-sm font-medium ${val ? 'text-green-400' : 'text-red-400'}`}>{val ? 'Enabled' : 'Disabled'}</span>
                  </div>
                ))}
                {(selectedPolicy.rules?.escrowDurationHours ?? 0) > 0 && <div className="flex justify-between text-sm"><span className="text-mutedText">Escrow Duration</span><span>{selectedPolicy.rules.escrowDurationHours}h</span></div>}
                {(selectedPolicy.rules?.allowedChainIds ?? []).length > 0 && <div className="flex justify-between text-sm"><span className="text-mutedText">Allowed Chains</span><span>{selectedPolicy.rules.allowedChainIds.join(', ')}</span></div>}
                {(selectedPolicy.rules?.blockedCountries ?? []).length > 0 && <div className="flex justify-between text-sm"><span className="text-mutedText">Blocked Countries</span><span className="text-red-400">{selectedPolicy.rules.blockedCountries.join(', ')}</span></div>}
              </div>
            </div>

            {/* Whitelist / Blacklist */}
            {((selectedPolicy.whitelist?.length ?? 0) > 0 || (selectedPolicy.blacklist?.length ?? 0) > 0) && (
              <div className="mb-6 grid grid-cols-2 gap-4">
                {(selectedPolicy.whitelist?.length ?? 0) > 0 && (
                  <div><h3 className="text-sm font-medium text-mutedText mb-2">Whitelist ({selectedPolicy.whitelist.length})</h3>
                    <div className="bg-slate-700/50 rounded-lg p-3 space-y-1">{selectedPolicy.whitelist.map(a => <code key={a} className="block text-xs text-green-400 truncate">{a}</code>)}</div>
                  </div>
                )}
                {(selectedPolicy.blacklist?.length ?? 0) > 0 && (
                  <div><h3 className="text-sm font-medium text-mutedText mb-2">Blacklist ({selectedPolicy.blacklist.length})</h3>
                    <div className="bg-slate-700/50 rounded-lg p-3 space-y-1">{selectedPolicy.blacklist.map(a => <code key={a} className="block text-xs text-red-400 truncate">{a}</code>)}</div>
                  </div>
                )}
              </div>
            )}

            {/* Stats */}
            {selectedPolicy.stats && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-mutedText mb-2">Evaluation Stats</h3>
                <div className="bg-slate-700/50 rounded-lg p-4 grid grid-cols-5 gap-3 text-center">
                  <div><div className="text-lg font-bold">{selectedPolicy.stats.totalTransactions.toLocaleString()}</div><div className="text-xs text-mutedText">Total</div></div>
                  <div><div className="text-lg font-bold text-green-400">{selectedPolicy.stats.approvedCount.toLocaleString()}</div><div className="text-xs text-mutedText">Approved</div></div>
                  <div><div className="text-lg font-bold text-yellow-400">{selectedPolicy.stats.reviewedCount.toLocaleString()}</div><div className="text-xs text-mutedText">Reviewed</div></div>
                  <div><div className="text-lg font-bold text-orange-400">{selectedPolicy.stats.escrowedCount.toLocaleString()}</div><div className="text-xs text-mutedText">Escrowed</div></div>
                  <div><div className="text-lg font-bold text-red-400">{selectedPolicy.stats.blockedCount.toLocaleString()}</div><div className="text-xs text-mutedText">Blocked</div></div>
                </div>
              </div>
            )}

            <div className="flex justify-between text-xs text-mutedText mb-6">
              <span>Created: {new Date(selectedPolicy.createdAt).toLocaleString()} by {selectedPolicy.createdBy?.slice(0, 10)}…</span>
              <span>Updated: {new Date(selectedPolicy.updatedAt).toLocaleString()}</span>
            </div>

            <div className="flex gap-3 justify-end">
              {!selectedPolicy.isDefault && <button onClick={() => deletePolicy(selectedPolicy.id)} className="px-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-lg mr-auto">Delete</button>}
              <button onClick={() => setSelectedPolicy(null)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">Close</button>
              <button onClick={() => openEdit(selectedPolicy)} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg">Edit Policy</button>
            </div>
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {editingPolicy && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-surface rounded-xl p-6 max-w-4xl w-full mx-4 border border-borderSubtle max-h-[85vh] overflow-y-auto">
            <h2 className="text-xl font-bold mb-6">{editingPolicy.id ? 'Edit Policy' : 'Create New Policy'}</h2>

            {/* Basic */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div>
                <label className="block text-sm text-mutedText mb-1">Name *</label>
                <input value={editingPolicy.name ?? ''} onChange={e => setEditingPolicy(p => ({ ...p!, name: e.target.value }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" placeholder="Policy name" />
              </div>
              <div>
                <label className="block text-sm text-mutedText mb-1">Status</label>
                <button onClick={() => setEditingPolicy(p => ({ ...p!, isActive: !p!.isActive }))} className={`px-4 py-2 rounded-lg text-sm font-medium w-full ${editingPolicy.isActive ? 'bg-green-600/20 text-green-400 border border-green-500/30' : 'bg-slate-700 text-mutedText border border-borderSubtle'}`}>
                  {editingPolicy.isActive ? 'Active' : 'Inactive'}
                </button>
              </div>
              <div className="col-span-2">
                <label className="block text-sm text-mutedText mb-1">Description</label>
                <input value={editingPolicy.description ?? ''} onChange={e => setEditingPolicy(p => ({ ...p!, description: e.target.value }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" placeholder="Description" />
              </div>
            </div>

            {/* Thresholds */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Risk Thresholds</h3>
              <div className="grid grid-cols-3 gap-4">
                {(['lowRiskMax', 'mediumRiskMax', 'highRiskMax'] as const).map(k => (
                  <div key={k}>
                    <label className="block text-xs text-mutedText mb-1">{k === 'lowRiskMax' ? 'Low → Medium' : k === 'mediumRiskMax' ? 'Medium → High' : 'High → Critical'}</label>
                    <input type="number" min={0} max={100} value={editingPolicy.thresholds?.[k] ?? 0} onChange={e => setEditingPolicy(p => ({ ...p!, thresholds: { ...p!.thresholds!, [k]: parseInt(e.target.value) || 0 } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" />
                  </div>
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Risk Actions</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {Object.keys(ACTION_LABELS).map(key => (
                  <div key={key}>
                    <label className="block text-xs text-mutedText mb-1">{ACTION_LABELS[key]}</label>
                    <select value={(editingPolicy.actions as any)?.[key] ?? 'REVIEW'} onChange={e => setEditingPolicy(p => ({ ...p!, actions: { ...p!.actions!, [key]: e.target.value } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm">
                      {ACTION_OPTIONS.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  </div>
                ))}
              </div>
            </div>

            {/* Limits */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Transaction Limits (ETH)</h3>
              <div className="grid grid-cols-2 gap-4">
                {[
                  ['maxTransactionAmount', 'Max Transaction'],
                  ['dailyLimit', 'Daily Limit'],
                  ['monthlyLimit', 'Monthly Limit'],
                ].map(([k, label]) => (
                  <div key={k}>
                    <label className="block text-xs text-mutedText mb-1">{label}</label>
                    <input type="number" step="0.01" value={(() => { try { return Number(BigInt(editingPolicy.limits?.[k as keyof PolicyLimits] as string ?? '0') / BigInt(10**14)) / 10000; } catch { return 0; } })()} onChange={e => setEditingPolicy(p => ({ ...p!, limits: { ...p!.limits!, [k]: ethToWei(e.target.value) } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" />
                  </div>
                ))}
                <div>
                  <label className="block text-xs text-mutedText mb-1">Max Counterparties</label>
                  <input type="number" value={editingPolicy.limits?.maxCounterparties ?? 100} onChange={e => setEditingPolicy(p => ({ ...p!, limits: { ...p!.limits!, maxCounterparties: parseInt(e.target.value) || 0 } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" />
                </div>
              </div>
            </div>

            {/* Rules */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-mutedText mb-2">Rules</h3>
              <div className="space-y-2">
                {[
                  ['blockSanctionedAddresses', 'Block Sanctioned Addresses'],
                  ['requireKYCAboveThreshold', 'Require KYC Above Threshold'],
                  ['autoEscrowHighRisk', 'Auto-Escrow High Risk'],
                ].map(([k, label]) => (
                  <label key={k} className="flex items-center gap-3 cursor-pointer">
                    <input type="checkbox" checked={(editingPolicy.rules as any)?.[k] ?? false} onChange={e => setEditingPolicy(p => ({ ...p!, rules: { ...p!.rules!, [k]: e.target.checked } }))} className="w-4 h-4 rounded border-borderSubtle accent-indigo-600" />
                    <span className="text-sm">{label}</span>
                  </label>
                ))}
                <div className="grid grid-cols-2 gap-4 mt-3">
                  <div>
                    <label className="block text-xs text-mutedText mb-1">Escrow Duration (hours)</label>
                    <input type="number" value={editingPolicy.rules?.escrowDurationHours ?? 24} onChange={e => setEditingPolicy(p => ({ ...p!, rules: { ...p!.rules!, escrowDurationHours: parseInt(e.target.value) || 0 } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs text-mutedText mb-1">Blocked Countries (comma-separated)</label>
                    <input value={(editingPolicy.rules?.blockedCountries ?? []).join(', ')} onChange={e => setEditingPolicy(p => ({ ...p!, rules: { ...p!.rules!, blockedCountries: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } }))} className="w-full bg-background border border-borderSubtle rounded-lg px-3 py-2 text-sm" placeholder="KP, IR, SY" />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex gap-3 justify-end border-t border-borderSubtle pt-4">
              <button onClick={() => setEditingPolicy(null)} className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg">Cancel</button>
              <button onClick={savePolicy} disabled={saving} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 rounded-lg font-medium">
                {saving ? 'Saving...' : editingPolicy.id ? 'Update Policy' : 'Create Policy'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
