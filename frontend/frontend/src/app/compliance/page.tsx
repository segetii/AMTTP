'use client';

import { useState, useEffect } from 'react';

interface SanctionsCheckResult {
  query: { address?: string; name?: string };
  is_sanctioned: boolean;
  matches: Array<{
    match_type: string;
    confidence: number;
    entity?: { name: string; source_list: string };
  }>;
  check_timestamp: string;
}

interface CountryRisk {
  country_code: string;
  risk_score: number;
  risk_level: string;
  risk_factors: string[];
  is_fatf_black_list: boolean;
  is_fatf_grey_list: boolean;
  transaction_policy: string;
}

interface MonitoringAlert {
  id: string;
  rule_type: string;
  severity: string;
  status: string;
  address: string;
  description: string;
  created_at: string;
}

interface ServiceHealth {
  status: string;
  service: string;
  profiles_loaded?: number;
  connected_services?: Record<string, string>;
}

interface EntityProfile {
  address: string;
  entity_type: string;
  kyc_level: string;
  risk_tolerance: string;
  jurisdiction: string;
  daily_limit_eth: number;
  monthly_limit_eth: number;
  single_tx_limit_eth: number;
  total_transactions: number;
  daily_volume_eth: number;
}

interface ComplianceDecision {
  decision_id: string;
  action: string;
  risk_score: number;
  reasons: string[];
  requires_travel_rule: boolean;
  requires_sar: boolean;
  requires_escrow: boolean;
  escrow_duration_hours: number;
  processing_time_ms: number;
  checks: Array<{
    service: string;
    check_type: string;
    passed: boolean;
    score?: number;
    reason?: string;
  }>;
}

// Use gateway origin when running Next dev on :3004 (no nginx) so requests hit unified stack on :80.
// In production or when served via nginx, keep relative paths.
const resolveGatewayOrigin = () => {
  const envOrigin = process.env.NEXT_PUBLIC_GATEWAY_ORIGIN;
  if (envOrigin && envOrigin.length > 0) {
    return envOrigin.replace(/\/$/, '');
  }

  if (typeof window === 'undefined') {
    return '';
  }

  const { protocol, hostname, port } = window.location;
  if (port === '3004') {
    // Next dev server; backend is on same host port 80 via nginx
    return `${protocol}//${hostname}`;
  }

  // Default: same-origin relative paths behind nginx
  return '';
};

const GATEWAY_ORIGIN = resolveGatewayOrigin();
const SANCTIONS_API = `${GATEWAY_ORIGIN}/sanctions`;
const MONITORING_API = `${GATEWAY_ORIGIN}/monitoring`;
const GEO_RISK_API = `${GATEWAY_ORIGIN}/geo`;
const ORCHESTRATOR_API = `${GATEWAY_ORIGIN}/api`;

