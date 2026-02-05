'use client';

/**
 * War Room Mode Shell
 * 
 * Full-featured dashboard shell for R3/R4/R5/R6 users (Institutional)
 * 
 * Features:
 * - Rich sidebar navigation
 * - System status indicators
 * - UI snapshot hash display
 * - Role badges
 * - Detection studio access
 * - Policy engine access
 * - Multisig panels
 */

import React, { ReactNode, useState } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { useUISnapshot } from '@/lib/ui-snapshot-chain';
import { Role } from '@/types/rbac';
import { PlatformAppSwitcher } from '@/components/shared/PlatformAppSwitcher';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface WarRoomShellProps {
  children: ReactNode;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  badge?: string;
  requiresRole?: Role[];
}

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS (Inline SVGs for reliability)
// ═══════════════════════════════════════════════════════════════════════════════

const DashboardIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="3" y="3" width="7" height="7"></rect>
    <rect x="14" y="3" width="7" height="7"></rect>
    <rect x="14" y="14" width="7" height="7"></rect>
    <rect x="3" y="14" width="7" height="7"></rect>
  </svg>
);

const AlertIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
    <line x1="12" y1="9" x2="12" y2="13"></line>
    <line x1="12" y1="17" x2="12.01" y2="17"></line>
  </svg>
);

const GraphIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="18" cy="5" r="3"></circle>
    <circle cx="6" cy="12" r="3"></circle>
    <circle cx="18" cy="19" r="3"></circle>
    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
  </svg>
);

const PolicyIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
    <polyline points="14 2 14 8 20 8"></polyline>
    <line x1="16" y1="13" x2="8" y2="13"></line>
    <line x1="16" y1="17" x2="8" y2="17"></line>
    <polyline points="10 9 9 9 8 9"></polyline>
  </svg>
);

const ScaleIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="3" x2="12" y2="21"></line>
    <path d="M5 8l-2 3h6L7 8"></path>
    <path d="M17 8l-2 3h6l-2-3"></path>
    <path d="M5 11a4 4 0 0 0 0 8"></path>
    <path d="M19 11a4 4 0 0 1 0 8"></path>
  </svg>
);

const UsersIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
    <circle cx="9" cy="7" r="4"></circle>
    <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
    <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
  </svg>
);

const SettingsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="3"></circle>
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
  </svg>
);

const ShieldIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
  </svg>
);

const UserCogIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="7" r="4"></circle>
    <path d="M5 21v-2a7 7 0 0 1 7-7"></path>
    <circle cx="18" cy="18" r="3"></circle>
    <path d="M18 14v1"></path>
    <path d="M18 21v1"></path>
    <path d="M21 18h1"></path>
    <path d="M14 18h1"></path>
    <path d="M19.5 15.5l.7.7"></path>
    <path d="M15.8 19.2l.7.7"></path>
    <path d="M19.5 20.5l.7-.7"></path>
    <path d="M15.8 16.8l.7-.7"></path>
  </svg>
);

const ChevronIcon = ({ isOpen }: { isOpen: boolean }) => (
  <svg 
    xmlns="http://www.w3.org/2000/svg" 
    width="16" 
    height="16" 
    viewBox="0 0 24 24" 
    fill="none" 
    stroke="currentColor" 
    strokeWidth="2"
    className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
  >
    <polyline points="6 9 12 15 18 9"></polyline>
  </svg>
);

const MenuIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="3" y1="12" x2="21" y2="12"></line>
    <line x1="3" y1="6" x2="21" y2="6"></line>
    <line x1="3" y1="18" x2="21" y2="18"></line>
  </svg>
);

const CloseIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

const GlobeIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="2" y1="12" x2="22" y2="12"></line>
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
  </svg>
);

const BellAlertIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
    <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
  </svg>
);

const BanIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
  </svg>
);

const LinkIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
  </svg>
);

const BeakerIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4.5 3h15"></path>
    <path d="M6 3v16a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V3"></path>
    <path d="M6 14h12"></path>
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════════

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Monitoring',
    items: [
      { label: 'Dashboard', href: '/war-room', icon: <DashboardIcon /> },
      { label: 'Live Alerts', href: '/war-room/alerts', icon: <AlertIcon />, badge: 'LIVE' },
      { label: 'Transaction Flow', href: '/war-room/transactions', icon: <GraphIcon /> },
      { 
        label: 'Cross-Chain', 
        href: '/war-room/cross-chain', 
        icon: <LinkIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
    ],
  },
  {
    label: 'Detection Studio',
    items: [
      { 
        label: 'Visual Studio', 
        href: '/war-room/detection-studio', 
        icon: <BeakerIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { label: 'Graph Analysis', href: '/war-room/detection/graph', icon: <GraphIcon /> },
      { 
        label: 'ML Models', 
        href: '/war-room/detection/models', 
        icon: <DashboardIcon />,
        requiresRole: [Role.R6_SUPER_ADMIN],
      },
      { label: 'Risk Scoring', href: '/war-room/detection/risk', icon: <AlertIcon /> },
    ],
  },
  {
    label: 'Compliance Hub',
    items: [
      { 
        label: 'Unified Dashboard', 
        href: '/compliance', 
        icon: <ShieldIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { 
        label: 'FATF Rules', 
        href: '/compliance/fatf-rules', 
        icon: <GlobeIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { 
        label: 'Sanctions Check', 
        href: '/compliance/sanctions', 
        icon: <BanIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { 
        label: 'Compliance Alerts', 
        href: '/compliance/alerts', 
        icon: <BellAlertIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
    ],
  },
  {
    label: 'Governance',
    items: [
      { 
        label: 'Policy Engine', 
        href: '/policies', 
        icon: <PolicyIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { 
        label: 'Disputes', 
        href: '/war-room/disputes', 
        icon: <ScaleIcon /> 
      },
      { 
        label: 'Multisig Actions', 
        href: '/war-room/multisig', 
        icon: <UsersIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
    ],
  },
  {
    label: 'System',
    items: [
      { 
        label: 'Settings', 
        href: '/war-room/settings', 
        icon: <SettingsIcon />,
        requiresRole: [Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { label: 'Audit Trail', href: '/war-room/audit', icon: <ShieldIcon /> },
      { 
        label: 'Compliance Reports', 
        href: '/war-room/compliance', 
        icon: <PolicyIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
      { 
        label: 'Role Management', 
        href: '/war-room/admin/roles', 
        icon: <UserCogIcon />,
        requiresRole: [Role.R4_INSTITUTION_COMPLIANCE, Role.R5_PLATFORM_ADMIN, Role.R6_SUPER_ADMIN],
      },
    ],
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function WarRoomShell({ children }: WarRoomShellProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { session, logout, roleLabel, roleColor, capabilities, isAuthenticated } = useAuth();
  const { shortHash, isVerified } = useUISnapshot();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<string[]>(
    NAV_GROUPS.filter((g) => g.label !== 'System').map((g) => g.label)
  );
  const isLoading = !session && isAuthenticated;
  const lastUpdatedLabel = new Date().toLocaleTimeString();
  
  // CHECK FOR EMBED MODE - When embedded in Flutter, hide all navigation chrome
  const isEmbedMode = searchParams.get('embed') === 'true';
  
  // In embed mode, return ONLY the children - no sidebar, no header, no footer
  // Flutter app provides all navigation via its own shell
  if (isEmbedMode) {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-100">
        {children}
      </div>
    );
  }
  
  // Preserve important query params (embed, role) when navigating
  const buildHref = (basePath: string): string => {
    const params = new URLSearchParams();
    const embed = searchParams.get('embed');
    const role = searchParams.get('role');
    if (embed) params.set('embed', embed);
    if (role) params.set('role', role);
    const queryString = params.toString();
    return queryString ? `${basePath}?${queryString}` : basePath;
  };
  
  const toggleGroup = (label: string) => {
    setExpandedGroups(prev => 
      prev.includes(label) 
        ? prev.filter(l => l !== label)
        : [...prev, label]
    );
  };
  
  const canSeeNavItem = (item: NavItem): boolean => {
    if (!item.requiresRole) return true;
    if (!session) return false;
    return item.requiresRole.includes(session.role);
  };
  
  return (
    <div className="min-h-screen bg-background text-text flex">
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Sidebar */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <aside 
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 bg-surface border-r border-borderSubtle
          transform transition-transform lg:translate-x-0
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Logo */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-borderSubtle">
          <Link href={buildHref('/war-room')} className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-primary to-purple-500 rounded-lg flex items-center justify-center text-white">
              <ShieldIcon />
            </div>
            <div>
              <span className="font-bold text-white">AMTTP</span>
            </div>
          </Link>
          <button 
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1 hover:bg-slate-700 rounded"
          >
            <CloseIcon />
          </button>
        </div>
        
        {/* Navigation */}
        <nav className="p-4 space-y-4 overflow-y-auto h-[calc(100vh-4rem-8rem)]">
          {NAV_GROUPS.map((group) => {
            const visibleItems = group.items.filter(canSeeNavItem);
            if (visibleItems.length === 0) return null;

            const groupActive = visibleItems.some((item) => pathname?.startsWith(item.href));
            const isExpanded = expandedGroups.includes(group.label) || groupActive;

            return (
              <div key={group.label} className={`rounded-lg border ${groupActive ? 'bg-surface/90 border-primary/40 ring-1 ring-primary/30' : 'bg-surface/60 border-borderSubtle'}`}>
                <button
                  onClick={() => toggleGroup(group.label)}
                  className={`w-full flex items-center justify-between text-xs font-semibold uppercase tracking-wider px-3 py-2 rounded-t-lg transition-colors ${groupActive ? 'text-text' : 'text-mutedText'} ${groupActive ? 'bg-surface' : 'hover:text-text hover:bg-surface/80'}`}
                >
                  <span className="flex items-center gap-2">
                    <span className={`${groupActive ? 'text-text font-bold' : 'text-mutedText'}`}>{group.label}</span>
                  </span>
                  <ChevronIcon isOpen={isExpanded} />
                </button>

                {isExpanded && (
                  <div className="mt-1 space-y-1 px-1 pb-2">
                    {visibleItems.map((item) => {
                      const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');

                      return (
                        <Link
                          key={item.href}
                          href={buildHref(item.href)}
                          className={`
                            flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors
                            ${isActive
                              ? 'bg-surface text-text border border-borderSubtle shadow-sm'
                              : 'text-mutedText hover:bg-surface/70 hover:text-text'
                            }
                          `}
                          onClick={() => setSidebarOpen(false)}
                        >
                          <div className="flex items-center gap-3">
                            <span className={`text-mutedText ${isActive ? 'text-text' : ''}`}>{item.icon}</span>
                            <span className={`font-medium ${isActive ? 'text-text' : ''}`}>{item.label}</span>
                          </div>
                          {item.badge && (
                            <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-warning/20 text-warning border border-warning/40">
                              {item.badge}
                            </span>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>
        
        {/* User Section */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-slate-700 bg-slate-800">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg ${roleColor} flex items-center justify-center text-white font-bold`}>
              {roleLabel?.slice(0, 2) || 'U'}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-white truncate">
                {session?.address?.slice(0, 6)}...{session?.address?.slice(-4) || 'Not connected'}
              </div>
              <div className="text-xs text-slate-400">
                {roleLabel || 'Unknown Role'}
              </div>
            </div>
            <button
              onClick={logout}
              className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white"
              title="Logout"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                <polyline points="16 17 21 12 16 7"></polyline>
                <line x1="21" y1="12" x2="9" y2="12"></line>
              </svg>
            </button>
          </div>
        </div>
      </aside>
      
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Main Area */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-16 bg-surface/70 border-b border-borderSubtle flex items-center justify-between px-4 lg:px-6 sticky top-0 z-40 backdrop-blur-sm">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setSidebarOpen(true)}
              className="lg:hidden p-2 hover:bg-slate-700 rounded-lg"
            >
              <MenuIcon />
            </button>
            
            {/* App Switcher */}
            <PlatformAppSwitcher currentApp="war-room" />
            
            {/* System Status */}
            <div className="hidden md:flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
              <span className="text-sm text-slate-400">System Operational</span>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {/* UI Snapshot Hash */}
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-700/50 rounded-lg">
              <span className="text-xs text-slate-400">UI Hash:</span>
              <code className={`text-xs font-mono ${isVerified ? 'text-green-400' : 'text-red-400'}`}>
                {shortHash || '--------'}
              </code>
              {!isVerified && (
                <span className="text-xs text-red-400 font-semibold">INVALID</span>
              )}
            </div>
            
            {/* Role Badge */}
            <div className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${roleColor} text-white`}>
              {roleLabel}
            </div>
          </div>
        </header>
        
        {/* Content */}
        <main className="flex-1 p-4 lg:p-6 overflow-auto bg-background">
          {isLoading ? <SkeletonDashboard /> : children}
          {!isLoading && (
            <div className="mt-4 text-xs text-mutedText">Last updated at {lastUpdatedLabel}</div>
          )}
        </main>
        
        {/* Footer Status Bar */}
        <footer className="h-8 bg-surface/70 border-t border-borderSubtle flex items-center justify-between px-4 text-xs text-mutedText">
          <div className="flex items-center gap-4">
            <span>AMTTP v2.3</span>
            <span>•</span>
            <span>ML Pipeline: GraphSAGE+LightGBM+XGBoost+β-VAE</span>
          </div>
          <div className="flex items-center gap-4">
            <span>Orchestrator: Connected</span>
            <span>•</span>
            <span>Risk Engine: Active</span>
            <span>•</span>
            <span className={isVerified ? 'text-green-400' : 'text-red-400'}>
              Chain: {isVerified ? 'Verified' : 'Invalid'}
            </span>
          </div>
        </footer>
      </div>

      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Mobile Sidebar Overlay */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-40"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}

function SkeletonDashboard() {
  return (
    <div className="space-y-4" data-testid="warroom-skeleton">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-28 rounded-xl bg-surface/70 border border-borderSubtle animate-pulse" />
        ))}
      </div>
      <div className="rounded-xl bg-surface/70 border border-borderSubtle p-4 animate-pulse">
        <div className="h-4 w-24 bg-borderSubtle rounded mb-3" />
        <div className="space-y-2">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-3 bg-borderSubtle rounded w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}
