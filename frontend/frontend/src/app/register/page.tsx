'use client';

/**
 * Registration Page
 * 
 * Create a new AMTTP account using wallet or email
 */

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  useAuthService,
  detectWallet,
} from '@/lib/auth-service';
import {
  AuthMethod,
  WalletType,
  RegistrationError,
  validateEmail,
  validatePassword,
  truncateAddress,
} from '@/types/auth';

// ═══════════════════════════════════════════════════════════════════════════════
// WALLET ICONS
// ═══════════════════════════════════════════════════════════════════════════════

function MetaMaskIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
      <path d="M27.2684 4.03125L17.5765 11.2708L19.3359 6.85625L27.2684 4.03125Z" fill="#E17726" stroke="#E17726" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M4.73145 4.03125L14.3362 11.3396L12.6641 6.85625L4.73145 4.03125Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M23.7285 21.0312L21.0762 25.2L26.6934 26.75L28.3184 21.125L23.7285 21.0312Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M3.69141 21.125L5.30641 26.75L10.9236 25.2L8.27141 21.0312L3.69141 21.125Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M10.6172 14.1562L9.04688 16.5312L14.6172 16.7812L14.4141 10.7812L10.6172 14.1562Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M21.3828 14.1562L17.5234 10.7188L17.5762 16.7812L23.1406 16.5312L21.3828 14.1562Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M10.9238 25.2L14.2613 23.5625L11.3613 21.1562L10.9238 25.2Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
      <path d="M17.7383 23.5625L21.0758 25.2L20.6383 21.1562L17.7383 23.5625Z" fill="#E27625" stroke="#E27625" strokeWidth="0.25" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function WalletIcon() {
  return (
    <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a2.25 2.25 0 00-2.25-2.25H15a3 3 0 11-6 0H5.25A2.25 2.25 0 003 12m18 0v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6m18 0V9M3 12V9m18 0a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 9m18 0V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v3" />
    </svg>
  );
}

