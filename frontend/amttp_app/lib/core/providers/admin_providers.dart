import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';

/// Provider for API Service
final adminApiServiceProvider = Provider<ApiService>((ref) => ApiService());

// ============================================================
// SYSTEM HEALTH & METRICS
// ============================================================

/// System health state
class SystemHealth {
  final bool isOperational;
  final double uptime;
  final String modelStatus;
  final String modelVersion;
  final int todayTransactions;
  final int todayTransactionsChange;
  final int fraudBlocked;
  final double fraudRate;
  final int pendingEDDCases;
  final int unresolvedAlerts;

  SystemHealth({
    required this.isOperational,
    required this.uptime,
    required this.modelStatus,
    required this.modelVersion,
    required this.todayTransactions,
    required this.todayTransactionsChange,
    required this.fraudBlocked,
    required this.fraudRate,
    required this.pendingEDDCases,
    required this.unresolvedAlerts,
  });

  factory SystemHealth.initial() => SystemHealth(
    isOperational: true,
    uptime: 99.9,
    modelStatus: 'Active',
    modelVersion: 'DQN v2.1.0',
    todayTransactions: 0,
    todayTransactionsChange: 0,
    fraudBlocked: 0,
    fraudRate: 0.0,
    pendingEDDCases: 0,
    unresolvedAlerts: 0,
  );
}

/// Provider for system health
final systemHealthProvider = FutureProvider<SystemHealth>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  
  try {
    // Parallel fetch all metrics
    final results = await Future.wait([
      api.getPendingEDDCases().catchError((_) => <EDDCaseDetails>[]),
      api.getMonitoringAlerts(unresolvedOnly: true).catchError((_) => <MonitoringAlert>[]),
      api.getActivePolicies().catchError((_) => <PolicyInfo>[]),
    ]);

    final pendingEDD = results[0] as List<EDDCaseDetails>;
    final unresolvedAlerts = results[1] as List<MonitoringAlert>;

    return SystemHealth(
      isOperational: true,
      uptime: 99.9,
      modelStatus: 'Active',
      modelVersion: 'DQN v2.1.0 (F1: 0.669)',
      todayTransactions: 2847, // Would come from backend metrics endpoint
      todayTransactionsChange: 12,
      fraudBlocked: 23,
      fraudRate: 0.8,
      pendingEDDCases: pendingEDD.length,
      unresolvedAlerts: unresolvedAlerts.length,
    );
  } catch (e) {
    // Return defaults on error
    return SystemHealth.initial();
  }
});

// ============================================================
// DISPUTE MANAGEMENT
// ============================================================

/// Provider for pending disputes (for admin review)
final pendingDisputesProvider = FutureProvider<List<DisputeDetails>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  // In production, this would fetch all pending disputes for admin
  // For now we'll return empty list
  return [];
});

// ============================================================
// EDD CASES
// ============================================================

/// Provider for pending EDD cases
final pendingEDDCasesProvider = FutureProvider<List<EDDCaseDetails>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  try {
    return await api.getPendingEDDCases();
  } catch (e) {
    return [];
  }
});

// ============================================================
// MONITORING ALERTS
// ============================================================

/// Provider for unresolved monitoring alerts
final unresolvedAlertsProvider = FutureProvider<List<MonitoringAlert>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  try {
    return await api.getMonitoringAlerts(unresolvedOnly: true);
  } catch (e) {
    return [];
  }
});

// ============================================================
// REPUTATION LEADERBOARD
// ============================================================

/// Provider for reputation leaderboard
final reputationLeaderboardProvider = FutureProvider<List<LeaderboardEntry>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  try {
    return await api.getReputationLeaderboard(limit: 20);
  } catch (e) {
    return [];
  }
});

// ============================================================
// POLICY MANAGEMENT
// ============================================================

/// Provider for active policies
final activePoliciesProvider = FutureProvider<List<PolicyInfo>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  try {
    return await api.getActivePolicies();
  } catch (e) {
    return [];
  }
});

// ============================================================
// WEBHOOK MANAGEMENT
// ============================================================

