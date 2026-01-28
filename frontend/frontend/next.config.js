/** @type {import('next').NextConfig} */
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
        destination: 'http://localhost:8007/:path*',
      },
      // Sanctions Screening Service (port 8004) - strip /sanctions prefix
      {
        source: '/sanctions/:path*',
        destination: 'http://localhost:8004/:path*',
      },
      // Transaction Monitoring Service (port 8005) - strip /monitoring prefix
      {
        source: '/monitoring/:path*',
        destination: 'http://localhost:8005/:path*',
      },
      // Geographic Risk Service (port 8006) - /geo/health goes to /health, other /geo/* keeps prefix
      {
        source: '/geo/health',
        destination: 'http://localhost:8006/health',
      },
      {
        source: '/geo/:path*',
        destination: 'http://localhost:8006/geo/:path*',
      },
      // Explainability Service (port 8009)
      {
        source: '/explain/:path*',
        destination: 'http://localhost:8009/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
