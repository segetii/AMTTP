'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';

function ConciergeContent() {
  const { profile } = useProfile();
  const [activeTab, setActiveTab] = useState<'support' | 'services' | 'history'>('support');

  if (!profile || profile.entity_type !== 'HIGH_NET_WORTH') {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Access Restricted</h2>
        <p className="text-gray-400">Concierge services are exclusive to HIGH_NET_WORTH accounts.</p>
      </div>
    );
  }

  const manager = {
    name: 'Alexandra Chen',
    title: 'Senior Wealth Manager',
    phone: '+1 (888) 555-0199',
    email: 'a.chen@amttp.vip',
    avatar: '👩‍💼',
    available: true,
  };

  const services = [
    { icon: '📊', name: 'Tax Optimization', desc: 'Cross-jurisdictional tax planning', status: 'Available' },
    { icon: '⚖️', name: 'Legal Advisory', desc: 'Regulatory compliance consultation', status: 'Available' },
    { icon: '🏦', name: 'Banking Relations', desc: 'Private banking introductions', status: 'Available' },
    { icon: '🔒', name: 'Estate Planning', desc: 'Digital asset succession', status: 'Available' },
    { icon: '📈', name: 'Investment Advisory', desc: 'DeFi yield optimization', status: 'Available' },
    { icon: '🛡️', name: 'Security Audit', desc: 'Personal wallet security review', status: 'Scheduled' },
  ];

  const requestHistory = [
    { id: 'req_001', date: '2026-01-10', type: 'Tax Advisory', status: 'Completed', response: 'Report delivered' },
    { id: 'req_002', date: '2026-01-08', type: 'Security Review', status: 'In Progress', response: 'Scheduled for Jan 15' },
    { id: 'req_003', date: '2026-01-05', type: 'Banking Intro', status: 'Completed', response: 'Meeting set with UBS' },
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">🌟 Private Concierge</h1>
      <p className="text-gray-400 mb-6">24/7 dedicated support for your wealth management needs</p>

      {/* Dedicated Manager Card */}
      <div className="bg-gradient-to-r from-purple-900/50 to-pink-900/50 border border-purple-700/50 rounded-lg p-6 mb-6">
        <div className="flex items-center gap-6">
          <div className="text-6xl">{manager.avatar}</div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-2xl font-bold">{manager.name}</h2>
              {manager.available && (
                <span className="bg-green-900 text-green-300 text-xs px-2 py-1 rounded-full flex items-center gap-1">
                  <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                  Available Now
                </span>
              )}
            </div>
            <p className="text-gray-400">{manager.title}</p>
            <div className="flex gap-6 mt-3">
              <a href={`tel:${manager.phone}`} className="text-blue-400 hover:underline">
                📞 {manager.phone}
              </a>
              <a href={`mailto:${manager.email}`} className="text-blue-400 hover:underline">
                ✉️ {manager.email}
              </a>
            </div>
          </div>
          <div className="flex flex-col gap-2">
            <button className="bg-green-600 hover:bg-green-700 px-6 py-3 rounded-lg font-medium">
              📞 Call Now
            </button>
            <button className="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg font-medium">
              💬 Chat
            </button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        {(
          [
            { id: 'support', label: '🎧 Quick Support' },
            { id: 'services', label: '🛎️ Services' },
            { id: 'history', label: '📋 Request History' },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded font-medium transition-colors ${
              activeTab === tab.id ? 'bg-purple-600 text-white' : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'support' && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h3 className="text-xl font-semibold mb-4">Submit Priority Request</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Request Type</label>
              <select className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-3">
                <option>Urgent Transaction Assistance</option>
                <option>Compliance Question</option>
                <option>Technical Support</option>
                <option>Advisory Request</option>
                <option>General Inquiry</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Priority Level</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="priority" className="text-red-500" />
                  <span className="text-red-400">🔴 Critical</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="priority" defaultChecked className="text-yellow-500" />
                  <span className="text-yellow-400">🟡 High</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="radio" name="priority" className="text-blue-500" />
                  <span className="text-blue-400">🔵 Standard</span>
                </label>
              </div>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Description</label>
              <textarea
                rows={4}
                placeholder="Describe your request in detail..."
                className="w-full bg-gray-700 border border-gray-600 rounded px-4 py-3"
              ></textarea>
            </div>
            <div className="flex justify-between items-center">
              <p className="text-sm text-gray-500">
                ⚡ Critical requests receive response within 15 minutes
              </p>
              <button className="bg-purple-600 hover:bg-purple-700 px-6 py-3 rounded-lg font-medium">
                Submit Request
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'services' && (
        <div className="grid grid-cols-3 gap-4">
          {services.map(service => (
            <div key={service.name} className="bg-gray-800 rounded-lg p-5">
              <div className="text-3xl mb-3">{service.icon}</div>
              <h3 className="font-semibold mb-1">{service.name}</h3>
              <p className="text-sm text-gray-400 mb-3">{service.desc}</p>
              <div className="flex justify-between items-center">
                <span className={`text-xs px-2 py-1 rounded ${
                  service.status === 'Available' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                }`}>
                  {service.status}
                </span>
                <button className="text-blue-400 hover:underline text-sm">Request →</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="bg-gray-800 rounded-lg p-6">
          <table className="w-full">
            <thead>
              <tr className="text-gray-500 text-sm border-b border-gray-700">
                <th className="text-left p-3">Date</th>
                <th className="text-left p-3">Type</th>
                <th className="text-left p-3">Status</th>
                <th className="text-left p-3">Response</th>
                <th className="text-center p-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {requestHistory.map(req => (
                <tr key={req.id} className="border-b border-gray-700/50">
                  <td className="p-3">{req.date}</td>
                  <td className="p-3">{req.type}</td>
                  <td className="p-3">
                    <span className={`px-2 py-1 rounded text-xs ${
                      req.status === 'Completed' ? 'bg-green-900 text-green-300' : 'bg-yellow-900 text-yellow-300'
                    }`}>
                      {req.status}
                    </span>
                  </td>
                  <td className="p-3 text-gray-400">{req.response}</td>
                  <td className="p-3 text-center">
                    <button className="text-blue-400 hover:underline text-sm">View</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Emergency Banner */}
      <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mt-6 flex items-center justify-between">
        <div>
          <h3 className="font-bold text-red-400">🚨 Emergency Hotline</h3>
          <p className="text-sm text-gray-400">For urgent security incidents or time-critical matters</p>
        </div>
        <a href="tel:+18885550911" className="bg-red-600 hover:bg-red-700 px-6 py-3 rounded-lg font-medium">
          📞 +1 (888) 555-0911
        </a>
      </div>
    </div>
  );
}

export default function ConciergePage() {
  return (
    <AppLayout>
      <ConciergeContent />
    </AppLayout>
  );
}
