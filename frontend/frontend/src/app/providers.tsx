// Client-side providers wrapper
'use client';

import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { queryClient } from '@/lib/query-client';
import { ToastProvider } from '@/lib/toast';
import { ReactNode } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        {children}
      </ToastProvider>
      {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools initialIsOpen={false} position="bottom" />
      )}
    </QueryClientProvider>
  );
}
