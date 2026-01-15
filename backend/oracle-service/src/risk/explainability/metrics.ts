/**
 * Metrics Collection for Explainability System
 * 
 * Provides observability into:
 * - Explanation generation performance
 * - Action distribution
 * - Typology frequency
 * - Error rates
 * - Cache performance
 */

import {
  ExplainabilityMetrics,
  RiskAction,
  RiskExplanation,
  Severity
} from './types.js';

// ═══════════════════════════════════════════════════════════════════════════════
// METRICS COLLECTOR
// ═══════════════════════════════════════════════════════════════════════════════

export class MetricsCollector {
  private metrics: ExplainabilityMetrics;
  private processingTimes: number[] = [];
  private maxSampleSize = 1000;
  
  constructor() {
    this.metrics = this.createInitialMetrics();
  }
  
  private createInitialMetrics(): ExplainabilityMetrics {
    return {
      explanationsTotal: 0,
      explanationsByAction: {
        [RiskAction.ALLOW]: 0,
        [RiskAction.REVIEW]: 0,
        [RiskAction.ESCROW]: 0,
        [RiskAction.BLOCK]: 0
      },
      explanationsByTypology: {},
      processingTimeMs: {
        p50: 0,
        p90: 0,
        p99: 0,
        avg: 0
      },
      cacheHits: 0,
      cacheMisses: 0,
      errorsTotal: 0,
      errorsByType: {},
      degradedModeCount: 0
    };
  }
  
  /**
   * Record a successful explanation
   */
  recordExplanation(explanation: RiskExplanation): void {
    this.metrics.explanationsTotal++;
    this.metrics.explanationsByAction[explanation.action]++;
    
    // Track typologies
    for (const match of explanation.typologyMatches) {
      const key = match.typology;
      this.metrics.explanationsByTypology[key] = 
        (this.metrics.explanationsByTypology[key] ?? 0) + 1;
    }
    
    // Track degraded mode
    if (explanation.degradedMode) {
      this.metrics.degradedModeCount++;
    }
    
    // Track processing time
    if (explanation.metadata?.processingTimeMs) {
      this.recordProcessingTime(explanation.metadata.processingTimeMs);
    }
  }
  
  /**
   * Record processing time
   */
  recordProcessingTime(timeMs: number): void {
    this.processingTimes.push(timeMs);
    
    // Keep sample size bounded
    if (this.processingTimes.length > this.maxSampleSize) {
      this.processingTimes.shift();
    }
    
    // Update percentiles
    this.updatePercentiles();
  }
  
  private updatePercentiles(): void {
    if (this.processingTimes.length === 0) return;
    
    const sorted = [...this.processingTimes].sort((a, b) => a - b);
    const len = sorted.length;
    
    this.metrics.processingTimeMs = {
      p50: sorted[Math.floor(len * 0.5)] ?? 0,
      p90: sorted[Math.floor(len * 0.9)] ?? 0,
      p99: sorted[Math.floor(len * 0.99)] ?? 0,
      avg: sorted.reduce((a, b) => a + b, 0) / len
    };
  }
  
  /**
   * Record cache hit
   */
  recordCacheHit(): void {
    this.metrics.cacheHits++;
  }
  
  /**
   * Record cache miss
   */
  recordCacheMiss(): void {
    this.metrics.cacheMisses++;
  }
  
  /**
   * Record an error
   */
  recordError(errorType: string): void {
    this.metrics.errorsTotal++;
    this.metrics.errorsByType[errorType] = 
      (this.metrics.errorsByType[errorType] ?? 0) + 1;
  }
  
  /**
   * Get current metrics snapshot
   */
  getMetrics(): ExplainabilityMetrics {
    return { ...this.metrics };
  }
  
