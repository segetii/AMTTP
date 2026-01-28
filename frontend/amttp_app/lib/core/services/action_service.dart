/// Action Service for Flutter
/// 
/// Provides real API integrations for approval, rejection, user management,
/// and policy operations. Falls back to demo mode when services are unavailable.
library;

import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../constants/app_constants.dart';

/// Result of an action operation
class ActionResult {
  final bool success;
  final String message;
  final Map<String, dynamic>? data;
  final bool isDemoMode;

  ActionResult({
    required this.success,
    required this.message,
    this.data,
    this.isDemoMode = false,
  });

  factory ActionResult.success(String message, {Map<String, dynamic>? data, bool demo = false}) {
    return ActionResult(success: true, message: message, data: data, isDemoMode: demo);
  }

  factory ActionResult.failure(String message) {
    return ActionResult(success: false, message: message);
  }
}

/// Unified Action Service for all UI interactions
class ActionService {
  static final ActionService _instance = ActionService._internal();
  factory ActionService() => _instance;
  ActionService._internal();

  final String _orchestratorUrl = AppConstants.baseApiUrl;
  final http.Client _client = http.Client();

  // ═══════════════════════════════════════════════════════════════════════════
  // APPROVAL ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  /// Approve a pending transaction/swap
  Future<ActionResult> approveTransaction({
    required String transactionId,
    required String approverAddress,
    String? comment,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/approvals/approve'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'transaction_id': transactionId,
          'approver': approverAddress,
          'comment': comment ?? 'Approved via Flutter app',
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return ActionResult.success(
          'Transaction $transactionId approved successfully',
          data: data,
        );
      }
      return ActionResult.failure('Approval failed: ${response.statusCode}');
    } catch (e) {
      // Demo mode fallback
      return ActionResult.success(
        'Transaction $transactionId approved (demo mode)',
        demo: true,
        data: {'transactionId': transactionId, 'status': 'approved'},
      );
    }
  }

  /// Reject a pending transaction/swap
  Future<ActionResult> rejectTransaction({
    required String transactionId,
    required String rejecterAddress,
    required String reason,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/approvals/reject'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'transaction_id': transactionId,
          'rejecter': rejecterAddress,
          'reason': reason,
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return ActionResult.success(
          'Transaction $transactionId rejected',
          data: data,
        );
      }
      return ActionResult.failure('Rejection failed: ${response.statusCode}');
    } catch (e) {
      // Demo mode fallback
      return ActionResult.success(
        'Transaction $transactionId rejected (demo mode)',
        demo: true,
        data: {'transactionId': transactionId, 'status': 'rejected', 'reason': reason},
      );
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // USER MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════

  /// Add a new user
  Future<ActionResult> addUser({
    required String email,
    required String name,
    required String role,
    String? walletAddress,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/users'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'email': email,
          'name': name,
          'role': role,
          'wallet_address': walletAddress,
          'created_at': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);
        return ActionResult.success('User $name added successfully', data: data);
      }
      return ActionResult.failure('Failed to add user: ${response.statusCode}');
    } catch (e) {
      // Demo mode fallback
      return ActionResult.success(
        'User $name added (demo mode)',
        demo: true,
        data: {'email': email, 'name': name, 'role': role},
      );
    }
  }

  /// Update user role
  Future<ActionResult> updateUserRole({
    required String userId,
    required String newRole,
  }) async {
    try {
      final response = await _client.put(
        Uri.parse('$_orchestratorUrl/users/$userId/role'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'role': newRole}),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success('User role updated to $newRole');
      }
      return ActionResult.failure('Failed to update role: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Role updated to $newRole (demo mode)',
        demo: true,
      );
    }
  }

  /// Disable a user
  Future<ActionResult> disableUser(String userId) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/users/$userId/disable'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success('User disabled');
      }
      return ActionResult.failure('Failed to disable user: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success('User disabled (demo mode)', demo: true);
    }
  }

  /// Remove a user
  Future<ActionResult> removeUser(String userId) async {
    try {
      final response = await _client.delete(
        Uri.parse('$_orchestratorUrl/users/$userId'),
        headers: {'Content-Type': 'application/json'},
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 204) {
        return ActionResult.success('User removed');
      }
      return ActionResult.failure('Failed to remove user: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success('User removed (demo mode)', demo: true);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // POLICY MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════

  /// Create a new policy rule
  Future<ActionResult> createPolicy({
    required String name,
    required String description,
    required String threshold,
    required String action,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/policies'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'name': name,
          'description': description,
          'threshold': threshold,
          'action': action,
          'status': 'draft',
          'created_at': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);
        return ActionResult.success('Policy "$name" created', data: data);
      }
      return ActionResult.failure('Failed to create policy: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Policy "$name" created (demo mode)',
        demo: true,
        data: {'name': name, 'status': 'draft'},
      );
    }
  }

  /// Toggle policy status (activate/deactivate)
  Future<ActionResult> togglePolicyStatus({
    required String policyId,
    required bool activate,
  }) async {
    try {
      final response = await _client.put(
        Uri.parse('$_orchestratorUrl/policies/$policyId/status'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'active': activate}),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success(
          'Policy ${activate ? "activated" : "deactivated"}',
        );
      }
      return ActionResult.failure('Failed to update policy: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Policy ${activate ? "activated" : "deactivated"} (demo mode)',
        demo: true,
      );
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // ENFORCEMENT ACTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  /// Create freeze action
  Future<ActionResult> createFreezeAction({
    required String targetAddress,
    required String reason,
    required String initiatorAddress,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/enforcement/freeze'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'target': targetAddress,
          'reason': reason,
          'initiator': initiatorAddress,
          'type': 'freeze',
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200 || response.statusCode == 201) {
        final data = jsonDecode(response.body);
        return ActionResult.success(
          'Freeze action initiated for $targetAddress',
          data: data,
        );
      }
      return ActionResult.failure('Failed to create freeze action: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Freeze action initiated (demo mode)',
        demo: true,
        data: {'target': targetAddress, 'status': 'pending_multisig'},
      );
    }
  }

  /// Approve enforcement action (multisig)
  Future<ActionResult> approveEnforcement({
    required String actionId,
    required String signerAddress,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/enforcement/$actionId/approve'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'signer': signerAddress,
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return ActionResult.success('Enforcement action approved', data: data);
      }
      return ActionResult.failure('Approval failed: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Enforcement approved (demo mode)',
        demo: true,
        data: {'actionId': actionId, 'signaturesCollected': 2, 'required': 3},
      );
    }
  }

  /// Reject enforcement action
  Future<ActionResult> rejectEnforcement({
    required String actionId,
    required String signerAddress,
    required String reason,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/enforcement/$actionId/reject'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'signer': signerAddress,
          'reason': reason,
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success('Enforcement action rejected');
      }
      return ActionResult.failure('Rejection failed: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Enforcement rejected (demo mode)',
        demo: true,
      );
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // FLAG MANAGEMENT
  // ═══════════════════════════════════════════════════════════════════════════

  /// Mark a flagged transaction as reviewed
  Future<ActionResult> markAsReviewed({
    required String transactionId,
    required String reviewerAddress,
    required String verdict, // 'cleared', 'escalated', 'suspicious'
    String? notes,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/flags/$transactionId/review'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'reviewer': reviewerAddress,
          'verdict': verdict,
          'notes': notes,
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success('Transaction marked as $verdict');
      }
      return ActionResult.failure('Review failed: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Transaction marked as $verdict (demo mode)',
        demo: true,
      );
    }
  }

  /// Escalate a flagged transaction
  Future<ActionResult> escalateFlag({
    required String transactionId,
    required String escalatorAddress,
    required String reason,
  }) async {
    try {
      final response = await _client.post(
        Uri.parse('$_orchestratorUrl/flags/$transactionId/escalate'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'escalator': escalatorAddress,
          'reason': reason,
          'timestamp': DateTime.now().toIso8601String(),
        }),
      ).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        return ActionResult.success('Transaction escalated for review');
      }
      return ActionResult.failure('Escalation failed: ${response.statusCode}');
    } catch (e) {
      return ActionResult.success(
        'Transaction escalated (demo mode)',
        demo: true,
      );
    }
  }

  void dispose() {
    _client.close();
  }
}

/// Helper to show action results as snackbars
void showActionResult(BuildContext context, ActionResult result) {
  final color = result.success
      ? (result.isDemoMode ? Colors.orange : Colors.green)
      : Colors.red;
  
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Row(
        children: [
          Icon(
            result.success ? Icons.check_circle : Icons.error,
            color: Colors.white,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(child: Text(result.message)),
          if (result.isDemoMode)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.2),
                borderRadius: BorderRadius.circular(4),
              ),
              child: const Text(
                'DEMO',
                style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold),
              ),
            ),
        ],
      ),
      backgroundColor: color,
      behavior: SnackBarBehavior.floating,
      duration: Duration(seconds: result.isDemoMode ? 4 : 3),
    ),
  );
}
