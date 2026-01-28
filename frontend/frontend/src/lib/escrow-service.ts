/**
 * Escrow Service
 * 
 * Ground Truth Reference:
 * - Escrow is risk mitigation, not a payment rail
 * - Atomic: Fund, Release, Dispute
 * - All actions bound to UI snapshot hash
 */

'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  EscrowContract,
  EscrowStatus,
  EscrowTrigger,
  EscrowType,
  EscrowAction,
  FundEscrowParams,
  ReleaseEscrowParams,
  DisputeEscrowParams,
  EscrowSummary,
  toEscrowSummary,
  ReleaseCondition,
} from '@/types/escrow';
import { Role } from '@/types/rbac';
import { sha256 } from './ui-snapshot-chain';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE RESULT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface EscrowServiceResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  txHash?: string;
}

export interface CreateEscrowParams {
  recipient: string;
  amount: string;
  token: string;
  chainId: number;
  trigger: EscrowTrigger;
  triggerReason: string;
  lockDurationHours: number;
  type?: EscrowType;
  uiSnapshotHash: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// API FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export async function createEscrow(
  params: CreateEscrowParams,
  senderAddress: string
): Promise<EscrowServiceResult<EscrowContract>> {
  try {
    // Generate escrow ID
    const escrowId = `escrow_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    
    // Build release conditions based on type
    const releaseConditions: ReleaseCondition[] = [
      {
        id: 'rc_1',
        type: 'time_elapsed',
        description: `${params.lockDurationHours} hours must pass`,
        met: false,
      },
      {
        id: 'rc_2',
        type: 'dispute_window_passed',
        description: 'No disputes raised during lock period',
        met: false,
      },
    ];
    
    const now = new Date();
    const expiresAt = new Date(now.getTime() + params.lockDurationHours * 60 * 60 * 1000);
    
    const escrow: EscrowContract = {
      id: escrowId,
      type: params.type || EscrowType.TIME_LOCKED,
      status: EscrowStatus.PENDING_FUNDING,
      
      sender: {
        address: senderAddress,
        verified: true,
      },
      recipient: {
        address: params.recipient,
        verified: false,
      },
      
      token: params.token,
      amount: params.amount,
      amountUSD: parseFloat(params.amount) * 1800, // Mock ETH price
      chainId: params.chainId,
      
      trigger: params.trigger,
      triggerReason: params.triggerReason,
      riskScoreAtCreation: 65, // Would come from ML model
      
      createdAt: now.toISOString(),
      expiresAt: expiresAt.toISOString(),
      
      lockDurationHours: params.lockDurationHours,
      releaseConditions,
      
      contractAddress: `0x${Math.random().toString(16).slice(2, 42)}`,
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
      
      uiSnapshotHash: params.uiSnapshotHash,
    };
    
    // In production, this would call the backend API
    // For now, store in localStorage for demo
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored) as EscrowContract[];
    escrows.push(escrow);
    localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    
    return {
      success: true,
      data: escrow,
      txHash: escrow.txHash,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to create escrow',
    };
  }
}

export async function fundEscrow(
  params: FundEscrowParams,
  senderAddress: string,
  uiSnapshotHash: string
): Promise<EscrowServiceResult<EscrowContract>> {
  try {
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored) as EscrowContract[];
    const index = escrows.findIndex(e => e.id === params.escrowId);
    
    if (index === -1) {
      return { success: false, error: 'Escrow not found' };
    }
    
    const escrow = escrows[index];
    
    if (escrow.status !== EscrowStatus.PENDING_FUNDING) {
      return { success: false, error: 'Escrow is not pending funding' };
    }
    
    if (escrow.sender.address.toLowerCase() !== senderAddress.toLowerCase()) {
      return { success: false, error: 'Only sender can fund escrow' };
    }
    
    // Update escrow
    escrow.status = EscrowStatus.FUNDED;
    escrow.fundedAt = new Date().toISOString();
    escrow.uiSnapshotHash = uiSnapshotHash;
    
    escrows[index] = escrow;
    localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    
    return {
      success: true,
      data: escrow,
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to fund escrow',
    };
  }
}

export async function requestRelease(
  params: ReleaseEscrowParams,
  recipientAddress: string,
  uiSnapshotHash: string
): Promise<EscrowServiceResult<EscrowContract>> {
  try {
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored) as EscrowContract[];
    const index = escrows.findIndex(e => e.id === params.escrowId);
    
    if (index === -1) {
      return { success: false, error: 'Escrow not found' };
    }
    
    const escrow = escrows[index];
    
    if (escrow.status !== EscrowStatus.FUNDED) {
      return { success: false, error: 'Escrow must be funded to request release' };
    }
    
    if (escrow.recipient.address.toLowerCase() !== recipientAddress.toLowerCase()) {
      return { success: false, error: 'Only recipient can request release' };
    }
    
    // Update escrow
    escrow.status = EscrowStatus.RELEASE_REQUESTED;
    escrow.releaseRequestedAt = new Date().toISOString();
    escrow.uiSnapshotHash = uiSnapshotHash;
    
    escrows[index] = escrow;
    localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    
    return {
      success: true,
      data: escrow,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to request release',
    };
  }
}

export async function approveRelease(
  escrowId: string,
  senderAddress: string,
  uiSnapshotHash: string
): Promise<EscrowServiceResult<EscrowContract>> {
  try {
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored) as EscrowContract[];
    const index = escrows.findIndex(e => e.id === escrowId);
    
    if (index === -1) {
      return { success: false, error: 'Escrow not found' };
    }
    
    const escrow = escrows[index];
    
    if (escrow.status !== EscrowStatus.RELEASE_REQUESTED) {
      return { success: false, error: 'Release must be requested first' };
    }
    
    if (escrow.sender.address.toLowerCase() !== senderAddress.toLowerCase()) {
      return { success: false, error: 'Only sender can approve release' };
    }
    
    // Update escrow
    escrow.status = EscrowStatus.RELEASED;
    escrow.releasedAt = new Date().toISOString();
    escrow.uiSnapshotHash = uiSnapshotHash;
    
    // Mark conditions as met
    escrow.releaseConditions = escrow.releaseConditions.map(c => ({
      ...c,
      met: true,
      metAt: new Date().toISOString(),
    }));
    
    escrows[index] = escrow;
    localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    
    return {
      success: true,
      data: escrow,
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to approve release',
    };
  }
}

export async function raiseDispute(
  params: DisputeEscrowParams,
  disputerAddress: string,
  uiSnapshotHash: string
): Promise<EscrowServiceResult<{ escrow: EscrowContract; disputeId: string }>> {
  try {
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored) as EscrowContract[];
    const index = escrows.findIndex(e => e.id === params.escrowId);
    
    if (index === -1) {
      return { success: false, error: 'Escrow not found' };
    }
    
    const escrow = escrows[index];
    
    if (![EscrowStatus.FUNDED, EscrowStatus.RELEASE_REQUESTED].includes(escrow.status)) {
      return { success: false, error: 'Cannot dispute in current status' };
    }
    
    const isSender = escrow.sender.address.toLowerCase() === disputerAddress.toLowerCase();
    const isRecipient = escrow.recipient.address.toLowerCase() === disputerAddress.toLowerCase();
    
    if (!isSender && !isRecipient) {
      return { success: false, error: 'Only parties can raise dispute' };
    }
    
    // Generate dispute ID
    const disputeId = `dispute_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    
    // Update escrow
    escrow.status = EscrowStatus.DISPUTE_RAISED;
    escrow.disputeId = disputeId;
    escrow.disputeRaisedAt = new Date().toISOString();
    escrow.uiSnapshotHash = uiSnapshotHash;
    
    escrows[index] = escrow;
    localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    
    return {
      success: true,
      data: { escrow, disputeId },
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to raise dispute',
    };
  }
}

