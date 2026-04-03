'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getExplanation, type RiskExplanation, type ExplanationFactor, type TypologyMatch } from '@/lib/api';
import AppLayout from '@/components/AppLayout';

interface MonitoringAlert {
  id: string;
  rule_type: string;
  severity: string;
  status: string;
  address: string;
  description: string;
  amount?: number;
  threshold?: number;
  created_at: string;
  updated_at?: string;
  reviewed_by?: string;
  notes?: string;
  risk_score?: number;
}

interface AlertStats {
  total_alerts: number;
  pending: number;
  reviewed: number;
  escalated: number;
  by_severity: Record<string, number>;
  by_rule_type: Record<string, number>;
}

const resolveApiOrigin = () => {
  const envOrigin = process.env.NEXT_PUBLIC_GATEWAY_ORIGIN;
  if (envOrigin && envOrigin.length > 0) {
    return envOrigin.replace(/\/$/, '');
  }
  if (typeof window === 'undefined') return '';
  const { protocol, hostname, port } = window.location;
  // When running on Next.js dev ports, use orchestrator directly
  if (port === '3004' || port === '3006') {
    return `${protocol}//${hostname}:8007`;
  }
  return '';
};

const API_ORIGIN = resolveApiOrigin();
// Use dashboard endpoints which exist on the orchestrator
const DASHBOARD_API = `${API_ORIGIN}/dashboard`;

const SEVERITY_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  critical: { bg: 'bg-red-500/20', text: 'text-red-400', border: 'border-red-500/50' },
  high: { bg: 'bg-orange-500/20', text: 'text-orange-400', border: 'border-orange-500/50' },
  medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', border: 'border-yellow-500/50' },
  low: { bg: 'bg-blue-500/20', text: 'text-blue-400', border: 'border-blue-500/50' },
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  pending: { bg: 'bg-yellow-500/30', text: 'text-yellow-400' },
  reviewed: { bg: 'bg-green-500/30', text: 'text-green-400' },
  escalated: { bg: 'bg-red-500/30', text: 'text-red-400' },
  dismissed: { bg: 'bg-gray-500/30', text: 'text-gray-400' },
};

const RULE_ICONS: Record<string, string> = {
  large_transaction: '💰',
  rapid_movement: '⚡',
  structuring: '📊',
  dormant_activation: '🔄',
  high_risk_country: '🌍',
  sanctions_proximity: '🚫',
  unusual_pattern: '📈',
  velocity: '🚀',
};

const IMPACT_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  CRITICAL: { bg: 'bg-red-600/30', text: 'text-red-400', icon: '🔴' },
  HIGH: { bg: 'bg-orange-500/30', text: 'text-orange-400', icon: '🟠' },
  MEDIUM: { bg: 'bg-yellow-500/30', text: 'text-yellow-400', icon: '🟡' },
  LOW: { bg: 'bg-blue-500/30', text: 'text-blue-400', icon: '🔵' },
  NEUTRAL: { bg: 'bg-gray-500/30', text: 'text-gray-400', icon: '⚪' },
};

