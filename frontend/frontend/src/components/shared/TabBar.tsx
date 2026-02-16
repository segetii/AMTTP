'use client';

/**
 * TabBar – Consistent tab navigation for War Room pages
 * 
 * Standardised styling: rounded-t tabs with surface active background.
 */

import React, { ReactNode } from 'react';

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
}

interface TabBarProps {
  tabs: TabItem[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export default function TabBar({ tabs, activeTab, onTabChange }: TabBarProps) {
  return (
    <div className="flex gap-1 border-b border-borderSubtle pb-0">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors flex items-center gap-2
            ${activeTab === tab.id
              ? 'bg-surface text-text border-b-2 border-primary'
              : 'text-mutedText hover:text-text'
            }`}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}
