import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import '../constants/api_endpoints.dart';
import 'api_exception.dart';
import 'result.dart';

/// Standard API client with consistent error handling, retry logic, and caching
/// 
/// Usage:
/// ```dart
/// final client = ApiClient();
/// final result = await client.get<UserData>(
///   '/api/user/profile',
///   fromJson: UserData.fromJson,
/// );
/// result.when(
///   success: (data) => print(data),
///   failure: (error) => print(error.message),
/// );
/// ```

class ApiClient {
  final http.Client _httpClient;
  final String baseUrl;
  final Duration timeout;
  final int maxRetries;
  final Map<String, String> _defaultHeaders;
  
  // Simple in-memory cache
  final Map<String, _CacheEntry> _cache = {};
  final Duration defaultCacheDuration;

  ApiClient({
    http.Client? httpClient,
    String? baseUrl,
    this.timeout = const Duration(seconds: 30),
    this.maxRetries = 3,
    this.defaultCacheDuration = const Duration(minutes: 5),
    Map<String, String>? defaultHeaders,
  })  : _httpClient = httpClient ?? http.Client(),
        baseUrl = baseUrl ?? ApiEndpoints.baseUrl,
        _defaultHeaders = {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          ...?defaultHeaders,
        };

  /// Sets the authorization token for all requests
  void setAuthToken(String token) {
    _defaultHeaders['Authorization'] = 'Bearer $token';
  }

  /// Removes the authorization token
  void clearAuthToken() {
    _defaultHeaders.remove('Authorization');
  }

  /// Adds a custom header
  void setHeader(String key, String value) {
    _defaultHeaders[key] = value;
  }

  /// Performs a GET request
  Future<Result<T>> get<T>(
    String path, {
    required T Function(Map<String, dynamic>) fromJson,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
    bool useCache = false,
    Duration? cacheDuration,
  }) async {
    final uri = _buildUri(path, queryParams);
    final cacheKey = uri.toString();

    // Check cache
    if (useCache) {
      final cached = _getFromCache<T>(cacheKey);
      if (cached != null) return Result.success(cached);
    }

    final result = await _executeWithRetry<T>(
      () => _httpClient.get(uri, headers: _mergeHeaders(headers)),
      fromJson,
    );

    // Cache successful results
    if (useCache && result.isSuccess) {
      _setCache(cacheKey, result.valueOrNull, cacheDuration);
    }

    return result;
  }

  /// Performs a GET request expecting a list response
  Future<Result<List<T>>> getList<T>(
    String path, {
    required T Function(Map<String, dynamic>) fromJson,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
    bool useCache = false,
    Duration? cacheDuration,
  }) async {
    final uri = _buildUri(path, queryParams);
    final cacheKey = '${uri}_list';

    if (useCache) {
      final cached = _getFromCache<List<T>>(cacheKey);
      if (cached != null) return Result.success(cached);
    }

    final result = await _executeWithRetry<List<T>>(
      () => _httpClient.get(uri, headers: _mergeHeaders(headers)),
      (json) {
        if (json['data'] is List) {
          return (json['data'] as List)
              .map((item) => fromJson(item as Map<String, dynamic>))
              .toList();
        }
        throw ParseException.invalidType('data', 'List');
      },
    );

    if (useCache && result.isSuccess) {
      _setCache(cacheKey, result.valueOrNull, cacheDuration);
    }

    return result;
  }

  /// Performs a POST request
  Future<Result<T>> post<T>(
    String path, {
    required T Function(Map<String, dynamic>) fromJson,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
  }) async {
    final uri = _buildUri(path, queryParams);
    return _executeWithRetry<T>(
      () => _httpClient.post(
        uri,
        headers: _mergeHeaders(headers),
        body: body != null ? jsonEncode(body) : null,
      ),
      fromJson,
    );
  }

  /// Performs a PUT request
  Future<Result<T>> put<T>(
    String path, {
    required T Function(Map<String, dynamic>) fromJson,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
  }) async {
    final uri = _buildUri(path, queryParams);
    return _executeWithRetry<T>(
      () => _httpClient.put(
        uri,
        headers: _mergeHeaders(headers),
        body: body != null ? jsonEncode(body) : null,
      ),
      fromJson,
    );
  }

  /// Performs a PATCH request
  Future<Result<T>> patch<T>(
    String path, {
    required T Function(Map<String, dynamic>) fromJson,
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
  }) async {
    final uri = _buildUri(path, queryParams);
    return _executeWithRetry<T>(
      () => _httpClient.patch(
        uri,
        headers: _mergeHeaders(headers),
        body: body != null ? jsonEncode(body) : null,
      ),
      fromJson,
    );
  }

  /// Performs a DELETE request
  Future<Result<void>> delete(
    String path, {
    Map<String, String>? queryParams,
    Map<String, String>? headers,
  }) async {
    final uri = _buildUri(path, queryParams);
    return _executeWithRetry<void>(
      () => _httpClient.delete(uri, headers: _mergeHeaders(headers)),
      (_) {},
    );
  }