  /**
   * Get Prometheus-formatted metrics
   */
  toPrometheus(prefix: string = 'amttp_explainability'): string {
    const lines: string[] = [];
    
    // Total explanations
    lines.push(`# HELP ${prefix}_explanations_total Total explanations generated`);
    lines.push(`# TYPE ${prefix}_explanations_total counter`);
    lines.push(`${prefix}_explanations_total ${this.metrics.explanationsTotal}`);
    
    // By action
    lines.push(`# HELP ${prefix}_by_action_total Explanations by action type`);
    lines.push(`# TYPE ${prefix}_by_action_total counter`);
    for (const [action, count] of Object.entries(this.metrics.explanationsByAction)) {
      lines.push(`${prefix}_by_action_total{action="${action}"} ${count}`);
    }
    
    // By typology
    lines.push(`# HELP ${prefix}_by_typology_total Explanations by typology`);
    lines.push(`# TYPE ${prefix}_by_typology_total counter`);
    for (const [typology, count] of Object.entries(this.metrics.explanationsByTypology)) {
      lines.push(`${prefix}_by_typology_total{typology="${typology}"} ${count}`);
    }
    
    // Processing time
    lines.push(`# HELP ${prefix}_processing_time_ms Processing time percentiles`);
    lines.push(`# TYPE ${prefix}_processing_time_ms summary`);
    lines.push(`${prefix}_processing_time_ms{quantile="0.5"} ${this.metrics.processingTimeMs.p50}`);
    lines.push(`${prefix}_processing_time_ms{quantile="0.9"} ${this.metrics.processingTimeMs.p90}`);
    lines.push(`${prefix}_processing_time_ms{quantile="0.99"} ${this.metrics.processingTimeMs.p99}`);
    
    // Cache
    lines.push(`# HELP ${prefix}_cache_hits_total Cache hits`);
    lines.push(`# TYPE ${prefix}_cache_hits_total counter`);
    lines.push(`${prefix}_cache_hits_total ${this.metrics.cacheHits}`);
    lines.push(`${prefix}_cache_misses_total ${this.metrics.cacheMisses}`);
    
    // Errors
    lines.push(`# HELP ${prefix}_errors_total Total errors`);
    lines.push(`# TYPE ${prefix}_errors_total counter`);
    lines.push(`${prefix}_errors_total ${this.metrics.errorsTotal}`);
    
    // Degraded mode
    lines.push(`# HELP ${prefix}_degraded_mode_total Explanations in degraded mode`);
    lines.push(`# TYPE ${prefix}_degraded_mode_total counter`);
    lines.push(`${prefix}_degraded_mode_total ${this.metrics.degradedModeCount}`);
    
    return lines.join('\n');
  }
  
  /**
   * Reset metrics (for testing)
   */
  reset(): void {
    this.metrics = this.createInitialMetrics();
    this.processingTimes = [];
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// LOGGER
// ═══════════════════════════════════════════════════════════════════════════════

export interface LogEntry {
  level: Severity;
  message: string;
  timestamp: string;
  context?: Record<string, unknown>;
}

export class Logger {
  private level: Severity;
  private redactPII: boolean;
  
  constructor(options: { level?: Severity; redactPII?: boolean } = {}) {
    this.level = options.level ?? Severity.INFO;
    this.redactPII = options.redactPII ?? true;
  }
  
  private shouldLog(level: Severity): boolean {
    const levels: Record<Severity, number> = {
      [Severity.DEBUG]: 0,
      [Severity.INFO]: 1,
      [Severity.WARN]: 2,
      [Severity.ERROR]: 3,
      [Severity.CRITICAL]: 4
    };
    return levels[level] >= levels[this.level];
  }
  
  private format(level: Severity, message: string, context?: Record<string, unknown>): LogEntry {
    const entry: LogEntry = {
      level,
      message,
      timestamp: new Date().toISOString()
    };
    
    if (context) {
      entry.context = this.redactPII ? this.redact(context) : context;
    }
    
    return entry;
  }
  
  private redact(obj: Record<string, unknown>): Record<string, unknown> {
    const sensitive = ['address', 'ip', 'email', 'phone', 'name', 'ssn'];
    const result: Record<string, unknown> = {};
    
    for (const [key, value] of Object.entries(obj)) {
      if (sensitive.some(s => key.toLowerCase().includes(s))) {
        result[key] = '[REDACTED]';
      } else if (typeof value === 'object' && value !== null) {
        result[key] = this.redact(value as Record<string, unknown>);
      } else {
        result[key] = value;
      }
    }
    
    return result;
  }
  
  debug(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(Severity.DEBUG)) {
      console.debug(JSON.stringify(this.format(Severity.DEBUG, message, context)));
    }
  }
  
  info(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(Severity.INFO)) {
      console.info(JSON.stringify(this.format(Severity.INFO, message, context)));
    }
  }
  
  warn(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(Severity.WARN)) {
      console.warn(JSON.stringify(this.format(Severity.WARN, message, context)));
    }
  }
  
  error(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(Severity.ERROR)) {
      console.error(JSON.stringify(this.format(Severity.ERROR, message, context)));
    }
  }
  
  critical(message: string, context?: Record<string, unknown>): void {
    if (this.shouldLog(Severity.CRITICAL)) {
      console.error(JSON.stringify(this.format(Severity.CRITICAL, message, context)));
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SINGLETON INSTANCES
// ═══════════════════════════════════════════════════════════════════════════════

export const metrics = new MetricsCollector();
export const logger = new Logger();
