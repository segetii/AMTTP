'use client';

/**
 * Enhanced Velocity Heatmap with Baseline Comparison
 * 
 * Ground Truth Reference:
 * - Netflix-style grid: Each square = 1 hour
 * - Color = deviation vs 30-day baseline
 * - Used to confirm automation/bot behavior
 * 
 * Features:
 * - Baseline overlay (ghosted)
 * - Z-score tooltips
 * - Anomaly annotations
 */

import React, { useMemo, useCallback, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { 
  VelocityBaseline, 
  DeviationResult, 
  detectDeviation,
  calculateBaselineStats,
} from '@/lib/baseline-service';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface VelocityDataPoint {
  hour: number;      // 0-23
  day: number;       // 0-6 (Sunday-Saturday)
  value: number;     // Actual transaction count
  baseline?: number; // Expected from baseline
  zScore?: number;   // Deviation from baseline
}

export interface BaselineVelocityHeatmapProps {
  data: VelocityDataPoint[];
  baseline?: VelocityBaseline;
  title?: string;
  showBaseline?: boolean;
  showZScores?: boolean;
  onCellClick?: (hour: number, day: number, deviation: DeviationResult) => void;
  height?: string | number;
  darkMode?: boolean;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const HOURS = Array.from({ length: 24 }, (_, i) => 
  i === 0 ? '12am' : i < 12 ? `${i}am` : i === 12 ? '12pm' : `${i - 12}pm`
);

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function BaselineVelocityHeatmap({
  data,
  baseline,
  title = 'Velocity vs Baseline',
  showBaseline = true,
  showZScores = true,
  onCellClick,
  height = 400,
  darkMode = true,
}: BaselineVelocityHeatmapProps) {
  const [hoveredCell, setHoveredCell] = useState<{ hour: number; day: number } | null>(null);
  
  // Calculate deviations from baseline
  const deviationData = useMemo(() => {
    return data.map(point => {
      if (!baseline) {
        return { ...point, deviation: null };
      }
      
      // Get baseline for this hour
      const hourBaseline = baseline.hourly[point.hour];
      const deviation = detectDeviation(point.value, hourBaseline);
      
      return {
        ...point,
        baseline: hourBaseline.mean,
        zScore: deviation.zScore,
        deviation,
      };
    });
  }, [data, baseline]);
  
  // Process data for ECharts
  const chartData = useMemo(() => {
    return deviationData.map(d => {
      // Color based on z-score (deviation from baseline)
      const zScore = d.zScore ?? 0;
      return [d.hour, d.day, d.value, zScore, d.baseline ?? d.value];
    });
  }, [deviationData]);
  
  // Find max for scaling
  const maxValue = useMemo(() => {
    return Math.max(...data.map(d => d.value), 1);
  }, [data]);
  
  // Color function based on z-score
  const getZScoreColor = (zScore: number) => {
    const absZ = Math.abs(zScore);
    if (absZ >= 4) return '#7c3aed'; // Critical - purple
    if (absZ >= 3) return '#ef4444'; // High - red
    if (absZ >= 2) return '#f59e0b'; // Elevated - amber
    if (absZ >= 1) return '#10b981'; // Normal elevated - green
    return '#3b82f6'; // Normal - blue
  };
  
  // ECharts options
  const option = useMemo(() => ({
    title: {
      text: title,
      subtext: baseline ? 'Color indicates deviation from 30-day baseline' : 'Raw velocity data',
      left: 'center',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
        fontSize: 16,
        fontWeight: 600,
      },
      subtextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 12,
      },
    },
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        const [hour, day, value, zScore, baselineVal] = params.data;
        const dayName = DAYS[day];
        const hourLabel = HOURS[hour];
        
        let html = `
          <div style="padding: 8px; min-width: 180px;">
            <div style="font-weight: 600; margin-bottom: 8px;">${dayName} @ ${hourLabel}</div>
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span>Actual:</span>
              <span style="font-weight: 600;">${value.toFixed(0)} tx</span>
            </div>
        `;
        
        if (baseline && showBaseline) {
          html += `
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span>Baseline:</span>
              <span style="color: #94a3b8;">${baselineVal.toFixed(1)} tx</span>
            </div>
          `;
        }
        
        if (showZScores && zScore !== undefined) {
          const absZ = Math.abs(zScore);
          const severity = absZ >= 4 ? 'CRITICAL' : absZ >= 3 ? 'HIGH' : absZ >= 2 ? 'ELEVATED' : 'NORMAL';
          const color = getZScoreColor(zScore);
          
          html += `
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
              <span>Z-Score:</span>
              <span style="color: ${color}; font-weight: 600;">${zScore.toFixed(2)}σ</span>
            </div>
            <div style="display: flex; justify-content: space-between;">
              <span>Status:</span>
              <span style="color: ${color}; font-weight: 600;">${severity}</span>
            </div>
          `;
        }
        
        html += '</div>';
        return html;
      },
      backgroundColor: darkMode ? '#1e293b' : '#ffffff',
      borderColor: darkMode ? '#334155' : '#e2e8f0',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
      },
    },
    grid: {
      top: 80,
      bottom: 80,
      left: 60,
      right: 40,
    },
    xAxis: {
      type: 'category',
      data: HOURS,
      splitArea: { show: true },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        rotate: 45,
        fontSize: 10,
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
    },
    yAxis: {
      type: 'category',
      data: DAYS,
      splitArea: { show: true },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
    },
    visualMap: {
      show: true,
      min: -4,
      max: 4,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 10,
      dimension: 3, // Use z-score for color
      inRange: {
        color: [
          '#3b82f6',  // -4: Below normal (blue)
          '#10b981',  // -2: Slightly below (green)
          '#22c55e',  // 0: Normal (bright green)
          '#f59e0b',  // +2: Elevated (amber)
          '#ef4444',  // +3: High (red)
          '#7c3aed',  // +4: Critical (purple)
        ],
      },
      text: ['+4σ', '-4σ'],
      textStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
    },
    series: [
      {
        name: 'Velocity',
        type: 'heatmap',
        data: chartData,
        label: {
          show: false,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.5)',
          },
        },
      },
    ],
    dataZoom: [
      {
        type: 'inside',
        xAxisIndex: 0,
        filterMode: 'none',
      },
    ],
  }), [chartData, title, baseline, showBaseline, showZScores, darkMode]);
  
  // Handle click events
  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (onCellClick && params.data) {
        const [hour, day] = params.data;
        const point = deviationData.find(d => d.hour === hour && d.day === day);
        if (point?.deviation) {
          onCellClick(hour, day, point.deviation);
        }
      }
    },
  }), [onCellClick, deviationData]);
  
  return (
    <div className="w-full">
      <ReactECharts
        option={option}
        style={{ height }}
        opts={{ renderer: 'canvas' }}
        onEvents={onEvents}
        notMerge={true}
      />
      
      {/* Legend */}
      <div className={`mt-4 flex flex-wrap justify-center gap-4 text-xs ${
        darkMode ? 'text-slate-400' : 'text-gray-600'
      }`}>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#3b82f6' }} />
          <span>Below Normal</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#22c55e' }} />
          <span>Normal</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#f59e0b' }} />
          <span>Elevated (2σ+)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#ef4444' }} />
          <span>High (3σ+)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: '#7c3aed' }} />
          <span>Critical (4σ+)</span>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Generate mock data with baseline
