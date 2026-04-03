'use client';

import { useState } from 'react';
import {
  Shield, Save, X, Plus, Trash2, AlertTriangle,
  ChevronDown, ChevronUp, Settings, Lock, Globe
} from 'lucide-react';
import type { PolicyFormData, RiskAction, DEFAULT_POLICY } from '@/types/policy';

interface PolicyFormProps {
  initialData?: PolicyFormData;
  onSubmit: (data: PolicyFormData) => Promise<void>;
  onCancel: () => void;
  isEdit?: boolean;
}

const CHAIN_OPTIONS = [
  { id: 1, name: 'Ethereum', symbol: 'ETH' },
  { id: 137, name: 'Polygon', symbol: 'MATIC' },
  { id: 42161, name: 'Arbitrum One', symbol: 'ETH' },
  { id: 10, name: 'Optimism', symbol: 'ETH' },
  { id: 8453, name: 'Base', symbol: 'ETH' },
  { id: 56, name: 'BNB Chain', symbol: 'BNB' },
  { id: 43114, name: 'Avalanche', symbol: 'AVAX' },
];

const RISK_ACTIONS: RiskAction[] = ['APPROVE', 'REVIEW', 'ESCROW', 'BLOCK'];

const DEFAULT_FORM_DATA: PolicyFormData = {
  name: '',
  description: '',
  isActive: true,
  thresholds: {
    lowRiskMax: 25,
    mediumRiskMax: 50,
    highRiskMax: 75,
  },
  limits: {
    maxTransactionAmount: '1000',
    dailyLimit: '10000',
    monthlyLimit: '100000',
    maxCounterparties: 100,
  },
  rules: {
    blockSanctionedAddresses: true,
    requireKYCAboveThreshold: true,
    kycThresholdAmount: '10',
    autoEscrowHighRisk: true,
    escrowDurationHours: 24,
    allowedChainIds: [1, 137, 42161],
    blockedCountries: [],
  },
  actions: {
    onLowRisk: 'APPROVE',
    onMediumRisk: 'REVIEW',
    onHighRisk: 'ESCROW',
    onCriticalRisk: 'BLOCK',
    onSanctionedAddress: 'BLOCK',
    onUnknownAddress: 'REVIEW',
  },
  whitelist: [],
  blacklist: [],
};