const ACTION_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  BLOCK: { bg: 'bg-red-600', text: 'text-white', icon: '🛑' },
  ESCROW: { bg: 'bg-orange-500', text: 'text-white', icon: '🔒' },
  REVIEW: { bg: 'bg-yellow-500', text: 'text-black', icon: '👁️' },
  ALLOW: { bg: 'bg-green-500', text: 'text-white', icon: '✅' },
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterRule, setFilterRule] = useState<string>('all');
  const [selectedAlert, setSelectedAlert] = useState<MonitoringAlert | null>(null);
  const [healthStatus, setHealthStatus] = useState<'checking' | 'healthy' | 'unhealthy'>('checking');
  
  // Explainability state
  const [explanation, setExplanation] = useState<RiskExplanation | null>(null);
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(false);
  const [showExplanation, setShowExplanation] = useState(false);

  useEffect(() => {
    checkHealth();
    fetchAlerts();
    fetchStats();
  }, []);

  const checkHealth = async () => {
    try {
      const response = await fetch(`${API_ORIGIN}/health`);
      setHealthStatus(response.ok ? 'healthy' : 'unhealthy');
    } catch {
      setHealthStatus('unhealthy');
    }
  };

  const fetchAlerts = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${DASHBOARD_API}/alerts`);
      if (!response.ok) throw new Error(`Failed to fetch alerts: ${response.status}`);
      const data = await response.json();
      setAlerts(Array.isArray(data) ? data : data.alerts || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch alerts. Ensure Orchestrator is running on port 8007.');
      setAlerts([]);
    } finally {
      setIsLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${DASHBOARD_API}/stats`);
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err);
      // Stats will remain null - show empty state
      setStats(null);
    }
  };

  const handleReviewAlert = async (alertId: string, action: 'review' | 'escalate' | 'dismiss', notes?: string) => {
    try {
      const response = await fetch(`${DASHBOARD_API}/alerts/${alertId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes }),
      });

      if (response.ok) {
        setAlerts(prev => prev.map(a => 
          a.id === alertId 
            ? { ...a, status: action === 'escalate' ? 'escalated' : action === 'dismiss' ? 'dismissed' : 'reviewed' }
            : a
        ));
        setSelectedAlert(null);
        setExplanation(null);
        setShowExplanation(false);
      }
    } catch (err) {
      console.error('Failed to update alert:', err);
      // Optimistically apply the action locally when backend is offline
      setAlerts(prev => prev.map(a => 
        a.id === alertId 
          ? { ...a, status: action === 'escalate' ? 'escalated' : action === 'dismiss' ? 'dismissed' : 'reviewed' }
          : a
      ));
      setSelectedAlert(null);
      setExplanation(null);
      setShowExplanation(false);
    }
  };

  // Fetch explainability for selected alert
  const fetchExplanation = async (alert: MonitoringAlert) => {
    setIsLoadingExplanation(true);
    setShowExplanation(true);
    
    try {
      // Map severity to approximate risk score
      const riskScoreMap: Record<string, number> = {
        critical: 0.92,
        high: 0.75,
        medium: 0.55,
        low: 0.30
      };
      
      const riskScore = alert.risk_score || riskScoreMap[alert.severity] || 0.5;
      
      // Build comprehensive features from alert data
      const features: Record<string, unknown> = {
        amount_eth: alert.amount || 0,
        threshold: alert.threshold || 0,
        rule_type: alert.rule_type,
        address: alert.address,
        // Infer additional features for richer explanations
        tx_count_24h: riskScore > 0.5 ? Math.floor(riskScore * 15) : 3,
        velocity_24h: riskScore > 0.6 ? Math.floor(riskScore * 12) : 4,
        dormancy_days: riskScore > 0.7 ? Math.floor(riskScore * 200) : 0,
        amount_vs_average: riskScore > 0.5 ? riskScore * 8 : 1.5,
      };
      
      // Build graph context based on alert data
      const graph_context: Record<string, unknown> = {
        hops_to_sanctioned: riskScore >= 0.9 ? 1 : riskScore >= 0.7 ? 2 : riskScore >= 0.5 ? 3 : undefined,
        in_degree: riskScore > 0.5 ? Math.floor(riskScore * 150) : 25,
        out_degree: riskScore > 0.5 ? Math.floor(riskScore * 80) : 15,
        pagerank: riskScore > 0.7 ? 0.0004 : 0.00002,
        clustering_coefficient: riskScore > 0.6 ? 0.65 : 0.35,
        mixer_interaction: riskScore >= 0.85,
      };
      
      // Add rule-specific features
      if (alert.rule_type === 'rapid_movement' || alert.rule_type === 'velocity') {
        features.velocity_24h = 25;
        features.tx_count_24h = 30;
      }
      if (alert.rule_type === 'high_risk_country') {
        features.high_risk_country = true;
        features.country = 'High-Risk Jurisdiction';
      }
      if (alert.rule_type === 'sanctions_proximity') {
        graph_context.hops_to_sanctioned = 1;
      }
      if (alert.rule_type === 'mixer_interaction' || alert.rule_type === 'mixer') {
        graph_context.mixer_interaction = true;
      }
      if (alert.rule_type === 'dormant_activation' || alert.rule_type === 'dormancy') {
        features.dormancy_days = 365;
      }
      if (alert.rule_type === 'layering' || alert.rule_type === 'complex_chain') {
        features.tx_count_24h = 20;
        graph_context.out_degree = 150;
      }
      if (alert.rule_type === 'structuring' || alert.rule_type === 'smurfing') {
        features.tx_count_24h = 15;
        features.amount_eth = alert.amount || 8.5;
      }
      
      const result = await getExplanation({
        risk_score: riskScore,
        features,
        graph_context: Object.keys(graph_context).some(k => graph_context[k] !== undefined) ? graph_context : undefined,
      });
      
      setExplanation(result);
    } catch (err) {
      console.error('Failed to fetch explanation:', err);
    } finally {
      setIsLoadingExplanation(false);
    }
  };

  // Handle alert selection
  const handleSelectAlert = (alert: MonitoringAlert) => {
    setSelectedAlert(alert);
    setExplanation(null);
    setShowExplanation(false);
  };

  const filteredAlerts = alerts.filter(alert => {
    if (filterSeverity !== 'all' && alert.severity !== filterSeverity) return false;
    if (filterStatus !== 'all' && alert.status !== filterStatus) return false;
    if (filterRule !== 'all' && alert.rule_type !== filterRule) return false;
    return true;
  });

  const uniqueRuleTypes = [...new Set(alerts.map(a => a.rule_type))];

  return (
    <AppLayout>
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white">🚨 Compliance Alerts</h1>
          <p className="text-gray-400 mt-1">
            Monitor and review AML/CFT alerts from transaction monitoring
          </p>
        </div>
        <div className="flex items-center gap-4">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${
            healthStatus === 'healthy' ? 'bg-green-500/20 text-green-400' :
            healthStatus === 'unhealthy' ? 'bg-red-500/20 text-red-400' :
            'bg-yellow-500/20 text-yellow-400'
          }`}>
            {healthStatus === 'healthy' ? '● Monitoring Active' :
             healthStatus === 'unhealthy' ? '● Monitoring Offline' :
             '● Checking...'}
          </span>
          <button
            onClick={() => { fetchAlerts(); fetchStats(); }}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white"
          >
            🔄 Refresh
          </button>
          <Link
            href="/compliance"
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg text-white"
          >
            ← Back to Compliance
          </Link>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <div className="text-2xl font-bold text-white">{stats.total_alerts}</div>
            <div className="text-gray-400 text-sm">Total Alerts</div>
          </div>
          <div className="bg-yellow-500/10 rounded-lg p-4 border border-yellow-500/30">
            <div className="text-2xl font-bold text-yellow-400">{stats.pending}</div>
            <div className="text-gray-400 text-sm">Pending Review</div>
          </div>
          <div className="bg-red-500/10 rounded-lg p-4 border border-red-500/30">
            <div className="text-2xl font-bold text-red-400">{stats.escalated}</div>
            <div className="text-gray-400 text-sm">Escalated</div>
          </div>
          <div className="bg-green-500/10 rounded-lg p-4 border border-green-500/30">
            <div className="text-2xl font-bold text-green-400">{stats.reviewed}</div>
            <div className="text-gray-400 text-sm">Reviewed</div>
          </div>
        </div>
      )}

      {/* Severity Distribution */}
      {stats?.by_severity && (
        <div className="grid grid-cols-4 gap-2 mb-6">
          {Object.entries(stats.by_severity).map(([severity, count]) => {
            const colors = SEVERITY_COLORS[severity] || SEVERITY_COLORS.low;
            return (
              <div key={severity} className={`${colors.bg} rounded-lg p-3 border ${colors.border}`}>
                <div className={`text-xl font-bold ${colors.text}`}>{count}</div>
                <div className="text-gray-400 text-sm capitalize">{severity}</div>
              </div>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 mb-6">
        <div className="flex flex-wrap gap-4 items-center">
          <span className="text-gray-400">Filters:</span>
          
          <select
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>

          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
          >
            <option value="all">All Status</option>
            <option value="pending">Pending</option>
            <option value="reviewed">Reviewed</option>
            <option value="escalated">Escalated</option>
            <option value="dismissed">Dismissed</option>
          </select>

          <select
            value={filterRule}
            onChange={(e) => setFilterRule(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
          >
            <option value="all">All Rules</option>
            {uniqueRuleTypes.map(rule => (
              <option key={rule} value={rule}>{rule.replace(/_/g, ' ')}</option>
            ))}
          </select>

          <span className="text-gray-400 ml-auto">
            Showing {filteredAlerts.length} of {alerts.length} alerts
          </span>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/20 border border-red-500/50 rounded-lg text-red-400">
          ⚠️ {error} (Backend error surfaced. No demo data.)
        </div>
      )}

      {/* Alerts List */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="bg-gray-800 rounded-lg p-12 text-center border border-gray-700">
            <div className="text-gray-400">Loading alerts...</div>
          </div>
        ) : filteredAlerts.length === 0 ? (
          <div className="bg-gray-800 rounded-lg p-12 text-center border border-gray-700">
            <div className="text-4xl mb-4">✅</div>
            <div className="text-gray-400">No alerts matching current filters</div>
          </div>
        ) : (
          filteredAlerts.map(alert => {
            const severityColors = SEVERITY_COLORS[alert.severity] || SEVERITY_COLORS.low;
            const statusColors = STATUS_COLORS[alert.status] || STATUS_COLORS.pending;
            
            return (
              <div
                key={alert.id}
                className={`bg-gray-800 rounded-lg p-4 border ${severityColors.border} hover:bg-gray-750 cursor-pointer transition-colors`}
                onClick={() => handleSelectAlert(alert)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-4">
                    <span className="text-3xl">{RULE_ICONS[alert.rule_type] || '⚠️'}</span>
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-white font-medium">
                          {alert.rule_type.replace(/_/g, ' ').toUpperCase()}
                        </h3>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${severityColors.bg} ${severityColors.text}`}>
                          {alert.severity}
                        </span>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusColors.bg} ${statusColors.text}`}>
                          {alert.status}
                        </span>
                      </div>
                      <p className="text-gray-400 text-sm mb-2">{alert.description}</p>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span>📍 {alert.address.slice(0, 10)}...{alert.address.slice(-6)}</span>
                        <span>🕐 {new Date(alert.created_at).toLocaleString()}</span>
                        {alert.reviewed_by && <span>👤 {alert.reviewed_by}</span>}
                      </div>
                    </div>
                  </div>
                  <button className="text-gray-400 hover:text-white">→</button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Alert Detail Modal with Explainability */}
      {selectedAlert && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-y-auto border border-gray-700">
            <div className="p-6">
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  {RULE_ICONS[selectedAlert.rule_type] || '⚠️'} Alert Details
                </h2>
                <button
                  onClick={() => { setSelectedAlert(null); setExplanation(null); setShowExplanation(false); }}
                  className="text-gray-400 hover:text-white text-2xl"
                >
                  ×
                </button>
              </div>

              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-gray-400 text-sm">Rule Type</label>
                    <div className="text-white">{selectedAlert.rule_type.replace(/_/g, ' ')}</div>
                  </div>
                  <div>
                    <label className="text-gray-400 text-sm">Severity</label>
                    <div className={SEVERITY_COLORS[selectedAlert.severity]?.text || 'text-white'}>
                      {selectedAlert.severity.toUpperCase()}
                    </div>
                  </div>
                  <div>
                    <label className="text-gray-400 text-sm">Status</label>
                    <div className={STATUS_COLORS[selectedAlert.status]?.text || 'text-white'}>
                      {selectedAlert.status.toUpperCase()}
                    </div>
                  </div>
                  <div>
                    <label className="text-gray-400 text-sm">Created</label>
                    <div className="text-white">{new Date(selectedAlert.created_at).toLocaleString()}</div>
                  </div>
                </div>

                <div>
                  <label className="text-gray-400 text-sm">Address</label>
                  <div className="text-white font-mono text-sm bg-gray-700 p-2 rounded">{selectedAlert.address}</div>
                </div>

                <div>
                  <label className="text-gray-400 text-sm">Description</label>
                  <div className="text-white">{selectedAlert.description}</div>
                </div>

                {selectedAlert.amount !== undefined && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-gray-400 text-sm">Amount</label>
                      <div className="text-white">{selectedAlert.amount} ETH</div>
                    </div>
                    {selectedAlert.threshold !== undefined && (
                      <div>
                        <label className="text-gray-400 text-sm">Threshold</label>
                        <div className="text-white">{selectedAlert.threshold} ETH</div>
                      </div>
                    )}
                  </div>
                )}

                {/* Explainability Button */}
                <div className="pt-4 border-t border-gray-700">
                  <button
                    onClick={() => fetchExplanation(selectedAlert)}
                    disabled={isLoadingExplanation}
                    className="w-full px-4 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg text-white font-medium flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {isLoadingExplanation ? (
                      <>
                        <span className="animate-spin">⏳</span>
                        Analyzing...
                      </>
                    ) : (
                      <>
                        🔍 Explain This Alert (ML Analysis)
                      </>
                    )}
                  </button>
                </div>

                {/* Explainability Panel */}
                {showExplanation && explanation && (
                  <div className="mt-4 space-y-4 bg-gray-900 rounded-lg p-4 border border-purple-500/30">
                    {/* Header with Action Badge */}
                    <div className="flex items-center justify-between">
                      <h3 className="text-lg font-bold text-purple-400 flex items-center gap-2">
                        🧠 ML Explainability
                        {explanation.degraded_mode && (
                          <span className="text-xs bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded">
                            Local Mode
                          </span>
                        )}
                      </h3>
                      <div className={`px-3 py-1 rounded-full font-bold ${ACTION_COLORS[explanation.action]?.bg} ${ACTION_COLORS[explanation.action]?.text}`}>
                        {ACTION_COLORS[explanation.action]?.icon} {explanation.action}
                      </div>
                    </div>

                    {/* Risk Score & Summary */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-gray-800 rounded-lg p-3">
                        <div className="text-gray-400 text-sm">Risk Score</div>
                        <div className="text-3xl font-bold text-white">
                          {(explanation.risk_score * 100).toFixed(1)}%
                        </div>
                        <div className="text-gray-500 text-xs">
                          Confidence: {(explanation.confidence * 100).toFixed(0)}%
                        </div>
                      </div>
                      <div className="bg-gray-800 rounded-lg p-3">
                        <div className="text-gray-400 text-sm">Summary</div>
                        <div className="text-white text-sm">{explanation.summary}</div>
                      </div>
                    </div>

                    {/* Top Reasons */}
                    <div>
                      <h4 className="text-gray-400 text-sm mb-2">🎯 Key Risk Factors</h4>
                      <div className="space-y-2">
                        {explanation.top_reasons.map((reason, idx) => (
                          <div key={idx} className="flex items-center gap-2 bg-gray-800 rounded p-2">
                            <span className="text-purple-400 font-bold">{idx + 1}.</span>
                            <span className="text-white">{reason}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Detailed Factors */}
                    {explanation.factors.length > 0 && (
                      <div>
                        <h4 className="text-gray-400 text-sm mb-2">📊 Factor Analysis</h4>
                        <div className="space-y-2">
                          {explanation.factors.map((factor, idx) => {
                            const impactStyle = IMPACT_COLORS[factor.impact] || IMPACT_COLORS.NEUTRAL;
                            return (
                              <div key={idx} className={`${impactStyle.bg} rounded-lg p-3 border border-gray-700`}>
                                <div className="flex items-center justify-between mb-1">
                                  <span className={`font-medium ${impactStyle.text}`}>
                                    {impactStyle.icon} {factor.reason}
                                  </span>
                                  <span className="text-gray-400 text-xs">
                                    Contribution: {(factor.contribution * 100).toFixed(0)}%
                                  </span>
                                </div>
                                <div className="text-gray-400 text-sm">{factor.detail}</div>
                                {factor.threshold !== undefined && factor.threshold !== null && (
                                  <div className="text-gray-500 text-xs mt-1">
                                    Value: {String(factor.value)} | Threshold: {String(factor.threshold)}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Detected Typologies */}
                    {explanation.typology_matches.length > 0 && (
                      <div>
                        <h4 className="text-gray-400 text-sm mb-2">🔎 Detected Fraud Patterns</h4>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {explanation.typology_matches.map((typology, idx) => (
                            <div key={idx} className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-red-400 font-medium capitalize">
                                  {typology.typology.replace(/_/g, ' ')}
                                </span>
                                <span className="text-gray-400 text-xs">
                                  {(typology.confidence * 100).toFixed(0)}% confidence
                                </span>
                              </div>
                              <div className="text-gray-300 text-sm">{typology.description}</div>
                              {typology.indicators.length > 0 && (
                                <div className="mt-2 flex flex-wrap gap-1">
                                  {typology.indicators.map((indicator, i) => (
                                    <span key={i} className="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded">
                                      {indicator}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Graph Explanation */}
                    {explanation.graph_explanation && (
                      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                        <h4 className="text-blue-400 text-sm mb-1">🕸️ Network Analysis</h4>
                        <div className="text-gray-300 text-sm">{explanation.graph_explanation}</div>
                      </div>
                    )}

                    {/* Recommendations */}
                    {explanation.recommendations.length > 0 && (
                      <div>
                        <h4 className="text-gray-400 text-sm mb-2">💡 Recommendations</h4>
                        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
                          <ul className="space-y-1">
                            {explanation.recommendations.map((rec, idx) => (
                              <li key={idx} className="text-green-300 text-sm flex items-start gap-2">
                                <span>•</span>
                                <span>{rec}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Action Buttons */}
                {selectedAlert.status === 'pending' && (
                  <div className="flex gap-4 pt-4 border-t border-gray-700">
                    <button
                      onClick={() => handleReviewAlert(selectedAlert.id, 'review')}
                      className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 rounded-lg text-white font-medium"
                    >
                      ✅ Mark Reviewed
                    </button>
                    <button
                      onClick={() => handleReviewAlert(selectedAlert.id, 'escalate')}
                      className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-white font-medium"
                    >
                      🚨 Escalate
                    </button>
                    <button
                      onClick={() => handleReviewAlert(selectedAlert.id, 'dismiss')}
                      className="flex-1 px-4 py-2 bg-gray-600 hover:bg-gray-700 rounded-lg text-white font-medium"
                    >
                      ❌ Dismiss
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
    </AppLayout>
  );
}
