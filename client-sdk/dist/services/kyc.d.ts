/**
 * KYC Service
 * Wraps /kyc endpoints for Know Your Customer verification
 */
import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';
export type KYCStatus = 'none' | 'pending' | 'verified' | 'rejected' | 'expired';
export type KYCLevel = 'none' | 'basic' | 'standard' | 'enhanced';
export interface KYCSubmission {
    address: string;
    documentType: 'passport' | 'driving_license' | 'national_id';
    documentNumber: string;
    firstName: string;
    lastName: string;
    dateOfBirth: string;
    nationality: string;
    documentFrontHash?: string;
    documentBackHash?: string;
    selfieHash?: string;
    metadata?: Record<string, any>;
}
export interface KYCVerificationResult {
    address: string;
    status: KYCStatus;
    level: KYCLevel;
    verifiedAt?: string;
    expiresAt?: string;
    rejectionReason?: string;
    requiredDocuments?: string[];
    provider?: string;
}
export interface KYCDocument {
    id: string;
    type: string;
    status: 'pending' | 'verified' | 'rejected';
    uploadedAt: string;
    verifiedAt?: string;
    expiresAt?: string;
}
export interface KYCRequirements {
    level: KYCLevel;
    requiredDocuments: string[];
    maxTransactionLimit: string;
    features: string[];
}
export declare class KYCService extends BaseService {
    constructor(http: AxiosInstance, events: EventEmitter);
    /**
     * Submit KYC documents for verification
     */
    submit(submission: KYCSubmission): Promise<KYCVerificationResult>;
    /**
     * Get KYC status for an address
     */
    getStatus(address: string): Promise<KYCVerificationResult>;
    /**
     * Check if address is KYC verified
     */
    isVerified(address: string): Promise<boolean>;
    /**
     * Get KYC level for an address
     */
    getLevel(address: string): Promise<KYCLevel>;
    /**
     * Upload document for KYC verification
     */
    uploadDocument(address: string, document: {
        type: 'document_front' | 'document_back' | 'selfie' | 'proof_of_address';
        contentHash: string;
        mimeType: string;
        encryptedContent?: string;
    }): Promise<{
        documentId: string;
        status: string;
    }>;
    /**
     * Get uploaded documents for an address
     */
    getDocuments(address: string): Promise<KYCDocument[]>;
    /**
     * Get KYC requirements for a specific level
     */
    getRequirements(level?: KYCLevel): Promise<KYCRequirements[]>;
    /**
     * Request KYC level upgrade
     */
    requestUpgrade(address: string, targetLevel: KYCLevel): Promise<{
        requestId: string;
        requiredDocuments: string[];
        status: string;
    }>;
    /**
     * Verify KYC attestation on-chain
     */
    verifyOnChain(address: string, chainId: number): Promise<{
        verified: boolean;
        attestationHash?: string;
        verifiedAt?: string;
        level?: KYCLevel;
    }>;
    /**
     * Renew expiring KYC
     */
    renew(address: string): Promise<KYCVerificationResult>;
    /**
     * Check if KYC is expiring soon
     */
    checkExpiry(address: string): Promise<{
        isExpiring: boolean;
        expiresAt?: string;
        daysRemaining?: number;
    }>;
}
//# sourceMappingURL=kyc.d.ts.map