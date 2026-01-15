import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';

// Re-export classes used by providers
export '../services/api_service.dart' show PolicyEvaluationResult, ReputationResponse, MonitoringAlert, BulkJobStatus;

/// Singleton API Service provider
final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService();
});

/// ═══════════════════════════════════════════════════════════════════════════
/// RISK SCORING PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Request parameters for risk scoring
class RiskScoreRequest {
  final String fromAddress;
  final String toAddress;
  final double amount;
  final Map<String, dynamic>? features;

  RiskScoreRequest({
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    this.features,
  });

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RiskScoreRequest &&
          runtimeType == other.runtimeType &&
          fromAddress == other.fromAddress &&
          toAddress == other.toAddress &&
          amount == other.amount;

  @override
  int get hashCode => fromAddress.hashCode ^ toAddress.hashCode ^ amount.hashCode;
}

/// Async provider for DQN risk scoring
final riskScoreProvider = FutureProvider.family<RiskScoreResponse, RiskScoreRequest>((ref, request) async {
  final apiService = ref.read(apiServiceProvider);
  
  try {
    return await apiService.getDQNRiskScore(
      fromAddress: request.fromAddress,
      toAddress: request.toAddress,
      amount: request.amount,
      features: request.features ?? {},
    );
  } catch (e) {
    // Fallback to heuristic scoring
    return await apiService.getHeuristicRiskScore(
      fromAddress: request.fromAddress,
      toAddress: request.toAddress,
      amount: request.amount,
    );
  }
});

/// ═══════════════════════════════════════════════════════════════════════════
/// KYC PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// KYC status for an address
final kycStatusProvider = FutureProvider.family<KYCStatusResponse, String>((ref, address) async {
  if (address.isEmpty) {
    return KYCStatusResponse(
      status: 'none',
      isVerified: false,
      verifiedAt: null,
      documentType: null,
    );
  }
  
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getKYCStatus(address);
});

/// ═══════════════════════════════════════════════════════════════════════════
/// TRANSACTION PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Transaction history for an address
final transactionHistoryProvider = FutureProvider.family<List<TransactionHistoryItem>, String>((ref, address) async {
  if (address.isEmpty) return [];
  
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getTransactionHistory(address);
});

/// Transaction validation request
class TransactionValidationRequest {
  final String fromAddress;
  final String toAddress;
  final double amount;
  final double riskScore;

  TransactionValidationRequest({
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    required this.riskScore,
  });
}

/// Validate a transaction before execution
final transactionValidationProvider = FutureProvider.family<TransactionValidationResponse, TransactionValidationRequest>((ref, request) async {
  final apiService = ref.read(apiServiceProvider);
  return await apiService.validateTransaction(
    fromAddress: request.fromAddress,
    toAddress: request.toAddress,
    amount: request.amount,
    riskScore: request.riskScore,
  );
});

/// ═══════════════════════════════════════════════════════════════════════════
/// POLICY PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Policy evaluation state
class PolicyEvaluationState {
  final bool isLoading;
  final PolicyEvaluationResult? result;
  final String? error;

  PolicyEvaluationState({
    this.isLoading = false,
    this.result,
    this.error,
  });

  PolicyEvaluationState copyWith({
    bool? isLoading,
    PolicyEvaluationResult? result,
    String? error,
  }) {
    return PolicyEvaluationState(
      isLoading: isLoading ?? this.isLoading,
      result: result ?? this.result,
      error: error ?? this.error,
    );
  }
}

/// Policy evaluation notifier for transaction policies
class PolicyEvaluationNotifier extends StateNotifier<PolicyEvaluationState> {
  final ApiService _apiService;

  PolicyEvaluationNotifier(this._apiService) : super(PolicyEvaluationState());

