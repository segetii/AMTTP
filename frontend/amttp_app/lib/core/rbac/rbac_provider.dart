/// RBAC Provider - State management for role-based access
///
/// Provides:
/// - Current user role state
/// - App mode (Focus/War Room)
/// - Permission checks
/// - Role switching (for testing)
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'roles.dart';

/// User session state with RBAC
class RBACState {
  final Role role;
  final AppMode mode;
  final String userId;
  final String walletAddress;
  final String? institutionId;
  final String displayName;
  final bool isAuthenticated;
  final DateTime? sessionExpiry;
  final String? sessionToken;

  const RBACState({
    this.role = Role.r1EndUser,
    this.mode = AppMode.focusMode,
    this.userId = '',
    this.walletAddress = '',
    this.institutionId,
    this.displayName = 'Guest',
    this.isAuthenticated = false,
    this.sessionExpiry,
    this.sessionToken,
  });

  RBACState copyWith({
    Role? role,
    AppMode? mode,
    String? userId,
    String? walletAddress,
    String? institutionId,
    String? displayName,
    bool? isAuthenticated,
    DateTime? sessionExpiry,
    String? sessionToken,
  }) {
    return RBACState(
      role: role ?? this.role,
      mode: mode ?? this.mode,
      userId: userId ?? this.userId,
      walletAddress: walletAddress ?? this.walletAddress,
      institutionId: institutionId ?? this.institutionId,
      displayName: displayName ?? this.displayName,
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      sessionExpiry: sessionExpiry ?? this.sessionExpiry,
      sessionToken: sessionToken ?? this.sessionToken,
    );
  }

  /// Get capabilities for current role
  RoleCapabilities get capabilities => getCapabilities(role);

  /// Check if user can perform an action
  bool can(String action) => canPerform(role, action);

  /// Check if session is valid
  bool get isSessionValid {
    if (!isAuthenticated) return false;
    if (sessionExpiry == null) return true;
    return DateTime.now().isBefore(sessionExpiry!);
  }

  /// Check if user is in Focus Mode
  bool get isFocusMode => mode == AppMode.focusMode;

  /// Check if user is in War Room Mode
  bool get isWarRoomMode => mode == AppMode.warRoomMode;

  /// Check if user is an end user (R1 or R2)
  bool get isEndUser => role == Role.r1EndUser || role == Role.r2EndUserPep;

  /// Check if user is institutional (R3+)
  bool get isInstitutional => role.level >= Role.r3InstitutionOps.level;

  /// Check if user is admin (R5+)
  bool get isAdmin => role.level >= Role.r5PlatformAdmin.level;
}

/// RBAC State Notifier
class RBACNotifier extends StateNotifier<RBACState> {
  RBACNotifier() : super(const RBACState());

  /// Login with role
  void login({
    required Role role,
    required String userId,
    required String walletAddress,
    String? institutionId,
    String? displayName,
    String? sessionToken,
    Duration sessionDuration = const Duration(hours: 24),
  }) {
    state = RBACState(
      role: role,
      mode: getModeForRole(role),
      userId: userId,
      walletAddress: walletAddress,
      institutionId: institutionId,
      displayName: displayName ?? role.displayName,
      isAuthenticated: true,
      sessionExpiry: DateTime.now().add(sessionDuration),
      sessionToken: sessionToken,
    );
  }

  /// Logout
  void logout() {
    state = const RBACState();
  }

  /// Switch role (for testing/demo)
  void switchRole(Role role) {
    state = state.copyWith(
      role: role,
      mode: getModeForRole(role),
      displayName: role.displayName,
      isAuthenticated: true,
    );
  }

  /// Set role (alias for switchRole - used by auth provider)
  void setRole(Role role) {
    state = state.copyWith(
      role: role,
      mode: getModeForRole(role),
      isAuthenticated: true,
    );
  }

  /// Switch mode (if allowed by role)
  void switchMode(AppMode mode) {
    // End users can only use Focus Mode
    if (state.isEndUser && mode == AppMode.warRoomMode) {
      return;
    }
    state = state.copyWith(mode: mode);
  }

  /// Update session token
  void updateSessionToken(String token, {Duration? duration}) {
    state = state.copyWith(
      sessionToken: token,
      sessionExpiry:
          duration != null ? DateTime.now().add(duration) : state.sessionExpiry,
    );
  }

  /// Update wallet address
  void updateWallet(String walletAddress) {
    state = state.copyWith(walletAddress: walletAddress);
  }
}

/// Main RBAC provider
final rbacProvider = StateNotifierProvider<RBACNotifier, RBACState>((ref) {
  return RBACNotifier();
});

/// Provider for current role
final currentRoleProvider = Provider<Role>((ref) {
  return ref.watch(rbacProvider).role;
});

/// Provider for current mode
final currentModeProvider = Provider<AppMode>((ref) {
  return ref.watch(rbacProvider).mode;
});

/// Provider for checking if RBAC-authenticated (use auth isAuthenticatedProvider for canonical check)
final isRbacAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(rbacProvider).isAuthenticated;
});

/// Provider for checking capabilities
final capabilitiesProvider = Provider<RoleCapabilities>((ref) {
  return ref.watch(rbacProvider).capabilities;
});

/// Provider for checking specific permission
final canPerformProvider = Provider.family<bool, String>((ref, action) {
  return ref.watch(rbacProvider).can(action);
});

/// Provider for focus mode check
final isFocusModeProvider = Provider<bool>((ref) {
  return ref.watch(rbacProvider).isFocusMode;
});

/// Provider for war room mode check
final isWarRoomModeProvider = Provider<bool>((ref) {
  return ref.watch(rbacProvider).isWarRoomMode;
});
