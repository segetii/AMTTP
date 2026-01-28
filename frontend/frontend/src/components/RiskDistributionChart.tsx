'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import type { DashboardStats } from '@/types/siem';

interface RiskDistributionChartProps {
  stats: DashboardStats | null;
}

export function RiskDistributionChart({ stats }: RiskDistributionChartProps) {
  if (!stats) {
    return (
      <div className="h-[250px] flex items-center justify-center text-gray-500">
        Loading...
      </div>
    );
  }

  const rawData = [
    { name: 'Critical', value: stats.criticalAlerts ?? 0, color: '#ef4444' },
    { name: 'High', value: stats.highAlerts ?? 0, color: '#f97316' },
    { name: 'Medium', value: stats.mediumAlerts ?? 0, color: '#eab308' },
    { name: 'Low', value: stats.lowAlerts ?? 0, color: '#22c55e' },
  ];

  const data = rawData.filter(d => (d.value ?? 0) > 0);
  const severityTotal = rawData.reduce((sum, d) => sum + (d.value ?? 0), 0);
  const total = stats.totalAlerts ?? severityTotal;

  if (severityTotal === 0) {
    return (
      <div className="h-[250px] flex items-center justify-center text-gray-500 bg-gray-900/40 rounded-lg">
        <span>No risk distribution data available yet.</span>
      </div>
    );
  }

  const containerStyle = { minWidth: 240, minHeight: 250 } as const;

  return (
    <div className="h-[250px] relative" style={containerStyle}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={90}
            paddingAngle={2}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
            }}
            formatter={(value, name) => [
              `${value} (${((Number(value) / total) * 100).toFixed(1)}%)`,
              name
            ]}
          />
          <Legend
            verticalAlign="bottom"
            iconType="circle"
            iconSize={10}
            formatter={(value, entry) => (
              <span className="text-gray-300 text-sm">
                {value}: {entry.payload?.value ?? 0}
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Quick legend summary for clarity */}
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-gray-300">
        <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full inline-block" style={{ background: '#ef4444' }} /> Critical: {rawData[0].value}</div>
        <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full inline-block" style={{ background: '#f97316' }} /> High: {rawData[1].value}</div>
        <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full inline-block" style={{ background: '#eab308' }} /> Medium: {rawData[2].value}</div>
        <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full inline-block" style={{ background: '#22c55e' }} /> Low: {rawData[3].value}</div>
      </div>
    </div>
  );
}
