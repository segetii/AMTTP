/// KYC verification repository
library;

import 'package:dio/dio.dart';
import 'http_client.dart';
import '../api_config.dart';

/// KYC verification status
enum KycStatus {
  pending,
  verified,
  rejected,
  expired,
  notStarted,
}

/// KYC verification response
class KycResponse {
  final bool success;
  final String? applicantId;
  final String status;
  final String? redirectUrl;
  final String? errorMessage;

  KycResponse({
    required this.success,
    this.applicantId,
    required this.status,
    this.redirectUrl,
    this.errorMessage,
  });

  factory KycResponse.fromJson(Map<String, dynamic> json) {
    return KycResponse(
      success: json['success'] as bool? ?? false,
      applicantId: json['applicant_id'] as String?,
      status: json['status'] as String? ?? 'unknown',
      redirectUrl: json['redirect_url'] as String?,
      errorMessage: json['error'] as String?,
    );
  }
}

/// KYC status response with details
class KycStatusResponse {
  final KycStatus status;
  final DateTime? verifiedAt;
  final DateTime? expiresAt;
  final String? tier;
  final Map<String, dynamic>? details;

  KycStatusResponse({
    required this.status,
    this.verifiedAt,
    this.expiresAt,
    this.tier,
    this.details,
  });

  factory KycStatusResponse.fromJson(Map<String, dynamic> json) {
    return KycStatusResponse(
      status: _parseStatus(json['status'] as String?),
      verifiedAt: json['verified_at'] != null 
          ? DateTime.tryParse(json['verified_at'])
          : null,
      expiresAt: json['expires_at'] != null
          ? DateTime.tryParse(json['expires_at'])
          : null,
      tier: json['tier'] as String?,
      details: json['details'] as Map<String, dynamic>?,
    );
  }

  static KycStatus _parseStatus(String? status) {
    switch (status?.toLowerCase()) {
      case 'verified':
        return KycStatus.verified;
      case 'pending':
        return KycStatus.pending;
      case 'rejected':
        return KycStatus.rejected;
      case 'expired':
        return KycStatus.expired;
      default:
        return KycStatus.notStarted;
    }
  }

  bool get isVerified => status == KycStatus.verified;
  bool get isPending => status == KycStatus.pending;
  bool get needsResubmission => status == KycStatus.rejected || status == KycStatus.expired;
}

/// Repository for KYC operations
class KycRepository {
  final HttpClient _client;

  KycRepository({HttpClient? client}) : _client = client ?? HttpClient();

  /// Start KYC verification process
  Future<KycResponse> startVerification({
    required String address,
    required String email,
    String? firstName,
    String? lastName,
  }) async {
    final response = await _client.post<Map<String, dynamic>>(
      ApiConfig.kycVerify,
      data: {
        'address': address,
        'email': email,
        if (firstName != null) 'first_name': firstName,
        if (lastName != null) 'last_name': lastName,
      },
    );
    
    return KycResponse.fromJson(response);
  }

  /// Upload KYC document
  Future<KycResponse> uploadDocument({
    required String address,
    required String documentType,
    required String filePath,
    void Function(int, int)? onProgress,
  }) async {
    final formData = FormData.fromMap({
      'address': address,
      'document_type': documentType,
      'document': await MultipartFile.fromFile(filePath),
    });

    final response = await _client.uploadFile<Map<String, dynamic>>(
      '${ApiConfig.kycVerify}/document',
      formData: formData,
      onSendProgress: onProgress,
    );
    
    return KycResponse.fromJson(response);
  }

  /// Get KYC status for an address
  Future<KycStatusResponse> getStatus(String address) async {
    final response = await _client.get<Map<String, dynamic>>(
      '${ApiConfig.kycStatus}/$address',
    );
    
    return KycStatusResponse.fromJson(response);
  }

  /// Refresh/renew KYC verification
  Future<KycResponse> refreshVerification(String address) async {
    final response = await _client.post<Map<String, dynamic>>(
      '${ApiConfig.kycVerify}/refresh',
      data: {'address': address},
    );
    
    return KycResponse.fromJson(response);
  }
}
