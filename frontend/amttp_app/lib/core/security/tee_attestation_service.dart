// ignore_for_file: avoid_print
import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

// ---------------------------------------------------------------------------
// TEE Attestation Service (Flutter)
//
// Uses:
//  - Web: WebAuthn / FIDO2 via dart:js_interop + Web Crypto API
//  - Mobile: local_auth (biometrics) + flutter_secure_storage
//
// Critical actions defined in shared/rbac_config.json.criticalActions
// are gated through this service.
// ---------------------------------------------------------------------------

/// Result of an attestation attempt
class AttestationResult {
  final bool success;
  final String method; // 'webauthn', 'biometric', 'secure-key', 'fallback-pin'
  final String? credentialId;
  final String? signature; // base64url
  final String? challenge; // base64url
  final int timestamp;
  final String? error;

  const AttestationResult({
    required this.success,
    required this.method,
    this.credentialId,
    this.signature,
    this.challenge,
    required this.timestamp,
    this.error,
  });

  Map<String, dynamic> toJson() => {
        'success': success,
        'method': method,
        if (credentialId != null) 'credentialId': credentialId,
        if (signature != null) 'signature': signature,
        if (challenge != null) 'challenge': challenge,
        'timestamp': timestamp,
        if (error != null) 'error': error,
      };
}

/// A critical action descriptor from rbac_config.json
class CriticalAction {
  final String id;
  final String label;
  final int minRole;
  final bool requiresMultisig;
  final bool requiresTEE;
  final String description;

  const CriticalAction({
    required this.id,
    required this.label,
    required this.minRole,
    required this.requiresMultisig,
    required this.requiresTEE,
    required this.description,
  });

  factory CriticalAction.fromJson(Map<String, dynamic> json) => CriticalAction(
        id: json['id'] as String,
        label: json['label'] as String,
        minRole: json['minRole'] as int,
        requiresMultisig: json['requiresMultisig'] as bool,
        requiresTEE: json['requiresTEE'] as bool,
        description: json['description'] as String,
      );
}

/// Enrollment state for TEE credentials
class TeeEnrollmentState {
  final String? webAuthnCredentialId;
  final List<String> secureKeyIds;
  final bool biometricsAvailable;
  final bool enrolled;
  final DateTime? enrolledAt;

  const TeeEnrollmentState({
    this.webAuthnCredentialId,
    this.secureKeyIds = const [],
    this.biometricsAvailable = false,
    this.enrolled = false,
    this.enrolledAt,
  });

  TeeEnrollmentState copyWith({
    String? webAuthnCredentialId,
    List<String>? secureKeyIds,
    bool? biometricsAvailable,
    bool? enrolled,
    DateTime? enrolledAt,
  }) =>
      TeeEnrollmentState(
        webAuthnCredentialId: webAuthnCredentialId ?? this.webAuthnCredentialId,
        secureKeyIds: secureKeyIds ?? this.secureKeyIds,
        biometricsAvailable: biometricsAvailable ?? this.biometricsAvailable,
        enrolled: enrolled ?? this.enrolled,
        enrolledAt: enrolledAt ?? this.enrolledAt,
      );
}

// ---------------------------------------------------------------------------
// Platform Abstraction
// ---------------------------------------------------------------------------

/// Abstract TEE backend — platform implementations differ
abstract class TeeBackend {
  /// Whether hardware-backed attestation is available
  Future<bool> isHardwareAttestationAvailable();

  /// Register a credential for future attestation
  Future<String?> registerCredential(String userId, String userName);

  /// Perform attestation (biometric, WebAuthn, etc.)
  Future<AttestationResult> performAttestation(
    String actionId, {
    String? credentialId,
  });

  /// Generate a non-exportable key for action signing
  Future<bool> generateSecureKey(String keyId);

  /// Sign data with a secure key
  Future<String?> signWithSecureKey(String keyId, Uint8List data);
}

/// Web TEE Backend — delegates to JavaScript WebAuthn + Crypto APIs
class WebTeeBackend implements TeeBackend {
  @override
  Future<bool> isHardwareAttestationAvailable() async {
    if (!kIsWeb) return false;
    // On web, we check via JS interop (simplified — real impl uses dart:js_interop)
    // For now, assume available if running on HTTPS or localhost
    return true;
  }

  @override
  Future<String?> registerCredential(String userId, String userName) async {
    // On web, the actual WebAuthn registration is handled by the Next.js
    // layer via the auth bridge. Flutter can trigger it via postMessage
    // to the host, or use dart:js_interop to call navigator.credentials.create
    //
    // For this implementation, we store the credential ID after the JS layer
    // handles registration
    debugPrint('[TEE/Web] Credential registration delegated to JS layer');
    return null; // Will be set from JS callback
  }