export function PolicyForm({ initialData, onSubmit, onCancel, isEdit }: PolicyFormProps) {
  const [formData, setFormData] = useState<PolicyFormData>(initialData || DEFAULT_FORM_DATA);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['basic', 'thresholds', 'actions'])
  );

  const [newWhitelistAddress, setNewWhitelistAddress] = useState('');
  const [newBlacklistAddress, setNewBlacklistAddress] = useState('');

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Policy name is required';
    }

    if (formData.thresholds.lowRiskMax >= formData.thresholds.mediumRiskMax) {
      newErrors.thresholds = 'Low risk threshold must be less than medium';
    }

    if (formData.thresholds.mediumRiskMax >= formData.thresholds.highRiskMax) {
      newErrors.thresholds = 'Medium risk threshold must be less than high';
    }

    if (formData.rules.allowedChainIds.length === 0) {
      newErrors.chains = 'At least one chain must be selected';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;

    setSubmitting(true);
    try {
      await onSubmit(formData);
    } catch (error) {
      console.error('Submit error:', error);
    }
    setSubmitting(false);
  };

  const addWhitelistAddress = () => {
    if (newWhitelistAddress && /^0x[a-fA-F0-9]{40}$/.test(newWhitelistAddress)) {
      if (!formData.whitelist.includes(newWhitelistAddress)) {
        setFormData({
          ...formData,
          whitelist: [...formData.whitelist, newWhitelistAddress]
        });
      }
      setNewWhitelistAddress('');
    }
  };

  const addBlacklistAddress = () => {
    if (newBlacklistAddress && /^0x[a-fA-F0-9]{40}$/.test(newBlacklistAddress)) {
      if (!formData.blacklist.includes(newBlacklistAddress)) {
        setFormData({
          ...formData,
          blacklist: [...formData.blacklist, newBlacklistAddress]
        });
      }
      setNewBlacklistAddress('');
    }
  };

  const removeWhitelistAddress = (address: string) => {
    setFormData({
      ...formData,
      whitelist: formData.whitelist.filter(a => a !== address)
    });
  };

  const removeBlacklistAddress = (address: string) => {
    setFormData({
      ...formData,
      blacklist: formData.blacklist.filter(a => a !== address)
    });
  };

  const SectionHeader = ({ id, title, icon: Icon }: { id: string; title: string; icon: React.ElementType }) => (
    <button
      type="button"
      onClick={() => toggleSection(id)}
      className="w-full flex items-center justify-between p-4 hover:bg-gray-800/50 transition-colors"
    >
      <div className="flex items-center gap-3">
        <Icon className="w-5 h-5 text-purple-400" />
        <span className="font-medium">{title}</span>
      </div>
      {expandedSections.has(id) ? (
        <ChevronUp className="w-5 h-5 text-gray-400" />
      ) : (
        <ChevronDown className="w-5 h-5 text-gray-400" />
      )}
    </button>
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Basic Information */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="basic" title="Basic Information" icon={Shield} />
        {expandedSections.has('basic') && (
          <div className="p-4 border-t border-gray-800 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Policy Name *
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className={`w-full px-4 py-2 bg-gray-800 border rounded-lg focus:outline-none focus:border-purple-500 ${
                  errors.name ? 'border-red-500' : 'border-gray-700'
                }`}
                placeholder="e.g., High Value Transactions"
              />
              {errors.name && <p className="mt-1 text-sm text-red-400">{errors.name}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Description
              </label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 resize-none"
                rows={3}
                placeholder="Describe the purpose of this policy..."
              />
            </div>

            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="isActive"
                checked={formData.isActive}
                onChange={(e) => setFormData({ ...formData, isActive: e.target.checked })}
                className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-purple-600 focus:ring-purple-500"
              />
              <label htmlFor="isActive" className="text-sm text-gray-300">
                Policy is active
              </label>
            </div>
          </div>
        )}
      </div>

      {/* Risk Thresholds */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="thresholds" title="Risk Thresholds" icon={AlertTriangle} />
        {expandedSections.has('thresholds') && (
          <div className="p-4 border-t border-gray-800 space-y-4">
            {errors.thresholds && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                {errors.thresholds}
              </div>
            )}
            
            <div className="grid md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Low Risk Max (0-100)
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={formData.thresholds.lowRiskMax}
                  onChange={(e) => setFormData({
                    ...formData,
                    thresholds: { ...formData.thresholds, lowRiskMax: parseInt(e.target.value) || 0 }
                  })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
                />
                <p className="mt-1 text-xs text-gray-500">Scores below this = Low Risk</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Medium Risk Max
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={formData.thresholds.mediumRiskMax}
                  onChange={(e) => setFormData({
                    ...formData,
                    thresholds: { ...formData.thresholds, mediumRiskMax: parseInt(e.target.value) || 0 }
                  })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
                />
                <p className="mt-1 text-xs text-gray-500">Scores below this = Medium Risk</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  High Risk Max
                </label>
                <input
                  type="number"
                  min="0"
                  max="100"
                  value={formData.thresholds.highRiskMax}
                  onChange={(e) => setFormData({
                    ...formData,
                    thresholds: { ...formData.thresholds, highRiskMax: parseInt(e.target.value) || 0 }
                  })}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
                />
                <p className="mt-1 text-xs text-gray-500">Scores above this = Critical</p>
              </div>
            </div>

            {/* Visual threshold bar */}
            <div className="mt-4">
              <div className="relative h-4 bg-gray-800 rounded-full overflow-hidden">
                <div 
                  className="absolute h-full bg-green-500/60" 
                  style={{ left: 0, width: `${formData.thresholds.lowRiskMax}%` }}
                />
                <div 
                  className="absolute h-full bg-yellow-500/60" 
                  style={{ left: `${formData.thresholds.lowRiskMax}%`, width: `${formData.thresholds.mediumRiskMax - formData.thresholds.lowRiskMax}%` }}
                />
                <div 
                  className="absolute h-full bg-orange-500/60" 
                  style={{ left: `${formData.thresholds.mediumRiskMax}%`, width: `${formData.thresholds.highRiskMax - formData.thresholds.mediumRiskMax}%` }}
                />
                <div 
                  className="absolute h-full bg-red-500/60" 
                  style={{ left: `${formData.thresholds.highRiskMax}%`, right: 0 }}
                />
              </div>
              <div className="flex justify-between mt-2 text-xs text-gray-500">
                <span className="text-green-400">Low</span>
                <span className="text-yellow-400">Medium</span>
                <span className="text-orange-400">High</span>
                <span className="text-red-400">Critical</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Risk Actions */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="actions" title="Risk Actions" icon={Settings} />
        {expandedSections.has('actions') && (
          <div className="p-4 border-t border-gray-800 space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              {[
                { key: 'onLowRisk', label: 'On Low Risk' },
                { key: 'onMediumRisk', label: 'On Medium Risk' },
                { key: 'onHighRisk', label: 'On High Risk' },
                { key: 'onCriticalRisk', label: 'On Critical Risk' },
                { key: 'onSanctionedAddress', label: 'On Sanctioned Address' },
                { key: 'onUnknownAddress', label: 'On Unknown Address' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    {label}
                  </label>
                  <select
                    value={formData.actions[key as keyof typeof formData.actions]}
                    onChange={(e) => setFormData({
                      ...formData,
                      actions: { ...formData.actions, [key]: e.target.value as RiskAction }
                    })}
                    className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
                  >
                    {RISK_ACTIONS.map(action => (
                      <option key={action} value={action}>{action}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Compliance Rules */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="rules" title="Compliance Rules" icon={Lock} />
        {expandedSections.has('rules') && (
          <div className="p-4 border-t border-gray-800 space-y-4">
            <div className="grid md:grid-cols-2 gap-4">
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="blockSanctioned"
                  checked={formData.rules.blockSanctionedAddresses}
                  onChange={(e) => setFormData({
                    ...formData,
                    rules: { ...formData.rules, blockSanctionedAddresses: e.target.checked }
                  })}
                  className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-purple-600"
                />
                <label htmlFor="blockSanctioned" className="text-sm text-gray-300">
                  Block sanctioned addresses
                </label>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="requireKYC"
                  checked={formData.rules.requireKYCAboveThreshold}
                  onChange={(e) => setFormData({
                    ...formData,
                    rules: { ...formData.rules, requireKYCAboveThreshold: e.target.checked }
                  })}
                  className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-purple-600"
                />
                <label htmlFor="requireKYC" className="text-sm text-gray-300">
                  Require KYC above threshold
                </label>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="autoEscrow"
                  checked={formData.rules.autoEscrowHighRisk}
                  onChange={(e) => setFormData({
                    ...formData,
                    rules: { ...formData.rules, autoEscrowHighRisk: e.target.checked }
                  })}
                  className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-purple-600"
                />
                <label htmlFor="autoEscrow" className="text-sm text-gray-300">
                  Auto-escrow high risk transactions
                </label>
              </div>
            </div>

            {formData.rules.autoEscrowHighRisk && (
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Escrow Duration (hours)
                </label>
                <input
                  type="number"
                  min="1"
                  max="168"
                  value={formData.rules.escrowDurationHours}
                  onChange={(e) => setFormData({
                    ...formData,
                    rules: { ...formData.rules, escrowDurationHours: parseInt(e.target.value) || 24 }
                  })}
                  className="w-full md:w-48 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500"
                />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Allowed Chains */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="chains" title="Allowed Chains" icon={Globe} />
        {expandedSections.has('chains') && (
          <div className="p-4 border-t border-gray-800">
            {errors.chains && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                {errors.chains}
              </div>
            )}
            <div className="grid md:grid-cols-4 gap-3">
              {CHAIN_OPTIONS.map(chain => (
                <label
                  key={chain.id}
                  className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${
                    formData.rules.allowedChainIds.includes(chain.id)
                      ? 'bg-purple-500/10 border-purple-500'
                      : 'bg-gray-800 border-gray-700 hover:border-gray-600'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={formData.rules.allowedChainIds.includes(chain.id)}
                    onChange={(e) => {
                      const newChains = e.target.checked
                        ? [...formData.rules.allowedChainIds, chain.id]
                        : formData.rules.allowedChainIds.filter(id => id !== chain.id);
                      setFormData({
                        ...formData,
                        rules: { ...formData.rules, allowedChainIds: newChains }
                      });
                    }}
                    className="w-4 h-4 rounded border-gray-700 bg-gray-800 text-purple-600"
                  />
                  <div>
                    <p className="text-sm font-medium">{chain.name}</p>
                    <p className="text-xs text-gray-500">{chain.symbol}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Whitelist / Blacklist */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <SectionHeader id="lists" title="Whitelist / Blacklist" icon={Lock} />
        {expandedSections.has('lists') && (
          <div className="p-4 border-t border-gray-800 space-y-6">
            {/* Whitelist */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Whitelisted Addresses (always approved)
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newWhitelistAddress}
                  onChange={(e) => setNewWhitelistAddress(e.target.value)}
                  placeholder="0x..."
                  className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-green-500 font-mono text-sm"
                />
                <button
                  type="button"
                  onClick={addWhitelistAddress}
                  className="px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              {formData.whitelist.length > 0 && (
                <div className="space-y-1">
                  {formData.whitelist.map(addr => (
                    <div key={addr} className="flex items-center justify-between p-2 bg-green-500/10 border border-green-500/30 rounded">
                      <code className="text-sm text-green-400">{addr}</code>
                      <button
                        type="button"
                        onClick={() => removeWhitelistAddress(addr)}
                        className="text-gray-400 hover:text-red-400"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Blacklist */}
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Blacklisted Addresses (always blocked)
              </label>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={newBlacklistAddress}
                  onChange={(e) => setNewBlacklistAddress(e.target.value)}
                  placeholder="0x..."
                  className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-red-500 font-mono text-sm"
                />
                <button
                  type="button"
                  onClick={addBlacklistAddress}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
              {formData.blacklist.length > 0 && (
                <div className="space-y-1">
                  {formData.blacklist.map(addr => (
                    <div key={addr} className="flex items-center justify-between p-2 bg-red-500/10 border border-red-500/30 rounded">
                      <code className="text-sm text-red-400">{addr}</code>
                      <button
                        type="button"
                        onClick={() => removeBlacklistAddress(addr)}
                        className="text-gray-400 hover:text-red-400"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Form Actions */}
      <div className="flex justify-end gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="px-6 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg transition-colors disabled:opacity-50"
        >
          <Save className="w-4 h-4" />
          {submitting ? 'Saving...' : isEdit ? 'Update Policy' : 'Create Policy'}
        </button>
      </div>
    </form>
  );
}
