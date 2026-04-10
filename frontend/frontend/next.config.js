/** @type {import('next').NextConfig} */

// Backend service URLs - use Docker service names when in container, localhost for local dev
const ORCHESTRATOR_URL = process.env.ORCHESTRATOR_URL || 'http://localhost:8007';
const SANCTIONS_URL = process.env.SANCTIONS_URL || 'http://localhost:8004';
const MONITORING_URL = process.env.MONITORING_URL || 'http://localhost:8005';
const GEO_RISK_URL = process.env.GEO_RISK_URL || 'http://localhost:8006';
const EXPLAINABILITY_URL = process.env.EXPLAINABILITY_URL || 'http://localhost:8009';
const RISK_ENGINE_URL = process.env.RISK_ENGINE_URL || 'http://localhost:8000';
const POLICY_URL = process.env.POLICY_URL || 'http://localhost:8003';
const INTEGRITY_URL = process.env.INTEGRITY_URL || 'http://localhost:8008';
const ORACLE_URL = process.env.ORACLE_URL || 'http://localhost:3001';

const nextConfig = {
  // Enable standalone output for Docker deployment
  output: 'standalone',

  // Base path — empty for monolith deployment where nginx proxies routes directly
  // basePath: '/app',

  // Disable telemetry in production
  experimental: {
    // instrumentationHook: true,
  },

  // Skip ESLint + TS checks during production build (handled in CI separately)
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  
  // Environment variables
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || '/api',
  },

  // CORS headers — allow Flutter dev (port 3010) to call data APIs
  async headers() {
    return [
      {
        source: '/api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Content-Type, Accept' },
        ],
      },
      {
        source: '/app-api/:path*',
        headers: [
          { key: 'Access-Control-Allow-Origin', value: '*' },
          { key: 'Access-Control-Allow-Methods', value: 'GET, OPTIONS' },
          { key: 'Access-Control-Allow-Headers', value: 'Content-Type, Accept' },
        ],
      },
    ];
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
      // Risk Engine (port 8000)
      {
        source: '/risk/:path*',
        destination: `${RISK_ENGINE_URL}/:path*`,
      },
      // Policy Service (port 8003)
      {
        source: '/policy/:path*',
        destination: `${POLICY_URL}/:path*`,
      },
      // Integrity Service (port 8008)
      {
        source: '/integrity/:path*',
        destination: `${INTEGRITY_URL}/:path*`,
      },
      // Oracle Service (port 3001)
      {
        source: '/oracle/:path*',
        destination: `${ORACLE_URL}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
