'use client';

/**
 * Time Series Chart Component
 * 
 * ECharts-based time series visualization with dataZoom
 * 
 * Used in War Room - Detection Studio
 * Cognitive Job: Temporal anomaly detection, baseline vs deviation
 */

import React, { useMemo } from 'react';
import ReactECharts from 'echarts-for-react';

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export interface TimeSeriesDataPoint {
  timestamp: number;
  value: number;
  baseline?: number;
  upperBound?: number;
  lowerBound?: number;
  isAnomaly?: boolean;
}

export interface TimeSeriesChartProps {
  data: TimeSeriesDataPoint[];
  title?: string;
  yAxisLabel?: string;
  showBaseline?: boolean;
  showBounds?: boolean;
  showAnomalies?: boolean;
  height?: string | number;
  darkMode?: boolean;
  onBrushSelect?: (startTime: number, endTime: number) => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function TimeSeriesChart({
  data,
  title = 'Time Series Analysis',
  yAxisLabel = 'Value',
  showBaseline = true,
  showBounds = true,
  showAnomalies = true,
  height = 400,
  darkMode = true,
  onBrushSelect,
}: TimeSeriesChartProps) {
  
  // Extract series data
  const seriesData = useMemo(() => {
    return {
      timestamps: data.map(d => d.timestamp),
      values: data.map(d => [d.timestamp, d.value]),
      baseline: data.map(d => [d.timestamp, d.baseline ?? null]),
      upperBound: data.map(d => [d.timestamp, d.upperBound ?? null]),
      lowerBound: data.map(d => [d.timestamp, d.lowerBound ?? null]),
      anomalies: data.filter(d => d.isAnomaly).map(d => ({
        coord: [d.timestamp, d.value],
        value: d.value,
      })),
    };
  }, [data]);
  
  // ECharts options
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
      trigger: 'axis',
      axisPointer: {
        type: 'cross',
        animation: false,
        label: {
          backgroundColor: darkMode ? '#1e293b' : '#ffffff',
        },
      },
      backgroundColor: darkMode ? '#1e293b' : '#ffffff',
      borderColor: darkMode ? '#334155' : '#e2e8f0',
      textStyle: {
        color: darkMode ? '#e2e8f0' : '#1e293b',
      },
      formatter: (params: unknown) => {
        if (!Array.isArray(params)) return '';
        const first = params[0] as { value: [number, number] } | undefined;
        if (!first) return '';
        const time = new Date(first.value[0]).toLocaleString();
        let html = `<div style="font-weight: 600; margin-bottom: 4px;">${time}</div>`;
        params.forEach((p) => {
          const point = p as { marker?: string; seriesName?: string; value: [number, number] };
          if (point.value[1] !== null && point.value[1] !== undefined) {
            html += `<div>${point.marker ?? ''} ${point.seriesName ?? ''}: ${point.value[1].toFixed(2)}</div>`;
          }
        });
        return html;
      },
    },
    legend: {
      data: [
        'Value',
        showBaseline && 'Baseline',
        showBounds && 'Upper Bound',
        showBounds && 'Lower Bound',
      ].filter(Boolean) as string[],
      top: 30,
      textStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
    },
    grid: {
      top: 80,
      bottom: 80,
      left: 60,
      right: 40,
    },
    xAxis: {
      type: 'time',
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
        formatter: (value: number) => {
          const date = new Date(value);
          return `${date.getMonth() + 1}/${date.getDate()}\n${date.getHours()}:00`;
        },
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: darkMode ? '#1e293b' : '#f1f5f9',
        },
      },
    },
    yAxis: {
      type: 'value',
      name: yAxisLabel,
      nameTextStyle: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
      axisLine: {
        lineStyle: { color: darkMode ? '#334155' : '#e2e8f0' },
      },
      axisLabel: {
        color: darkMode ? '#94a3b8' : '#64748b',
      },
      splitLine: {
        lineStyle: {
          color: darkMode ? '#1e293b' : '#f1f5f9',
        },
      },
    },
    dataZoom: [
      {
        type: 'slider',
        xAxisIndex: 0,
        start: 0,
        end: 100,
        bottom: 20,
        height: 30,
        borderColor: darkMode ? '#334155' : '#e2e8f0',
        backgroundColor: darkMode ? '#1e293b' : '#f8fafc',
        fillerColor: darkMode ? 'rgba(59, 130, 246, 0.3)' : 'rgba(59, 130, 246, 0.2)',
        handleStyle: {
          color: '#3b82f6',
        },
        textStyle: {
          color: darkMode ? '#94a3b8' : '#64748b',
        },
        dataBackground: {
          lineStyle: { color: '#3b82f6' },
          areaStyle: { color: darkMode ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.1)' },
        },
      },
      {
        type: 'inside',
        xAxisIndex: 0,
        start: 0,
        end: 100,
      },
    ],
    toolbox: {
      feature: {
        dataZoom: {
          yAxisIndex: 'none',
        },
        restore: {},
        saveAsImage: {},
      },
      iconStyle: {
        borderColor: darkMode ? '#94a3b8' : '#64748b',
      },
      right: 20,
      top: 5,
    },
    brush: onBrushSelect ? {
      toolbox: ['lineX', 'clear'],
      xAxisIndex: 0,
    } : undefined,
    series: [
      // Main value line
      {
        name: 'Value',
        type: 'line',
        data: seriesData.values,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: '#3b82f6',
          width: 2,
        },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(59, 130, 246, 0.3)' },
              { offset: 1, color: 'rgba(59, 130, 246, 0.05)' },
            ],
          },
        },
        markPoint: showAnomalies ? {
          symbol: 'circle',
          symbolSize: 10,
          data: seriesData.anomalies,
          itemStyle: {
            color: '#ef4444',
          },
          label: {
            show: false,
          },
        } : undefined,
      },
      // Baseline
      showBaseline && {
        name: 'Baseline',
        type: 'line',
        data: seriesData.baseline,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: '#10b981',
          width: 1,
          type: 'dashed',
        },
      },
      // Upper bound
      showBounds && {
        name: 'Upper Bound',
        type: 'line',
        data: seriesData.upperBound,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: '#f59e0b',
          width: 1,
          type: 'dotted',
        },
      },
      // Lower bound
      showBounds && {
        name: 'Lower Bound',
        type: 'line',
        data: seriesData.lowerBound,
        smooth: true,
        symbol: 'none',
        lineStyle: {
          color: '#f59e0b',
          width: 1,
          type: 'dotted',
        },
      },
  ].filter(Boolean) as unknown[],
  }), [seriesData, title, yAxisLabel, showBaseline, showBounds, showAnomalies, darkMode, onBrushSelect]);
  
  // Handle brush selection
  const onEvents = useMemo(() => ({
    brushSelected: (params: unknown) => {
      if (!onBrushSelect || typeof params !== 'object' || params === null) return;
      const batch = (params as { batch?: Array<{ areas?: Array<{ coordRange?: [number, number] }> }> }).batch;
      const area = batch?.[0]?.areas?.[0];
      if (area?.coordRange) {
        onBrushSelect(area.coordRange[0], area.coordRange[1]);
      }
    },
  }), [onBrushSelect]);
  
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
// HELPER: Generate mock data
// ═══════════════════════════════════════════════════════════════════════════════

export function generateMockTimeSeriesData(days: number = 7): TimeSeriesDataPoint[] {
  const data: TimeSeriesDataPoint[] = [];
  const now = Date.now();
  const hourMs = 3600000;
  
  for (let i = days * 24; i >= 0; i--) {
    const timestamp = now - i * hourMs;
    const hour = new Date(timestamp).getHours();
    
    // Base pattern with day/night cycle
    const baseline = 50 + 30 * Math.sin((hour - 6) * Math.PI / 12);
    const noise = (Math.random() - 0.5) * 20;
    const value = baseline + noise;
    
    // Inject some anomalies
    const isAnomaly = Math.random() < 0.03;
    const anomalyMultiplier = isAnomaly ? 1.5 + Math.random() : 1;
    
    data.push({
      timestamp,
      value: value * anomalyMultiplier,
      baseline,
      upperBound: baseline + 25,
      lowerBound: baseline - 25,
      isAnomaly: isAnomaly || value * anomalyMultiplier > baseline + 25,
    });
  }
  
  return data;
}
