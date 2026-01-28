'use client';

/**
 * AlertChannelConfig Component
 * 
 * Configure notification delivery channels
 * 
 * Ground Truth Reference:
 * - Multi-channel notification support
 * - Channel-specific settings
 * - Test notification capability
 */

import React, { useState } from 'react';
import {
  DeliveryChannel,
  NotificationPreferences,
  AlertPriority,
} from '@/types/alert';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

// Simplified channel config for UI
interface UIAlertChannel {
  id: string;
  name: string;
  type: DeliveryChannel;
  enabled: boolean;
  config: Record<string, unknown>;
  createdAt: number;
}

interface AlertChannelConfigProps {
  channels: UIAlertChannel[];
  preferences: UINotificationPreferences;
  onToggleChannel: (channelId: string, enabled: boolean) => void;
  onUpdateChannel: (channel: UIAlertChannel) => void;
  onAddChannel: (channel: Omit<UIAlertChannel, 'id' | 'createdAt'>) => void;
  onUpdatePreferences: (prefs: UINotificationPreferences) => void;
  onTestChannel: (channelId: string) => void;
}

// UI-friendly notification preferences
interface UINotificationPreferences {
  soundEnabled: boolean;
  desktopNotifications: boolean;
  emailDigest: boolean;
  digestFrequency?: 'hourly' | 'daily' | 'weekly';
  quietHoursEnabled: boolean;
  quietHoursStart?: string;
  quietHoursEnd?: string;
}

const CHANNEL_ICONS: Record<DeliveryChannel, string> = {
  [DeliveryChannel.SLACK]: '💬',
  [DeliveryChannel.EMAIL]: '📧',
  [DeliveryChannel.WEBHOOK]: '🔗',
  [DeliveryChannel.SMS]: '📱',
  [DeliveryChannel.TELEGRAM]: '✈️',
  [DeliveryChannel.UI]: '🖥️',
  [DeliveryChannel.PUSH]: '🔔',
};

const CHANNEL_COLORS: Record<DeliveryChannel, string> = {
  [DeliveryChannel.SLACK]: 'bg-purple-600',
  [DeliveryChannel.EMAIL]: 'bg-blue-600',
  [DeliveryChannel.WEBHOOK]: 'bg-green-600',
  [DeliveryChannel.SMS]: 'bg-orange-600',
  [DeliveryChannel.TELEGRAM]: 'bg-sky-600',
  [DeliveryChannel.UI]: 'bg-cyan-600',
  [DeliveryChannel.PUSH]: 'bg-indigo-600',
};

