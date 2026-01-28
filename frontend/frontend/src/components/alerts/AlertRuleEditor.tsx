'use client';

/**
 * AlertRuleEditor Component
 * 
 * Create and edit alert rules with conditions and thresholds
 * 
 * Ground Truth Reference:
 * - Conditional logic builder
 * - Threshold configuration
 * - Rule preview and testing
 */

import React, { useState } from 'react';
import {
  AlertRule,
  AlertPriority,
  AlertCategory,
  AlertCondition,
  ConditionOperator,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface AlertRuleEditorProps {
  rule?: AlertRule;
  onSave: (rule: Omit<AlertRule, 'id' | 'createdAt' | 'updatedAt' | 'createdBy'>) => void;
  onCancel: () => void;
}

type ConditionField = 
  | 'transaction_value'
  | 'gas_price'
  | 'dispute_count'
  | 'escrow_balance'
  | 'bridge_delay'
  | 'policy_violations'
  | 'failed_transactions'
  | 'contract_call_failure';

const CONDITION_FIELDS: { value: ConditionField; label: string; unit: string }[] = [
  { value: 'transaction_value', label: 'Transaction Value', unit: 'ETH' },
  { value: 'gas_price', label: 'Gas Price', unit: 'Gwei' },
  { value: 'dispute_count', label: 'Active Disputes', unit: 'count' },
  { value: 'escrow_balance', label: 'Escrow Balance', unit: 'ETH' },
  { value: 'bridge_delay', label: 'Bridge Delay', unit: 'minutes' },
  { value: 'policy_violations', label: 'Policy Violations', unit: 'count' },
  { value: 'failed_transactions', label: 'Failed Transactions', unit: 'count' },
  { value: 'contract_call_failure', label: 'Contract Call Failures', unit: 'count' },
];

// UI-friendly threshold for display (simplified from full AlertCondition)
interface ThresholdConfig {
  metric: string;
  warning: number;
  critical: number;
  unit: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function ConditionBuilder({
  condition,
  onChange,
  onRemove,
}: {
  condition: AlertCondition;
  onChange: (condition: AlertCondition) => void;
  onRemove: () => void;
}) {
  const field = CONDITION_FIELDS.find(f => f.value === condition.field);
  
  const handleOperatorChange = (op: string) => {
    const operatorMap: Record<string, ConditionOperator> = {
      'greater_than': ConditionOperator.GREATER_THAN,
      'less_than': ConditionOperator.LESS_THAN,
      'equals': ConditionOperator.EQUALS,
      'not_equals': ConditionOperator.NOT_EQUALS,
      'contains': ConditionOperator.CONTAINS,
    };
    onChange({ ...condition, operator: operatorMap[op] || ConditionOperator.GREATER_THAN });
  };
  
  const getOperatorValue = (op: ConditionOperator): string => {
    const reverseMap: Record<ConditionOperator, string> = {
      [ConditionOperator.GREATER_THAN]: 'greater_than',
      [ConditionOperator.LESS_THAN]: 'less_than',
      [ConditionOperator.EQUALS]: 'equals',
      [ConditionOperator.NOT_EQUALS]: 'not_equals',
      [ConditionOperator.CONTAINS]: 'contains',
      [ConditionOperator.GREATER_THAN_OR_EQUAL]: 'greater_than',
      [ConditionOperator.LESS_THAN_OR_EQUAL]: 'less_than',
      [ConditionOperator.NOT_CONTAINS]: 'contains',
      [ConditionOperator.IN]: 'equals',
      [ConditionOperator.NOT_IN]: 'not_equals',
      [ConditionOperator.MATCHES]: 'contains',
      [ConditionOperator.EXISTS]: 'equals',
      [ConditionOperator.NOT_EXISTS]: 'not_equals',
    };
    return reverseMap[op] || 'greater_than';
  };
  
  return (
    <div className="flex items-center gap-2 p-3 bg-slate-800 rounded-lg">
      <select
        value={condition.field}
        onChange={(e) => onChange({ ...condition, field: e.target.value })}
        className="flex-1 bg-slate-700 border-slate-600 rounded px-2 py-1 text-sm"
      >
        {CONDITION_FIELDS.map((f) => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>
      
      <select
        value={getOperatorValue(condition.operator)}
        onChange={(e) => handleOperatorChange(e.target.value)}
        className="w-24 bg-slate-700 border-slate-600 rounded px-2 py-1 text-sm"
      >
        <option value="greater_than">&gt;</option>
        <option value="less_than">&lt;</option>
        <option value="equals">=</option>
        <option value="not_equals">≠</option>
        <option value="contains">contains</option>
      </select>
      
      <input
        type="number"
        value={typeof condition.value === 'number' ? condition.value : 0}
        onChange={(e) => onChange({ ...condition, value: parseFloat(e.target.value) || 0 })}
        className="w-24 bg-slate-700 border-slate-600 rounded px-2 py-1 text-sm"
      />
      
      <span className="text-xs text-slate-400 w-16">{field?.unit}</span>
      
      <button
        onClick={onRemove}
        className="p-1 text-red-400 hover:text-red-300"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

function ThresholdBuilder({
  threshold,
  onChange,
  onRemove,
}: {
  threshold: ThresholdConfig;
  onChange: (threshold: ThresholdConfig) => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2 p-3 bg-slate-800 rounded-lg">
      <span className="text-sm text-slate-400">When value exceeds</span>
      <input
        type="number"
        value={threshold.warning}
        onChange={(e) => onChange({ ...threshold, warning: parseFloat(e.target.value) || 0 })}
        className="w-24 bg-yellow-900/30 border-yellow-600 rounded px-2 py-1 text-sm text-yellow-300"
        placeholder="Warning"
      />
      <span className="text-xs text-yellow-400">⚠️</span>
      
      <input
        type="number"
        value={threshold.critical}
        onChange={(e) => onChange({ ...threshold, critical: parseFloat(e.target.value) || 0 })}
        className="w-24 bg-red-900/30 border-red-600 rounded px-2 py-1 text-sm text-red-300"
        placeholder="Critical"
      />
      <span className="text-xs text-red-400">🚨</span>
      
      <button
        onClick={onRemove}
        className="p-1 text-red-400 hover:text-red-300 ml-auto"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AlertRuleEditor({
  rule,
  onSave,
  onCancel,
}: AlertRuleEditorProps) {
  const [name, setName] = useState(rule?.name || '');
  const [description, setDescription] = useState(rule?.description || '');
  const [category, setCategory] = useState<AlertCategory>(rule?.category || AlertCategory.SECURITY);
  const [priority, setPriority] = useState<AlertPriority>(rule?.priority || AlertPriority.MEDIUM);
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [conditions, setConditions] = useState<AlertCondition[]>(
    rule?.conditions || [{ field: 'transaction_value', operator: ConditionOperator.GREATER_THAN, value: 100, valueType: 'number' }]
  );
  const [thresholds, setThresholds] = useState<ThresholdConfig[]>([]);
  const [cooldownMinutes, setCooldownMinutes] = useState(rule?.cooldownMinutes || 5);
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!name.trim()) return;
    
    onSave({
      name,
      description,
      category,
      priority,
      enabled,
      conditions,
      conditionLogic: 'AND',
      titleTemplate: name,
      messageTemplate: description,
      channels: [],
      recipients: [],
      cooldownMinutes,
      tags: [],
    });
  };
  
  const addCondition = () => {
    setConditions([
      ...conditions,
      { field: 'transaction_value', operator: ConditionOperator.GREATER_THAN, value: 0, valueType: 'number' },
    ]);
  };
  
  const updateCondition = (index: number, condition: AlertCondition) => {
    const newConditions = [...conditions];
    newConditions[index] = condition;
    setConditions(newConditions);
  };
  
  const removeCondition = (index: number) => {
    setConditions(conditions.filter((_, i) => i !== index));
  };
  
  const addThreshold = () => {
    setThresholds([
      ...thresholds,
      { metric: 'value', warning: 50, critical: 100, unit: 'ETH' },
    ]);
  };
  
  const updateThreshold = (index: number, threshold: ThresholdConfig) => {
    const newThresholds = [...thresholds];
    newThresholds[index] = threshold;
    setThresholds(newThresholds);
  };
  
  const removeThreshold = (index: number) => {
    setThresholds(thresholds.filter((_, i) => i !== index));
  };
  
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 p-6">
      <h3 className="text-lg font-semibold text-white mb-6">
        {rule ? 'Edit Alert Rule' : 'Create Alert Rule'}
      </h3>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic Info */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Rule Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white"
              placeholder="e.g., High Value Transaction Alert"
              required
            />
          </div>
          
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as AlertCategory)}
                className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white"
              >
                <option value="SECURITY">Security</option>
                <option value="TRANSACTION">Transaction</option>
                <option value="DISPUTE">Dispute</option>
                <option value="GOVERNANCE">Governance</option>
                <option value="COMPLIANCE">Compliance</option>
                <option value="SYSTEM">System</option>
              </select>
            </div>
            
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Priority
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as AlertPriority)}
                className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white"
              >
                <option value="INFO">Info</option>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </div>
          </div>
        </div>
        
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white h-20"
            placeholder="Describe when this alert should trigger..."
          />
        </div>
        
        {/* Conditions */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm font-medium text-slate-300">
              Conditions
            </label>
            <button
              type="button"
              onClick={addCondition}
              className="text-xs text-cyan-400 hover:text-cyan-300"
            >
              + Add Condition
            </button>
          </div>
          
          <div className="space-y-2">
            {conditions.map((condition, index) => (
              <ConditionBuilder
                key={index}
                condition={condition}
                onChange={(c) => updateCondition(index, c)}
                onRemove={() => removeCondition(index)}
              />
            ))}
          </div>
          
          {conditions.length > 1 && (
            <p className="text-xs text-slate-400 mt-2">
              All conditions must be met (AND logic)
            </p>
          )}
        </div>
        
        {/* Thresholds */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <label className="text-sm font-medium text-slate-300">
              Thresholds (optional)
            </label>
            <button
              type="button"
              onClick={addThreshold}
              className="text-xs text-cyan-400 hover:text-cyan-300"
            >
              + Add Threshold
            </button>
          </div>
          
          <div className="space-y-2">
            {thresholds.map((threshold, index) => (
              <ThresholdBuilder
                key={index}
                threshold={threshold}
                onChange={(t) => updateThreshold(index, t)}
                onRemove={() => removeThreshold(index)}
              />
            ))}
          </div>
        </div>
        
        {/* Settings */}
        <div className="flex items-center gap-6 pt-4 border-t border-slate-700">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-cyan-500 focus:ring-cyan-500"
            />
            <span className="text-sm text-slate-300">Enabled</span>
          </label>
          
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-400">Cooldown:</span>
            <input
              type="number"
              value={cooldownMinutes}
              onChange={(e) => setCooldownMinutes(parseInt(e.target.value) || 1)}
              className="w-16 bg-slate-800 border-slate-700 rounded px-2 py-1 text-sm text-white"
              min={1}
            />
            <span className="text-sm text-slate-400">minutes</span>
          </div>
        </div>
        
        {/* Actions */}
        <div className="flex justify-end gap-3 pt-4">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-slate-300 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg transition-colors"
          >
            {rule ? 'Update Rule' : 'Create Rule'}
          </button>
        </div>
      </form>
    </div>
  );
}
