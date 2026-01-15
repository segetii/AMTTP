import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Dispute Providers - State management for AMTTPDisputeResolver.sol functionality

// ========== State Classes ==========

class DisputeState {
  final bool isLoading;
  final String? error;
  final List<Map<String, dynamic>> activeDisputes;
  final List<Map<String, dynamic>> disputeHistory;
  final Map<String, dynamic>? currentDispute;

  const DisputeState({
    this.isLoading = false,
    this.error,
    this.activeDisputes = const [],
    this.disputeHistory = const [],
    this.currentDispute,
  });

  DisputeState copyWith({
    bool? isLoading,
    String? error,
    List<Map<String, dynamic>>? activeDisputes,
    List<Map<String, dynamic>>? disputeHistory,
    Map<String, dynamic>? currentDispute,
  }) {
    return DisputeState(
      isLoading: isLoading ?? this.isLoading,
      error: error,
      activeDisputes: activeDisputes ?? this.activeDisputes,
      disputeHistory: disputeHistory ?? this.disputeHistory,
      currentDispute: currentDispute ?? this.currentDispute,
    );
  }
}

// ========== Notifiers ==========

class DisputeNotifier extends StateNotifier<DisputeState> {
  DisputeNotifier() : super(const DisputeState());

  Future<void> loadActiveDisputes() async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Integrate with API/blockchain
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        activeDisputes: [
          {
            'id': 'DIS-001',
            'status': 'evidence_period',
            'swapId': 'SWP-001234',
            'amount': '2.5 ETH',
            'daysLeft': 5,
          },
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadDisputeHistory() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        disputeHistory: [
          {'id': 'DIS-098', 'status': 'resolved', 'outcome': 'challenger_won'},
          {'id': 'DIS-097', 'status': 'resolved', 'outcome': 'respondent_won'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadDisputeDetail(String disputeId) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Fetch from API
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(isLoading: false, currentDispute: {
        'id': disputeId,
        'status': 'evidence_period',
        'created': 'Jan 2, 2026',
      });
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> challengeTransaction({
    required String swapId,
    required String reason,
    required double stakeAmount,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPDisputeResolver.challengeTransaction()
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> submitEvidence({
    required String disputeId,
    required String evidence,
    List<String>? attachments,
  }) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPDisputeResolver.submitEvidence()
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> requestAppeal(String disputeId) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPDisputeResolver.requestAppeal()
      await Future.delayed(const Duration(seconds: 2));
      state = state.copyWith(isLoading: false);
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }
}

// ========== Providers ==========

final disputeProvider = StateNotifierProvider<DisputeNotifier, DisputeState>((ref) {
  return DisputeNotifier();
});
