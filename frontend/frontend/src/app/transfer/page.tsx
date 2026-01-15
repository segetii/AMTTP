'use client';

import { useState } from 'react';
import AppLayout, { useProfile } from '@/components/AppLayout';
import SecurePaymentFlow from '@/components/SecurePayment';

const ORCHESTRATOR_API = 'http://127.0.0.1:8007';
const INTEGRITY_API = 'http://127.0.0.1:8008';

interface ComplianceDecision {
  decision_id: string;
  action: string;
  risk_score: number;
  reasons: string[];
  requires_travel_rule: boolean;
  requires_sar: boolean;
  requires_escrow: boolean;
  escrow_duration_hours: number;
  processing_time_ms: number;
  checks: Array<{
    service: string;
    check_type: string;
    passed: boolean;
    score?: number;
  }>;
}

function TransferContent() {
  const { profile, address } = useProfile();
  const [showSecureFlow, setShowSecureFlow] = useState(false);

  const handleComplete = (txHash: string) => {
    console.log('Transaction complete:', txHash);
    setShowSecureFlow(false);
    // TODO: Refresh balance, show success notification
    alert(`✅ Transaction successful!\nTx Hash: ${txHash}`);
  };

  const handleCancel = () => {
    setShowSecureFlow(false);
  };

  if (!profile || !address) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">⚠️ Connect Wallet</h2>
        <p className="text-gray-400">Please connect a wallet address in the sidebar to make transfers</p>
      </div>
    );
  }

  if (profile.entity_type === 'UNVERIFIED') {
    return (
      <div className="bg-red-900/50 rounded-lg p-8 text-center">
        <h2 className="text-xl font-semibold mb-2">🚫 Transfers Disabled</h2>
        <p className="text-gray-300">UNVERIFIED accounts cannot make transfers. Please complete KYC verification.</p>
        <a href="/settings" className="inline-block mt-4 bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded">
          Complete KYC →
        </a>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-bold mb-2">🔒 Secure Transfer</h1>
      <p className="text-gray-400 mb-6">Protected against UI manipulation attacks</p>

      {/* Limits Info */}
      <div className="bg-gray-800 rounded-lg p-4 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-gray-400">Your Limits:</span>
            <span className="ml-2 text-white">{profile.single_tx_limit_eth} ETH per transaction</span>
          </div>
          <div>
            <span className="text-gray-400">Daily remaining:</span>
            <span className="ml-2 text-green-400">
              {(profile.daily_limit_eth - profile.daily_volume_eth).toFixed(2)} ETH
            </span>
          </div>
        </div>
      </div>

      {/* Security Badge */}
      <div className="bg-blue-900/30 border border-blue-500/50 rounded-lg p-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="text-3xl">🛡️</div>
          <div>
            <h3 className="font-semibold text-blue-300">UI Integrity Protection Active</h3>
            <p className="text-sm text-gray-400">
              This payment flow is protected against Bybit-style UI manipulation attacks.
              All components are hash-verified before transaction signing.
            </p>
          </div>
        </div>
      </div>

      {!showSecureFlow ? (
        <div className="bg-gray-800 rounded-lg p-6">
          <div className="text-center py-8">
            <div className="text-6xl mb-4">🔐</div>
            <h2 className="text-2xl font-bold mb-4">Ready to Make a Secure Transfer</h2>
            <p className="text-gray-400 mb-6 max-w-md mx-auto">
              Click below to start the integrity-protected payment flow. 
              The system will verify UI components before allowing any transaction.
            </p>
            <button
              onClick={() => setShowSecureFlow(true)}
              className="bg-blue-600 hover:bg-blue-700 px-8 py-4 rounded-lg font-semibold text-lg"
            >
              Start Secure Payment Flow →
            </button>
          </div>
        </div>
      ) : (
        <SecurePaymentFlow
          walletAddress={address}
          onComplete={handleComplete}
          onCancel={handleCancel}
          apiEndpoint={INTEGRITY_API}
        />
      )}
    </div>
  );
}

export default function TransferPage() {
  return (
    <AppLayout>
      <TransferContent />
    </AppLayout>
  );
}
