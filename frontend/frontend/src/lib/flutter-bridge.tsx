/**
 * Flutter Bridge - Next.js Side
 * 
 * Handles bidirectional communication between Next.js and Flutter app.
 * 
 * When embedded in Flutter WebView:
 * - Receives user context (session, role, wallet)
 * - Sends risk updates back to Flutter
 * - Handles navigation requests
 * - Supports "Open Full Screen" mode
 * 
 * Usage:
 * ```tsx
 * import { useFlutterBridge } from '@/lib/flutter-bridge';
 * 
 * function MyComponent() {
 *   const { isEmbedded, userContext, sendToFlutter } = useFlutterBridge();
 *   
 *   // Send risk score update to Flutter
 *   sendToFlutter('RISK_SCORE_UPDATE', { score: 0.85, address: '0x...' });
 * }
 * ```
 */

'use client';

import { useEffect, useState, useCallback, createContext, useContext, ReactNode } from 'react';
import { useSearchParams } from 'next/navigation';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface FlutterUserContext {
  sessionToken: string | null;
  userId: string | null;
  userRole: string | null;
  walletAddress: string | null;
  timestamp: string | null;
}

export interface FlutterBridgeMessage {
  type: string;
  payload: Record<string, unknown>;
  source?: string;
}

export interface FlutterBridgeState {
  isEmbedded: boolean;
  isReady: boolean;
  userContext: FlutterUserContext;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONTEXT
// ═══════════════════════════════════════════════════════════════════════════════

const FlutterBridgeContext = createContext<{
  state: FlutterBridgeState;
  sendToFlutter: (type: string, payload: Record<string, unknown>) => void;
  requestFullScreen: (route?: string) => void;
} | null>(null);

// ═══════════════════════════════════════════════════════════════════════════════
// PROVIDER
// ═══════════════════════════════════════════════════════════════════════════════

export function FlutterBridgeProvider({ children }: { children: ReactNode }) {
  const searchParams = useSearchParams();
  
  const [state, setState] = useState<FlutterBridgeState>({
    isEmbedded: false,
    isReady: false,
    userContext: {
      sessionToken: null,
      userId: null,
      userRole: null,
      walletAddress: null,
      timestamp: null,
    },
  });

  // Check if running in embedded mode
  useEffect(() => {
    const embedded = searchParams.get('embedded') === 'true';
    const source = searchParams.get('source');
    const token = searchParams.get('token');
    
    setState(prev => ({
      ...prev,
      isEmbedded: embedded || source === 'flutter',
      userContext: {
        ...prev.userContext,
        sessionToken: token || prev.userContext.sessionToken,
      },
    }));

    if (embedded || source === 'flutter') {
      console.log('🌉 Running in Flutter embedded mode');
    }
  }, [searchParams]);

  // Setup message listener
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data as FlutterBridgeMessage;
      
      if (!data || !data.type) return;
      if (data.source !== 'flutter') return;

      console.log('📩 Received from Flutter:', data.type);

      switch (data.type) {
        case 'FLUTTER_USER_CONTEXT':
          setState(prev => ({
            ...prev,
            isReady: true,
            userContext: {
              sessionToken: data.payload.sessionToken as string || null,
              userId: data.payload.userId as string || null,
              userRole: data.payload.userRole as string || null,
              walletAddress: data.payload.walletAddress as string || null,
              timestamp: data.payload.timestamp as string || null,
            },
          }));
          break;

        case 'SESSION_CLEARED':
          setState(prev => ({
            ...prev,
            userContext: {
              sessionToken: null,
              userId: null,
              userRole: null,
              walletAddress: null,
              timestamp: null,
            },
          }));
          break;

        case 'ANALYZE_TRANSACTION':
          // Navigate to transaction analysis
          const txHash = data.payload.txHash as string;
          if (txHash) {
            window.location.href = `/detection-studio?tx=${txHash}`;
          }
          break;

        case 'SHOW_WALLET_GRAPH':
          // Navigate to wallet graph
          const walletAddress = data.payload.walletAddress as string;
          if (walletAddress) {
            window.location.href = `/war-room/graphs?address=${walletAddress}`;
          }
          break;

        case 'NAVIGATE_TO':
          const route = data.payload.route as string;
          if (route) {
            window.location.href = route;
          }
          break;

        case 'REQUEST_RISK_CHECK':
          // Handle risk check request
          handleRiskCheckRequest(data.payload);
          break;

        default:
          console.log('⚠️ Unknown message type from Flutter:', data.type);
      }
    };

