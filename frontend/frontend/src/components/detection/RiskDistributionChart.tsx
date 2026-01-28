'use client';

/**
 * Risk Distribution Chart Component
 * 
 * ECharts-based distribution visualization
 * 
 * Used in War Room - Detection Studio
 * Cognitive Job: Statistical context - risk score evolution
 */

import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface DistributionBucket {
  range: string;
  rangeStart: number;
  rangeEnd: number;
  count: number;
  percentage?: number;
}

export interface RiskDistributionChartProps {
  data: DistributionBucket[];
  title?: string;
  xAxisLabel?: string;
  showPercentage?: boolean;
  thresholds?: { value: number; label: string; color: string }[];
  height?: string | number;
  darkMode?: boolean;
  onBarClick?: (bucket: DistributionBucket) => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function RiskDistributionChart({
  data,
  title = 'Risk Score Distribution',
  xAxisLabel = 'Risk Score',
  showPercentage = false,
  thresholds = [
    { value: 0.3, label: 'Low Risk', color: '#10b981' },
    { value: 0.7, label: 'Medium Risk', color: '#f59e0b' },
    { value: 1.0, label: 'High Risk', color: '#ef4444' },
  ],
  height = 350,
  darkMode = true,
  onBarClick,
}: RiskDistributionChartProps) {
  
  // Calculate total for percentages
  const total = useMemo(() => data.reduce((sum, d) => sum + d.count, 0), [data]);
  
  // Determine bar color based on risk range
  const getBarColor = (rangeStart: number, rangeEnd: number) => {
    const midpoint = (rangeStart + rangeEnd) / 2;
    
    for (let i = 0; i < thresholds.length; i++) {
      if (midpoint <= thresholds[i].value) {
        return thresholds[i].color;
      }
    }
    return thresholds[thresholds.length - 1].color;
  };
  
  // ECharts options
  const option: EChartsOption = useMemo(() => ({
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
      trigger: 'axis',
      axisPointer: {
        type: 'shadow',
      },
      backgroundColor: darkMode ? '#1e293b' : '#ffffff',
      borderColor: darkMode ? '#334155' : '#e2e8f0',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
      },
      formatter: (params: any) => {
        const p = params[0];
        const bucket = data[p.dataIndex];
        const pct = total > 0 ? ((bucket.count / total) * 100).toFixed(1) : 0;
        return `
          <div style="padding: 4px;">
            <div style="font-weight: 600;">${bucket.range}</div>
            <div>Count: ${bucket.count.toLocaleString()}</div>
            <div>Percentage: ${pct}%</div>
          </div>
        `;
      },
    },
    grid: {
      top: 60,
      bottom: 60,
      left: 60,
      right: 30,
    },
    xAxis: {
      type: 'category',
      data: data.map(d => d.range),
      name: xAxisLabel,
      nameLocation: 'center',
      nameGap: 35,
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        rotate: 45,
      },
    },
    yAxis: {
      type: 'value',
      name: showPercentage ? 'Percentage (%)' : 'Count',
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        formatter: showPercentage ? '{value}%' : '{value}',
      },
      splitLine: {
        lineStyle: {
          color: darkMode ? '#1e293b' : '#f1f5f9',
        },
      },
    },
    series: [
      {
        name: 'Distribution',
        type: 'bar',
        data: data.map((d, i) => ({
          value: showPercentage ? (d.count / total) * 100 : d.count,
          itemStyle: {
            color: getBarColor(d.rangeStart, d.rangeEnd),
            borderRadius: [4, 4, 0, 0],
          },
        })),
        barWidth: '60%',
        emphasis: {
          itemStyle: {
            shadowBlur: 10,
            shadowColor: 'rgba(0, 0, 0, 0.3)',
          },
        },
      },
    ],
    // Threshold lines
    markLine: thresholds.length > 0 ? {
      silent: true,
      symbol: 'none',
      data: thresholds.slice(0, -1).map(t => ({
        xAxis: t.value * 10 - 0.5,
        lineStyle: {
          color: t.color,
          type: 'dashed',
          width: 2,
        },
        label: {
          formatter: t.label,
          color: t.color,
        },
      })),
    } : undefined,
  }), [data, title, xAxisLabel, showPercentage, thresholds, total, darkMode]);
  
  // Handle click events
  const onEvents = useMemo(() => ({
    click: (params: any) => {
      if (onBarClick && params.dataIndex !== undefined) {
        onBarClick(data[params.dataIndex]);
      }
    },
  }), [onBarClick, data]);
  
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
      <div className={`mt-2 flex justify-center gap-6 text-sm ${
        darkMode ? 'text-slate-400' : 'text-gray-600'
      }`}>
        {thresholds.map((t, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ backgroundColor: t.color }} />
            <span>{t.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER: Generate mock data
// ═══════════════════════════════════════════════════════════════════════════════

export function generateMockDistributionData(): DistributionBucket[] {
  const buckets: DistributionBucket[] = [];
  
  // Generate 10 buckets (0.0-0.1, 0.1-0.2, etc.)
  for (let i = 0; i < 10; i++) {
    const rangeStart = i / 10;
    const rangeEnd = (i + 1) / 10;
    
    // Beta-like distribution - more low risk, fewer high risk
    const baseCount = Math.floor(1000 * Math.pow(1 - rangeStart, 2));
    const noise = Math.floor(Math.random() * 50);
    
    buckets.push({
      range: `${(rangeStart * 100).toFixed(0)}-${(rangeEnd * 100).toFixed(0)}`,
      rangeStart,
      rangeEnd,
      count: baseCount + noise,
    });
  }
  
  return buckets;
}
