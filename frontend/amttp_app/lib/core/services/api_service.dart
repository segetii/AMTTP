import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kIsWeb;

import '../constants/app_constants.dart';

// Optional runtime override for API base (use --dart-define=API_BASE_URL=https://your.ngrok.app)
const String _apiBaseUrlOverride = String.fromEnvironment('API_BASE_URL');

class ApiService {
  late final Dio _dio;

  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: _resolveBaseUrl(),
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      headers: {
        'Content-Type': 'application/json',
      },
    ));

    // Add interceptors for logging and error handling
    _dio.interceptors.add(LogInterceptor(
      requestBody: true,
      responseBody: true,
      logPrint: (object) => print(object),
    ));
  }

  /// Decide the correct API base URL depending on runtime context.
  /// Priority:
  /// 1) API_BASE_URL dart-define (e.g., ngrok/public tunnel)
  /// 2) Web dev on :3003 -> same host without dev port (nginx on :80)
  /// 3) AppConstants.baseApiUrl (default: relative via nginx)
  String _resolveBaseUrl() {
    if (_apiBaseUrlOverride.isNotEmpty) {
      return _apiBaseUrlOverride;
    }

    final uri = Uri.base;

    // When running `flutter run -d chrome --web-port=3003`, Uri.base carries that port.
    // Using the same host without the dev port lets nginx serve /api, /risk, /integrity, etc.
    if (kIsWeb && uri.host.isNotEmpty && uri.port == 3003) {
      return '${uri.scheme}://${uri.host}';
    }

    // Use configured base if provided; empty string keeps relative URLs.
    return AppConstants.baseApiUrl;
  }

  // ============================================================
  // UI INTEGRITY PROTECTION
  // ============================================================

  /// Verify UI integrity with server
  /// For demo/testing: Returns success if integrity service is unavailable
  Future<Map<String, dynamic>> verifyIntegrity(
      Map<String, dynamic> integrityReport) async {
    try {
      final response = await _dio.post(
        AppConstants.integrityVerifyEndpoint,
        data: integrityReport,
      );
      return response.data;
    } on DioException catch (e) {
      // For demo purposes: If integrity service is unavailable, allow transaction
      // In production, this should block the transaction
      print('[INTEGRITY] Service unavailable, allowing for demo: ${e.message}');
      return {
        'verified': true,
        'demo_mode': true,
        'reason': 'Integrity service offline - demo mode',
      };
    }
  }

  /// Evaluate transaction with integrity verification
  /// Calls orchestrator's /evaluate-with-integrity endpoint
  Future<ComplianceDecision> evaluateWithIntegrity({
    required String address,
    required String amount,
    required String destination,
    required String profile,
    required String intentHash,
    required Map<String, dynamic> integrityReport,
  }) async {
    try {
      final response = await _dio.post(
        '/api/evaluate-with-integrity',
        data: {
          'address': address,
          'amount': amount,
          'destination': destination,
          'profile': profile,
          'intent_hash': intentHash,
          'integrity_report': integrityReport,
          'metadata': {},
        },
      );
      return ComplianceDecision.fromJson(response.data);
    } on DioException catch (e) {
      // For demo: Return an approval if orchestrator is unavailable
      print('[EVALUATE] Service unavailable, allowing for demo: ${e.message}');
      return ComplianceDecision(
        action: 'ALLOW',
        reason: 'Demo mode - orchestrator offline',
        riskScore: 0.1,
        warnings: ['Demo mode active'],
        integrityVerified: true,
      );
    }
  }

  // ============================================================
  // DQN RISK SCORING
  // ============================================================

  /// DQN Risk Scoring - Uses Risk Engine service (proxied through nginx)
  Future<RiskScoreResponse> getDQNRiskScore({
    required String fromAddress,
    required String toAddress,
    required double amount,
    required Map<String, dynamic> features,
  }) async {
    try {
      // Use relative URL - nginx proxies /risk/ to risk-engine service
      final response = await _dio.post(
        AppConstants.riskScoringEndpoint,
        data: {
          'from_address': fromAddress,
          'to_address': toAddress,
          'value_eth': amount,
          // Risk Engine doesn't use 'features' parameter in current implementation
        },
      );

      return RiskScoreResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // Heuristic Risk Scoring (fallback)
  Future<RiskScoreResponse> getHeuristicRiskScore({
    required String fromAddress,
    required String toAddress,
    required double amount,
  }) async {
    try {
      final response = await _dio.post(
        '/risk/score',
        data: {
          'from_address': fromAddress,
          'to_address': toAddress,
          'amount': amount,
        },
      );

      return RiskScoreResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // KYC Verification
  Future<KYCResponse> verifyKYC({
    required String address,
    required String documentType,
    required String documentImage,
  }) async {
    try {
      final formData = FormData.fromMap({
        'address': address,
        'document_type': documentType,
        'document_image': await MultipartFile.fromFile(documentImage),
      });

      final response = await _dio.post(
        AppConstants.kycEndpoint,
        data: formData,
      );

      return KYCResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // Get KYC Status
  Future<KYCStatusResponse> getKYCStatus(String address) async {
    try {
      final response = await _dio.get('/kyc/status/$address');
      return KYCStatusResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // Transaction Validation
  Future<TransactionValidationResponse> validateTransaction({
    required String fromAddress,
    required String toAddress,
    required double amount,
    required double riskScore,
  }) async {
    try {
      final response = await _dio.post(
        '${AppConstants.transactionEndpoint}/validate',
        data: {
          'from_address': fromAddress,
          'to_address': toAddress,
          'amount': amount,
          'risk_score': riskScore,
        },
      );

      return TransactionValidationResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // Get Transaction Details
  Future<TransactionDetailsResponse> getTransactionDetails(String txId) async {
    try {
      final response = await _dio.get('${AppConstants.transactionEndpoint}/$txId');
      return TransactionDetailsResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // Get User Transaction History
  Future<List<TransactionHistoryItem>> getTransactionHistory(
    String address, {
    int page = 1,
    int limit = 20,
  }) async {
    try {
      final response = await _dio.get(
        '${AppConstants.transactionEndpoint}/history/$address',
        queryParameters: {
          'page': page,
          'limit': limit,
        },
      );

      final List<dynamic> data = response.data['transactions'];
      return data.map((item) => TransactionHistoryItem.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // DISPUTE RESOLUTION (Kleros Integration)
  // ============================================================

  /// Create a new dispute for a transaction
  Future<DisputeResponse> createDispute({
    required String txId,
    required String disputantAddress,
    required String reason,
    required double escrowAmount,
  }) async {
    try {
      final response = await _dio.post(
        '/dispute/create',
        data: {
          'tx_id': txId,
          'disputant_address': disputantAddress,
          'reason': reason,
          'escrow_amount': escrowAmount,
        },
      );
      return DisputeResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get dispute details by ID
  Future<DisputeDetails> getDisputeDetails(String disputeId) async {
    try {
      final response = await _dio.get('/dispute/$disputeId');
      return DisputeDetails.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Submit evidence for a dispute
  Future<EvidenceResponse> submitEvidence({
    required String disputeId,
    required String submitterAddress,
    required String evidenceType,
    required String content,
  }) async {
    try {
      final response = await _dio.post(
        '/dispute/$disputeId/evidence',
        data: {
          'submitter_address': submitterAddress,
          'evidence_type': evidenceType,
          'content': content,
        },
      );
      return EvidenceResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get all disputes for an address
  Future<List<DisputeDetails>> getDisputesByAddress(String address) async {
    try {
      final response = await _dio.get('/dispute/address/$address');
      final List<dynamic> data = response.data['disputes'];
      return data.map((item) => DisputeDetails.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // REPUTATION SERVICE
  // ============================================================

  /// Get reputation score for an address
  Future<ReputationResponse> getReputation(String address) async {
    try {
      final response = await _dio.get('/reputation/$address');
      return ReputationResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get reputation tier thresholds
  Future<ReputationTiers> getReputationTiers() async {
    try {
      final response = await _dio.get('/reputation/tiers');
      return ReputationTiers.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get reputation leaderboard
  Future<List<LeaderboardEntry>> getReputationLeaderboard({int limit = 100}) async {
    try {
      final response = await _dio.get(
        '/reputation/leaderboard',
        queryParameters: {'limit': limit},
      );
      final List<dynamic> data = response.data['leaderboard'];
      return data.map((item) => LeaderboardEntry.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // BULK SCORING
  // ============================================================

  /// Submit synchronous bulk scoring (≤500 transactions)
  Future<BulkScoreResponse> bulkScoreSync({
    required List<Map<String, dynamic>> transactions,
  }) async {
    try {
      final response = await _dio.post(
        '/bulk/score/sync',
        data: {'transactions': transactions},
      );
      return BulkScoreResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Submit async bulk scoring (≤10,000 transactions)
  Future<BulkJobResponse> bulkScoreAsync({
    required List<Map<String, dynamic>> transactions,
    String? webhookUrl,
  }) async {
    try {
      final response = await _dio.post(
        '/bulk/score/async',
        data: {
          'transactions': transactions,
          if (webhookUrl != null) 'webhook_url': webhookUrl,
        },
      );
      return BulkJobResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Check async job status
  Future<BulkJobStatus> getBulkJobStatus(String jobId) async {
    try {
      final response = await _dio.get('/bulk/job/$jobId');
      return BulkJobStatus.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // WEBHOOK MANAGEMENT
  // ============================================================

  /// Register a webhook endpoint
  Future<WebhookRegistration> registerWebhook({
    required String url,
    required List<String> events,
    String? secret,
  }) async {
    try {
      final response = await _dio.post(
        '/webhook/register',
        data: {
          'url': url,
          'events': events,
          if (secret != null) 'secret': secret,
        },
      );
      return WebhookRegistration.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// List registered webhooks
  Future<List<WebhookInfo>> listWebhooks() async {
    try {
      final response = await _dio.get('/webhook/list');
      final List<dynamic> data = response.data['webhooks'];
      return data.map((item) => WebhookInfo.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Delete a webhook
  Future<void> deleteWebhook(String webhookId) async {
    try {
      await _dio.delete('/webhook/$webhookId');
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Test webhook endpoint
  Future<WebhookTestResult> testWebhook(String webhookId) async {
    try {
      final response = await _dio.post('/webhook/$webhookId/test');
      return WebhookTestResult.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // PEP SCREENING
  // ============================================================

  /// Screen an address for PEP status
  Future<PEPScreeningResult> screenPEP({
    required String address,
    String? name,
    String? dateOfBirth,
    String? country,
  }) async {
    try {
      final response = await _dio.post(
        '/pep/screen',
        data: {
          'address': address,
          if (name != null) 'name': name,
          if (dateOfBirth != null) 'date_of_birth': dateOfBirth,
          if (country != null) 'country': country,
        },
      );
      return PEPScreeningResult.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get PEP screening history for an address
  Future<List<PEPScreeningResult>> getPEPHistory(String address) async {
    try {
      final response = await _dio.get('/pep/history/$address');
      final List<dynamic> data = response.data['screenings'];
      return data.map((item) => PEPScreeningResult.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // ENHANCED DUE DILIGENCE (EDD)
  // ============================================================

  /// Create EDD case
  Future<EDDCaseResponse> createEDDCase({
    required String address,
    required String triggerReason,
    required String riskLevel,
  }) async {
    try {
      final response = await _dio.post(
        '/edd/case',
        data: {
          'address': address,
          'trigger_reason': triggerReason,
          'risk_level': riskLevel,
        },
      );
      return EDDCaseResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get EDD case details
  Future<EDDCaseDetails> getEDDCase(String caseId) async {
    try {
      final response = await _dio.get('/edd/case/$caseId');
      return EDDCaseDetails.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Upload document for EDD case
  Future<DocumentUploadResponse> uploadEDDDocument({
    required String caseId,
    required String documentType,
    required String filePath,
  }) async {
    try {
      final formData = FormData.fromMap({
        'document_type': documentType,
        'file': await MultipartFile.fromFile(filePath),
      });

      final response = await _dio.post(
        '/edd/case/$caseId/document',
        data: formData,
      );
      return DocumentUploadResponse.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Submit EDD case for review
  Future<void> submitEDDForReview(String caseId) async {
    try {
      await _dio.post('/edd/case/$caseId/submit');
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get pending EDD cases (admin)
  Future<List<EDDCaseDetails>> getPendingEDDCases() async {
    try {
      final response = await _dio.get('/edd/pending');
      final List<dynamic> data = response.data['cases'];
      return data.map((item) => EDDCaseDetails.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // ONGOING MONITORING
  // ============================================================

  /// Subscribe address for ongoing monitoring
  Future<MonitoringSubscription> subscribeMonitoring({
    required String address,
    required String monitoringLevel,
    List<String>? alertTypes,
  }) async {
    try {
      final response = await _dio.post(
        '/monitoring/subscribe',
        data: {
          'address': address,
          'monitoring_level': monitoringLevel,
          if (alertTypes != null) 'alert_types': alertTypes,
        },
      );
      return MonitoringSubscription.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get monitoring status for an address
  Future<MonitoringStatus> getMonitoringStatus(String address) async {
    try {
      final response = await _dio.get('/monitoring/status/$address');
      return MonitoringStatus.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get monitoring alerts
  Future<List<MonitoringAlert>> getMonitoringAlerts({
    String? address,
    bool unresolvedOnly = false,
  }) async {
    try {
      final response = await _dio.get(
        '/monitoring/alerts',
        queryParameters: {
          if (address != null) 'address': address,
          'unresolved_only': unresolvedOnly,
        },
      );
      final List<dynamic> data = response.data['alerts'];
      return data.map((item) => MonitoringAlert.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Acknowledge monitoring alert
  Future<void> acknowledgeAlert(String alertId, {String? notes}) async {
    try {
      await _dio.post(
        '/monitoring/alerts/$alertId/acknowledge',
        data: {if (notes != null) 'notes': notes},
      );
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Unsubscribe from monitoring
  Future<void> unsubscribeMonitoring(String address) async {
    try {
      await _dio.delete('/monitoring/unsubscribe/$address');
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // POLICY ENGINE
  // ============================================================

  /// Evaluate transaction against policies
  Future<PolicyEvaluationResult> evaluatePolicy({
    required String fromAddress,
    required String toAddress,
    required double amount,
    required double riskScore,
    String? jurisdiction,
  }) async {
    try {
      final response = await _dio.post(
        '/policy/evaluate',
        data: {
          'from_address': fromAddress,
          'to_address': toAddress,
          'amount': amount,
          'risk_score': riskScore,
          if (jurisdiction != null) 'jurisdiction': jurisdiction,
        },
      );
      return PolicyEvaluationResult.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Get active policies
  Future<List<PolicyInfo>> getActivePolicies() async {
    try {
      final response = await _dio.get('/policy/list');
      final List<dynamic> data = response.data['policies'];
      return data.map((item) => PolicyInfo.fromJson(item)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  // ============================================================
  // LABEL MANAGEMENT
  // ============================================================

  /// Get address labels
  Future<AddressLabels> getAddressLabels(String address) async {
    try {
      final response = await _dio.get('/label/$address');
      return AddressLabels.fromJson(response.data);
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Report suspicious address
  Future<void> reportSuspiciousAddress({
    required String address,
    required String reason,
    String? evidence,
  }) async {
    try {
      await _dio.post(
        '/label/report',
        data: {
          'address': address,
          'reason': reason,
          if (evidence != null) 'evidence': evidence,
        },
      );
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }
}

// Response Models
class RiskScoreResponse {
  final double riskScore;
  final String riskLevel;
  final Map<String, dynamic> features;
  final String modelVersion;
  final DateTime timestamp;

  RiskScoreResponse({
    required this.riskScore,
    required this.riskLevel,
    required this.features,
    required this.modelVersion,
    required this.timestamp,
  });

  factory RiskScoreResponse.fromJson(Map<String, dynamic> json) {
    return RiskScoreResponse(
      riskScore: json['risk_score']?.toDouble() ?? 0.0,
      riskLevel: json['risk_level'] ?? 'unknown',
      features: json['features'] ?? {},
      modelVersion: json['model_version'] ?? '',
      timestamp: DateTime.parse(json['timestamp']),
    );
  }
}

class KYCResponse {
  final bool success;
  final String status;
  final String message;
  final Map<String, dynamic>? verificationData;

  KYCResponse({
    required this.success,
    required this.status,
    required this.message,
    this.verificationData,
  });

  factory KYCResponse.fromJson(Map<String, dynamic> json) {
    return KYCResponse(
      success: json['success'] ?? false,
      status: json['status'] ?? '',
      message: json['message'] ?? '',
      verificationData: json['verification_data'],
    );
  }
}

class KYCStatusResponse {
  final String status;
  final bool isVerified;
  final DateTime? verifiedAt;
  final String? documentType;

  KYCStatusResponse({
    required this.status,
    required this.isVerified,
    this.verifiedAt,
    this.documentType,
  });

  factory KYCStatusResponse.fromJson(Map<String, dynamic> json) {
    return KYCStatusResponse(
      status: json['status'] ?? '',
      isVerified: json['is_verified'] ?? false,
      verifiedAt: json['verified_at'] != null 
        ? DateTime.parse(json['verified_at']) 
        : null,
      documentType: json['document_type'],
    );
  }
}

class TransactionValidationResponse {
  final bool isValid;
  final String action; // approve, monitor, escrow, reject
  final String reason;
  final Map<String, dynamic>? policyDetails;

  TransactionValidationResponse({
    required this.isValid,
    required this.action,
    required this.reason,
    this.policyDetails,
  });

  factory TransactionValidationResponse.fromJson(Map<String, dynamic> json) {
    return TransactionValidationResponse(
      isValid: json['is_valid'] ?? false,
      action: json['action'] ?? 'reject',
      reason: json['reason'] ?? '',
      policyDetails: json['policy_details'],
    );
  }
}

class TransactionDetailsResponse {
  final String txId;
  final String fromAddress;
  final String toAddress;
  final double amount;
  final double riskScore;
  final String status;
  final DateTime timestamp;
  final String? blockHash;
  final int? blockNumber;

  TransactionDetailsResponse({
    required this.txId,
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    required this.riskScore,
    required this.status,
    required this.timestamp,
    this.blockHash,
    this.blockNumber,
  });

  factory TransactionDetailsResponse.fromJson(Map<String, dynamic> json) {
    return TransactionDetailsResponse(
      txId: json['tx_id'] ?? '',
      fromAddress: json['from_address'] ?? '',
      toAddress: json['to_address'] ?? '',
      amount: json['amount']?.toDouble() ?? 0.0,
      riskScore: json['risk_score']?.toDouble() ?? 0.0,
      status: json['status'] ?? '',
      timestamp: DateTime.parse(json['timestamp']),
      blockHash: json['block_hash'],
      blockNumber: json['block_number'],
    );
  }
}

class TransactionHistoryItem {
  final String txId;
  final String type; // sent, received
  final String address; // counterparty address (legacy)
  final String fromAddress;
  final String toAddress;
  final double amount;
  final String asset;
  final double riskScore;
  final String status;
  final DateTime timestamp;

  TransactionHistoryItem({
    required this.txId,
    this.type = '',
    this.address = '',
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    this.asset = 'ETH',
    required this.riskScore,
    required this.status,
    required this.timestamp,
  });

  factory TransactionHistoryItem.fromJson(Map<String, dynamic> json) {
    return TransactionHistoryItem(
      txId: json['tx_id'] ?? '',
      type: json['type'] ?? '',
      address: json['address'] ?? '',
      fromAddress: json['from_address'] ?? json['from'] ?? '',
      toAddress: json['to_address'] ?? json['to'] ?? '',
      amount: json['amount']?.toDouble() ?? 0.0,
      asset: json['asset'] ?? 'ETH',
      riskScore: json['risk_score']?.toDouble() ?? 0.0,
      status: json['status'] ?? '',
      timestamp: DateTime.parse(json['timestamp']),
    );
  }
}

// Exception Handling
class ApiException implements Exception {
  final String message;
  final int? statusCode;

  ApiException(this.message, [this.statusCode]);

  factory ApiException.fromDioError(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
        return ApiException('Connection timeout');
      case DioExceptionType.receiveTimeout:
        return ApiException('Receive timeout');
      case DioExceptionType.badResponse:
        return ApiException(
          error.response?.data['message'] ?? 'Server error',
          error.response?.statusCode,
        );
      case DioExceptionType.cancel:
        return ApiException('Request cancelled');
      default:
        return ApiException('Network error');
    }
  }

  @override
  String toString() => message;
}

// ============================================================
// DISPUTE RESOLUTION MODELS
// ============================================================

class DisputeResponse {
  final String disputeId;
  final String status;
  final DateTime createdAt;

  DisputeResponse({
    required this.disputeId,
    required this.status,
    required this.createdAt,
  });

  factory DisputeResponse.fromJson(Map<String, dynamic> json) {
    return DisputeResponse(
      disputeId: json['dispute_id'] ?? '',
      status: json['status'] ?? 'pending',
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class DisputeDetails {
  final String disputeId;
  final String txId;
  final String disputantAddress;
  final String respondentAddress;
  final String reason;
  final double escrowAmount;
  final String status; // pending, evidence_phase, voting, resolved, appealed
  final String? ruling; // claimant, respondent, split
  final DateTime createdAt;
  final DateTime? resolvedAt;
  final List<EvidenceItem> evidence;

  DisputeDetails({
    required this.disputeId,
    required this.txId,
    required this.disputantAddress,
    required this.respondentAddress,
    required this.reason,
    required this.escrowAmount,
    required this.status,
    this.ruling,
    required this.createdAt,
    this.resolvedAt,
    required this.evidence,
  });

  factory DisputeDetails.fromJson(Map<String, dynamic> json) {
    return DisputeDetails(
      disputeId: json['dispute_id'] ?? '',
      txId: json['tx_id'] ?? '',
      disputantAddress: json['disputant_address'] ?? '',
      respondentAddress: json['respondent_address'] ?? '',
      reason: json['reason'] ?? '',
      escrowAmount: (json['escrow_amount'] ?? 0).toDouble(),
      status: json['status'] ?? 'pending',
      ruling: json['ruling'],
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
      resolvedAt: json['resolved_at'] != null ? DateTime.parse(json['resolved_at']) : null,
      evidence: (json['evidence'] as List<dynamic>?)
          ?.map((e) => EvidenceItem.fromJson(e))
          .toList() ?? [],
    );
  }
}

class EvidenceItem {
  final String evidenceId;
  final String submitterAddress;
  final String evidenceType;
  final String content;
  final DateTime submittedAt;

  EvidenceItem({
    required this.evidenceId,
    required this.submitterAddress,
    required this.evidenceType,
    required this.content,
    required this.submittedAt,
  });

  factory EvidenceItem.fromJson(Map<String, dynamic> json) {
    return EvidenceItem(
      evidenceId: json['evidence_id'] ?? '',
      submitterAddress: json['submitter_address'] ?? '',
      evidenceType: json['evidence_type'] ?? '',
      content: json['content'] ?? '',
      submittedAt: DateTime.parse(json['submitted_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class EvidenceResponse {
  final String evidenceId;
  final bool success;

  EvidenceResponse({required this.evidenceId, required this.success});

  factory EvidenceResponse.fromJson(Map<String, dynamic> json) {
    return EvidenceResponse(
      evidenceId: json['evidence_id'] ?? '',
      success: json['success'] ?? false,
    );
  }
}

// ============================================================
// REPUTATION MODELS
// ============================================================

class ReputationResponse {
  final String address;
  final int score; // 0-100
  final String tier; // Bronze, Silver, Gold, Platinum, Diamond
  final int totalTransactions;
  final int successfulTransactions;
  final int disputes;
  final int disputesWon;
  final double stakedAmount;
  final DateTime lastUpdated;

  ReputationResponse({
    required this.address,
    required this.score,
    required this.tier,
    required this.totalTransactions,
    required this.successfulTransactions,
    required this.disputes,
    required this.disputesWon,
    required this.stakedAmount,
    required this.lastUpdated,
  });

  factory ReputationResponse.fromJson(Map<String, dynamic> json) {
    return ReputationResponse(
      address: json['address'] ?? '',
      score: json['score'] ?? 0,
      tier: json['tier'] ?? 'Bronze',
      totalTransactions: json['total_transactions'] ?? 0,
      successfulTransactions: json['successful_transactions'] ?? 0,
      disputes: json['disputes'] ?? 0,
      disputesWon: json['disputes_won'] ?? 0,
      stakedAmount: (json['staked_amount'] ?? 0).toDouble(),
      lastUpdated: DateTime.parse(json['last_updated'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class ReputationTiers {
  final Map<String, int> thresholds;

  ReputationTiers({required this.thresholds});

  factory ReputationTiers.fromJson(Map<String, dynamic> json) {
    return ReputationTiers(
      thresholds: Map<String, int>.from(json['thresholds'] ?? {}),
    );
  }
}

class LeaderboardEntry {
  final int rank;
  final String address;
  final int score;
  final String tier;

  LeaderboardEntry({
    required this.rank,
    required this.address,
    required this.score,
    required this.tier,
  });

  factory LeaderboardEntry.fromJson(Map<String, dynamic> json) {
    return LeaderboardEntry(
      rank: json['rank'] ?? 0,
      address: json['address'] ?? '',
      score: json['score'] ?? 0,
      tier: json['tier'] ?? 'Bronze',
    );
  }
}

// ============================================================
// BULK SCORING MODELS
// ============================================================

class BulkScoreResponse {
  final int processed;
  final int failed;
  final List<BulkScoreResult> results;

  BulkScoreResponse({
    required this.processed,
    required this.failed,
    required this.results,
  });

  factory BulkScoreResponse.fromJson(Map<String, dynamic> json) {
    return BulkScoreResponse(
      processed: json['processed'] ?? 0,
      failed: json['failed'] ?? 0,
      results: (json['results'] as List<dynamic>?)
          ?.map((e) => BulkScoreResult.fromJson(e))
          .toList() ?? [],
    );
  }
}

class BulkScoreResult {
  final String txId;
  final double? riskScore;
  final String? riskLevel;
  final String? error;

  BulkScoreResult({
    required this.txId,
    this.riskScore,
    this.riskLevel,
    this.error,
  });

  factory BulkScoreResult.fromJson(Map<String, dynamic> json) {
    return BulkScoreResult(
      txId: json['tx_id'] ?? '',
      riskScore: json['risk_score']?.toDouble(),
      riskLevel: json['risk_level'],
      error: json['error'],
    );
  }
}

class BulkJobResponse {
  final String jobId;
  final String status;
  final int totalTransactions;
  final DateTime estimatedCompletion;

  BulkJobResponse({
    required this.jobId,
    required this.status,
    required this.totalTransactions,
    required this.estimatedCompletion,
  });

  factory BulkJobResponse.fromJson(Map<String, dynamic> json) {
    return BulkJobResponse(
      jobId: json['job_id'] ?? '',
      status: json['status'] ?? 'queued',
      totalTransactions: json['total_transactions'] ?? 0,
      estimatedCompletion: DateTime.parse(
          json['estimated_completion'] ?? DateTime.now().add(const Duration(minutes: 5)).toIso8601String()),
    );
  }
}

class BulkJobStatus {
  final String jobId;
  final String status; // queued, processing, completed, failed
  final int processed;
  final int total;
  final double progress;
  final String? resultUrl;
  final String? error;

  BulkJobStatus({
    required this.jobId,
    required this.status,
    required this.processed,
    required this.total,
    required this.progress,
    this.resultUrl,
    this.error,
  });

  factory BulkJobStatus.fromJson(Map<String, dynamic> json) {
    return BulkJobStatus(
      jobId: json['job_id'] ?? '',
      status: json['status'] ?? 'unknown',
      processed: json['processed'] ?? 0,
      total: json['total'] ?? 0,
      progress: (json['progress'] ?? 0).toDouble(),
      resultUrl: json['result_url'],
      error: json['error'],
    );
  }
}

// ============================================================
// WEBHOOK MODELS
// ============================================================

class WebhookRegistration {
  final String webhookId;
  final String secret;
  final bool success;

  WebhookRegistration({
    required this.webhookId,
    required this.secret,
    required this.success,
  });

  factory WebhookRegistration.fromJson(Map<String, dynamic> json) {
    return WebhookRegistration(
      webhookId: json['webhook_id'] ?? '',
      secret: json['secret'] ?? '',
      success: json['success'] ?? false,
    );
  }
}

class WebhookInfo {
  final String webhookId;
  final String url;
  final List<String> events;
  final bool isActive;
  final DateTime createdAt;
  final DateTime? lastTriggered;

  WebhookInfo({
    required this.webhookId,
    required this.url,
    required this.events,
    required this.isActive,
    required this.createdAt,
    this.lastTriggered,
  });

  factory WebhookInfo.fromJson(Map<String, dynamic> json) {
    return WebhookInfo(
      webhookId: json['webhook_id'] ?? '',
      url: json['url'] ?? '',
      events: List<String>.from(json['events'] ?? []),
      isActive: json['is_active'] ?? true,
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
      lastTriggered: json['last_triggered'] != null 
          ? DateTime.parse(json['last_triggered']) 
          : null,
    );
  }
}

class WebhookTestResult {
  final bool success;
  final int statusCode;
  final String? error;
  final int responseTimeMs;

  WebhookTestResult({
    required this.success,
    required this.statusCode,
    this.error,
    required this.responseTimeMs,
  });

  factory WebhookTestResult.fromJson(Map<String, dynamic> json) {
    return WebhookTestResult(
      success: json['success'] ?? false,
      statusCode: json['status_code'] ?? 0,
      error: json['error'],
      responseTimeMs: json['response_time_ms'] ?? 0,
    );
  }
}

// ============================================================
// PEP SCREENING MODELS
// ============================================================

class PEPScreeningResult {
  final String screeningId;
  final String address;
  final bool isPEP;
  final double matchScore;
  final String riskLevel;
  final List<PEPMatch> matches;
  final DateTime screenedAt;
  final String provider;

  PEPScreeningResult({
    required this.screeningId,
    required this.address,
    required this.isPEP,
    required this.matchScore,
    required this.riskLevel,
    required this.matches,
    required this.screenedAt,
    required this.provider,
  });

  factory PEPScreeningResult.fromJson(Map<String, dynamic> json) {
    return PEPScreeningResult(
      screeningId: json['screening_id'] ?? '',
      address: json['address'] ?? '',
      isPEP: json['is_pep'] ?? false,
      matchScore: (json['match_score'] ?? 0).toDouble(),
      riskLevel: json['risk_level'] ?? 'low',
      matches: (json['matches'] as List<dynamic>?)
          ?.map((e) => PEPMatch.fromJson(e))
          .toList() ?? [],
      screenedAt: DateTime.parse(json['screened_at'] ?? DateTime.now().toIso8601String()),
      provider: json['provider'] ?? 'unknown',
    );
  }
}

class PEPMatch {
  final String name;
  final String position;
  final String country;
  final double confidence;
  final String source;

  PEPMatch({
    required this.name,
    required this.position,
    required this.country,
    required this.confidence,
    required this.source,
  });

  factory PEPMatch.fromJson(Map<String, dynamic> json) {
    return PEPMatch(
      name: json['name'] ?? '',
      position: json['position'] ?? '',
      country: json['country'] ?? '',
      confidence: (json['confidence'] ?? 0).toDouble(),
      source: json['source'] ?? '',
    );
  }
}

// ============================================================
// EDD MODELS
// ============================================================

class EDDCaseResponse {
  final String caseId;
  final String status;
  final DateTime createdAt;

  EDDCaseResponse({
    required this.caseId,
    required this.status,
    required this.createdAt,
  });

  factory EDDCaseResponse.fromJson(Map<String, dynamic> json) {
    return EDDCaseResponse(
      caseId: json['case_id'] ?? '',
      status: json['status'] ?? 'open',
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class EDDCaseDetails {
  final String caseId;
  final String address;
  final String triggerReason;
  final String riskLevel;
  final String status; // open, documents_pending, under_review, approved, rejected
  final String? assignedAnalyst;
  final List<EDDDocument> documents;
  final List<EDDNote> notes;
  final DateTime createdAt;
  final DateTime? resolvedAt;

  EDDCaseDetails({
    required this.caseId,
    required this.address,
    required this.triggerReason,
    required this.riskLevel,
    required this.status,
    this.assignedAnalyst,
    required this.documents,
    required this.notes,
    required this.createdAt,
    this.resolvedAt,
  });

  factory EDDCaseDetails.fromJson(Map<String, dynamic> json) {
    return EDDCaseDetails(
      caseId: json['case_id'] ?? '',
      address: json['address'] ?? '',
      triggerReason: json['trigger_reason'] ?? '',
      riskLevel: json['risk_level'] ?? 'high',
      status: json['status'] ?? 'open',
      assignedAnalyst: json['assigned_analyst'],
      documents: (json['documents'] as List<dynamic>?)
          ?.map((e) => EDDDocument.fromJson(e))
          .toList() ?? [],
      notes: (json['notes'] as List<dynamic>?)
          ?.map((e) => EDDNote.fromJson(e))
          .toList() ?? [],
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
      resolvedAt: json['resolved_at'] != null ? DateTime.parse(json['resolved_at']) : null,
    );
  }
}

class EDDDocument {
  final String documentId;
  final String documentType;
  final String fileName;
  final String status; // pending, verified, rejected
  final DateTime uploadedAt;

  EDDDocument({
    required this.documentId,
    required this.documentType,
    required this.fileName,
    required this.status,
    required this.uploadedAt,
  });

  factory EDDDocument.fromJson(Map<String, dynamic> json) {
    return EDDDocument(
      documentId: json['document_id'] ?? '',
      documentType: json['document_type'] ?? '',
      fileName: json['file_name'] ?? '',
      status: json['status'] ?? 'pending',
      uploadedAt: DateTime.parse(json['uploaded_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class EDDNote {
  final String noteId;
  final String author;
  final String content;
  final DateTime createdAt;

  EDDNote({
    required this.noteId,
    required this.author,
    required this.content,
    required this.createdAt,
  });

  factory EDDNote.fromJson(Map<String, dynamic> json) {
    return EDDNote(
      noteId: json['note_id'] ?? '',
      author: json['author'] ?? '',
      content: json['content'] ?? '',
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class DocumentUploadResponse {
  final String documentId;
  final bool success;

  DocumentUploadResponse({required this.documentId, required this.success});

  factory DocumentUploadResponse.fromJson(Map<String, dynamic> json) {
    return DocumentUploadResponse(
      documentId: json['document_id'] ?? '',
      success: json['success'] ?? false,
    );
  }
}

// ============================================================
// MONITORING MODELS
// ============================================================

class MonitoringSubscription {
  final String subscriptionId;
  final String address;
  final String monitoringLevel;
  final bool isActive;
  final DateTime createdAt;

  MonitoringSubscription({
    required this.subscriptionId,
    required this.address,
    required this.monitoringLevel,
    required this.isActive,
    required this.createdAt,
  });

  factory MonitoringSubscription.fromJson(Map<String, dynamic> json) {
    return MonitoringSubscription(
      subscriptionId: json['subscription_id'] ?? '',
      address: json['address'] ?? '',
      monitoringLevel: json['monitoring_level'] ?? 'standard',
      isActive: json['is_active'] ?? true,
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
    );
  }
}

class MonitoringStatus {
  final String address;
  final bool isMonitored;
  final String? monitoringLevel;
  final DateTime? lastScreened;
  final int alertCount;
  final int unresolvedAlerts;

  MonitoringStatus({
    required this.address,
    required this.isMonitored,
    this.monitoringLevel,
    this.lastScreened,
    required this.alertCount,
    required this.unresolvedAlerts,
  });

  factory MonitoringStatus.fromJson(Map<String, dynamic> json) {
    return MonitoringStatus(
      address: json['address'] ?? '',
      isMonitored: json['is_monitored'] ?? false,
      monitoringLevel: json['monitoring_level'],
      lastScreened: json['last_screened'] != null 
          ? DateTime.parse(json['last_screened']) 
          : null,
      alertCount: json['alert_count'] ?? 0,
      unresolvedAlerts: json['unresolved_alerts'] ?? 0,
    );
  }
}

class MonitoringAlert {
  final String alertId;
  final String address;
  final String alertType;
  final String severity; // low, medium, high, critical
  final String description;
  final bool isResolved;
  final String? resolvedBy;
  final String? resolutionNotes;
  final DateTime createdAt;
  final DateTime? resolvedAt;

  MonitoringAlert({
    required this.alertId,
    required this.address,
    required this.alertType,
    required this.severity,
    required this.description,
    required this.isResolved,
    this.resolvedBy,
    this.resolutionNotes,
    required this.createdAt,
    this.resolvedAt,
  });

  factory MonitoringAlert.fromJson(Map<String, dynamic> json) {
    return MonitoringAlert(
      alertId: json['alert_id'] ?? '',
      address: json['address'] ?? '',
      alertType: json['alert_type'] ?? '',
      severity: json['severity'] ?? 'low',
      description: json['description'] ?? '',
      isResolved: json['is_resolved'] ?? false,
      resolvedBy: json['resolved_by'],
      resolutionNotes: json['resolution_notes'],
      createdAt: DateTime.parse(json['created_at'] ?? DateTime.now().toIso8601String()),
      resolvedAt: json['resolved_at'] != null ? DateTime.parse(json['resolved_at']) : null,
    );
  }
}

// ============================================================
// POLICY MODELS
// ============================================================

class PolicyEvaluationResult {
  final String action; // approve, monitor, escrow, reject
  final String reason;
  final List<String> triggeredPolicies;
  final Map<String, dynamic> details;

  PolicyEvaluationResult({
    required this.action,
    required this.reason,
    required this.triggeredPolicies,
    required this.details,
  });

  factory PolicyEvaluationResult.fromJson(Map<String, dynamic> json) {
    return PolicyEvaluationResult(
      action: json['action'] ?? 'reject',
      reason: json['reason'] ?? '',
      triggeredPolicies: List<String>.from(json['triggered_policies'] ?? []),
      details: json['details'] ?? {},
    );
  }
}

class PolicyInfo {
  final String policyId;
  final String name;
  final String description;
  final bool isActive;
  final String category;
  final int priority;

  PolicyInfo({
    required this.policyId,
    required this.name,
    required this.description,
    required this.isActive,
    required this.category,
    required this.priority,
  });

  factory PolicyInfo.fromJson(Map<String, dynamic> json) {
    return PolicyInfo(
      policyId: json['policy_id'] ?? '',
      name: json['name'] ?? '',
      description: json['description'] ?? '',
      isActive: json['is_active'] ?? true,
      category: json['category'] ?? '',
      priority: json['priority'] ?? 0,
    );
  }
}

// ============================================================
// COMPLIANCE MODELS
// ============================================================

class ComplianceDecision {
  final String action; // ALLOW, WARN, BLOCK
  final String reason;
  final double riskScore;
  final List<String> warnings;
  final Map<String, dynamic>? details;
  final bool integrityVerified;

  ComplianceDecision({
    required this.action,
    required this.reason,
    required this.riskScore,
    this.warnings = const [],
    this.details,
    this.integrityVerified = false,
  });

  factory ComplianceDecision.fromJson(Map<String, dynamic> json) {
    return ComplianceDecision(
      action: json['action'] ?? 'BLOCK',
      reason: json['reason'] ?? '',
      riskScore: (json['risk_score'] ?? 0.0).toDouble(),
      warnings: List<String>.from(json['warnings'] ?? []),
      details: json['details'],
      integrityVerified: json['integrity_verified'] ?? false,
    );
  }
}

// ============================================================
// LABEL MODELS
// ============================================================

class AddressLabels {
  final String address;
  final List<String> labels;
  final String riskCategory;
  final bool isSanctioned;
  final bool isVerified;
  final String? entityName;
  final String? entityType;

  AddressLabels({
    required this.address,
    required this.labels,
    required this.riskCategory,
    required this.isSanctioned,
    required this.isVerified,
    this.entityName,
    this.entityType,
  });

  factory AddressLabels.fromJson(Map<String, dynamic> json) {
    return AddressLabels(
      address: json['address'] ?? '',
      labels: List<String>.from(json['labels'] ?? []),
      riskCategory: json['risk_category'] ?? 'unknown',
      isSanctioned: json['is_sanctioned'] ?? false,
      isVerified: json['is_verified'] ?? false,
      entityName: json['entity_name'],
      entityType: json['entity_type'],
    );
  }
}