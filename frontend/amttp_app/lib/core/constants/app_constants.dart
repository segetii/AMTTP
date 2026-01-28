class AppConstants {
  // App Info
  static const String appName = 'AMTTP Protocol';
  static const String appVersion = '1.0.0';
  static const String appDescription = 'DeFi with DQN-powered fraud detection';
  
  // Network Configuration
  static const String defaultNetworkName = 'Ethereum Mainnet';
  static const int defaultChainId = 1;
  static const String testnetName = 'Goerli Testnet';
  static const int testnetChainId = 5;
  
  // Contract Addresses (to be updated after deployment)
  static const String amttpStreamlinedAddress = '0x...'; // AMTTPStreamlined
  static const String amttpPolicyManagerAddress = '0x...'; // AMTTPPolicyManager  
  static const String amttpPolicyEngineAddress = '0x...'; // AMTTPPolicyEngine
  
  // API Endpoints - Use relative URLs for production (nginx proxies to services)
  // When deployed, nginx proxies these paths to the correct backend services
  // For local development, use the full URLs
  
  // Base URL - For local dev, point to orchestrator directly
  // In production with nginx, this would be empty string
  static const String baseApiUrl = 'http://localhost:8007';  // Orchestrator
  // Risk Engine endpoint  
  static const String riskEngineUrl = 'http://localhost:8002';  // Risk engine
  // Integrity Service endpoint
  static const String integrityServiceUrl = 'http://localhost:8008';  // Integrity service
  
  // Next.js Frontend (for embedded visualizations)
  static const String nextJsUrl = 'http://localhost:3006';  // Next.js app
  
  // API Paths (relative - nginx will proxy these)
  static const String riskScoringEndpoint = '/risk/score';
  static const String integrityVerifyEndpoint = '/verify-integrity';
  static const String kycEndpoint = '/api/profiles';
  static const String transactionEndpoint = '/api/evaluate';
  
  // WebSocket - Disabled for now (no WS backend service)
  static const String wsUrl = 'ws://localhost:8007';
  
  // Risk Thresholds (matching your smart contract logic)
  static const double lowRiskThreshold = 0.4;
  static const double mediumRiskThreshold = 0.7;
  static const double highRiskThreshold = 0.8;
  
  // Transaction Limits
  static const double defaultDailyLimit = 10000.0;
  static const double defaultTransactionLimit = 1000.0;
  
  // DQN Model Info
  static const double dqnF1Score = 0.669;
  static const String dqnModelVersion = 'v1.0';
  static const int dqnTrainingDataSize = 28457;
  
  // UI Constants
  static const double borderRadius = 12.0;
  static const double padding = 16.0;
  static const double iconSize = 24.0;
  
  // Animation Durations
  static const Duration fastAnimation = Duration(milliseconds: 200);
  static const Duration normalAnimation = Duration(milliseconds: 300);
  static const Duration slowAnimation = Duration(milliseconds: 500);
}