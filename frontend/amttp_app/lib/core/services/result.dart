/// Result type for handling success/failure states
/// 
/// Provides a type-safe way to handle operations that can fail
/// without using exceptions for control flow.

sealed class Result<T> {
  const Result();

  /// Creates a success result with the given value
  factory Result.success(T value) = Success<T>;

  /// Creates a failure result with the given error
  factory Result.failure(AppException error) = Failure<T>;

  /// Returns true if this is a success result
  bool get isSuccess => this is Success<T>;

  /// Returns true if this is a failure result
  bool get isFailure => this is Failure<T>;

  /// Returns the value if success, null otherwise
  T? get valueOrNull {
    final self = this;
    if (self is Success<T>) return self.value;
    return null;
  }

  /// Returns the error if failure, null otherwise
  AppException? get errorOrNull {
    final self = this;
    if (self is Failure<T>) return self.error;
    return null;
  }

  /// Maps the success value to a new type
  Result<R> map<R>(R Function(T value) transform) {
    final self = this;
    if (self is Success<T>) {
      return Result.success(transform(self.value));
    }
    return Result.failure((self as Failure<T>).error);
  }

  /// Maps the success value to a new Result
  Result<R> flatMap<R>(Result<R> Function(T value) transform) {
    final self = this;
    if (self is Success<T>) {
      return transform(self.value);
    }
    return Result.failure((self as Failure<T>).error);
  }

  /// Handles both success and failure cases
  R when<R>({
    required R Function(T value) success,
    required R Function(AppException error) failure,
  }) {
    final self = this;
    if (self is Success<T>) {
      return success(self.value);
    }
    return failure((self as Failure<T>).error);
  }

  /// Gets the value or throws the error
  T getOrThrow() {
    final self = this;
    if (self is Success<T>) {
      return self.value;
    }
    throw (self as Failure<T>).error;
  }

  /// Gets the value or returns a default
  T getOrElse(T Function() defaultValue) {
    final self = this;
    if (self is Success<T>) {
      return self.value;
    }
    return defaultValue();
  }

  /// Gets the value or returns the provided default
  T getOrDefault(T defaultValue) {
    final self = this;
    if (self is Success<T>) {
      return self.value;
    }
    return defaultValue;
  }
}

/// Success result containing a value
final class Success<T> extends Result<T> {
  final T value;

  const Success(this.value);

  @override
  String toString() => 'Success($value)';

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Success<T> &&
          runtimeType == other.runtimeType &&
          value == other.value;

  @override
  int get hashCode => value.hashCode;
}

/// Failure result containing an error
final class Failure<T> extends Result<T> {
  final AppException error;

  const Failure(this.error);

  @override
  String toString() => 'Failure($error)';

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is Failure<T> &&
          runtimeType == other.runtimeType &&
          error == other.error;

  @override
  int get hashCode => error.hashCode;
}

/// Base exception type for the app
class AppException implements Exception {
  final String message;
  final String? code;
  final dynamic originalError;
  final StackTrace? stackTrace;

  const AppException({
    required this.message,
    this.code,
    this.originalError,
    this.stackTrace,
  });

  @override
  String toString() => 'AppException: $message${code != null ? ' (code: $code)' : ''}';
}

/// Extension to run operations that might throw and wrap in Result
extension ResultExtension<T> on Future<T> {
  /// Converts a Future to a Result, catching any exceptions
  Future<Result<T>> toResult() async {
    try {
      final value = await this;
      return Result.success(value);
    } on AppException catch (e) {
      return Result.failure(e);
    } catch (e, st) {
      return Result.failure(AppException(
        message: e.toString(),
        originalError: e,
        stackTrace: st,
      ));
    }
  }
}

/// Extension for working with nullable values
extension NullableResultExtension<T> on T? {
  /// Converts a nullable value to a Result
  Result<T> toResult({String errorMessage = 'Value is null'}) {
    if (this != null) {
      return Result.success(this as T);
    }
    return Result.failure(AppException(message: errorMessage));
  }
}
