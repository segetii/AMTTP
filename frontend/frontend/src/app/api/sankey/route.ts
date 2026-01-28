/**
 * Sankey Flow Data API
 * 
 * Fetches value flow data for Sankey visualization
 * Priority:
 * 1. Try to fetch from backend orchestrator (which queries Memgraph)
 * 2. Fall back to static JSON data file
 * 3. Generate sample data as last resort
 */

import { NextRequest, NextResponse } from 'next/server';

// Backend service URL
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'http://localhost:8007';

interface SankeyNode {
  id: string;
  label: string;
  type: 'source' | 'intermediate' | 'sink' | 'mixer' | 'exchange';
  riskLevel?: 'low' | 'medium' | 'high' | 'critical';
  address?: string;
}

interface SankeyLink {
  source: string;
  target: string;
  value: number;
  count?: number;
  isAnomaly?: boolean;
}

export async function GET(request: NextRequest) {
  try {
    // Try to fetch from backend orchestrator first
    const backendData = await fetchFromBackend();
    
    if (backendData && backendData.nodes.length > 0) {
      return NextResponse.json(backendData);
    }
    
    // Fallback to static data file
    const staticData = await fetchStaticData();
    if (staticData && staticData.links.length > 0) {
      return NextResponse.json(staticData);
    }
    
    // Generate realistic sample data
    return NextResponse.json(generateSampleData());
    
  } catch (error) {
    console.error('Sankey API error:', error);
    return NextResponse.json(generateSampleData());
  }
}

async function fetchFromBackend(): Promise<{ nodes: SankeyNode[], links: SankeyLink[] } | null> {
  try {
    // Try the orchestrator's sankey endpoint
    const response = await fetch(`${ORCHESTRATOR_URL}/sankey-flow`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      // Short timeout to fail fast
      signal: AbortSignal.timeout(2000),
    });
    
    if (response.ok) {
      return await response.json();
    }
    return null;
  } catch (error) {
    console.log('Backend sankey endpoint not available, using fallback');
    return null;
  }
}

async function fetchStaticData(): Promise<{ nodes: SankeyNode[], links: SankeyLink[] }> {
  try {
    // Try to read from generated data file
    const fs = await import('fs/promises');
    const path = await import('path');
    
    const dataPath = path.join(process.cwd(), 'src', 'data', 'sankeyFlowData.json');
    const data = await fs.readFile(dataPath, 'utf-8');
    const parsed = JSON.parse(data);
    
    // Transform to proper format if needed
    const nodes: SankeyNode[] = parsed.nodes.map((n: any) => ({
      id: n.id,
      label: n.label,
      type: n.id === 'low' ? 'source' : 
            n.id === 'critical' ? 'sink' : 'intermediate',
      riskLevel: n.id as any,
    }));
    
    const links: SankeyLink[] = parsed.links.map((l: any) => ({
      source: l.source,
      target: l.target,
      value: l.value || 1,
      count: l.count || 1,
      isAnomaly: l.source === 'critical' || l.target === 'critical',
    }));
    
    // If links are empty, generate sample links
    if (links.length === 0) {
      return generateSampleData();
    }
    
    return { nodes, links };
    
  } catch (error) {
    console.error('Static data fetch error:', error);
    return generateSampleData();
  }
}

function generateSampleData(): { nodes: SankeyNode[], links: SankeyLink[] } {
  // Generate realistic sample data based on typical transaction patterns
  const nodes: SankeyNode[] = [
    { id: 'exchange-a', label: 'Exchange A', type: 'exchange', riskLevel: 'low' },
    { id: 'exchange-b', label: 'Exchange B', type: 'exchange', riskLevel: 'low' },
    { id: 'defi-pool', label: 'DeFi Pool', type: 'intermediate', riskLevel: 'medium' },
    { id: 'wallet-1', label: 'Hot Wallet 1', type: 'intermediate', riskLevel: 'low' },
    { id: 'wallet-2', label: 'Hot Wallet 2', type: 'intermediate', riskLevel: 'medium' },
    { id: 'mixer', label: 'Suspected Mixer', type: 'mixer', riskLevel: 'high' },
    { id: 'cold-storage', label: 'Cold Storage', type: 'sink', riskLevel: 'low' },
    { id: 'flagged', label: 'Flagged Wallet', type: 'sink', riskLevel: 'critical' },
  ];

  const links: SankeyLink[] = [
    { source: 'exchange-a', target: 'wallet-1', value: 150.5, count: 45 },
    { source: 'exchange-a', target: 'defi-pool', value: 280.2, count: 23 },
    { source: 'exchange-b', target: 'wallet-2', value: 95.8, count: 31 },
    { source: 'wallet-1', target: 'defi-pool', value: 75.3, count: 12 },
    { source: 'wallet-1', target: 'cold-storage', value: 50.2, count: 8 },
    { source: 'wallet-2', target: 'mixer', value: 45.1, count: 15, isAnomaly: true },
    { source: 'defi-pool', target: 'wallet-2', value: 180.5, count: 34 },
    { source: 'defi-pool', target: 'cold-storage', value: 120.8, count: 19 },
    { source: 'mixer', target: 'flagged', value: 42.3, count: 7, isAnomaly: true },
    { source: 'mixer', target: 'exchange-b', value: 25.6, count: 5, isAnomaly: true },
  ];

  return { nodes, links };
}
