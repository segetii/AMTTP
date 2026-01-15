/**
 * Simple Event Emitter for AMTTP SDK
 * Provides typed event handling
 */

import EventEmitter3 from 'eventemitter3';

export interface AMTTPEvents {
  // Connection events
  'connected': () => void;
  'disconnected': () => void;
  'reconnecting': (attempt: number) => void;

  // Transaction events
  'transaction:pending': (txHash: string) => void;
  'transaction:confirmed': (txHash: string, blockNumber: number) => void;
  'transaction:failed': (txHash: string, error: Error) => void;
  'transaction:escrowed': (txHash: string, escrowId: string) => void;
  'transaction:validated': (data: any) => void;
  'transaction:submitted': (data: any) => void;
  'transaction:cancelled': (data: any) => void;
  'transaction:retried': (data: any) => void;

  // Risk events
  'risk:scored': (address: string, score: number, level: string) => void;
  'risk:alert': (address: string, alertType: string, severity: string) => void;
  'risk:assessed': (data: any) => void;
  'risk:batchCompleted': (data: any) => void;
  'risk:cacheInvalidated': (data: any) => void;

  // KYC events
  'kyc:submitted': (data: any) => void;
  'kyc:documentUploaded': (data: any) => void;
  'kyc:upgradeRequested': (data: any) => void;
  'kyc:renewed': (data: any) => void;

  // Policy events
  'policy:evaluated': (data: any) => void;
  'policy:created': (data: any) => void;
  'policy:updated': (data: any) => void;
  'policy:deleted': (data: any) => void;

  // Compliance events
  'compliance:kyc_required': (address: string) => void;
  'compliance:edd_required': (address: string, caseId: string) => void;
  'compliance:blocked': (address: string, reason: string) => void;

  // Dispute events
  'dispute:created': (data: any) => void;
  'dispute:evidence_submitted': (disputeId: string, evidenceId: string) => void;
  'dispute:resolved': (disputeId: string, ruling: string) => void;
  'dispute:evidenceSubmitted': (data: any) => void;
  'dispute:escalated': (data: any) => void;
  'dispute:resolutionAccepted': (data: any) => void;
  'dispute:appealed': (data: any) => void;
  'dispute:withdrawn': (data: any) => void;

  // Reputation events
  'reputation:impactCalculated': (data: any) => void;

  // Monitoring events
  'monitoring:alert': (alertId: string, address: string, type: string) => void;
  'monitoring:re-screened': (address: string, newScore: number) => void;

  // Webhook events
  'webhook:received': (eventType: string, payload: unknown) => void;

  // General events
  'error': (error: Error) => void;
}

export class EventEmitter extends EventEmitter3<AMTTPEvents> {
  /**
   * Wait for a specific event with timeout
   */
  waitFor(
    event: keyof AMTTPEvents,
    timeout: number = 30000
  ): Promise<unknown[]> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Timeout waiting for event: ${String(event)}`));
      }, timeout);

      this.once(event, ((...args: unknown[]) => {
        clearTimeout(timer);
        resolve(args);
      }) as any);
    });
  }

  /**
   * Emit with logging
   */
  emitWithLog(event: keyof AMTTPEvents, ...args: unknown[]): boolean {
    if (process.env.AMTTP_DEBUG) {
      console.log(`[AMTTP Event] ${String(event)}:`, ...args);
    }
    return (this.emit as any)(event, ...args);
  }
}
