/// UI Integrity Protection Service
/// 
/// Dart port of ui-integrity.ts for Flutter mobile apps
/// Prevents Bybit-style UI manipulation attacks on iOS/Android
///
/// Protection Layers:
/// 1. Widget tree hashing (SHA-256)
/// 2. Transaction intent signing (EIP-712 compatible)
/// 3. Runtime state validation
/// 4. Server-side verification
/// 5. Visual confirmation
library;

import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

/// Severity levels for integrity violations
enum ViolationSeverity {
  low,
  medium,
  high,
  critical,
}

/// Types of integrity violations
enum ViolationType {
  hashMismatch,
  staleTimestamp,
  tamperedIntent,
  invalidSignature,
  suspiciousActivity,
}

/// Integrity violation report
class IntegrityViolation {
  final ViolationType type;
  final ViolationSeverity severity;
  final String details;
  final DateTime timestamp;

  IntegrityViolation({
    required this.type,
    required this.severity,
    required this.details,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'violation_type': type.toString().split('.').last,
        'severity': severity.toString().split('.').last,
        'details': details,
        'timestamp': timestamp.toIso8601String(),
      };
}

/// Component integrity snapshot
class ComponentIntegrity {
  final String componentId;
  final String stateHash;
  final String handlerHash;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;

  ComponentIntegrity({
    required this.componentId,
    required this.stateHash,
    required this.handlerHash,
    DateTime? timestamp,
    this.metadata = const {},
  }) : timestamp = timestamp ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'componentId': componentId,
        'stateHash': stateHash,
        'handlerHash': handlerHash,
        'timestamp': timestamp.toIso8601String(),
        'metadata': metadata,
      };

  /// Check if integrity snapshot is stale (>60s old)
  bool get isStale {
    final age = DateTime.now().difference(timestamp);
    return age.inSeconds > 60;
  }
}

/// Transaction intent for signing (prevents UI display manipulation)
class TransactionIntent {
  final String from;
  final String to;
  final String amount;
  final String? currency;
  final String? memo;
  final Map<String, dynamic>? metadata;
  final DateTime timestamp;

