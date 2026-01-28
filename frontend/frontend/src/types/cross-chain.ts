/**
 * Cross-Chain Types
 * 
 * Sprint 8: Cross-Chain Dashboard
 * 
 * Ground Truth Reference:
 * - Cross-chain transfers need unified monitoring
 * - Bridge status is critical for compliance
 * - LayerZero integration for omnichain messaging
 */

// ═══════════════════════════════════════════════════════════════════════════════
// CHAIN DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

export enum Chain {
  ETHEREUM = 'ethereum',
  POLYGON = 'polygon',
  ARBITRUM = 'arbitrum',
  OPTIMISM = 'optimism',
  BASE = 'base',
  AVALANCHE = 'avalanche',
  BSC = 'bsc',
  FANTOM = 'fantom',
  GNOSIS = 'gnosis',
  ZKSYNC = 'zksync',
  LINEA = 'linea',
}

export interface ChainConfig {
  id: Chain;
  name: string;
  chainId: number;
  lzEndpointId?: number; // LayerZero endpoint
  rpcUrl: string;
  explorerUrl: string;
  nativeCurrency: {
    name: string;
    symbol: string;
    decimals: number;
  };
  iconUrl?: string;
  color: string;
  status: ChainStatus;
  latency: number; // ms
  blockTime: number; // seconds
}

export enum ChainStatus {
  HEALTHY = 'HEALTHY',
  DEGRADED = 'DEGRADED',
  DOWN = 'DOWN',
  MAINTENANCE = 'MAINTENANCE',
}

// ═══════════════════════════════════════════════════════════════════════════════
// BRIDGE DEFINITIONS
// ═══════════════════════════════════════════════════════════════════════════════

export enum BridgeProtocol {
  LAYERZERO = 'LAYERZERO',
  WORMHOLE = 'WORMHOLE',
  AXELAR = 'AXELAR',
  CCIP = 'CCIP', // Chainlink CCIP
  STARGATE = 'STARGATE',
  HOP = 'HOP',
  ACROSS = 'ACROSS',
  NATIVE = 'NATIVE', // Native bridges (L2 -> L1)
}

export interface Bridge {
  id: string;
  protocol: BridgeProtocol;
  sourceChain: Chain;
  destinationChain: Chain;
  status: BridgeStatus;
  supportedAssets: string[];
  fees: BridgeFees;
  limits: BridgeLimits;
  stats: BridgeStats;
  lastHealthCheck: number;
}

export enum BridgeStatus {
  OPERATIONAL = 'OPERATIONAL',
  CONGESTED = 'CONGESTED',
  PAUSED = 'PAUSED',
  OFFLINE = 'OFFLINE',
}

export interface BridgeFees {
  baseFee: number;
  percentageFee: number; // basis points
  gasEstimate: number;
  currency: string;
}

export interface BridgeLimits {
  minAmount: number;
  maxAmount: number;
  dailyLimit: number;
  remainingDailyLimit: number;
}

export interface BridgeStats {
  totalVolume24h: number;
  totalTransactions24h: number;
  avgTransferTime: number; // seconds
  successRate: number; // percentage
  pendingTransactions: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CROSS-CHAIN TRANSFER
// ═══════════════════════════════════════════════════════════════════════════════

export interface CrossChainTransfer {
  id: string;
  sourceChain: Chain;
  destinationChain: Chain;
  bridge: BridgeProtocol;
  
  // Transaction details
  sourceTxHash: string;
  destinationTxHash?: string;
  sender: string;
  recipient: string;
  amount: number;
  asset: string;
  
  // Status
  status: TransferStatus;
  phase: TransferPhase;
  progress: number; // 0-100
  
  // Timing
  initiatedAt: number;
  confirmedAt?: number;
  completedAt?: number;
  estimatedCompletionTime?: number;
  
  // Fees
  gasPaidSource: number;
  gasPaidDestination?: number;
  bridgeFee: number;
  
  // Error handling
  errorMessage?: string;
  retryCount: number;
  
  // Compliance
  riskScore: number;
  policyFlags: string[];
  requiresApproval: boolean;
  approvedBy?: string;
}

export enum TransferStatus {
  PENDING = 'PENDING',
  PROCESSING = 'PROCESSING',
  CONFIRMING = 'CONFIRMING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  STUCK = 'STUCK',
  CANCELLED = 'CANCELLED',
}

export enum TransferPhase {
  INITIATED = 'INITIATED',
  SOURCE_CONFIRMED = 'SOURCE_CONFIRMED',
  BRIDGE_PROCESSING = 'BRIDGE_PROCESSING',
  DESTINATION_PENDING = 'DESTINATION_PENDING',
  DESTINATION_CONFIRMED = 'DESTINATION_CONFIRMED',
  COMPLETED = 'COMPLETED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// CROSS-CHAIN MESSAGE (LayerZero)
// ═══════════════════════════════════════════════════════════════════════════════

export interface CrossChainMessage {
  id: string;
  nonce: number;
  srcChain: Chain;
  srcEndpoint: string;
  dstChain: Chain;
  dstEndpoint: string;
  
  // Message data
  payload: string;
  adapterParams?: string;
  
  // Status
  status: MessageStatus;
  srcTxHash: string;
  dstTxHash?: string;
  
  // Timing
  sentAt: number;
  receivedAt?: number;
  
