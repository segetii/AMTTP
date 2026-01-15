'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft, Shield, Plus } from 'lucide-react';
import { PolicyForm } from '@/components/PolicyForm';
import { createPolicy } from '@/lib/api';
import type { PolicyFormData } from '@/types/policy';

export default function NewPolicyPage() {
  const router = useRouter();

  async function handleSubmit(data: PolicyFormData) {
    await createPolicy(data);
    router.push('/policies');
  }

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
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <Plus className="w-5 h-5 text-purple-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold">Create New Policy</h1>
                <p className="text-sm text-gray-400">Configure transaction compliance rules</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-[1200px] mx-auto px-6 py-6">
        <PolicyForm
          onSubmit={handleSubmit}
          onCancel={() => router.push('/policies')}
        />
      </main>
    </div>
  );
}