  @override
  Future<AttestationResult> performAttestation(
    String actionId, {
    String? credentialId,
  }) async {
    // On web, call the JavaScript TEE attestation via JS interop
    // This invokes the same WebAuthn flow as tee-attestation.ts
    debugPrint(
        '[TEE/Web] Performing WebAuthn attestation for action: $actionId');

    // In a real implementation, use dart:js_interop to call:
    // window.amttpTEE.performAttestation(actionId, credentialId)
    //
    // For now, return a placeholder that the wiring layer will replace
    // with actual JS calls
    return AttestationResult(
      success: false,
      method: 'webauthn',
      timestamp: DateTime.now().millisecondsSinceEpoch,
      error: 'NEEDS_JS_BRIDGE',
    );
  }

  @override
  Future<bool> generateSecureKey(String keyId) async {
    // Delegated to JS layer's Web Crypto API
    debugPrint('[TEE/Web] Secure key generation delegated to JS layer: $keyId');
    return false;
  }

  @override
  Future<String?> signWithSecureKey(String keyId, Uint8List data) async {
    debugPrint('[TEE/Web] Signing delegated to JS layer');
    return null;
  }
}

/// Mobile TEE Backend — uses local_auth + flutter_secure_storage
class MobileTeeBackend implements TeeBackend {
  @override
  Future<bool> isHardwareAttestationAvailable() async {
    // In production, use local_auth package:
    // final localAuth = LocalAuthentication();
    // return await localAuth.canCheckBiometrics || await localAuth.isDeviceSupported();
    return false; // Placeholder until local_auth is wired
  }

  @override
  Future<String?> registerCredential(String userId, String userName) async {
    // On mobile, we use the device's biometric enrollment
    // No explicit credential registration needed — the OS manages it
    return 'device_biometric_$userId';
  }

  @override
  Future<AttestationResult> performAttestation(
    String actionId, {
    String? credentialId,
  }) async {
    // In production, use local_auth:
    // final localAuth = LocalAuthentication();
    // final didAuth = await localAuth.authenticate(
    //   localizedReason: 'Confirm critical action: $actionId',
    //   options: const AuthenticationOptions(biometricOnly: true),
    // );
    //
    // For now, return needs-pin fallback
    return AttestationResult(
      success: false,
      method: 'biometric',
      timestamp: DateTime.now().millisecondsSinceEpoch,
      error: 'NEEDS_BIOMETRIC_PACKAGE',
    );
  }

  @override
  Future<bool> generateSecureKey(String keyId) async {
    // In production, use flutter_secure_storage with hardware-backed keystore
    return false;
  }

  @override
  Future<String?> signWithSecureKey(String keyId, Uint8List data) async {
    return null;
  }
}

// ---------------------------------------------------------------------------
// TEE Attestation Service (main orchestrator)
// ---------------------------------------------------------------------------

class TeeAttestationService {
  final TeeBackend _backend;
  TeeEnrollmentState _enrollment;

  TeeAttestationService({TeeBackend? backend})
      : _backend = backend ?? (kIsWeb ? WebTeeBackend() : MobileTeeBackend()),
        _enrollment = const TeeEnrollmentState();

  TeeEnrollmentState get enrollment => _enrollment;

  /// All critical actions from rbac_config.json
  static const List<CriticalAction> criticalActions = [
    CriticalAction(
      id: 'freeze_address',
      label: 'Freeze Address',
      minRole: 4,
      requiresMultisig: true,
      requiresTEE: true,
      description: 'Freeze a wallet address from all protocol interactions',
    ),
    CriticalAction(
      id: 'unfreeze_address',
      label: 'Unfreeze Address',
      minRole: 4,
      requiresMultisig: true,
      requiresTEE: true,
      description: 'Unfreeze a previously frozen wallet address',
    ),
    CriticalAction(
      id: 'emergency_override',
      label: 'Emergency Override',
      minRole: 6,
      requiresMultisig: false,
      requiresTEE: true,
      description: 'Bypass all safety checks in emergency situations',
    ),
    CriticalAction(
      id: 'policy_update',
      label: 'Update Compliance Policy',
      minRole: 4,
      requiresMultisig: true,
      requiresTEE: true,
      description: 'Modify FATF or custom compliance policy rules',
    ),
    CriticalAction(
      id: 'role_escalation',
      label: 'Escalate User Role',
      minRole: 5,
      requiresMultisig: true,
      requiresTEE: true,
      description: 'Promote a user to a higher RBAC role',
    ),
    CriticalAction(
      id: 'export_pii',
      label: 'Export PII Data',
      minRole: 4,
      requiresMultisig: false,
      requiresTEE: true,
      description: 'Export personally identifiable information for SAR filing',
    ),
    CriticalAction(
      id: 'ml_model_retrain',
      label: 'Retrain ML Model',
      minRole: 6,
      requiresMultisig: false,
      requiresTEE: true,
      description: 'Trigger retraining of fraud detection ML models',
    ),
  ];

  /// Look up a critical action by ID
  static CriticalAction? findAction(String actionId) {
    try {
      return criticalActions.firstWhere((a) => a.id == actionId);
    } catch (_) {
      return null;
    }
  }

