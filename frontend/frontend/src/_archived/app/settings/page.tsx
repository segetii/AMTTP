'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

function SettingsContent() {
  const { profile, address, loadProfile } = useProfile();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  // Form state
  const [jurisdiction, setJurisdiction] = useState(profile?.jurisdiction || '');
  const [kycLevel, setKycLevel] = useState(profile?.kyc_level || 'NONE');

  const handleUpdateProfile = async (updates: Record<string, unknown>) => {
    if (!address) return;
    setSaving(true);
    setMessage('');

    try {
      const res = await fetch(`${ORCHESTRATOR_API}/profiles/${address}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates)
      });

      if (res.ok) {
        setMessage('Profile updated successfully');
        await loadProfile();
      } else {
        setMessage('Failed to update profile');
      }
    } catch (e) {
      setMessage('Error updating profile');
    }
    setSaving(false);
  };

  const handleSetEntityType = async (entityType: string) => {
    if (!address) return;
    setSaving(true);
    setMessage('');

    try {
      const res = await fetch(`${ORCHESTRATOR_API}/profiles/${address}/set-type/${entityType}`, {
        method: 'POST'
      });

      if (res.ok) {
        setMessage(`Profile type set to ${entityType}`);
        await loadProfile();
      } else {
        setMessage('Failed to set profile type');
      }
    } catch (e) {
      setMessage('Error setting profile type');
    }
    setSaving(false);
  };

  if (!profile) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">⚠️ Connect Wallet</h2>
        <p className="text-gray-400">Connect a wallet address in the sidebar to manage settings</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">⚙️ Settings</h1>
      <p className="text-gray-400 mb-6">Manage your profile and compliance settings</p>

      {message && (
        <div className={`mb-4 p-3 rounded ${message.includes('success') ? 'bg-green-900' : 'bg-red-900'}`}>
          {message}
        </div>
      )}

      {/* Profile Overview */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">👤 Profile Overview</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-500">Wallet Address</p>
            <p className="font-mono text-sm break-all">{profile.address}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Entity Type</p>
            <p className="text-lg font-bold text-blue-400">{profile.entity_type}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">KYC Level</p>
            <p className="font-medium">{profile.kyc_level}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500">Risk Tolerance</p>
            <p className="font-medium">{profile.risk_tolerance}</p>
          </div>
        </div>
      </div>

      {/* KYC Upgrade */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">🪪 KYC Verification</h2>
        <p className="text-gray-400 text-sm mb-4">
          Upgrade your KYC level to unlock higher transaction limits
        </p>

        <div className="grid grid-cols-5 gap-2 mb-4">
          {['NONE', 'BASIC', 'STANDARD', 'ENHANCED', 'INSTITUTIONAL'].map(level => (
            <button
              key={level}
              onClick={() => handleUpdateProfile({ kyc_level: level })}
              disabled={saving}
              className={`p-3 rounded text-center ${
                profile.kyc_level === level 
                  ? 'bg-blue-600 border-2 border-blue-400' 
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              <p className="font-medium text-sm">{level}</p>
              <p className="text-xs text-gray-400">
                {level === 'NONE' && 'No verification'}
                {level === 'BASIC' && 'Email + Phone'}
                {level === 'STANDARD' && 'ID Verified'}
                {level === 'ENHANCED' && 'Full KYC'}
                {level === 'INSTITUTIONAL' && 'Corporate'}
              </p>
            </button>
          ))}
        </div>

        <div className="bg-gray-700 rounded p-4 text-sm">
          <p className="font-medium mb-2">Current Limits:</p>
          <ul className="text-gray-400 space-y-1">
            <li>• Single Transaction: {profile.single_tx_limit_eth} ETH</li>
            <li>• Daily Limit: {profile.daily_limit_eth} ETH</li>
            <li>• Monthly Limit: {profile.monthly_limit_eth} ETH</li>
          </ul>
        </div>
      </div>

      {/* Entity Type */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">🏢 Entity Type</h2>
        <p className="text-gray-400 text-sm mb-4">
          Set your entity type to apply appropriate limits and compliance rules
        </p>

        <div className="grid grid-cols-5 gap-2">
          {[
            { type: 'UNVERIFIED', desc: 'New accounts', limits: '0.5 ETH/tx' },
            { type: 'RETAIL', desc: 'Individuals', limits: '5 ETH/tx' },
            { type: 'INSTITUTIONAL', desc: 'Corporate', limits: '500 ETH/tx' },
            { type: 'VASP', desc: 'Exchanges', limits: '5,000 ETH/tx' },
            { type: 'HIGH_NET_WORTH', desc: 'Private', limits: '250 ETH/tx' },
          ].map(item => (
            <button
              key={item.type}
              onClick={() => handleSetEntityType(item.type)}
              disabled={saving}
              className={`p-3 rounded text-left ${
                profile.entity_type === item.type 
                  ? 'bg-purple-600 border-2 border-purple-400' 
                  : 'bg-gray-700 hover:bg-gray-600'
              }`}
            >
              <p className="font-medium text-sm">{item.type}</p>
              <p className="text-xs text-gray-400">{item.desc}</p>
              <p className="text-xs text-green-400 mt-1">{item.limits}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Jurisdiction */}
      <div className="bg-gray-800 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">🌍 Jurisdiction</h2>
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm text-gray-400 mb-1">Country Code</label>
            <input
              type="text"
              placeholder="e.g., GB, US, DE"
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value.toUpperCase())}
              maxLength={2}
              className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-2"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={() => handleUpdateProfile({ jurisdiction })}
              disabled={saving || jurisdiction.length !== 2}
              className="bg-blue-600 hover:bg-blue-700 px-6 py-2 rounded disabled:opacity-50"
            >
              Update
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          Current: {profile.jurisdiction || 'Not set'} 
          {profile.jurisdiction === 'UNKNOWN' && ' (Transactions may be restricted)'}
        </p>
      </div>

      {/* Activity Summary */}
      <div className="bg-gray-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">📊 Activity Summary</h2>
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gray-700 rounded p-4 text-center">
            <p className="text-2xl font-bold">{profile.total_transactions}</p>
            <p className="text-sm text-gray-400">Total Transactions</p>
          </div>
          <div className="bg-gray-700 rounded p-4 text-center">
            <p className="text-2xl font-bold">{profile.daily_volume_eth.toFixed(2)}</p>
            <p className="text-sm text-gray-400">Daily Volume (ETH)</p>
          </div>
          <div className="bg-gray-700 rounded p-4 text-center">
            <p className="text-2xl font-bold">{profile.monthly_volume_eth.toFixed(2)}</p>
            <p className="text-sm text-gray-400">Monthly Volume (ETH)</p>
          </div>
          <div className="bg-gray-700 rounded p-4 text-center">
            <p className="text-2xl font-bold">
              {((profile.daily_volume_eth / profile.daily_limit_eth) * 100).toFixed(0)}%
            </p>
            <p className="text-sm text-gray-400">Daily Limit Used</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <AppLayout>
      <SettingsContent />
    </AppLayout>
  );
}
