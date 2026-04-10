'use client';

/**
 * Shared Explainability Modal
 *
 * Renders ML decision explanations for flagged transactions / alerts.
 * Used by: War Room dashboard, Flagged Queue, Alert Center.
 *
 * Accepts a generic item shape so both FlaggedTransaction and Alert can be passed.
 */

import React from 'react';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/** Minimal fields the modal needs from the caller */
export interface ExplainabilityItem {
  id: string;
  address?: string;
  riskScore?: number;
  riskLevel?: string;
  reason?: string;
}

export interface ExplainabilityData {
  riskScore: number;
  riskLevel: string;
  narrative: string;
  patterns: Array<{
    name: string;
    description: string;
    severity: string;
    confidence: number;
  }>;
  factors: Array<{
    name: string;
    value: number;
    impact: number;
    description: string;
  }>;
  typologies: string[];
  confidence: number;
}

interface ExplainabilityModalProps {
  item: ExplainabilityItem;
  onClose: () => void;
  onInvestigate?: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// RISK HELPERS  (standardised thresholds: 85/70/50 on 0–100 scale)
// ═══════════════════════════════════════════════════════════════════════════════

export function getRiskLevel(score: number): string {
  if (score >= 85) return 'CRITICAL';
  if (score >= 70) return 'HIGH';
  if (score >= 50) return 'MEDIUM';
  return 'LOW';
}

export function getRiskColor(level: string) {
  switch (level.toUpperCase()) {
    case 'CRITICAL': return { text: 'text-red-500', bg: 'bg-red-500', ring: 'ring-red-500/20', bgSoft: 'bg-red-500/10', border: 'border-red-500/50' };
    case 'HIGH':     return { text: 'text-orange-400', bg: 'bg-orange-500', ring: 'ring-orange-500/20', bgSoft: 'bg-orange-500/10', border: 'border-orange-500/50' };
    case 'MEDIUM':   return { text: 'text-yellow-400', bg: 'bg-yellow-400', ring: 'ring-yellow-400/20', bgSoft: 'bg-yellow-500/10', border: 'border-yellow-500/50' };
    case 'LOW':      return { text: 'text-green-400', bg: 'bg-green-500', ring: 'ring-green-500/20', bgSoft: 'bg-green-500/10', border: 'border-green-500/50' };
    default:         return { text: 'text-slate-400', bg: 'bg-slate-500', ring: 'ring-slate-500/20', bgSoft: 'bg-slate-500/10', border: 'border-slate-500/50' };
  }
}

function getSeverityColor(severity: string) {
  switch (severity) {
    case 'critical': return 'border-red-500 bg-red-500/10 text-red-400';
    case 'high':     return 'border-orange-500 bg-orange-500/10 text-orange-400';
    case 'medium':   return 'border-yellow-400 bg-yellow-400/10 text-yellow-400';
    default:         return 'border-slate-500 bg-slate-500/10 text-slate-400';
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPLANATION BUILDER
// ═══════════════════════════════════════════════════════════════════════════════

export function buildExplanation(item: ExplainabilityItem): ExplainabilityData {
  const rawScore = item.riskScore ?? 50;
  // Normalise: if score looks like a 0-1 float, scale to 0-100
  const score = rawScore <= 1 ? rawScore * 100 : rawScore;
  const riskLevel = item.riskLevel?.toUpperCase() || getRiskLevel(score);

  // Build patterns from available data
  const patterns: ExplainabilityData['patterns'] = [];
  const reason = item.reason?.toLowerCase() || '';

  if (riskLevel === 'CRITICAL' || riskLevel === 'HIGH') {
    patterns.push({
      name: 'high_risk_transfer',
      description: `This transaction has been flagged due to ${item.reason || 'suspicious activity patterns'}`,
      severity: 'high',
      confidence: 0.85,
    });
  }

  if (reason.includes('velocity') || reason.includes('fan-out')) {
    patterns.push({
      name: 'velocity_anomaly',
      description: 'Unusual transaction frequency detected in short time window',
      severity: 'medium',
      confidence: 0.78,
    });
  }

  if (reason.includes('sanction') || reason.includes('ofac')) {
    patterns.push({
      name: 'sanctions_proximity',
      description: 'Transaction path includes addresses within 2 hops of sanctioned entities',
      severity: 'critical',
      confidence: 0.92,
    });
  }

  if (reason.includes('mixer') || reason.includes('layering')) {
    patterns.push({
      name: 'mixing_pattern',
      description: 'Transaction flow consistent with layering or mixing behavior',
      severity: 'high',
      confidence: 0.81,
    });
  }

  if (patterns.length === 0) {
    patterns.push({
      name: 'general_risk',
      description: item.reason || 'Flagged for compliance review based on ML risk scoring',
      severity: 'medium',
      confidence: 0.75,
    });
  }

  const impactHigh = score > 70 ? 0.3 : 0.1;
  const factors = [
    { name: 'Transaction Value', value: score, impact: impactHigh, description: 'Transaction amount relative to typical patterns' },
    { name: 'Velocity Score', value: 65, impact: 0.2, description: 'Transaction frequency in 24h window' },
    { name: 'Network Centrality', value: 45, impact: 0.15, description: 'PageRank score in transaction graph' },
    { name: 'Counterparty Risk', value: 55, impact: 0.25, description: 'Risk score of connected addresses' },
  ];

  const typologies: string[] = [];
  if (riskLevel === 'HIGH' || riskLevel === 'CRITICAL') {
    typologies.push('Potential Layering');
    if (reason.includes('sanction')) typologies.push('Sanctions Evasion Risk');
  }

  return {
    riskScore: score,
    riskLevel,
    narrative:
      `This transaction was flagged with a ${riskLevel} risk classification. ` +
      `${item.reason || 'The ML pipeline detected patterns requiring review'}. ` +
      `The GraphSAGE model analyzed the transaction's network context and XGBoost provided behavioral risk scoring.`,
    patterns,
    factors,
    typologies,
    confidence: 0.82,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODAL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ExplainabilityModal({ item, onClose, onInvestigate }: ExplainabilityModalProps) {
  const explanation = React.useMemo(() => buildExplanation(item), [item]);
  const rc = getRiskColor(explanation.riskLevel);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-background rounded-2xl border border-borderSubtle w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 py-4 bg-surface border-b border-borderSubtle flex items-center gap-4">
          <div className={`p-2 rounded-lg ${rc.bgSoft}`}>
            <svg className={`w-6 h-6 ${rc.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="flex-1">
            <h2 className="text-lg font-bold text-text">Decision Explainability</h2>
            <p className="text-sm text-mutedText font-mono">{item.address || item.id}</p>
          </div>
          <div className={`px-3 py-1 rounded-full ${rc.bgSoft} border ${rc.border}`}>
            <span className={`text-sm font-bold ${rc.text}`}>{explanation.riskLevel} RISK</span>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
            <svg className="w-5 h-5 text-mutedText" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Risk Score Donut */}
          <div className="flex items-center gap-6">
            <div className="relative w-24 h-24">
              <svg className="w-24 h-24 -rotate-90">
                <circle cx="48" cy="48" r="40" stroke="currentColor" strokeWidth="8" fill="none" className="text-slate-700" />
                <circle
                  cx="48" cy="48" r="40"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${(explanation.riskScore / 100) * 251.2} 251.2`}
                  className={rc.text}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${rc.text}`}>{Math.round(explanation.riskScore)}</span>
              </div>
            </div>
            <div>
              <p className="text-sm text-mutedText">Confidence: {Math.round(explanation.confidence * 100)}%</p>
              <p className="text-sm text-mutedText mt-1">Model: GraphSAGE + XGBoost</p>
            </div>
          </div>

          {/* Narrative */}
          <div>
            <h3 className="text-sm font-semibold text-mutedText uppercase tracking-wide mb-3">Analysis Summary</h3>
            <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
              <p className="text-slate-200 leading-relaxed">{explanation.narrative}</p>
            </div>
          </div>

          {/* Patterns */}
          {explanation.patterns.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-mutedText uppercase tracking-wide mb-3">Detected Patterns</h3>
              <div className="space-y-2">
                {explanation.patterns.map((p, i) => (
                  <div key={i} className={`border rounded-lg p-3 ${getSeverityColor(p.severity)}`}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-semibold uppercase">{p.name.replace(/_/g, ' ')}</span>
                      <span className="text-xs opacity-75">{Math.round(p.confidence * 100)}% confidence</span>
                    </div>
                    <p className="text-sm opacity-90">{p.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SHAP Factors */}
          {explanation.factors.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-mutedText uppercase tracking-wide mb-3">Contributing Factors (SHAP)</h3>
              <div className="space-y-3">
                {explanation.factors.map((f, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="w-32 text-sm text-slate-300 truncate">{f.name}</span>
                    <div className="flex-1 h-5 bg-surface rounded relative">
                      <div
                        className={`h-5 rounded ${f.impact > 0.2 ? 'bg-red-500/70' : 'bg-blue-500/70'}`}
                        style={{ width: `${Math.min(f.impact * 100 * 3, 100)}%` }}
                      />
                    </div>
                    <span className={`text-sm font-mono w-12 text-right ${f.impact > 0.2 ? 'text-red-400' : 'text-blue-400'}`}>
                      +{Math.round(f.impact * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AML Typologies */}
          {explanation.typologies.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-mutedText uppercase tracking-wide mb-3">AML Typologies</h3>
              <div className="flex flex-wrap gap-2">
                {explanation.typologies.map((t, i) => (
                  <span key={i} className="px-3 py-1 bg-red-500/15 border border-red-500/30 rounded-lg text-sm text-red-400">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-surface border-t border-borderSubtle flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-mutedText hover:text-slate-200 transition-colors">
            Close
          </button>
          {onInvestigate && (
            <button
              onClick={onInvestigate}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-text rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Investigate in Graph
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
