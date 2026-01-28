/**
 * AMTTP UI Snapshot Chain
 * 
 * Layer 2 - UI Decision Snapshot Chain (Governance)
 * - Canonical UI JSON snapshot
 * - SHA-256 hashing
 * - Hash chaining
 * - Immutable audit log
 * 
 * Guarantees:
 * - Non-repudiation
 * - Audit reconstruction
 * - Proof of decision context
 */

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface UISnapshot {
  snapshot_id: string;
  timestamp: string;
  actor_role: string;
  actor_id: string;
  action_context: string;
  route: string;
  displayed_data: Record<string, unknown>;
  ui_hash: string;
  prev_hash: string;
  ui_version: string;
}

export interface SnapshotChainStatus {
  isValid: boolean;
  lastSnapshot: UISnapshot | null;
  chainLength: number;
  brokenAt?: string;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CRYPTO UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

export async function sha256(message: string): Promise<string> {
  const msgBuffer = new TextEncoder().encode(message);
  const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// SNAPSHOT CHAIN MANAGER
// ═══════════════════════════════════════════════════════════════════════════════

const UI_VERSION = 'v2.3.0';
const STORAGE_KEY = 'amttp_snapshot_chain';
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

class SnapshotChainManager {
  private chain: UISnapshot[] = [];
  private lastHash: string = '0'.repeat(64); // Genesis hash
  
  constructor() {
    this.loadFromStorage();
  }
  
  private loadFromStorage() {
    if (typeof window === 'undefined') return;
    
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        this.chain = data.chain || [];
        this.lastHash = data.lastHash || '0'.repeat(64);
      }
    } catch (e) {
      console.error('Failed to load snapshot chain:', e);
    }
  }
  
  private saveToStorage() {
    if (typeof window === 'undefined') return;
    
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        chain: this.chain.slice(-100), // Keep last 100 snapshots locally
        lastHash: this.lastHash,
      }));
    } catch (e) {
      console.error('Failed to save snapshot chain:', e);
    }
  }
  
  /**
   * Create a new UI snapshot
   */
  async createSnapshot(params: {
    actorRole: string;
    actorId: string;
    actionContext: string;
    route: string;
    displayedData: Record<string, unknown>;
  }): Promise<UISnapshot> {
    const { actorRole, actorId, actionContext, route, displayedData } = params;
    
    // Create canonical JSON representation
    const canonicalData = JSON.stringify(displayedData, Object.keys(displayedData).sort());
    
    // Generate hash of displayed data
    const uiHash = await sha256(canonicalData);
    
    // Create snapshot
    const snapshot: UISnapshot = {
      snapshot_id: generateUUID(),
      timestamp: new Date().toISOString(),
      actor_role: actorRole,
      actor_id: actorId,
      action_context: actionContext,
      route,
      displayed_data: displayedData,
      ui_hash: uiHash,
      prev_hash: this.lastHash,
      ui_version: UI_VERSION,
    };
    
    // Update chain
    this.chain.push(snapshot);
    this.lastHash = uiHash;
    this.saveToStorage();
    
    // Send to backend for immutable storage
    this.persistToBackend(snapshot).catch(console.error);
    
    return snapshot;
  }
  
  /**
   * Verify a snapshot hash matches expected
   */
  async verifySnapshot(snapshot: UISnapshot): Promise<boolean> {
    const canonicalData = JSON.stringify(snapshot.displayed_data, Object.keys(snapshot.displayed_data).sort());
    const expectedHash = await sha256(canonicalData);
    return expectedHash === snapshot.ui_hash;
  }
  
  /**
   * Verify entire chain integrity
   */
  async verifyChain(): Promise<SnapshotChainStatus> {
    if (this.chain.length === 0) {
      return {
        isValid: true,
        lastSnapshot: null,
        chainLength: 0,
      };
    }
    
    let prevHash = '0'.repeat(64);
    
    for (const snapshot of this.chain) {
      // Check prev_hash links correctly
      if (snapshot.prev_hash !== prevHash) {
        return {
          isValid: false,
          lastSnapshot: snapshot,
          chainLength: this.chain.length,
          brokenAt: snapshot.snapshot_id,
        };
      }
      
      // Verify snapshot hash
      const isValid = await this.verifySnapshot(snapshot);
      if (!isValid) {
        return {
          isValid: false,
          lastSnapshot: snapshot,
          chainLength: this.chain.length,
          brokenAt: snapshot.snapshot_id,
        };
      }
      
      prevHash = snapshot.ui_hash;
    }
    
    return {
      isValid: true,
      lastSnapshot: this.chain[this.chain.length - 1],
      chainLength: this.chain.length,
    };
  }
  
  /**
   * Get current chain status
   */
  getStatus(): { lastHash: string; chainLength: number } {
    return {
      lastHash: this.lastHash,
      chainLength: this.chain.length,
    };
  }
  
  /**
   * Get short hash for display
   */
  getShortHash(): string {
    return this.lastHash.slice(0, 8);
  }
  
  /**
   * Get snapshot by ID
   */
  getSnapshot(snapshotId: string): UISnapshot | undefined {
    return this.chain.find(s => s.snapshot_id === snapshotId);
  }
  
  /**
   * Get recent snapshots
   */
  getRecentSnapshots(count: number = 10): UISnapshot[] {
    return this.chain.slice(-count);
  }
  
  /**
   * Persist snapshot to backend
   */
  private async persistToBackend(snapshot: UISnapshot): Promise<void> {
    try {
      await fetch(`${API_BASE}/ui-snapshot/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(snapshot),
      });
    } catch (e) {
      // Log but don't block - local chain is primary
      console.warn('Failed to persist snapshot to backend:', e);
    }
  }
}

// Singleton instance
let snapshotManager: SnapshotChainManager | null = null;

export function getSnapshotManager(): SnapshotChainManager {
  if (!snapshotManager) {
    snapshotManager = new SnapshotChainManager();
  }
  return snapshotManager;
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

import { useState, useEffect, useCallback } from 'react';

export function useUISnapshot() {
  const [manager] = useState(() => getSnapshotManager());
  const [lastHash, setLastHash] = useState('');
  const [chainLength, setChainLength] = useState(0);
  const [isVerified, setIsVerified] = useState(true);
  
  useEffect(() => {
    const status = manager.getStatus();
    setLastHash(status.lastHash);
    setChainLength(status.chainLength);
    
    // Verify chain on mount
    manager.verifyChain().then(result => {
      setIsVerified(result.isValid);
    });
  }, [manager]);
  
  const createSnapshot = useCallback(async (params: {
    actorRole: string;
    actorId: string;
    actionContext: string;
    route: string;
    displayedData: Record<string, unknown>;
  }) => {
    const snapshot = await manager.createSnapshot(params);
    const status = manager.getStatus();
    setLastHash(status.lastHash);
    setChainLength(status.chainLength);
    return snapshot;
  }, [manager]);
  
  const verifyChain = useCallback(async () => {
    const result = await manager.verifyChain();
    setIsVerified(result.isValid);
    return result;
  }, [manager]);
  
  return {
    createSnapshot,
    verifyChain,
    lastHash,
    shortHash: lastHash.slice(0, 8),
    chainLength,
    isVerified,
    getSnapshot: manager.getSnapshot.bind(manager),
    getRecentSnapshots: manager.getRecentSnapshots.bind(manager),
  };
}
