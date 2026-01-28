'use client';

/**
 * Risk Scoring Page
 * 
 * Risk assessment and scoring engine
 * RBAC: R4+ required (Institution, Regulator, Admin)
 */

import React, { useState } from 'react';
import dynamic from 'next/dynamic';
import { 
  ArrowPathIcon,
  MagnifyingGlassIcon,
  AdjustmentsHorizontalIcon,
  ExclamationTriangleIcon,
  ShieldCheckIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';

// Dynamically import chart components
const RiskDistributionChart = dynamic(
  () => import('@/components/detection/RiskDistributionChart'),
  { ssr: false, loading: () => <ChartPlaceholder /> }
);

import { generateMockDistributionData } from '@/components/detection/RiskDistributionChart';

// ═══════════════════════════════════════════════════════════════════════════════
// PLACEHOLDER
// ═══════════════════════════════════════════════════════════════════════════════

function ChartPlaceholder() {
  return (
    <div className="h-[300px] bg-slate-900 rounded-lg flex items-center justify-center">
      <div className="text-center">
        <div className="w-8 h-8 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin mx-auto mb-2" />
        <p className="text-slate-400 text-sm">Loading chart...</p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

interface RiskAssessment {
  id: string;
  address: string;
  overallScore: number;
  transactionScore: number;
  behaviorScore: number;
  networkScore: number;
  complianceScore: number;
  lastAssessed: string;
  riskFactors: string[];
}

const mockAssessments: RiskAssessment[] = [
  {
    id: 'risk_001',
    address: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    overallScore: 0.15,
    transactionScore: 0.12,
    behaviorScore: 0.18,
    networkScore: 0.14,
    complianceScore: 0.10,
    lastAssessed: new Date(Date.now() - 300000).toISOString(),
    riskFactors: [],
  },
  {
    id: 'risk_002',
    address: '0x8Ba1f109551bD432803012645Ac136ddd64DBA72',
    overallScore: 0.67,
    transactionScore: 0.72,
    behaviorScore: 0.58,
    networkScore: 0.75,
    complianceScore: 0.62,
    lastAssessed: new Date(Date.now() - 600000).toISOString(),
    riskFactors: ['High velocity', 'Mixer interaction', 'New wallet'],
  },
  {
    id: 'risk_003',
    address: '0xABc2f109551bD432803012645Ac136ddd64DBA74',
    overallScore: 0.89,
    transactionScore: 0.92,
    behaviorScore: 0.85,
    networkScore: 0.91,
    complianceScore: 0.88,
    lastAssessed: new Date(Date.now() - 900000).toISOString(),
    riskFactors: ['Sanctioned interaction', 'Layering pattern', 'High velocity', 'Cross-chain obfuscation'],
  },
  {
    id: 'risk_004',
    address: '0xDEf35Cc6634C0532925a3b844Bc9e7595f8c2E5',
    overallScore: 0.34,
    transactionScore: 0.28,
    behaviorScore: 0.42,
    networkScore: 0.30,
    complianceScore: 0.35,
    lastAssessed: new Date(Date.now() - 1200000).toISOString(),
    riskFactors: ['Unusual hours'],
  },
  {
    id: 'risk_005',
    address: '0xFEd35Cc6634C0532925a3b844Bc9e7595f8c2E6',
    overallScore: 0.52,
    transactionScore: 0.48,
    behaviorScore: 0.55,
    networkScore: 0.58,
    complianceScore: 0.47,
    lastAssessed: new Date(Date.now() - 1800000).toISOString(),
    riskFactors: ['Round amounts', 'Frequent small transfers'],
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function RiskScoringPage() {
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [riskThreshold, setRiskThreshold] = useState(0.5);

  const distributionData = generateMockDistributionData();

  const handleRefresh = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 1000);
  };

  const getRiskLevel = (score: number) => {
    if (score < 0.3) return { label: 'Low', color: 'text-green-400', bg: 'bg-green-900/50', border: 'border-green-700' };
    if (score < 0.6) return { label: 'Medium', color: 'text-yellow-400', bg: 'bg-yellow-900/50', border: 'border-yellow-700' };
    if (score < 0.8) return { label: 'High', color: 'text-orange-400', bg: 'bg-orange-900/50', border: 'border-orange-700' };
    return { label: 'Critical', color: 'text-red-400', bg: 'bg-red-900/50', border: 'border-red-700' };
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  };

  const filteredAssessments = mockAssessments.filter(a =>
    a.address.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const highRiskCount = mockAssessments.filter(a => a.overallScore >= 0.7).length;
  const avgScore = mockAssessments.reduce((sum, a) => sum + a.overallScore, 0) / mockAssessments.length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Risk Scoring</h1>
          <p className="text-slate-400 mt-1">Assess and monitor wallet risk scores</p>
        </div>
        <button 
          onClick={handleRefresh}
          disabled={isLoading}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ChartBarIcon className="w-4 h-4" />
            <span>Total Assessed</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{mockAssessments.length}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ExclamationTriangleIcon className="w-4 h-4 text-red-400" />
            <span>High Risk</span>
          </div>
          <p className="text-2xl font-bold text-red-400 mt-2">{highRiskCount}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ChartBarIcon className="w-4 h-4" />
            <span>Avg Score</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{avgScore.toFixed(2)}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ShieldCheckIcon className="w-4 h-4 text-green-400" />
            <span>Low Risk</span>
          </div>
          <p className="text-2xl font-bold text-green-400 mt-2">
            {mockAssessments.filter(a => a.overallScore < 0.3).length}
          </p>
        </div>
      </div>

      {/* Distribution Chart */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <h2 className="text-lg font-semibold text-white mb-4">Risk Distribution</h2>
        <RiskDistributionChart data={distributionData} />
      </div>

      {/* Search & Filters */}
      <div className="flex flex-wrap gap-4 items-center bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="relative flex-1 max-w-md">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <input
            type="text"
            placeholder="Search wallet address..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="flex items-center gap-2">
          <AdjustmentsHorizontalIcon className="w-5 h-5 text-slate-400" />
          <label className="text-slate-400 text-sm">Threshold:</label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={riskThreshold}
            onChange={(e) => setRiskThreshold(Number(e.target.value))}
            className="w-24"
          />
          <span className="text-white text-sm w-12">{riskThreshold.toFixed(1)}</span>
        </div>
      </div>

      {/* Risk Assessments */}
      <div className="space-y-4">
        {filteredAssessments.map((assessment) => {
          const risk = getRiskLevel(assessment.overallScore);
          return (
            <div 
              key={assessment.id}
              className="bg-slate-800 rounded-lg border border-slate-700 p-4 hover:border-slate-600 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <code className="text-blue-400 font-mono">
                      {assessment.address.slice(0, 10)}...{assessment.address.slice(-8)}
                    </code>
                    <span className={`px-2 py-1 rounded-full text-xs ${risk.bg} ${risk.color} border ${risk.border}`}>
                      {risk.label} Risk
                    </span>
                  </div>
                  <p className="text-slate-500 text-sm mt-1">
                    Last assessed: {formatTime(assessment.lastAssessed)}
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-3xl font-bold ${risk.color}`}>
                    {(assessment.overallScore * 100).toFixed(0)}
                  </p>
                  <p className="text-slate-500 text-xs">Overall Score</p>
                </div>
              </div>

              {/* Score Breakdown */}
              <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-slate-700">
                <div>
                  <p className="text-slate-500 text-xs uppercase">Transaction</p>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 bg-slate-700 rounded-full h-2">
                      <div 
                        className="bg-blue-500 rounded-full h-2" 
                        style={{ width: `${assessment.transactionScore * 100}%` }}
                      />
                    </div>
                    <span className="text-white text-sm">{(assessment.transactionScore * 100).toFixed(0)}</span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">Behavior</p>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 bg-slate-700 rounded-full h-2">
                      <div 
                        className="bg-purple-500 rounded-full h-2" 
                        style={{ width: `${assessment.behaviorScore * 100}%` }}
                      />
                    </div>
                    <span className="text-white text-sm">{(assessment.behaviorScore * 100).toFixed(0)}</span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">Network</p>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 bg-slate-700 rounded-full h-2">
                      <div 
                        className="bg-orange-500 rounded-full h-2" 
                        style={{ width: `${assessment.networkScore * 100}%` }}
                      />
                    </div>
                    <span className="text-white text-sm">{(assessment.networkScore * 100).toFixed(0)}</span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">Compliance</p>
                  <div className="flex items-center gap-2 mt-1">
                    <div className="flex-1 bg-slate-700 rounded-full h-2">
                      <div 
                        className="bg-green-500 rounded-full h-2" 
                        style={{ width: `${assessment.complianceScore * 100}%` }}
                      />
                    </div>
                    <span className="text-white text-sm">{(assessment.complianceScore * 100).toFixed(0)}</span>
                  </div>
                </div>
              </div>

              {/* Risk Factors */}
              {assessment.riskFactors.length > 0 && (
                <div className="mt-4 pt-4 border-t border-slate-700">
                  <p className="text-slate-500 text-xs uppercase mb-2">Risk Factors</p>
                  <div className="flex flex-wrap gap-2">
                    {assessment.riskFactors.map((factor, idx) => (
                      <span 
                        key={idx}
                        className="px-2 py-1 rounded bg-red-900/30 text-red-400 text-xs border border-red-800"
                      >
                        {factor}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
