'use client';

/**
 * ML Models Page
 * 
 * Machine Learning model management and monitoring
 * RBAC: R6 SUPER ADMIN ONLY - Model configuration, pause, retrain
 * 
 * Supports embed mode (?embed=true) for Flutter integration
 */

import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { 
  ArrowPathIcon,
  PlayIcon,
  PauseIcon,
  ChartBarIcon,
  CpuChipIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ArrowTrendingUpIcon,
  Cog6ToothIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function MLModelsPage() {
  const [models, setModels] = useState<any[]>([]);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('http://127.0.0.1:3001/risk/models/status')
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(data => setModels(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleRefresh = () => {
    setLoading(true);
    fetch('http://127.0.0.1:3001/risk/models/status')
      .then(r => { if (!r.ok) throw new Error(`API ${r.status}`); return r.json(); })
      .then(data => setModels(Array.isArray(data) ? data : []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-green-900/50 text-green-400 border border-green-700">
            <CheckCircleIcon className="w-3 h-3" />
            Active
          </span>
        );
      case 'training':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-blue-900/50 text-blue-400 border border-blue-700">
            <ArrowPathIcon className="w-3 h-3 animate-spin" />
            Training
          </span>
        );
      case 'paused':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-yellow-900/50 text-yellow-400 border border-yellow-700">
            <PauseIcon className="w-3 h-3" />
            Paused
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-red-900/50 text-red-400 border border-red-700">
            <ExclamationTriangleIcon className="w-3 h-3" />
            Error
          </span>
        );
      default:
        return null;
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const activeModels = models.filter(m => m.status === 'active').length;
  const totalPredictions = models.reduce((sum, m) => sum + m.predictions24h, 0);
  const avgAccuracy = models.reduce((sum, m) => sum + m.accuracy, 0) / models.length;

  // Check for embed mode (Flutter integration)
  const searchParams = useSearchParams();
  const isEmbedded = searchParams.get('embed') === 'true';

  return (
    <div className={`${isEmbedded ? 'p-4' : ''} space-y-6`}>
      {error && <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4 text-red-400 text-sm">⚠ Backend unavailable: {error}</div>}
      {loading && <div className="text-zinc-500 text-sm mb-4">Loading from backend...</div>}
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`${isEmbedded ? 'text-xl' : 'text-2xl'} font-bold text-text`}>ML Models</h1>
            <span className="px-2 py-1 bg-purple-900/50 text-purple-400 border border-purple-700 rounded text-xs font-medium flex items-center gap-1">
              <ShieldCheckIcon className="w-3 h-3" />
              SUPER ADMIN
            </span>
          </div>
          <p className="text-mutedText mt-1">Configure, pause, and retrain machine learning models</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg flex items-center gap-2 transition-colors">
            <CpuChipIcon className="w-5 h-5" />
            Deploy New Model
          </button>
          <button 
            onClick={handleRefresh}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            <ArrowPathIcon className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <CpuChipIcon className="w-4 h-4" />
            <span>Total Models</span>
          </div>
          <p className="text-2xl font-bold text-text mt-2">{models.length}</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <CheckCircleIcon className="w-4 h-4 text-green-400" />
            <span>Active Models</span>
          </div>
          <p className="text-2xl font-bold text-green-400 mt-2">{activeModels}</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ChartBarIcon className="w-4 h-4" />
            <span>Predictions (24h)</span>
          </div>
          <p className="text-2xl font-bold text-text mt-2">{totalPredictions.toLocaleString()}</p>
        </div>
        <div className="bg-surface rounded-lg p-4 border border-borderSubtle">
          <div className="flex items-center gap-2 text-mutedText text-sm">
            <ArrowTrendingUpIcon className="w-4 h-4 text-green-400" />
            <span>Avg Accuracy</span>
          </div>
          <p className="text-2xl font-bold text-text mt-2">{(avgAccuracy * 100).toFixed(1)}%</p>
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {models.map((model) => (
          <div 
            key={model.id}
            className={`bg-surface rounded-lg border transition-colors cursor-pointer ${
              selectedModel === model.id 
                ? 'border-blue-500' 
                : 'border-borderSubtle hover:border-borderSubtle'
            }`}
            onClick={() => setSelectedModel(selectedModel === model.id ? null : model.id)}
          >
            <div className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-text">{model.name}</h3>
                  <p className="text-mutedText text-sm">{model.type} • v{model.version}</p>
                </div>
                {getStatusBadge(model.status)}
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-4 gap-4 mt-4">
                <div>
                  <p className="text-mutedText text-xs uppercase">Accuracy</p>
                  <p className="text-text font-semibold">{(model.accuracy * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-mutedText text-xs uppercase">Precision</p>
                  <p className="text-text font-semibold">{(model.precision * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-mutedText text-xs uppercase">Recall</p>
                  <p className="text-text font-semibold">{(model.recall * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-mutedText text-xs uppercase">F1 Score</p>
                  <p className="text-text font-semibold">{(model.f1Score * 100).toFixed(1)}%</p>
                </div>
              </div>

              {/* Additional Info */}
              <div className="flex items-center gap-6 mt-4 pt-4 border-t border-borderSubtle text-sm">
                <div className="flex items-center gap-1 text-mutedText">
                  <ClockIcon className="w-4 h-4" />
                  <span>Trained: {formatDate(model.lastTrained)}</span>
                </div>
                <div className="flex items-center gap-1 text-mutedText">
                  <ChartBarIcon className="w-4 h-4" />
                  <span>{model.predictions24h.toLocaleString()} predictions</span>
                </div>
                <div className="text-mutedText">
                  <span>{model.avgLatency}ms avg</span>
                </div>
              </div>

              {/* Expanded Actions */}
              {selectedModel === model.id && (
                <div className="flex gap-2 mt-4 pt-4 border-t border-borderSubtle">
                  {model.status === 'active' && (
                    <button className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 rounded text-sm flex items-center gap-1">
                      <PauseIcon className="w-4 h-4" />
                      Pause
                    </button>
                  )}
                  {model.status === 'paused' && (
                    <button className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-sm flex items-center gap-1">
                      <PlayIcon className="w-4 h-4" />
                      Resume
                    </button>
                  )}
                  <button className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm flex items-center gap-1">
                    <ArrowPathIcon className="w-4 h-4" />
                    Retrain
                  </button>
                  <button className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 rounded text-sm">
                    View Logs
                  </button>
                  <button className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 rounded text-sm">
                    Configure
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
