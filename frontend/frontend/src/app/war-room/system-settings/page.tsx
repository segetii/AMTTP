'use client';

import { useState } from 'react';
import Link from 'next/link';

interface SystemSetting {
  id: string;
  category: string;
  name: string;
  description: string;
  type: 'toggle' | 'number' | 'select' | 'text';
  value: string | number | boolean;
  options?: string[];
}

const mockSettings: SystemSetting[] = [
  // Risk & ML Settings
  { id: '1', category: 'Risk & ML', name: 'ML Risk Threshold', description: 'Transactions above this score are flagged', type: 'number', value: 75 },
  { id: '2', category: 'Risk & ML', name: 'Auto-Escrow Threshold', description: 'Automatically escrow if risk score exceeds', type: 'number', value: 90 },
  { id: '3', category: 'Risk & ML', name: 'ML Model Version', description: 'Active ML model for risk scoring', type: 'select', value: 'v2.3.1', options: ['v2.3.1', 'v2.2.0', 'v2.1.5'] },
  { id: '4', category: 'Risk & ML', name: 'Real-time Scoring', description: 'Score transactions in real-time', type: 'toggle', value: true },
  
  // Velocity Limits
  { id: '5', category: 'Velocity Limits', name: 'Daily Transfer Limit', description: 'Default daily limit per user', type: 'number', value: 50000 },
  { id: '6', category: 'Velocity Limits', name: 'Single Transaction Limit', description: 'Max single transaction amount', type: 'number', value: 25000 },
  { id: '7', category: 'Velocity Limits', name: 'Hourly Transaction Count', description: 'Max transactions per hour', type: 'number', value: 10 },
  
  // Compliance
  { id: '8', category: 'Compliance', name: 'KYC Required', description: 'Require KYC for all users', type: 'toggle', value: true },
  { id: '9', category: 'Compliance', name: 'Sanctions Screening', description: 'Screen against OFAC/EU lists', type: 'toggle', value: true },
  { id: '10', category: 'Compliance', name: 'PEP Screening', description: 'Screen for Politically Exposed Persons', type: 'toggle', value: true },
  { id: '11', category: 'Compliance', name: 'Travel Rule Threshold', description: 'Apply travel rule above this amount', type: 'number', value: 1000 },
  
  // Approvals
  { id: '12', category: 'Approvals', name: 'Multisig Required', description: 'Require multisig for enforcement actions', type: 'toggle', value: true },
  { id: '13', category: 'Approvals', name: 'Required Approvers', description: 'Number of approvers for multisig', type: 'number', value: 3 },
  { id: '14', category: 'Approvals', name: 'Approval Timeout', description: 'Hours before approval request expires', type: 'number', value: 24 },
  
  // Notifications
  { id: '15', category: 'Notifications', name: 'Email Alerts', description: 'Send email for critical events', type: 'toggle', value: true },
  { id: '16', category: 'Notifications', name: 'Slack Integration', description: 'Post alerts to Slack channel', type: 'toggle', value: false },
  { id: '17', category: 'Notifications', name: 'Webhook URL', description: 'External webhook for events', type: 'text', value: 'https://hooks.example.com/amttp' },
];

export default function SystemSettingsPage() {
  const [settings, setSettings] = useState(mockSettings);
  const [hasChanges, setHasChanges] = useState(false);

  const categories = [...new Set(settings.map(s => s.category))];

  const updateSetting = (id: string, value: string | number | boolean) => {
    setSettings(prev => prev.map(s => s.id === id ? { ...s, value } : s));
    setHasChanges(true);
  };

  const saveChanges = () => {
    // In real app, save to backend
    setHasChanges(false);
    alert('Settings saved successfully!');
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-slate-400 hover:text-white">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">System Settings</h1>
          <p className="text-slate-400 mt-1">Configure platform-wide settings and thresholds</p>
        </div>
        {hasChanges && (
          <button 
            onClick={saveChanges}
            className="px-6 py-2 bg-green-600 hover:bg-green-700 rounded-lg flex items-center gap-2"
          >
            Save Changes
          </button>
        )}
      </div>

      {/* Settings by Category */}
      <div className="space-y-8">
        {categories.map(category => (
          <div key={category} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
            <div className="p-4 border-b border-slate-700 bg-slate-700/30">
              <h2 className="font-semibold text-lg">{category}</h2>
            </div>
            <div className="divide-y divide-slate-700">
              {settings.filter(s => s.category === category).map(setting => (
                <div key={setting.id} className="p-4 flex items-center justify-between">
                  <div className="flex-1">
                    <div className="font-medium">{setting.name}</div>
                    <div className="text-sm text-slate-400">{setting.description}</div>
                  </div>
                  <div className="ml-4">
                    {setting.type === 'toggle' && (
                      <button
                        onClick={() => updateSetting(setting.id, !setting.value)}
                        className={`w-14 h-7 rounded-full transition-colors relative ${
                          setting.value ? 'bg-green-600' : 'bg-slate-600'
                        }`}
                      >
                        <div 
                          className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform ${
                            setting.value ? 'translate-x-8' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    )}
                    {setting.type === 'number' && (
                      <input
                        type="number"
                        value={setting.value as number}
                        onChange={e => updateSetting(setting.id, parseInt(e.target.value) || 0)}
                        className="w-32 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-right focus:outline-none focus:border-indigo-500"
                      />
                    )}
                    {setting.type === 'select' && (
                      <select
                        value={setting.value as string}
                        onChange={e => updateSetting(setting.id, e.target.value)}
                        className="bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
                      >
                        {setting.options?.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    )}
                    {setting.type === 'text' && (
                      <input
                        type="text"
                        value={setting.value as string}
                        onChange={e => updateSetting(setting.id, e.target.value)}
                        className="w-64 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Danger Zone */}
      <div className="mt-8 bg-red-900/20 rounded-xl border border-red-500/30 p-6">
        <h2 className="font-semibold text-lg text-red-400 mb-4">Danger Zone</h2>
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Reset All Settings</div>
            <div className="text-sm text-slate-400">Reset all settings to their default values</div>
          </div>
          <button className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg">
            Reset to Defaults
          </button>
        </div>
      </div>
    </div>
  );
}