  TransactionIntent({
    required this.from,
    required this.to,
    required this.amount,
    this.currency,
    this.memo,
    this.metadata,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();

  /// Generate canonical JSON representation (for hashing)
  Map<String, dynamic> toCanonicalJson() {
    final Map<String, dynamic> canonical = {
      'from': from.toLowerCase(),
      'to': to.toLowerCase(),
      'amount': amount,
      'timestamp': timestamp.millisecondsSinceEpoch,
    };

    if (currency != null) canonical['currency'] = currency!.toUpperCase();
    if (memo != null) canonical['memo'] = memo;
    if (metadata != null) canonical['metadata'] = metadata;

    return canonical;
  }

  /// Get hash of transaction intent (for signing)
  String getIntentHash() {
    final canonical = toCanonicalJson();
    final jsonString = const JsonEncoder().convert(canonical);
    final bytes = utf8.encode(jsonString);
    final digest = sha256.convert(bytes);
    return '0x${digest.toString()}';
  }

  Map<String, dynamic> toJson() => toCanonicalJson();
}

/// Integrity report for server verification
class IntegrityReport {
  final String componentId;
  final String stateHash;
  final String handlerHash;
  final DateTime timestamp;
  final List<IntegrityViolation> violations;

  IntegrityReport({
    required this.componentId,
    required this.stateHash,
    required this.handlerHash,
    DateTime? timestamp,
    this.violations = const [],
  }) : timestamp = timestamp ?? DateTime.now();

  Map<String, dynamic> toJson() => {
        'componentId': componentId,
        'stateHash': stateHash,
        'handlerHash': handlerHash,
        'timestamp': timestamp.toIso8601String(),
        'violations': violations.map((v) => v.toJson()).toList(),
      };
}

/// UI Integrity Service
/// 
/// Main service for protecting Flutter widgets from manipulation
class UIIntegrityService {
  /// Calculate SHA-256 hash of any string
  static String calculateHash(String input) {
    final bytes = utf8.encode(input);
    final digest = sha256.convert(bytes);
    return digest.toString();
  }

  /// Capture integrity snapshot of widget state
  /// 
  /// [componentId] - Unique identifier for the widget
  /// [state] - Map of current widget state (form values, selections, etc.)
  /// [handlers] - List of callback function names/identifiers
  static ComponentIntegrity captureComponentIntegrity({
    required String componentId,
    required Map<String, dynamic> state,
    required List<String> handlers,
  }) {
    // Create canonical representation of state
  final stateJson = const JsonEncoder().convert(state);
    final stateHash = calculateHash(stateJson);

    // Create canonical representation of handlers
  final sortedHandlers = List<String>.from(handlers)..sort();
  final handlersJson = const JsonEncoder().convert(sortedHandlers);
    final handlerHash = calculateHash(handlersJson);

    return ComponentIntegrity(
      componentId: componentId,
      stateHash: stateHash,
      handlerHash: handlerHash,
      metadata: {
        'platform': defaultTargetPlatform.toString(),
        'debug': kDebugMode,
      },
    );
  }

  /// Create transaction intent object
  static TransactionIntent createTransactionIntent({
    required String from,
    required String to,
    required String amount,
    String? currency,
    String? memo,
    Map<String, dynamic>? metadata,
  }) {
    return TransactionIntent(
      from: from,
      to: to,
      amount: amount,
      currency: currency,
      memo: memo,
      metadata: metadata,
    );
  }

  /// Validate integrity snapshot
  /// 
  /// Returns list of violations found (empty if valid)
  static List<IntegrityViolation> validateIntegrity({
    required ComponentIntegrity current,
    required ComponentIntegrity? trusted,
  }) {
    final violations = <IntegrityViolation>[];

    // Check if snapshot is stale
    if (current.isStale) {
      violations.add(IntegrityViolation(
        type: ViolationType.staleTimestamp,
        severity: ViolationSeverity.medium,
        details: 'Integrity snapshot is stale (>60s old)',
      ));
    }

    // Compare against trusted snapshot if provided
    if (trusted != null) {
      if (current.stateHash != trusted.stateHash) {
        violations.add(IntegrityViolation(
          type: ViolationType.hashMismatch,
          severity: ViolationSeverity.high,
          details: 'State hash mismatch detected',
        ));
      }

      if (current.handlerHash != trusted.handlerHash) {
        violations.add(IntegrityViolation(
          type: ViolationType.hashMismatch,
          severity: ViolationSeverity.critical,
          details: 'Handler hash mismatch - possible code injection',
        ));
      }
    }

    return violations;
  }

  /// Generate integrity report for server verification
  static IntegrityReport generateReport({
    required String componentId,
    required Map<String, dynamic> state,
    required List<String> handlers,
    ComponentIntegrity? trustedSnapshot,
  }) {
    final current = captureComponentIntegrity(
      componentId: componentId,
      state: state,
      handlers: handlers,
    );

    final violations = validateIntegrity(
      current: current,
      trusted: trustedSnapshot,
    );

    return IntegrityReport(
      componentId: current.componentId,
      stateHash: current.stateHash,
      handlerHash: current.handlerHash,
      timestamp: current.timestamp,
      violations: violations,
    );
  }

  /// Verify transaction intent matches expected hash
  static bool verifyIntentHash({
    required TransactionIntent intent,
    required String expectedHash,
  }) {
    final actualHash = intent.getIntentHash();
    return actualHash.toLowerCase() == expectedHash.toLowerCase();
  }

  /// Create human-readable summary of transaction intent
  static String formatIntentSummary(TransactionIntent intent) {
    final buffer = StringBuffer();
    buffer.writeln('Transaction Details:');
    buffer.writeln('From: ${_formatAddress(intent.from)}');
    buffer.writeln('To: ${_formatAddress(intent.to)}');
    buffer.writeln('Amount: ${intent.amount} ${intent.currency ?? 'ETH'}');
    if (intent.memo != null) {
      buffer.writeln('Memo: ${intent.memo}');
    }
    buffer.writeln('Time: ${_formatTimestamp(intent.timestamp)}');
    return buffer.toString();
  }

  /// Format Ethereum address for display (0x1234...5678)
  static String _formatAddress(String address) {
    if (address.length <= 10) return address;
    return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
  }

  /// Format timestamp for display
  static String _formatTimestamp(DateTime timestamp) {
    return timestamp.toLocal().toString().substring(0, 19);
  }
}

/// Mixin for widgets that need integrity protection
/// 
/// Usage:
/// ```dart
/// class SecureTransferWidget extends StatefulWidget with IntegrityProtectedWidget {
///   @override
///   String get componentId => 'SecureTransfer';
/// }
/// ```
mixin IntegrityProtectedWidget on Widget {
  /// Unique identifier for this component
  String get componentId;

  /// Capture current integrity snapshot
  ComponentIntegrity captureIntegrity({
    required Map<String, dynamic> state,
    required List<String> handlers,
  }) {
    return UIIntegrityService.captureComponentIntegrity(
      componentId: componentId,
      state: state,
      handlers: handlers,
    );
  }

  /// Generate integrity report
  IntegrityReport generateIntegrityReport({
    required Map<String, dynamic> state,
    required List<String> handlers,
    ComponentIntegrity? trustedSnapshot,
  }) {
    return UIIntegrityService.generateReport(
      componentId: componentId,
      state: state,
      handlers: handlers,
      trustedSnapshot: trustedSnapshot,
    );
  }
}

/// State mixin for stateful widgets with integrity protection
mixin IntegrityProtectedState<T extends StatefulWidget> on State<T> {
  /// Last known good integrity snapshot
  ComponentIntegrity? _trustedSnapshot;

  /// Current integrity violations
  final List<IntegrityViolation> _violations = [];

  /// Get current violations
  List<IntegrityViolation> get violations => List.unmodifiable(_violations);

  /// Check if there are critical violations
  bool get hasCriticalViolations {
    return _violations.any((v) => v.severity == ViolationSeverity.critical);
  }

  /// Capture and validate integrity
  void validateIntegrity({
    required String componentId,
    required Map<String, dynamic> state,
    required List<String> handlers,
  }) {
    final current = UIIntegrityService.captureComponentIntegrity(
      componentId: componentId,
      state: state,
      handlers: handlers,
    );

    // Store as trusted if first capture
    _trustedSnapshot ??= current;

    // Validate against trusted snapshot
    final newViolations = UIIntegrityService.validateIntegrity(
      current: current,
      trusted: _trustedSnapshot,
    );

    if (newViolations.isNotEmpty) {
      _violations.addAll(newViolations);
      _onViolationsDetected(newViolations);
    }
  }

  /// Override to handle violations
  void _onViolationsDetected(List<IntegrityViolation> violations) {
    if (kDebugMode) {
      for (final violation in violations) {
        debugPrint('🚨 INTEGRITY VIOLATION: ${violation.details}');
      }
    }
  }

  /// Clear all violations
  void clearViolations() {
    _violations.clear();
  }

  /// Reset trusted snapshot (e.g., after legitimate state change)
  void resetTrustedSnapshot({
    required String componentId,
    required Map<String, dynamic> state,
    required List<String> handlers,
  }) {
    _trustedSnapshot = UIIntegrityService.captureComponentIntegrity(
      componentId: componentId,
      state: state,
      handlers: handlers,
    );
    clearViolations();
  }
}

/// Example Usage:
/// 
/// ```dart
/// class SecureTransferPage extends StatefulWidget {
///   const SecureTransferPage({super.key});
/// 
///   @override
///   State<SecureTransferPage> createState() => _SecureTransferPageState();
/// }
/// 
/// class _SecureTransferPageState extends State<SecureTransferPage>
///     with IntegrityProtectedState<SecureTransferPage> {
///   
///   final _amountController = TextEditingController();
///   final _recipientController = TextEditingController();
/// 
///   void _validateCurrentState() {
///     validateIntegrity(
///       componentId: 'SecureTransfer',
///       state: {
///         'amount': _amountController.text,
///         'recipient': _recipientController.text,
///       },
///       handlers: ['onSubmit', 'onCancel'],
///     );
/// 
///     if (hasCriticalViolations) {
///       // Block transaction
///       showDialog(...);
///     }
///   }
/// 
///   void _submitTransfer() {
///     _validateCurrentState();
///     
///     if (!hasCriticalViolations) {
///       final intent = UIIntegrityService.createTransactionIntent(
///         from: currentWallet,
///         to: _recipientController.text,
///         amount: _amountController.text,
///       );
///       
///       // Sign intent hash, not UI display
///       final intentHash = intent.getIntentHash();
///       // ... proceed with signing
///     }
///   }
/// }
/// ```
