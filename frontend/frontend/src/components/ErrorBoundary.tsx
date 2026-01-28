// Error boundary component for graceful error handling
'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  /** Component name for error reporting */
  name?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to error reporting service
    console.error(`[ErrorBoundary${this.props.name ? `: ${this.props.name}` : ''}]`, error, errorInfo);
    
    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      // Custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI
      return (
        <div 
          className="flex flex-col items-center justify-center p-8 bg-gray-900 rounded-xl border border-red-500/20"
          role="alert"
          aria-live="assertive"
        >
          <AlertTriangle className="w-12 h-12 text-red-400 mb-4" aria-hidden="true" />
          <h3 className="text-lg font-semibold text-gray-100 mb-2">
            Something went wrong
          </h3>
          <p className="text-sm text-gray-400 mb-4 text-center max-w-md">
            {this.state.error?.message || 'An unexpected error occurred while loading this component.'}
          </p>
          <button
            onClick={this.handleRetry}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            aria-label="Try loading again"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

// Functional wrapper for easier use with hooks
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  options?: { name?: string; fallback?: ReactNode }
) {
  return function WithErrorBoundaryWrapper(props: P) {
    return (
      <ErrorBoundary name={options?.name} fallback={options?.fallback}>
        <WrappedComponent {...props} />
      </ErrorBoundary>
    );
  };
}

// Suspense boundary with error handling
import { Suspense } from 'react';

interface AsyncBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
  errorFallback?: ReactNode;
  name?: string;
}

export function AsyncBoundary({ 
  children, 
  fallback, 
  errorFallback,
  name 
}: AsyncBoundaryProps) {
  const loadingFallback = fallback || <LoadingSpinner />;
  
  return (
    <ErrorBoundary name={name} fallback={errorFallback}>
      <Suspense fallback={loadingFallback}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
}

// Reusable loading spinner
export function LoadingSpinner({ size = 'md', className = '' }: { size?: 'sm' | 'md' | 'lg'; className?: string }) {
  const sizes = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  };

  return (
    <div className={`flex items-center justify-center p-8 ${className}`} role="status" aria-label="Loading">
      <div 
        className={`${sizes[size]} border-2 border-gray-700 border-t-blue-500 rounded-full animate-spin`}
        aria-hidden="true"
      />
      <span className="sr-only">Loading...</span>
    </div>
  );
}

// Skeleton loader for content placeholders
export function Skeleton({ 
  className = '', 
  variant = 'text' 
}: { 
  className?: string; 
  variant?: 'text' | 'circular' | 'rectangular';
}) {
  const baseClasses = 'animate-pulse bg-gray-700 rounded';
  const variantClasses = {
    text: 'h-4 w-full',
    circular: 'rounded-full',
    rectangular: '',
  };

  return (
    <div 
      className={`${baseClasses} ${variantClasses[variant]} ${className}`}
      aria-hidden="true"
    />
  );
}

// Card skeleton for dashboard stats
export function StatCardSkeleton() {
  return (
    <div className="p-4 rounded-xl border border-gray-700 bg-gray-800/50">
      <div className="flex items-center justify-between mb-2">
        <Skeleton className="w-5 h-5" variant="circular" />
        <Skeleton className="w-12 h-4" />
      </div>
      <Skeleton className="w-16 h-8 mb-1" />
      <Skeleton className="w-20 h-3" />
    </div>
  );
}

// Table skeleton for alerts
export function TableRowSkeleton() {
  return (
    <tr className="border-b border-gray-800">
      <td className="px-4 py-3"><Skeleton className="w-4 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-16 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-32 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-16 h-6" /></td>
      <td className="px-4 py-3"><Skeleton className="w-20 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-8 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-24 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-16 h-4" /></td>
      <td className="px-4 py-3"><Skeleton className="w-20 h-6" /></td>
      <td className="px-4 py-3"><Skeleton className="w-6 h-6" /></td>
    </tr>
  );
}