export async function getEscrow(escrowId: string): Promise<EscrowContract | null> {
  const stored = localStorage.getItem('amttp_escrows') || '[]';
  const escrows = JSON.parse(stored) as EscrowContract[];
  return escrows.find(e => e.id === escrowId) || null;
}

export async function getUserEscrows(userAddress: string): Promise<EscrowContract[]> {
  const stored = localStorage.getItem('amttp_escrows') || '[]';
  const escrows = JSON.parse(stored) as EscrowContract[];
  return escrows.filter(
    e => e.sender.address.toLowerCase() === userAddress.toLowerCase() ||
         e.recipient.address.toLowerCase() === userAddress.toLowerCase()
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export interface UseEscrowReturn {
  escrows: EscrowContract[];
  summaries: EscrowSummary[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  create: (params: CreateEscrowParams) => Promise<EscrowServiceResult<EscrowContract>>;
  fund: (params: FundEscrowParams) => Promise<EscrowServiceResult<EscrowContract>>;
  requestRelease: (params: ReleaseEscrowParams) => Promise<EscrowServiceResult<EscrowContract>>;
  approveRelease: (escrowId: string) => Promise<EscrowServiceResult<EscrowContract>>;
  raiseDispute: (params: DisputeEscrowParams) => Promise<EscrowServiceResult<{ escrow: EscrowContract; disputeId: string }>>;
  
  // Refresh
  refresh: () => Promise<void>;
}

export function useEscrow(userAddress: string | null): UseEscrowReturn {
  const [escrows, setEscrows] = useState<EscrowContract[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Fetch escrows
  const refresh = useCallback(async () => {
    if (!userAddress) {
      setEscrows([]);
      setIsLoading(false);
      return;
    }
    
    setIsLoading(true);
    try {
      const userEscrows = await getUserEscrows(userAddress);
      setEscrows(userEscrows);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch escrows');
    } finally {
      setIsLoading(false);
    }
  }, [userAddress]);
  
  useEffect(() => {
    refresh();
  }, [refresh]);
  
  // Generate UI snapshot hash
  const getSnapshotHash = useCallback(async () => {
    return await sha256(JSON.stringify({
      timestamp: Date.now(),
      userAddress,
      action: 'escrow_action',
    }));
  }, [userAddress]);
  
  // Actions
  const create = useCallback(async (params: CreateEscrowParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await createEscrow(params, userAddress);
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh]);
  
  const doFund = useCallback(async (params: FundEscrowParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await fundEscrow(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doRequestRelease = useCallback(async (params: ReleaseEscrowParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await requestRelease(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doApproveRelease = useCallback(async (escrowId: string) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await approveRelease(escrowId, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doRaiseDispute = useCallback(async (params: DisputeEscrowParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await raiseDispute(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  // Summaries for Focus Mode
  const summaries = userAddress 
    ? escrows.map(e => toEscrowSummary(e, userAddress))
    : [];
  
  return {
    escrows,
    summaries,
    isLoading,
    error,
    create,
    fund: doFund,
    requestRelease: doRequestRelease,
    approveRelease: doApproveRelease,
    raiseDispute: doRaiseDispute,
    refresh,
  };
}
