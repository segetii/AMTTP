'use client';

/**
 * Shared Explainability Modal
 *
 * Renders ML decision explanations for flagged transactions / alerts.
 * Used by: War Room dashboard, Flagged Queue, Alert Center.
 *
 * Fetches real explanations from the explainability service (port 8009)
 * via the Next.js API route /api/explain. Falls back to local generation
 * if the service is unavailable.
 */

import React, { useEffect, useState } from 'react';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/** Fields the modal needs from the caller — pass everything available */
export interface ExplainabilityItem {
  id: string;
  address?: string;
  riskScore?: number;
  riskLevel?: string;
  reason?: string;
  // Enriched fields (from FlaggedTransaction / Alert metadata)
  hash?: string;
  from?: string;
  to?: string;
  value?: number;
  timestamp?: string;
  flags?: string[];
  patternCount?: number;
  totalTransactions?: number;
  uniqueCounterparties?: number;
}

export interface ExplainabilityData {
  riskScore: number;
  riskLevel: string;
  action: string;
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
  recommendations: string[];
  graphExplanation: string | null;
  source: 'live' | 'fallback';
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
    action: score >= 85 ? 'BLOCK' : score >= 70 ? 'ESCROW' : score >= 50 ? 'REVIEW' : 'ALLOW',
    narrative:
      `This transaction was flagged with a ${riskLevel} risk classification. ` +
      `${item.reason || 'The ML pipeline detected patterns requiring review'}. ` +
      `The GraphSAGE model analyzed the transaction's network context and XGBoost provided behavioral risk scoring.`,
    patterns,
    factors,
    typologies,
    confidence: 0.82,
    recommendations: [],
    graphExplanation: null,
    source: 'fallback' as const,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// LIVE API FETCH
// ═══════════════════════════════════════════════════════════════════════════════

async function fetchExplanation(item: ExplainabilityItem): Promise<ExplainabilityData> {
  const rawScore = item.riskScore ?? 50;
  const score = rawScore <= 1 ? rawScore * 100 : rawScore;

  // Build rich features dict from all available item fields
  const features: Record<string, unknown> = {
    risk_reason: item.reason || '',
    sender: item.address || item.from || '',
  };
  if (item.value != null) features.amount_eth = item.value;
  if (item.totalTransactions != null) features.tx_count_24h = item.totalTransactions;
  if (item.patternCount != null) features.tx_count_1h = item.patternCount;
  if (item.timestamp) {
    const hour = new Date(item.timestamp).getUTCHours();
    if (hour < 6 || hour > 22) features.unusual_hour = hour;
  }

  // Inject ML factors from the stored record (populated by enriched _persist_flagged)
  const mlf = (item as Record<string, unknown>).ml_factors as Record<string, unknown> | undefined;
  if (mlf) {
    if (mlf.risk_score != null) features.xgb_prob = mlf.risk_score;
    if (mlf.confidence != null) features.ml_confidence = mlf.confidence;
    if (mlf.risk_level) features.ml_risk_level = mlf.risk_level;
    const mlFactors = mlf.factors as Record<string, unknown> | undefined;
    if (mlFactors) {
      for (const [k, v] of Object.entries(mlFactors)) {
        features[k.toLowerCase()] = v;
      }
    }
  }

  // Inject originator data
  const orig = (item as Record<string, unknown>).originator as Record<string, unknown> | undefined;
  if (orig) {
    if (orig.entity_type === 'UNVERIFIED') features.unverified_entity = true;
    if (orig.kyc_level === 'NONE') features.kyc_required = true;
  }

  // Inject SAR / travel rule / escrow flags
  if ((item as Record<string, unknown>).requires_sar) features.sar_required = true;
  if ((item as Record<string, unknown>).requires_travel_rule) features.travel_rule_triggered = true;

  // Build graph context from network-related fields
  const graph_context: Record<string, unknown> = {};
  if (item.uniqueCounterparties != null) graph_context.out_degree = item.uniqueCounterparties;

  // Convert stored checks into rule_results the backend can use
  const storedChecks = ((item as Record<string, unknown>).checks || []) as Array<Record<string, unknown>>;
  const rule_results: Array<{ rule_id: string; rule_type?: string; triggered: boolean; details: string }> = [];

  for (const chk of storedChecks) {
    rule_results.push({
      rule_id: String(chk.service || chk.check_type || 'unknown'),
      rule_type: String(chk.check_type || chk.service || ''),
      triggered: !chk.passed,
      details: String(chk.reason || chk.service || ''),
    });
  }

  // Convert flags into additional rule_results for typology matching
  const FLAG_TO_RULE_TYPE: Record<string, string> = {
    'structur': 'STRUCTURING', 'smurfing': 'STRUCTURING', 'small txn': 'STRUCTURING',
    'layer': 'LAYERING', 'chain': 'LAYERING',
    'round_trip': 'ROUND_TRIP', 'round trip': 'ROUND_TRIP',
    'mixer': 'MIXER', 'mixing': 'MIXER', 'tumbl': 'MIXER', 'tornado': 'MIXER',
    'sanction': 'SANCTIONS', 'ofac': 'SANCTIONS',
    'dormant': 'DORMANT', 'inactive': 'DORMANT',
    'fan-out': 'FAN_OUT', 'fan_out': 'FAN_OUT', 'distribut': 'FAN_OUT',
    'fan-in': 'FAN_IN', 'fan_in': 'FAN_IN', 'aggregat': 'FAN_IN', 'consolidat': 'FAN_IN',
  };

  const allSignals = [...(item.flags || []), item.reason || ''].map(s => s.toLowerCase()).join(' ');

  // Supplement rule_results from flags (for records without stored checks)
  if (rule_results.length === 0 && item.flags && item.flags.length > 0) {
    for (const flag of item.flags) {
      const fl = flag.toLowerCase();
      // Find matching rule_type for this flag
      let ruleType: string | undefined;
      for (const [keyword, rt] of Object.entries(FLAG_TO_RULE_TYPE)) {
        if (fl.includes(keyword)) { ruleType = rt; break; }
      }
      rule_results.push({ rule_id: flag, rule_type: ruleType, triggered: true, details: flag });
    }
  }

  // Promote well-known signal keywords into features/graph_context
  // (check all flags + reason together for broader coverage)
  if (/velocity|high_velocity|rapid|cycling|burst/.test(allSignals)) features.tx_count_1h = features.tx_count_1h ?? 10;
  if (/volume|anomaly|spike/.test(allSignals)) features.amount_vs_average = features.amount_vs_average ?? 8;
  if (/dormant|inactive|reactivat/.test(allSignals)) features.dormancy_days = features.dormancy_days ?? 200;
  if (/structur|smurfing|small txn|multiple small/.test(allSignals)) {
    features.tx_count_1h = features.tx_count_1h ?? 8;
    features.avg_tx_size_eth = features.avg_tx_size_eth ?? 9.5;
  }
  if (/sanction|ofac|hmt|sdn/.test(allSignals)) graph_context.hops_to_sanctioned = graph_context.hops_to_sanctioned ?? 2;
  if (/mixer|mixing|tumbl|tornado/.test(allSignals)) {
    graph_context.hops_to_mixer = graph_context.hops_to_mixer ?? 1;
    graph_context.mixer_interaction = graph_context.mixer_interaction ?? true;
  }
  if (/layer|chain|rapid|cycling/.test(allSignals)) graph_context.out_degree = graph_context.out_degree ?? 55;
  if (/fan.?out|distribut/.test(allSignals)) {
    graph_context.out_degree = graph_context.out_degree ?? 60;
    features.unique_recipients_24h = features.unique_recipients_24h ?? 15;
  }
  if (/fan.?in|aggregat|consolidat/.test(allSignals)) {
    graph_context.in_degree = graph_context.in_degree ?? 120;
    features.unique_senders_24h = features.unique_senders_24h ?? 15;
  }
  if (/counterpart|new.?address/.test(allSignals)) graph_context.out_degree = graph_context.out_degree ?? 45;

  const payload: Record<string, unknown> = {
    risk_score: rawScore <= 1 ? rawScore : rawScore / 100,
    features,
  };
  if (Object.keys(graph_context).length > 0) payload.graph_context = graph_context;
  if (rule_results.length > 0) payload.rule_results = rule_results;

  const res = await fetch('/explain/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) throw new Error(`API ${res.status}`);

  const data = await res.json();
  const explanation = data.explanation || data;

  const riskLevel = item.riskLevel?.toUpperCase() || getRiskLevel(score);

  // Map backend factors → UI factors
  const factors = (explanation.factors || []).map((f: { factor_id?: string; reason?: string; contribution?: number; detail?: string; impact?: string; value?: number }) => ({
    name: (f.factor_id || '').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    value: typeof f.value === 'number' ? f.value : 0,
    impact: f.contribution ?? 0.1,
    description: f.reason || f.detail || '',
  }));

  // Map backend typology_matches → UI patterns + typology labels
  const typologyMatches = explanation.typology_matches || [];
  const patterns = typologyMatches.map((t: { typology?: string; description?: string; confidence?: number }) => ({
    name: t.typology || 'unknown',
    description: t.description || '',
    severity: (t.confidence ?? 0) >= 0.8 ? 'critical' : (t.confidence ?? 0) >= 0.6 ? 'high' : 'medium',
    confidence: t.confidence ?? 0.5,
  }));
  const typologies = typologyMatches.map((t: { typology?: string }) =>
    (t.typology || '').replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
  );

  // Also convert top-level factors with impact into patterns if no typology matches
  if (patterns.length === 0 && factors.length > 0) {
    for (const f of factors.slice(0, 3)) {
      if (f.impact >= 0.15) {
        patterns.push({
          name: f.name.toLowerCase().replace(/ /g, '_'),
          description: f.description,
          severity: f.impact >= 0.3 ? 'high' : 'medium',
          confidence: Math.min(f.impact * 3, 0.95),
        });
      }
    }
  }

  return {
    riskScore: score,
    riskLevel,
    action: explanation.action || 'REVIEW',
    narrative: explanation.summary || `Risk score ${Math.round(score)} — ${riskLevel} risk.`,
    patterns,
    factors,
    typologies,
    confidence: explanation.confidence ?? 0.5,
    recommendations: explanation.recommendations || [],
    graphExplanation: explanation.graph_explanation || null,
    source: 'live',
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// MODAL COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ExplainabilityModal({ item, onClose, onInvestigate }: ExplainabilityModalProps) {
  const [explanation, setExplanation] = useState<ExplainabilityData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetchExplanation(item)
      .then((data) => { if (!cancelled) setExplanation(data); })
      .catch(() => { if (!cancelled) setExplanation(buildExplanation(item)); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [item]);

  const rc = getRiskColor(explanation?.riskLevel || getRiskLevel(item.riskScore ?? 50));

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-background rounded-2xl border border-borderSubtle w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3.5 bg-surface border-b border-borderSubtle flex items-center gap-3">
          <div className={`p-2 rounded-lg ${rc.bgSoft}`}>
            <svg className={`w-6 h-6 ${rc.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-bold text-text">Decision Explainability</h2>
            <p className="text-sm text-mutedText font-mono truncate">{item.address || item.id}</p>
          </div>
          <div className={`px-3 py-1 rounded-full ${rc.bgSoft} border ${rc.border}`}>
            <span className={`text-sm font-bold ${rc.text}`}>{explanation?.riskLevel || '...'} RISK</span>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-slate-700 rounded-lg transition-colors">
            <svg className="w-5 h-5 text-mutedText" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-10 gap-3">
              <div className="w-8 h-8 border-2 border-slate-500 border-t-indigo-500 rounded-full animate-spin" />
              <p className="text-sm text-mutedText">Fetching explanation from XAI service…</p>
            </div>
          ) : explanation ? (
            <>
              {/* Risk Score + Source row */}
              <div className="flex items-center gap-4">
                <div className="relative w-20 h-20 flex-shrink-0">
                  <svg className="w-20 h-20 -rotate-90">
                    <circle cx="40" cy="40" r="33" stroke="currentColor" strokeWidth="7" fill="none" className="text-slate-700" />
                    <circle
                      cx="40" cy="40" r="33"
                      stroke="currentColor"
                      strokeWidth="7"
                      fill="none"
                      strokeDasharray={`${(explanation.riskScore / 100) * 207.3} 207.3`}
                      className={rc.text}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className={`text-xl font-bold ${rc.text}`}>{Math.round(explanation.riskScore)}</span>
                  </div>
                </div>
                <div className="flex-1 min-w-0 space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2.5 py-0.5 rounded text-xs font-medium ${
                      explanation.source === 'live'
                        ? 'bg-green-500/15 text-green-400 border border-green-500/30'
                        : 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30'
                    }`}>
                      {explanation.source === 'live' ? 'Live XAI' : 'Fallback'}
                    </span>
                    {explanation.action && (
                      <span className={`px-2.5 py-0.5 rounded text-xs font-bold ${
                        explanation.action === 'BLOCK' ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                        : explanation.action === 'ESCROW' ? 'bg-orange-500/15 text-orange-400 border border-orange-500/30'
                        : explanation.action === 'REVIEW' ? 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30'
                        : 'bg-green-500/15 text-green-400 border border-green-500/30'
                      }`}>
                        {explanation.action}
                      </span>
                    )}
                    <span className="text-xs text-mutedText">Confidence: {Math.round(explanation.confidence * 100)}%</span>
                  </div>
                  <p className="text-sm text-slate-300 leading-snug">{explanation.narrative}</p>
                </div>
              </div>

              {/* Graph Explanation */}
              {explanation.graphExplanation && (
                <div className="bg-surface rounded-lg px-3.5 py-2.5 border border-borderSubtle">
                  <p className="text-sm text-slate-300"><span className="font-semibold text-mutedText uppercase tracking-wide mr-1.5">Graph:</span>{explanation.graphExplanation}</p>
                </div>
              )}

              {/* Patterns */}
              {explanation.patterns.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-mutedText uppercase tracking-wide mb-2">Detected Patterns</h3>
                  <div className="space-y-2">
                    {explanation.patterns.map((p, i) => (
                      <div key={i} className={`border rounded-lg px-3.5 py-2.5 ${getSeverityColor(p.severity)}`}>
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold uppercase">{p.name.replace(/_/g, ' ')}</span>
                          <span className="text-xs opacity-75">{Math.round(p.confidence * 100)}%</span>
                        </div>
                        <p className="text-sm opacity-90 mt-0.5">{p.description}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Contributing Factors */}
              {explanation.factors.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-mutedText uppercase tracking-wide mb-2">Contributing Factors</h3>
                  <div className="space-y-2">
                    {explanation.factors.map((f, i) => (
                      <div key={i} className="flex items-center gap-2.5">
                        <span className="w-32 text-sm text-slate-300 truncate flex-shrink-0" title={f.description}>{f.name}</span>
                        <div className="flex-1 h-5 bg-surface rounded relative">
                          <div
                            className={`h-5 rounded ${f.impact > 0.2 ? 'bg-red-500/70' : 'bg-blue-500/70'}`}
                            style={{ width: `${Math.min(f.impact * 100 * 3, 100)}%` }}
                          />
                        </div>
                        <span className={`text-sm font-mono w-12 text-right flex-shrink-0 ${f.impact > 0.2 ? 'text-red-400' : 'text-blue-400'}`}>
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
                  <h3 className="text-xs font-semibold text-mutedText uppercase tracking-wide mb-2">AML Typologies</h3>
                  <div className="flex flex-wrap gap-2">
                    {explanation.typologies.map((t, i) => (
                      <span key={i} className="px-2.5 py-1 bg-red-500/15 border border-red-500/30 rounded-lg text-sm text-red-400">
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Recommendations */}
              {explanation.recommendations.length > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-mutedText uppercase tracking-wide mb-1.5">Recommendations</h3>
                  <ul className="space-y-1">
                    {explanation.recommendations.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                        <span className="text-indigo-400 mt-0.5">→</span>
                        <span>{r}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8 text-mutedText">
              <p className="text-sm">Unable to load explanation data.</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3.5 bg-surface border-t border-borderSubtle flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm text-mutedText hover:text-slate-200 transition-colors">
            Close
          </button>
          {onInvestigate && (
            <button
              onClick={onInvestigate}
              className="px-4 py-2 text-sm bg-indigo-600 hover:bg-indigo-700 text-text rounded-lg transition-colors flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Investigate
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