function EmailIcon() {
  return (
    <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// ERROR MESSAGES
// ═══════════════════════════════════════════════════════════════════════════════

const errorMessages: Record<RegistrationError, string> = {
  [RegistrationError.WALLET_ALREADY_REGISTERED]: 'This wallet is already registered. Please sign in instead.',
  [RegistrationError.EMAIL_ALREADY_REGISTERED]: 'This email is already registered. Please sign in instead.',
  [RegistrationError.INVALID_SIGNATURE]: 'Invalid wallet signature. Please try again.',
  [RegistrationError.INVALID_EMAIL]: 'Please enter a valid email address.',
  [RegistrationError.WEAK_PASSWORD]: 'Password does not meet security requirements.',
  [RegistrationError.TERMS_NOT_ACCEPTED]: 'You must accept the Terms of Service and Privacy Policy.',
  [RegistrationError.BLOCKED_REGION]: 'Registration is not available in your region.',
  [RegistrationError.RATE_LIMITED]: 'Too many attempts. Please try again later.',
  [RegistrationError.UNKNOWN_ERROR]: 'An unexpected error occurred. Please try again.',
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function RegisterPage() {
  const router = useRouter();
  const {
    isLoading,
    isAuthenticated,
    walletConnected,
    walletAddress,
    walletType,
    connect,
    register,
  } = useAuthService();
  
  const [step, setStep] = useState<'method' | 'wallet' | 'email' | 'profile'>('method');
  const [authMethod, setAuthMethod] = useState<AuthMethod | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Form fields
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [acceptedPrivacy, setAcceptedPrivacy] = useState(false);
  
  // Password validation
  const [passwordErrors, setPasswordErrors] = useState<string[]>([]);
  
  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      router.push('/focus');
    }
  }, [isAuthenticated, router]);
  
  // Validate password on change
  useEffect(() => {
    if (password) {
      const validation = validatePassword(password);
      setPasswordErrors(validation.errors);
    } else {
      setPasswordErrors([]);
    }
  }, [password]);
  
  // Handle wallet connection
  const handleConnectWallet = async () => {
    setError(null);
    try {
      const result = await connect();
      if (result) {
        setStep('profile');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to connect wallet');
    }
  };
  
  // Handle method selection
  const handleSelectMethod = (method: AuthMethod) => {
    setAuthMethod(method);
    setError(null);
    
    if (method === AuthMethod.WALLET) {
      if (walletConnected && walletAddress) {
        setStep('profile');
      } else {
        setStep('wallet');
      }
    } else if (method === AuthMethod.EMAIL) {
      setStep('email');
    }
  };
  
  // Handle email form submission
  const handleEmailSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    if (!validateEmail(email)) {
      setError('Please enter a valid email address');
      return;
    }
    
    if (passwordErrors.length > 0) {
      setError('Please fix the password issues');
      return;
    }
    
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    
    setStep('profile');
  };
  
  // Handle final registration
  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    if (!acceptedTerms || !acceptedPrivacy) {
      setError('You must accept the Terms of Service and Privacy Policy');
      return;
    }
    
    try {
      const result = await register({
        authMethod: authMethod!,
        walletAddress: authMethod === AuthMethod.WALLET ? walletAddress! : undefined,
        walletType: authMethod === AuthMethod.WALLET ? walletType! : undefined,
        email: authMethod === AuthMethod.EMAIL ? email : undefined,
        password: authMethod === AuthMethod.EMAIL ? password : undefined,
        displayName: displayName || undefined,
        acceptedTerms,
        acceptedPrivacy,
      });
      
      if (result.success) {
        if (result.requiresVerification) {
          // TODO: Show verification page
          router.push('/login?verified=pending');
        } else {
          router.push('/focus');
        }
      } else {
        setError(errorMessages[result.error!] || 'Registration failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed');
    }
  };
  
  // Detect available wallet
  const detectedWallet = detectWallet();
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-cyan-500 to-blue-600 rounded-2xl mb-4">
            <span className="text-3xl">🔐</span>
          </div>
          <h1 className="text-2xl font-bold text-white">Create Account</h1>
          <p className="text-slate-400 mt-1">Join AMTTP - Secure Transfer Protocol</p>
        </div>
        
        {/* Card */}
        <div className="bg-slate-800/50 backdrop-blur border border-slate-700 rounded-2xl p-6">
          {/* Error Message */}
          {error && (
            <div className="mb-4 p-3 bg-red-900/30 border border-red-600/30 rounded-lg">
              <p className="text-sm text-red-400">{error}</p>
            </div>
          )}
          
          {/* Step: Select Method */}
          {step === 'method' && (
            <div className="space-y-4">
              <h2 className="text-lg font-medium text-white mb-4">Choose how to sign up</h2>
              
              {/* Wallet Option */}
              <button
                onClick={() => handleSelectMethod(AuthMethod.WALLET)}
                className="w-full p-4 bg-slate-700/50 border border-slate-600 rounded-xl hover:bg-slate-700 hover:border-cyan-500/50 transition-all group"
              >
                <div className="flex items-center gap-4">
                  <div className="p-2 bg-orange-500/20 rounded-lg text-orange-400">
                    {detectedWallet === WalletType.METAMASK ? <MetaMaskIcon /> : <WalletIcon />}
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-white">Connect Wallet</p>
                    <p className="text-sm text-slate-400">
                      {detectedWallet 
                        ? `${detectedWallet} detected` 
                        : 'MetaMask, WalletConnect, etc.'}
                    </p>
                  </div>
                  <svg className="w-5 h-5 text-slate-500 ml-auto group-hover:text-cyan-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </button>
              
              {/* Email Option */}
              <button
                onClick={() => handleSelectMethod(AuthMethod.EMAIL)}
                className="w-full p-4 bg-slate-700/50 border border-slate-600 rounded-xl hover:bg-slate-700 hover:border-cyan-500/50 transition-all group"
              >
                <div className="flex items-center gap-4">
                  <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
                    <EmailIcon />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-white">Email & Password</p>
                    <p className="text-sm text-slate-400">Traditional account</p>
                  </div>
                  <svg className="w-5 h-5 text-slate-500 ml-auto group-hover:text-cyan-400 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </button>
              
              {/* Divider */}
              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-700"></div>
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-slate-800/50 text-slate-500">Recommended for Web3</span>
                </div>
              </div>
              
              {/* Info */}
              <div className="p-3 bg-cyan-900/20 border border-cyan-600/20 rounded-lg">
                <p className="text-xs text-cyan-400">
                  🔒 Wallet authentication provides the highest security and enables full blockchain features including on-chain transfers and smart contract interactions.
                </p>
              </div>
            </div>
          )}
          
          {/* Step: Connect Wallet */}
          {step === 'wallet' && (
            <div className="space-y-4">
              <button
                onClick={() => setStep('method')}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>
              
              <h2 className="text-lg font-medium text-white">Connect your wallet</h2>
              
              {!detectedWallet ? (
                <div className="p-4 bg-yellow-900/20 border border-yellow-600/20 rounded-lg">
                  <p className="text-sm text-yellow-400 mb-3">
                    No Web3 wallet detected. Please install MetaMask or another wallet.
                  </p>
                  <a
                    href="https://metamask.io/download/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm text-cyan-400 hover:text-cyan-300"
                  >
                    Install MetaMask
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                </div>
              ) : (
                <button
                  onClick={handleConnectWallet}
                  disabled={isLoading}
                  className="w-full p-4 bg-gradient-to-r from-orange-500 to-orange-600 text-white rounded-xl hover:from-orange-600 hover:to-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-3"
                >
                  {isLoading ? (
                    <>
                      <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                      </svg>
                      Connecting...
                    </>
                  ) : (
                    <>
                      <MetaMaskIcon />
                      Connect {detectedWallet}
                    </>
                  )}
                </button>
              )}
            </div>
          )}
          
          {/* Step: Email Form */}
          {step === 'email' && (
            <form onSubmit={handleEmailSubmit} className="space-y-4">
              <button
                type="button"
                onClick={() => setStep('method')}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>
              
              <h2 className="text-lg font-medium text-white">Create your account</h2>
              
              {/* Email */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                  required
                />
              </div>
              
              {/* Password */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                  required
                />
                {passwordErrors.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {passwordErrors.map((err, i) => (
                      <li key={i} className="text-xs text-red-400 flex items-center gap-1">
                        <span>✗</span> {err}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              
              {/* Confirm Password */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Confirm Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  className={`w-full px-4 py-3 bg-slate-900 border rounded-lg text-white placeholder-slate-500 focus:outline-none ${
                    confirmPassword && password !== confirmPassword
                      ? 'border-red-500 focus:border-red-500'
                      : 'border-slate-600 focus:border-cyan-500'
                  }`}
                  required
                />
                {confirmPassword && password !== confirmPassword && (
                  <p className="mt-1 text-xs text-red-400">Passwords do not match</p>
                )}
              </div>
              
              <button
                type="submit"
                disabled={!email || !password || !confirmPassword || passwordErrors.length > 0 || password !== confirmPassword}
                className="w-full py-3 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Continue
              </button>
            </form>
          )}
          
          {/* Step: Profile & Terms */}
          {step === 'profile' && (
            <form onSubmit={handleRegister} className="space-y-4">
              <button
                type="button"
                onClick={() => setStep(authMethod === AuthMethod.WALLET ? 'wallet' : 'email')}
                className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
                Back
              </button>
              
              <h2 className="text-lg font-medium text-white">Complete your profile</h2>
              
              {/* Connected Wallet Info */}
              {authMethod === AuthMethod.WALLET && walletAddress && (
                <div className="p-3 bg-green-900/20 border border-green-600/20 rounded-lg flex items-center gap-3">
                  <div className="w-8 h-8 bg-green-500/20 rounded-full flex items-center justify-center">
                    <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm text-green-400">Wallet Connected</p>
                    <code className="text-xs text-slate-400">{truncateAddress(walletAddress, 6)}</code>
                  </div>
                </div>
              )}
              
              {/* Display Name */}
              <div>
                <label className="block text-sm text-slate-400 mb-1">Display Name (optional)</label>
                <input
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="How should we call you?"
                  className="w-full px-4 py-3 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              
              {/* Terms */}
              <div className="space-y-3 pt-4">
                <label className="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={acceptedTerms}
                    onChange={(e) => setAcceptedTerms(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-slate-600 bg-slate-900 text-cyan-600 focus:ring-cyan-600"
                  />
                  <span className="text-sm text-slate-400 group-hover:text-slate-300">
                    I agree to the{' '}
                    <a href="/terms" className="text-cyan-400 hover:text-cyan-300">Terms of Service</a>
                  </span>
                </label>
                
                <label className="flex items-start gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={acceptedPrivacy}
                    onChange={(e) => setAcceptedPrivacy(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-slate-600 bg-slate-900 text-cyan-600 focus:ring-cyan-600"
                  />
                  <span className="text-sm text-slate-400 group-hover:text-slate-300">
                    I agree to the{' '}
                    <a href="/privacy" className="text-cyan-400 hover:text-cyan-300">Privacy Policy</a>
                  </span>
                </label>
              </div>
              
              <button
                type="submit"
                disabled={isLoading || !acceptedTerms || !acceptedPrivacy}
                className="w-full py-3 bg-gradient-to-r from-cyan-500 to-blue-600 text-white rounded-lg hover:from-cyan-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
              >
                {isLoading ? (
                  <>
                    <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Creating Account...
                  </>
                ) : (
                  'Create Account'
                )}
              </button>
            </form>
          )}
          
          {/* Sign In Link */}
          <div className="mt-6 text-center">
            <p className="text-sm text-slate-400">
              Already have an account?{' '}
              <Link href="/login" className="text-cyan-400 hover:text-cyan-300">
                Sign in
              </Link>
            </p>
          </div>
        </div>
        
        {/* Footer */}
        <p className="mt-6 text-center text-xs text-slate-500">
          Protected by industry-standard encryption
        </p>
      </div>
    </div>
  );
}
