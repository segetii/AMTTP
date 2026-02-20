/**
 * Simple Event Emitter for AMTTP SDK
 * Provides typed event handling
 */
import EventEmitter3 from 'eventemitter3';
export interface AMTTPEvents {
    'connected': () => void;
    'disconnected': () => void;
    'reconnecting': (attempt: number) => void;
    'transaction:pending': (txHash: string) => void;
    'transaction:confirmed': (txHash: string, blockNumber: number) => void;
    'transaction:failed': (txHash: string, error: Error) => void;
    'transaction:escrowed': (txHash: string, escrowId: string) => void;
    'transaction:validated': (data: any) => void;
    'transaction:submitted': (data: any) => void;
    'transaction:cancelled': (data: any) => void;
    'transaction:retried': (data: any) => void;
    'risk:scored': (address: string, score: number, level: string) => void;
    'risk:alert': (address: string, alertType: string, severity: string) => void;
    'risk:assessed': (data: any) => void;
    'risk:batchCompleted': (data: any) => void;
    'risk:cacheInvalidated': (data: any) => void;
    'kyc:submitted': (data: any) => void;
    'kyc:documentUploaded': (data: any) => void;
    'kyc:upgradeRequested': (data: any) => void;
    'kyc:renewed': (data: any) => void;
    'policy:evaluated': (data: any) => void;
    'policy:created': (data: any) => void;
    'policy:updated': (data: any) => void;
    'policy:deleted': (data: any) => void;
    'compliance:kyc_required': (address: string) => void;
    'compliance:edd_required': (address: string, caseId: string) => void;
    'compliance:blocked': (address: string, reason: string) => void;
    'dispute:created': (data: any) => void;
    'dispute:evidence_submitted': (disputeId: string, evidenceId: string) => void;
    'dispute:resolved': (disputeId: string, ruling: string) => void;
    'dispute:evidenceSubmitted': (data: any) => void;
    'dispute:escalated': (data: any) => void;
    'dispute:resolutionAccepted': (data: any) => void;
    'dispute:appealed': (data: any) => void;
    'dispute:withdrawn': (data: any) => void;
    'reputation:impactCalculated': (data: any) => void;
    'monitoring:alert': (alertId: string, address: string, type: string) => void;
    'monitoring:re-screened': (address: string, newScore: number) => void;
    'webhook:received': (eventType: string, payload: unknown) => void;
    'error': (error: Error) => void;
}
export declare class EventEmitter extends EventEmitter3<AMTTPEvents> {
    /**
     * Wait for a specific event with timeout
     */
    waitFor(event: keyof AMTTPEvents, timeout?: number): Promise<unknown[]>;
    /**
     * Emit with logging
     */
    emitWithLog(event: keyof AMTTPEvents, ...args: unknown[]): boolean;
}
//# sourceMappingURL=events.d.ts.map