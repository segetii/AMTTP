/**
 * Dispute Service
 * 
 * Ground Truth Reference:
 * - Evidence-driven dispute resolution
 * - Kleros integration for decentralized arbitration
 * - All actions bound to UI snapshot hash
 */

'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  Dispute,
  DisputeStatus,
  DisputeCategory,
  DisputeOutcome,
  Evidence,
  DisputeSummary,
  FileDisputeParams,
  RespondToDisputeParams,
  AppealDisputeParams,
  EvidenceSubmission,
  toDisputeSummary,
} from '@/types/dispute';
import { sha256 } from './ui-snapshot-chain';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

// ═══════════════════════════════════════════════════════════════════════════════
// SERVICE RESULT TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface DisputeServiceResult<T = void> {
  success: boolean;
  data?: T;
  error?: string;
  txHash?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// API FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export async function fileDispute(
  params: FileDisputeParams,
  claimantAddress: string,
  uiSnapshotHash: string
): Promise<DisputeServiceResult<Dispute>> {
  try {
    // Generate dispute ID
    const disputeId = `dispute_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    
    // Get escrow info (would fetch from backend)
    const stored = localStorage.getItem('amttp_escrows') || '[]';
    const escrows = JSON.parse(stored);
    const escrow = escrows.find((e: any) => e.id === params.escrowId);
    
    if (!escrow) {
      return { success: false, error: 'Escrow not found' };
    }
    
    const now = new Date();
    const evidenceDeadline = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000); // 7 days
    const responseDeadline = new Date(now.getTime() + 3 * 24 * 60 * 60 * 1000); // 3 days
    
    const isClaimantSender = escrow.sender.address.toLowerCase() === claimantAddress.toLowerCase();
    
    const dispute: Dispute = {
      id: disputeId,
      status: DisputeStatus.FILED,
      category: params.category,
      outcome: DisputeOutcome.PENDING,
      
      escrowId: params.escrowId,
      escrowAmount: escrow.amount,
      escrowToken: escrow.token,
      
      claimant: {
        address: claimantAddress,
        role: isClaimantSender ? 'sender' : 'recipient',
      },
      respondent: {
        address: isClaimantSender ? escrow.recipient.address : escrow.sender.address,
        role: isClaimantSender ? 'recipient' : 'sender',
      },
      
      claim: {
        summary: params.summary,
        requestedOutcome: params.requestedOutcome,
        requestedAmount: params.requestedAmount,
        details: params.details,
      },
      
      evidence: [],
      evidenceDeadline: evidenceDeadline.toISOString(),
      
      arbitrationProvider: 'kleros',
      arbitrationFee: '0.05',
      arbitrationFeeToken: 'ETH',
      
      filedAt: now.toISOString(),
      responseDeadline: responseDeadline.toISOString(),
      
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
      contractAddress: `0x${Math.random().toString(16).slice(2, 42)}`,
      
      uiSnapshotHash,
    };
    
    // Store dispute
    const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
    disputes.push(dispute);
    localStorage.setItem('amttp_disputes', JSON.stringify(disputes));
    
    // Update escrow status
    const escrowIndex = escrows.findIndex((e: any) => e.id === params.escrowId);
    if (escrowIndex !== -1) {
      escrows[escrowIndex].status = 'DISPUTE_RAISED';
      escrows[escrowIndex].disputeId = disputeId;
      escrows[escrowIndex].disputeRaisedAt = now.toISOString();
      localStorage.setItem('amttp_escrows', JSON.stringify(escrows));
    }
    
    return {
      success: true,
      data: dispute,
      txHash: dispute.txHash,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to file dispute',
    };
  }
}

export async function respondToDispute(
  params: RespondToDisputeParams,
  respondentAddress: string,
  uiSnapshotHash: string
): Promise<DisputeServiceResult<Dispute>> {
  try {
    const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
    const index = disputes.findIndex((d: Dispute) => d.id === params.disputeId);
    
    if (index === -1) {
      return { success: false, error: 'Dispute not found' };
    }
    
    const dispute = disputes[index] as Dispute;
    
    if (dispute.respondent.address.toLowerCase() !== respondentAddress.toLowerCase()) {
      return { success: false, error: 'Only respondent can respond' };
    }
    
    if (dispute.response) {
      return { success: false, error: 'Already responded' };
    }
    
    // Update dispute
    dispute.response = {
      summary: params.summary,
      counterClaim: params.counterClaim,
      submittedAt: new Date().toISOString(),
    };
    dispute.status = DisputeStatus.EVIDENCE_PERIOD;
    dispute.uiSnapshotHash = uiSnapshotHash;
    
    disputes[index] = dispute;
    localStorage.setItem('amttp_disputes', JSON.stringify(disputes));
    
    return {
      success: true,
      data: dispute,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to respond to dispute',
    };
  }
}

export async function submitEvidence(
  submission: EvidenceSubmission,
  submitterAddress: string,
  uiSnapshotHash: string
): Promise<DisputeServiceResult<Evidence>> {
  try {
    const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
    const index = disputes.findIndex((d: Dispute) => d.id === submission.disputeId);
    
    if (index === -1) {
      return { success: false, error: 'Dispute not found' };
    }
    
    const dispute = disputes[index] as Dispute;
    
    // Check if user is a party
    const isClaimant = dispute.claimant.address.toLowerCase() === submitterAddress.toLowerCase();
    const isRespondent = dispute.respondent.address.toLowerCase() === submitterAddress.toLowerCase();
    
    if (!isClaimant && !isRespondent) {
      return { success: false, error: 'Only parties can submit evidence' };
    }
    
    // Check deadline
    if (new Date(dispute.evidenceDeadline) < new Date()) {
      return { success: false, error: 'Evidence period has ended' };
    }
    
    // Generate file hashes
    const fileHashes = await Promise.all(
      submission.files.map(f => sha256(f.name + f.size))
    );
    
    // Create evidence
    const evidence: Evidence = {
      id: `evidence_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      disputeId: submission.disputeId,
      submittedBy: submitterAddress,
      submittedAt: new Date().toISOString(),
      
      title: submission.title,
      description: submission.description,
      category: submission.category,
      
      fileHashes,
      
      verified: false,
    };
    
    // Add to dispute
    dispute.evidence.push(evidence);
    dispute.uiSnapshotHash = uiSnapshotHash;
    
    disputes[index] = dispute;
    localStorage.setItem('amttp_disputes', JSON.stringify(disputes));
    
    return {
      success: true,
      data: evidence,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to submit evidence',
    };
  }
}

