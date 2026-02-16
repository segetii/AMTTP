'use client';

import Link from 'next/link';

export default function WarRoomLandingPage() {
  const sections = [
    {
      title: 'Monitoring & Alerts',
      description: 'Real-time transaction monitoring and risk alerts',
      items: [
        { name: 'Dashboard', href: '/war-room', icon: '📊', description: 'Overview of all activity' },
        { name: 'Alerts', href: '/war-room/alerts', icon: '🔔', description: 'Active alerts and notifications' },
        { name: 'Transactions', href: '/war-room/transactions', icon: '💸', description: 'Transaction monitoring' },
        { name: 'Flagged Queue', href: '/war-room/flagged-queue', icon: '🚩', description: 'Review flagged transactions' },
      ],
    },
    {
      title: 'Detection & Analysis',
      description: 'ML-powered risk detection and graph analysis',
      items: [
        { name: 'Detection Studio', href: '/war-room/detection-studio', icon: '🔬', description: 'ML model configuration' },
        { name: 'Graph Explorer', href: '/war-room/detection/graph', icon: '🕸️', description: 'Transaction graph analysis' },
        { name: 'ML Models', href: '/war-room/detection/models', icon: '🤖', description: 'Model performance metrics' },
        { name: 'Risk Scoring', href: '/war-room/detection/risk', icon: '📈', description: 'Risk score configuration' },
      ],
    },
    {
      title: 'Compliance & Policies',
      description: 'AML/KYC compliance and policy management',
      items: [
        { name: 'Compliance', href: '/war-room/compliance', icon: '✅', description: 'Compliance dashboard' },
        { name: 'Policy Engine', href: '/war-room/policy-engine', icon: '📜', description: 'Configure transaction policies' },
        { name: 'Policies', href: '/policies', icon: '⚙️', description: 'Manage policy rules' },
        { name: 'Disputes', href: '/war-room/disputes', icon: '⚖️', description: 'Dispute management' },
      ],
    },
    {
      title: 'Enforcement & Actions',
      description: 'Account controls and enforcement actions',
      items: [
        { name: 'Enforcement', href: '/war-room/enforcement', icon: '🔒', description: 'Freeze/unfreeze accounts' },
        { name: 'Pending Approvals', href: '/war-room/pending-approvals', icon: '⏳', description: 'Approve pending requests' },
        { name: 'Multisig Queue', href: '/war-room/multisig', icon: '🔑', description: 'Multisig approval queue' },
        { name: 'Cross-Chain', href: '/war-room/cross-chain', icon: '🔗', description: 'Cross-chain operations' },
      ],
    },
    {
      title: 'Audit & Reports',
      description: 'Audit trails, reports, and compliance documentation',
      items: [
        { name: 'Audit Trail', href: '/war-room/audit', icon: '📋', description: 'Complete audit log' },
        { name: 'Reports', href: '/war-room/reports', icon: '📄', description: 'Generate compliance reports' },
        { name: 'UI Snapshots', href: '/war-room/ui-snapshots', icon: '📸', description: 'UI state audit trail' },
      ],
    },
    {
      title: 'Administration',
      description: 'System settings and user management',
      items: [
        { name: 'User Management', href: '/war-room/user-management', icon: '👥', description: 'Manage team members' },
        { name: 'Roles', href: '/war-room/admin/roles', icon: '🎭', description: 'Role permissions' },
        { name: 'System Settings', href: '/war-room/system-settings', icon: '⚙️', description: 'Platform configuration' },
        { name: 'Settings', href: '/war-room/settings', icon: '🔧', description: 'War Room settings' },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">War Room</h1>
        <p className="text-mutedText text-lg">
          Institutional compliance console for monitoring, detection, and enforcement
        </p>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-5 gap-4 mb-8">
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-3xl font-bold text-green-400">1,247</div>
          <div className="text-mutedText text-sm">Transactions Today</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-3xl font-bold text-yellow-400">12</div>
          <div className="text-mutedText text-sm">Pending Review</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-3xl font-bold text-red-400">3</div>
          <div className="text-mutedText text-sm">High Risk Alerts</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-3xl font-bold text-purple-400">5</div>
          <div className="text-mutedText text-sm">Active Disputes</div>
        </div>
        <div className="bg-surface rounded-xl p-4 border border-borderSubtle">
          <div className="text-3xl font-bold text-blue-400">8</div>
          <div className="text-mutedText text-sm">Awaiting Approval</div>
        </div>
      </div>

      {/* Sections Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sections.map(section => (
          <div key={section.title} className="bg-surface rounded-xl border border-borderSubtle overflow-hidden">
            <div className="p-4 border-b border-borderSubtle bg-slate-700/30">
              <h2 className="font-semibold text-lg">{section.title}</h2>
              <p className="text-sm text-mutedText">{section.description}</p>
            </div>
            <div className="p-2">
              {section.items.map(item => (
                <Link 
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-700/50 transition-colors"
                >
                  <div className="text-2xl">{item.icon}</div>
                  <div>
                    <div className="font-medium">{item.name}</div>
                    <div className="text-xs text-mutedText">{item.description}</div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-8 text-center text-mutedText text-sm">
        <p>AMTTP War Room • Institutional Compliance Console</p>
        <p className="mt-1">Powered by ML Risk Detection, Kleros Arbitration, and On-Chain Policy Engine</p>
      </div>
    </div>
  );
}
