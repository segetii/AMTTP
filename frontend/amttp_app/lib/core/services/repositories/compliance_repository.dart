/// Compliance evaluation repository
/// 
/// Handles transaction compliance checks including integrity verification.
/// CRITICAL: Never silently approves - always propagates failures.
library;

import 'http_client.dart';
import '../api_config.dart';

/// Compliance decision from orchestrator
class ComplianceDecision {
  final String action;
  final String reason;
  final double riskScore;
  final List<String> warnings;
  final bool integrityVerified;
  final Map<String, dynamic>? details;

  ComplianceDecision({
    required this.action,
    required this.reason,
    required this.riskScore,
    required this.warnings,
    required this.integrityVerified,
    this.details,
  });

  factory ComplianceDecision.fromJson(Map<String, dynamic> json) {
    return ComplianceDecision(
      action: json['action'] as String? ?? 'BLOCK',
      reason: json['reason'] as String? ?? 'Unknown',
      riskScore: (json['risk_score'] as num?)?.toDouble() ?? 1.0,
      warnings: (json['warnings'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      integrityVerified: json['integrity_verified'] as bool? ?? false,
      details: json['details'] as Map<String, dynamic>?,
    );
  }

  bool get isAllowed => action == 'ALLOW' || action == 'APPROVE';
  bool get requiresReview => action == 'REVIEW' || action == 'FLAG';
  bool get requiresEscrow => action == 'ESCROW';
  bool get isBlocked => action == 'BLOCK';
}

/// Integrity verification result
class IntegrityResult {
  final bool verified;
  final String? reason;
  final List<String> violations;
  final bool isDemoMode;

  IntegrityResult({
    required this.verified,
    this.reason,
    this.violations = const [],
    this.isDemoMode = false,
  });

  factory IntegrityResult.fromJson(Map<String, dynamic> json) {
    return IntegrityResult(
      verified: json['verified'] as bool? ?? false,
      reason: json['reason'] as String?,
      violations: (json['violations'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          [],
      isDemoMode: json['demo_mode'] as bool? ?? false,
    );
  }
}

/// Repository for compliance operations
class ComplianceRepository {
  final HttpClient _client;

  ComplianceRepository({HttpClient? client}) : _client = client ?? HttpClient();

  /// Verify UI integrity with server
  /// 
  /// Returns verification result. On network failure, this should NOT
  /// silently approve - the caller must decide how to handle.
  Future<IntegrityResult> verifyIntegrity(Map<String, dynamic> integrityReport) async {
    try {
      final response = await _client.post<Map<String, dynamic>>(
        ApiConfig.integrityVerify,
        data: integrityReport,
      );
      return IntegrityResult.fromJson(response);
    } on ApiException {
      // Re-throw - let caller decide how to handle
      // DO NOT return IntegrityResult(verified: true) here!
      rethrow;
    }
  }

  /// Evaluate transaction with compliance rules
  /// 
  /// IMPORTANT: Throws on failure. Caller must handle errors appropriately.
  Future<ComplianceDecision> evaluateTransaction({
    required String address,
    required String amount,
    required String destination,
    required String profile,
    Map<String, dynamic>? metadata,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.compliance,
      data: {
        'address': address,
        'amount': amount,
        'destination': destination,
        'profile': profile,
        'metadata': metadata ?? {},
      },
    );
    
    return ComplianceDecision.fromJson(response);
  }

  /// Evaluate transaction with integrity verification
  /// 
  /// Combines UI integrity check with compliance evaluation.
  /// IMPORTANT: Throws on failure - never silently approves.
  Future<ComplianceDecision> evaluateWithIntegrity({
    required String address,
    required String amount,
    required String destination,
    required String profile,
    required String intentHash,
    required Map<String, dynamic> integrityReport,
    Map<String, dynamic>? metadata,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.complianceWithIntegrity,
      data: {
        'address': address,
        'amount': amount,
        'destination': destination,
        'profile': profile,
        'intent_hash': intentHash,
        'integrity_report': integrityReport,
        'metadata': metadata ?? {},
      },
    );
    
    return ComplianceDecision.fromJson(response);
  }

  /// Audit integrity report (async logging)
  Future<void> auditIntegrityReport({
    required Map<String, dynamic> report,
    required String action,
    required String outcome,
  }) async {
    try {
      await _client.post<void>(
        ApiConfig.integrityAudit,
        data: {
          'report': report,
          'action': action,
          'outcome': outcome,
          'timestamp': DateTime.now().toIso8601String(),
        },
      );
    } catch (_) {
      // Audit logging is non-critical, but log locally
      print('[AUDIT] Failed to send audit log');
    }
  }
}