export async function requestArbitration(
  disputeId: string,
  requesterAddress: string,
  uiSnapshotHash: string
): Promise<DisputeServiceResult<Dispute>> {
  try {
    const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
    const index = disputes.findIndex((d: Dispute) => d.id === disputeId);
    
    if (index === -1) {
      return { success: false, error: 'Dispute not found' };
    }
    
    const dispute = disputes[index] as Dispute;
    
    // Check status
    if (dispute.status !== DisputeStatus.EVIDENCE_PERIOD) {
      return { success: false, error: 'Cannot request arbitration in current status' };
    }
    
    // Update dispute
    dispute.status = DisputeStatus.AWAITING_ARBITRATION;
    dispute.klerosDisputeId = Math.floor(Math.random() * 10000);
    dispute.klerosCourtId = 0; // General court
    dispute.arbitrationStartedAt = new Date().toISOString();
    dispute.uiSnapshotHash = uiSnapshotHash;
    
    disputes[index] = dispute;
    localStorage.setItem('amttp_disputes', JSON.stringify(disputes));
    
    return {
      success: true,
      data: dispute,
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to request arbitration',
    };
  }
}

export async function appealDispute(
  params: AppealDisputeParams,
  appellantAddress: string,
  uiSnapshotHash: string
): Promise<DisputeServiceResult<Dispute>> {
  try {
    const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
    const index = disputes.findIndex((d: Dispute) => d.id === params.disputeId);
    
    if (index === -1) {
      return { success: false, error: 'Dispute not found' };
    }
    
    const dispute = disputes[index] as Dispute;
    
    if (dispute.status !== DisputeStatus.APPEAL_PERIOD) {
      return { success: false, error: 'Not in appeal period' };
    }
    
    // Update dispute
    dispute.status = DisputeStatus.APPEALED;
    dispute.uiSnapshotHash = uiSnapshotHash;
    
    disputes[index] = dispute;
    localStorage.setItem('amttp_disputes', JSON.stringify(disputes));
    
    return {
      success: true,
      data: dispute,
      txHash: `0x${Math.random().toString(16).slice(2, 66)}`,
    };
  } catch (error: any) {
    return {
      success: false,
      error: error.message || 'Failed to appeal dispute',
    };
  }
}

