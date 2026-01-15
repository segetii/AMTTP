'use client';

import { useState, useEffect } from 'react';
import AppLayout from '@/components/AppLayout';

interface FATFCountry {
  code: string;
  name: string;
  reason?: string;
  added_date?: string;
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

// Use relative URL so it works both behind nginx (proxies /geo -> geo service)
// and during local dev when frontend is served via the unified container.
const GEO_RISK_API = '';

export default function FATFRulesPage() {
  const [blackList, setBlackList] = useState<FATFCountry[]>([]);
  const [greyList, setGreyList] = useState<FATFCountry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Country check
  const [checkCountry, setCheckCountry] = useState('');
  const [countryRisk, setCountryRisk] = useState<CountryRisk | null>(null);
  const [checkLoading, setCheckLoading] = useState(false);

  useEffect(() => {
    loadFATFLists();
  }, []);

  async function loadFATFLists() {
    setLoading(true);
    setError(null);
    try {
      const [blackRes, greyRes] = await Promise.all([
        fetch(`/geo/lists/fatf-black`),
        fetch(`/geo/lists/fatf-grey`)
      ]);
      
      if (!blackRes.ok || !greyRes.ok) {
        throw new Error('Failed to fetch FATF lists');
      }
      
      const blackData = await blackRes.json();
      const greyData = await greyRes.json();
      
      setBlackList(blackData.countries || []);
      setGreyList(greyData.countries || []);
    } catch (e) {
      console.error('Failed to load FATF lists:', e);
      setError('Failed to load FATF lists. Ensure Geo-Risk service is running on port 8006.');
    }
    setLoading(false);
  }

  async function checkCountryRisk() {
    if (!checkCountry) return;
    setCheckLoading(true);
    setCountryRisk(null);
    try {
  const res = await fetch(`/geo/risk/${checkCountry.toUpperCase()}`);
      if (res.ok) {
        setCountryRisk(await res.json());
      }
    } catch (e) {
      console.error('Failed to check country:', e);
    }
    setCheckLoading(false);
  }

  const getRiskColor = (level: string) => {
    switch (level) {
      case 'PROHIBITED': return 'text-red-500 bg-red-500/20';
      case 'HIGH': return 'text-orange-500 bg-orange-500/20';
      case 'MEDIUM': return 'text-yellow-500 bg-yellow-500/20';
      case 'LOW': return 'text-green-500 bg-green-500/20';
      default: return 'text-gray-500 bg-gray-500/20';
    }
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              🌍 FATF Rules & Jurisdictions
            </h1>
            <p className="text-gray-400 mt-1">
              Financial Action Task Force compliance - High-risk and monitored jurisdictions
            </p>
          </div>
          <button
            onClick={loadFATFLists}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white text-sm"
          >
            🔄 Refresh Lists
          </button>
        </div>

        {/* Country Risk Checker */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <h2 className="text-lg font-semibold text-white mb-4">🔍 Check Country Risk</h2>
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="text-sm text-gray-400 block mb-1">Country Code (ISO 3166-1 alpha-2)</label>
              <input
                type="text"
                value={checkCountry}
                onChange={(e) => setCheckCountry(e.target.value.toUpperCase())}
                placeholder="e.g., GB, US, IR, KP"
                maxLength={2}
                className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
              />
            </div>
            <button
              onClick={checkCountryRisk}
              disabled={checkLoading || !checkCountry}
              className="px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-700 rounded-lg text-white"
            >
              {checkLoading ? 'Checking...' : 'Check Risk'}
            </button>
          </div>

          {countryRisk && (
            <div className="mt-4 p-4 bg-gray-800 rounded-lg">
              <div className="flex items-center justify-between mb-3">
                <span className="text-white font-medium">{countryRisk.country_code}</span>
                <span className={`px-3 py-1 rounded-full text-sm font-medium ${getRiskColor(countryRisk.risk_level)}`}>
                  {countryRisk.risk_level}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-400">Risk Score:</span>
                  <span className="text-white ml-2">{countryRisk.risk_score}/100</span>
                </div>
                <div>
                  <span className="text-gray-400">Policy:</span>
                  <span className="text-white ml-2">{countryRisk.transaction_policy}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-gray-400">FATF Status:</span>
                  <span className="ml-2">
                    {countryRisk.is_fatf_black_list && <span className="text-red-500">⛔ Black List</span>}
                    {countryRisk.is_fatf_grey_list && <span className="text-yellow-500">⚠️ Grey List</span>}
                    {!countryRisk.is_fatf_black_list && !countryRisk.is_fatf_grey_list && <span className="text-green-500">✅ Not Listed</span>}
                  </span>
                </div>
              </div>
              {countryRisk.risk_factors.length > 0 && (
                <div className="mt-3">
                  <span className="text-gray-400 text-sm">Risk Factors:</span>
                  <ul className="mt-1 space-y-1">
                    {countryRisk.risk_factors.map((factor, i) => (
                      <li key={i} className="text-yellow-400 text-sm">• {factor}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">Loading FATF lists...</div>
        ) : error ? (
          <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 text-red-400">
            {error}
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Black List */}
            <div className="bg-gray-900 rounded-xl border border-red-800/50">
              <div className="p-4 border-b border-gray-800 bg-red-900/20">
                <h2 className="text-lg font-semibold text-red-400 flex items-center gap-2">
                  ⛔ FATF Black List
                  <span className="text-sm bg-red-600 px-2 py-0.5 rounded-full text-white">
                    {blackList.length} countries
                  </span>
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  High-Risk Jurisdictions Subject to a Call for Action - Transactions PROHIBITED
                </p>
              </div>
              <div className="p-4 max-h-96 overflow-y-auto">
                {blackList.length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No countries on black list</p>
                ) : (
                  <div className="space-y-2">
                    {blackList.map((country) => (
                      <div key={country.code} className="flex items-center justify-between p-3 bg-gray-800 rounded-lg">
                        <div>
                          <span className="text-white font-medium">{country.code}</span>
                          <span className="text-gray-400 ml-2">{country.name}</span>
                        </div>
                        <span className="text-red-500 text-sm">🚫 Prohibited</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Grey List */}
            <div className="bg-gray-900 rounded-xl border border-yellow-800/50">
              <div className="p-4 border-b border-gray-800 bg-yellow-900/20">
                <h2 className="text-lg font-semibold text-yellow-400 flex items-center gap-2">
                  ⚠️ FATF Grey List
                  <span className="text-sm bg-yellow-600 px-2 py-0.5 rounded-full text-white">
                    {greyList.length} countries
                  </span>
                </h2>
                <p className="text-sm text-gray-400 mt-1">
                  Jurisdictions Under Increased Monitoring - Enhanced Due Diligence Required
                </p>
              </div>
              <div className="p-4 max-h-96 overflow-y-auto">
                {greyList.length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No countries on grey list</p>
                ) : (
                  <div className="space-y-2">
                    {greyList.map((country) => (
                      <div key={country.code} className="flex items-center justify-between p-3 bg-gray-800 rounded-lg">
                        <div>
                          <span className="text-white font-medium">{country.code}</span>
                          <span className="text-gray-400 ml-2">{country.name}</span>
                        </div>
                        <span className="text-yellow-500 text-sm">⚠️ Monitored</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* FATF Guidelines */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <h2 className="text-lg font-semibold text-white mb-4">📋 FATF Compliance Guidelines</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-gray-800 rounded-lg">
              <h3 className="text-red-400 font-medium mb-2">⛔ Black List Countries</h3>
              <ul className="text-sm text-gray-400 space-y-1">
                <li>• All transactions blocked</li>
                <li>• No exceptions allowed</li>
                <li>• Automatic SAR filing</li>
                <li>• Risk score: 100/100</li>
              </ul>
            </div>
            <div className="p-4 bg-gray-800 rounded-lg">
              <h3 className="text-yellow-400 font-medium mb-2">⚠️ Grey List Countries</h3>
              <ul className="text-sm text-gray-400 space-y-1">
                <li>• Enhanced due diligence required</li>
                <li>• Escrow for large transactions</li>
                <li>• 24-48 hour review period</li>
                <li>• Risk score: +40 points</li>
              </ul>
            </div>
            <div className="p-4 bg-gray-800 rounded-lg">
              <h3 className="text-blue-400 font-medium mb-2">📜 Travel Rule (Rec. 16)</h3>
              <ul className="text-sm text-gray-400 space-y-1">
                <li>• Threshold: £840 / €1,000</li>
                <li>• Originator info required</li>
                <li>• Beneficiary info required</li>
                <li>• Cross-border verification</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Quick Reference */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
          <h2 className="text-lg font-semibold text-white mb-4">🔗 Quick Reference</h2>
          <div className="flex flex-wrap gap-3">
            <a
              href="https://www.fatf-gafi.org/en/countries/black-and-grey-lists.html"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-blue-600/20 border border-blue-600/50 rounded-lg text-blue-400 hover:bg-blue-600/30"
            >
              FATF Official Lists →
            </a>
            <a
              href="https://www.fatf-gafi.org/en/topics/fatf-recommendations.html"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-purple-600/20 border border-purple-600/50 rounded-lg text-purple-400 hover:bg-purple-600/30"
            >
              FATF Recommendations →
            </a>
            <a
              href="/compliance"
              className="px-4 py-2 bg-green-600/20 border border-green-600/50 rounded-lg text-green-400 hover:bg-green-600/30"
            >
              Full Compliance Dashboard →
            </a>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
