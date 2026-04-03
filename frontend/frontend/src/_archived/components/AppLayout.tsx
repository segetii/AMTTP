'use client';

import { useState, useEffect, createContext, useContext, ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface EntityProfile {
  address: string;
  entity_type: 'RETAIL' | 'INSTITUTIONAL' | 'VASP' | 'HIGH_NET_WORTH' | 'UNVERIFIED';
  kyc_level: 'NONE' | 'BASIC' | 'STANDARD' | 'ENHANCED' | 'INSTITUTIONAL';
  risk_tolerance: 'STRICT' | 'CONSERVATIVE' | 'MODERATE' | 'PERMISSIVE';
  jurisdiction: string;
  daily_limit_eth: number;
  monthly_limit_eth: number;
  single_tx_limit_eth: number;
  total_transactions: number;
  daily_volume_eth: number;
  monthly_volume_eth: number;
}

interface ProfileContextType {
  profile: EntityProfile | null;
  address: string;
  setAddress: (addr: string) => void;
  loadProfile: () => Promise<void>;
  loading: boolean;
}

declare global {
  interface Window {
    ethereum?: {
      isMetaMask?: boolean;
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
      on?: (event: string, handler: (payload: unknown) => void) => void;
      removeListener?: (event: string, handler: (payload: unknown) => void) => void;
    };
  }
}

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// CONTEXT
// ═══════════════════════════════════════════════════════════════════════════════

const ProfileContext = createContext<ProfileContextType>({
  profile: null,
  address: '',
  setAddress: () => {},
  loadProfile: async () => {},
  loading: false,
});

export const useProfile = () => useContext(ProfileContext);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<EntityProfile | null>(null);
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);

  const loadProfile = async () => {
    if (!address) return;
    setLoading(true);
    try {
      const res = await fetch(`${ORCHESTRATOR_API}/profiles/${address}`);
      if (res.ok) {
        setProfile(await res.json());
      }
    } catch (e) {
      console.error('Failed to load profile:', e);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (address) loadProfile();
  }, [address]);

  // Keep in sync with MetaMask account changes if present.
  useEffect(() => {
    const eth = window.ethereum;
    if (!eth?.on) return;

    const handleAccountsChanged = (payload: unknown) => {
      const accounts = Array.isArray(payload) ? (payload as unknown[]) : [];
      const next = (typeof accounts[0] === 'string' ? (accounts[0] as string) : '') || '';
      if (next && next !== address) setAddress(next);
      if (!next) setProfile(null);
    };

    eth.on('accountsChanged', handleAccountsChanged);
    return () => {
      eth.removeListener?.('accountsChanged', handleAccountsChanged);
    };
  }, [address]);

  return (
    <ProfileContext.Provider value={{ profile, address, setAddress, loadProfile, loading }}>
      {children}
    </ProfileContext.Provider>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION ITEMS BY PROFILE
// ═══════════════════════════════════════════════════════════════════════════════

interface NavItem {
  href: string;
  label: string;
  icon: string;
  profiles: string[]; // Which profiles can access
}

const NAV_ITEMS: NavItem[] = [
  { href: '/dashboard', label: 'Dashboard', icon: '📊', profiles: ['ALL'] },
  { href: '/transfer', label: 'Transfer', icon: '🔄', profiles: ['RETAIL', 'INSTITUTIONAL', 'VASP', 'HIGH_NET_WORTH'] },
  { href: '/transfer/batch', label: 'Batch Transfer', icon: '📦', profiles: ['INSTITUTIONAL', 'VASP'] },
  { href: '/history', label: 'History', icon: '📜', profiles: ['ALL'] },
  { href: '/compliance', label: 'Compliance', icon: '🛡️', profiles: ['ALL'] },
  { href: '/compliance/fatf-rules', label: 'FATF Rules', icon: '🌍', profiles: ['ALL'] },
  { href: '/compliance/sanctions', label: 'Sanctions', icon: '🚫', profiles: ['INSTITUTIONAL', 'VASP'] },
  { href: '/compliance/alerts', label: 'Alerts', icon: '🚨', profiles: ['INSTITUTIONAL', 'VASP'] },
  { href: '/reports', label: 'Reports', icon: '📈', profiles: ['INSTITUTIONAL', 'VASP', 'HIGH_NET_WORTH'] },
  { href: '/reports/tax', label: 'Tax Reports', icon: '💰', profiles: ['HIGH_NET_WORTH'] },
  { href: '/team', label: 'Team', icon: '👥', profiles: ['INSTITUTIONAL', 'VASP'] },
  { href: '/api-keys', label: 'API Keys', icon: '🔑', profiles: ['INSTITUTIONAL', 'VASP'] },
  { href: '/vault', label: 'Vault', icon: '🏦', profiles: ['HIGH_NET_WORTH'] },
  { href: '/concierge', label: 'Concierge', icon: '🎩', profiles: ['HIGH_NET_WORTH'] },
  { href: '/interops', label: 'Interops', icon: '🔗', profiles: ['VASP'] },
  { href: '/settings', label: 'Settings', icon: '⚙️', profiles: ['ALL'] },
  { href: '/policies', label: 'Policies', icon: '📋', profiles: ['INSTITUTIONAL', 'VASP'] },
];

function canAccess(item: NavItem, entityType: string | undefined): boolean {
  if (item.profiles.includes('ALL')) return true;
  if (!entityType) return false;
  return item.profiles.includes(entityType);
}

// ═══════════════════════════════════════════════════════════════════════════════
// SIDEBAR COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function Sidebar() {
  const pathname = usePathname();
  const { profile, address, setAddress, loading } = useProfile();
  const [inputAddr, setInputAddr] = useState(address);
  const [walletError, setWalletError] = useState<string | null>(null);

  const handleConnect = () => {
    setAddress(inputAddr);
  };

  const handleConnectMetaMask = async () => {
    setWalletError(null);
    const eth = window.ethereum;
    if (!eth?.request) {
      setWalletError('MetaMask not detected');
      return;
    }

    try {
      const result = await eth.request({ method: 'eth_requestAccounts' });
      const accounts = Array.isArray(result) ? (result as unknown[]) : [];
      const next = (typeof accounts[0] === 'string' ? (accounts[0] as string) : '') || '';
      if (next) {
        setInputAddr(next);
        setAddress(next);
      }
    } catch (e) {
      console.error('MetaMask connect failed:', e);
      setWalletError('Wallet connection rejected');
    }
  };

  const getProfileColor = (type: string) => {
    switch (type) {
      case 'VASP': return 'bg-purple-600';
      case 'INSTITUTIONAL': return 'bg-blue-600';
      case 'HIGH_NET_WORTH': return 'bg-yellow-600';
      case 'RETAIL': return 'bg-green-600';
      default: return 'bg-gray-600';
    }
  };

  return (
    <aside className="w-64 bg-gray-900 border-r border-gray-800 flex flex-col h-screen fixed left-0 top-0">
      {/* Logo */}
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-xl font-bold text-white">🛡️ AMTTP</h1>
        <p className="text-xs text-gray-500">Compliance Platform</p>
      </div>

      {/* Profile Selector */}
      <div className="p-4 border-b border-gray-800">
        <label className="text-xs text-gray-500 block mb-1">Wallet Address</label>
        <div className="flex gap-2 mb-2">
          <button
            onClick={handleConnectMetaMask}
            className="flex-1 bg-orange-600 hover:bg-orange-700 px-2 py-1 rounded text-xs"
          >
            🦊 Connect MetaMask
          </button>
        </div>
        <div className="flex gap-1">
          <input
            type="text"
            placeholder="0x..."
            value={inputAddr}
            onChange={(e) => setInputAddr(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-white"
          />
          <button
            onClick={handleConnect}
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 px-2 py-1 rounded text-xs disabled:opacity-50"
          >
            {loading ? '...' : '→'}
          </button>
        </div>

        {walletError && (
          <p className="text-xs text-red-400 mt-2">{walletError}</p>
        )}

        {profile && (
          <div className="mt-3 p-2 bg-gray-800 rounded">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${getProfileColor(profile.entity_type)}`}>
                {profile.entity_type}
              </span>
              <span className="text-xs text-gray-400">{profile.kyc_level}</span>
            </div>
            <p className="text-xs text-gray-500 mt-1 truncate">{profile.address}</p>
            <div className="text-xs text-gray-400 mt-1">
              Limit: {profile.single_tx_limit_eth} ETH/tx
            </div>
          </div>
        )}

        {!profile && address && !loading && (
          <p className="text-xs text-yellow-500 mt-2">Profile not found</p>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-2">
        {NAV_ITEMS.filter(item => canAccess(item, profile?.entity_type)).map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-blue-900/50 text-blue-400 border-r-2 border-blue-500'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-white'
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Quick Actions */}
      <div className="p-4 border-t border-gray-800">
        <div className="text-xs text-gray-500 mb-2">Quick Test Profiles:</div>
        <div className="flex flex-wrap gap-1">
          {[
            { addr: '0x1234', type: 'RETAIL' },
            { addr: '0xABCD1234567890abcdef1234567890abcd123456', type: 'VASP' },
            { addr: '0x5678', type: 'HNW' },
          ].map((t) => (
            <button
              key={t.addr}
              onClick={() => { setInputAddr(t.addr); setAddress(t.addr); }}
              className="text-xs bg-gray-800 hover:bg-gray-700 px-2 py-1 rounded"
            >
              {t.type}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN LAYOUT
// ═══════════════════════════════════════════════════════════════════════════════

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ProfileProvider>
      <div className="min-h-screen bg-gray-950 text-white">
        <Sidebar />
        <main className="ml-64 p-6">
          {children}
        </main>
      </div>
    </ProfileProvider>
  );
}
