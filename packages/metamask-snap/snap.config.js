module.exports = {
  input: './src/index.ts',
  output: {
    path: './dist',
    filename: 'bundle.js',
  },
  server: {
    port: 8080,
  },
  polyfills: {
    buffer: true,
  },
  environment: {
    AMTTP_API_URL: 'http://localhost:8000',
    FCA_API_URL: 'http://localhost:8002',
  },
};
