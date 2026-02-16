'use client';

/**
 * Velocity Heatmap Component
 * 
 * ECharts-based heatmap for temporal anomaly detection
 * Shows transaction velocity patterns across time (hour x day)
 * 
 * Used in War Room - Detection Studio
 * Cognitive Job: "Machine behavior" - velocity & time anomalies
 */

import React, { useMemo, useCallback } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface VelocityDataPoint {
  hour: number;      // 0-23
  day: number;       // 0-6 (Sunday-Saturday)
  velocity: number;  // Transactions per hour
  anomalyScore?: number;  // 0-1, optional anomaly indicator
}

export interface VelocityHeatmapProps {
  data: VelocityDataPoint[];
  title?: string;
  showAnomalies?: boolean;
  onCellClick?: (hour: number, day: number, velocity: number) => void;
  baselineThreshold?: number;
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

export default function VelocityHeatmap({
  data = [],
  title = 'Transaction Velocity',
  showAnomalies = true,
  onCellClick,
  baselineThreshold = 0.8,
  height = 400,
  darkMode = true,
}: VelocityHeatmapProps) {
  
  // Guard against empty or invalid data
  const safeData = Array.isArray(data) ? data : [];
  
  // Transform data for ECharts
  const chartData = useMemo(() => {
    return safeData.map(d => [d.hour, d.day, d.velocity, d.anomalyScore ?? 0]);
  }, [safeData]);
  
  // Calculate max velocity for scaling
  const maxVelocity = useMemo(() => {
    if (safeData.length === 0) return 1;
    return Math.max(...safeData.map(d => d.velocity), 1);
  }, [safeData]);

  // Calculate min velocity for better contrast
  const minVelocity = useMemo(() => {
    if (safeData.length === 0) return 0;
    return Math.min(...safeData.map(d => d.velocity), 0);
  }, [safeData]);
  
  // Detect anomalies (above baseline)
  const anomalyMarkers = useMemo(() => {
    if (!showAnomalies) return [];
    
    return safeData
      .filter(d => (d.anomalyScore ?? 0) > baselineThreshold)
      .map(d => ({
        coord: [d.hour, d.day],
        value: d.velocity,
        itemStyle: {
          borderColor: '#ef4444',
          borderWidth: 2,
          borderType: 'solid',
        },
      }));
  }, [safeData, showAnomalies, baselineThreshold]);
  
  // ECharts options (using type assertion to avoid strict type checking)
  const option = useMemo(() => ({
    title: {
      text: title,
      left: 'center',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
        fontSize: 16,
        fontWeight: 600,
      },
    },
    tooltip: {
      position: 'top',
      formatter: (params: any) => {
        // Guard against invalid data format
        if (!params || !params.data || !Array.isArray(params.data) || params.data.length < 3) {
          return 'No data available';
        }
        const hour = params.data[0] ?? 0;
        const day = params.data[1] ?? 0;
        const velocity = params.data[2] ?? 0;
        const anomaly = params.data[3] ?? 0;
        const dayName = DAYS[day] || 'Unknown';
        const hourName = HOURS[hour] || 'Unknown';
        const isAnomaly = anomaly > baselineThreshold;
        
        return `
          <div style="padding: 8px;">
            <div style="font-weight: 600; margin-bottom: 4px;">
              ${dayName} ${hourName}
            </div>
            <div style="color: ${isAnomaly ? '#ef4444' : '#10b981'};">
              Velocity: ${Number(velocity).toFixed(1)} tx/hr
            </div>
            ${isAnomaly ? `
              <div style="color: #ef4444; margin-top: 4px; font-size: 12px;">
                ⚠️ Anomaly detected (${(Number(anomaly) * 100).toFixed(0)}% confidence)
              </div>
            ` : ''}
          </div>
        `;
      },
      backgroundColor: darkMode ? '#1e293b' : '#ffffff',
      borderColor: darkMode ? '#334155' : '#e2e8f0',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
      },
    },
    grid: {
      top: 60,
      bottom: 100,
      left: 60,
      right: 40,
    },
    xAxis: {
      type: 'category',
      data: HOURS,
      name: 'Hour of Day',
      nameLocation: 'center',
      nameGap: 30,
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 11,
      },
      splitArea: { show: true },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 10,
        interval: 2,
        rotate: 45,
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
    },
    yAxis: {
      type: 'category',
      data: DAYS,
      name: 'Day',
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 11,
      },
      splitArea: { show: true },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 11,
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
    },
    visualMap: {
      min: minVelocity,
      max: maxVelocity,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 55,
      inRange: {
        color: darkMode 
          ? ['#0c4a6e', '#0369a1', '#0ea5e9', '#f59e0b', '#ef4444']
          : ['#e0f2fe', '#7dd3fc', '#38bdf8', '#fbbf24', '#f87171'],
      },
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
        markPoint: showAnomalies ? {
          symbol: 'pin',
          symbolSize: 28,
          data: anomalyMarkers,
          itemStyle: {
            color: '#ef4444',
            shadowBlur: 8,
            shadowColor: 'rgba(239, 68, 68, 0.5)',
          },
          label: {
            show: true,
            formatter: '!',
            color: '#fff',
            fontSize: 11,
            fontWeight: 'bold',
          },
        } : undefined,
      },
    ],
    dataZoom: [
      {
        type: 'slider',
        xAxisIndex: 0,
        start: 0,
        end: 100,
        bottom: 10,
        height: 15,
        borderColor: darkMode ? '#334155' : '#e2e8f0',
        backgroundColor: darkMode ? '#1e293b' : '#f8fafc',
        fillerColor: darkMode ? 'rgba(59, 130, 246, 0.3)' : 'rgba(59, 130, 246, 0.2)',
        handleStyle: {
          color: '#3b82f6',
        },
        textStyle: {
          color: darkMode ? '#94a3b8' : '#64748b',
        },
      },
    ],
  }), [chartData, minVelocity, maxVelocity, title, showAnomalies, anomalyMarkers, baselineThreshold, darkMode]);
  
  // Handle click events
  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (onCellClick && params?.data && Array.isArray(params.data) && params.data.length >= 3) {
        const hour = params.data[0] ?? 0;
        const day = params.data[1] ?? 0;
        const velocity = params.data[2] ?? 0;
        onCellClick(hour, day, velocity);
      }
    },
  }), [onCellClick]);
  
  return (
    <div className="w-full">
      <ReactECharts
        option={option}
        style={{ height }}
        opts={{ renderer: 'canvas' }}
        onEvents={onEvents}
        notMerge={true}
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Generate mock data for testing
// ═══════════════════════════════════════════════════════════════════════════════

export function generateMockVelocityData(): VelocityDataPoint[] {
  const data: VelocityDataPoint[] = [];
  
  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      // Base velocity with day/hour patterns
      let baseVelocity = 10;
      
      // Higher during business hours (9-17)
      if (hour >= 9 && hour <= 17) baseVelocity += 20;
      
      // Higher on weekdays
      if (day >= 1 && day <= 5) baseVelocity += 15;
      
      // Random variation
      const velocity = baseVelocity + Math.random() * 10;
      
      // Inject some anomalies
      const isAnomaly = Math.random() < 0.05;
      const anomalyMultiplier = isAnomaly ? 3 + Math.random() * 2 : 1;
      
      data.push({
        hour,
        day,
        velocity: velocity * anomalyMultiplier,
        anomalyScore: isAnomaly ? 0.85 + Math.random() * 0.15 : Math.random() * 0.3,
      });
    }
  }
  
  return data;
}