  // Metadata
  gasLimit: number;
  nativeFee: number;
  zroFee: number;
}

export enum MessageStatus {
  INFLIGHT = 'INFLIGHT',
  DELIVERED = 'DELIVERED',
  FAILED = 'FAILED',
  BLOCKED = 'BLOCKED',
}

// ═══════════════════════════════════════════════════════════════════════════════
// NETWORK HEALTH
// ═══════════════════════════════════════════════════════════════════════════════

export interface NetworkHealth {
  chain: Chain;
  status: ChainStatus;
  blockHeight: number;
  lastBlockTime: number;
  avgBlockTime: number;
  gasPrice: number;
  gasPriceGwei: number;
  pendingTxCount: number;
  peersCount: number;
  syncStatus: SyncStatus;
  rpcLatency: number;
  indexerLatency: number;
  alertLevel: AlertLevel;
  alerts: NetworkAlert[];
}

export enum SyncStatus {
  SYNCED = 'SYNCED',
  SYNCING = 'SYNCING',
  BEHIND = 'BEHIND',
}

export enum AlertLevel {
  NONE = 'NONE',
  INFO = 'INFO',
  WARNING = 'WARNING',
  CRITICAL = 'CRITICAL',
}

export interface NetworkAlert {
  id: string;
  chain: Chain;
  level: AlertLevel;
  title: string;
  message: string;
  timestamp: number;
  acknowledged: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CROSS-CHAIN ANALYTICS
// ═══════════════════════════════════════════════════════════════════════════════

export interface CrossChainAnalytics {
  timeRange: {
    start: number;
    end: number;
  };
  
  // Volume metrics
  totalVolume: number;
  volumeByChain: Record<Chain, number>;
  volumeByBridge: Record<BridgeProtocol, number>;
  volumeByAsset: Record<string, number>;
  
  // Transfer metrics
  totalTransfers: number;
  transfersByStatus: Record<TransferStatus, number>;
  avgTransferTime: number;
  successRate: number;
  
  // Fee metrics
  totalFeesPaid: number;
  avgFeePerTransfer: number;
  
  // Risk metrics
  highRiskTransfers: number;
  flaggedTransfers: number;
  blockedTransfers: number;
  
  // Time series
  volumeTimeSeries: Array<{ timestamp: number; volume: number }>;
  transferCountTimeSeries: Array<{ timestamp: number; count: number }>;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROUTE OPTIMIZATION
// ═══════════════════════════════════════════════════════════════════════════════

export interface RouteQuote {
  id: string;
  sourceChain: Chain;
  destinationChain: Chain;
  asset: string;
  amount: number;
  
  // Route details
  bridge: BridgeProtocol;
  estimatedTime: number; // seconds
  estimatedGas: number;
  bridgeFee: number;
  totalCost: number;
  
  // Output
  estimatedReceived: number;
  priceImpact: number;
  slippage: number;
  
  // Metadata
  validUntil: number;
  warning?: string;
}

export interface RouteComparison {
  sourceChain: Chain;
  destinationChain: Chain;
  amount: number;
  asset: string;
  quotes: RouteQuote[];
  recommended: string; // quote id
  comparedAt: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function getChainName(chain: Chain): string {
  const names: Record<Chain, string> = {
    [Chain.ETHEREUM]: 'Ethereum',
    [Chain.POLYGON]: 'Polygon',
    [Chain.ARBITRUM]: 'Arbitrum',
    [Chain.OPTIMISM]: 'Optimism',
    [Chain.BASE]: 'Base',
    [Chain.AVALANCHE]: 'Avalanche',
    [Chain.BSC]: 'BNB Chain',
    [Chain.FANTOM]: 'Fantom',
    [Chain.GNOSIS]: 'Gnosis',
    [Chain.ZKSYNC]: 'zkSync Era',
    [Chain.LINEA]: 'Linea',
  };
  return names[chain];
}

export function getChainColor(chain: Chain): string {
  const colors: Record<Chain, string> = {
    [Chain.ETHEREUM]: '#627EEA',
    [Chain.POLYGON]: '#8247E5',
    [Chain.ARBITRUM]: '#28A0F0',
    [Chain.OPTIMISM]: '#FF0420',
    [Chain.BASE]: '#0052FF',
    [Chain.AVALANCHE]: '#E84142',
    [Chain.BSC]: '#F0B90B',
    [Chain.FANTOM]: '#1969FF',
    [Chain.GNOSIS]: '#04795B',
    [Chain.ZKSYNC]: '#4E529A',
    [Chain.LINEA]: '#61DFFF',
  };
  return colors[chain];
}

export function getBridgeProtocolName(protocol: BridgeProtocol): string {
  const names: Record<BridgeProtocol, string> = {
    [BridgeProtocol.LAYERZERO]: 'LayerZero',
    [BridgeProtocol.WORMHOLE]: 'Wormhole',
    [BridgeProtocol.AXELAR]: 'Axelar',
    [BridgeProtocol.CCIP]: 'Chainlink CCIP',
    [BridgeProtocol.STARGATE]: 'Stargate',
    [BridgeProtocol.HOP]: 'Hop Protocol',
    [BridgeProtocol.ACROSS]: 'Across',
    [BridgeProtocol.NATIVE]: 'Native Bridge',
  };
  return names[protocol];
}

export function getStatusColor(status: BridgeStatus | ChainStatus | TransferStatus): string {
  const colors: Record<string, string> = {
    // Bridge/Chain status
    OPERATIONAL: 'green',
    HEALTHY: 'green',
    CONGESTED: 'yellow',
    DEGRADED: 'yellow',
    PAUSED: 'orange',
    MAINTENANCE: 'orange',
    OFFLINE: 'red',
    DOWN: 'red',
    // Transfer status
    PENDING: 'yellow',
    PROCESSING: 'blue',
    CONFIRMING: 'cyan',
    COMPLETED: 'green',
    FAILED: 'red',
    STUCK: 'orange',
    CANCELLED: 'gray',
  };
  return colors[status] || 'gray';
}

export function formatTransferTime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}
