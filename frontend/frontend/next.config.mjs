/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    turbopack: {
      // This tells Turbopack that the root of the monorepo is two directories up.
      root: '../..',
    },
  },
};

export default nextConfig;