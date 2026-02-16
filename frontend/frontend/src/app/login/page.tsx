'use client';

/**
 * Login Page
 * 
 * Real authentication page with multiple login methods:
 * - Wallet-based (MetaMask, etc.)
 * - Email/Password
 * - Demo mode for testing
 */

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { connectWallet, isWalletConnected, detectWallet } from '@/lib/auth-service';
import { Role, getRoleMode, AppMode } from '@/types/rbac';

type LoginTab = 'wallet' | 'email' | 'demo';

// ═══════════════════════════════════════════════════════════════════════════════
// DEMO ROLE OPTIONS (for demo mode)
// NOTE: End Users (R1/R2) are handled by the Flutter app, not Next.js
// ═══════════════════════════════════════════════════════════════════════════════

const ROLE_OPTIONS = [
  {
    role: Role.R3_INSTITUTION_OPS,
    title: 'Institution Ops',
    description: 'Operations team with War Room access',
    mode: 'War Room (View)',
    color: 'from-blue-500 to-indigo-600',
  },
  {
    role: Role.R4_INSTITUTION_COMPLIANCE,
    title: 'Compliance Officer',
    description: 'Full War Room access with enforcement',
    mode: 'War Room (Full)',
    color: 'from-purple-500 to-violet-600',
  },
  {
    role: Role.R5_PLATFORM_ADMIN,
    title: 'Platform Admin',
    description: 'Platform-wide administration and user management',
    mode: 'War Room (Admin)',
    color: 'from-rose-500 to-pink-600',
  },
  {
    role: Role.R6_SUPER_ADMIN,
    title: 'Super Admin',
    description: 'Full system access, role management, emergency override',
    mode: 'War Room (Super)',
    color: 'from-red-600 to-rose-700',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// LOGIN CONTENT COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

function LoginContent() {
  const router = useRouter();
  const { login, isLoading } = useAuth();
  
  // Tab state
  const [activeTab, setActiveTab] = useState<LoginTab>('wallet');
  
  // Wallet login state
  const [isWalletAvailable, setIsWalletAvailable] = useState(false);
  const [walletConnecting, setWalletConnecting] = useState(false);
  
  // Email login state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [emailError, setEmailError] = useState('');
  const [isEmailLoading, setIsEmailLoading] = useState(false);
  
  // Demo mode state
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [isConnecting, setIsConnecting] = useState(false);
  
  // Check for wallet on mount
  useEffect(() => {
    setIsWalletAvailable(isWalletConnected());
  }, []);
  
  // Handle wallet login
  const handleWalletLogin = async () => {
    setWalletConnecting(true);
    setEmailError('');
    
    try {
      const result = await connectWallet();
      if (result) {
        await login(result.address);
        router.push('/war-room');
      } else {
        setEmailError('Wallet connection cancelled');
      }
    } catch (error) {
      setEmailError('Failed to connect wallet');
      console.error('Wallet login error:', error);
    } finally {
      setWalletConnecting(false);
    }
  };
  
  // Handle email login
  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setEmailError('No real backend authentication is available.');
    setIsEmailLoading(false);
  };
  
  // Handle demo connect - use pre-seeded mock user addresses
  const handleDemoConnect = async () => {
    setIsConnecting(true);
    setTimeout(() => {
      setIsConnecting(false);
      setEmailError('Demo connect is disabled. No backend auth available.');
    }, 500);
  };
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-lg w-full">
        {/* Logo & Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white">AMTTP</h1>
          <p className="text-slate-400 mt-2">Anti-Money Laundering Transaction Transfer Protocol</p>
        </div>
        
        {/* Login Card */}
        <div className="bg-slate-800/50 backdrop-blur-sm rounded-2xl border border-slate-700 overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-slate-700">
            <button
              onClick={() => setActiveTab('wallet')}
              className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${
                activeTab === 'wallet' 
                  ? 'text-indigo-400 border-b-2 border-indigo-400 bg-slate-800/50' 
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
                Wallet
              </span>
            </button>
            <button
              onClick={() => setActiveTab('email')}
              className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${
                activeTab === 'email' 
                  ? 'text-indigo-400 border-b-2 border-indigo-400 bg-slate-800/50' 
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                Email
              </span>
            </button>
            <button
              onClick={() => setActiveTab('demo')}
              className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${
                activeTab === 'demo' 
                  ? 'text-indigo-400 border-b-2 border-indigo-400 bg-slate-800/50' 
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                Demo
              </span>
            </button>
          </div>
          
          <div className="p-6">
            {/* Error Display */}
            {emailError && (
              <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {emailError}
              </div>
            )}
            
            {/* Wallet Tab */}
            {activeTab === 'wallet' && (
              <div className="space-y-4">
                <div className="text-center">
                  <h2 className="text-lg font-semibold text-white mb-2">Connect Your Wallet</h2>
                  <p className="text-sm text-slate-400">
                    Connect with MetaMask or another Web3 wallet to sign in securely.
                  </p>
                </div>
                
                {isWalletAvailable ? (
                  <button
                    onClick={handleWalletLogin}
                    disabled={walletConnecting}
                    className="w-full py-3 px-4 rounded-xl font-semibold bg-gradient-to-r from-orange-500 to-amber-600 hover:from-orange-600 hover:to-amber-700 text-white shadow-lg shadow-orange-500/30 transition-all flex items-center justify-center gap-2"
                  >
                    {walletConnecting ? (
                      <>
                        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Connecting...
                      </>
                    ) : (
                      <>
                        <svg className="w-5 h-5" viewBox="0 0 40 40" fill="currentColor">
                          <path d="M36.08 16.23l-16-14a.5.5 0 00-.66 0l-16 14a.5.5 0 00-.17.38v15a.5.5 0 00.5.5h32a.5.5 0 00.5-.5v-15a.5.5 0 00-.17-.38z" />
                        </svg>
                        Connect MetaMask
                      </>
                    )}
                  </button>
                ) : (
                  <div className="text-center">
                    <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-slate-700/50 flex items-center justify-center">
                      <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <p className="text-slate-400 mb-4">No Web3 wallet detected</p>
                    <a
                      href="https://metamask.io/download/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500/20 text-orange-400 hover:bg-orange-500/30 transition-colors text-sm"
                    >
                      Install MetaMask
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  </div>
                )}
              </div>
            )}
            
            {/* Email Tab */}
            {activeTab === 'email' && (
              <form onSubmit={handleEmailLogin} className="space-y-4">
                <div className="text-center mb-4">
                  <h2 className="text-lg font-semibold text-white mb-2">Sign In with Email</h2>
                  <p className="text-sm text-slate-400">
                    Enter your email and password to sign in.
                  </p>
                </div>
                
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    id="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="you@example.com"
                    required
                  />
                </div>
                
                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1">
                    Password
                  </label>
                  <input
                    type="password"
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-2 rounded-lg bg-slate-700/50 border border-slate-600 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    placeholder="••••••••"
                    required
                  />
                </div>
                
                <button
                  type="submit"
                  disabled={isEmailLoading || !email || !password}
                  className={`
                    w-full py-3 px-4 rounded-xl font-semibold transition-all
                    ${email && password
                      ? 'bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white shadow-lg shadow-indigo-500/30' 
                      : 'bg-slate-600 text-slate-400 cursor-not-allowed'
                    }
                  `}
                >
                  {isEmailLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Signing in...
                    </span>
                  ) : (
                    'Sign In'
                  )}
                </button>
                
                <div className="text-center">
                  <Link
                    href="/register"
                    className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    Don&apos;t have an account? Register
                  </Link>
                </div>
              </form>
            )}
            
            {/* Demo Tab */}
            {activeTab === 'demo' && (
              <div className="space-y-4">
                <div className="text-center mb-4">
                  <h2 className="text-lg font-semibold text-white mb-2">Demo Mode</h2>
                  <p className="text-sm text-slate-400">
                    Select a role to explore different modes without creating an account.
                  </p>
                </div>
                
                <div className="space-y-3">
                  {ROLE_OPTIONS.map((option) => (
                    <button
                      key={option.role}
                      onClick={() => setSelectedRole(option.role)}
                      className={`
                        w-full text-left p-4 rounded-xl border-2 transition-all
                        ${selectedRole === option.role 
                          ? 'border-indigo-500 bg-indigo-500/10' 
                          : 'border-slate-600 hover:border-slate-500 bg-slate-700/50'
                        }
                      `}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-lg bg-gradient-to-br ${option.color} flex items-center justify-center text-white font-bold`}>
                          {option.title[0]}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-white">{option.title}</span>
                            <span className="px-2 py-0.5 text-xs rounded-full bg-slate-600 text-slate-300">
                              {option.mode}
                            </span>
                          </div>
                          <p className="text-sm text-slate-400 mt-0.5">{option.description}</p>
                        </div>
                        {selectedRole === option.role && (
                          <svg className="w-5 h-5 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
                
                <button
                  onClick={handleDemoConnect}
                  disabled={!selectedRole || isConnecting}
                  className={`
                    w-full py-3 px-4 rounded-xl font-semibold transition-all
                    ${selectedRole 
                      ? 'bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white shadow-lg shadow-indigo-500/30' 
                      : 'bg-slate-600 text-slate-400 cursor-not-allowed'
                    }
                  `}
                >
                  {isConnecting ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Connecting...
                    </span>
                  ) : (
                    'Enter Demo Mode'
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
        
        {/* Footer */}
        <p className="text-center text-sm text-slate-500 mt-6">
          By signing in, you agree to the AMTTP Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function LoginPage() {
  return (
    <AuthProvider>
      <LoginContent />
    </AuthProvider>
  );
}
