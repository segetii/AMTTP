'use client';

/**
 * StatGrid – Responsive stat cards grid for War Room pages
 * 
 * Responsive: 1 col → 2 cols → 4 cols (sm/lg breakpoints)
 */

import React, { ReactNode } from 'react';

export interface StatItem {
  label: string;
  value: string | number;
  icon?: ReactNode;
  valueColor?: string; // e.g. 'text-green-400'
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
}

interface StatGridProps {
  stats: StatItem[];
  columns?: 3 | 4 | 5;
}

export default function StatGrid({ stats, columns = 4 }: StatGridProps) {
  const gridCols = {
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
    5: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-5',
  };

  const changeColors = {
    positive: 'text-green-400',
    negative: 'text-red-400',
    neutral: 'text-mutedText',
  };

  return (
    <div className={`grid ${gridCols[columns]} gap-4`}>
      {stats.map((stat) => (
        <div
          key={stat.label}
          className="bg-surface rounded-xl p-4 border border-borderSubtle"
        >
          {stat.icon && (
            <div className="flex items-center gap-2 text-mutedText text-sm mb-2">
              {stat.icon}
              <span>{stat.label}</span>
            </div>
          )}
          <p className={`text-2xl font-bold ${stat.valueColor || 'text-text'}`}>
            {stat.value}
          </p>
          {!stat.icon && (
            <p className="text-sm text-mutedText mt-1">{stat.label}</p>
          )}
          {stat.change && (
            <p className={`text-sm mt-1 ${changeColors[stat.changeType || 'neutral']}`}>
              {stat.change}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
