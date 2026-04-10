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
  showAnomalies = false,
  onCellClick,
  baselineThreshold = 0.8,
  height = 400,
  darkMode = true,
}: VelocityHeatmapProps) {
  
  // Guard against empty or invalid data
  const safeData = Array.isArray(data) ? data : [];
  
  // Transform data for ECharts - use sqrt for visual value to spread skewed data across colors
  // Format: [hour, day, sqrtVelocity, anomalyScore, rawVelocity]
  const chartData = useMemo(() => {
    return safeData.map(d => [d.hour, d.day, Math.sqrt(d.velocity), d.anomalyScore ?? 0, d.velocity]);
  }, [safeData]);
  
  // Calculate max velocity for scaling (use sqrt scale to match data transform)
  const maxVelocity = useMemo(() => {
    if (safeData.length === 0) return 1;
    return Math.sqrt(Math.max(...safeData.map(d => d.velocity), 1));
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
        if (!params || !params.data) return 'No data available';

        // markPoint items have { coord, value } instead of array
        if (params.componentType === 'markPoint' || params.data.coord) {
          const coord = params.data.coord || [0, 0];
          const hour = coord[0] ?? 0;
          const day = coord[1] ?? 0;
          const velocity = params.data.value ?? 0;
          const dayName = DAYS[day] || 'Unknown';
          const hourName = HOURS[hour] || 'Unknown';
          return `
            <div style="padding: 8px;">
              <div style="font-weight: 600; margin-bottom: 4px;">
                ${dayName} ${hourName}
              </div>
              <div style="color: #ef4444;">
                Velocity: ${Number(velocity).toFixed(0)} tx/hr
              </div>
              <div style="color: #ef4444; margin-top: 4px; font-size: 12px;">
                ⚠️ Anomalous activity detected
              </div>
            </div>
          `;
        }

        // Heatmap cells: [hour, day, sqrtVelocity, anomalyScore, rawVelocity]
        if (!Array.isArray(params.data) || params.data.length < 5) {
          return 'No data available';
        }
        const hour = params.data[0] ?? 0;
        const day = params.data[1] ?? 0;
        const anomaly = params.data[3] ?? 0;
        const velocity = params.data[4] ?? 0;
        const dayName = DAYS[day] || 'Unknown';
        const hourName = HOURS[hour] || 'Unknown';
        const isAnomaly = anomaly > baselineThreshold;
        
        return `
          <div style="padding: 8px;">
            <div style="font-weight: 600; margin-bottom: 4px;">
              ${dayName} ${hourName}
            </div>
            <div style="color: ${isAnomaly ? '#ef4444' : '#10b981'};">
              Velocity: ${Number(velocity).toFixed(0)} tx/hr
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
      top: 50,
      bottom: 30,
      left: 60,
      right: 120,
    },
    xAxis: {
      type: 'category',
      data: HOURS,
      name: 'Hour of Day',
      nameLocation: 'center',
      nameGap: 25,
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 11,
      },
      splitArea: { show: true },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        fontSize: 10,
        interval: 2,
        rotate: 0,
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
      type: 'continuous',
      min: 0,
      max: maxVelocity,
      dimension: 2,
      calculable: false,
      orient: 'vertical',
      right: 10,
      top: 50,
      bottom: 30,
      itemWidth: 14,
      itemHeight: undefined,
      text: ['Anomalous', 'Quiet'],
      inRange: {
        color: darkMode
          ? ['#1e3a5f', '#0d9488', '#10b981', '#84cc16', '#eab308', '#f97316', '#ef4444']
          : ['#ecfdf5', '#99f6e4', '#6ee7b7', '#bef264', '#fde047', '#fdba74', '#fca5a5'],
      },
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
        fontSize: 11,
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
  }), [chartData, maxVelocity, title, showAnomalies, anomalyMarkers, baselineThreshold, darkMode]);
  
  // Handle click events
  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (onCellClick && params?.data && Array.isArray(params.data) && params.data.length >= 5) {
        const hour = params.data[0] ?? 0;
        const day = params.data[1] ?? 0;
        const velocity = params.data[4] ?? 0;
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
        notMerge={false}
        lazyUpdate={true}
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
