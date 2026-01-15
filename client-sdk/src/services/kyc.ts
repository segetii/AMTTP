/**
 * KYC Service
 * Wraps /kyc endpoints for Know Your Customer verification
 */

import { AxiosInstance } from 'axios';
import { EventEmitter } from '../events';
import { BaseService } from './base';

// Local type definitions
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

export class KYCService extends BaseService {
  constructor(http: AxiosInstance, events: EventEmitter) {
    super(http, events);
  }

  /**
   * Submit KYC documents for verification
   */
  async submit(submission: KYCSubmission): Promise<KYCVerificationResult> {
    const response = await this.http.post<KYCVerificationResult>('/kyc/submit', submission);
    
    this.events.emit('kyc:submitted', {
      address: submission.address,
      documentType: submission.documentType
    });

    return response.data;
  }

  /**
   * Get KYC status for an address
   */
  async getStatus(address: string): Promise<KYCVerificationResult> {
    const response = await this.http.get<KYCVerificationResult>(`/kyc/status/${address}`);
    return response.data;
  }

  /**
   * Check if address is KYC verified
   */
  async isVerified(address: string): Promise<boolean> {
    const status = await this.getStatus(address);
    return status.status === 'verified';
  }

  /**
   * Get KYC level for an address
   */
  async getLevel(address: string): Promise<KYCLevel> {
    const status = await this.getStatus(address);
    return status.level;
  }

  /**
   * Upload document for KYC verification
   */
  async uploadDocument(address: string, document: {
    type: 'document_front' | 'document_back' | 'selfie' | 'proof_of_address';
    contentHash: string;
    mimeType: string;
    encryptedContent?: string;
  }): Promise<{ documentId: string; status: string }> {
    const response = await this.http.post<{ documentId: string; status: string }>(
      `/kyc/documents/${address}`,
      document
    );
    
    this.events.emit('kyc:documentUploaded', {
      address,
      documentType: document.type,
      documentId: response.data.documentId
    });

    return response.data;
  }

  /**
   * Get uploaded documents for an address
   */
  async getDocuments(address: string): Promise<KYCDocument[]> {
    const response = await this.http.get<{ documents: KYCDocument[] }>(`/kyc/documents/${address}`);
    return response.data.documents;
  }

  /**
   * Get KYC requirements for a specific level
   */
  async getRequirements(level?: KYCLevel): Promise<KYCRequirements[]> {
    const url = level ? `/kyc/requirements?level=${level}` : '/kyc/requirements';
    const response = await this.http.get<{ requirements: KYCRequirements[] }>(url);
    return response.data.requirements;
  }

  /**
   * Request KYC level upgrade
   */
  async requestUpgrade(address: string, targetLevel: KYCLevel): Promise<{
    requestId: string;
    requiredDocuments: string[];
    status: string;
  }> {
    const response = await this.http.post<{
      requestId: string;
      requiredDocuments: string[];
      status: string;
    }>('/kyc/upgrade', { address, targetLevel });
    
    this.events.emit('kyc:upgradeRequested', {
      address,
      targetLevel,
      requestId: response.data.requestId
    });

    return response.data;
  }

  /**
   * Verify KYC attestation on-chain
   */
  async verifyOnChain(address: string, chainId: number): Promise<{
    verified: boolean;
    attestationHash?: string;
    verifiedAt?: string;
    level?: KYCLevel;
  }> {
    const response = await this.http.get<{
      verified: boolean;
      attestationHash?: string;
      verifiedAt?: string;
      level?: KYCLevel;
    }>(`/kyc/verify-onchain/${address}?chainId=${chainId}`);
    
    return response.data;
  }

  /**
   * Renew expiring KYC
   */
  async renew(address: string): Promise<KYCVerificationResult> {
    const response = await this.http.post<KYCVerificationResult>(`/kyc/renew/${address}`);
    
    this.events.emit('kyc:renewed', { address });
    
    return response.data;
  }

  /**
   * Check if KYC is expiring soon
   */
  async checkExpiry(address: string): Promise<{
    isExpiring: boolean;
    expiresAt?: string;
    daysRemaining?: number;
  }> {
    const response = await this.http.get<{
      isExpiring: boolean;
      expiresAt?: string;
      daysRemaining?: number;
    }>(`/kyc/expiry/${address}`);
    
    return response.data;
  }
}
