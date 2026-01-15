import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Session Key Providers - State management for AMTTPBiconomyModule.sol (ERC-4337)

// ========== State Classes ==========

class SessionKeyState {
  final bool isLoading;
  final String? error;
  final bool isAccountRegistered;
  final Map<String, dynamic>? accountConfig;
  final List<Map<String, dynamic>> activeKeys;
  final List<Map<String, dynamic>> keyHistory;

  const SessionKeyState({
    this.isLoading = false,
    this.error,
    this.isAccountRegistered = false,
    this.accountConfig,
    this.activeKeys = const [],
    this.keyHistory = const [],
  });

  SessionKeyState copyWith({
    bool? isLoading,
    String? error,
    bool? isAccountRegistered,
    Map<String, dynamic>? accountConfig,
    List<Map<String, dynamic>>? activeKeys,
    List<Map<String, dynamic>>? keyHistory,
  }) {
    return SessionKeyState(
      isLoading: isLoading ?? this.isLoading,
      error: error,
      isAccountRegistered: isAccountRegistered ?? this.isAccountRegistered,
      accountConfig: accountConfig ?? this.accountConfig,
      activeKeys: activeKeys ?? this.activeKeys,
      keyHistory: keyHistory ?? this.keyHistory,
    );
  }
}

// ========== Notifiers ==========

class SessionKeyNotifier extends StateNotifier<SessionKeyState> {
  SessionKeyNotifier() : super(const SessionKeyState());

  Future<void> checkAccountRegistration(String accountAddress) async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        isAccountRegistered: true,
        accountConfig: {
          'address': accountAddress,
          'dailyLimit': 1.0,
          'riskThreshold': 70,
          'gaslessEnabled': true,
          'sessionKeysEnabled': true,
        },
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadActiveKeys() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        activeKeys: [
          {
            'key': '0x742d...f44e',
            'created': 'Jan 4, 2026 10:00',
            'expires': 'Jan 5, 2026 10:00',
            'limit': 1.0,
            'used': 0.25,
            'status': 'active',
          },
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadKeyHistory() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        keyHistory: [
          {'key': '0xabc1...', 'action': 'Revoked', 'date': 'Jan 3, 2026', 'reason': 'Manual revoke'},
          {'key': '0xdef4...', 'action': 'Expired', 'date': 'Jan 1, 2026', 'reason': 'Validity ended'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> registerAccount({
    required String accountAddress,
    required double dailyLimit,
    required int riskThreshold,
    required bool enableGasless,
    required bool enableSessionKeys,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPBiconomyModule.registerAccount()
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(
        isLoading: false,
        isAccountRegistered: true,
        accountConfig: {
          'address': accountAddress,
          'dailyLimit': dailyLimit,
          'riskThreshold': riskThreshold,
          'gaslessEnabled': enableGasless,
          'sessionKeysEnabled': enableSessionKeys,
        },
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> updateAccountConfig({
    required double dailyLimit,
    required int riskThreshold,
    required bool enableGasless,
    required bool enableSessionKeys,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPBiconomyModule.updateAccountConfig()
      await Future.delayed(const Duration(seconds: 2));
      if (state.accountConfig != null) {
        state = state.copyWith(
          isLoading: false,
          accountConfig: {
            ...state.accountConfig!,
            'dailyLimit': dailyLimit,
            'riskThreshold': riskThreshold,
            'gaslessEnabled': enableGasless,
            'sessionKeysEnabled': enableSessionKeys,
          },
        );
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> createSessionKey({
    required String sessionKeyAddress,
    required String validityPeriod,
    required double maxPerTx,
    required double totalSpendLimit,
    List<String>? allowedContracts,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPBiconomyModule.createSessionKey()
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(isLoading: false);
      await loadActiveKeys();
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> revokeSessionKey(String keyAddress) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPBiconomyModule.revokeSessionKey()
      await Future.delayed(const Duration(seconds: 2));
      final updatedKeys = state.activeKeys.where((k) => k['key'] != keyAddress).toList();
      state = state.copyWith(isLoading: false, activeKeys: updatedKeys);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }
}

// ========== Providers ==========

final sessionKeyProvider = StateNotifierProvider<SessionKeyNotifier, SessionKeyState>((ref) {
  return SessionKeyNotifier();
});
