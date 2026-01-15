/**
 * AMTTP Bulk Transaction API
 * High-throughput batch scoring for exchanges processing 1000+ tx/batch
 */

import { Router } from 'express';
import { createHash, randomUUID } from 'crypto';

// ═══════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════

export interface BulkTransaction {
  id: string;                    // Client-provided ID
  fromAddress: string;
  toAddress: string;
  amount: string;
  asset: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
}

export interface ScoredTransaction {
  id: string;
  riskScore: number;             // 0-100
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  flags: string[];
  sanctioned: boolean;
  pepExposure: boolean;
  processingTimeMs: number;
}

export interface BatchJob {
  jobId: string;
  status: 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  submittedAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  
  totalTransactions: number;
  processedTransactions: number;
  
  results?: ScoredTransaction[];
  summary?: BatchSummary;
  
  error?: string;
}

export interface BatchSummary {
  totalProcessed: number;
  avgRiskScore: number;
  riskDistribution: {
    LOW: number;
    MEDIUM: number;
    HIGH: number;
    CRITICAL: number;
  };
  flaggedCount: number;
  sanctionedCount: number;
  pepCount: number;
  processingTimeMs: number;
  throughput: number;  // tx/second
}

// ═══════════════════════════════════════════════════════════════════════════
// MOCK DATA FOR RISK SCORING
// ═══════════════════════════════════════════════════════════════════════════

const SANCTIONED_ADDRESSES = new Set([
  '0x19aa5fe80d33a56d56c78e82ea5e50e5d80b4dff',  // Tornado Cash
  '0x8589427373d6d84e98730d7795d8f6f8731fda16',  // Tornado Cash
  '0x722122df12d4e14e13ac3b6895a86e84145b6967',  // Tornado Cash
  '0xd4b88df4d29f5cedd6857912842cff3b20c8cfa3',  // Tornado Cash
]);

const HIGH_RISK_PATTERNS = [
  { pattern: /tornado/i, flag: 'TORNADO_CASH' },
  { pattern: /mixer/i, flag: 'MIXER_DETECTED' },
  { pattern: /privacy/i, flag: 'PRIVACY_TOOL' },
];

// ═══════════════════════════════════════════════════════════════════════════
// BULK SCORING SERVICE
// ═══════════════════════════════════════════════════════════════════════════

export class BulkScoringService {
  private jobs: Map<string, BatchJob> = new Map();
  private maxBatchSize = 10000;
  private concurrentWorkers = 4;
  
  /**
   * Submit a batch for async processing
   */
  async submitBatch(transactions: BulkTransaction[]): Promise<{ jobId: string; estimatedTimeMs: number }> {
    if (transactions.length > this.maxBatchSize) {
      throw new Error(`Batch size ${transactions.length} exceeds maximum ${this.maxBatchSize}`);
    }
    
    const jobId = randomUUID();
    const estimatedTimeMs = Math.ceil(transactions.length * 2); // ~2ms per tx
    
    const job: BatchJob = {
      jobId,
      status: 'QUEUED',
      submittedAt: new Date(),
      totalTransactions: transactions.length,
      processedTransactions: 0,
    };
    
    this.jobs.set(jobId, job);
    
    // Process async
    this.processJobAsync(jobId, transactions);
    
    return { jobId, estimatedTimeMs };
  }

  /**
   * Synchronous batch scoring (for smaller batches)
   */
  scoreBatchSync(transactions: BulkTransaction[]): {
    results: ScoredTransaction[];
    summary: BatchSummary;
  } {
    const startTime = Date.now();
    const results: ScoredTransaction[] = [];
    
    for (const tx of transactions) {
      const result = this.scoreTransaction(tx);
      results.push(result);
    }
    
    const processingTimeMs = Date.now() - startTime;
    const summary = this.generateSummary(results, processingTimeMs);
    
    return { results, summary };
  }

  /**
   * Get job status
   */
  getJob(jobId: string): BatchJob | undefined {
    return this.jobs.get(jobId);
  }

  /**
   * Get all jobs
   */
  getJobs(limit = 100): BatchJob[] {
    return Array.from(this.jobs.values())
      .sort((a, b) => b.submittedAt.getTime() - a.submittedAt.getTime())
      .slice(0, limit);
  }

