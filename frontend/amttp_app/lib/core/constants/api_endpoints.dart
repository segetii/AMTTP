/// API Endpoints - Centralized API Configuration
/// 
/// All API endpoints are defined here.
/// Use environment variables for different environments.
library;

abstract class ApiEndpoints {
  // ═══════════════════════════════════════════════════════════════════════════
  // BASE URLS
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Main orchestrator API
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8007',
  );
  
  /// Risk engine service
  static const String riskEngineUrl = String.fromEnvironment(
    'RISK_ENGINE_URL',
    defaultValue: 'http://localhost:8002',
  );
  
  /// Integrity service
  static const String integrityUrl = String.fromEnvironment(
    'INTEGRITY_URL',
    defaultValue: 'http://localhost:8008',
  );
  
  /// Next.js frontend (for embeds)
  static const String nextJsUrl = String.fromEnvironment(
    'NEXTJS_URL',
    defaultValue: 'http://localhost:3006',
  );
  
  // ═══════════════════════════════════════════════════════════════════════════
  // AUTH ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String authLogin = '/auth/login';
  static const String authLogout = '/auth/logout';
  static const String authRefresh = '/auth/refresh';
  static const String authRegister = '/auth/register';
  static const String authVerify = '/auth/verify';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // RISK SCORING ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String riskScore = '/risk/score';
  static const String riskBatch = '/risk/batch';
  static const String riskHistory = '/risk/history';
  static const String riskExplain = '/risk/explain';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // TRANSACTION ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String txEvaluate = '/api/evaluate';
  static const String txSubmit = '/api/submit';
  static const String txStatus = '/api/status';
  static const String txHistory = '/api/history';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // PROFILE & KYC ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String profile = '/api/profiles';
  static const String kycStatus = '/api/kyc/status';
  static const String kycSubmit = '/api/kyc/submit';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // INTEGRITY ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String integrityVerify = '/verify-integrity';
  static const String integrityAudit = '/audit-trail';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // DISPUTE ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String disputes = '/api/disputes';
  static const String disputeCreate = '/api/disputes/create';
  static const String disputeEvidence = '/api/disputes/evidence';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // POLICY ENDPOINTS
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String policies = '/api/policies';
  static const String policyCheck = '/api/policies/check';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // HELPER METHODS
  // ═══════════════════════════════════════════════════════════════════════════
  
  /// Build full URL for main API
  static String api(String path) => '$baseUrl$path';
  
  /// Build full URL for risk engine
  static String risk(String path) => '$riskEngineUrl$path';
  
  /// Build full URL for integrity service
  static String integrity(String path) => '$integrityUrl$path';
  
  /// Build Next.js embed URL
  static String nextJs(String path) => '$nextJsUrl$path';
  
  /// Build Next.js War Room embed URL
  static String warRoomEmbed(String path, {String? role}) {
    final base = '$nextJsUrl$path?embed=true';
    if (role != null) {
      return '$base&role=$role';
    }
    return base;
  }
}
