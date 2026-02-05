import 'result.dart';

/// Standard API exception types for consistent error handling
/// 
/// These exceptions provide structured error information for
/// API-related failures with proper error codes and messages.

/// Base class for all API exceptions
class ApiException extends AppException {
  final int? statusCode;
  final Map<String, dynamic>? responseBody;
  final String? requestId;

  const ApiException({
    required super.message,
    super.code,
    super.originalError,
    super.stackTrace,
    this.statusCode,
    this.responseBody,
    this.requestId,
  });

  @override
  String toString() => 'ApiException: $message (status: $statusCode, code: $code)';
}

/// Network connectivity issues
class NetworkException extends ApiException {
  const NetworkException({
    super.message = 'Network connection failed. Please check your internet connection.',
    super.code = 'NETWORK_ERROR',
    super.originalError,
    super.stackTrace,
  }) : super(statusCode: null);

  factory NetworkException.timeout() => const NetworkException(
        message: 'Request timed out. Please try again.',
        code: 'TIMEOUT',
      );

  factory NetworkException.noInternet() => const NetworkException(
        message: 'No internet connection. Please check your network.',
        code: 'NO_INTERNET',
      );
}

/// Server-side errors (5xx)
class ServerException extends ApiException {
  const ServerException({
    super.message = 'Server error occurred. Please try again later.',
    super.code = 'SERVER_ERROR',
    super.statusCode = 500,
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
  });

  factory ServerException.unavailable() => const ServerException(
        message: 'Service temporarily unavailable. Please try again later.',
        code: 'SERVICE_UNAVAILABLE',
        statusCode: 503,
      );

  factory ServerException.maintenance() => const ServerException(
        message: 'Server is under maintenance. Please try again later.',
        code: 'MAINTENANCE',
        statusCode: 503,
      );
}

/// Client-side errors (4xx)
class ClientException extends ApiException {
  const ClientException({
    required super.message,
    super.code = 'CLIENT_ERROR',
    super.statusCode = 400,
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
  });

  factory ClientException.badRequest({String? message}) => ClientException(
        message: message ?? 'Invalid request. Please check your input.',
        code: 'BAD_REQUEST',
        statusCode: 400,
      );

  factory ClientException.notFound({String? resource}) => ClientException(
        message: resource != null 
            ? '$resource not found.' 
            : 'Requested resource not found.',
        code: 'NOT_FOUND',
        statusCode: 404,
      );

  factory ClientException.conflict({String? message}) => ClientException(
        message: message ?? 'Operation conflicts with current state.',
        code: 'CONFLICT',
        statusCode: 409,
      );

  factory ClientException.tooManyRequests() => const ClientException(
        message: 'Too many requests. Please wait and try again.',
        code: 'RATE_LIMITED',
        statusCode: 429,
      );
}

/// Authentication errors
class AuthException extends ApiException {
  const AuthException({
    super.message = 'Authentication required. Please sign in.',
    super.code = 'AUTH_ERROR',
    super.statusCode = 401,
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
  });

  factory AuthException.unauthorized() => const AuthException(
        message: 'Please sign in to continue.',
        code: 'UNAUTHORIZED',
        statusCode: 401,
      );

  factory AuthException.forbidden() => const AuthException(
        message: 'You do not have permission to perform this action.',
        code: 'FORBIDDEN',
        statusCode: 403,
      );

  factory AuthException.tokenExpired() => const AuthException(
        message: 'Your session has expired. Please sign in again.',
        code: 'TOKEN_EXPIRED',
        statusCode: 401,
      );

  factory AuthException.invalidCredentials() => const AuthException(
        message: 'Invalid credentials. Please check and try again.',
        code: 'INVALID_CREDENTIALS',
        statusCode: 401,
      );
}

/// Validation errors
class ValidationException extends ApiException {
  final Map<String, List<String>>? fieldErrors;

  const ValidationException({
    super.message = 'Validation failed. Please check your input.',
    super.code = 'VALIDATION_ERROR',
    super.statusCode = 422,
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
    this.fieldErrors,
  });

  factory ValidationException.fromFieldErrors(Map<String, List<String>> errors) {
    final messages = errors.entries
        .map((e) => '${e.key}: ${e.value.join(', ')}')
        .join('; ');
    return ValidationException(
      message: messages.isEmpty ? 'Validation failed' : messages,
      fieldErrors: errors,
    );
  }

  /// Gets errors for a specific field
  List<String>? errorsForField(String field) => fieldErrors?[field];

