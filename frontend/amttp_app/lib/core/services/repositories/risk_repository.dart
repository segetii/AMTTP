/// Risk scoring repository
/// 
/// Handles all ML-based risk scoring operations.
/// NEVER silently approves transactions on error - always propagates failures.
library;

import 'http_client.dart';
import '../api_config.dart';

/// Risk score response from ML engine
class RiskScoreResult {
  final double riskScore;
  final String riskLevel;
  final double confidence;
  final Map<String, dynamic> factors;
  final String modelVersion;
  final DateTime timestamp;
  final String recommendedAction;

  RiskScoreResult({
    required this.riskScore,
    required this.riskLevel,
    required this.confidence,
    required this.factors,
    required this.modelVersion,
    required this.timestamp,
    required this.recommendedAction,
  });

  factory RiskScoreResult.fromJson(Map<String, dynamic> json) {
    return RiskScoreResult(
      riskScore: (json['risk_score'] as num).toDouble(),
      riskLevel: json['risk_level'] as String,
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      factors: json['factors'] as Map<String, dynamic>? ?? {},
      modelVersion: json['model_version'] as String? ?? 'unknown',
      timestamp: DateTime.tryParse(json['timestamp'] ?? '') ?? DateTime.now(),
      recommendedAction: _mapRiskToAction(json['risk_level'] as String),
    );
  }

  static String _mapRiskToAction(String riskLevel) {
    switch (riskLevel.toLowerCase()) {
      case 'critical':
        return 'BLOCK';
      case 'high':
        return 'ESCROW';
      case 'medium':
        return 'REVIEW';
      case 'low':
      case 'minimal':
        return 'ALLOW';
      default:
        return 'REVIEW';
    }
  }

  bool get isSafe => riskLevel == 'low' || riskLevel == 'minimal';
  bool get requiresReview => riskLevel == 'medium';
  bool get isHighRisk => riskLevel == 'high' || riskLevel == 'critical';
}

/// Risk engine health status
class RiskEngineHealth {
  final String status;
  final bool modelLoaded;
  final String version;
  final int uptimeSeconds;

  RiskEngineHealth({
    required this.status,
    required this.modelLoaded,
    required this.version,
    required this.uptimeSeconds,
  });

  factory RiskEngineHealth.fromJson(Map<String, dynamic> json) {
    return RiskEngineHealth(
      status: json['status'] as String? ?? 'unknown',
      modelLoaded: json['model_loaded'] as bool? ?? false,
      version: json['version'] as String? ?? 'unknown',
      uptimeSeconds: json['uptime_seconds'] as int? ?? 0,
    );
  }

  bool get isHealthy => status == 'ok' && modelLoaded;
}

/// Repository for risk scoring operations
class RiskRepository {
  final HttpClient _client;

  RiskRepository({HttpClient? client}) : _client = client ?? HttpClient();

  /// Score a transaction
  /// 
  /// IMPORTANT: This method throws on failure - callers must handle errors.
  /// Do NOT catch and return default/safe values as that could approve risky txs.
  Future<RiskScoreResult> scoreTransaction({
    required String fromAddress,
    required String toAddress,
    required double valueEth,
    double? gasPriceGwei,
    int? nonce,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.riskScore,
      data: {
        'from_address': fromAddress,
        'to_address': toAddress,
        'value_eth': valueEth,
        if (gasPriceGwei != null) 'gas_price_gwei': gasPriceGwei,
        if (nonce != null) 'nonce': nonce,
      },
    );
    
    return RiskScoreResult.fromJson(response);
  }

  /// Batch score multiple transactions
  Future<List<RiskScoreResult>> scoreTransactionBatch(
    List<Map<String, dynamic>> transactions,
  ) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.riskBatch,
      data: {'transactions': transactions},
    );

    final results = response['results'] as List<dynamic>;
    return results
        .map((r) => RiskScoreResult.fromJson(r as Map<String, dynamic>))
        .toList();
  }

  /// Check risk engine health
  Future<RiskEngineHealth> checkHealth() async {
    final response = await _client.get<Map<String, dynamic>>(ApiConfig.riskHealth);
    return RiskEngineHealth.fromJson(response);
  }

  /// Score an address (reputation check)
  Future<RiskScoreResult> scoreAddress(String address) async {
    final response = await _client.post<Map<String, dynamic>>(
      '/score/address',
      data: {'address': address},
    );
    
    return RiskScoreResult.fromJson(response);
  }
}