  /**
   * Score a single transaction
   */
  private scoreTransaction(tx: BulkTransaction): ScoredTransaction {
    const startTime = Date.now();
    const flags: string[] = [];
    let riskScore = 20; // Base score
    let sanctioned = false;
    let pepExposure = false;
    
    // Check sanctioned addresses
    const fromLower = tx.fromAddress.toLowerCase();
    const toLower = tx.toAddress.toLowerCase();
    
    if (SANCTIONED_ADDRESSES.has(fromLower) || SANCTIONED_ADDRESSES.has(toLower)) {
      sanctioned = true;
      riskScore = 100;
      flags.push('SANCTIONED_ADDRESS');
    }
    
    // Check amount thresholds
    const amount = parseFloat(tx.amount);
    if (amount > 100000) {
      riskScore = Math.min(100, riskScore + 30);
      flags.push('HIGH_VALUE_TX');
    } else if (amount > 10000) {
      riskScore = Math.min(100, riskScore + 15);
      flags.push('MEDIUM_VALUE_TX');
    }
    
    // Pattern matching
    for (const { pattern, flag } of HIGH_RISK_PATTERNS) {
      if (pattern.test(tx.metadata?.description as string || '')) {
        riskScore = Math.min(100, riskScore + 25);
        flags.push(flag);
      }
    }
    
    // Randomize for demo (remove in production)
    if (!sanctioned && Math.random() < 0.02) {
      pepExposure = true;
      riskScore = Math.min(100, riskScore + 20);
      flags.push('PEP_EXPOSURE');
    }
    
    // Determine risk level
    let riskLevel: ScoredTransaction['riskLevel'];
    if (riskScore >= 80) {
      riskLevel = 'CRITICAL';
    } else if (riskScore >= 60) {
      riskLevel = 'HIGH';
    } else if (riskScore >= 40) {
      riskLevel = 'MEDIUM';
    } else {
      riskLevel = 'LOW';
    }
    
    return {
      id: tx.id,
      riskScore,
      riskLevel,
      flags,
      sanctioned,
      pepExposure,
      processingTimeMs: Date.now() - startTime,
    };
  }

  /**
   * Generate summary statistics
   */
  private generateSummary(results: ScoredTransaction[], processingTimeMs: number): BatchSummary {
    const totalProcessed = results.length;
    
    return {
      totalProcessed,
      avgRiskScore: results.reduce((s, r) => s + r.riskScore, 0) / totalProcessed || 0,
      riskDistribution: {
        LOW: results.filter(r => r.riskLevel === 'LOW').length,
        MEDIUM: results.filter(r => r.riskLevel === 'MEDIUM').length,
        HIGH: results.filter(r => r.riskLevel === 'HIGH').length,
        CRITICAL: results.filter(r => r.riskLevel === 'CRITICAL').length,
      },
      flaggedCount: results.filter(r => r.flags.length > 0).length,
      sanctionedCount: results.filter(r => r.sanctioned).length,
      pepCount: results.filter(r => r.pepExposure).length,
      processingTimeMs,
      throughput: Math.round(totalProcessed / (processingTimeMs / 1000)),
    };
  }

