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

export default function SystemSettingsPage() {
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [loading] = useState(false);
  const [error] = useState<string | null>('No settings API configured');
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
    <div className="space-y-6">
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Link href="/war-room" className="text-mutedText hover:text-text">
              ← War Room
            </Link>
          </div>
          <h1 className="text-3xl font-bold">System Settings</h1>
          <p className="text-mutedText mt-1">Configure platform-wide settings and thresholds</p>
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
          <div key={category} className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
            <div className="p-4 border-b border-borderSubtle bg-slate-700/30">
              <h2 className="font-semibold text-lg">{category}</h2>
            </div>
            <div className="divide-y divide-slate-700">
              {settings.filter(s => s.category === category).map(setting => (
                <div key={setting.id} className="p-4 flex items-center justify-between">
                  <div className="flex-1">
                    <div className="font-medium">{setting.name}</div>
                    <div className="text-sm text-mutedText">{setting.description}</div>
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
                        className="w-32 bg-slate-700 border border-borderSubtle rounded-lg px-3 py-2 text-right focus:outline-none focus:border-indigo-500"
                      />
                    )}
                    {setting.type === 'select' && (
                      <select
                        value={setting.value as string}
                        onChange={e => updateSetting(setting.id, e.target.value)}
                        className="bg-slate-700 border border-borderSubtle rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
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
                        className="w-64 bg-slate-700 border border-borderSubtle rounded-lg px-3 py-2 focus:outline-none focus:border-indigo-500"
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
            <div className="text-sm text-mutedText">Reset all settings to their default values</div>
          </div>
          <button className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg">
            Reset to Defaults
          </button>
        </div>
      </div>
    </div>
  );
}
