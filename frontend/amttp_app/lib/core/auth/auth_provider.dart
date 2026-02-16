import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'auth_service.dart';
import 'cross_app_auth_bridge.dart';
import '../rbac/roles.dart';
import '../rbac/rbac_provider.dart';

/// Authentication state
enum AuthStatus {
  initial,
  loading,
  authenticated,
  unauthenticated,
  error,
}

class AuthState {
  final AuthStatus status;
  final AppUser? user;
  final String? errorMessage;
  final bool isLoading;

  const AuthState({
    this.status = AuthStatus.initial,
    this.user,
    this.errorMessage,
    this.isLoading = false,
  });

  bool get isAuthenticated =>
      status == AuthStatus.authenticated && user != null;

  AuthState copyWith({
    AuthStatus? status,
    AppUser? user,
    String? errorMessage,
    bool? isLoading,
  }) {
    return AuthState(
      status: status ?? this.status,
      user: user ?? this.user,
      errorMessage: errorMessage,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}

/// Auth state notifier
class AuthNotifier extends StateNotifier<AuthState> {
  final AuthService _authService;
  final Ref _ref;

  AuthNotifier(this._authService, this._ref) : super(const AuthState()) {
    _init();
  }

  Future<void> _init() async {
    state = state.copyWith(status: AuthStatus.loading, isLoading: true);

    try {
      await _authService.init();

      if (_authService.isLoggedIn && _authService.currentUser != null) {
        final user = _authService.currentUser!;
        state = state.copyWith(
          status: AuthStatus.authenticated,
          user: user,
          isLoading: false,
        );

        // Sync with RBAC provider
        _ref.read(rbacProvider.notifier).setRole(user.role);
      } else {
        state = state.copyWith(
          status: AuthStatus.unauthenticated,
          isLoading: false,
        );
      }
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.error,
        errorMessage: e.toString(),
        isLoading: false,
      );
    }
  }

  /// Sign in with email and password
  Future<bool> signIn({
    required String email,
    required String password,
  }) async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final result = await _authService.signIn(
        email: email,
        password: password,
      );

      if (result.success && result.user != null) {
        final user = result.user!;

        state = state.copyWith(
          status: AuthStatus.authenticated,
          user: user,
          isLoading: false,
        );

        // Sync full RBAC context (role + identifiers)
        _ref.read(rbacProvider.notifier).login(
              role: user.role,
              userId: user.id,
              walletAddress: user.walletAddress ?? '',
              displayName: user.displayName,
            );

        // Write cross-app auth bridge cookie (web only)
        try {
          CrossAppAuthBridge.writeCookie(
            CrossAppAuthBridge.createToken(
              userId: user.id,
              email: user.email,
              role: user.role.name,
              mode: user.role.mode,
              displayName: user.displayName,
            ),
          );
        } catch (_) {}

        return true;
      } else {
        state = state.copyWith(
          status: AuthStatus.unauthenticated,
          errorMessage: result.message ?? 'Login failed',
          isLoading: false,
        );
        return false;
      }
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.error,
        errorMessage: e.toString(),
        isLoading: false,
      );
      return false;
    }
  }

  /// Register a new user
  Future<bool> register({
    required String email,
    required String password,
    required String displayName,
    required Role role,
    String? walletAddress,
  }) async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final result = await _authService.register(
        email: email,
        password: password,
        displayName: displayName,
        role: role,
        walletAddress: walletAddress,
      );

      if (result.success && result.user != null) {
        final user = result.user!;

        state = state.copyWith(
          status: AuthStatus.authenticated,
          user: user,
          isLoading: false,
        );

        // Sync full RBAC context (role + identifiers)
        _ref.read(rbacProvider.notifier).login(
              role: user.role,
              userId: user.id,
              walletAddress: user.walletAddress ?? '',
              displayName: user.displayName,
            );

        return true;
      } else {
        state = state.copyWith(
          errorMessage: result.message ?? 'Registration failed',
          isLoading: false,
        );
        return false;
      }
    } catch (e) {
      state = state.copyWith(
        status: AuthStatus.error,
        errorMessage: e.toString(),
        isLoading: false,
      );
      return false;
    }
  }

  /// Sign out
  Future<void> signOut() async {
    state = state.copyWith(isLoading: true);

    try {
      await _authService.logout();
      state = const AuthState(status: AuthStatus.unauthenticated);

      // Reset RBAC provider
      _ref.read(rbacProvider.notifier).logout();

      // Clear cross-app auth bridge cookie (web only)
      try {
        CrossAppAuthBridge.clearCookie();
      } catch (_) {}
    } catch (e) {
      state = state.copyWith(
        errorMessage: e.toString(),
        isLoading: false,
      );
    }
  }

  /// Update user profile
  Future<bool> updateProfile({
    String? displayName,
    Role? role,
    String? walletAddress,
  }) async {
    if (state.user == null) return false;

    state = state.copyWith(isLoading: true);

    try {
      final result = await _authService.updateProfile(
        userId: state.user!.id,
        displayName: displayName,
        role: role,
        walletAddress: walletAddress,
      );

      if (result.success && result.user != null) {
        state = state.copyWith(
          user: result.user,
          isLoading: false,
        );

        // Sync with RBAC provider
        _ref.read(rbacProvider.notifier).setRole(result.user!.role);

        return true;
      }
      return false;
    } catch (e) {
      state = state.copyWith(
        errorMessage: e.toString(),
        isLoading: false,
      );
      return false;
    }
  }

  /// Clear error message
  void clearError() {
    state = state.copyWith(errorMessage: null);
  }
}

/// Auth service provider
final authServiceProvider = Provider<AuthService>((ref) {
  return AuthService();
});

/// Auth state provider
final authProvider = StateNotifierProvider<AuthNotifier, AuthState>((ref) {
  final authService = ref.watch(authServiceProvider);
  return AuthNotifier(authService, ref);
});

/// Convenience provider for checking if authenticated
final isAuthenticatedProvider = Provider<bool>((ref) {
  return ref.watch(authProvider).isAuthenticated;
});

/// Convenience provider for current user
final currentUserProvider = Provider<AppUser?>((ref) {
  return ref.watch(authProvider).user;
});