  /**
   * Process job asynchronously
   */
  private async processJobAsync(jobId: string, transactions: BulkTransaction[]): Promise<void> {
    const job = this.jobs.get(jobId);
    if (!job) return;
    
    job.status = 'PROCESSING';
    job.startedAt = new Date();
    
    try {
      const startTime = Date.now();
      const results: ScoredTransaction[] = [];
      
      // Process in chunks
      const chunkSize = Math.ceil(transactions.length / this.concurrentWorkers);
      const chunks: BulkTransaction[][] = [];
      
      for (let i = 0; i < transactions.length; i += chunkSize) {
        chunks.push(transactions.slice(i, i + chunkSize));
      }
      
      // Simulate parallel processing
      for (const chunk of chunks) {
        for (const tx of chunk) {
          results.push(this.scoreTransaction(tx));
          job.processedTransactions++;
        }
        // Yield to event loop
        await new Promise(resolve => setImmediate(resolve));
      }
      
      const processingTimeMs = Date.now() - startTime;
      
      job.status = 'COMPLETED';
      job.completedAt = new Date();
      job.results = results;
      job.summary = this.generateSummary(results, processingTimeMs);
      
    } catch (error) {
      job.status = 'FAILED';
      job.error = error instanceof Error ? error.message : String(error);
    }
    
    this.jobs.set(jobId, job);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// REST API ROUTES
// ═══════════════════════════════════════════════════════════════════════════

export const bulkRouter = Router();
const bulkService = new BulkScoringService();

// GET /bulk - API info
bulkRouter.get('/', (req, res) => {
  res.json({
    service: 'AMTTP Bulk Transaction API',
    description: 'High-throughput batch risk scoring for exchanges',
    limits: {
      maxBatchSize: 10000,
      recommendedBatchSize: 1000,
      estimatedThroughput: '500+ tx/sec',
    },
    endpoints: {
      'POST /bulk/score': 'Synchronous batch scoring (< 500 tx)',
      'POST /bulk/submit': 'Async batch submission (large batches)',
      'GET /bulk/job/:id': 'Get job status and results',
      'GET /bulk/jobs': 'List all jobs',
    },
    requestFormat: {
      transactions: [
        {
          id: 'tx-123',
          fromAddress: '0x...',
          toAddress: '0x...',
          amount: '1000.00',
          asset: 'ETH',
          timestamp: '2024-01-15T10:30:00Z',
          metadata: { description: 'Optional metadata' },
        },
      ],
    },
  });
});

// POST /bulk/score - Synchronous scoring
bulkRouter.post('/score', (req, res) => {
  try {
    const transactions: BulkTransaction[] = req.body.transactions;
    
    if (!transactions || !Array.isArray(transactions)) {
      res.status(400).json({ error: 'transactions array required' });
      return;
    }
    
    if (transactions.length > 500) {
      res.status(400).json({ 
        error: 'Use /bulk/submit for batches > 500 transactions',
        suggestion: 'POST /bulk/submit for async processing',
      });
      return;
    }
    
    const { results, summary } = bulkService.scoreBatchSync(transactions);
    
    res.json({
      success: true,
      results,
      summary,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// POST /bulk/submit - Async batch submission
bulkRouter.post('/submit', async (req, res) => {
  try {
    const transactions: BulkTransaction[] = req.body.transactions;
    
    if (!transactions || !Array.isArray(transactions)) {
      res.status(400).json({ error: 'transactions array required' });
      return;
    }
    
    const { jobId, estimatedTimeMs } = await bulkService.submitBatch(transactions);
    
    res.status(202).json({
      success: true,
      jobId,
      status: 'QUEUED',
      estimatedTimeMs,
      statusUrl: `/bulk/job/${jobId}`,
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error);
    res.status(400).json({ error: msg });
  }
});

// GET /bulk/job/:id - Get job status
bulkRouter.get('/job/:id', (req, res) => {
  const job = bulkService.getJob(req.params.id);
  
  if (!job) {
    res.status(404).json({ error: 'Job not found' });
    return;
  }
  
  // Don't include full results in status check (can be large)
  const response: Partial<BatchJob> = {
    jobId: job.jobId,
    status: job.status,
    submittedAt: job.submittedAt,
    startedAt: job.startedAt,
    completedAt: job.completedAt,
    totalTransactions: job.totalTransactions,
    processedTransactions: job.processedTransactions,
    error: job.error,
  };
  
  if (job.status === 'COMPLETED') {
    response.summary = job.summary;
  }
  
  res.json(response);
});

// GET /bulk/job/:id/results - Get full results
bulkRouter.get('/job/:id/results', (req, res) => {
  const job = bulkService.getJob(req.params.id);
  
  if (!job) {
    res.status(404).json({ error: 'Job not found' });
    return;
  }
  
  if (job.status !== 'COMPLETED') {
    res.status(400).json({ 
      error: 'Job not completed',
      status: job.status,
    });
    return;
  }
  
  // Pagination
  const page = parseInt(req.query.page as string) || 1;
  const pageSize = parseInt(req.query.pageSize as string) || 100;
  const start = (page - 1) * pageSize;
  
  const results = job.results?.slice(start, start + pageSize) || [];
  
  res.json({
    jobId: job.jobId,
    summary: job.summary,
    pagination: {
      page,
      pageSize,
      totalResults: job.results?.length || 0,
      totalPages: Math.ceil((job.results?.length || 0) / pageSize),
    },
    results,
  });
});

// GET /bulk/job/:id/flagged - Get only flagged transactions
bulkRouter.get('/job/:id/flagged', (req, res) => {
  const job = bulkService.getJob(req.params.id);
  
  if (!job) {
    res.status(404).json({ error: 'Job not found' });
    return;
  }
  
  if (job.status !== 'COMPLETED') {
    res.status(400).json({ 
      error: 'Job not completed',
      status: job.status,
    });
    return;
  }
  
  const flagged = job.results?.filter(r => 
    r.riskLevel === 'HIGH' || 
    r.riskLevel === 'CRITICAL' || 
    r.sanctioned || 
    r.pepExposure
  ) || [];
  
  res.json({
    jobId: job.jobId,
    totalFlagged: flagged.length,
    flagged,
  });
});

// GET /bulk/jobs - List jobs
bulkRouter.get('/list/jobs', (req, res) => {
  const limit = parseInt(req.query.limit as string) || 100;
  const jobs = bulkService.getJobs(limit).map(job => ({
    jobId: job.jobId,
    status: job.status,
    submittedAt: job.submittedAt,
    completedAt: job.completedAt,
    totalTransactions: job.totalTransactions,
    processedTransactions: job.processedTransactions,
  }));
  
  res.json({ count: jobs.length, jobs });
});

export default bulkRouter;
