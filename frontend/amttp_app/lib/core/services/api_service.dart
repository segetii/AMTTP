import 'package:dio/dio.dart';
import '../constants/app_constants.dart';

class ApiService {
  late final Dio _dio;

  ApiService() {
    _dio = Dio(BaseOptions(
      baseUrl: AppConstants.baseApiUrl,
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

  // DQN Risk Scoring
  Future<RiskScoreResponse> getDQNRiskScore({
    required String fromAddress,
    required String toAddress,
    required double amount,
    required Map<String, dynamic> features,
  }) async {
    try {
      final response = await _dio.post(
        AppConstants.riskScoringEndpoint,
        data: {
          'from_address': fromAddress,
          'to_address': toAddress,
          'transaction_amount': amount,
          'features': features,
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
  final String address; // counterparty address
  final double amount;
  final double riskScore;
  final String status;
  final DateTime timestamp;

  TransactionHistoryItem({
    required this.txId,
    required this.type,
    required this.address,
    required this.amount,
    required this.riskScore,
    required this.status,
    required this.timestamp,
  });

  factory TransactionHistoryItem.fromJson(Map<String, dynamic> json) {
    return TransactionHistoryItem(
      txId: json['tx_id'] ?? '',
      type: json['type'] ?? '',
      address: json['address'] ?? '',
      amount: json['amount']?.toDouble() ?? 0.0,
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