    window.addEventListener('message', handleMessage);
    
    // Expose global handler for bridge script injection
    (window as any).handleFlutterMessage = (data: FlutterBridgeMessage) => {
      handleMessage({ data } as MessageEvent);
    };

    return () => {
      window.removeEventListener('message', handleMessage);
      delete (window as any).handleFlutterMessage;
    };
  }, []);

  // Send message to Flutter
  const sendToFlutter = useCallback((type: string, payload: Record<string, unknown>) => {
    if (typeof window === 'undefined') return;
    
    // Check if FlutterBridge channel exists (injected by Flutter WebView)
    const flutterBridge = (window as any).FlutterBridge;
    
    if (flutterBridge && typeof flutterBridge.postMessage === 'function') {
      flutterBridge.postMessage(JSON.stringify({ type, payload }));
      console.log('📤 Sent to Flutter:', type);
    } else {
      console.log('⚠️ FlutterBridge not available (not in WebView?)');
    }
  }, []);

  // Request Flutter to open full screen
  const requestFullScreen = useCallback((route: string = '/war-room') => {
    sendToFlutter('OPEN_FULL_SCREEN', { route });
  }, [sendToFlutter]);

  // Handle risk check request (stub - would call actual API)
  const handleRiskCheckRequest = async (payload: Record<string, unknown>) => {
    const { counterpartyAddress, amount } = payload;
    
    try {
      // Call risk API
      const response = await fetch('/api/risk/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ address: counterpartyAddress, amount }),
      });
      
      if (response.ok) {
        const result = await response.json();
        sendToFlutter('RISK_SCORE_UPDATE', {
          address: counterpartyAddress,
          score: result.riskScore,
          factors: result.factors,
        });
      }
    } catch (error) {
      console.error('Risk check failed:', error);
    }
  };

  return (
    <FlutterBridgeContext.Provider value={{ state, sendToFlutter, requestFullScreen }}>
      {children}
    </FlutterBridgeContext.Provider>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HOOK
// ═══════════════════════════════════════════════════════════════════════════════

export function useFlutterBridge() {
  const context = useContext(FlutterBridgeContext);
  
  if (!context) {
    // Return a default state if not in provider (standalone mode)
    return {
      isEmbedded: false,
      isReady: true,
      userContext: {
        sessionToken: null,
        userId: null,
        userRole: null,
        walletAddress: null,
        timestamp: null,
      },
      sendToFlutter: () => console.log('FlutterBridge not available'),
      requestFullScreen: () => console.log('FlutterBridge not available'),
    };
  }

  return {
    ...context.state,
    sendToFlutter: context.sendToFlutter,
    requestFullScreen: context.requestFullScreen,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Send a risk score update to Flutter
 */
export function notifyRiskScore(address: string, score: number, factors?: string[]) {
  const flutterBridge = (window as any).FlutterBridge;
  if (flutterBridge) {
    flutterBridge.postMessage(JSON.stringify({
      type: 'RISK_SCORE_UPDATE',
      payload: { address, score, factors },
    }));
  }
}

/**
 * Send an alert to Flutter
 */
export function notifyAlert(title: string, message: string, severity: 'low' | 'medium' | 'high' | 'critical') {
  const flutterBridge = (window as any).FlutterBridge;
  if (flutterBridge) {
    flutterBridge.postMessage(JSON.stringify({
      type: 'ALERT_RECEIVED',
      payload: { title, message, severity, timestamp: new Date().toISOString() },
    }));
  }
}

/**
 * Request Flutter to navigate to a screen
 */
export function requestFlutterNavigation(route: string) {
  const flutterBridge = (window as any).FlutterBridge;
  if (flutterBridge) {
    flutterBridge.postMessage(JSON.stringify({
      type: 'NAVIGATION_REQUEST',
      payload: { route },
    }));
  }
}