// ═══════════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function ChannelCard({
  channel,
  onToggle,
  onTest,
  onEdit,
}: {
  channel: UIAlertChannel;
  onToggle: (enabled: boolean) => void;
  onTest: () => void;
  onEdit: () => void;
}) {
  return (
    <div className={`rounded-lg border p-4 transition-all ${
      channel.enabled 
        ? 'bg-slate-800 border-slate-600' 
        : 'bg-slate-900 border-slate-700 opacity-60'
    }`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${CHANNEL_COLORS[channel.type] || 'bg-slate-600'}`}>
            <span className="text-xl">{CHANNEL_ICONS[channel.type] || '📡'}</span>
          </div>
          
          <div>
            <h4 className="font-medium text-white">{channel.name}</h4>
            <p className="text-xs text-slate-400">{channel.type}</p>
          </div>
        </div>
        
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={channel.enabled}
            onChange={(e) => onToggle(e.target.checked)}
            className="sr-only peer"
          />
          <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none rounded-full peer 
                        peer-checked:after:translate-x-full peer-checked:bg-cyan-600
                        after:content-[''] after:absolute after:top-[2px] after:left-[2px] 
                        after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
        </label>
      </div>
      
      <div className="mt-3 pt-3 border-t border-slate-700">
        <div className="text-xs text-slate-400 space-y-1">
          {channel.type === DeliveryChannel.SLACK && channel.config.webhookUrl ? (
            <p>Webhook: {String(channel.config.webhookUrl).substring(0, 30)}...</p>
          ) : null}
          {channel.type === DeliveryChannel.EMAIL && channel.config.recipients ? (
            <p>Recipients: {(channel.config.recipients as string[]).slice(0, 2).join(', ')}{(channel.config.recipients as string[]).length > 2 ? '...' : ''}</p>
          ) : null}
          {channel.type === DeliveryChannel.WEBHOOK && channel.config.url ? (
            <p>URL: {String(channel.config.url).substring(0, 40)}...</p>
          ) : null}
          <p>Created: {new Date(channel.createdAt).toLocaleDateString()}</p>
        </div>
        
        <div className="flex gap-2 mt-3">
          <button
            onClick={onTest}
            disabled={!channel.enabled}
            className="flex-1 px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 
                     text-slate-300 rounded transition-colors disabled:opacity-50"
          >
            Test
          </button>
          <button
            onClick={onEdit}
            className="flex-1 px-3 py-1.5 text-xs bg-slate-700 hover:bg-slate-600 
                     text-slate-300 rounded transition-colors"
          >
            Edit
          </button>
        </div>
      </div>
    </div>
  );
}

function AddChannelModal({
  onAdd,
  onClose,
}: {
  onAdd: (channel: Omit<UIAlertChannel, 'id' | 'createdAt'>) => void;
  onClose: () => void;
}) {
  const [type, setType] = useState<DeliveryChannel>(DeliveryChannel.SLACK);
  const [name, setName] = useState('');
  const [config, setConfig] = useState<Record<string, unknown>>({});
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAdd({ name, type, enabled: true, config });
    onClose();
  };
  
  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-slate-900 rounded-xl border border-slate-700 p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold text-white mb-4">Add Notification Channel</h3>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Channel Type
            </label>
            <select
              value={type}
              onChange={(e) => setType(e.target.value as DeliveryChannel)}
              className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white"
            >
              <option value={DeliveryChannel.SLACK}>Slack</option>
              <option value={DeliveryChannel.EMAIL}>Email</option>
              <option value={DeliveryChannel.WEBHOOK}>Webhook</option>
              <option value={DeliveryChannel.SMS}>SMS</option>
              <option value={DeliveryChannel.TELEGRAM}>Telegram</option>
              <option value={DeliveryChannel.UI}>In-App</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">
              Channel Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white"
              placeholder="e.g., Team Alerts"
              required
            />
          </div>
          
          {/* Type-specific config */}
          {type === DeliveryChannel.SLACK && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Webhook URL
              </label>
              <input
                type="url"
                value={(config.webhookUrl as string) || ''}
                onChange={(e) => setConfig({ ...config, webhookUrl: e.target.value })}
                className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
                placeholder="https://hooks.slack.com/services/..."
              />
            </div>
          )}
          
          {type === DeliveryChannel.EMAIL && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Recipients (comma-separated)
              </label>
              <input
                type="text"
                value={(config.recipients as string[])?.join(', ') || ''}
                onChange={(e) => setConfig({ ...config, recipients: e.target.value.split(',').map(s => s.trim()) })}
                className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
                placeholder="admin@company.com, security@company.com"
              />
            </div>
          )}
          
          {type === DeliveryChannel.WEBHOOK && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Webhook URL
              </label>
              <input
                type="url"
                value={(config.url as string) || ''}
                onChange={(e) => setConfig({ ...config, url: e.target.value })}
                className="w-full bg-slate-800 border-slate-700 rounded-lg px-3 py-2 text-white text-sm"
                placeholder="https://api.yourservice.com/alerts"
              />
            </div>
          )}
          
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-slate-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-6 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg"
            >
              Add Channel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AlertChannelConfig({
  channels,
  preferences,
  onToggleChannel,
  onUpdateChannel,
  onAddChannel,
  onUpdatePreferences,
  onTestChannel,
}: AlertChannelConfigProps) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingChannel, setEditingChannel] = useState<UIAlertChannel | null>(null);
  
  return (
    <div className="space-y-6">
      {/* Global Preferences */}
      <div className="bg-slate-900 rounded-xl border border-slate-700 p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Notification Preferences</h3>
        
        <div className="grid grid-cols-2 gap-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={preferences.soundEnabled}
              onChange={(e) => onUpdatePreferences({ ...preferences, soundEnabled: e.target.checked })}
              className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-cyan-500"
            />
            <span className="text-sm text-slate-300">Sound alerts</span>
          </label>
          
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={preferences.desktopNotifications}
              onChange={(e) => onUpdatePreferences({ ...preferences, desktopNotifications: e.target.checked })}
              className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-cyan-500"
            />
            <span className="text-sm text-slate-300">Desktop notifications</span>
          </label>
          
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={preferences.emailDigest}
              onChange={(e) => onUpdatePreferences({ ...preferences, emailDigest: e.target.checked })}
              className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-cyan-500"
            />
            <span className="text-sm text-slate-300">Email digest</span>
          </label>
          
          {preferences.emailDigest && (
            <select
              value={preferences.digestFrequency || 'daily'}
              onChange={(e) => onUpdatePreferences({ ...preferences, digestFrequency: e.target.value as 'hourly' | 'daily' | 'weekly' })}
              className="bg-slate-800 border-slate-700 rounded px-3 py-1 text-sm text-white"
            >
              <option value="hourly">Hourly</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          )}
        </div>
        
        <div className="mt-4 pt-4 border-t border-slate-700">
          <h4 className="text-sm font-medium text-slate-300 mb-2">Quiet Hours</h4>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={preferences.quietHoursEnabled}
                onChange={(e) => onUpdatePreferences({ ...preferences, quietHoursEnabled: e.target.checked })}
                className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-cyan-500"
              />
              <span className="text-sm text-slate-400">Enable</span>
            </label>
            
            {preferences.quietHoursEnabled && (
              <>
                <input
                  type="time"
                  value={preferences.quietHoursStart || '22:00'}
                  onChange={(e) => onUpdatePreferences({ ...preferences, quietHoursStart: e.target.value })}
                  className="bg-slate-800 border-slate-700 rounded px-2 py-1 text-sm text-white"
                />
                <span className="text-slate-400">to</span>
                <input
                  type="time"
                  value={preferences.quietHoursEnd || '08:00'}
                  onChange={(e) => onUpdatePreferences({ ...preferences, quietHoursEnd: e.target.value })}
                  className="bg-slate-800 border-slate-700 rounded px-2 py-1 text-sm text-white"
                />
              </>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Only CRITICAL alerts will be sent during quiet hours
          </p>
        </div>
      </div>
      
      {/* Channels */}
      <div className="bg-slate-900 rounded-xl border border-slate-700 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white">Notification Channels</h3>
          <button
            onClick={() => setShowAddModal(true)}
            className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition-colors"
          >
            + Add Channel
          </button>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {channels.map((channel) => (
            <ChannelCard
              key={channel.id}
              channel={channel}
              onToggle={(enabled) => onToggleChannel(channel.id, enabled)}
              onTest={() => onTestChannel(channel.id)}
              onEdit={() => setEditingChannel(channel)}
            />
          ))}
          
          {channels.length === 0 && (
            <div className="col-span-full text-center py-8 text-slate-400">
              <p className="text-4xl mb-2">📭</p>
              <p>No notification channels configured</p>
              <button
                onClick={() => setShowAddModal(true)}
                className="mt-2 text-cyan-400 hover:text-cyan-300"
              >
                Add your first channel
              </button>
            </div>
          )}
        </div>
      </div>
      
      {/* Modals */}
      {showAddModal && (
        <AddChannelModal
          onAdd={onAddChannel}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  );
}