  Future<PolicyEvaluationResult> evaluate({
    required String fromAddress,
    required String toAddress,
    required double amount,
    required double riskScore,
  }) async {
    state = state.copyWith(isLoading: true, error: null);

    try {
      final result = await _apiService.evaluatePolicy(
        fromAddress: fromAddress,
        toAddress: toAddress,
        amount: amount,
        riskScore: riskScore,
      );

      state = state.copyWith(isLoading: false, result: result);
      return result;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  void reset() {
    state = PolicyEvaluationState();
  }
}

final policyEvaluationProvider = StateNotifierProvider<PolicyEvaluationNotifier, PolicyEvaluationState>((ref) {
  return PolicyEvaluationNotifier(ref.read(apiServiceProvider));
});

/// ═══════════════════════════════════════════════════════════════════════════
/// DISPUTE PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Dispute list for an address
final disputesProvider = FutureProvider.family<List<DisputeDetails>, String>((ref, address) async {
  if (address.isEmpty) return [];
  
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getDisputesByAddress(address);
});

/// Dispute state for creating/managing disputes
class DisputeState {
  final bool isLoading;
  final DisputeDetails? currentDispute;
  final String? error;

  DisputeState({
    this.isLoading = false,
    this.currentDispute,
    this.error,
  });
}

class DisputeNotifier extends StateNotifier<DisputeState> {
  final ApiService _apiService;

  DisputeNotifier(this._apiService) : super(DisputeState());

  Future<DisputeDetails> openDispute({
    required String swapId,
    required String claimant,
    required String respondent,
    required String amountInDispute,
    required String reason,
  }) async {
    state = DisputeState(isLoading: true);

    try {
      // Create dispute using the actual API method
      final disputeResponse = await _apiService.createDispute(
        txId: swapId,
        disputantAddress: claimant,
        reason: reason,
        escrowAmount: double.parse(amountInDispute),
      );

      // Get full dispute details
      final dispute = await _apiService.getDisputeDetails(disputeResponse.disputeId);

      state = DisputeState(currentDispute: dispute);
      return dispute;
    } catch (e) {
      state = DisputeState(error: e.toString());
      rethrow;
    }
  }

  Future<void> submitEvidence({
    required String disputeId,
    required String submittedBy,
    required String content,
  }) async {
    state = DisputeState(isLoading: true, currentDispute: state.currentDispute);

    try {
      await _apiService.submitEvidence(
        disputeId: disputeId,
        submitterAddress: submittedBy,
        evidenceType: 'document', // Default evidence type
        content: content,
      );

      // Refresh dispute
      final dispute = await _apiService.getDisputeDetails(disputeId);
      state = DisputeState(currentDispute: dispute);
    } catch (e) {
      state = DisputeState(error: e.toString(), currentDispute: state.currentDispute);
      rethrow;
    }
  }
}

final disputeNotifierProvider = StateNotifierProvider<DisputeNotifier, DisputeState>((ref) {
  return DisputeNotifier(ref.read(apiServiceProvider));
});

/// ═══════════════════════════════════════════════════════════════════════════
/// REPUTATION PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Reputation score for an address
final reputationProvider = FutureProvider.family<ReputationResponse, String>((ref, address) async {
  if (address.isEmpty) {
    return ReputationResponse(
      address: '',
      score: 50,
      tier: 'BRONZE',
      totalTransactions: 0,
      successfulTransactions: 0,
      disputes: 0,
      disputesWon: 0,
      stakedAmount: 0.0,
      lastUpdated: DateTime.now(),
    );
  }
  
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getReputation(address);
});

/// ═══════════════════════════════════════════════════════════════════════════
/// MONITORING PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Monitoring alerts for an entity
final monitoringAlertsProvider = FutureProvider.family<List<MonitoringAlert>, String>((ref, entityId) async {
  if (entityId.isEmpty) return [];
  
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getMonitoringAlerts(address: entityId);
});

/// ═══════════════════════════════════════════════════════════════════════════
/// BULK SCORING PROVIDERS
/// ═══════════════════════════════════════════════════════════════════════════

/// Bulk job status
final bulkJobStatusProvider = FutureProvider.family<BulkJobStatus, String>((ref, jobId) async {
  final apiService = ref.read(apiServiceProvider);
  return await apiService.getBulkJobStatus(jobId);
});
