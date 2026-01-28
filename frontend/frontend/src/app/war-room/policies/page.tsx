'use client';

/**
 * War Room - Policy Engine Page
 * 
 * Sprint 7: Policy Engine UI
 * 
 * Ground Truth Reference:
 * - Policies are rules, not suggestions
 * - Clear cause-effect for compliance
 * - Version control for all policy changes
 * - Simulation before activation
 */

import React, { useState } from 'react';
import { usePolicy } from '@/lib/policy-engine-service';
import { PolicyList, PolicyEditor, PolicySimulator } from '@/components/policy';
import { Policy, PolicyStatus } from '@/types/policy-engine';

// ═══════════════════════════════════════════════════════════════════════════════
// VIEW TABS
// ═══════════════════════════════════════════════════════════════════════════════

type ViewTab = 'list' | 'simulator';

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ═══════════════════════════════════════════════════════════════════════════════

export default function PoliciesPage() {
  const {
    policies,
    isLoading,
    createPolicy,
    updatePolicy,
    togglePolicy,
    deletePolicy,
  } = usePolicy();
  
  const [activeTab, setActiveTab] = useState<ViewTab>('list');
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  
  const selectedPolicy = selectedPolicyId 
    ? policies.find(p => p.id === selectedPolicyId) || null 
    : null;
  
  // Handlers
  const handleSelect = (policyId: string) => {
    setSelectedPolicyId(policyId);
    setIsEditing(false);
    setIsCreating(false);
  };
  
  const handleCreate = () => {
    setSelectedPolicyId(null);
    setIsEditing(false);
    setIsCreating(true);
  };
  
  const handleEdit = () => {
    if (selectedPolicyId) {
      setIsEditing(true);
      setIsCreating(false);
    }
  };
  
  const handleCancel = () => {
    setIsEditing(false);
    setIsCreating(false);
  };
  
  const handleSave = async (policyData: Partial<Policy>) => {
    try {
      if (isCreating) {
        await createPolicy(policyData as Omit<Policy, 'id' | 'createdAt' | 'updatedAt' | 'createdBy' | 'version'>);
      } else if (selectedPolicyId) {
        await updatePolicy(selectedPolicyId, policyData);
      }
      setIsEditing(false);
      setIsCreating(false);
    } catch (error) {
      console.error('Failed to save policy:', error);
    }
  };
  
  const handleActivate = async (policyId: string) => {
    await togglePolicy(policyId, true);
  };
  
  const handleSuspend = async (policyId: string) => {
    await togglePolicy(policyId, false);
  };
  
  const handleDelete = async () => {
    if (selectedPolicyId && confirm('Are you sure you want to delete this policy?')) {
      await deletePolicy(selectedPolicyId);
      setSelectedPolicyId(null);
    }
  };
  
  // Stats
  const stats = {
    total: policies.length,
    active: policies.filter(p => p.status === PolicyStatus.ACTIVE).length,
    pending: policies.filter(p => [PolicyStatus.DRAFT, PolicyStatus.PENDING_APPROVAL].includes(p.status)).length,
    totalRules: policies.reduce((sum, p) => sum + p.rules.length, 0),
  };
  
  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-white">Policy Engine</h1>
            <p className="text-slate-400">Configure and manage transfer policies</p>
          </div>
          
          {/* Quick Stats */}
          <div className="flex items-center gap-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-white">{stats.total}</p>
              <p className="text-xs text-slate-500">Policies</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-green-400">{stats.active}</p>
              <p className="text-xs text-slate-500">Active</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-yellow-400">{stats.pending}</p>
              <p className="text-xs text-slate-500">Pending</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-cyan-400">{stats.totalRules}</p>
              <p className="text-xs text-slate-500">Rules</p>
            </div>
          </div>
        </div>
        
        {/* Tabs & Actions */}
        <div className="flex items-center justify-between border-b border-slate-700 pb-4">
          <div className="flex gap-1">
            <button
              onClick={() => setActiveTab('list')}
              className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
                ${activeTab === 'list'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-white'}`}
            >
              📋 Policies
            </button>
            <button
              onClick={() => setActiveTab('simulator')}
              className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors
                ${activeTab === 'simulator'
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:text-white'}`}
            >
              🧪 Simulator
            </button>
          </div>
          
          <button
            onClick={handleCreate}
            className="px-4 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-500 flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Policy
          </button>
        </div>
      </header>
      
      {/* Content */}
      {activeTab === 'list' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Policy List */}
          <div className="lg:col-span-1">
            <PolicyList
              policies={policies}
              onSelect={handleSelect}
              onActivate={handleActivate}
              onSuspend={handleSuspend}
              isLoading={isLoading}
              selectedId={selectedPolicyId || undefined}
            />
          </div>
          
          {/* Detail / Editor Panel */}
          <div className="lg:col-span-2">
            {isCreating || isEditing ? (
              <PolicyEditor
                policy={isEditing ? selectedPolicy : null}
                onSave={handleSave}
                onCancel={handleCancel}
                isLoading={isLoading}
              />
            ) : selectedPolicy ? (
              <PolicyDetailPanel
                policy={selectedPolicy}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onActivate={() => handleActivate(selectedPolicy.id)}
                onSuspend={() => handleSuspend(selectedPolicy.id)}
              />
            ) : (
              <EmptyStatePanel onCreateClick={handleCreate} />
            )}
          </div>
        </div>
      )}
      
      {activeTab === 'simulator' && (
        <PolicySimulator policies={policies} />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// POLICY DETAIL PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function PolicyDetailPanel({
  policy,
  onEdit,
  onDelete,
  onActivate,
  onSuspend,
}: {
  policy: Policy;
  onEdit: () => void;
  onDelete: () => void;
  onActivate: () => void;
  onSuspend: () => void;
}) {
  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <div>
          <h2 className="text-lg font-medium text-white">{policy.name}</h2>
          <p className="text-sm text-slate-400">Version {policy.version}</p>
        </div>
        <div className="flex items-center gap-2">
          {policy.status === PolicyStatus.ACTIVE && (
            <button
              onClick={onSuspend}
              className="px-3 py-1.5 text-sm bg-orange-600/20 text-orange-400 rounded hover:bg-orange-600/30"
            >
              Suspend
            </button>
          )}
          {[PolicyStatus.DRAFT, PolicyStatus.SUSPENDED].includes(policy.status) && (
            <button
              onClick={onActivate}
              className="px-3 py-1.5 text-sm bg-green-600/20 text-green-400 rounded hover:bg-green-600/30"
            >
              Activate
            </button>
          )}
          <button
            onClick={onEdit}
            className="px-3 py-1.5 text-sm bg-slate-700 text-slate-300 rounded hover:bg-slate-600"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="px-3 py-1.5 text-sm bg-red-600/20 text-red-400 rounded hover:bg-red-600/30"
          >
            Delete
          </button>
        </div>
      </div>
      
      {/* Content */}
      <div className="p-4 space-y-6">
        {/* Description */}
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-2">Description</h3>
          <p className="text-slate-300">{policy.description || 'No description'}</p>
        </div>
        
        {/* Stats */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-slate-900/50 rounded-lg p-3 text-center">
            <p className="text-xl font-bold text-white">{policy.stats?.evaluations.toLocaleString() || 0}</p>
            <p className="text-xs text-slate-500">Evaluations</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 text-center">
            <p className="text-xl font-bold text-amber-400">{policy.stats?.triggers.toLocaleString() || 0}</p>
            <p className="text-xs text-slate-500">Triggers</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 text-center">
            <p className="text-xl font-bold text-red-400">0</p>
            <p className="text-xs text-slate-500">Blocks</p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 text-center">
            <p className="text-xl font-bold text-green-400">0.0ms</p>
            <p className="text-xs text-slate-500">Avg Time</p>
          </div>
        </div>
        
        {/* Rules */}
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-3">
            Rules ({policy.rules.length})
          </h3>
          <div className="space-y-2">
            {policy.rules.map((rule, idx) => (
              <div
                key={rule.id}
                className={`bg-slate-900/50 rounded-lg p-3 border ${
                  rule.enabled ? 'border-slate-600' : 'border-slate-700 opacity-50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-5 h-5 bg-slate-700 rounded-full flex items-center justify-center text-xs">
                      {idx + 1}
                    </span>
                    <span className="font-medium text-white">{rule.name}</span>
                    {!rule.enabled && (
                      <span className="px-2 py-0.5 text-xs bg-slate-700 text-slate-400 rounded">Disabled</span>
                    )}
                  </div>
                  <span className={`px-2 py-0.5 text-xs rounded ${
                    rule.action === 'ALLOW' ? 'bg-green-900/30 text-green-400' :
                    rule.action === 'BLOCK' ? 'bg-red-900/30 text-red-400' :
                    rule.action === 'FLAG' ? 'bg-yellow-900/30 text-yellow-400' :
                    rule.action === 'REQUIRE_ESCROW' ? 'bg-blue-900/30 text-blue-400' :
                    'bg-orange-900/30 text-orange-400'
                  }`}>
                    {rule.action}
                  </span>
                </div>
                
                {rule.conditions.length > 0 && (
                  <div className="text-xs text-slate-500 space-y-1">
                    {rule.conditions.map((cond, cIdx) => (
                      <div key={cIdx}>
                        <span className="text-slate-400">{cond.field}</span>
                        {' '}
                        <span className="text-cyan-400">{cond.operator}</span>
                        {' '}
                        <span className="text-white">{JSON.stringify(cond.value)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        
        {/* Tags */}
        {policy.tags && policy.tags.length > 0 && (
          <div>
            <h3 className="text-sm font-medium text-slate-400 mb-2">Tags</h3>
            <div className="flex flex-wrap gap-2">
              {policy.tags.map((tag) => (
                <span key={tag} className="px-2 py-1 bg-slate-700 text-slate-300 text-sm rounded-full">
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
        
        {/* Metadata */}
        <div className="pt-4 border-t border-slate-700 text-xs text-slate-500 flex items-center justify-between">
          <span>Created by {policy.createdBy}</span>
          <span>Updated {policy.updatedAt ? new Date(policy.updatedAt).toLocaleString() : 'N/A'}</span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EMPTY STATE
// ═══════════════════════════════════════════════════════════════════════════════

function EmptyStatePanel({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-12 text-center">
      <svg className="w-16 h-16 text-slate-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <h3 className="text-lg font-medium text-slate-300 mb-2">Select a Policy</h3>
      <p className="text-sm text-slate-500 mb-6">
        Select a policy from the list to view details, or create a new one.
      </p>
      <button
        onClick={onCreateClick}
        className="px-4 py-2 bg-cyan-600 text-white rounded-lg text-sm font-medium hover:bg-cyan-500"
      >
        Create New Policy
      </button>
    </div>
  );
}