// ═══════════════════════════════════════════════════════════════════════════════

export function generateMockBaselineData(): {
  current: VelocityDataPoint[];
  baseline: VelocityBaseline;
} {
  // Generate baseline (historical averages)
  const hourlyBaselines = Array.from({ length: 24 }, (_, hour) => {
    // Higher during business hours
    let baseMean = 15;
    if (hour >= 9 && hour <= 17) baseMean = 45;
    if (hour >= 22 || hour <= 5) baseMean = 5;
    
    return {
      mean: baseMean,
      stdDev: baseMean * 0.3,
      min: baseMean * 0.2,
      max: baseMean * 2,
      count: 30,
      period: '30d',
    };
  });
  
  const dailyBaselines = Array.from({ length: 7 }, (_, day) => {
    // Lower on weekends
    const baseMean = (day === 0 || day === 6) ? 20 : 35;
    return {
      mean: baseMean,
      stdDev: baseMean * 0.25,
      min: baseMean * 0.3,
      max: baseMean * 1.8,
      count: 30,
      period: '30d',
    };
  });
  
  const baseline: VelocityBaseline = {
    hourly: hourlyBaselines,
    daily: dailyBaselines,
    overall: {
      mean: 25,
      stdDev: 15,
      min: 0,
      max: 100,
      count: 720,
      period: '30d',
    },
  };
  
  // Generate current data with some anomalies
  const current: VelocityDataPoint[] = [];
  
  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      const baseValue = hourlyBaselines[hour].mean;
      const stdDev = hourlyBaselines[hour].stdDev;
      
      // Random normal variation
      let value = baseValue + (Math.random() - 0.5) * stdDev * 2;
      
      // Inject some anomalies
      if (Math.random() < 0.08) {
        // 8% chance of anomaly
        const anomalyMultiplier = 2 + Math.random() * 3; // 2x to 5x
        value = baseValue * anomalyMultiplier;
      }
      
      current.push({
        hour,
        day,
        value: Math.max(0, Math.round(value)),
      });
    }
  }
  
  return { current, baseline };
}
