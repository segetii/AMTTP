'use client';

/**
 * PageHeader – Shared page header for War Room subpages
 * 
 * Provides consistent title, description, and optional actions slot.
 */

import React, { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  actions?: ReactNode;
}

export default function PageHeader({ title, description, icon, actions }: PageHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold text-text flex items-center gap-3">
          {icon && <span className="text-3xl">{icon}</span>}
          {title}
        </h1>
        {description && (
          <p className="text-mutedText mt-1">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}
