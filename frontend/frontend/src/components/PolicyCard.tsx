'use client';

import {
  Shield, Star, ToggleLeft, ToggleRight, Edit, Trash2,
  CheckCircle, XCircle, Clock, AlertTriangle, Settings,
  ChevronRight, Lock, Unlock
} from 'lucide-react';
import type { Policy, RiskAction } from '@/types/policy';

interface PolicyCardProps {
  policy: Policy;
  onEdit: () => void;
  onToggleStatus: () => void;
  onSetDefault: () => void;
  onDelete: () => void;
}

export function PolicyCard({ policy, onEdit, onToggleStatus, onSetDefault, onDelete }: PolicyCardProps) {
  const formatNumber = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', { 
      day: '2-digit', 
      month: 'short', 
      year: 'numeric' 
    });
  };

  const getActionBadgeClass = (action: RiskAction) => {
    switch (action) {
      case 'APPROVE': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'REVIEW': return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
      case 'ESCROW': return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
      case 'BLOCK': return 'bg-red-500/20 text-red-400 border-red-500/30';
    }
  };

  const successRate = policy.stats.totalTransactions > 0
    ? ((policy.stats.approvedCount / policy.stats.totalTransactions) * 100).toFixed(1)
    : '0';

  return (
    <div 
      className={`bg-gray-900 border rounded-xl overflow-hidden transition-all hover:border-purple-500/50 ${
        policy.isDefault ? 'border-purple-500' : 'border-gray-800'
      }`}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${policy.isActive ? 'bg-purple-500/20' : 'bg-gray-700/50'}`}>
              <Shield className={`w-5 h-5 ${policy.isActive ? 'text-purple-400' : 'text-gray-500'}`} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{policy.name}</h3>
                {policy.isDefault && (
                  <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 text-xs rounded-full flex items-center gap-1">
                    <Star className="w-3 h-3" />
                    Default
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-500 mt-0.5">{policy.description}</p>
            </div>
          </div>
          
          {/* Status Toggle */}
          <button
            onClick={(e) => { e.stopPropagation(); onToggleStatus(); }}
            className="p-1 hover:bg-gray-800 rounded transition-colors"
            title={policy.isActive ? 'Deactivate' : 'Activate'}
          >
            {policy.isActive ? (
              <ToggleRight className="w-6 h-6 text-green-400" />
            ) : (
              <ToggleLeft className="w-6 h-6 text-gray-500" />
            )}
          </button>
        </div>
      </div>

      {/* Action Rules */}
      <div className="p-4 border-b border-gray-800">
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Risk Actions</p>
        <div className="grid grid-cols-2 gap-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Low Risk:</span>
            <span className={`px-2 py-0.5 text-xs rounded border ${getActionBadgeClass(policy.actions.onLowRisk)}`}>
              {policy.actions.onLowRisk}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Medium:</span>
            <span className={`px-2 py-0.5 text-xs rounded border ${getActionBadgeClass(policy.actions.onMediumRisk)}`}>
              {policy.actions.onMediumRisk}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">High Risk:</span>
            <span className={`px-2 py-0.5 text-xs rounded border ${getActionBadgeClass(policy.actions.onHighRisk)}`}>
              {policy.actions.onHighRisk}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Critical:</span>
            <span className={`px-2 py-0.5 text-xs rounded border ${getActionBadgeClass(policy.actions.onCriticalRisk)}`}>
              {policy.actions.onCriticalRisk}
            </span>
          </div>
        </div>
      </div>

      {/* Thresholds */}
      <div className="p-4 border-b border-gray-800">
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-3">Risk Thresholds</p>
        <div className="relative h-3 bg-gray-800 rounded-full overflow-hidden">
          <div 
            className="absolute h-full bg-green-500/60" 
            style={{ left: 0, width: `${policy.thresholds.lowRiskMax}%` }}
          />
          <div 
            className="absolute h-full bg-yellow-500/60" 
            style={{ left: `${policy.thresholds.lowRiskMax}%`, width: `${policy.thresholds.mediumRiskMax - policy.thresholds.lowRiskMax}%` }}
          />
          <div 
            className="absolute h-full bg-orange-500/60" 
            style={{ left: `${policy.thresholds.mediumRiskMax}%`, width: `${policy.thresholds.highRiskMax - policy.thresholds.mediumRiskMax}%` }}
          />
          <div 
            className="absolute h-full bg-red-500/60" 
            style={{ left: `${policy.thresholds.highRiskMax}%`, right: 0 }}
          />
        </div>
        <div className="flex justify-between mt-2 text-xs text-gray-500">
          <span>0</span>
          <span>{policy.thresholds.lowRiskMax}</span>
          <span>{policy.thresholds.mediumRiskMax}</span>
          <span>{policy.thresholds.highRiskMax}</span>
          <span>100</span>
        </div>
      </div>

      {/* Stats */}
      <div className="p-4 border-b border-gray-800">
        <div className="grid grid-cols-4 gap-2 text-center">
          <div>
            <p className="text-lg font-bold text-green-400">{formatNumber(policy.stats.approvedCount)}</p>
            <p className="text-xs text-gray-500">Approved</p>
          </div>
          <div>
            <p className="text-lg font-bold text-yellow-400">{formatNumber(policy.stats.reviewedCount)}</p>
            <p className="text-xs text-gray-500">Reviewed</p>
          </div>
          <div>
            <p className="text-lg font-bold text-orange-400">{formatNumber(policy.stats.escrowedCount)}</p>
            <p className="text-xs text-gray-500">Escrowed</p>
          </div>
          <div>
            <p className="text-lg font-bold text-red-400">{formatNumber(policy.stats.blockedCount)}</p>
            <p className="text-xs text-gray-500">Blocked</p>
          </div>
        </div>
      </div>

      {/* Rules Summary */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex flex-wrap gap-2">
          {policy.rules.blockSanctionedAddresses && (
            <span className="px-2 py-1 bg-red-500/10 text-red-400 text-xs rounded-full flex items-center gap-1">
              <Lock className="w-3 h-3" />
              Block Sanctioned
            </span>
          )}
          {policy.rules.requireKYCAboveThreshold && (
            <span className="px-2 py-1 bg-blue-500/10 text-blue-400 text-xs rounded-full flex items-center gap-1">
              <CheckCircle className="w-3 h-3" />
              KYC Required
            </span>
          )}
          {policy.rules.autoEscrowHighRisk && (
            <span className="px-2 py-1 bg-orange-500/10 text-orange-400 text-xs rounded-full flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Auto-Escrow
            </span>
          )}
          <span className="px-2 py-1 bg-purple-500/10 text-purple-400 text-xs rounded-full">
            {policy.rules.allowedChainIds.length} chains
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 flex items-center justify-between">
        <div className="text-xs text-gray-500">
          Updated {formatDate(policy.updatedAt)}
        </div>
        
        <div className="flex items-center gap-1">
          {!policy.isDefault && (
            <button
              onClick={(e) => { e.stopPropagation(); onSetDefault(); }}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-purple-400"
              title="Set as default"
            >
              <Star className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-blue-400"
            title="Edit policy"
          >
            <Edit className="w-4 h-4" />
          </button>
          {!policy.isDefault && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-red-400"
              title="Delete policy"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
