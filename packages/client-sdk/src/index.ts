// src/index.ts
export { AMTTPClient } from './client.js';
export { MLService, createMLService } from './ml.js';
export { CrossChainService, createCrossChainService, LZ_CHAIN_IDS } from './crosschain.js';
export type { ChainName, CrossChainRiskScore, CrossChainMessageResult, CrossChainConfig } from './crosschain.js';
// zkNAF Zero-Knowledge Privacy Layer
export { ZkNAFService, ProofType } from './zknaf.js';
export type { ZkNAFConfig, Groth16Proof, ProofResult, SanctionsProofInput, RiskRangeProofInput, KYCProofInput } from './zknaf.js';
// L2 Risk Router (Polygon/Arbitrum)
export { RiskRouterClient, createRiskRouterClient, RiskAction, L2_ROUTER_ADDRESSES, CHAIN_NAMES, getActionColor, getActionIcon, predictAction, formatStatistics } from './risk-router.js';
export type { RiskRouterConfig, RiskResult, BatchRequest, RouterStatistics, RiskThresholds } from './risk-router.js';
// Explainability - Human-readable risk explanations
export { 
  ExplainabilityService, 
  createExplainabilityService, 
  formatExplanationForDisplay,
  TYPOLOGIES 
} from './explainability.js';
export type { 
  ImpactLevel, 
  TypologyType, 
  ExplanationFactor, 
  TypologyMatch, 
  GraphExplanation,
  RiskExplanation, 
  ExplainRequest, 
  TransactionExplainRequest,
  TypologyInfo 
} from './explainability.js';
export {
  PolicyAction,
  RiskLevel
} from './types.js';
export type {
  AMTTPConfig,
  TransactionRequest,
  TransactionMetadata,
  RiskScore,
  KYCStatus,
  SwapParams,
  PolicySettings,
  AMTTPResult,
} from './types.js';
export { AMTTP_ABI, CROSSCHAIN_ABI } from './abi.js';

// Utility functions
export const utils = {
  /**
   * Format risk score for display
   */
  formatRiskScore: (score: number): string => {
    return `${(score * 100).toFixed(1)}%`;
  },

  /**
   * Get risk color for UI
   */
  getRiskColor: (category: string): string => {
    switch (category) {
      case 'MINIMAL': return '#22c55e'; // green
      case 'LOW': return '#84cc16';     // lime  
      case 'MEDIUM': return '#f59e0b';  // amber
      case 'HIGH': return '#ef4444';    // red
      default: return '#6b7280';        // gray
    }
  },

  /**
   * Get action color for UI
   */
  getActionColor: (action: string): string => {
    switch (action) {
      case 'APPROVE': return '#22c55e'; // green
      case 'REVIEW': return '#f59e0b';  // amber
      case 'ESCROW': return '#f97316';  // orange
      case 'BLOCK': return '#ef4444';   // red
      default: return '#6b7280';        // gray
    }
  },

  /**
   * Check if address is valid Ethereum address
   */
  isValidAddress: (address: string): boolean => {
    return /^0x[a-fA-F0-9]{40}$/.test(address);
  },

  /**
   * Format wei amount to readable string
   */
  formatAmount: (wei: bigint, decimals: number = 18): string => {
    return (Number(wei) / Math.pow(10, decimals)).toFixed(4);
  },

  /**
   * Convert risk score (0-1) to contract format (0-1000)
   */
  toContractScore: (score: number): number => {
    return Math.round(Math.max(0, Math.min(1, score)) * 1000);
  },

  /**
   * Convert contract score (0-1000) to normalized (0-1)
   */
  fromContractScore: (score: number): number => {
    return Math.max(0, Math.min(1000, score)) / 1000;
  }
};