import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Compliance Providers - State management for AMTTPPolicyEngine.sol

// ========== State Classes ==========

class ComplianceState {
  final bool isLoading;
  final String? error;
  final List<Map<String, dynamic>> frozenAccounts;
  final List<Map<String, dynamic>> trustedUsers;
  final List<Map<String, dynamic>> trustedCounterparties;
  final List<Map<String, dynamic>> pepScreeningResults;
  final List<Map<String, dynamic>> eddQueue;

  const ComplianceState({
    this.isLoading = false,
    this.error,
    this.frozenAccounts = const [],
    this.trustedUsers = const [],
    this.trustedCounterparties = const [],
    this.pepScreeningResults = const [],
    this.eddQueue = const [],
  });

  ComplianceState copyWith({
    bool? isLoading,
    String? error,
    List<Map<String, dynamic>>? frozenAccounts,
    List<Map<String, dynamic>>? trustedUsers,
    List<Map<String, dynamic>>? trustedCounterparties,
    List<Map<String, dynamic>>? pepScreeningResults,
    List<Map<String, dynamic>>? eddQueue,
  }) {
    return ComplianceState(
      isLoading: isLoading ?? this.isLoading,
      error: error,
      frozenAccounts: frozenAccounts ?? this.frozenAccounts,
      trustedUsers: trustedUsers ?? this.trustedUsers,
      trustedCounterparties: trustedCounterparties ?? this.trustedCounterparties,
      pepScreeningResults: pepScreeningResults ?? this.pepScreeningResults,
      eddQueue: eddQueue ?? this.eddQueue,
    );
  }
}

// ========== Notifiers ==========

class ComplianceNotifier extends StateNotifier<ComplianceState> {
  ComplianceNotifier() : super(const ComplianceState());

  Future<void> loadFrozenAccounts() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        frozenAccounts: [
          {'address': '0x1234...5678', 'frozenAt': 'Jan 3, 2026', 'reason': 'Suspicious activity', 'by': 'Compliance Officer'},
          {'address': '0xabcd...ef12', 'frozenAt': 'Jan 1, 2026', 'reason': 'OFAC match', 'by': 'Automated'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadTrustedAddresses() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        trustedUsers: [
          {'address': '0x7777...8888', 'addedAt': 'Jan 2, 2026'},
          {'address': '0xbbbb...cccc', 'addedAt': 'Dec 28, 2025'},
        ],
        trustedCounterparties: [
          {'address': '0x9999...aaaa', 'addedAt': 'Jan 1, 2026'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadEDDQueue() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        eddQueue: [
          {'address': '0x1111...2222', 'reason': 'High-value transaction', 'priority': 'high', 'submitted': '2 hours ago'},
          {'address': '0x3333...4444', 'reason': 'New counterparty', 'priority': 'medium', 'submitted': '1 day ago'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> freezeAccount({
    required String address,
    required String reason,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPPolicyEngine.freezeAccount()
      await Future.delayed(const Duration(seconds: 2));
      final newFrozen = [
        ...state.frozenAccounts,
        {'address': address, 'frozenAt': 'Just now', 'reason': reason, 'by': 'You'},
      ];
      state = state.copyWith(isLoading: false, frozenAccounts: newFrozen);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> unfreezeAccount(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPPolicyEngine.unfreezeAccount()
      await Future.delayed(const Duration(seconds: 2));
      final updated = state.frozenAccounts.where((a) => a['address'] != address).toList();
      state = state.copyWith(isLoading: false, frozenAccounts: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> addTrustedUser(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPPolicyEngine.addTrustedUser()
      await Future.delayed(const Duration(seconds: 2));
      final updated = [
        ...state.trustedUsers,
        {'address': address, 'addedAt': 'Just now'},
      ];
      state = state.copyWith(isLoading: false, trustedUsers: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> addTrustedCounterparty(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPPolicyEngine.addTrustedCounterparty()
      await Future.delayed(const Duration(seconds: 2));
      final updated = [
        ...state.trustedCounterparties,
        {'address': address, 'addedAt': 'Just now'},
      ];
      state = state.copyWith(isLoading: false, trustedCounterparties: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> removeTrustedUser(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      final updated = state.trustedUsers.where((u) => u['address'] != address).toList();
      state = state.copyWith(isLoading: false, trustedUsers: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> removeTrustedCounterparty(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      final updated = state.trustedCounterparties.where((c) => c['address'] != address).toList();
      state = state.copyWith(isLoading: false, trustedCounterparties: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> runPEPScreening(String addressOrName) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call API for PEP/Sanctions screening
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(
        isLoading: false,
        pepScreeningResults: [
          {'source': 'OFAC SDN', 'match': 'No Match', 'score': 0},
          {'source': 'UN Sanctions', 'match': 'No Match', 'score': 0},
          {'source': 'EU Sanctions', 'match': 'No Match', 'score': 0},
          {'source': 'PEP Database', 'match': 'Potential Match', 'score': 45},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> completeEDD(String address) async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      final updated = state.eddQueue.where((e) => e['address'] != address).toList();
      state = state.copyWith(isLoading: false, eddQueue: updated);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }
}

// ========== Providers ==========

final complianceProvider = StateNotifierProvider<ComplianceNotifier, ComplianceState>((ref) {
  return ComplianceNotifier();
});
