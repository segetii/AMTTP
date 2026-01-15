import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Approver Providers - State management for AMTTPCore.sol approval workflow

// ========== State Classes ==========

class ApproverState {
  final bool isLoading;
  final String? error;
  final List<Map<String, dynamic>> pendingSwaps;
  final List<Map<String, dynamic>> approvedSwaps;
  final List<Map<String, dynamic>> rejectedSwaps;
  final Map<String, int> stats;

  const ApproverState({
    this.isLoading = false,
    this.error,
    this.pendingSwaps = const [],
    this.approvedSwaps = const [],
    this.rejectedSwaps = const [],
    this.stats = const {},
  });

  ApproverState copyWith({
    bool? isLoading,
    String? error,
    List<Map<String, dynamic>>? pendingSwaps,
    List<Map<String, dynamic>>? approvedSwaps,
    List<Map<String, dynamic>>? rejectedSwaps,
    Map<String, int>? stats,
  }) {
    return ApproverState(
      isLoading: isLoading ?? this.isLoading,
      error: error,
      pendingSwaps: pendingSwaps ?? this.pendingSwaps,
      approvedSwaps: approvedSwaps ?? this.approvedSwaps,
      rejectedSwaps: rejectedSwaps ?? this.rejectedSwaps,
      stats: stats ?? this.stats,
    );
  }
}

// ========== Notifiers ==========

class ApproverNotifier extends StateNotifier<ApproverState> {
  ApproverNotifier() : super(const ApproverState());

  Future<void> loadPendingSwaps() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        pendingSwaps: [
          {
            'swapId': 'SWP-001234',
            'from': '0x1234...5678',
            'to': '0xabcd...ef12',
            'amount': '2.5 ETH',
            'riskScore': 35,
            'created': '2 hours ago',
            'urgency': 'normal',
          },
          {
            'swapId': 'SWP-001235',
            'from': '0x8888...9999',
            'to': '0x1111...2222',
            'amount': '10.0 ETH',
            'riskScore': 72,
            'created': '15 min ago',
            'urgency': 'high',
          },
        ],
        stats: {
          'pending': 2,
          'approvedToday': 5,
          'rejectedToday': 1,
        },
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadApprovedSwaps() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        approvedSwaps: [
          {'swapId': 'SWP-001200', 'amount': '1.5 ETH', 'approvedAt': 'Jan 3, 2026', 'by': 'You'},
          {'swapId': 'SWP-001199', 'amount': '3.0 ETH', 'approvedAt': 'Jan 2, 2026', 'by': 'You'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> loadRejectedSwaps() async {
    state = state.copyWith(isLoading: true);
    try {
      await Future.delayed(const Duration(seconds: 1));
      state = state.copyWith(
        isLoading: false,
        rejectedSwaps: [
          {'swapId': 'SWP-001150', 'amount': '25.0 ETH', 'rejectedAt': 'Jan 1, 2026', 'reason': 'High risk score'},
        ],
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> approveSwap(String swapId) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPCore.approveSwap()
      await Future.delayed(const Duration(seconds: 2));
      
      // Move from pending to approved
      final swap = state.pendingSwaps.firstWhere((s) => s['swapId'] == swapId, orElse: () => {});
      if (swap.isNotEmpty) {
        final updatedPending = state.pendingSwaps.where((s) => s['swapId'] != swapId).toList();
        final updatedApproved = [
          ...state.approvedSwaps,
          {...swap, 'approvedAt': 'Just now', 'by': 'You'}
        ];
        state = state.copyWith(
          isLoading: false,
          pendingSwaps: updatedPending,
          approvedSwaps: updatedApproved,
        );
      } else {
        state = state.copyWith(isLoading: false);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> rejectSwap(String swapId, String reason) async {
    state = state.copyWith(isLoading: true);
    try {
      // TODO: Call AMTTPCore.rejectSwap()
      await Future.delayed(const Duration(seconds: 2));
      
      // Move from pending to rejected
      final swap = state.pendingSwaps.firstWhere((s) => s['swapId'] == swapId, orElse: () => {});
      if (swap.isNotEmpty) {
        final updatedPending = state.pendingSwaps.where((s) => s['swapId'] != swapId).toList();
        final updatedRejected = [
          ...state.rejectedSwaps,
          {...swap, 'rejectedAt': 'Just now', 'reason': reason}
        ];
        state = state.copyWith(
          isLoading: false,
          pendingSwaps: updatedPending,
          rejectedSwaps: updatedRejected,
        );
      } else {
        state = state.copyWith(isLoading: false);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  Future<void> bulkApprove(List<String> swapIds) async {
    for (final id in swapIds) {
      await approveSwap(id);
    }
  }

  Future<void> bulkReject(List<String> swapIds, String reason) async {
    for (final id in swapIds) {
      await rejectSwap(id, reason);
    }
  }
}

// ========== Providers ==========

final approverProvider = StateNotifierProvider<ApproverNotifier, ApproverState>((ref) {
  return ApproverNotifier();
});
