import ComplianceClientPage from './ComplianceClientPage';

// Force dynamic rendering and disable caching to avoid prerender errors
export const dynamic = 'force-dynamic';
export const fetchCache = 'force-no-store';
export const revalidate = 0;

export default function CompliancePage() {
  return <ComplianceClientPage />;
}

