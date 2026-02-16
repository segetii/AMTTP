/**
 * AMTTP Secure Payment Component
 * 
 * Anti-Bybit attack protection:
 * 1. UI integrity verification before any transaction
 * 2. Transaction intent signing (sign actual data, not UI)
 * 3. Mutation monitoring during payment flow
 * 4. Visual confirmation in isolated layer
 */

"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  capturePaymentPageIntegrity,
  captureComponentIntegrity,
  createTransactionIntent,
  getIntentHash,
  generateConfirmationData,
  startMutationMonitoring,
  stopMutationMonitoring,
  verifyWithServer,
  generateIntegrityReport,
  type TransactionIntent,
  type MutationAlert,
  type ConfirmationData,
  type IntegrityReport,
} from "@/lib/ui-integrity";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface PaymentRequest {
  toAddress: string;
  valueWei: string;
  chainId: number;
  networkName: string;
  tokenAddress?: string;
  tokenSymbol?: string;
}

interface SecurePaymentState {
  stage: "input" | "verify" | "confirm" | "sign" | "complete" | "blocked";
  integrityReport: IntegrityReport | null;
  intent: TransactionIntent | null;
  confirmationData: ConfirmationData | null;
  mutationAlerts: MutationAlert[];
  error: string | null;
}

interface SecurePaymentProps {
  walletAddress: string;
  onComplete: (txHash: string) => void;
  onCancel: () => void;
  apiEndpoint?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// SECURE PAYMENT COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export function SecurePaymentFlow({
  walletAddress,
  onComplete,
  onCancel,
  apiEndpoint = "/api",
}: SecurePaymentProps) {
  const componentRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<SecurePaymentState>({
    stage: "input",
    integrityReport: null,
    intent: null,
    confirmationData: null,
    mutationAlerts: [],
    error: null,
  });

  const [payment, setPayment] = useState<PaymentRequest>({
    toAddress: "",
    valueWei: "0",
    chainId: 1,
    networkName: "Ethereum Mainnet",
  });

  // ─────────────────────────────────────────────────────────────────────────
  // MUTATION MONITORING
  // ─────────────────────────────────────────────────────────────────────────

  const handleMutationAlert = useCallback((alert: MutationAlert) => {
    console.error("[INTEGRITY] Mutation detected:", alert);
    
    setState((prev) => ({
      ...prev,
      mutationAlerts: [...prev.mutationAlerts, alert],
    }));

    // Block on critical alerts
    if (alert.severity === "critical") {
      setState((prev) => ({
        ...prev,
        stage: "blocked",
        error: `Security alert: ${alert.details}`,
      }));
    }
  }, []);

  useEffect(() => {
    if (componentRef.current) {
      startMutationMonitoring(componentRef.current, handleMutationAlert);
    }
    return () => stopMutationMonitoring();
  }, [handleMutationAlert]);

  // ─────────────────────────────────────────────────────────────────────────
  // INTEGRITY VERIFICATION
  // ─────────────────────────────────────────────────────────────────────────

  const verifyIntegrity = async (): Promise<boolean> => {
    try {
      // Capture component integrity
      const componentIntegrity = await captureComponentIntegrity(
        "secure-payment",
        componentRef.current
      );

      // Generate full report
      const report = await generateIntegrityReport([
        { id: "secure-payment", element: componentRef.current },
      ]);

      setState((prev) => ({ ...prev, integrityReport: report }));

      // Verify with server
      const serverResult = await verifyWithServer(report, apiEndpoint);

      if (!serverResult.valid) {
        console.error("[INTEGRITY] Server verification failed:", serverResult.message);
        return false;
      }

      if (report.isCompromised) {
        setState((prev) => ({
          ...prev,
          stage: "blocked",
          error: "UI integrity check failed. Page may be compromised.",
        }));
        return false;
      }

      return true;
    } catch (error) {
      console.error("[INTEGRITY] Verification error:", error);
      return false;
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // PAYMENT FLOW
  // ─────────────────────────────────────────────────────────────────────────

  const handleProceedToVerify = async () => {
    setState((prev) => ({ ...prev, stage: "verify", error: null }));

    const isValid = await verifyIntegrity();
    if (!isValid) {
      setState((prev) => ({
        ...prev,
        stage: "blocked",
        error: prev.error || "Integrity verification failed",
      }));
      return;
    }

    // Create transaction intent
    const componentHash = state.integrityReport?.pageIntegrity.combinedHash || "";
    
    const intent = await createTransactionIntent(
      {
        type: "TRANSFER",
        fromAddress: walletAddress,
        toAddress: payment.toAddress,
        valueWei: payment.valueWei,
        chainId: payment.chainId,
        networkName: payment.networkName,
        tokenAddress: payment.tokenAddress,
        tokenSymbol: payment.tokenSymbol,
      },
      componentHash,
      {
        toAddress: payment.toAddress,
        valueWei: payment.valueWei,
        displayedValue: weiToEth(payment.valueWei),
      }
    );

    // Generate confirmation data
    // First, get compliance evaluation from orchestrator
    const orchestratorUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8007";
    try {
      const complianceResponse = await fetch(`${orchestratorUrl}/evaluate-with-integrity`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent,
          integrityReport: state.integrityReport,
          intentHash: await getIntentHash(intent),
        }),
      });

      if (!complianceResponse.ok) {
        const error = await complianceResponse.json();
        throw new Error(error.detail || "Compliance check failed");
      }

      const complianceResult = await complianceResponse.json();
      const decision = complianceResult.decision;

      // Check if transaction is blocked
      if (decision.action === "BLOCK") {
        setState((prev) => ({
          ...prev,
          stage: "blocked",
          error: `Transaction blocked: ${decision.reasons.join(", ")}`,
        }));
        return;
      }

      // Generate confirmation with compliance warnings
      const warnings = decision.reasons || [];
      if (decision.requires_sar) {
        warnings.push("⚠️ Suspicious Activity Report (SAR) will be filed");
      }
      if (decision.requires_escrow) {
        warnings.push(`⏳ Transaction will be held in escrow for ${decision.escrow_duration_hours} hours`);
      }

      const confirmationData = await generateConfirmationData(
        intent,
        decision.risk_score,
        warnings
      );

      setState((prev) => ({
        ...prev,
        stage: "confirm",
        intent,
        confirmationData,
      }));
    } catch (error) {
      setState((prev) => ({
        ...prev,
        stage: "blocked",
        error: `Compliance check failed: ${error}`,
      }));
    }
  };

  const handleConfirm = async () => {
    if (!state.intent) return;

    setState((prev) => ({ ...prev, stage: "sign" }));

    try {
      // Get intent hash for signing
      const intentHash = await getIntentHash(state.intent);

      // Request signature from wallet
      // In production: use EIP-712 typed data signing
      const message = `AMTTP Payment Authorization\n\nIntent: ${intentHash}\nTo: ${state.intent.toAddress}\nValue: ${state.intent.valueEth} ETH\nChain: ${state.intent.networkName}\nTime: ${new Date(state.intent.timestamp).toISOString()}`;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const ethereum = (window as any).ethereum;
      if (!ethereum) {
        throw new Error("No wallet connected");
      }

      const signature = await ethereum.request({
        method: "personal_sign",
        params: [message, walletAddress],
      });

      // Submit to backend with integrity proof
      const response = await fetch(`${apiEndpoint}/submit-payment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent: state.intent,
          intentHash,
          signature,
          integrityReport: state.integrityReport,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || "Payment submission failed");
      }

      const result = await response.json();
      
      setState((prev) => ({ ...prev, stage: "complete" }));
      onComplete(result.txHash);
    } catch (error) {
      setState((prev) => ({
        ...prev,
        stage: "confirm",
        error: `Signing failed: ${error}`,
      }));
    }
  };

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────

  return (
    <div
      ref={componentRef}
      className="secure-payment-container"
      data-integrity-protected="true"
    >
      {/* Security Status Bar */}
      <SecurityStatusBar
        integrityReport={state.integrityReport}
        mutationAlerts={state.mutationAlerts}
      />

      {/* Error Display */}
      {state.error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          <strong>Security Alert:</strong> {state.error}
        </div>
      )}

      {/* Stage: Blocked */}
      {state.stage === "blocked" && (
        <BlockedView error={state.error || "Unknown error"} onCancel={onCancel} />
      )}

      {/* Stage: Input */}
      {state.stage === "input" && (
        <PaymentInputView
          payment={payment}
          setPayment={setPayment}
          onProceed={handleProceedToVerify}
          onCancel={onCancel}
        />
      )}

      {/* Stage: Verify */}
      {state.stage === "verify" && <VerifyingView />}

      {/* Stage: Confirm */}
      {state.stage === "confirm" && state.confirmationData && (
        <ConfirmationView
          data={state.confirmationData}
          intent={state.intent!}
          onConfirm={handleConfirm}
          onCancel={onCancel}
        />
      )}

      {/* Stage: Sign */}
      {state.stage === "sign" && <SigningView />}

      {/* Stage: Complete */}
      {state.stage === "complete" && <CompleteView />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SUB-COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

function SecurityStatusBar({
  integrityReport,
  mutationAlerts,
}: {
  integrityReport: IntegrityReport | null;
  mutationAlerts: MutationAlert[];
}) {
  const status = integrityReport?.riskLevel || "checking";
  const alertCount = mutationAlerts.length;

  const statusColors = {
    safe: "bg-green-500",
    suspicious: "bg-yellow-500",
    compromised: "bg-red-500",
    checking: "bg-gray-400",
  };

  return (
    <div className="flex items-center justify-between p-2 bg-gray-100 rounded mb-4 text-sm">
      <div className="flex items-center gap-2">
        <div className={`w-3 h-3 rounded-full ${statusColors[status as keyof typeof statusColors]}`} />
        <span>
          UI Integrity: <strong>{status.toUpperCase()}</strong>
        </span>
      </div>
      {alertCount > 0 && (
        <span className="text-red-600">
          {alertCount} security alert{alertCount > 1 ? "s" : ""}
        </span>
      )}
    </div>
  );
}

function PaymentInputView({
  payment,
  setPayment,
  onProceed,
  onCancel,
}: {
  payment: PaymentRequest;
  setPayment: React.Dispatch<React.SetStateAction<PaymentRequest>>;
  onProceed: () => void;
  onCancel: () => void;
}) {
  const [ethValue, setEthValue] = useState("");

  const handleEthChange = (value: string) => {
    setEthValue(value);
    try {
      const wei = ethToWei(value);
      setPayment((p) => ({ ...p, valueWei: wei }));
    } catch {
      // Invalid input
    }
  };

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Secure Payment</h2>

      <div>
        <label className="block text-sm font-medium mb-1">Recipient Address</label>
        <input
          type="text"
          className="w-full p-2 border rounded font-mono text-sm"
          placeholder="0x..."
          value={payment.toAddress}
          onChange={(e) => setPayment((p) => ({ ...p, toAddress: e.target.value }))}
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Amount (ETH)</label>
        <input
          type="text"
          className="w-full p-2 border rounded"
          placeholder="0.0"
          value={ethValue}
          onChange={(e) => handleEthChange(e.target.value)}
        />
      </div>

      <div className="flex gap-2">
        <button
          className="flex-1 bg-blue-600 text-white py-2 px-4 rounded hover:bg-blue-700"
          onClick={onProceed}
          disabled={!payment.toAddress || payment.valueWei === "0"}
        >
          Verify & Continue
        </button>
        <button
          className="px-4 py-2 border rounded hover:bg-gray-100"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function VerifyingView() {
  return (
    <div className="text-center py-8">
      <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
      <p className="text-lg font-medium">Verifying UI Integrity...</p>
      <p className="text-sm text-gray-500">Checking for tampering and manipulation</p>
    </div>
  );
}

function ConfirmationView({
  data,
  intent,
  onConfirm,
  onCancel,
}: {
  data: ConfirmationData;
  intent: TransactionIntent;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const warningStyles = {
    none: "",
    caution: "border-yellow-400 bg-yellow-50",
    warning: "border-orange-400 bg-orange-50",
    danger: "border-red-400 bg-red-50",
  };

  return (
    <div className={`space-y-4 p-4 border-2 rounded ${warningStyles[data.warningLevel]}`}>
      <h2 className="text-xl font-bold">Confirm Transaction</h2>

      {/* Integrity Hash - proves UI wasn't manipulated */}
      <div className="bg-gray-100 p-2 rounded font-mono text-xs">
        Intent Hash: {data.intentHash}
      </div>

      {/* Transaction Details - displayed from verified data */}
      <div className="space-y-2">
        <div className="flex justify-between">
          <span className="text-gray-600">To Address:</span>
          <span className="font-mono text-sm">{data.toAddressChecksum}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">Amount:</span>
          <span className="font-bold">{data.valueEth} ETH</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-600">Network:</span>
          <span>{data.networkName}</span>
        </div>
      </div>

      {/* Warnings */}
      {data.warnings.length > 0 && (
        <div className="bg-yellow-100 border border-yellow-400 p-3 rounded">
          <strong>Warnings:</strong>
          <ul className="list-disc ml-4 mt-1">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Visual Address Verification */}
      <div className="bg-blue-50 border border-blue-200 p-3 rounded">
        <p className="text-sm font-medium mb-2">Visual Address Check:</p>
        <div className="grid grid-cols-4 gap-1">
          {intent.toAddress.slice(2).match(/.{1,10}/g)?.map((chunk, i) => (
            <span key={i} className="font-mono text-xs bg-white p-1 rounded text-center">
              {chunk}
            </span>
          ))}
        </div>
      </div>

      <div className="flex gap-2 pt-4">
        <button
          className="flex-1 bg-green-600 text-white py-3 px-4 rounded font-bold hover:bg-green-700"
          onClick={onConfirm}
        >
          ✓ Sign & Send
        </button>
        <button
          className="px-4 py-3 border rounded hover:bg-gray-100"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function SigningView() {
  return (
    <div className="text-center py-8">
      <div className="animate-pulse text-4xl mb-4">🔐</div>
      <p className="text-lg font-medium">Waiting for Wallet Signature...</p>
      <p className="text-sm text-gray-500">Please confirm in your wallet</p>
    </div>
  );
}

function CompleteView() {
  return (
    <div className="text-center py-8">
      <div className="text-4xl mb-4">✅</div>
      <p className="text-lg font-medium text-green-600">Transaction Submitted</p>
    </div>
  );
}

function BlockedView({ error, onCancel }: { error: string; onCancel: () => void }) {
  return (
    <div className="text-center py-8 bg-red-50 border-2 border-red-400 rounded">
      <div className="text-4xl mb-4">🚨</div>
      <p className="text-xl font-bold text-red-600">Transaction Blocked</p>
      <p className="text-red-700 mt-2">{error}</p>
      <p className="text-sm text-gray-600 mt-4">
        This page may have been compromised. Do not proceed with any transactions.
      </p>
      <button
        className="mt-4 px-6 py-2 bg-gray-600 text-white rounded hover:bg-gray-700"
        onClick={onCancel}
      >
        Close
      </button>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

function ethToWei(eth: string): string {
  const parsed = parseFloat(eth);
  if (isNaN(parsed)) return "0";
  return (BigInt(Math.floor(parsed * 1e18))).toString();
}

function weiToEth(wei: string): string {
  const bn = BigInt(wei);
  const eth = Number(bn) / 1e18;
  return eth.toFixed(6);
}

export default SecurePaymentFlow;
