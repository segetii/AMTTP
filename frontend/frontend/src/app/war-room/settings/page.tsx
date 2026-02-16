'use client';

/**
 * War Room Settings Page
 * 
 * System settings for admins
 * RBAC: R5+ required (Platform Admin, Super Admin)
 */

import React, { useState } from 'react';
import { 
  Cog6ToothIcon,
  ShieldCheckIcon,
  BellIcon,
  GlobeAltIcon,
  KeyIcon,
  ServerIcon,
  DocumentTextIcon,
  CheckIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('general');
  const [saved, setSaved] = useState(false);

  // General Settings
  const [systemName, setSystemName] = useState('AMTTP Production');
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [debugMode, setDebugMode] = useState(false);

  // Security Settings
  const [mfaRequired, setMfaRequired] = useState(true);
  const [sessionTimeout, setSessionTimeout] = useState(30);
  const [ipWhitelist, setIpWhitelist] = useState('');

  // Notification Settings
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [slackAlerts, setSlackAlerts] = useState(false);
  const [alertThreshold, setAlertThreshold] = useState(0.7);

  // API Settings
  const [rateLimitEnabled, setRateLimitEnabled] = useState(true);
  const [rateLimit, setRateLimit] = useState(1000);
  const [apiVersion, setApiVersion] = useState('v2');

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const tabs = [
    { id: 'general', label: 'General', icon: Cog6ToothIcon },
    { id: 'security', label: 'Security', icon: ShieldCheckIcon },
    { id: 'notifications', label: 'Notifications', icon: BellIcon },
    { id: 'api', label: 'API', icon: GlobeAltIcon },
    { id: 'integrations', label: 'Integrations', icon: ServerIcon },
    { id: 'compliance', label: 'Compliance', icon: DocumentTextIcon },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-text">System Settings</h1>
          <p className="text-mutedText mt-1">Configure system-wide settings and preferences</p>
        </div>
        <button 
          onClick={handleSave}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors"
        >
          {saved ? (
            <>
              <CheckIcon className="w-5 h-5" />
              Saved!
            </>
          ) : (
            <>
              <Cog6ToothIcon className="w-5 h-5" />
              Save Changes
            </>
          )}
        </button>
      </div>

      <div className="flex gap-6">
        {/* Tabs Sidebar */}
        <div className="w-64 shrink-0">
          <nav className="space-y-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-left transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-text'
                    : 'text-mutedText hover:bg-surface hover:text-text'
                }`}
              >
                <tab.icon className="w-5 h-5" />
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 bg-surface rounded-lg border border-borderSubtle p-6">
          {/* General Settings */}
          {activeTab === 'general' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">General Settings</h2>
              
              <div>
                <label className="block text-mutedText text-sm mb-2">System Name</label>
                <input
                  type="text"
                  value={systemName}
                  onChange={(e) => setSystemName(e.target.value)}
                  className="w-full px-4 py-2 bg-background border border-borderSubtle rounded-lg text-text focus:outline-none focus:border-blue-500"
                />
              </div>

              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Maintenance Mode</p>
                  <p className="text-mutedText text-sm">Temporarily disable user access for maintenance</p>
                </div>
                <button
                  onClick={() => setMaintenanceMode(!maintenanceMode)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    maintenanceMode ? 'bg-red-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    maintenanceMode ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>

              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Debug Mode</p>
                  <p className="text-mutedText text-sm">Enable verbose logging and debug information</p>
                </div>
                <button
                  onClick={() => setDebugMode(!debugMode)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    debugMode ? 'bg-blue-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    debugMode ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>
            </div>
          )}

          {/* Security Settings */}
          {activeTab === 'security' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">Security Settings</h2>
              
              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Require MFA</p>
                  <p className="text-mutedText text-sm">Require multi-factor authentication for all users</p>
                </div>
                <button
                  onClick={() => setMfaRequired(!mfaRequired)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    mfaRequired ? 'bg-green-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    mfaRequired ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>

              <div>
                <label className="block text-mutedText text-sm mb-2">Session Timeout (minutes)</label>
                <input
                  type="number"
                  value={sessionTimeout}
                  onChange={(e) => setSessionTimeout(Number(e.target.value))}
                  className="w-32 px-4 py-2 bg-background border border-borderSubtle rounded-lg text-text focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-mutedText text-sm mb-2">IP Whitelist (comma-separated)</label>
                <textarea
                  value={ipWhitelist}
                  onChange={(e) => setIpWhitelist(e.target.value)}
                  placeholder="e.g., 192.168.1.1, 10.0.0.0/24"
                  className="w-full px-4 py-2 bg-background border border-borderSubtle rounded-lg text-text focus:outline-none focus:border-blue-500 h-24"
                />
              </div>
            </div>
          )}

          {/* Notification Settings */}
          {activeTab === 'notifications' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">Notification Settings</h2>
              
              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Email Alerts</p>
                  <p className="text-mutedText text-sm">Send critical alerts via email</p>
                </div>
                <button
                  onClick={() => setEmailAlerts(!emailAlerts)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    emailAlerts ? 'bg-green-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    emailAlerts ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>

              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Slack Alerts</p>
                  <p className="text-mutedText text-sm">Send alerts to Slack channel</p>
                </div>
                <button
                  onClick={() => setSlackAlerts(!slackAlerts)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    slackAlerts ? 'bg-green-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    slackAlerts ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>

              <div>
                <label className="block text-mutedText text-sm mb-2">Alert Threshold (Risk Score)</label>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={alertThreshold}
                    onChange={(e) => setAlertThreshold(Number(e.target.value))}
                    className="flex-1"
                  />
                  <span className="text-text w-12">{alertThreshold.toFixed(1)}</span>
                </div>
              </div>
            </div>
          )}

          {/* API Settings */}
          {activeTab === 'api' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">API Settings</h2>
              
              <div className="flex items-center justify-between py-3 border-b border-borderSubtle">
                <div>
                  <p className="text-text font-medium">Rate Limiting</p>
                  <p className="text-mutedText text-sm">Enable API rate limiting</p>
                </div>
                <button
                  onClick={() => setRateLimitEnabled(!rateLimitEnabled)}
                  className={`relative w-12 h-6 rounded-full transition-colors ${
                    rateLimitEnabled ? 'bg-green-600' : 'bg-slate-600'
                  }`}
                >
                  <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                    rateLimitEnabled ? 'left-7' : 'left-1'
                  }`} />
                </button>
              </div>

              <div>
                <label className="block text-mutedText text-sm mb-2">Rate Limit (requests/minute)</label>
                <input
                  type="number"
                  value={rateLimit}
                  onChange={(e) => setRateLimit(Number(e.target.value))}
                  className="w-32 px-4 py-2 bg-background border border-borderSubtle rounded-lg text-text focus:outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="block text-mutedText text-sm mb-2">API Version</label>
                <select
                  value={apiVersion}
                  onChange={(e) => setApiVersion(e.target.value)}
                  className="px-4 py-2 bg-background border border-borderSubtle rounded-lg text-text focus:outline-none focus:border-blue-500"
                >
                  <option value="v1">v1 (Legacy)</option>
                  <option value="v2">v2 (Current)</option>
                  <option value="v3">v3 (Beta)</option>
                </select>
              </div>

              <div className="p-4 bg-background rounded-lg border border-borderSubtle">
                <p className="text-mutedText text-sm mb-2">API Endpoint</p>
                <code className="text-blue-400">https://api.amttp.io/{apiVersion}/</code>
              </div>
            </div>
          )}

          {/* Integrations */}
          {activeTab === 'integrations' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">Integrations</h2>
              
              <div className="grid gap-4">
                {[
                  { name: 'Memgraph', status: 'connected', icon: '🔗' },
                  { name: 'MongoDB', status: 'connected', icon: '🍃' },
                  { name: 'Redis', status: 'connected', icon: '🔴' },
                  { name: 'IPFS (Helia)', status: 'connected', icon: '🌐' },
                  { name: 'Vault', status: 'connected', icon: '🔐' },
                  { name: 'LayerZero', status: 'configured', icon: '⛓️' },
                ].map((integration) => (
                  <div key={integration.name} className="flex items-center justify-between p-4 bg-background rounded-lg border border-borderSubtle">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{integration.icon}</span>
                      <div>
                        <p className="text-text font-medium">{integration.name}</p>
                        <p className="text-mutedText text-sm capitalize">{integration.status}</p>
                      </div>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      integration.status === 'connected' 
                        ? 'bg-green-900/50 text-green-400 border border-green-700'
                        : 'bg-blue-900/50 text-blue-400 border border-blue-700'
                    }`}>
                      {integration.status === 'connected' ? 'Connected' : 'Configured'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Compliance */}
          {activeTab === 'compliance' && (
            <div className="space-y-6">
              <h2 className="text-lg font-semibold text-text">Compliance Settings</h2>
              
              <div className="grid gap-4">
                {[
                  { name: 'FCA Compliance', enabled: true },
                  { name: 'MiCA Compliance', enabled: true },
                  { name: 'FATF Travel Rule', enabled: true },
                  { name: 'KYC/AML Checks', enabled: true },
                  { name: 'Sanctions Screening', enabled: true },
                  { name: 'PEP Screening', enabled: false },
                ].map((item) => (
                  <div key={item.name} className="flex items-center justify-between p-4 bg-background rounded-lg border border-borderSubtle">
                    <p className="text-text font-medium">{item.name}</p>
                    <span className={`px-2 py-1 rounded-full text-xs ${
                      item.enabled 
                        ? 'bg-green-900/50 text-green-400 border border-green-700'
                        : 'bg-slate-700 text-mutedText'
                    }`}>
                      {item.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
