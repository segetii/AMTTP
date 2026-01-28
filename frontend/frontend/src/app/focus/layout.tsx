'use client';

/**
 * Focus Mode Layout
 * 
 * Wrapper for all Focus Mode pages
 * Ensures RBAC context and redirects unauthorized users
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { AppMode } from '@/types/rbac';

function FocusModeGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { mode, isAuthenticated, isLoading } = useAuth();
  
  useEffect(() => {
    // If not loading and not authenticated, redirect to login
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
      return;
    }
    
    // If authenticated but wrong mode, redirect to appropriate mode
    if (!isLoading && isAuthenticated && mode !== AppMode.FOCUS) {
      router.push('/war-room');
      return;
    }
  }, [isLoading, isAuthenticated, mode, router]);
  
  // Show loading while checking auth
  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-indigo-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-indigo-600 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          </div>
          <p className="text-gray-500">Loading...</p>
        </div>
      </div>
    );
  }
  
  // Don't render if not authorized for Focus mode
  if (!isAuthenticated || mode !== AppMode.FOCUS) {
    return null;
  }
  
  return <>{children}</>;
}

export default function FocusLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <FocusModeGuard>{children}</FocusModeGuard>
    </AuthProvider>
  );
}
