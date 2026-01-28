/**
 * Secure Bridge - Web ↔ Flutter Communication
 * 
 * CRITICAL COMPLIANCE COMPONENT
 * 
 * Purpose: Ensure regulators can verify that what the user saw = what they signed
 * 
 * Architecture:
 * 1. postMessage transport (browser ↔ Flutter WebView)
 * 2. EIP-712 structured data signing
 * 3. UI snapshot hashing for integrity
 * 
 * Flow:
 * 1. Web builds TransferIntent with UI state hash
 * 2. Bridge sends to Flutter via postMessage
 * 3. Flutter signs EIP-712 typed data (includes UI hash)
 * 4. Signature returned to web for submission
 * 5. Transaction includes hash → regulators can verify
 */

import { sha256 } from './ui-snapshot-chain';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Transfer Intent - What the user saw and intends to do
 * This is the payload that gets signed
 */
export interface TransferIntent {
  // Transaction details
  recipient: string;
  amount: string;
  token: string;
  chainId: number;
  
  // UI State Integrity
  uiSnapshotHash: string;
  trustPillarsShown: string[];
  riskScoreDisplayed: number;
  warningsAcknowledged: string[];
  
  // Metadata
  timestamp: number;
  nonce: string;
  sessionId: string;
}

/**
 * EIP-712 TypedData structure
 */
export interface EIP712TypedData {
  types: {
    EIP712Domain: Array<{ name: string; type: string }>;
    TransferIntent: Array<{ name: string; type: string }>;
  };
  primaryType: string;
  domain: {
    name: string;
    version: string;
    chainId: number;
    verifyingContract: string;
  };
  message: TransferIntent;
}

/**
 * Bridge Message Types
 */
export type BridgeMessageType = 
  | 'SIGN_INTENT'
  | 'SIGNATURE_RESULT'
  | 'CONNECT_WALLET'
  | 'WALLET_CONNECTED'
  | 'DISCONNECT_WALLET'
  | 'ERROR'
  | 'READY'
  | 'PING'
  | 'PONG';

export interface BridgeMessage {
  type: BridgeMessageType;
  id: string;
  payload: any;
  timestamp: number;
}

export interface SignatureResult {
  signature: string;
  signedHash: string;
  signerAddress: string;
  timestamp: number;
}

export interface BridgeError {
  code: string;
  message: string;
  details?: any;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const BRIDGE_ORIGIN = typeof window !== 'undefined' ? window.location.origin : '';
const MESSAGE_TIMEOUT = 30000; // 30 seconds
const FLUTTER_FRAME_ID = 'flutter-wallet-frame';

const EIP712_DOMAIN = {
  name: 'AMTTP Transfer Intent',
  version: '1',
  verifyingContract: '0x0000000000000000000000000000000000000000', // Set on deployment
};

const TRANSFER_INTENT_TYPES = {
  EIP712Domain: [
    { name: 'name', type: 'string' },
    { name: 'version', type: 'string' },
    { name: 'chainId', type: 'uint256' },
    { name: 'verifyingContract', type: 'address' },
  ],
  TransferIntent: [
    { name: 'recipient', type: 'address' },
    { name: 'amount', type: 'uint256' },
    { name: 'token', type: 'address' },
    { name: 'chainId', type: 'uint256' },
    { name: 'uiSnapshotHash', type: 'bytes32' },
    { name: 'trustPillarsShown', type: 'string' },
    { name: 'riskScoreDisplayed', type: 'uint8' },
    { name: 'warningsAcknowledged', type: 'string' },
    { name: 'timestamp', type: 'uint256' },
    { name: 'nonce', type: 'bytes32' },
    { name: 'sessionId', type: 'bytes32' },
  ],
};

// ═══════════════════════════════════════════════════════════════════════════════
// SECURE BRIDGE CLASS
// ═══════════════════════════════════════════════════════════════════════════════

export class SecureBridge {
  private pendingRequests: Map<string, { resolve: (value: any) => void; reject: (error: any) => void; timeout: NodeJS.Timeout }>;
  private messageHandler: ((event: MessageEvent) => void) | null = null;
  private isConnected: boolean = false;
  private flutterFrame: HTMLIFrameElement | null = null;
  
