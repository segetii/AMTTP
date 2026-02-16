/// Base HTTP client with centralized configuration and error handling
/// 
/// This provides the foundation for all domain-specific repositories.
/// Separates HTTP concerns from business logic.
library;

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import '../api_config.dart';

/// Custom API exception with typed error codes
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final String? code;
  final dynamic data;

  ApiException({
    required this.message,
    this.statusCode,
    this.code,
    this.data,
  });

  factory ApiException.fromDioError(DioException e) {
    String message;
    String? code;

    switch (e.type) {
      case DioExceptionType.connectionTimeout:
        message = 'Connection timeout';
        code = 'TIMEOUT';
        break;
      case DioExceptionType.sendTimeout:
        message = 'Send timeout';
        code = 'TIMEOUT';
        break;
      case DioExceptionType.receiveTimeout:
        message = 'Receive timeout';
        code = 'TIMEOUT';
        break;
      case DioExceptionType.badResponse:
        final statusCode = e.response?.statusCode;
        final responseData = e.response?.data;
        message = _extractErrorMessage(responseData) ?? 
                  'Request failed with status $statusCode';
        code = 'HTTP_$statusCode';
        return ApiException(
          message: message,
          statusCode: statusCode,
          code: code,
          data: responseData,
        );
      case DioExceptionType.cancel:
        message = 'Request cancelled';
        code = 'CANCELLED';
        break;
      case DioExceptionType.connectionError:
        message = 'Connection error. Please check your network.';
        code = 'NETWORK_ERROR';
        break;
      default:
        message = e.message ?? 'Unknown error occurred';
        code = 'UNKNOWN';
    }

    return ApiException(
      message: message,
      statusCode: e.response?.statusCode,
      code: code,
    );
  }

  static String? _extractErrorMessage(dynamic data) {
    if (data is Map) {
      return data['message'] ?? data['error'] ?? data['detail'];
    }
    if (data is String) return data;
    return null;
  }

  @override
  String toString() => 'ApiException: $message (code: $code)';

  bool get isNetworkError => code == 'NETWORK_ERROR' || code == 'TIMEOUT';
  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isNotFound => statusCode == 404;
  bool get isServerError => (statusCode ?? 0) >= 500;
}

/// Centralized HTTP client for all API calls
class HttpClient {
  late final Dio _dio;
  final String? baseUrl;
  
  HttpClient({this.baseUrl}) {
    _dio = Dio(BaseOptions(
      baseUrl: baseUrl ?? ApiConfig.resolveBaseUrl(),
      connectTimeout: ApiConfig.connectTimeout,
      receiveTimeout: ApiConfig.receiveTimeout,
      sendTimeout: ApiConfig.sendTimeout,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    // Add interceptors
    _dio.interceptors.addAll([
      _LoggingInterceptor(),
      _RetryInterceptor(_dio),
    ]);
  }

  /// GET request
  Future<T> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.get<T>(
        path,
        queryParameters: queryParameters,
        options: options,
        cancelToken: cancelToken,
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// POST request
  Future<T> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.post<T>(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
        cancelToken: cancelToken,
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// PUT request
  Future<T> put<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.put<T>(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
        cancelToken: cancelToken,
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// PATCH request
  Future<T> patch<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.patch<T>(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
        cancelToken: cancelToken,
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// DELETE request
  Future<T> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.delete<T>(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
        cancelToken: cancelToken,
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }

  /// Upload file with multipart form data
  Future<T> uploadFile<T>(
    String path, {
    required FormData formData,
    void Function(int, int)? onSendProgress,
    CancelToken? cancelToken,
  }) async {
    try {
      final response = await _dio.post<T>(
        path,
        data: formData,
        onSendProgress: onSendProgress,
        cancelToken: cancelToken,
        options: Options(
          contentType: 'multipart/form-data',
        ),
      );
      return response.data as T;
    } on DioException catch (e) {
      throw ApiException.fromDioError(e);
    }
  }
}

/// Logging interceptor - redacts sensitive data in production
class _LoggingInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (kDebugMode) {
      _log('[HTTP] ${options.method} ${options.path}');
      // Don't log full body in production - may contain PII
      if (options.data != null) {
        _log('[HTTP] Body: ${_redactSensitiveData(options.data)}');
      }
    }
    handler.next(options);
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    if (kDebugMode) {
      _log('[HTTP] ${response.statusCode} ${response.requestOptions.path}');
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (kDebugMode) {
      _log('[HTTP ERROR] ${err.type} ${err.message}');
    }
    handler.next(err);
  }

  void _log(String message) {
    // Use structured logging in production
    if (kDebugMode) {
      print(message);
    }
  }

  dynamic _redactSensitiveData(dynamic data) {
    if (!kDebugMode) return '[REDACTED]';
    if (data is Map) {
      final redacted = Map.from(data);
      const sensitiveKeys = ['password', 'token', 'secret', 'key', 'private'];
      for (final key in sensitiveKeys) {
        if (redacted.containsKey(key)) {
          redacted[key] = '[REDACTED]';
        }
      }
      return redacted;
    }
    return data;
  }
}

/// Retry interceptor with exponential backoff
class _RetryInterceptor extends Interceptor {
  final Dio _dio;
  final int maxRetries;
  final Duration baseDelay;

  _RetryInterceptor(
    this._dio);

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    // Only retry on network errors or 5xx server errors
    if (_shouldRetry(err)) {
      final retryCount = err.requestOptions.extra['retryCount'] ?? 0;
      
      if (retryCount < maxRetries) {
        final delay = baseDelay * (1 << retryCount); // Exponential backoff
        
        if (kDebugMode) {
          print('[HTTP] Retrying request (attempt ${retryCount + 1}/$maxRetries) after ${delay.inSeconds}s');
        }
        
        await Future.delayed(delay);
        
        err.requestOptions.extra['retryCount'] = retryCount + 1;
        
        try {
          final response = await _dio.fetch(err.requestOptions);
          handler.resolve(response);
          return;
        } catch (e) {
          // Continue to error handler if retry fails
        }
      }
    }
    
    handler.next(err);
  }

  bool _shouldRetry(DioException err) {
    return err.type == DioExceptionType.connectionTimeout ||
           err.type == DioExceptionType.receiveTimeout ||
           err.type == DioExceptionType.connectionError ||
           (err.response?.statusCode ?? 0) >= 500;
  }
}
