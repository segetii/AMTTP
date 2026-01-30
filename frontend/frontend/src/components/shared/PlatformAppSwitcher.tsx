/**
 * Platform App Switcher
 * 
 * Unified app switcher component for AMTTP Platform
 * Provides navigation between Flutter Wallet and Next.js War Room
 */

'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';

// App configuration
const WALLET_APP_URL = process.env.NEXT_PUBLIC_WALLET_URL || 'http://localhost:3010';
const WAR_ROOM_URL = process.env.NEXT_PUBLIC_WAR_ROOM_URL || '/war-room';

interface AppOption {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  url: string;
}

const WalletIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"></path>
    <path d="M3 5v14a2 2 0 0 0 2 2h16v-5"></path>
    <path d="M18 12a2 2 0 0 0 0 4h4v-4Z"></path>
  </svg>
);

const ShieldIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
  </svg>
);

const apps: AppOption[] = [
  {
    id: 'wallet',
    label: 'Wallet App',
    description: 'Transfers & Trust Check',
    icon: <WalletIcon />,
    url: WALLET_APP_URL,
  },
  {
    id: 'war-room',
    label: 'War Room',
    description: 'Compliance & Monitoring',
    icon: <ShieldIcon />,
    url: WAR_ROOM_URL,
  },
];

interface PlatformAppSwitcherProps {
  currentApp?: 'wallet' | 'war-room';
}

export function PlatformAppSwitcher({ currentApp = 'war-room' }: PlatformAppSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentAppData = apps.find(app => app.id === currentApp) || apps[1];

  const handleAppSelect = (app: AppOption) => {
    setIsOpen(false);
    if (app.id !== currentApp) {
      // Navigate to the other app
      window.location.href = app.url;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`
          flex items-center gap-2 px-3 py-1.5 rounded-lg
          border transition-colors
          ${isOpen 
            ? 'bg-white/10 border-white/20' 
            : 'bg-transparent border-white/10 hover:bg-white/5 hover:border-white/15'
          }
        `}
      >
        <span className="text-primary">{currentAppData.icon}</span>
        <span className="text-white text-sm font-medium">{currentAppData.label}</span>
        <svg 
          xmlns="http://www.w3.org/2000/svg" 
          width="16" 
          height="16" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
          className={`text-white/50 transition-transform ${isOpen ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-56 z-50">
          <div className="bg-[#1A1A24] rounded-xl border border-white/10 shadow-xl overflow-hidden">
            {apps.map((app, index) => (
              <React.Fragment key={app.id}>
                {index > 0 && <div className="h-px bg-white/8" />}
                <button
                  onClick={() => handleAppSelect(app)}
                  className={`
                    w-full p-3 flex items-start gap-3 text-left transition-colors
                    ${app.id === currentApp 
                      ? 'bg-primary/10' 
                      : 'hover:bg-white/5'
                    }
                  `}
                >
                  <div className={`
                    w-9 h-9 rounded-lg flex items-center justify-center
                    ${app.id === currentApp 
                      ? 'bg-primary/20 text-primary' 
                      : 'bg-white/5 text-white/50'
                    }
                  `}>
                    {app.icon}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${app.id === currentApp ? 'text-white' : 'text-white/70'}`}>
                        {app.label}
                      </span>
                      {app.id === currentApp && (
                        <span className="px-1.5 py-0.5 text-[10px] font-bold text-white bg-primary rounded">
                          Active
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-white/40">{app.description}</span>
                  </div>
                </button>
              </React.Fragment>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Platform Header
 * 
 * Unified header with AMTTP branding and app switcher
 */
interface PlatformHeaderProps {
  currentApp?: 'wallet' | 'war-room';
  children?: React.ReactNode;
}

export function PlatformHeader({ currentApp = 'war-room', children }: PlatformHeaderProps) {
  const { session, logout } = useAuth();
  
  const shortAddress = session?.address 
    ? `${session.address.substring(0, 6)}...${session.address.substring(session.address.length - 4)}`
    : null;

  return (
    <div className="h-14 px-4 flex items-center border-b border-white/8 bg-[#0F0F14]">
      {/* Logo */}
      <div className="flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-md bg-gradient-to-br from-primary to-purple-500 flex items-center justify-center">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
          </svg>
        </div>
        <span className="text-white text-lg font-bold tracking-wider">AMTTP</span>
      </div>

      <div className="mx-4">
        <PlatformAppSwitcher currentApp={currentApp} />
      </div>

      <div className="flex-1" />

      {/* Additional children (search, etc.) */}
      {children}

      {/* User Menu */}
      {session && (
        <div className="ml-4 relative group">
          <button className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
            <div className="w-6 h-6 rounded-full bg-primary flex items-center justify-center">
              <span className="text-white text-xs font-bold">
                {session.address.substring(2, 4).toUpperCase()}
              </span>
            </div>
            <span className="text-white/70 text-sm">{shortAddress}</span>
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-white/40">
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </button>
          
          {/* Dropdown */}
          <div className="absolute right-0 top-full mt-2 w-48 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <div className="bg-[#1A1A24] rounded-xl border border-white/10 shadow-xl overflow-hidden">
              <div className="p-3 border-b border-white/8">
                <div className="text-white text-sm font-medium">{shortAddress}</div>
                <div className="text-white/40 text-xs">Role: {session.role}</div>
              </div>
              <button 
                onClick={logout}
                className="w-full p-3 flex items-center gap-2 text-red-400 hover:bg-white/5 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                  <polyline points="16 17 21 12 16 7"></polyline>
                  <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                <span className="text-sm">Logout</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PlatformAppSwitcher;