export default function CompliancePage() {
  // Service health
  const [orchestratorHealth, setOrchestratorHealth] = useState<ServiceHealth | null>(null);
  const [sanctionsHealth, setSanctionsHealth] = useState<ServiceHealth | null>(null);
  const [monitoringHealth, setMonitoringHealth] = useState<ServiceHealth | null>(null);
  const [geoHealth, setGeoHealth] = useState<ServiceHealth | null>(null);

  // Unified evaluation
  const [evalFrom, setEvalFrom] = useState('');
  const [evalTo, setEvalTo] = useState('');
  const [evalValue, setEvalValue] = useState('1.0');
  const [evalResult, setEvalResult] = useState<ComplianceDecision | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);

  // Profile management
  const [profileAddress, setProfileAddress] = useState('');
  const [profile, setProfile] = useState<EntityProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Sanctions check
  const [addressToCheck, setAddressToCheck] = useState('');
  const [sanctionsResult, setSanctionsResult] = useState<SanctionsCheckResult | null>(null);
  const [sanctionsLoading, setSanctionsLoading] = useState(false);

  // Geo risk check
  const [countryCode, setCountryCode] = useState('');
  const [countryRisk, setCountryRisk] = useState<CountryRisk | null>(null);
  const [geoLoading, setGeoLoading] = useState(false);

  // Monitoring alerts
  const [alerts, setAlerts] = useState<MonitoringAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(false);

  // FATF lists
  const [fatfBlack, setFatfBlack] = useState<Array<{ code: string; name: string }>>([]);
  const [fatfGrey, setFatfGrey] = useState<Array<{ code: string; name: string }>>([]);

  // Check service health on load
  useEffect(() => {
    checkHealth();
    loadFatfLists();
    loadAlerts();
  }, []);

  async function checkHealth() {
    try {
  const res0 = await fetch(`${ORCHESTRATOR_API}/health`);
      setOrchestratorHealth(await res0.json());
    } catch { setOrchestratorHealth(null); }

    try {
  const res1 = await fetch(`${SANCTIONS_API}/health`);
      setSanctionsHealth(await res1.json());
    } catch { setSanctionsHealth(null); }

    try {
  const res2 = await fetch(`${MONITORING_API}/health`);
      setMonitoringHealth(await res2.json());
    } catch { setMonitoringHealth(null); }

    try {
  const res3 = await fetch(`${GEO_RISK_API}/health`);
      setGeoHealth(await res3.json());
    } catch { setGeoHealth(null); }
  }

  // Unified transaction evaluation
  async function evaluateTransaction() {
    if (!evalFrom || !evalTo) return;
    setEvalLoading(true);
    setEvalResult(null);
    try {
  const res = await fetch(`${ORCHESTRATOR_API}/evaluate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          from_address: evalFrom,
          to_address: evalTo,
          value_eth: parseFloat(evalValue)
        })
      });
      setEvalResult(await res.json());
    } catch (e) {
      console.error('Evaluation failed:', e);
    }
    setEvalLoading(false);
  }

  // Load entity profile
  async function loadProfile() {
    if (!profileAddress) return;
    setProfileLoading(true);
    setProfile(null);
    try {
  const res = await fetch(`${ORCHESTRATOR_API}/profiles/${profileAddress}`);
      setProfile(await res.json());
    } catch (e) {
      console.error('Failed to load profile:', e);
    }
    setProfileLoading(false);
  }

  // Set profile type
  async function setProfileType(entityType: string) {
    if (!profileAddress) return;
    try {
  const res = await fetch(`${ORCHESTRATOR_API}/profiles/${profileAddress}/set-type/${entityType}`, {
        method: 'POST'
      });
      setProfile(await res.json());
    } catch (e) {
      console.error('Failed to set profile type:', e);
    }
  }

  async function loadFatfLists() {
    try {
  const res1 = await fetch(`${GEO_RISK_API}/lists/fatf-black`);
      const data1 = await res1.json();
      setFatfBlack(data1.countries || []);

  const res2 = await fetch(`${GEO_RISK_API}/lists/fatf-grey`);
      const data2 = await res2.json();
      setFatfGrey(data2.countries || []);
    } catch (e) {
      console.error('Failed to load FATF lists:', e);
    }
  }

  async function loadAlerts() {
    setAlertsLoading(true);
    try {
  const res = await fetch(`${MONITORING_API}/alerts?limit=10`);
      const data = await res.json();
      setAlerts(data.alerts || []);
    } catch (e) {
      console.error('Failed to load alerts:', e);
    }
    setAlertsLoading(false);
  }

  async function checkSanctions() {
    if (!addressToCheck) return;
    setSanctionsLoading(true);
    setSanctionsResult(null);

    try {
  const res = await fetch(`${SANCTIONS_API}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: addressToCheck })
      });
      const data = await res.json();
      setSanctionsResult(data);
    } catch (e) {
      console.error('Sanctions check failed:', e);
    }
    setSanctionsLoading(false);
  }

  async function checkCountryRisk() {
    if (!countryCode || countryCode.length !== 2) return;
    setGeoLoading(true);
    setCountryRisk(null);

    try {
      const res = await fetch(`${GEO_RISK_API}/geo/country-risk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ country_code: countryCode.toUpperCase() })
      });
      const data = await res.json();
      setCountryRisk(data);
    } catch (e) {
      console.error('Country risk check failed:', e);
    }
    setGeoLoading(false);
  }

  function getRiskColor(level: string) {
    switch (level) {
      case 'PROHIBITED': return 'bg-black text-white';
      case 'VERY_HIGH': return 'bg-red-600 text-white';
      case 'HIGH': return 'bg-red-500 text-white';
      case 'MEDIUM': return 'bg-yellow-500 text-black';
      case 'LOW': return 'bg-green-400 text-black';
      case 'MINIMAL': return 'bg-green-300 text-black';
      default: return 'bg-gray-400';
    }
  }

  function getSeverityColor(severity: string) {
    switch (severity) {
      case 'CRITICAL': return 'bg-red-600 text-white';
      case 'HIGH': return 'bg-red-500 text-white';
      case 'MEDIUM': return 'bg-yellow-500 text-black';
      case 'LOW': return 'bg-blue-400 text-white';
      default: return 'bg-gray-400';
    }
  }

  function getActionColor(action: string) {
    switch (action) {
      case 'APPROVE': return 'bg-green-600 text-white';
      case 'ESCROW': return 'bg-yellow-600 text-black';
      case 'REVIEW': return 'bg-orange-500 text-white';
      case 'BLOCK': return 'bg-red-600 text-white';
      case 'REQUIRE_INFO': return 'bg-purple-600 text-white';
      default: return 'bg-gray-600';
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">🛡️ Unified Compliance Dashboard</h1>
        <p className="text-gray-400 mb-6">Profile-based transaction evaluation, sanctions screening, AML monitoring, and geographic risk</p>

        {/* Service Health Status */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className={`p-4 rounded-lg ${orchestratorHealth?.status === 'healthy' ? 'bg-blue-900' : 'bg-red-900'}`}>
            <h3 className="font-semibold">🎯 Orchestrator</h3>
            <p className="text-sm">Port 8007 - {orchestratorHealth?.status || 'Offline'}</p>
            {orchestratorHealth?.profiles_loaded !== undefined && (
              <p className="text-xs text-gray-300">{orchestratorHealth.profiles_loaded} profiles</p>
            )}
          </div>
          <div className={`p-4 rounded-lg ${sanctionsHealth?.status === 'healthy' ? 'bg-green-900' : 'bg-red-900'}`}>
            <h3 className="font-semibold">Sanctions Screening</h3>
            <p className="text-sm">Port 8004 - {sanctionsHealth?.status || 'Offline'}</p>
          </div>
          <div className={`p-4 rounded-lg ${monitoringHealth?.status === 'healthy' ? 'bg-green-900' : 'bg-red-900'}`}>
            <h3 className="font-semibold">Transaction Monitoring</h3>
            <p className="text-sm">Port 8005 - {monitoringHealth?.status || 'Offline'}</p>
          </div>
          <div className={`p-4 rounded-lg ${geoHealth?.status === 'healthy' ? 'bg-green-900' : 'bg-red-900'}`}>
            <h3 className="font-semibold">Geographic Risk</h3>
            <p className="text-sm">Port 8006 - {geoHealth?.status || 'Offline'}</p>
          </div>
        </div>

        {/* UNIFIED TRANSACTION EVALUATION */}
        <div className="bg-gradient-to-r from-blue-900 to-purple-900 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">🔄 Unified Transaction Evaluation</h2>
          <p className="text-gray-300 text-sm mb-4">Evaluate transactions through all compliance services based on entity profiles</p>
          
          <div className="grid grid-cols-4 gap-4 mb-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1">From Address</label>
              <input
                type="text"
                placeholder="0x..."
                value={evalFrom}
                onChange={(e) => setEvalFrom(e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">To Address</label>
              <input
                type="text"
                placeholder="0x..."
                value={evalTo}
                onChange={(e) => setEvalTo(e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Value (ETH)</label>
              <input
                type="number"
                step="0.01"
                value={evalValue}
                onChange={(e) => setEvalValue(e.target.value)}
                className="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={evaluateTransaction}
                disabled={evalLoading}
                className="w-full bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium disabled:opacity-50"
              >
                {evalLoading ? 'Evaluating...' : '⚡ Evaluate'}
              </button>
            </div>
          </div>

          {/* Quick test buttons */}
          <div className="text-xs text-gray-400 mb-4">
            <span>Quick tests: </span>
            <button onClick={() => { setEvalFrom('0x1234567890123456789012345678901234567890'); setEvalTo('0x2345678901234567890123456789012345678901'); setEvalValue('0.5'); }}
              className="text-green-400 hover:underline">Clean Small TX</button>
            {' | '}
            <button onClick={() => { setEvalFrom('0x8589427373d6d84e98730d7795d8f6f8731fda16'); setEvalTo('0x2345678901234567890123456789012345678901'); setEvalValue('1.0'); }}
              className="text-red-400 hover:underline">Sanctioned Address</button>
            {' | '}
            <button onClick={() => { setEvalFrom('0xabcd1234567890abcdef1234567890abcd123456'); setEvalTo('0x2345678901234567890123456789012345678901'); setEvalValue('500.0'); }}
              className="text-blue-400 hover:underline">VASP Large TX</button>
          </div>

          {evalResult && (
            <div className="bg-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-4">
                  <span className={`px-4 py-2 rounded-lg font-bold text-lg ${getActionColor(evalResult.action)}`}>
                    {evalResult.action}
                  </span>
                  <div>
                    <p className="text-sm">Risk Score: <span className={`font-bold ${evalResult.risk_score > 50 ? 'text-red-400' : 'text-green-400'}`}>{evalResult.risk_score.toFixed(1)}%</span></p>
                    <p className="text-xs text-gray-400">Processing: {evalResult.processing_time_ms.toFixed(0)}ms</p>
                  </div>
                </div>
                <div className="flex gap-2">
                  {evalResult.requires_travel_rule && <span className="bg-purple-700 px-2 py-1 rounded text-xs">Travel Rule</span>}
                  {evalResult.requires_sar && <span className="bg-red-700 px-2 py-1 rounded text-xs">SAR Required</span>}
                  {evalResult.requires_escrow && <span className="bg-yellow-700 px-2 py-1 rounded text-xs">Escrow {evalResult.escrow_duration_hours}h</span>}
                </div>
              </div>
              
              {evalResult.reasons.length > 0 && (
                <div className="mb-4">
                  <p className="text-sm font-medium text-gray-300 mb-1">Reasons:</p>
                  <ul className="text-xs text-gray-400 list-disc list-inside">
                    {evalResult.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-3 gap-2">
                {evalResult.checks.map((check, i) => (
                  <div key={i} className={`p-2 rounded text-xs ${check.passed ? 'bg-green-900/50' : 'bg-red-900/50'}`}>
                    <p className="font-medium">{check.service}: {check.check_type}</p>
                    {check.score !== undefined && <p>Score: {check.score.toFixed(0)}</p>}
                    <p>{check.passed ? '✓ Passed' : '✗ Failed'}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ENTITY PROFILE MANAGEMENT */}
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">👤 Entity Profile Management</h2>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              placeholder="Enter wallet address to view/manage profile"
              value={profileAddress}
              onChange={(e) => setProfileAddress(e.target.value)}
              className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
            />
            <button
              onClick={loadProfile}
              disabled={profileLoading}
              className="bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded font-medium disabled:opacity-50"
            >
              {profileLoading ? 'Loading...' : 'Load Profile'}
            </button>
          </div>

          {profile && (
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-700 rounded p-4">
                <h3 className="font-medium mb-2">Profile Details</h3>
                <div className="text-sm space-y-1">
                  <p>Entity Type: <span className="font-bold text-blue-400">{profile.entity_type}</span></p>
                  <p>KYC Level: <span className="text-gray-300">{profile.kyc_level}</span></p>
                  <p>Risk Tolerance: <span className="text-gray-300">{profile.risk_tolerance}</span></p>
                  <p>Jurisdiction: <span className="text-gray-300">{profile.jurisdiction}</span></p>
                </div>
              </div>
              <div className="bg-gray-700 rounded p-4">
                <h3 className="font-medium mb-2">Limits & Activity</h3>
                <div className="text-sm space-y-1">
                  <p>Single TX Limit: <span className="text-green-400">{profile.single_tx_limit_eth} ETH</span></p>
                  <p>Daily Limit: <span className="text-gray-300">{profile.daily_limit_eth} ETH</span></p>
                  <p>Daily Used: <span className="text-yellow-400">{profile.daily_volume_eth.toFixed(2)} ETH</span></p>
                  <p>Total Transactions: <span className="text-gray-300">{profile.total_transactions}</span></p>
                </div>
              </div>
              <div className="col-span-2">
                <h3 className="font-medium mb-2">Set Entity Type</h3>
                <div className="flex gap-2">
                  {['RETAIL', 'INSTITUTIONAL', 'VASP', 'HIGH_NET_WORTH', 'UNVERIFIED'].map(type => (
                    <button
                      key={type}
                      onClick={() => setProfileType(type)}
                      className={`px-3 py-1 rounded text-sm ${profile.entity_type === type ? 'bg-blue-600' : 'bg-gray-600 hover:bg-gray-500'}`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-6">
          {/* Sanctions Check */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">🔍 Sanctions Check</h2>
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                placeholder="Enter wallet address (0x...)"
                value={addressToCheck}
                onChange={(e) => setAddressToCheck(e.target.value)}
                className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm"
              />
              <button
                onClick={checkSanctions}
                disabled={sanctionsLoading}
                className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium disabled:opacity-50"
              >
                {sanctionsLoading ? 'Checking...' : 'Check'}
              </button>
            </div>

            {/* Quick test addresses */}
            <div className="text-xs text-gray-400 mb-4">
              <span>Quick test: </span>
              <button
                onClick={() => setAddressToCheck('0x8589427373d6d84e98730d7795d8f6f8731fda16')}
                className="text-red-400 hover:underline"
              >
                Tornado Cash
              </button>
              {' | '}
              <button
                onClick={() => setAddressToCheck('0x098b716b8aaf21512996dc57eb0615e2383e2f96')}
                className="text-red-400 hover:underline"
              >
                Lazarus Group
              </button>
              {' | '}
              <button
                onClick={() => setAddressToCheck('0x1234567890123456789012345678901234567890')}
                className="text-green-400 hover:underline"
              >
                Clean Address
              </button>
            </div>

            {sanctionsResult && (
              <div className={`p-4 rounded ${sanctionsResult.is_sanctioned ? 'bg-red-900' : 'bg-green-900'}`}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">{sanctionsResult.is_sanctioned ? '🚫' : '✅'}</span>
                  <span className="font-bold">
                    {sanctionsResult.is_sanctioned ? 'SANCTIONED' : 'CLEAR'}
                  </span>
                </div>
                {sanctionsResult.matches.length > 0 && (
                  <div className="text-sm">
                    <p><strong>Match:</strong> {sanctionsResult.matches[0].entity?.name}</p>
                    <p><strong>List:</strong> {sanctionsResult.matches[0].entity?.source_list}</p>
                    <p><strong>Confidence:</strong> {(sanctionsResult.matches[0].confidence * 100).toFixed(0)}%</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Country Risk Check */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">🌍 Geographic Risk</h2>
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                placeholder="Country code (e.g., KP, NG, GB)"
                value={countryCode}
                onChange={(e) => setCountryCode(e.target.value.toUpperCase())}
                maxLength={2}
                className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm uppercase"
              />
              <button
                onClick={checkCountryRisk}
                disabled={geoLoading}
                className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded font-medium disabled:opacity-50"
              >
                {geoLoading ? 'Checking...' : 'Check'}
              </button>
            </div>

            {/* Quick test countries */}
            <div className="text-xs text-gray-400 mb-4">
              <span>Quick test: </span>
              <button onClick={() => setCountryCode('KP')} className="text-red-400 hover:underline">KP (N.Korea)</button>
              {' | '}
              <button onClick={() => setCountryCode('IR')} className="text-red-400 hover:underline">IR (Iran)</button>
              {' | '}
              <button onClick={() => setCountryCode('NG')} className="text-yellow-400 hover:underline">NG (Nigeria)</button>
              {' | '}
              <button onClick={() => setCountryCode('GB')} className="text-green-400 hover:underline">GB (UK)</button>
            </div>

            {countryRisk && (
              <div className="space-y-3">
                <div className={`inline-block px-3 py-1 rounded text-sm font-bold ${getRiskColor(countryRisk.risk_level)}`}>
                  {countryRisk.risk_level} - Score: {countryRisk.risk_score}/100
                </div>
                <div className="text-sm space-y-1">
                  <p><strong>Country:</strong> {countryRisk.country_code}</p>
                  <p><strong>Policy:</strong> {countryRisk.transaction_policy}</p>
                  {countryRisk.is_fatf_black_list && (
                    <p className="text-red-400">⛔ FATF Black List</p>
                  )}
                  {countryRisk.is_fatf_grey_list && (
                    <p className="text-yellow-400">⚠️ FATF Grey List</p>
                  )}
                </div>
                {countryRisk.risk_factors.length > 0 && (
                  <div className="text-xs bg-gray-700 p-2 rounded">
                    <strong>Risk Factors:</strong>
                    <ul className="list-disc list-inside mt-1">
                      {countryRisk.risk_factors.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* FATF Lists */}
        <div className="grid grid-cols-2 gap-6 mt-6">
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">⛔ FATF Black List ({fatfBlack.length})</h2>
            <p className="text-xs text-gray-400 mb-3">High-Risk Jurisdictions - Transactions PROHIBITED</p>
            <div className="flex flex-wrap gap-2">
              {fatfBlack.map((c) => (
                <span key={c.code} className="bg-red-900 text-red-200 px-2 py-1 rounded text-xs">
                  {c.code} - {c.name}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">⚠️ FATF Grey List ({fatfGrey.length})</h2>
            <p className="text-xs text-gray-400 mb-3">Jurisdictions Under Increased Monitoring</p>
            <div className="flex flex-wrap gap-2">
              {fatfGrey.map((c) => (
                <span key={c.code} className="bg-yellow-900 text-yellow-200 px-2 py-1 rounded text-xs">
                  {c.code}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* AML Monitoring Alerts */}
        <div className="bg-gray-800 rounded-lg p-6 mt-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">📊 AML Monitoring Alerts</h2>
            <button
              onClick={loadAlerts}
              className="bg-gray-700 hover:bg-gray-600 px-3 py-1 rounded text-sm"
            >
              Refresh
            </button>
          </div>

          {alertsLoading ? (
            <p className="text-gray-400">Loading alerts...</p>
          ) : alerts.length === 0 ? (
            <p className="text-gray-400">No alerts - System is clean ✅</p>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert) => (
                <div key={alert.id} className="bg-gray-700 p-3 rounded flex items-center gap-4">
                  <span className={`px-2 py-1 rounded text-xs font-bold ${getSeverityColor(alert.severity)}`}>
                    {alert.severity}
                  </span>
                  <span className="bg-gray-600 px-2 py-1 rounded text-xs">
                    {alert.rule_type}
                  </span>
                  <span className="flex-1 text-sm">{alert.description}</span>
                  <span className="text-xs text-gray-400">
                    {new Date(alert.created_at).toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-gray-500 text-sm">
          <p>AMTTP Compliance Services v1.0</p>
          <p>Sanctions: HMT/OFAC/EU/UN | AML: 6 Rules | Geo: FATF Black/Grey Lists</p>
        </div>
      </div>
    </div>
  );
}
