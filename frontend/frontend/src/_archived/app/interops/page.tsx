'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

function InteropsContent() {
  const { profile } = useProfile();
  const [activeTab, setActiveTab] = useState<'crosschain' | 'dex' | 'custodians'>('crosschain');

  if (!profile || profile.entity_type !== 'VASP') {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">Interoperability features are exclusive to VASP (Exchange) accounts.</p>
      </div>
    );
  }

  const layerZeroChains = [
    { name: 'Ethereum', icon: '⟠', status: 'Connected', volume: '15,000 ETH', latency: '12s' },
    { name: 'Polygon', icon: '🟣', status: 'Connected', volume: '8,500 ETH', latency: '2s' },
    { name: 'Arbitrum', icon: '🔵', status: 'Connected', volume: '12,000 ETH', latency: '1s' },
    { name: 'Optimism', icon: '🔴', status: 'Connected', volume: '6,200 ETH', latency: '1s' },
    { name: 'Base', icon: '🟦', status: 'Connected', volume: '4,800 ETH', latency: '1s' },
    { name: 'Avalanche', icon: '🔺', status: 'Syncing', volume: '2,100 ETH', latency: '3s' },
  ];

  const dexConnections = [
    { name: 'Uniswap V3', type: 'AMM', status: 'Active', pairs: 156, volume24h: '$12.5M' },
    { name: 'Curve Finance', type: 'Stable', status: 'Active', pairs: 42, volume24h: '$8.2M' },
    { name: 'SushiSwap', type: 'AMM', status: 'Active', pairs: 89, volume24h: '$3.1M' },
    { name: 'Balancer', type: 'Multi', status: 'Inactive', pairs: 0, volume24h: '$0' },
  ];

  const custodians = [
    { name: 'Fireblocks', status: 'Connected', type: 'MPC Custody', assets: '$150M' },
    { name: 'BitGo', status: 'Connected', type: 'Multi-sig', assets: '$85M' },
    { name: 'Anchorage', status: 'Pending', type: 'Qualified Custody', assets: '-' },
    { name: 'Copper', status: 'Connected', type: 'MPC Custody', assets: '$42M' },
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">🔗 Interoperability Hub</h1>
      <p className="text-gray-400 mb-6">Cross-chain bridges, DEX integrations, and custodian connections</p>

      {/* Stats Overview */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="bg-gradient-to-br from-blue-900/50 to-cyan-900/50 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-blue-400">6</p>
          <p className="text-sm text-gray-400">Connected Chains</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-green-400">$23.8M</p>
          <p className="text-sm text-gray-400">24h DEX Volume</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-purple-400">$277M</p>
          <p className="text-sm text-gray-400">Custody AUM</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-yellow-400">99.9%</p>
          <p className="text-sm text-gray-400">Bridge Uptime</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(
          [
            { id: 'crosschain', label: '🌉 Cross-Chain (LayerZero)' },
            { id: 'dex', label: '💱 DEX Integrations' },
            { id: 'custodians', label: '🏛️ Custodians' },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded font-medium transition-colors ${
              activeTab === tab.id ? 'bg-blue-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'crosschain' && (
        <div>
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">LayerZero Bridge Status</h2>
              <span className="bg-green-900 text-green-300 px-3 py-1 rounded text-sm">
                ✓ All Systems Operational
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4">
              {layerZeroChains.map(chain => (
                <div key={chain.name} className="bg-gray-700 rounded-lg p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl">{chain.icon}</span>
                    <div>
                      <p className="font-medium">{chain.name}</p>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        chain.status === 'Connected' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                      }`}>
                        {chain.status}
                      </span>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-gray-500">Volume</p>
                      <p className="font-medium">{chain.volume}</p>
                    </div>
                    <div>
                      <p className="text-gray-500">Latency</p>
                      <p className="font-medium">{chain.latency}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Bridge Transaction */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">🔄 Initiate Cross-Chain Transfer</h2>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Source Chain</label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2">
                  <option>Ethereum ⟠</option>
                  <option>Polygon 🟣</option>
                  <option>Arbitrum 🔵</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Destination Chain</label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2">
                  <option>Arbitrum 🔵</option>
                  <option>Optimism 🔴</option>
                  <option>Base 🟦</option>
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-6 mt-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Amount</label>
                <input
                  type="number"
                  placeholder="0.0"
                  className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Recipient (optional)</label>
                <input
                  type="text"
                  placeholder="0x... (defaults to sender)"
                  className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
                />
              </div>
            </div>
            <div className="mt-4 p-4 bg-gray-700 rounded">
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Estimated Fee:</span>
                <span>~0.002 ETH</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-400">Estimated Time:</span>
                <span>~15 minutes</span>
              </div>
            </div>
            <button className="w-full bg-blue-600 hover:bg-blue-700 py-3 rounded mt-4 font-medium">
              🌉 Bridge Assets
            </button>
          </div>
        </div>
      )}

      {activeTab === 'dex' && (
        <div className="bg-gray-800 rounded-lg p-6">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-semibold">DEX Connections</h2>
            <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
              + Add Integration
            </button>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-gray-500 text-sm border-b border-gray-700">
                <th className="text-left p-3">DEX</th>
                <th className="text-left p-3">Type</th>
                <th className="text-center p-3">Status</th>
                <th className="text-center p-3">Pairs</th>
                <th className="text-right p-3">24h Volume</th>
                <th className="text-center p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {dexConnections.map(dex => (
                <tr key={dex.name} className="border-b border-gray-700/50">
                  <td className="p-3 font-medium">{dex.name}</td>
                  <td className="p-3 text-gray-400">{dex.type}</td>
                  <td className="p-3 text-center">
                    <span className={`px-2 py-1 rounded text-xs ${
                      dex.status === 'Active' ? 'bg-green-900 text-green-300' : 'bg-gray-600 text-gray-400'
                    }`}>
                      {dex.status}
                    </span>
                  </td>
                  <td className="p-3 text-center">{dex.pairs}</td>
                  <td className="p-3 text-right font-medium">{dex.volume24h}</td>
                  <td className="p-3 text-center">
                    <button className="text-blue-400 hover:underline text-sm mr-2">Configure</button>
                    <button className="text-red-400 hover:underline text-sm">Disconnect</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'custodians' && (
        <div>
          <div className="bg-gray-800 rounded-lg p-6 mb-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Connected Custodians</h2>
              <button className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded text-sm">
                + Connect Custodian
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              {custodians.map(custodian => (
                <div key={custodian.name} className="bg-gray-700 rounded-lg p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <h3 className="font-semibold text-lg">{custodian.name}</h3>
                      <p className="text-sm text-gray-400">{custodian.type}</p>
                    </div>
                    <span className={`px-2 py-1 rounded text-xs ${
                      custodian.status === 'Connected' ? 'bg-green-900 text-green-300' :
                      custodian.status === 'Pending' ? 'bg-yellow-900 text-yellow-300' :
                      'bg-gray-600 text-gray-400'
                    }`}>
                      {custodian.status}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <div>
                      <p className="text-gray-500 text-sm">Assets Under Management</p>
                      <p className="text-xl font-bold text-green-400">{custodian.assets}</p>
                    </div>
                    <button className="text-blue-400 hover:underline text-sm">
                      Manage →
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Settlement */}
          <div className="bg-gray-800 rounded-lg p-6">
            <h2 className="text-xl font-semibold mb-4">⚡ Instant Settlement</h2>
            <p className="text-gray-400 mb-4">Configure automatic settlement between custodians</p>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">From Custodian</label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2">
                  <option>Fireblocks</option>
                  <option>BitGo</option>
                  <option>Copper</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">To Custodian</label>
                <select className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2">
                  <option>BitGo</option>
                  <option>Fireblocks</option>
                  <option>Copper</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Threshold</label>
                <input
                  type="text"
                  placeholder="e.g., 100 ETH"
                  className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
                />
              </div>
            </div>
            <button className="mt-4 bg-purple-600 hover:bg-purple-700 px-6 py-2 rounded font-medium">
              Create Settlement Rule
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function InteropsPage() {
  return (
    <AppLayout>
      <InteropsContent />
    </AppLayout>
  );
}
