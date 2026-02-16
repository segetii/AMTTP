'use client';

import React, { useState, useCallback } from 'react';
import {
  CriticalAction,
  AttestationResult,
  gateCriticalAction,
  isWebAuthnSupported,
  hasPlatformAuthenticator,
} from '@/lib/tee-attestation';

interface CriticalActionDialogProps {
  action: CriticalAction;
  userRole: number;
  credentialId?: string;
  details?: Record<string, string>;
  onConfirm: (attestation: AttestationResult) => void;
  onCancel: () => void;
}

/**
 * Critical Action Confirmation Dialog
 *
 * Shows action details, performs TEE attestation, and returns result.
 * Falls back to PIN entry if hardware attestation is unavailable.
 *
 * Usage:
 *   <CriticalActionDialog
 *     action={action}
 *     userRole={4}
 *     onConfirm={(att) => executeAction(att)}
 *     onCancel={() => setOpen(false)}
 *   />
 */
export function CriticalActionDialog({
  action,
  userRole,
  credentialId,
  details = {},
  onConfirm,
  onCancel,
}: CriticalActionDialogProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [showPinEntry, setShowPinEntry] = useState(false);
  const [pin, setPin] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [hwAvailable, setHwAvailable] = useState<boolean | null>(null);

  // Check hardware on mount
  React.useEffect(() => {
    (async () => {
      const supported = isWebAuthnSupported();
      const platform = supported ? await hasPlatformAuthenticator() : false;
      setHwAvailable(platform);
    })();
  }, []);

  const handleConfirm = useCallback(async () => {
    setIsProcessing(true);
    setError(null);

    const result = await gateCriticalAction(action, userRole, credentialId);

    if (result.success) {
      onConfirm(result);
      return;
    }

    // Needs PIN fallback
    if (result.error === 'NEEDS_PIN_CONFIRMATION') {
      if (showPinEntry && pin.length >= 4) {
        // PIN entered — in production, verify against stored hash
        onConfirm({
          success: true,
          method: 'fallback-pin',
          timestamp: Date.now(),
        });
        return;
      }
      setShowPinEntry(true);
      setIsProcessing(false);
      return;
    }

    setError(result.error ?? 'Attestation failed');
    setIsProcessing(false);
  }, [action, userRole, credentialId, onConfirm, showPinEntry, pin]);

  const roleOk = userRole >= action.minRole;

  return (
    <div style={styles.overlay}>
      <div style={styles.dialog}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.iconBox}>🛡️</div>
          <div>
            <div style={styles.tag}>CRITICAL ACTION</div>
            <div style={styles.title}>{action.label}</div>
          </div>
        </div>

        {/* Description */}
        <p style={styles.desc}>{action.description}</p>

        {/* Details */}
        {Object.entries(details).length > 0 && (
          <div style={styles.detailsBox}>
            {Object.entries(details).map(([k, v]) => (
              <div key={k} style={styles.detailRow}>
                <span style={styles.detailKey}>{k}:</span>
                <span style={styles.detailVal}>{v}</span>
              </div>
            ))}
          </div>
        )}

        {/* Security Requirements */}
        <div style={styles.reqBox}>
          <div style={styles.reqTitle}>Security Requirements</div>
          <Requirement label={`Role R${action.minRole}+`} satisfied={roleOk} />
          {action.requiresTEE && (
            <Requirement
              label="Hardware attestation"
              satisfied={false}
              pending
              note={hwAvailable === false ? '(not available — PIN fallback)' : undefined}
            />
          )}
          {action.requiresMultisig && (
            <Requirement label="Multisig approval required" satisfied={false} pending />
          )}
        </div>

        {/* PIN entry */}
        {showPinEntry && (
          <div style={{ marginTop: 16 }}>
            <p style={{ color: '#9CA3AF', fontSize: 12, marginBottom: 8 }}>
              Hardware attestation unavailable. Enter your PIN to confirm:
            </p>
            <input
              type="password"
              maxLength={6}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
              style={styles.pinInput}
              autoFocus
              placeholder="••••••"
            />
          </div>
        )}

        {/* Error */}
        {error && <p style={styles.error}>{error}</p>}

        {/* Actions */}
        <div style={styles.actions}>
          <button onClick={onCancel} style={styles.cancelBtn} disabled={isProcessing}>
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            style={{
              ...styles.confirmBtn,
              opacity: isProcessing || !roleOk ? 0.5 : 1,
            }}
            disabled={isProcessing || !roleOk}
          >
            {isProcessing ? 'Verifying...' : showPinEntry ? 'Confirm with PIN' : 'Authenticate'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Requirement({
  label,
  satisfied,
  pending,
  note,
}: {
  label: string;
  satisfied: boolean;
  pending?: boolean;
  note?: string;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '2px 0' }}>
      <span style={{ fontSize: 14 }}>
        {satisfied ? '✅' : pending ? '⏳' : '❌'}
      </span>
      <span style={{ color: satisfied ? '#10B981' : '#9CA3AF', fontSize: 12 }}>
        {label}
        {note && <span style={{ color: '#6B7280', marginLeft: 4 }}>{note}</span>}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hook for easy usage
// ---------------------------------------------------------------------------

export function useCriticalAction() {
  const [dialogState, setDialogState] = useState<{
    action: CriticalAction;
    userRole: number;
    credentialId?: string;
    details?: Record<string, string>;
    resolve: (result: AttestationResult | null) => void;
  } | null>(null);

  const gate = useCallback(
    (
      action: CriticalAction,
      userRole: number,
      credentialId?: string,
      details?: Record<string, string>,
    ): Promise<AttestationResult | null> => {
      return new Promise((resolve) => {
        setDialogState({ action, userRole, credentialId, details, resolve });
      });
    },
    [],
  );

  const dialog = dialogState ? (
    <CriticalActionDialog
      action={dialogState.action}
      userRole={dialogState.userRole}
      credentialId={dialogState.credentialId}
      details={dialogState.details}
      onConfirm={(att) => {
        dialogState.resolve(att);
        setDialogState(null);
      }}
      onCancel={() => {
        dialogState.resolve(null);
        setDialogState(null);
      }}
    />
  ) : null;

  return { gate, dialog };
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10000,
    backdropFilter: 'blur(4px)',
  },
  dialog: {
    background: '#1A1A2E',
    borderRadius: 16,
    padding: 24,
    maxWidth: 480,
    width: '90%',
    border: '1px solid rgba(245,158,11,0.3)',
    fontFamily: 'system-ui, -apple-system, sans-serif',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    marginBottom: 16,
  },
  iconBox: {
    width: 40,
    height: 40,
    borderRadius: 8,
    background: 'rgba(245,158,11,0.2)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 20,
  },
  tag: {
    color: '#F59E0B',
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 1.5,
  },
  title: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: 600,
    marginTop: 2,
  },
  desc: {
    color: '#9CA3AF',
    fontSize: 14,
    lineHeight: '1.5',
    marginBottom: 16,
  },
  detailsBox: {
    background: 'rgba(255,255,255,0.05)',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
  },
  detailRow: {
    display: 'flex',
    gap: 8,
    padding: '2px 0',
  },
  detailKey: {
    color: '#6B7280',
    fontSize: 12,
  },
  detailVal: {
    color: '#FFFFFF',
    fontSize: 12,
    fontFamily: 'monospace',
  },
  reqBox: {
    background: 'rgba(255,255,255,0.05)',
    borderRadius: 8,
    padding: 12,
  },
  reqTitle: {
    color: '#D1D5DB',
    fontSize: 12,
    fontWeight: 600,
    marginBottom: 8,
  },
  pinInput: {
    width: '100%',
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8,
    padding: '10px 16px',
    color: '#FFFFFF',
    fontSize: 20,
    letterSpacing: 8,
    textAlign: 'center' as const,
    outline: 'none',
  },
  error: {
    color: '#DC2626',
    fontSize: 12,
    marginTop: 12,
  },
  actions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 20,
  },
  cancelBtn: {
    background: 'transparent',
    border: 'none',
    color: '#6B7280',
    padding: '8px 16px',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 14,
  },
  confirmBtn: {
    background: '#F59E0B',
    border: 'none',
    color: '#000000',
    padding: '8px 20px',
    borderRadius: 8,
    cursor: 'pointer',
    fontSize: 14,
    fontWeight: 600,
  },
};
