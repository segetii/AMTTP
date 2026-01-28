'use client';

/**
 * PolicySimulator Component
 * 
 * Test transactions against policies in a sandbox
 * 
 * Ground Truth Reference:
 * - Show exactly which rules would trigger
 * - Transparent cause-effect for compliance
 * - No surprises - simulate before executing
 */

import React, { useState } from 'react';
import {
  Policy,
  PolicyAction,
  SimulationResult,
  TransferContext,
  RiskLevel,
} from '@/types/policy-engine';
import { usePolicy } from '@/lib/policy-engine-service';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface PolicySimulatorProps {
  policies: Policy[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// RESULT DISPLAY
// ═══════════════════════════════════════════════════════════════════════════════

function SimulationResultView({ result }: { result: SimulationResult }) {
  const actionColors: Record<string, string> = {
    [PolicyAction.ALLOW]: 'text-green-400 bg-green-900/30 border-green-600/30',
    [PolicyAction.FLAG]: 'text-yellow-400 bg-yellow-900/30 border-yellow-600/30',
    [PolicyAction.FLAG_FOR_REVIEW]: 'text-yellow-400 bg-yellow-900/30 border-yellow-600/30',
    [PolicyAction.REQUIRE_APPROVAL]: 'text-orange-400 bg-orange-900/30 border-orange-600/30',
    [PolicyAction.REQUIRE_ESCROW]: 'text-blue-400 bg-blue-900/30 border-blue-600/30',
    [PolicyAction.BLOCK]: 'text-red-400 bg-red-900/30 border-red-600/30',
    [PolicyAction.DELAY]: 'text-purple-400 bg-purple-900/30 border-purple-600/30',
    [PolicyAction.NOTIFY]: 'text-cyan-400 bg-cyan-900/30 border-cyan-600/30',
  };
  
  const riskColors: Record<RiskLevel, string> = {
    [RiskLevel.LOW]: 'text-green-400',
    [RiskLevel.MEDIUM]: 'text-yellow-400',
    [RiskLevel.HIGH]: 'text-orange-400',
    [RiskLevel.CRITICAL]: 'text-red-400',
  };
  
  return (
    <div className="bg-slate-800/50 rounded-lg border border-slate-700 p-4 space-y-4">
      {/* Overall Result */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-slate-400">Simulation Result</h3>
          <div className="flex items-center gap-3 mt-1">
            <span className={`px-3 py-1 rounded-lg border ${actionColors[result.action] || 'text-slate-400 bg-slate-900/30 border-slate-600/30'}`}>
              {result.action}
            </span>
            <span className={`text-sm ${riskColors[result.riskLevel]}`}>
              Risk: {result.riskLevel}
            </span>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Transfer Status</p>
          <p className={`text-sm ${result.allowed ? 'text-green-400' : 'text-red-400'}`}>
            {result.allowed ? '✓ Allowed' : '✗ Blocked'}
          </p>
        </div>
      </div>
      
      {/* Triggered Policies */}
      <div>
        <h4 className="text-sm font-medium text-slate-400 mb-2">
          Triggered Policies ({result.triggeredPolicies.length})
        </h4>
        {result.triggeredPolicies.length === 0 ? (
          <div className="bg-green-900/20 border border-green-600/20 rounded p-3 text-sm text-green-400">
            ✓ No policies triggered - transfer would be allowed
          </div>
        ) : (
          <div className="space-y-2">
            {result.triggeredPolicies.map((policy, idx) => (
              <div
                key={idx}
                className="bg-slate-900/50 rounded p-3 border border-slate-600/30"
              >
                <span className="font-medium text-white">{policy}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Reasons */}
      {result.reasons.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-slate-400 mb-2">Reasons</h4>
          <ul className="space-y-1">
            {result.reasons.map((reason, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-slate-300">
                <span className="text-cyan-400">•</span>
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}
      
      {/* Estimated Delay */}
      {result.estimatedDelay && result.estimatedDelay > 0 && (
        <div className="bg-orange-900/20 border border-orange-600/20 rounded p-3">
          <p className="text-sm text-orange-400">
            ⏱️ Estimated delay: {result.estimatedDelay} hours
          </p>
        </div>
      )}
      
      {/* Required Approvers */}
      {result.requiredApprovers && result.requiredApprovers.length > 0 && (
        <div>
          <h4 className="text-sm font-medium text-slate-400 mb-2">Required Approvers</h4>
          <div className="flex flex-wrap gap-2">
            {result.requiredApprovers.map((approver, idx) => (
              <span key={idx} className="px-2 py-1 bg-blue-900/30 text-blue-400 text-xs rounded border border-blue-600/30">
                {approver}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function PolicySimulator({ policies }: PolicySimulatorProps) {
  const { simulateTransfer, isSimulating } = usePolicy();
  
  const [context, setContext] = useState<TransferContext>({
    from: '0x742d35Cc6634C0532925a3b844Bc9e7595f8c2E4',
    to: '0x8Ba1f109551bD432803012645Ac136ddd64DBA72',
    amount: 10000,
    currency: 'USDC',
  });
  
  const [result, setResult] = useState<SimulationResult | null>(null);
  
  const runSimulation = async () => {
    const simResult = await simulateTransfer(context);
    setResult(simResult);
  };
  
  const updateContext = <K extends keyof TransferContext>(field: K, value: TransferContext[K]) => {
    setContext(prev => ({ ...prev, [field]: value }));
    setResult(null); // Clear previous result
  };
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-white">Policy Simulator</h2>
          <p className="text-sm text-slate-400">
            Test how policies would affect a transaction
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span className="w-2 h-2 bg-green-400 rounded-full" />
          {policies.filter(p => p.status === 'ACTIVE').length} active policies
        </div>
      </div>
      
      {/* Input Form */}
      <div className="bg-slate-800/30 rounded-lg border border-slate-700 p-4">
        <h3 className="text-sm font-medium text-slate-400 mb-4">Transfer Details</h3>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Amount</label>
            <input
              type="number"
              value={context.amount}
              onChange={(e) => updateContext('amount', parseFloat(e.target.value) || 0)}
              placeholder="10000"
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
            />
          </div>
          
          <div>
            <label className="block text-xs text-slate-500 mb-1">Currency</label>
            <select
              value={context.currency}
              onChange={(e) => updateContext('currency', e.target.value)}
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white"
            >
              <option value="USDC">USDC</option>
              <option value="USDT">USDT</option>
              <option value="DAI">DAI</option>
              <option value="ETH">ETH</option>
              <option value="BTC">BTC</option>
            </select>
          </div>
          
          <div>
            <label className="block text-xs text-slate-500 mb-1">From Address</label>
            <input
              type="text"
              value={context.from}
              onChange={(e) => updateContext('from', e.target.value)}
              placeholder="0x..."
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
            />
          </div>
          
          <div>
            <label className="block text-xs text-slate-500 mb-1">To Address</label>
            <input
              type="text"
              value={context.to}
              onChange={(e) => updateContext('to', e.target.value)}
              placeholder="0x..."
              className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-white text-sm"
            />
          </div>
        </div>
        
        {/* Quick Amount Presets */}
        <div className="mt-4">
          <label className="block text-xs text-slate-500 mb-2">Quick Amounts</label>
          <div className="flex flex-wrap gap-2">
            {[1000, 5000, 10000, 25000, 50000, 100000, 250000].map(amount => (
              <button
                key={amount}
                onClick={() => updateContext('amount', amount)}
                className={`px-3 py-1 rounded text-sm transition-colors ${
                  context.amount === amount
                    ? 'bg-cyan-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                ${amount.toLocaleString()}
              </button>
            ))}
          </div>
        </div>
        
        {/* Simulate Button */}
        <div className="mt-6 flex justify-end">
          <button
            onClick={runSimulation}
            disabled={isSimulating || !context.amount || !context.from || !context.to}
            className="px-6 py-2.5 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSimulating ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Simulating...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Run Simulation
              </>
            )}
          </button>
        </div>
      </div>
      
      {/* Results */}
      {result && <SimulationResultView result={result} />}
      
      {/* No policies warning */}
      {policies.filter(p => p.status === 'ACTIVE').length === 0 && (
        <div className="bg-yellow-900/20 border border-yellow-600/30 rounded-lg p-4 flex items-start gap-3">
          <svg className="w-5 h-5 text-yellow-400 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h4 className="text-sm font-medium text-yellow-400">No Active Policies</h4>
            <p className="text-sm text-yellow-200/70 mt-1">
              There are no active policies to test against. Create and activate policies first.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
