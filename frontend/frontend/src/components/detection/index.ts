/**
 * Detection Components Index
 * 
 * Exports all Detection Studio visualization components
 * 
 * Visualization Stack (Ground Truth):
 * - ECharts: Time series, distributions, heatmaps
 * - Canvas 2D: Network graphs (ForceGraph2D – no WebGL)
 * - Unovis: Sankey diagrams
 */

// ECharts-based components
export { default as VelocityHeatmap, generateMockVelocityData } from './VelocityHeatmap';
export type { VelocityDataPoint, VelocityHeatmapProps } from './VelocityHeatmap';

export { default as TimeSeriesChart, generateMockTimeSeriesData } from './TimeSeriesChart';
export type { TimeSeriesDataPoint, TimeSeriesChartProps } from './TimeSeriesChart';

export { default as RiskDistributionChart, generateMockDistributionData } from './RiskDistributionChart';
export type { DistributionBucket, RiskDistributionChartProps } from './RiskDistributionChart';

// Canvas 2D force-directed graph (replaced reagraph WebGL)
export { default as GraphExplorer, generateMockGraphData } from './GraphExplorer';
export { default as ForceGraph2D } from './ForceGraph2D';

// Unovis-based components
export { default as SankeyAuditor, generateMockSankeyData } from './SankeyAuditor';