  /// Performs a POST without expecting a response body
  Future<Result<void>> postVoid(
    String path, {
    Map<String, dynamic>? body,
    Map<String, String>? queryParams,
    Map<String, String>? headers,
  }) async {
    final uri = _buildUri(path, queryParams);
    return _executeWithRetry<void>(
      () => _httpClient.post(
        uri,
        headers: _mergeHeaders(headers),
        body: body != null ? jsonEncode(body) : null,
      ),
      (_) {},
    );
  }

  /// Clears the entire cache
  void clearCache() {
    _cache.clear();
  }

  /// Clears cache for a specific path
  void clearCacheFor(String path) {
    final uri = _buildUri(path, null);
    _cache.remove(uri.toString());
    _cache.remove('${uri}_list');
  }

  /// Disposes the HTTP client
  void dispose() {
    _httpClient.close();
  }

  // Private methods

  Uri _buildUri(String path, Map<String, String>? queryParams) {
    final fullPath = path.startsWith('http') ? path : '$baseUrl$path';
    final uri = Uri.parse(fullPath);
    if (queryParams != null && queryParams.isNotEmpty) {
      return uri.replace(queryParameters: {
        ...uri.queryParameters,
        ...queryParams,
      });
    }
    return uri;
  }

  Map<String, String> _mergeHeaders(Map<String, String>? headers) {
    return {
      ..._defaultHeaders,
      ...?headers,
    };
  }

  Future<Result<T>> _executeWithRetry<T>(
    Future<http.Response> Function() request,
    T Function(Map<String, dynamic>) fromJson,
  ) async {
    int attempts = 0;
    ApiException? lastError;

    while (attempts < maxRetries) {
      attempts++;
      
      try {
        final response = await request().timeout(timeout);
        return _handleResponse<T>(response, fromJson);
      } on TimeoutException {
        lastError = NetworkException.timeout();
        if (attempts >= maxRetries) break;
        await _backoff(attempts);
      } on http.ClientException catch (e) {
        lastError = NetworkException(
          message: 'Network error: ${e.message}',
          originalError: e,
        );
        if (attempts >= maxRetries) break;
        await _backoff(attempts);
      } on ApiException catch (e) {
        // Don't retry client errors (4xx)
        if (e is ClientException || e is AuthException || e is ValidationException) {
          return Result.failure(e);
        }
        lastError = e;
        if (attempts >= maxRetries) break;
        await _backoff(attempts);
      } catch (e, st) {
        lastError = ApiException(
          message: 'Unexpected error: $e',
          originalError: e,
          stackTrace: st,
        );
        break; // Don't retry unknown errors
      }
    }

    return Result.failure(lastError ?? NetworkException());
  }

  Future<void> _backoff(int attempt) async {
    // Exponential backoff: 1s, 2s, 4s, etc.
    final delay = Duration(milliseconds: (1000 * (1 << (attempt - 1))).clamp(0, 10000));
    await Future.delayed(delay);
  }

  Result<T> _handleResponse<T>(
    http.Response response,
    T Function(Map<String, dynamic>) fromJson,
  ) {
    final statusCode = response.statusCode;
    final requestId = response.headers['x-request-id'];

    // Success responses
    if (statusCode >= 200 && statusCode < 300) {
      if (T == void || response.body.isEmpty) {
        return Result.success(null as T);
      }

      try {
        final json = jsonDecode(response.body);
        if (json is Map<String, dynamic>) {
          return Result.success(fromJson(json));
        }
        throw ParseException.invalidType('response', 'Map');
      } on FormatException {
        return Result.failure(ParseException.invalidJson());
      } on ParseException catch (e) {
        return Result.failure(e);
      } catch (e) {
        return Result.failure(ParseException(
          message: 'Failed to parse response: $e',
          originalError: e,
        ));
      }
    }

    // Error responses
    Map<String, dynamic>? errorBody;
    String? errorMessage;
    String? errorCode;

    try {
      if (response.body.isNotEmpty) {
        errorBody = jsonDecode(response.body);
        errorMessage = errorBody?['message'] ?? errorBody?['error'];
        errorCode = errorBody?['code'];
      }
    } catch (_) {
      // Ignore JSON parsing errors for error responses
    }

    return Result.failure(exceptionFromStatusCode(
      statusCode,
      message: errorMessage,
      code: errorCode,
      responseBody: errorBody,
      requestId: requestId,
    ));
  }

  T? _getFromCache<T>(String key) {
    final entry = _cache[key];
    if (entry != null && !entry.isExpired) {
      return entry.value as T?;
    }
    if (entry?.isExpired == true) {
      _cache.remove(key);
    }
    return null;
  }

  void _setCache(String key, dynamic value, Duration? duration) {
    _cache[key] = _CacheEntry(
      value: value,
      expiresAt: DateTime.now().add(duration ?? defaultCacheDuration),
    );
  }
}

class _CacheEntry {
  final dynamic value;
  final DateTime expiresAt;

  _CacheEntry({required this.value, required this.expiresAt});

  bool get isExpired => DateTime.now().isAfter(expiresAt);
}

/// Singleton instance for easy access
/// 
/// Usage:
/// ```dart
/// final result = await apiClient.get<User>(...);
/// ```
final apiClient = ApiClient();
