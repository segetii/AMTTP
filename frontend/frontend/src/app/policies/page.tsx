'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Shield, Plus, Settings, ToggleLeft, ToggleRight,
  Trash2, Edit, Copy, Star, AlertTriangle, CheckCircle,
  XCircle, Clock, TrendingUp, Filter, Search, ArrowLeft
} from 'lucide-react';
import { fetchPolicies, deletePolicy, togglePolicyStatus, setDefaultPolicy } from '@/lib/api';
import type { Policy } from '@/types/policy';
import { PolicyCard } from '@/components/PolicyCard';

export default function PoliciesPage() {
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'inactive'>('all');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  useEffect(() => {
    loadPolicies();
  }, []);

  async function loadPolicies() {
    setLoading(true);
    try {
      const data = await fetchPolicies();
      setPolicies(data);
    } catch (error) {
      console.error('Failed to load policies:', error);
    }
    setLoading(false);
  }

  async function handleToggleStatus(id: string, currentStatus: boolean) {
    try {
      await togglePolicyStatus(id, !currentStatus);
      setPolicies(policies.map(p => 
        p.id === id ? { ...p, isActive: !currentStatus } : p
      ));
    } catch (error) {
      console.error('Failed to toggle policy status:', error);
    }
  }

  async function handleSetDefault(id: string) {
    try {
      await setDefaultPolicy(id);
      setPolicies(policies.map(p => ({
        ...p,
        isDefault: p.id === id
      })));
    } catch (error) {
      console.error('Failed to set default policy:', error);
    }
  }

  async function handleDelete(id: string) {
    try {
      await deletePolicy(id);
      setPolicies(policies.filter(p => p.id !== id));
      setDeleteConfirm(null);
    } catch (error) {
      console.error('Failed to delete policy:', error);
    }
  }

  const filteredPolicies = policies.filter(policy => {
    if (filterStatus === 'active' && !policy.isActive) return false;
    if (filterStatus === 'inactive' && policy.isActive) return false;
    if (searchQuery && !policy.name.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false;
    }
    return true;
  });

  const stats = {
    total: policies.length,
    active: policies.filter(p => p.isActive).length,
    inactive: policies.filter(p => !p.isActive).length,
    totalTransactions: policies.reduce((sum, p) => sum + p.stats.totalTransactions, 0),
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-[1600px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => router.push('/war-room')}
                className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5" />
              </button>
              <Shield className="w-8 h-8 text-purple-500" />
              <div>
                <h1 className="text-xl font-bold">Policy Management</h1>
                <p className="text-sm text-gray-400">Configure transaction compliance rules</p>
              </div>
            </div>

            <div className="flex items-center gap-4">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
                <input
                  type="text"
                  placeholder="Search policies..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10 pr-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-purple-500 w-64"
                />
              </div>

              {/* Filter */}
              <div className="flex bg-gray-800 rounded-lg p-1">
                {(['all', 'active', 'inactive'] as const).map((status) => (
                  <button
                    key={status}
                    onClick={() => setFilterStatus(status)}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors capitalize ${
                      filterStatus === status
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {status}
                  </button>
                ))}
              </div>

              {/* Create New Policy */}
              <button
                onClick={() => router.push('/policies/new')}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors"
              >
                <Plus className="w-4 h-4" />
                New Policy
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-6">
        {/* Stats Overview */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <Settings className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">{stats.total}</p>
                <p className="text-sm text-gray-400">Total Policies</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-500/20 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">{stats.active}</p>
                <p className="text-sm text-gray-400">Active</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gray-500/20 rounded-lg">
                <XCircle className="w-5 h-5 text-gray-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">{stats.inactive}</p>
                <p className="text-sm text-gray-400">Inactive</p>
              </div>
            </div>
          </div>
          
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <TrendingUp className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">{stats.totalTransactions.toLocaleString()}</p>
                <p className="text-sm text-gray-400">Total Transactions</p>
              </div>
            </div>
          </div>
        </div>

        {/* Policies Grid */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full" />
          </div>
        ) : filteredPolicies.length === 0 ? (
          <div className="text-center py-20">
            <Settings className="w-16 h-16 mx-auto mb-4 text-gray-600" />
            <h3 className="text-lg font-medium text-gray-400">No policies found</h3>
            <p className="text-gray-500 mt-2">
              {searchQuery ? 'Try a different search term' : 'Create your first policy to get started'}
            </p>
            {!searchQuery && (
              <button
                onClick={() => router.push('/policies/new')}
                className="mt-4 px-4 py-2 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm font-medium transition-colors"
              >
                Create Policy
              </button>
            )}
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredPolicies.map((policy) => (
              <PolicyCard
                key={policy.id}
                policy={policy}
                onEdit={() => router.push(`/policies/${policy.id}/edit`)}
                onToggleStatus={() => handleToggleStatus(policy.id, policy.isActive)}
                onSetDefault={() => handleSetDefault(policy.id)}
                onDelete={() => setDeleteConfirm(policy.id)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md mx-4">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-red-500/20 rounded-lg">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-lg font-bold">Delete Policy</h3>
            </div>
            <p className="text-gray-400 mb-6">
              Are you sure you want to delete this policy? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteConfirm)}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg text-sm transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
