'use client';

/**
 * Chain Replay Tool Component
 * 
 * Sprint 11: Compliance Reporting & Export System
 * 
 * Ground Truth Reference:
 * - Replay UI states from snapshots
 * - Step-by-step audit reconstruction
 * - Visual diff between states
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  UISnapshot,
  ReplaySession,
  SnapshotDiff,
  formatSnapshotDate,
  truncateHash,
} from '@/types/compliance-report';
import { useChainReplay } from '@/lib/compliance-report-service';

// ═══════════════════════════════════════════════════════════════════════════════
// INTERFACES
// ═══════════════════════════════════════════════════════════════════════════════

interface ChainReplayToolProps {
  initialTransactionId?: string;
  onSnapshotSelect?: (snapshot: UISnapshot) => void;
  className?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CREATE SESSION PANEL
// ═══════════════════════════════════════════════════════════════════════════════

function CreateSessionPanel({
  onCreate,
  isLoading,
}: {
  onCreate: (name: string, start: string, end: string, options?: { transactionId?: string }) => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState('');
  const [startTime, setStartTime] = useState(
    new Date(Date.now() - 3600000).toISOString().slice(0, 16)
  );
  const [endTime, setEndTime] = useState(
    new Date().toISOString().slice(0, 16)
  );
  const [transactionId, setTransactionId] = useState('');
  
  const handleCreate = () => {
    if (!name) return;
    onCreate(
      name,
      new Date(startTime).toISOString(),
      new Date(endTime).toISOString(),
      transactionId ? { transactionId } : undefined
    );
  };
  
  return (
    <div className="p-6 bg-slate-800 border border-slate-700 rounded-xl">
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <span className="text-xl">🎬</span>
        Create Replay Session
      </h3>
      
      <div className="space-y-4">
        {/* Session Name */}
        <div>
          <label className="block text-sm text-slate-400 mb-1">Session Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., Transaction Investigation #123"
            className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500"
          />
        </div>
        
        {/* Time Range */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-slate-400 mb-1">Start Time</label>
            <input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-slate-400 mb-1">End Time</label>
            <input
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white"
            />
          </div>
        </div>
        
        {/* Transaction ID Filter */}
        <div>
          <label className="block text-sm text-slate-400 mb-1">Transaction ID (optional)</label>
          <input
            type="text"
            value={transactionId}
            onChange={(e) => setTransactionId(e.target.value)}
            placeholder="Filter by transaction ID"
            className="w-full px-4 py-2 bg-slate-900 border border-slate-600 rounded-lg text-white placeholder-slate-500"
          />
        </div>
        
        {/* Create Button */}
        <button
          onClick={handleCreate}
          disabled={!name || isLoading}
          className="w-full px-4 py-3 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors"
        >
          {isLoading ? (
            <>
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading Snapshots...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              Start Replay Session
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PLAYBACK CONTROLS
// ═══════════════════════════════════════════════════════════════════════════════

function PlaybackControls({
  session,
  onPlay,
  onPause,
  onGoToStep,
  onSetSpeed,
  onClose,
}: {
  session: ReplaySession;
  onPlay: () => void;
  onPause: () => void;
  onGoToStep: (index: number) => void;
  onSetSpeed: (speed: number) => void;
  onClose: () => void;
}) {
  return (
    <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg">
      {/* Session Info */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h4 className="font-medium text-white">{session.name}</h4>
          <p className="text-xs text-slate-400">
            {session.totalSnapshots} snapshot{session.totalSnapshots !== 1 ? 's' : ''} loaded
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      
      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
          <span>Step {session.currentSnapshotIndex + 1} of {session.totalSnapshots}</span>
          <span>{Math.round((session.currentSnapshotIndex / Math.max(session.totalSnapshots - 1, 1)) * 100)}%</span>
        </div>
        <div className="relative h-2 bg-slate-700 rounded overflow-hidden">
          <div 
            className="absolute left-0 top-0 h-full bg-cyan-500 transition-all duration-300"
            style={{ width: `${(session.currentSnapshotIndex / Math.max(session.totalSnapshots - 1, 1)) * 100}%` }}
          />
        </div>
        {/* Step markers */}
        <div className="relative h-2 mt-1">
          {session.snapshots.map((_, i) => (
            <button
              key={i}
              onClick={() => onGoToStep(i)}
              className={`absolute w-3 h-3 rounded-full border-2 transform -translate-x-1/2 transition-all ${
                i === session.currentSnapshotIndex
                  ? 'bg-cyan-400 border-cyan-300 scale-110'
                  : i < session.currentSnapshotIndex
                  ? 'bg-cyan-600 border-cyan-500'
                  : 'bg-slate-600 border-slate-500'
              }`}
              style={{ left: `${(i / Math.max(session.totalSnapshots - 1, 1)) * 100}%` }}
              title={`Step ${i + 1}`}
            />
          ))}
        </div>
      </div>
      
      {/* Controls */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Step Back */}
          <button
            onClick={() => onGoToStep(session.currentSnapshotIndex - 1)}
            disabled={session.currentSnapshotIndex === 0}
            className="p-2 text-slate-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0019 16V8a1 1 0 00-1.6-.8l-5.333 4zM4.066 11.2a1 1 0 000 1.6l5.334 4A1 1 0 0011 16V8a1 1 0 00-1.6-.8l-5.334 4z" />
            </svg>
          </button>
          
          {/* Play/Pause */}
          <button
            onClick={session.status === 'playing' ? onPause : onPlay}
            className="p-3 bg-cyan-600 text-white rounded-full hover:bg-cyan-500 transition-colors"
          >
            {session.status === 'playing' ? (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ) : (
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
          </button>
          
          {/* Step Forward */}
          <button
            onClick={() => onGoToStep(session.currentSnapshotIndex + 1)}
            disabled={session.currentSnapshotIndex === session.totalSnapshots - 1}
            className="p-2 text-slate-400 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11.933 12.8a1 1 0 000-1.6L6.6 7.2A1 1 0 005 8v8a1 1 0 001.6.8l5.333-4zM19.933 12.8a1 1 0 000-1.6l-5.333-4A1 1 0 0013 8v8a1 1 0 001.6.8l5.333-4z" />
            </svg>
          </button>
        </div>
        
        {/* Speed Control */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Speed:</span>
          <div className="flex bg-slate-700 rounded overflow-hidden">
            {[0.5, 1, 2].map(speed => (
              <button
                key={speed}
                onClick={() => onSetSpeed(speed)}
                className={`px-2 py-1 text-xs transition-colors ${
                  session.playbackSpeed === speed
                    ? 'bg-cyan-600 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// SNAPSHOT VIEWER
// ═══════════════════════════════════════════════════════════════════════════════

function SnapshotViewer({
  snapshot,
  previousSnapshot,
  diffs,
}: {
  snapshot: UISnapshot;
  previousSnapshot?: UISnapshot;
  diffs: SnapshotDiff[];
}) {
  const [showDiffs, setShowDiffs] = useState(true);
  
  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-white">{snapshot.screenName}</h3>
            <p className="text-xs text-slate-400">{formatSnapshotDate(snapshot.timestamp)}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-1 rounded text-xs ${
              snapshot.integrityProof.verified
                ? 'bg-green-900/50 text-green-400'
                : 'bg-yellow-900/50 text-yellow-400'
            }`}>
              {snapshot.integrityProof.verified ? '✓ Verified' : '⏳ Pending'}
            </span>
            <button
              onClick={() => setShowDiffs(!showDiffs)}
              className={`px-2 py-1 rounded text-xs transition-colors ${
                showDiffs ? 'bg-cyan-600 text-white' : 'bg-slate-700 text-slate-400'
              }`}
            >
              Show Changes
            </button>
          </div>
        </div>
      </div>
      
      {/* Content */}
      <div className="p-4 space-y-4">
        {/* User Context */}
        <div className="p-4 bg-slate-900 rounded-lg border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">User Context</h4>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-slate-500">Role</p>
              <p className="text-sm text-white">{snapshot.userContext.role}</p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Mode</p>
              <p className="text-sm text-white capitalize">{snapshot.userContext.mode}</p>
            </div>
          </div>
        </div>
        
        {/* Transaction Context */}
        {snapshot.transactionContext && (
          <div className="p-4 bg-slate-900 rounded-lg border border-slate-700">
            <h4 className="text-sm font-medium text-white mb-3">Transaction</h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-slate-500">Action</p>
                <p className="text-sm text-white">{snapshot.transactionContext.action}</p>
              </div>
              {snapshot.transactionContext.amount && (
                <div>
                  <p className="text-xs text-slate-500">Amount</p>
                  <p className="text-sm text-green-400">{snapshot.transactionContext.amount}</p>
                </div>
              )}
            </div>
          </div>
        )}
        
        {/* Components */}
        <div className="p-4 bg-slate-900 rounded-lg border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">Components ({snapshot.components.length})</h4>
          <div className="space-y-3">
            {snapshot.components.map(comp => {
              const compDiffs = diffs.filter(d => d.componentId === comp.id);
              
              return (
                <div 
                  key={comp.id} 
                  className={`p-3 rounded border ${
                    compDiffs.length > 0 && showDiffs
                      ? 'bg-cyan-900/20 border-cyan-600/30'
                      : 'bg-slate-800 border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="text-sm font-medium text-white">{comp.name}</span>
                      <span className="text-xs text-slate-500 ml-2">{comp.type}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {comp.interacted && (
                        <span className="px-2 py-0.5 bg-cyan-900/50 text-cyan-400 rounded text-xs">Interacted</span>
                      )}
                      {compDiffs.length > 0 && showDiffs && (
                        <span className="px-2 py-0.5 bg-cyan-600 text-white rounded text-xs">
                          {compDiffs.length} change{compDiffs.length !== 1 ? 's' : ''}
                        </span>
                      )}
                    </div>
                  </div>
                  
                  {/* Component State */}
                  {Object.keys(comp.state).length > 0 && (
                    <div className="mt-2 p-2 bg-slate-900 rounded text-xs">
                      <pre className="text-slate-300 overflow-x-auto">
                        {JSON.stringify(comp.state, null, 2)}
                      </pre>
                    </div>
                  )}
                  
                  {/* Diffs */}
                  {compDiffs.length > 0 && showDiffs && (
                    <div className="mt-2 space-y-1">
                      {compDiffs.map((diff, i) => (
                        <div key={i} className="flex items-center gap-2 text-xs">
                          <span className={`px-1.5 py-0.5 rounded ${
                            diff.changeType === 'added' 
                              ? 'bg-green-900/50 text-green-400'
                              : diff.changeType === 'removed'
                              ? 'bg-red-900/50 text-red-400'
                              : 'bg-yellow-900/50 text-yellow-400'
                          }`}>
                            {diff.changeType}
                          </span>
                          <span className="text-slate-400">{diff.field}:</span>
                          {diff.previousValue !== null && (
                            <span className="text-red-400 line-through">
                              {JSON.stringify(diff.previousValue)}
                            </span>
                          )}
                          {diff.newValue !== null && (
                            <span className="text-green-400">
                              {JSON.stringify(diff.newValue)}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        
        {/* Hash Info */}
        <div className="p-4 bg-slate-900 rounded-lg border border-slate-700">
          <h4 className="text-sm font-medium text-white mb-3">Integrity Proof</h4>
          <div className="space-y-2">
            <div>
              <p className="text-xs text-slate-500">State Hash</p>
              <code className="text-xs text-cyan-400 font-mono">{truncateHash(snapshot.stateHash, 16)}</code>
            </div>
            {previousSnapshot && (
              <div>
                <p className="text-xs text-slate-500">Previous Hash</p>
                <code className="text-xs text-slate-400 font-mono">{truncateHash(snapshot.previousHash, 16)}</code>
              </div>
            )}
            {snapshot.integrityProof.onChainAnchor && (
              <div>
                <p className="text-xs text-slate-500">On-Chain Anchor</p>
                <code className="text-xs text-green-400 font-mono">{truncateHash(snapshot.integrityProof.onChainAnchor, 16)}</code>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ChainReplayTool({
  initialTransactionId,
  onSnapshotSelect,
  className = '',
}: ChainReplayToolProps) {
  const {
    session,
    isLoading,
    createReplaySession,
    play,
    pause,
    goToStep,
    setPlaybackSpeed,
    getStepDiff,
    closeSession,
  } = useChainReplay();
  
  const [diffs, setDiffs] = useState<SnapshotDiff[]>([]);
  
  // Calculate diffs when step changes
  useEffect(() => {
    if (session && session.currentSnapshotIndex > 0) {
      const stepDiffs = getStepDiff(session.currentSnapshotIndex - 1, session.currentSnapshotIndex);
      setDiffs(stepDiffs);
    } else {
      setDiffs([]);
    }
  }, [session?.currentSnapshotIndex, getStepDiff]);
  
  // Auto-play effect
  useEffect(() => {
    if (!session || session.status !== 'playing') return;
    
    const interval = setInterval(() => {
      if (session.currentSnapshotIndex < session.totalSnapshots - 1) {
        goToStep(session.currentSnapshotIndex + 1);
      } else {
        pause();
      }
    }, 2000 / session.playbackSpeed);
    
    return () => clearInterval(interval);
  }, [session?.status, session?.currentSnapshotIndex, session?.playbackSpeed, goToStep, pause]);
  
  const handleCreate = useCallback(async (
    name: string,
    start: string,
    end: string,
    options?: { transactionId?: string }
  ) => {
    await createReplaySession(name, start, end, options);
  }, [createReplaySession]);
  
  const currentSnapshot = session?.snapshots[session.currentSnapshotIndex];
  const previousSnapshot = session && session.currentSnapshotIndex > 0 
    ? session.snapshots[session.currentSnapshotIndex - 1] 
    : undefined;
  
  return (
    <div className={`flex flex-col h-full ${className}`}>
      {/* Header */}
      <div className="mb-4">
        <h2 className="text-xl font-bold text-white flex items-center gap-2 mb-1">
          <span className="text-2xl">🔄</span>
          Chain Replay Tool
        </h2>
        <p className="text-sm text-slate-400">
          Step through UI state snapshots for complete audit reconstruction
        </p>
      </div>
      
      {/* Content */}
      {!session ? (
        <CreateSessionPanel
          onCreate={handleCreate}
          isLoading={isLoading}
        />
      ) : (
        <div className="flex-1 flex flex-col min-h-0">
          {/* Playback Controls */}
          <PlaybackControls
            session={session}
            onPlay={play}
            onPause={pause}
            onGoToStep={goToStep}
            onSetSpeed={setPlaybackSpeed}
            onClose={closeSession}
          />
          
          {/* Snapshot Viewer */}
          {currentSnapshot && (
            <div className="flex-1 mt-4 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              <SnapshotViewer
                snapshot={currentSnapshot}
                previousSnapshot={previousSnapshot}
                diffs={diffs}
              />
            </div>
          )}
          
          {/* Timeline */}
          <div className="mt-4 p-4 bg-slate-800 border border-slate-700 rounded-lg">
            <h4 className="text-sm font-medium text-white mb-3">Timeline</h4>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {session.snapshots.map((snap, i) => (
                <button
                  key={snap.id}
                  onClick={() => goToStep(i)}
                  className={`flex-shrink-0 p-3 rounded-lg border transition-all ${
                    i === session.currentSnapshotIndex
                      ? 'bg-cyan-900/50 border-cyan-500'
                      : 'bg-slate-900 border-slate-700 hover:border-slate-600'
                  }`}
                >
                  <p className="text-xs font-medium text-white truncate max-w-[120px]">{snap.screenName}</p>
                  <p className="text-xs text-slate-500">{new Date(snap.timestamp).toLocaleTimeString()}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