export async function getDispute(disputeId: string): Promise<Dispute | null> {
  const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]');
  return disputes.find((d: Dispute) => d.id === disputeId) || null;
}

export async function getUserDisputes(userAddress: string): Promise<Dispute[]> {
  const disputes = JSON.parse(localStorage.getItem('amttp_disputes') || '[]') as Dispute[];
  return disputes.filter(
    d => d.claimant.address.toLowerCase() === userAddress.toLowerCase() ||
         d.respondent.address.toLowerCase() === userAddress.toLowerCase()
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export interface UseDisputeReturn {
  disputes: Dispute[];
  summaries: DisputeSummary[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  file: (params: FileDisputeParams) => Promise<DisputeServiceResult<Dispute>>;
  respond: (params: RespondToDisputeParams) => Promise<DisputeServiceResult<Dispute>>;
  submitEvidence: (submission: EvidenceSubmission) => Promise<DisputeServiceResult<Evidence>>;
  requestArbitration: (disputeId: string) => Promise<DisputeServiceResult<Dispute>>;
  appeal: (params: AppealDisputeParams) => Promise<DisputeServiceResult<Dispute>>;
  
  // Refresh
  refresh: () => Promise<void>;
}

export function useDispute(userAddress: string | null): UseDisputeReturn {
  const [disputes, setDisputes] = useState<Dispute[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // Fetch disputes
  const refresh = useCallback(async () => {
    if (!userAddress) {
      setDisputes([]);
      setIsLoading(false);
      return;
    }
    
    setIsLoading(true);
    try {
      const userDisputes = await getUserDisputes(userAddress);
      setDisputes(userDisputes);
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to fetch disputes');
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
      action: 'dispute_action',
    }));
  }, [userAddress]);
  
  // Actions
  const doFile = useCallback(async (params: FileDisputeParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await fileDispute(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doRespond = useCallback(async (params: RespondToDisputeParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await respondToDispute(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doSubmitEvidence = useCallback(async (submission: EvidenceSubmission) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await submitEvidence(submission, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doRequestArbitration = useCallback(async (disputeId: string) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await requestArbitration(disputeId, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  const doAppeal = useCallback(async (params: AppealDisputeParams) => {
    if (!userAddress) return { success: false, error: 'Not authenticated' };
    const result = await appealDispute(params, userAddress, await getSnapshotHash());
    if (result.success) await refresh();
    return result;
  }, [userAddress, refresh, getSnapshotHash]);
  
  // Summaries for Focus Mode
  const summaries = userAddress 
    ? disputes.map(d => toDisputeSummary(d, userAddress))
    : [];
  
  return {
    disputes,
    summaries,
    isLoading,
    error,
    file: doFile,
    respond: doRespond,
    submitEvidence: doSubmitEvidence,
    requestArbitration: doRequestArbitration,
    appeal: doAppeal,
    refresh,
  };
}
