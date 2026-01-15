'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { ArrowLeft, Edit } from 'lucide-react';
import { PolicyForm } from '@/components/PolicyForm';
import { fetchPolicy, updatePolicy } from '@/lib/api';
import type { Policy, PolicyFormData } from '@/types/policy';

export default function EditPolicyPage() {
  const router = useRouter();
  const params = useParams();
  const policyId = params?.id as string;
  
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (policyId) {
      loadPolicy();
    }
  }, [policyId]);

  async function loadPolicy() {
    setLoading(true);
    try {
      const data = await fetchPolicy(policyId);
      setPolicy(data);
    } catch (error) {
      console.error('Failed to load policy:', error);
    }
    setLoading(false);
  }

  async function handleSubmit(data: PolicyFormData) {
    await updatePolicy(policyId, data);
    router.push('/policies');
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!policy) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center text-gray-400">
        Policy not found
      </div>
    );
  }

  // Convert Policy to PolicyFormData
  const initialData: PolicyFormData = {
    name: policy.name,
    description: policy.description,
    isActive: policy.isActive,
    thresholds: policy.thresholds,
    limits: policy.limits,
    rules: policy.rules,
    actions: policy.actions,
    whitelist: policy.whitelist,
    blacklist: policy.blacklist,
  };

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-50">
        <div className="max-w-[1200px] mx-auto px-6 py-4">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.push('/policies')}
              className="p-2 hover:bg-gray-800 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <Edit className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Edit Policy</h1>
                <p className="text-sm text-gray-400">{policy.name}</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-6 py-6">
        <PolicyForm
          initialData={initialData}
          onSubmit={handleSubmit}
          onCancel={() => router.push('/policies')}
          isEdit
        />
      </main>
    </div>
  );
}
