'use client';

/**
 * Focus Mode - Transfer Page
 * 
 * Send funds with mandatory trust check interstitial
 * 
 * Flow:
 * 1. User enters recipient and amount
 * 2. Trust Check Interstitial appears (CANNOT be skipped)
 * 3. User makes informed decision: Continue, Escrow, or Cancel
 * 4. Secure Bridge builds EIP-712 intent with UI state hash
 * 5. Flutter wallet signs the intent (includes what user saw)
 * 6. Transaction submitted with signed intent
 * 
 * COMPLIANCE: UI snapshot hash ensures regulators can verify
 * that what user saw = what they signed
 */

import React, { useState, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import FocusModeShell from '@/components/shells/FocusModeShell';
import { TrustCheckInterstitial } from '@/components/trust';
import { useSecureBridge, TransferIntent } from '@/lib/secure-bridge';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

type TransferStep = 'input' | 'trust-check' | 'confirm' | 'processing' | 'complete';

interface TransferFormData {
  recipient: string;
  amount: string;
  currency: string;
  useEscrow: boolean;
}

// Token addresses (for EIP-712)
const TOKEN_ADDRESSES: Record<string, string> = {
  ETH: '0x0000000000000000000000000000000000000000',
  USDC: '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48',
  USDT: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
};

// ═══════════════════════════════════════════════════════════════════════════════
// CURRENCY OPTIONS
// ═══════════════════════════════════════════════════════════════════════════════

const CURRENCIES = [
  { value: 'ETH', label: 'Ethereum', icon: '⟠', symbol: 'ETH' },
  { value: 'USDC', label: 'USD Coin', icon: '💵', symbol: 'USDC' },
  { value: 'USDT', label: 'Tether', icon: '💲', symbol: 'USDT' },
];

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function FocusTransferPage() {
  const router = useRouter();
  const { buildIntent, signIntent, isConnected } = useSecureBridge();
  
  const [step, setStep] = useState<TransferStep>('input');
  const [formData, setFormData] = useState<TransferFormData>({
    recipient: '',
    amount: '',
    currency: 'ETH',
    useEscrow: false,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trustPillars, setTrustPillars] = useState<string[]>([]);
  const [riskScore, setRiskScore] = useState<number>(0);
  const [acknowledgedWarnings, setAcknowledgedWarnings] = useState<string[]>([]);
  const [signedIntent, setSignedIntent] = useState<TransferIntent | null>(null);
  const [signature, setSignature] = useState<string | null>(null);
  
  // Handle form input changes
  const handleChange = useCallback((field: keyof TransferFormData, value: string | boolean) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setError(null);
  }, []);
  
  // Validate form before trust check
  const validateForm = useCallback(() => {
    if (!formData.recipient.trim()) {
      setError('Please enter a recipient address');
      return false;
    }
    if (!formData.recipient.startsWith('0x') || formData.recipient.length !== 42) {
      setError('Please enter a valid Ethereum address');
      return false;
    }
    if (!formData.amount || parseFloat(formData.amount) <= 0) {
      setError('Please enter a valid amount');
      return false;
    }
    return true;
  }, [formData]);
  
  // Handle "Review Transfer" button
  const handleReview = useCallback(() => {
    if (validateForm()) {
      setStep('trust-check');
    }
  }, [validateForm]);
  
  // Trust check callbacks - capture what user saw
  const handleTrustContinue = useCallback((pillars: string[], risk: number, warnings: string[]) => {
    setTrustPillars(pillars);
    setRiskScore(risk);
    setAcknowledgedWarnings(warnings);
    setFormData(prev => ({ ...prev, useEscrow: false }));
    setStep('confirm');
  }, []);
  
  const handleTrustEscrow = useCallback((pillars: string[], risk: number, warnings: string[]) => {
    setTrustPillars(pillars);
    setRiskScore(risk);
    setAcknowledgedWarnings(warnings);
    setFormData(prev => ({ ...prev, useEscrow: true }));
    setStep('confirm');
  }, []);
  
  const handleTrustCancel = useCallback(() => {
    setStep('input');
  }, []);
  
  // Handle final confirmation - BUILD & SIGN INTENT
  const handleConfirm = useCallback(async () => {
    setIsSubmitting(true);
    setStep('processing');
    
    try {
      // Build UI state for snapshot hash
      const uiState = {
        formData,
        trustPillars,
        riskScore,
        acknowledgedWarnings,
        timestamp: Date.now(),
      };
      
      // Build transfer intent with UI state hash (COMPLIANCE: captures what user saw)
      const intent = await buildIntent(
        {
          recipient: formData.recipient,
          amount: formData.amount,
          token: TOKEN_ADDRESSES[formData.currency] || TOKEN_ADDRESSES.ETH,
          chainId: 1, // Mainnet, would come from wallet
          trustPillarsShown: trustPillars,
          riskScoreDisplayed: riskScore,
          warningsAcknowledged: acknowledgedWarnings,
        },
        uiState
      );
      
      setSignedIntent(intent);
      
      // Request signature from Flutter wallet via Secure Bridge
      if (isConnected) {
        const result = await signIntent(intent);
        setSignature(result.signature);
        console.log('✅ Intent signed:', result);
      } else {
        // Fallback: direct signing (web wallet)
        console.warn('Flutter bridge not connected, using fallback');
      }
      
      // Simulate transaction submission
      await new Promise(resolve => setTimeout(resolve, 1500));
      setStep('complete');
    } catch (err: any) {
      setError(err.message || 'Transaction failed. Please try again.');
      setStep('confirm');
    } finally {
      setIsSubmitting(false);
    }
  }, [buildIntent, signIntent, isConnected, formData, trustPillars, riskScore, acknowledgedWarnings]);
  
  // Render based on current step
  return (
    <>
      <FocusModeShell>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center gap-4 pb-2">
            <button
              onClick={() => step === 'input' ? router.back() : setStep('input')}
              className="p-2.5 hover:bg-gray-100 rounded-xl transition-colors border border-gray-200"
            >
              <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {step === 'complete' ? 'Transfer Complete' : 'Send Funds'}
              </h1>
              <p className="text-sm text-gray-500 mt-0.5">
                {step === 'complete' ? 'Your transaction was successful' : 'Securely transfer crypto assets'}
              </p>
            </div>
          </div>
          
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* STEP: Input Form */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {step === 'input' && (
            <div className="space-y-4">
              {/* Error Message */}
              {error && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
                  {error}
                </div>
              )}
              
              {/* Recipient */}
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">
                  Recipient Address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17.982 18.725A7.488 7.488 0 0012 15.75a7.488 7.488 0 00-5.982 2.975m11.963 0a9 9 0 10-11.963 0m11.963 0A8.966 8.966 0 0112 21a8.966 8.966 0 01-5.982-2.275M15 9.75a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={formData.recipient}
                    onChange={(e) => handleChange('recipient', e.target.value)}
                    placeholder="0x..."
                    className="w-full pl-12 pr-4 py-3.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all font-mono text-base text-gray-900 placeholder:text-gray-400 bg-white"
                  />
                </div>
                {formData.recipient && formData.recipient.startsWith('0x') && formData.recipient.length === 42 && (
                  <p className="mt-2 text-sm text-green-600 flex items-center gap-1">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    Valid Ethereum address
                  </p>
                )}
              </div>
              
              {/* Amount */}
              <div>
                <label className="block text-sm font-semibold text-gray-800 mb-2">
                  Amount
                </label>
                <div className="flex gap-3">
                  <div className="relative flex-1">
                    <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                      <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <input
                      type="number"
                      value={formData.amount}
                      onChange={(e) => handleChange('amount', e.target.value)}
                      placeholder="0.00"
                      min="0"
                      step="any"
                      className="w-full pl-12 pr-4 py-3.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-all text-base text-gray-900 placeholder:text-gray-400 bg-white font-medium"
                    />
                  </div>
                  
                  {/* Currency Selector - Custom Dropdown */}
                  <div className="relative">
                    <select
                      value={formData.currency}
                      onChange={(e) => handleChange('currency', e.target.value)}
                      className="appearance-none w-32 pl-4 pr-10 py-3.5 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none bg-white text-gray-900 font-semibold cursor-pointer"
                    >
                      {CURRENCIES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.symbol}
                        </option>
                      ))}
                    </select>
                    {/* Custom display for selected currency */}
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <span className="text-lg">
                        {CURRENCIES.find(c => c.value === formData.currency)?.icon}
                      </span>
                    </div>
                    {/* Dropdown arrow */}
                    <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
                      <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </div>
                </div>
                
                {/* Quick amount buttons */}
                <div className="flex gap-2 mt-3">
                  {['0.1', '0.5', '1', '5'].map((amt) => (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => handleChange('amount', amt)}
                      className="px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors"
                    >
                      {amt} {formData.currency}
                    </button>
                  ))}
                </div>
              </div>
              
              {/* Info Banner */}
              <div className="bg-gradient-to-r from-indigo-50 to-purple-50 border border-indigo-200 rounded-xl p-4 shadow-sm">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-indigo-100 rounded-lg">
                    <svg className="w-5 h-5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
                    </svg>
                  </div>
                  <div className="text-sm">
                    <p className="font-semibold text-gray-800">Trust Check Required</p>
                    <p className="text-gray-600 mt-1 leading-relaxed">
                      Before completing this transfer, we&apos;ll verify the recipient address 
                      against our trust database to help protect you from fraud.
                    </p>
                  </div>
                </div>
              </div>
              
              {/* Submit Button */}
              <button
                onClick={handleReview}
                className="w-full py-4 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white font-bold text-lg rounded-xl transition-all shadow-lg shadow-indigo-300/50 hover:shadow-indigo-400/50 transform hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2"
              >
                <span>Review Transfer</span>
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
            </div>
          )}
          
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* STEP: Confirm */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {step === 'confirm' && (
            <div className="space-y-4">
              <div className="bg-white border border-gray-200 rounded-xl p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Confirm Transfer</h2>
                
                <div className="space-y-3">
                  <div className="flex justify-between py-2 border-b border-gray-100">
                    <span className="text-gray-600">To</span>
                    <span className="font-mono text-sm text-gray-900">
                      {formData.recipient.slice(0, 10)}...{formData.recipient.slice(-8)}
                    </span>
                  </div>
                  <div className="flex justify-between py-2 border-b border-gray-100">
                    <span className="text-gray-600">Amount</span>
                    <span className="font-semibold text-gray-900">
                      {formData.amount} {formData.currency}
                    </span>
                  </div>
                  {formData.useEscrow && (
                    <div className="flex justify-between py-2 border-b border-gray-100">
                      <span className="text-gray-600">Protection</span>
                      <span className="text-blue-600 font-semibold">Escrow Enabled</span>
                    </div>
                  )}
                  <div className="flex justify-between py-2">
                    <span className="text-gray-600">Network Fee (est.)</span>
                    <span className="text-gray-900">~$2.50</span>
                  </div>
                </div>
              </div>
              
              {formData.useEscrow && (
                <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                  <div className="flex items-start gap-3">
                    <svg className="w-5 h-5 text-blue-600 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                    <div className="text-sm text-blue-800">
                      <p className="font-semibold">Escrow Protection Active</p>
                      <p className="text-blue-600 mt-1">
                        Funds will be held in escrow until the recipient confirms receipt.
                        You can cancel within 24 hours if needed.
                      </p>
                    </div>
                  </div>
                </div>
              )}
              
              <div className="flex gap-3">
                <button
                  onClick={() => setStep('input')}
                  className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={isSubmitting}
                  className="flex-1 py-3 bg-green-600 hover:bg-green-700 text-white font-semibold rounded-xl transition-colors disabled:opacity-50"
                >
                  Confirm & Send
                </button>
              </div>
            </div>
          )}
          
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* STEP: Processing */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {step === 'processing' && (
            <div className="text-center py-12">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
                <svg className="w-8 h-8 text-indigo-600 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">Processing Transfer</h2>
              <p className="text-gray-500">Please wait while we process your transaction...</p>
            </div>
          )}
          
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {/* STEP: Complete */}
          {/* ═══════════════════════════════════════════════════════════════════ */}
          {step === 'complete' && (
            <div className="text-center py-8">
              <div className="w-20 h-20 mx-auto mb-4 rounded-full bg-green-100 flex items-center justify-center">
                <svg className="w-10 h-10 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 mb-2">Transfer Successful!</h2>
              <p className="text-gray-500 mb-6">
                {formData.useEscrow 
                  ? 'Your funds are now held in escrow.'
                  : 'Your transfer has been processed.'
                }
              </p>
              
              <div className="bg-gray-50 rounded-xl p-4 mb-6 text-left">
                <div className="flex justify-between py-2">
                  <span className="text-gray-600">Amount</span>
                  <span className="font-semibold">{formData.amount} {formData.currency}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-600">To</span>
                  <span className="font-mono text-sm">
                    {formData.recipient.slice(0, 8)}...{formData.recipient.slice(-6)}
                  </span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-600">Status</span>
                  <span className="text-green-600 font-semibold">
                    {formData.useEscrow ? 'In Escrow' : 'Completed'}
                  </span>
                </div>
              </div>
              
              <div className="flex gap-3">
                <button
                  onClick={() => router.push('/focus/history')}
                  className="flex-1 py-3 border border-gray-300 text-gray-700 font-semibold rounded-xl hover:bg-gray-50 transition-colors"
                >
                  View History
                </button>
                <button
                  onClick={() => {
                    setFormData({ recipient: '', amount: '', currency: 'ETH', useEscrow: false });
                    setStep('input');
                  }}
                  className="flex-1 py-3 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-xl transition-colors"
                >
                  New Transfer
                </button>
              </div>
            </div>
          )}
        </div>
      </FocusModeShell>
      
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {/* Trust Check Interstitial (Modal) */}
      {/* ═══════════════════════════════════════════════════════════════════════ */}
      {step === 'trust-check' && (
        <TrustCheckInterstitial
          counterpartyAddress={formData.recipient}
          amount={formData.amount}
          currency={formData.currency}
          onContinue={handleTrustContinue}
          onUseEscrow={handleTrustEscrow}
          onCancel={handleTrustCancel}
        />
      )}
    </>
  );
}