  constructor() {
    this.pendingRequests = new Map();
  }
  
  /**
   * Initialize the bridge and set up message listener
   */
  public init(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (typeof window === 'undefined') {
        reject(new Error('Bridge can only be initialized in browser'));
        return;
      }
      
      // Remove existing handler if any
      if (this.messageHandler) {
        window.removeEventListener('message', this.messageHandler);
      }
      
      // Set up message handler
      this.messageHandler = this.handleMessage.bind(this);
      window.addEventListener('message', this.messageHandler);
      
      // Find Flutter iframe
      this.flutterFrame = document.getElementById(FLUTTER_FRAME_ID) as HTMLIFrameElement;
      
      // Send ready ping
      this.sendMessage({ type: 'PING', id: this.generateId(), payload: null, timestamp: Date.now() });
      
      // Wait for PONG or timeout
      const timeout = setTimeout(() => {
        console.warn('Flutter bridge connection timeout - operating in standalone mode');
        this.isConnected = false;
        resolve(); // Don't reject, allow operation in standalone mode
      }, 5000);
      
      this.pendingRequests.set('INIT_PING', {
        resolve: () => {
          clearTimeout(timeout);
          this.isConnected = true;
          console.log('✅ Secure Bridge connected to Flutter');
          resolve();
        },
        reject,
        timeout,
      });
    });
  }
  
  /**
   * Clean up the bridge
   */
  public destroy(): void {
    if (this.messageHandler && typeof window !== 'undefined') {
      window.removeEventListener('message', this.messageHandler);
    }
    this.pendingRequests.forEach(({ timeout }) => clearTimeout(timeout));
    this.pendingRequests.clear();
    this.isConnected = false;
  }
  
  /**
   * Build a TransferIntent with UI state hash
   */
  public async buildTransferIntent(
    params: {
      recipient: string;
      amount: string;
      token: string;
      chainId: number;
      trustPillarsShown: string[];
      riskScoreDisplayed: number;
      warningsAcknowledged: string[];
    },
    uiState: any
  ): Promise<TransferIntent> {
    // Hash the UI state for integrity verification
    const uiSnapshotHash = await sha256(JSON.stringify(uiState));
    
    return {
      recipient: params.recipient,
      amount: params.amount,
      token: params.token,
      chainId: params.chainId,
      uiSnapshotHash,
      trustPillarsShown: params.trustPillarsShown,
      riskScoreDisplayed: params.riskScoreDisplayed,
      warningsAcknowledged: params.warningsAcknowledged,
      timestamp: Date.now(),
      nonce: this.generateId(),
      sessionId: this.getSessionId(),
    };
  }
  
  /**
   * Request signature from Flutter wallet
   */
  public async signIntent(intent: TransferIntent): Promise<SignatureResult> {
    const typedData = this.buildEIP712TypedData(intent);
    const messageId = this.generateId();
    
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingRequests.delete(messageId);
        reject(new Error('Signature request timed out'));
      }, MESSAGE_TIMEOUT);
      
      this.pendingRequests.set(messageId, { resolve, reject, timeout });
      
      this.sendMessage({
        type: 'SIGN_INTENT',
        id: messageId,
        payload: { intent, typedData },
        timestamp: Date.now(),
      });
    });
  }
  
  /**
   * Build EIP-712 typed data for signing
   */
  private buildEIP712TypedData(intent: TransferIntent): EIP712TypedData {
    return {
      types: TRANSFER_INTENT_TYPES,
      primaryType: 'TransferIntent',
      domain: {
        ...EIP712_DOMAIN,
        chainId: intent.chainId,
      },
      message: intent,
    };
  }
  
  /**
   * Handle incoming messages from Flutter
   */
  private handleMessage(event: MessageEvent): void {
    // Validate origin
    if (event.origin !== BRIDGE_ORIGIN && event.origin !== window.location.origin) {
      console.warn('Rejected message from unknown origin:', event.origin);
      return;
    }
    
    const message = event.data as BridgeMessage;
    
    if (!message || !message.type) return;
    
    console.log('📨 Bridge received:', message.type, message.id);
    
    switch (message.type) {
      case 'PONG':
        const initPending = this.pendingRequests.get('INIT_PING');
        if (initPending) {
          clearTimeout(initPending.timeout);
          initPending.resolve(null);
          this.pendingRequests.delete('INIT_PING');
        }
        break;
        
      case 'SIGNATURE_RESULT':
        const signPending = this.pendingRequests.get(message.id);
        if (signPending) {
          clearTimeout(signPending.timeout);
          signPending.resolve(message.payload as SignatureResult);
          this.pendingRequests.delete(message.id);
        }
        break;
        
      case 'WALLET_CONNECTED':
        console.log('Wallet connected:', message.payload);
        break;
        
      case 'ERROR':
        const errorPending = this.pendingRequests.get(message.id);
        if (errorPending) {
          clearTimeout(errorPending.timeout);
          errorPending.reject(message.payload as BridgeError);
          this.pendingRequests.delete(message.id);
        }
        break;
        
      default:
        console.log('Unknown message type:', message.type);
    }
  }
  
  /**
   * Send message to Flutter
   */
  private sendMessage(message: BridgeMessage): void {
    console.log('📤 Bridge sending:', message.type, message.id);
    
    // Try iframe first
    if (this.flutterFrame?.contentWindow) {
      this.flutterFrame.contentWindow.postMessage(message, '*');
      return;
    }
    
    // Fallback to parent window (if embedded)
    if (window.parent !== window) {
      window.parent.postMessage(message, '*');
      return;
    }
    
    // Last resort: broadcast
    window.postMessage(message, '*');
  }
  
  /**
   * Generate unique ID
   */
  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
  
  /**
   * Get or create session ID
   */
  private getSessionId(): string {
    if (typeof window === 'undefined') return 'server';
    
    let sessionId = sessionStorage.getItem('amttp_session_id');
    if (!sessionId) {
      sessionId = this.generateId();
      sessionStorage.setItem('amttp_session_id', sessionId);
    }
    return sessionId;
  }
  
  /**
   * Check if bridge is connected
   */
  public get connected(): boolean {
    return this.isConnected;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SINGLETON INSTANCE
// ═══════════════════════════════════════════════════════════════════════════════

let bridgeInstance: SecureBridge | null = null;

export function getSecureBridge(): SecureBridge {
  if (!bridgeInstance) {
    bridgeInstance = new SecureBridge();
  }
  return bridgeInstance;
}

// ═══════════════════════════════════════════════════════════════════════════════
// REACT HOOK
// ═══════════════════════════════════════════════════════════════════════════════

import { useEffect, useState, useCallback } from 'react';

export function useSecureBridge() {
  const [bridge, setBridge] = useState<SecureBridge | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  
  useEffect(() => {
    const b = getSecureBridge();
    setBridge(b);
    
    b.init()
      .then(() => {
        setIsReady(true);
        setIsConnected(b.connected);
      })
      .catch((err) => {
        setError(err);
        setIsReady(true); // Ready but with error
      });
    
    return () => {
      // Don't destroy singleton on unmount
    };
  }, []);
  
  const signIntent = useCallback(async (intent: TransferIntent) => {
    if (!bridge) throw new Error('Bridge not initialized');
    return bridge.signIntent(intent);
  }, [bridge]);
  
  const buildIntent = useCallback(async (
    params: {
      recipient: string;
      amount: string;
      token: string;
      chainId: number;
      trustPillarsShown: string[];
      riskScoreDisplayed: number;
      warningsAcknowledged: string[];
    },
    uiState: any
  ) => {
    if (!bridge) throw new Error('Bridge not initialized');
    return bridge.buildTransferIntent(params, uiState);
  }, [bridge]);
  
  return {
    bridge,
    isReady,
    isConnected,
    error,
    signIntent,
    buildIntent,
  };
}
