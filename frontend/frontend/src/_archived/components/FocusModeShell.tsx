'use client';

/**
 * Focus Mode Shell
 * 
 * Clean, minimal shell for R1/R2 users (End Users)
 * 
 * Features:
 * - Minimal chrome
 * - No charts or analytics
 * - Trust pillar indicators (qualitative, no numbers)
 * - Simple navigation
 * - Clear action prompts
 */

import React, { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface FocusModeShellProps {
  children: ReactNode;
}

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS (Simple inline SVGs)
// ═══════════════════════════════════════════════════════════════════════════════

const HomeIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
    <polyline points="9 22 9 12 15 12 15 22"></polyline>
  </svg>
);

const SendIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"></line>
    <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
  </svg>
);

const HistoryIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <polyline points="12 6 12 12 16 14"></polyline>
  </svg>
);

const ShieldIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
  </svg>
);

const UserIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
    <circle cx="12" cy="7" r="4"></circle>
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION ITEMS
// ═══════════════════════════════════════════════════════════════════════════════

const FOCUS_NAV_ITEMS: NavItem[] = [
  { label: 'Home', href: '/focus', icon: <HomeIcon /> },
  { label: 'Send', href: '/focus/transfer', icon: <SendIcon /> },
  { label: 'History', href: '/focus/history', icon: <HistoryIcon /> },
  { label: 'Trust', href: '/focus/trust', icon: <ShieldIcon /> },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function FocusModeShell({ children }: FocusModeShellProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { session, logout, roleLabel } = useAuth();
  
  // CHECK FOR EMBED MODE - When embedded in Flutter, hide all navigation chrome
  const isEmbedMode = searchParams.get('embed') === 'true';
  
  // In embed mode, return ONLY the children - no header, no bottom nav
  // Flutter app provides all navigation via its own shell
  if (isEmbedMode) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100">
        {children}
      </div>
    );
  }
  
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 flex flex-col">
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Header - Minimal and Clean */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 sticky top-0 z-50">
        <div className="max-w-2xl mx-auto flex items-center justify-between">
          {/* Logo */}
          <Link href="/focus" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
              <ShieldIcon />
            </div>
            <span className="font-semibold text-gray-900">AMTTP</span>
          </Link>
          
          {/* User Menu */}
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <div className="text-sm font-medium text-gray-900">
                {roleLabel || 'User'}
              </div>
              <div className="text-xs text-gray-500">
                Protected Account
              </div>
            </div>
            <button
              onClick={logout}
              className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-600 hover:bg-gray-200 transition-colors"
              aria-label="Account"
            >
              <UserIcon />
            </button>
          </div>
        </div>
      </header>
      
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Main Content - Centered and Focused */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <main className="flex-1 px-4 py-6">
        <div className="max-w-2xl mx-auto">
          {children}
        </div>
      </main>
      
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Bottom Navigation - Mobile-friendly */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <nav className="bg-white border-t border-gray-200 px-4 py-2 sticky bottom-0 safe-area-bottom">
        <div className="max-w-2xl mx-auto flex items-center justify-around">
          {FOCUS_NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
            
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`
                  flex flex-col items-center gap-1 px-4 py-2 rounded-lg transition-colors
                  ${isActive 
                    ? 'text-indigo-600 bg-indigo-50' 
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }
                `}
              >
                {item.icon}
                <span className="text-xs font-medium">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
      
      {/* ─────────────────────────────────────────────────────────────────────── */}
      {/* Trust Indicator Bar - Always visible */}
      {/* ─────────────────────────────────────────────────────────────────────── */}
      <div className="fixed bottom-20 left-4 right-4 pointer-events-none">
        <div className="max-w-2xl mx-auto">
          <div className="bg-green-50 border border-green-200 rounded-full px-4 py-2 flex items-center justify-center gap-2 text-sm text-green-700 shadow-sm pointer-events-auto">
            <ShieldIcon />
            <span>Your transactions are protected by AMTTP</span>
          </div>
        </div>
      </div>
    </div>
  );
}
