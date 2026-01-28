/**
 * Detection Components Index
 * 
 * Exports all Detection Studio visualization components
 * 
 * Visualization Stack (Ground Truth):
 * - ECharts: Time series, distributions, heatmaps
 * - Reagraph: Network graphs (WebGL)
 * - Unovis: Sankey diagrams
 */

// ECharts-based components
export { default as VelocityHeatmap, generateMockVelocityData } from './VelocityHeatmap';
export type { VelocityDataPoint, VelocityHeatmapProps } from './VelocityHeatmap';

export { default as TimeSeriesChart, generateMockTimeSeriesData } from './TimeSeriesChart';
export type { TimeSeriesDataPoint, TimeSeriesChartProps } from './TimeSeriesChart';

export { default as RiskDistributionChart, generateMockDistributionData } from './RiskDistributionChart';
export type { DistributionBucket, RiskDistributionChartProps } from './RiskDistributionChart';

// Reagraph-based components
export { default as GraphExplorer, generateMockGraphData } from './GraphExplorer';

// Unovis-based components
export { default as SankeyAuditor, generateMockSankeyData } from './SankeyAuditor';