  /// Initialize TEE capabilities
  Future<void> initialize() async {
    final hwAvailable = await _backend.isHardwareAttestationAvailable();
    _enrollment = _enrollment.copyWith(biometricsAvailable: hwAvailable);
  }

  /// Enroll the user for TEE-protected actions
  Future<List<String>> enroll(
      String userId, String userName, int roleLevel) async {
    final errors = <String>[];

    // Register hardware credential
    final credId = await _backend.registerCredential(userId, userName);
    if (credId != null) {
      _enrollment = _enrollment.copyWith(webAuthnCredentialId: credId);
    } else {
      errors.add('Hardware credential registration unavailable');
    }

    // Generate secure keys for each accessible critical action
    final keyIds = <String>[];
    for (final action in criticalActions) {
      if (roleLevel >= action.minRole && action.requiresTEE) {
        final keyId = 'amttp_action_key_${action.id}';
        final ok = await _backend.generateSecureKey(keyId);
        if (ok) {
          keyIds.add(keyId);
        } else {
          errors.add('Secure key generation failed for: ${action.label}');
        }
      }
    }

    _enrollment = _enrollment.copyWith(
      secureKeyIds: keyIds,
      enrolled: true,
      enrolledAt: DateTime.now(),
    );

    return errors;
  }

  /// Gate a critical action — returns attestation result
  ///
  /// Flow:
  /// 1. Check role level
  /// 2. If TEE required: attempt hardware attestation
  /// 3. If hardware unavailable: attempt secure key signing
  /// 4. Fallback: require PIN re-entry
  Future<AttestationResult> gateCriticalAction(
    String actionId,
    int userRoleLevel,
  ) async {
    final action = findAction(actionId);
    if (action == null) {
      return AttestationResult(
        success: false,
        method: 'webauthn',
        timestamp: DateTime.now().millisecondsSinceEpoch,
        error: 'Unknown critical action: $actionId',
      );
    }

    // Role check (hard fail)
    if (userRoleLevel < action.minRole) {
      return AttestationResult(
        success: false,
        method: 'webauthn',
        timestamp: DateTime.now().millisecondsSinceEpoch,
        error:
            'Insufficient role level. Required: R${action.minRole}, current: R$userRoleLevel',
      );
    }

    // If TEE not required, pass immediately
    if (!action.requiresTEE) {
      return AttestationResult(
        success: true,
        method: 'fallback-pin',
        timestamp: DateTime.now().millisecondsSinceEpoch,
      );
    }

    // Try hardware attestation
    if (_enrollment.webAuthnCredentialId != null ||
        _enrollment.biometricsAvailable) {
      final result = await _backend.performAttestation(
        actionId,
        credentialId: _enrollment.webAuthnCredentialId,
      );
      if (result.success) return result;
      // Fall through if user cancelled or unavailable
    }

    // Try secure key signing
    final keyId = 'amttp_action_key_$actionId';
    if (_enrollment.secureKeyIds.contains(keyId)) {
      final challenge = Uint8List(32);
      // In production, get challenge from server
      for (int i = 0; i < 32; i++) {
        challenge[i] = (DateTime.now().microsecond + i * 7) % 256;
      }
      final sig = await _backend.signWithSecureKey(keyId, challenge);
      if (sig != null) {
        return AttestationResult(
          success: true,
          method: 'secure-key',
          challenge: base64Url.encode(challenge),
          signature: sig,
          timestamp: DateTime.now().millisecondsSinceEpoch,
        );
      }
    }

    // Fallback: UI must show PIN/password re-entry dialog
    return AttestationResult(
      success: false,
      method: 'fallback-pin',
      timestamp: DateTime.now().millisecondsSinceEpoch,
      error: 'NEEDS_PIN_CONFIRMATION',
    );
  }

  /// Check if an action requires multisig approval
  bool requiresMultisig(String actionId) {
    return findAction(actionId)?.requiresMultisig ?? false;
  }

  /// Get all actions accessible by a given role level
  List<CriticalAction> actionsForRole(int roleLevel) {
    return criticalActions.where((a) => roleLevel >= a.minRole).toList();
  }
}

// ---------------------------------------------------------------------------
// Riverpod Providers
// ---------------------------------------------------------------------------

final teeServiceProvider = Provider<TeeAttestationService>((ref) {
  final service = TeeAttestationService();
  service.initialize();
  return service;
});

final teeEnrollmentProvider = StateProvider<TeeEnrollmentState>((ref) {
  return ref.watch(teeServiceProvider).enrollment;
});

/// Provider to gate a critical action — usage:
///   final result = await ref.read(criticalActionGateProvider('freeze_address').future);
final criticalActionGateProvider = FutureProvider.family<AttestationResult,
    ({String actionId, int roleLevel})>(
  (ref, params) async {
    final tee = ref.read(teeServiceProvider);
    return tee.gateCriticalAction(params.actionId, params.roleLevel);
  },
);