/// Provider for registered webhooks
final registeredWebhooksProvider = FutureProvider<List<WebhookInfo>>((ref) async {
  final api = ref.read(adminApiServiceProvider);
  try {
    return await api.listWebhooks();
  } catch (e) {
    return [];
  }
});

// ============================================================
// RISK DISTRIBUTION
// ============================================================

class RiskDistribution {
  final int lowRisk;
  final int mediumRisk;
  final int highRisk;
  final int blocked;

  RiskDistribution({
    required this.lowRisk,
    required this.mediumRisk,
    required this.highRisk,
    required this.blocked,
  });

  int get total => lowRisk + mediumRisk + highRisk + blocked;

  double get lowRiskPercent => total > 0 ? lowRisk / total * 100 : 0;
  double get mediumRiskPercent => total > 0 ? mediumRisk / total * 100 : 0;
  double get highRiskPercent => total > 0 ? highRisk / total * 100 : 0;
  double get blockedPercent => total > 0 ? blocked / total * 100 : 0;
}

/// Provider for risk distribution
final riskDistributionProvider = Provider<RiskDistribution>((ref) {
  // In production, this would come from backend analytics
  return RiskDistribution(
    lowRisk: 70,
    mediumRisk: 20,
    highRisk: 8,
    blocked: 2,
  );
});

// ============================================================
// REAL-TIME TRANSACTION FEED
// ============================================================

class RealtimeTransaction {
  final String txId;
  final String fromAddress;
  final String toAddress;
  final double amount;
  final double riskScore;
  final String status;
  final DateTime timestamp;

  RealtimeTransaction({
    required this.txId,
    required this.fromAddress,
    required this.toAddress,
    required this.amount,
    required this.riskScore,
    required this.status,
    required this.timestamp,
  });
}

/// State notifier for real-time transactions (would use WebSocket in production)
class RealtimeTransactionNotifier extends StateNotifier<List<RealtimeTransaction>> {
  RealtimeTransactionNotifier() : super(_generateMockTransactions());

  static List<RealtimeTransaction> _generateMockTransactions() {
    return List.generate(20, (index) {
      final riskScore = 0.1 + (index * 0.08) % 0.8;
      return RealtimeTransaction(
        txId: '0x${(1000000 + index).toRadixString(16)}',
        fromAddress: '0x1234...${(1000 + index).toString().substring(0, 4)}',
        toAddress: '0x5678...${(5000 + index).toString().substring(0, 4)}',
        amount: 100 + (index * 150) % 1000,
        riskScore: riskScore,
        status: riskScore < 0.4 ? 'approved' : riskScore < 0.7 ? 'monitoring' : riskScore < 0.8 ? 'escrow' : 'blocked',
        timestamp: DateTime.now().subtract(Duration(minutes: index)),
      );
    });
  }

  void addTransaction(RealtimeTransaction tx) {
    state = [tx, ...state.take(19)];
  }

  void refresh() {
    state = _generateMockTransactions();
  }
}

final realtimeTransactionsProvider = 
    StateNotifierProvider<RealtimeTransactionNotifier, List<RealtimeTransaction>>(
      (ref) => RealtimeTransactionNotifier());

// ============================================================
// ADMIN ACTIONS
// ============================================================

/// Acknowledge an alert
Future<void> acknowledgeAlert(WidgetRef ref, String alertId, {String? notes}) async {
  final api = ref.read(adminApiServiceProvider);
  await api.acknowledgeAlert(alertId, notes: notes);
  ref.invalidate(unresolvedAlertsProvider);
}

/// Submit EDD case for review
Future<void> submitEDDCaseForReview(WidgetRef ref, String caseId) async {
  final api = ref.read(adminApiServiceProvider);
  await api.submitEDDForReview(caseId);
  ref.invalidate(pendingEDDCasesProvider);
}

/// Test webhook endpoint
Future<WebhookTestResult> testWebhook(WidgetRef ref, String webhookId) async {
  final api = ref.read(adminApiServiceProvider);
  return await api.testWebhook(webhookId);
}

/// Delete webhook
Future<void> deleteWebhook(WidgetRef ref, String webhookId) async {
  final api = ref.read(adminApiServiceProvider);
  await api.deleteWebhook(webhookId);
  ref.invalidate(registeredWebhooksProvider);
}
