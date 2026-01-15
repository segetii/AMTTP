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

  const data = [
    { name: 'Critical', value: stats.criticalAlerts, color: '#ef4444' },
    { name: 'High', value: stats.highAlerts, color: '#f97316' },
    { name: 'Medium', value: stats.mediumAlerts, color: '#eab308' },
    { name: 'Low', value: stats.lowAlerts, color: '#22c55e' },
  ].filter(d => d.value > 0);

  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="h-[250px]">
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
      
      {/* Center text */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ marginTop: '-40px' }}>
        <div className="text-center">
          <div className="text-3xl font-bold text-white">{total}</div>
          <div className="text-xs text-gray-400">Total Alerts</div>
        </div>
      </div>
    </div>
  );
}
