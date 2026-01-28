'use client';

/**
 * DisputeDetail Component
 * 
 * Detailed view of a single dispute
 * Shows claim, response, evidence, and resolution
 * 
 * Ground Truth Reference:
 * - Evidence-driven dispute resolution
 * - Clear timeline and deadlines
 * - Both parties' perspectives visible
 */

import React, { useState } from 'react';
import {
  Dispute,
  DisputeStatus,
  DisputeOutcome,
  Evidence,
  getDisputeStatusLabel,
  getDisputeStatusColor,
  getCategoryLabel,
  getOutcomeLabel,
  canSubmitEvidence,
  canAppeal,
} from '@/types/dispute';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

interface DisputeDetailProps {
  dispute: Dispute;
  userAddress: string;
  onSubmitEvidence?: () => void;
  onRespond?: () => void;
  onRequestArbitration?: () => void;
  onAppeal?: () => void;
  onClose: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// EVIDENCE LIST
// ═══════════════════════════════════════════════════════════════════════════════

function EvidenceList({ evidence, claimantAddress }: { evidence: Evidence[]; claimantAddress: string }) {
  if (evidence.length === 0) {
    return (
      <div className="text-center py-6 text-slate-500">
        <p>No evidence submitted yet</p>
      </div>
    );
  }
  
  return (
    <div className="space-y-3">
      {evidence.map((e) => {
        const isClaimantEvidence = e.submittedBy.toLowerCase() === claimantAddress.toLowerCase();
        
        return (
          <div 
            key={e.id}
            className={`rounded-lg p-4 border ${
              isClaimantEvidence 
                ? 'bg-blue-900/20 border-blue-600/30' 
                : 'bg-orange-900/20 border-orange-600/30'
            }`}
          >
            <div className="flex items-start justify-between mb-2">
              <div>
                <h4 className="font-medium text-white">{e.title}</h4>
                <p className="text-xs text-slate-400">
                  {isClaimantEvidence ? 'Claimant' : 'Respondent'} • {new Date(e.submittedAt).toLocaleString()}
                </p>
              </div>
              <span className={`px-2 py-0.5 text-xs rounded ${
                e.verified 
                  ? 'bg-green-900/50 text-green-300' 
                  : 'bg-slate-700/50 text-slate-400'
              }`}>
                {e.verified ? '✓ Verified' : 'Pending'}
              </span>
            </div>
            <p className="text-sm text-slate-300">{e.description}</p>
            {e.fileHashes.length > 0 && (
              <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
                {e.fileHashes.length} file(s) attached
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// TIMELINE
// ═══════════════════════════════════════════════════════════════════════════════

function DisputeTimeline({ dispute }: { dispute: Dispute }) {
  const events = [
    { date: dispute.filedAt, label: 'Filed', icon: '📝', completed: true },
    { date: dispute.response?.submittedAt, label: 'Response', icon: '💬', completed: !!dispute.response },
    { date: dispute.arbitrationStartedAt, label: 'Arbitration', icon: '⚖️', completed: !!dispute.arbitrationStartedAt },
    { date: dispute.resolvedAt, label: 'Resolved', icon: '✅', completed: !!dispute.resolvedAt },
  ];
  
  return (
    <div className="relative">
      <div className="absolute left-4 top-6 bottom-6 w-0.5 bg-slate-700" />
      <div className="space-y-4">
        {events.map((event, idx) => (
          <div key={idx} className="flex items-start gap-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center z-10
                          ${event.completed ? 'bg-green-900/50 border-green-500' : 'bg-slate-800 border-slate-600'} 
                          border text-lg`}>
              {event.icon}
            </div>
            <div className="flex-1 pt-1">
              <p className={`font-medium ${event.completed ? 'text-white' : 'text-slate-500'}`}>
                {event.label}
              </p>
              {event.date && (
                <p className="text-sm text-slate-400">
                  {new Date(event.date).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function DisputeDetail({
  dispute,
  userAddress,
  onSubmitEvidence,
  onRespond,
  onRequestArbitration,
  onAppeal,
  onClose,
}: DisputeDetailProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'evidence' | 'timeline'>('overview');
  
  const isClaimant = dispute.claimant.address.toLowerCase() === userAddress.toLowerCase();
  const statusColor = getDisputeStatusColor(dispute.status);
  
  const colorClasses: Record<string, string> = {
    green: 'from-green-600 to-emerald-600',
    yellow: 'from-yellow-600 to-amber-600',
    orange: 'from-orange-600 to-red-600',
    red: 'from-red-600 to-rose-600',
    blue: 'from-blue-600 to-cyan-600',
    gray: 'from-slate-600 to-slate-700',
  };
  
  const canUserSubmitEvidence = canSubmitEvidence(dispute);
  const canUserRespond = !isClaimant && dispute.status === DisputeStatus.FILED && !dispute.response;
  const canUserAppeal = canAppeal(dispute, userAddress);
  const canRequestArb = dispute.status === DisputeStatus.EVIDENCE_PERIOD && 
                         new Date(dispute.evidenceDeadline) < new Date();
  
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 overflow-hidden max-w-2xl w-full max-h-[90vh] flex flex-col">
      {/* Header */}
      <div className={`bg-gradient-to-r ${colorClasses[statusColor]} px-6 py-4`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-white/70">Dispute #{dispute.id.slice(-8)}</p>
            <h2 className="text-xl font-bold text-white">{getDisputeStatusLabel(dispute.status)}</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      
      {/* Amount & Category */}
      <div className="px-6 py-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400">Disputed Amount</p>
            <p className="text-3xl font-bold text-white">
              {dispute.escrowAmount} <span className="text-lg text-slate-400">{dispute.escrowToken}</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-slate-400">Category</p>
            <p className="text-lg font-medium text-amber-400">{getCategoryLabel(dispute.category)}</p>
          </div>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="border-b border-slate-700">
        <nav className="flex">
          {(['overview', 'evidence', 'timeline'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-6 py-3 text-sm font-medium border-b-2 transition-colors
                        ${activeTab === tab 
                          ? 'border-cyan-400 text-cyan-400' 
                          : 'border-transparent text-slate-400 hover:text-white'}`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
              {tab === 'evidence' && dispute.evidence.length > 0 && (
                <span className="ml-2 px-1.5 py-0.5 text-xs bg-slate-700 rounded">
                  {dispute.evidence.length}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>
      
      {/* Content */}
      <div className="p-6 overflow-y-auto flex-1">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Parties */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-blue-900/20 rounded-lg p-4 border border-blue-600/30">
                <p className="text-xs text-blue-400 uppercase tracking-wide mb-2">Claimant</p>
                <p className="font-medium text-white">
                  {dispute.claimant.name || dispute.claimant.address.slice(0, 10) + '...'}
                </p>
                <p className="text-sm text-slate-400 capitalize">{dispute.claimant.role}</p>
                {isClaimant && (
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-cyan-900/50 text-cyan-300 rounded">
                    You
                  </span>
                )}
              </div>
              <div className="bg-orange-900/20 rounded-lg p-4 border border-orange-600/30">
                <p className="text-xs text-orange-400 uppercase tracking-wide mb-2">Respondent</p>
                <p className="font-medium text-white">
                  {dispute.respondent.name || dispute.respondent.address.slice(0, 10) + '...'}
                </p>
                <p className="text-sm text-slate-400 capitalize">{dispute.respondent.role}</p>
                {!isClaimant && (
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs bg-cyan-900/50 text-cyan-300 rounded">
                    You
                  </span>
                )}
              </div>
            </div>
            
            {/* Claim */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <h4 className="text-sm font-medium text-slate-400 mb-2">Claim</h4>
              <p className="font-medium text-white mb-2">{dispute.claim.summary}</p>
              <p className="text-sm text-slate-300">{dispute.claim.details}</p>
              <div className="mt-3 pt-3 border-t border-slate-700">
                <p className="text-sm text-slate-400">
                  Requested Outcome: <span className="text-white">{dispute.claim.requestedOutcome.replace(/_/g, ' ')}</span>
                </p>
              </div>
            </div>
            
            {/* Response */}
            {dispute.response ? (
              <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                <h4 className="text-sm font-medium text-slate-400 mb-2">Response</h4>
                <p className="text-sm text-slate-300">{dispute.response.summary}</p>
                {dispute.response.counterClaim && (
                  <div className="mt-2 p-2 bg-orange-900/20 rounded border border-orange-600/30">
                    <p className="text-xs text-orange-400 mb-1">Counter-Claim:</p>
                    <p className="text-sm text-slate-300">{dispute.response.counterClaim}</p>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-slate-800/30 rounded-lg p-4 border border-slate-700 text-center">
                <p className="text-slate-500">Awaiting respondent's response</p>
                <p className="text-sm text-amber-400 mt-1">
                  Deadline: {new Date(dispute.responseDeadline).toLocaleDateString()}
                </p>
              </div>
            )}
            
            {/* Resolution */}
            {dispute.resolution && (
              <div className={`rounded-lg p-4 border ${
                dispute.outcome === DisputeOutcome.CLAIMANT_WINS ? 'bg-green-900/20 border-green-600/30' :
                dispute.outcome === DisputeOutcome.RESPONDENT_WINS ? 'bg-red-900/20 border-red-600/30' :
                'bg-slate-800/50 border-slate-700'
              }`}>
                <h4 className="text-sm font-medium text-slate-400 mb-2">Resolution</h4>
                <p className="font-medium text-white mb-2">{getOutcomeLabel(dispute.outcome)}</p>
                <p className="text-sm text-slate-300">{dispute.resolution.summary}</p>
                
                <div className="mt-3 pt-3 border-t border-slate-700/50 grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-slate-400">To Claimant</p>
                    <p className="text-white font-medium">{dispute.resolution.claimantAmount} {dispute.escrowToken}</p>
                  </div>
                  <div>
                    <p className="text-slate-400">To Respondent</p>
                    <p className="text-white font-medium">{dispute.resolution.respondentAmount} {dispute.escrowToken}</p>
                  </div>
                </div>
              </div>
            )}
            
            {/* Arbitration Info */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
              <h4 className="text-sm font-medium text-slate-400 mb-3">Arbitration</h4>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-slate-500">Provider</p>
                  <p className="text-white capitalize">{dispute.arbitrationProvider}</p>
                </div>
                <div>
                  <p className="text-slate-500">Fee</p>
                  <p className="text-white">{dispute.arbitrationFee} {dispute.arbitrationFeeToken}</p>
                </div>
                {dispute.klerosDisputeId && (
                  <>
                    <div>
                      <p className="text-slate-500">Kleros ID</p>
                      <p className="text-cyan-400">#{dispute.klerosDisputeId}</p>
                    </div>
                    <div>
                      <p className="text-slate-500">Court</p>
                      <p className="text-white">General Court</p>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
        
        {activeTab === 'evidence' && (
          <div>
            {/* Evidence Deadline */}
            {dispute.status === DisputeStatus.EVIDENCE_PERIOD && (
              <div className="mb-4 bg-amber-900/20 border border-amber-600/30 rounded-lg p-3 flex items-center gap-2">
                <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-amber-200 text-sm">
                  Evidence deadline: {new Date(dispute.evidenceDeadline).toLocaleString()}
                </span>
              </div>
            )}
            
            <EvidenceList evidence={dispute.evidence} claimantAddress={dispute.claimant.address} />
          </div>
        )}
        
        {activeTab === 'timeline' && (
          <DisputeTimeline dispute={dispute} />
        )}
      </div>
      
      {/* Actions */}
      <div className="px-6 py-4 bg-slate-800/50 border-t border-slate-700">
        <div className="flex flex-wrap gap-3">
          {canUserSubmitEvidence && onSubmitEvidence && (
            <button
              onClick={onSubmitEvidence}
              className="flex-1 py-3 bg-gradient-to-r from-cyan-600 to-blue-600 
                       hover:from-cyan-500 hover:to-blue-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Submit Evidence
            </button>
          )}
          
          {canUserRespond && onRespond && (
            <button
              onClick={onRespond}
              className="flex-1 py-3 bg-gradient-to-r from-blue-600 to-purple-600 
                       hover:from-blue-500 hover:to-purple-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Submit Response
            </button>
          )}
          
          {canRequestArb && onRequestArbitration && (
            <button
              onClick={onRequestArbitration}
              className="flex-1 py-3 bg-gradient-to-r from-amber-600 to-orange-600 
                       hover:from-amber-500 hover:to-orange-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Request Arbitration
            </button>
          )}
          
          {canUserAppeal && onAppeal && (
            <button
              onClick={onAppeal}
              className="flex-1 py-3 bg-gradient-to-r from-orange-600 to-red-600 
                       hover:from-orange-500 hover:to-red-500 text-white font-medium 
                       rounded-lg transition-all"
            >
              Appeal Decision
            </button>
          )}
          
          {!canUserSubmitEvidence && !canUserRespond && !canRequestArb && !canUserAppeal && (
            <p className="text-sm text-slate-500 w-full text-center py-2">
              No actions available at this time
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
