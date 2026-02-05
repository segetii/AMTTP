/** @type {import('next').NextConfig} */

// Backend service URLs - use Docker service names when in container, localhost for local dev
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'http://orchestrator:8007';
const SANCTIONS_URL = process.env.SANCTIONS_URL || 'http://sanctions:8004';
const MONITORING_URL = process.env.MONITORING_URL || 'http://monitoring:8005';
const GEO_RISK_URL = process.env.GEO_RISK_URL || 'http://geo-risk:8006';
const EXPLAINABILITY_URL = process.env.EXPLAINABILITY_URL || 'http://explainability:8009';

const nextConfig = {
  // Enable standalone output for Docker deployment
  output: 'standalone',
  
  // Disable telemetry in production
  experimental: {
    // instrumentationHook: true,
  },
  
  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8007',
  },

  // API rewrites to proxy backend services
  async rewrites() {
    return [
      // Orchestrator API (port 8007) - frontend calls /api/*
      {
        source: '/api/:path*',
        destination: `${ORCHESTRATOR_URL}/:path*`,
      },
      // Sanctions Screening Service (port 8004) - strip /sanctions prefix
      {
        source: '/sanctions/:path*',
        destination: `${SANCTIONS_URL}/:path*`,
      },
      // Transaction Monitoring Service (port 8005) - strip /monitoring prefix
      {
        source: '/monitoring/:path*',
        destination: `${MONITORING_URL}/:path*`,
      },
      // Geographic Risk Service (port 8006) - /geo/health goes to /health, other /geo/* keeps prefix
      {
        source: '/geo/health',
        destination: `${GEO_RISK_URL}/health`,
      },
      {
        source: '/geo/:path*',
        destination: `${GEO_RISK_URL}/geo/:path*`,
      },
      // Explainability Service (port 8009)
      {
        source: '/explain/:path*',
        destination: `${EXPLAINABILITY_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
