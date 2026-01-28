import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../repositories/repositories.dart';

/// Riverpod providers for all repositories
/// 
/// These providers use lazy singleton pattern - repositories are created
/// once and cached for the lifetime of the app.
/// 
/// Usage:
/// ```dart
/// class MyWidget extends ConsumerWidget {
///   @override
///   Widget build(BuildContext context, WidgetRef ref) {
///     final riskRepo = ref.watch(riskRepositoryProvider);
///     // Use repository...
///   }
/// }
/// ```

/// Risk scoring repository provider
final riskRepositoryProvider = Provider<RiskRepository>((ref) {
  return RiskRepository();
});

/// Compliance evaluation repository provider
final complianceRepositoryProvider = Provider<ComplianceRepository>((ref) {
  return ComplianceRepository();
});

/// KYC verification repository provider
final kycRepositoryProvider = Provider<KycRepository>((ref) {
  return KycRepository();
});

/// Dispute management repository provider
final disputeRepositoryProvider = Provider<DisputeRepository>((ref) {
  return DisputeRepository();
});

/// Wallet balance/history repository provider
final walletRepositoryProvider = Provider<WalletRepository>((ref) {
  return WalletRepository();
});

/// Policy management repository provider
final policyRepositoryProvider = Provider<PolicyRepository>((ref) {
  return PolicyRepository();
});

// ============================================================
// Async state providers for common operations
// ============================================================

/// Provider for fetching risk score
/// Usage: ref.watch(riskScoreProvider(RiskScoreParams(address, to, value)))
final riskScoreProvider = FutureProvider.family<RiskScore, RiskScoreParams>(
  (ref, params) async {
    final repo = ref.watch(riskRepositoryProvider);
    return repo.scoreTransaction(
      from: params.from,
      to: params.to,
      value: params.value,
      data: params.data,
    );
  },
);

/// Parameters for risk score provider
class RiskScoreParams {
  final String from;
  final String to;
  final String value;
  final String? data;

  RiskScoreParams({
    required this.from,
    required this.to,
    required this.value,
    this.data,
  });

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is RiskScoreParams &&
          runtimeType == other.runtimeType &&
          from == other.from &&
          to == other.to &&
          value == other.value &&
          data == other.data;

  @override
  int get hashCode => from.hashCode ^ to.hashCode ^ value.hashCode ^ (data?.hashCode ?? 0);
}

/// Provider for fetching compliance decision
final complianceDecisionProvider = FutureProvider.family<ComplianceDecision, ComplianceParams>(
  (ref, params) async {
    final repo = ref.watch(complianceRepositoryProvider);
    return repo.evaluateTransaction(
      from: params.from,
      to: params.to,
      value: params.value,
      chainId: params.chainId,
    );
  },
);

/// Parameters for compliance decision provider
class ComplianceParams {
  final String from;
  final String to;
  final String value;
  final String? chainId;

  ComplianceParams({
    required this.from,
    required this.to,
    required this.value,
    this.chainId,
  });

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ComplianceParams &&
          runtimeType == other.runtimeType &&
          from == other.from &&
          to == other.to &&
          value == other.value &&
          chainId == other.chainId;

  @override
  int get hashCode => from.hashCode ^ to.hashCode ^ value.hashCode ^ (chainId?.hashCode ?? 0);
}

/// Provider for KYC status
final kycStatusProvider = FutureProvider.family<KycStatusResult, String>(
  (ref, address) async {
    final repo = ref.watch(kycRepositoryProvider);
    return repo.getStatus(address);
  },
);

/// Provider for wallet balance
final walletBalanceProvider = FutureProvider.family<WalletBalance, WalletParams>(
  (ref, params) async {
    final repo = ref.watch(walletRepositoryProvider);
    return repo.getBalance(params.address, chainId: params.chainId);
  },
);

/// Parameters for wallet providers
class WalletParams {
  final String address;
  final String? chainId;

  WalletParams({required this.address, this.chainId});

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is WalletParams &&
          runtimeType == other.runtimeType &&
          address == other.address &&
          chainId == other.chainId;

  @override
  int get hashCode => address.hashCode ^ (chainId?.hashCode ?? 0);
}

/// Provider for token balances
final tokenBalancesProvider = FutureProvider.family<List<TokenBalance>, WalletParams>(
  (ref, params) async {
    final repo = ref.watch(walletRepositoryProvider);
    return repo.getTokenBalances(params.address, chainId: params.chainId);
  },
);

/// Provider for policies by address
final policiesProvider = FutureProvider.family<List<Policy>, String>(
  (ref, address) async {
    final repo = ref.watch(policyRepositoryProvider);
    return repo.getPoliciesForAddress(address);
  },
);

/// Provider for disputes by address
final disputesProvider = FutureProvider.family<List<Dispute>, String>(
  (ref, address) async {
    final repo = ref.watch(disputeRepositoryProvider);
    return repo.getDisputesForAddress(address);
  },
);
