'use client';

/**
 * ML Models Page
 * 
 * Machine Learning model management and monitoring
 * RBAC: R6 SUPER ADMIN ONLY - Model configuration, pause, retrain
 * 
 * Supports embed mode (?embed=true) for Flutter integration
 */

import React, { useState } from 'react';
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
// MOCK DATA
// ═══════════════════════════════════════════════════════════════════════════════

interface MLModel {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'training' | 'paused' | 'error';
  accuracy: number;
  precision: number;
  recall: number;
  f1Score: number;
  lastTrained: string;
  predictions24h: number;
  avgLatency: number;
  version: string;
}

const mockModels: MLModel[] = [
  {
    id: 'model_001',
    name: 'Anomaly Detector v3',
    type: 'Isolation Forest',
    status: 'active',
    accuracy: 0.94,
    precision: 0.92,
    recall: 0.89,
    f1Score: 0.905,
    lastTrained: '2026-01-20T14:30:00Z',
    predictions24h: 12450,
    avgLatency: 23,
    version: '3.2.1',
  },
  {
    id: 'model_002',
    name: 'Transaction Classifier',
    type: 'XGBoost',
    status: 'active',
    accuracy: 0.96,
    precision: 0.94,
    recall: 0.93,
    f1Score: 0.935,
    lastTrained: '2026-01-19T10:15:00Z',
    predictions24h: 8920,
    avgLatency: 15,
    version: '2.1.0',
  },
  {
    id: 'model_003',
    name: 'Risk Scoring Engine',
    type: 'Neural Network',
    status: 'training',
    accuracy: 0.91,
    precision: 0.88,
    recall: 0.85,
    f1Score: 0.865,
    lastTrained: '2026-01-18T08:00:00Z',
    predictions24h: 0,
    avgLatency: 45,
    version: '1.5.2',
  },
  {
    id: 'model_004',
    name: 'Wallet Clustering',
    type: 'DBSCAN',
    status: 'active',
    accuracy: 0.89,
    precision: 0.87,
    recall: 0.84,
    f1Score: 0.855,
    lastTrained: '2026-01-17T16:45:00Z',
    predictions24h: 3200,
    avgLatency: 120,
    version: '1.2.0',
  },
  {
    id: 'model_005',
    name: 'Velocity Anomaly',
    type: 'LSTM',
    status: 'paused',
    accuracy: 0.87,
    precision: 0.83,
    recall: 0.80,
    f1Score: 0.815,
    lastTrained: '2026-01-15T12:00:00Z',
    predictions24h: 0,
    avgLatency: 78,
    version: '1.0.3',
  },
];

// ═══════════════════════════════════════════════════════════════════════════════
// COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function MLModelsPage() {
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleRefresh = () => {
    setIsLoading(true);
    setTimeout(() => setIsLoading(false), 1000);
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

  const activeModels = mockModels.filter(m => m.status === 'active').length;
  const totalPredictions = mockModels.reduce((sum, m) => sum + m.predictions24h, 0);
  const avgAccuracy = mockModels.reduce((sum, m) => sum + m.accuracy, 0) / mockModels.length;

  // Check for embed mode (Flutter integration)
  const searchParams = useSearchParams();
  const isEmbedded = searchParams.get('embed') === 'true';

  return (
    <div className={`${isEmbedded ? 'p-4' : 'p-6'} space-y-6 min-h-screen bg-slate-950`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className={`${isEmbedded ? 'text-xl' : 'text-2xl'} font-bold text-white`}>ML Models</h1>
            <span className="px-2 py-1 bg-purple-900/50 text-purple-400 border border-purple-700 rounded text-xs font-medium flex items-center gap-1">
              <ShieldCheckIcon className="w-3 h-3" />
              SUPER ADMIN
            </span>
          </div>
          <p className="text-slate-400 mt-1">Configure, pause, and retrain machine learning models</p>
        </div>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg flex items-center gap-2 transition-colors">
            <CpuChipIcon className="w-5 h-5" />
            Deploy New Model
          </button>
          <button 
            onClick={handleRefresh}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            <ArrowPathIcon className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <CpuChipIcon className="w-4 h-4" />
            <span>Total Models</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{mockModels.length}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <CheckCircleIcon className="w-4 h-4 text-green-400" />
            <span>Active Models</span>
          </div>
          <p className="text-2xl font-bold text-green-400 mt-2">{activeModels}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ChartBarIcon className="w-4 h-4" />
            <span>Predictions (24h)</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{totalPredictions.toLocaleString()}</p>
        </div>
        <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-sm">
            <ArrowTrendingUpIcon className="w-4 h-4 text-green-400" />
            <span>Avg Accuracy</span>
          </div>
          <p className="text-2xl font-bold text-white mt-2">{(avgAccuracy * 100).toFixed(1)}%</p>
        </div>
      </div>

      {/* Models Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {mockModels.map((model) => (
          <div 
            key={model.id}
            className={`bg-slate-800 rounded-lg border transition-colors cursor-pointer ${
              selectedModel === model.id 
                ? 'border-blue-500' 
                : 'border-slate-700 hover:border-slate-600'
            }`}
            onClick={() => setSelectedModel(selectedModel === model.id ? null : model.id)}
          >
            <div className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-white">{model.name}</h3>
                  <p className="text-slate-400 text-sm">{model.type} • v{model.version}</p>
                </div>
                {getStatusBadge(model.status)}
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-4 gap-4 mt-4">
                <div>
                  <p className="text-slate-500 text-xs uppercase">Accuracy</p>
                  <p className="text-white font-semibold">{(model.accuracy * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">Precision</p>
                  <p className="text-white font-semibold">{(model.precision * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">Recall</p>
                  <p className="text-white font-semibold">{(model.recall * 100).toFixed(1)}%</p>
                </div>
                <div>
                  <p className="text-slate-500 text-xs uppercase">F1 Score</p>
                  <p className="text-white font-semibold">{(model.f1Score * 100).toFixed(1)}%</p>
                </div>
              </div>

              {/* Additional Info */}
              <div className="flex items-center gap-6 mt-4 pt-4 border-t border-slate-700 text-sm">
                <div className="flex items-center gap-1 text-slate-400">
                  <ClockIcon className="w-4 h-4" />
                  <span>Trained: {formatDate(model.lastTrained)}</span>
                </div>
                <div className="flex items-center gap-1 text-slate-400">
                  <ChartBarIcon className="w-4 h-4" />
                  <span>{model.predictions24h.toLocaleString()} predictions</span>
                </div>
                <div className="text-slate-400">
                  <span>{model.avgLatency}ms avg</span>
                </div>
              </div>

              {/* Expanded Actions */}
              {selectedModel === model.id && (
                <div className="flex gap-2 mt-4 pt-4 border-t border-slate-700">
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
