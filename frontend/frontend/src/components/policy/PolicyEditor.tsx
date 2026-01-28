'use client';

/**
 * PolicyEditor Component
 * 
 * Full policy rule builder for War Room
 * 
 * Ground Truth Reference:
 * - Rules must be explicit, not implied
 * - Clear cause-effect relationships
 * - Version control for all changes
 */

import React, { useState, useCallback } from 'react';
import {
  Policy,
  PolicyRule,
  PolicyCondition,
  PolicyType,
  PolicyAction,
  RuleType,
  ConditionOperator,
  getPolicyTypeLabel,
  getRuleTypeLabel,
  getConditionOperatorLabel,
  PolicyStatus,
} from '@/types/policy-engine';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface PolicyEditorProps {
  policy?: Policy | null;
  onSave: (policy: Partial<Policy>) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

type EditablePolicy = {
  name: string;
  description: string;
  type: PolicyType;
  rules: PolicyRule[];
  priority: number;
  tags: string[];
};

// ═══════════════════════════════════════════════════════════════════════════════
// CONDITION EDITOR
// ═══════════════════════════════════════════════════════════════════════════════

function ConditionEditor({
  condition,
  onChange,
  onRemove,
}: {
  condition: PolicyCondition;
  onChange: (condition: PolicyCondition) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2 bg-slate-900/50 rounded p-2">
      <input
        type="text"
        value={condition.field}
        onChange={(e) => onChange({ ...condition, field: e.target.value })}
        placeholder="field"
        className="w-24 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-sm text-white"
      />
      
      <select
        value={condition.operator}
        onChange={(e) => onChange({ ...condition, operator: e.target.value as ConditionOperator })}
        className="px-2 py-1 bg-slate-800 border border-slate-600 rounded text-sm text-white"
      >
        {Object.values(ConditionOperator).map((op) => (
          <option key={op} value={op}>{getConditionOperatorLabel(op)}</option>
        ))}
      </select>
      
      <input
        type="text"
        value={typeof condition.value === 'object' ? JSON.stringify(condition.value) : String(condition.value)}
        onChange={(e) => onChange({ ...condition, value: e.target.value })}
        placeholder="value"
        className="flex-1 px-2 py-1 bg-slate-800 border border-slate-600 rounded text-sm text-white"
      />
      
      <button
        onClick={onRemove}
        className="p-1 text-slate-500 hover:text-red-400"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// RULE EDITOR
// ═══════════════════════════════════════════════════════════════════════════════

function RuleEditor({
  rule,
  index,
  onChange,
  onRemove,
}: {
  rule: PolicyRule;
  index: number;
  onChange: (rule: PolicyRule) => void;
  onRemove: () => void;
}) {
  const addCondition = () => {
    const newCondition: PolicyCondition = {
      field: '',
      operator: ConditionOperator.EQ,
      value: '',
    };
    onChange({
      ...rule,
      conditions: [...rule.conditions, newCondition],
    });
  };
  
  const updateCondition = (idx: number, condition: PolicyCondition) => {
    const updated = [...rule.conditions];
    updated[idx] = condition;
    onChange({ ...rule, conditions: updated });
  };
  
  const removeCondition = (idx: number) => {
    onChange({
      ...rule,
      conditions: rule.conditions.filter((_, i) => i !== idx),
    });
  };
  
  return (
    <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="w-6 h-6 bg-slate-700 rounded-full flex items-center justify-center text-xs text-slate-300">
            {index + 1}
          </span>
          <input
            type="text"
            value={rule.name}
            onChange={(e) => onChange({ ...rule, name: e.target.value })}
            placeholder="Rule name"
            className="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-white"
          />
          <label className="flex items-center gap-2 text-sm text-slate-400">
            <input
              type="checkbox"
              checked={rule.enabled}
              onChange={(e) => onChange({ ...rule, enabled: e.target.checked })}
              className="rounded border-slate-600 bg-slate-800"
            />
            Enabled
          </label>
        </div>
        <button
          onClick={onRemove}
          className="text-sm text-red-400 hover:text-red-300"
        >
          Remove Rule
        </button>
      </div>
      
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Rule Type</label>
          <select
            value={rule.type}
            onChange={(e) => onChange({ ...rule, type: e.target.value as RuleType })}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
          >
            {Object.values(RuleType).map((type) => (
              <option key={type} value={type}>{getRuleTypeLabel(type)}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Action</label>
          <select
            value={rule.action}
            onChange={(e) => onChange({ ...rule, action: e.target.value as PolicyAction })}
            className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
          >
            {Object.values(PolicyAction).map((action) => (
              <option key={action} value={action}>{action}</option>
            ))}
          </select>
        </div>
      </div>
      
      {/* Conditions */}
      <div className="mb-3">
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-slate-500">Conditions (AND)</label>
          <button
            onClick={addCondition}
            className="text-xs text-cyan-400 hover:text-cyan-300"
          >
            + Add Condition
          </button>
        </div>
        
        {rule.conditions.length === 0 ? (
          <div className="text-sm text-slate-500 bg-slate-900/30 rounded p-3 text-center">
            No conditions - rule will match all transactions
          </div>
        ) : (
          <div className="space-y-2">
            {rule.conditions.map((condition, idx) => (
              <ConditionEditor
                key={idx}
                condition={condition}
                onChange={(c) => updateCondition(idx, c)}
                onRemove={() => removeCondition(idx)}
              />
            ))}
          </div>
        )}
      </div>
      
      {/* Description */}
      <textarea
        value={rule.description || ''}
        onChange={(e) => onChange({ ...rule, description: e.target.value })}
        placeholder="Rule description (optional)"
        rows={2}
        className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm resize-none"
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function PolicyEditor({
  policy,
  onSave,
  onCancel,
  isLoading = false,
}: PolicyEditorProps) {
  const isEditing = !!policy;
  
  const [editablePolicy, setEditablePolicy] = useState<EditablePolicy>(() => ({
    name: policy?.name || '',
    description: policy?.description || '',
    type: policy?.type || PolicyType.TRANSFER_LIMIT,
    rules: policy?.rules || [],
    priority: policy?.priority || 50,
    tags: policy?.tags || [],
  }));
  
  const [tagInput, setTagInput] = useState('');
  
  const updateField = useCallback(<K extends keyof EditablePolicy>(field: K, value: EditablePolicy[K]) => {
    setEditablePolicy(prev => ({ ...prev, [field]: value }));
  }, []);
  
  const addRule = () => {
    const newRule: PolicyRule = {
      id: `rule-${Date.now()}`,
      name: `Rule ${editablePolicy.rules.length + 1}`,
      description: '',
      priority: 1,
      type: RuleType.AMOUNT_LIMIT,
      conditions: [],
      action: PolicyAction.FLAG,
      enabled: true,
    };
    updateField('rules', [...editablePolicy.rules, newRule]);
  };
  
  const updateRule = (index: number, rule: PolicyRule) => {
    const updated = [...editablePolicy.rules];
    updated[index] = rule;
    updateField('rules', updated);
  };
  
  const removeRule = (index: number) => {
    updateField('rules', editablePolicy.rules.filter((_, i) => i !== index));
  };
  
  const addTag = () => {
    if (tagInput.trim() && !editablePolicy.tags.includes(tagInput.trim())) {
      updateField('tags', [...editablePolicy.tags, tagInput.trim()]);
      setTagInput('');
    }
  };
  
  const removeTag = (tag: string) => {
    updateField('tags', editablePolicy.tags.filter(t => t !== tag));
  };
  
  const handleSave = () => {
    if (!editablePolicy.name.trim()) return;
    
    onSave({
      ...policy,
      ...editablePolicy,
      status: policy?.status || PolicyStatus.DRAFT,
    });
  };
  
  return (
    <div className="bg-slate-800/30 rounded-lg border border-slate-700">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-700">
        <h2 className="text-lg font-medium text-white">
          {isEditing ? 'Edit Policy' : 'Create Policy'}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={isLoading || !editablePolicy.name.trim()}
            className="px-4 py-2 text-sm bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Saving...' : isEditing ? 'Update Policy' : 'Create Policy'}
          </button>
        </div>
      </div>
      
      {/* Form */}
      <div className="p-4 space-y-6">
        {/* Basic Info */}
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3">Basic Information</h3>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-xs text-slate-500 mb-1">Policy Name *</label>
              <input
                type="text"
                value={editablePolicy.name}
                onChange={(e) => updateField('name', e.target.value)}
                placeholder="e.g., High-Value Transfer Protection"
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
              />
            </div>
            
            <div>
              <label className="block text-xs text-slate-500 mb-1">Policy Type</label>
              <select
                value={editablePolicy.type}
                onChange={(e) => updateField('type', e.target.value as PolicyType)}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
              >
                {Object.values(PolicyType).map((type) => (
                  <option key={type} value={type}>{getPolicyTypeLabel(type)}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-xs text-slate-500 mb-1">Priority (1-100)</label>
              <input
                type="number"
                min={1}
                max={100}
                value={editablePolicy.priority}
                onChange={(e) => updateField('priority', Math.min(100, Math.max(1, parseInt(e.target.value) || 1)))}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
              />
            </div>
            
            <div className="col-span-2">
              <label className="block text-xs text-slate-500 mb-1">Description</label>
              <textarea
                value={editablePolicy.description}
                onChange={(e) => updateField('description', e.target.value)}
                placeholder="Describe what this policy does and why..."
                rows={3}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white resize-none"
              />
            </div>
          </div>
        </section>
        
        {/* Tags */}
        <section>
          <h3 className="text-sm font-medium text-slate-400 mb-3">Tags</h3>
          <div className="flex flex-wrap gap-2 mb-2">
            {editablePolicy.tags.map((tag) => (
              <span
                key={tag}
                className="px-2 py-1 bg-slate-700 text-slate-300 text-sm rounded-full flex items-center gap-1"
              >
                {tag}
                <button onClick={() => removeTag(tag)} className="text-slate-500 hover:text-red-400">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
              placeholder="Add tag..."
              className="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-white text-sm"
            />
            <button
              onClick={addTag}
              className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded text-sm hover:bg-slate-600"
            >
              Add
            </button>
          </div>
        </section>
        
        {/* Rules */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-slate-400">
              Rules ({editablePolicy.rules.length})
            </h3>
            <button
              onClick={addRule}
              className="px-3 py-1.5 bg-cyan-600/20 text-cyan-400 rounded text-sm hover:bg-cyan-600/30"
            >
              + Add Rule
            </button>
          </div>
          
          {editablePolicy.rules.length === 0 ? (
            <div className="bg-slate-900/30 rounded-lg border border-dashed border-slate-600 p-8 text-center">
              <svg className="w-12 h-12 text-slate-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-slate-500 mb-2">No rules defined</p>
              <p className="text-xs text-slate-600">Add rules to define policy behavior</p>
            </div>
          ) : (
            <div className="space-y-4">
              {editablePolicy.rules.map((rule, idx) => (
                <RuleEditor
                  key={rule.id}
                  rule={rule}
                  index={idx}
                  onChange={(r) => updateRule(idx, r)}
                  onRemove={() => removeRule(idx)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
