/**
 * Baseline Calculation Service
 * 
 * Provides statistical baselines for anomaly detection
 * 
 * Ground Truth Reference:
 * - 30-day rolling baseline
 * - Z-score calculation
 * - Deviation detection
 */

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface BaselineStats {
  mean: number;
  stdDev: number;
  min: number;
  max: number;
  count: number;
  period: string;
}

export interface VelocityBaseline {
  hourly: BaselineStats[];  // 24 hours
  daily: BaselineStats[];   // 7 days
  overall: BaselineStats;
}

export interface DeviationResult {
  value: number;
  baseline: number;
  zScore: number;
  isAnomaly: boolean;
  severity: 'normal' | 'elevated' | 'high' | 'critical';
}

export interface TimeSeriesPoint {
  timestamp: number;
  value: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const BASELINE_WINDOW_DAYS = 30;
const ANOMALY_THRESHOLD_Z = 2.0;  // 2 standard deviations
const HIGH_ANOMALY_Z = 3.0;
const CRITICAL_ANOMALY_Z = 4.0;

// ═══════════════════════════════════════════════════════════════════════════════
// STATISTICAL FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

export function calculateMean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function calculateStdDev(values: number[], mean?: number): number {
  if (values.length < 2) return 0;
  const m = mean ?? calculateMean(values);
  const squaredDiffs = values.map(v => Math.pow(v - m, 2));
  return Math.sqrt(squaredDiffs.reduce((sum, v) => sum + v, 0) / (values.length - 1));
}

export function calculateZScore(value: number, mean: number, stdDev: number): number {
  if (stdDev === 0) return 0;
  return (value - mean) / stdDev;
}

export function calculatePercentile(values: number[], percentile: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.ceil((percentile / 100) * sorted.length) - 1;
  return sorted[Math.max(0, index)];
}

// ═══════════════════════════════════════════════════════════════════════════════
// BASELINE CALCULATION
// ═══════════════════════════════════════════════════════════════════════════════

export function calculateBaselineStats(values: number[]): BaselineStats {
  const mean = calculateMean(values);
  const stdDev = calculateStdDev(values, mean);
  
  return {
    mean,
    stdDev,
    min: values.length > 0 ? Math.min(...values) : 0,
    max: values.length > 0 ? Math.max(...values) : 0,
    count: values.length,
    period: `${BASELINE_WINDOW_DAYS}d`,
  };
}

export function calculateVelocityBaseline(
  timeSeries: TimeSeriesPoint[],
  windowDays: number = BASELINE_WINDOW_DAYS
): VelocityBaseline {
  // Filter to window
  const cutoff = Date.now() - (windowDays * 24 * 60 * 60 * 1000);
  const filtered = timeSeries.filter(p => p.timestamp >= cutoff);
  
  // Group by hour of day (0-23)
  const hourlyBuckets: number[][] = Array.from({ length: 24 }, () => []);
  
  // Group by day of week (0-6)
  const dailyBuckets: number[][] = Array.from({ length: 7 }, () => []);
  
  filtered.forEach(point => {
    const date = new Date(point.timestamp);
    const hour = date.getHours();
    const day = date.getDay();
    
    hourlyBuckets[hour].push(point.value);
    dailyBuckets[day].push(point.value);
  });
  
  return {
    hourly: hourlyBuckets.map(calculateBaselineStats),
    daily: dailyBuckets.map(calculateBaselineStats),
    overall: calculateBaselineStats(filtered.map(p => p.value)),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// DEVIATION DETECTION
// ═══════════════════════════════════════════════════════════════════════════════

export function detectDeviation(
  value: number,
  baseline: BaselineStats
): DeviationResult {
  const zScore = calculateZScore(value, baseline.mean, baseline.stdDev);
  const absZ = Math.abs(zScore);
  
  let severity: DeviationResult['severity'] = 'normal';
  let isAnomaly = false;
  
  if (absZ >= CRITICAL_ANOMALY_Z) {
    severity = 'critical';
    isAnomaly = true;
  } else if (absZ >= HIGH_ANOMALY_Z) {
    severity = 'high';
    isAnomaly = true;
  } else if (absZ >= ANOMALY_THRESHOLD_Z) {
    severity = 'elevated';
    isAnomaly = true;
  }
  
  return {
    value,
    baseline: baseline.mean,
    zScore,
    isAnomaly,
    severity,
  };
}

export function detectTimeBasedDeviation(
  value: number,
  timestamp: number,
  velocityBaseline: VelocityBaseline
): DeviationResult {
  const date = new Date(timestamp);
  const hour = date.getHours();
  
  // Use hourly baseline for more accurate detection
  const hourlyBaseline = velocityBaseline.hourly[hour];
  
  // If hourly data is sparse, fall back to overall
  if (hourlyBaseline.count < 5) {
    return detectDeviation(value, velocityBaseline.overall);
  }
  
  return detectDeviation(value, hourlyBaseline);
}

// ═══════════════════════════════════════════════════════════════════════════════
// BATCH ANALYSIS
// ═══════════════════════════════════════════════════════════════════════════════

export interface AnomalyReport {
  totalPoints: number;
  anomalies: number;
  criticalCount: number;
  highCount: number;
  elevatedCount: number;
  anomalyRate: number;
  worstDeviation: DeviationResult | null;
}

export function analyzeTimeSeries(
  timeSeries: TimeSeriesPoint[],
  baseline: VelocityBaseline
): AnomalyReport {
  const deviations = timeSeries.map(point => 
    detectTimeBasedDeviation(point.value, point.timestamp, baseline)
  );
  
  const anomalies = deviations.filter(d => d.isAnomaly);
  const criticalCount = deviations.filter(d => d.severity === 'critical').length;
  const highCount = deviations.filter(d => d.severity === 'high').length;
  const elevatedCount = deviations.filter(d => d.severity === 'elevated').length;
  
  // Find worst deviation
  let worstDeviation: DeviationResult | null = null;
  let maxZ = 0;
  
  deviations.forEach(d => {
    if (Math.abs(d.zScore) > maxZ) {
      maxZ = Math.abs(d.zScore);
      worstDeviation = d;
    }
  });
  
  return {
    totalPoints: timeSeries.length,
    anomalies: anomalies.length,
    criticalCount,
    highCount,
    elevatedCount,
    anomalyRate: timeSeries.length > 0 ? anomalies.length / timeSeries.length : 0,
    worstDeviation,
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// API HELPERS
// ═══════════════════════════════════════════════════════════════════════════════

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8007';

export async function fetchBaseline(walletAddress: string): Promise<VelocityBaseline | null> {
  try {
    const response = await fetch(`${API_BASE}/baseline/${walletAddress}`);
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchDeviations(
  walletAddress: string,
  fromTimestamp?: number,
  toTimestamp?: number
): Promise<DeviationResult[]> {
  try {
    const params = new URLSearchParams();
    if (fromTimestamp) params.set('from', fromTimestamp.toString());
    if (toTimestamp) params.set('to', toTimestamp.toString());
    
    const response = await fetch(`${API_BASE}/deviations/${walletAddress}?${params}`);
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}