  /// Returns true if a field has errors
  bool hasErrorsForField(String field) => 
      fieldErrors?.containsKey(field) ?? false;
}

/// Blockchain-specific errors
class BlockchainException extends ApiException {
  const BlockchainException({
    required super.message,
    super.code = 'BLOCKCHAIN_ERROR',
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
  }) : super(statusCode: null);

  factory BlockchainException.insufficientFunds() => const BlockchainException(
        message: 'Insufficient funds for this transaction.',
        code: 'INSUFFICIENT_FUNDS',
      );

  factory BlockchainException.gasEstimationFailed() => const BlockchainException(
        message: 'Failed to estimate gas. Transaction may fail.',
        code: 'GAS_ESTIMATION_FAILED',
      );

  factory BlockchainException.transactionFailed({String? reason}) => 
      BlockchainException(
        message: reason ?? 'Transaction failed. Please try again.',
        code: 'TRANSACTION_FAILED',
      );

  factory BlockchainException.walletRejected() => const BlockchainException(
        message: 'Transaction rejected by wallet.',
        code: 'WALLET_REJECTED',
      );

  factory BlockchainException.networkMismatch() => const BlockchainException(
        message: 'Please switch to the correct network.',
        code: 'NETWORK_MISMATCH',
      );

  factory BlockchainException.contractError({String? message}) => 
      BlockchainException(
        message: message ?? 'Smart contract error occurred.',
        code: 'CONTRACT_ERROR',
      );
}

/// Risk engine specific errors
class RiskEngineException extends ApiException {
  final double? riskScore;
  final List<String>? riskFactors;

  const RiskEngineException({
    required super.message,
    super.code = 'RISK_ERROR',
    super.originalError,
    super.stackTrace,
    super.responseBody,
    super.requestId,
    this.riskScore,
    this.riskFactors,
  }) : super(statusCode: null);

  factory RiskEngineException.highRisk({
    required double score,
    List<String>? factors,
  }) => RiskEngineException(
        message: 'Transaction blocked due to high risk score.',
        code: 'HIGH_RISK',
        riskScore: score,
        riskFactors: factors,
      );

  factory RiskEngineException.analysisTimeout() => const RiskEngineException(
        message: 'Risk analysis timed out. Please try again.',
        code: 'ANALYSIS_TIMEOUT',
      );

  factory RiskEngineException.serviceUnavailable() => const RiskEngineException(
        message: 'Risk engine temporarily unavailable.',
        code: 'SERVICE_UNAVAILABLE',
      );
}

/// Parsing/serialization errors
class ParseException extends AppException {
  const ParseException({
    super.message = 'Failed to parse response.',
    super.code = 'PARSE_ERROR',
    super.originalError,
    super.stackTrace,
  });

  factory ParseException.invalidJson() => const ParseException(
        message: 'Invalid JSON response from server.',
        code: 'INVALID_JSON',
      );

  factory ParseException.missingField(String field) => ParseException(
        message: 'Missing required field: $field',
        code: 'MISSING_FIELD',
      );

  factory ParseException.invalidType(String field, String expected) => 
      ParseException(
        message: 'Invalid type for $field. Expected $expected.',
        code: 'INVALID_TYPE',
      );
}

/// Helper to create exception from HTTP status code
ApiException exceptionFromStatusCode(
  int statusCode, {
  String? message,
  String? code,
  Map<String, dynamic>? responseBody,
  String? requestId,
}) {
  switch (statusCode) {
    case 400:
      return ClientException.badRequest(message: message);
    case 401:
      return AuthException.unauthorized();
    case 403:
      return AuthException.forbidden();
    case 404:
      return ClientException.notFound();
    case 409:
      return ClientException.conflict(message: message);
    case 422:
      return ValidationException(message: message ?? 'Validation failed');
    case 429:
      return ClientException.tooManyRequests();
    case 500:
      return ServerException(message: message ?? 'Internal server error');
    case 502:
      return ServerException(
        message: message ?? 'Bad gateway',
        statusCode: 502,
      );
    case 503:
      return ServerException.unavailable();
    case 504:
      return NetworkException.timeout();
    default:
      if (statusCode >= 500) {
        return ServerException(
          message: message ?? 'Server error',
          statusCode: statusCode,
        );
      } else if (statusCode >= 400) {
        return ClientException(
          message: message ?? 'Request failed',
          statusCode: statusCode,
        );
      }
      return ApiException(
        message: message ?? 'Unknown error',
        statusCode: statusCode,
      );
  }
}
