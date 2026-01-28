/// API configuration constants
/// 
/// Centralized configuration for all API endpoints and timeouts.
library;

import 'package:flutter/foundation.dart' show kIsWeb;
import '../constants/app_constants.dart';

/// Runtime override for API base URL
/// Use: flutter run --dart-define=API_BASE_URL=https://your.ngrok.app
const String _apiBaseUrlOverride = String.fromEnvironment('API_BASE_URL');

/// Use mock data in development
const bool _useMocks = bool.fromEnvironment('USE_MOCKS', defaultValue: false);

class ApiConfig {
  ApiConfig._();

  /// Whether to use mock data
  static bool get useMocks => _useMocks;

  /// Connection timeout
  static const Duration connectTimeout = Duration(seconds: 15);
  
  /// Receive timeout
  static const Duration receiveTimeout = Duration(seconds: 30);
  
  /// Send timeout
  static const Duration sendTimeout = Duration(seconds: 30);

  /// Resolve the correct API base URL
  /// Priority:
  /// 1) API_BASE_URL dart-define
  /// 2) Web dev port detection
  /// 3) AppConstants default
  static String resolveBaseUrl() {
    if (_apiBaseUrlOverride.isNotEmpty) {
      return _apiBaseUrlOverride;
    }

    // Web development mode - use same host without dev port
    if (kIsWeb) {
      final uri = Uri.base;
      if (uri.host.isNotEmpty && uri.port == 3003) {
        return '${uri.scheme}://${uri.host}';
      }
    }

    return AppConstants.baseApiUrl;
  }

  // API Endpoints
  static const String riskScore = '/risk/score';
  static const String riskBatch = '/risk/score/batch';
  static const String riskHealth = '/risk/health';
  
  static const String integrityVerify = '/integrity/verify';
  static const String integrityAudit = '/integrity/audit';
  
  static const String compliance = '/evaluate';
  static const String complianceWithIntegrity = '/evaluate-with-integrity';
  
  static const String kycVerify = '/kyc/verify';
  static const String kycStatus = '/kyc/status';
  
  static const String disputes = '/disputes';
  static const String disputeEvidence = '/disputes/evidence';
  
  static const String policies = '/policies';
  
  static const String transactions = '/transactions';
  static const String transactionHistory = '/transactions/history';

  // Endpoint helpers for repositories
  static String get riskEndpoint => '${resolveBaseUrl()}$riskScore';
  static String get complianceEndpoint => '${resolveBaseUrl()}$compliance';
  static String get kycEndpoint => '${resolveBaseUrl()}/kyc';
  static String get disputeEndpoint => '${resolveBaseUrl()}$disputes';
  static String get walletEndpoint => '${resolveBaseUrl()}/wallet';
  static String get policyEndpoint => '${resolveBaseUrl()}$policies';
}
