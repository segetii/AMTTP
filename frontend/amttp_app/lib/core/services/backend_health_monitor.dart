/// Backend Health Monitor — Flutter
///
/// Provides real-time awareness of backend service availability.
/// Instead of silently returning mock data when the backend is down,
/// this service exposes the health state so the UI can show clear
/// "Backend Unavailable" banners and degrade gracefully.
///
/// Monitored services:
///   - Orchestrator (port 8007) — compliance evaluation, risk routing
///   - Integrity Service (port 8008) — UI snapshot verification
///   - Risk Engine (port 8000) — DQN/ML scoring
///   - Explainability (port 8009) — SHAP / factor breakdown
library;

import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

enum ServiceStatus { online, degraded, offline, unknown }

class ServiceHealth {
  final String name;
  final String endpoint;
  final ServiceStatus status;
  final int? latencyMs;
  final String? version;
  final DateTime checkedAt;
  final String? error;

  const ServiceHealth({
    required this.name,
    required this.endpoint,
    required this.status,
    this.latencyMs,
    this.version,
    required this.checkedAt,
    this.error,
  });

  ServiceHealth copyWith({ServiceStatus? status, String? error}) {
    return ServiceHealth(
      name: name,
      endpoint: endpoint,
      status: status ?? this.status,
      latencyMs: latencyMs,
      version: version,
      checkedAt: DateTime.now(),
      error: error ?? this.error,
    );
  }
}

class BackendHealthState {
  final Map<String, ServiceHealth> services;
  final bool isChecking;
  final DateTime? lastFullCheck;

  const BackendHealthState({
    this.services = const {},
    this.isChecking = false,
    this.lastFullCheck,
  });

  /// True if ALL monitored services are online
  bool get isFullyHealthy =>
      services.isNotEmpty &&
      services.values.every((s) => s.status == ServiceStatus.online);

  /// True if ANY service is offline
  bool get hasOutage =>
      services.values.any((s) => s.status == ServiceStatus.offline);

  /// True if some services are degraded but none offline
  bool get isDegraded =>
      !hasOutage &&
      services.values.any((s) => s.status == ServiceStatus.degraded);

  /// Get a human-readable summary
  String get summary {
    if (isChecking && services.isEmpty) return 'Checking backend services...';
    if (isFullyHealthy) return 'All services operational';
    final offline = services.values
        .where((s) => s.status == ServiceStatus.offline)
        .map((s) => s.name)
        .toList();
    if (offline.isNotEmpty) return 'Offline: ${offline.join(", ")}';
    final degraded = services.values
        .where((s) => s.status == ServiceStatus.degraded)
        .map((s) => s.name)
        .toList();
    if (degraded.isNotEmpty) return 'Degraded: ${degraded.join(", ")}';
    return 'Unknown state';
  }

  BackendHealthState copyWith({
    Map<String, ServiceHealth>? services,
    bool? isChecking,
    DateTime? lastFullCheck,
  }) {
    return BackendHealthState(
      services: services ?? this.services,
      isChecking: isChecking ?? this.isChecking,
      lastFullCheck: lastFullCheck ?? this.lastFullCheck,
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HEALTH CHECK NOTIFIER
// ═══════════════════════════════════════════════════════════════════════════════

class BackendHealthNotifier extends StateNotifier<BackendHealthState> {
  Timer? _pollingTimer;
  final Duration _pollInterval;

  /// Service definitions — in production these resolve through nginx
  final List<_ServiceDef> _serviceDefs;

  BackendHealthNotifier({
    Duration pollInterval = const Duration(seconds: 30),
  })  : _pollInterval = pollInterval,
        _serviceDefs = _buildServiceDefs(),
        super(const BackendHealthState()) {
    // Initial check
    checkAll();
    // Start polling
    _pollingTimer = Timer.periodic(_pollInterval, (_) => checkAll());
  }

  static List<_ServiceDef> _buildServiceDefs() {
    final base = _resolveBase();
    return [
      _ServiceDef('Orchestrator', '$base/health', 'orchestrator'),
      _ServiceDef('Integrity', '$base/integrity/health', 'integrity'),
      _ServiceDef('Risk Engine', '$base/risk/health', 'risk_engine'),
      _ServiceDef('Explainability', '$base/explain/health', 'explainability'),
    ];
  }

  static String _resolveBase() {
    if (kIsWeb) {
      final uri = Uri.base;
      // Dev mode — services are on separate ports
      if (uri.port == 3010 || uri.port == 3003) {
        return 'http://localhost:8007';
      }
      // Production — everything behind nginx on same origin
      return '${uri.scheme}://${uri.host}${uri.port != 80 && uri.port != 443 ? ":${uri.port}" : ""}/api';
    }
    return 'http://localhost:8007';
  }

  Future<void> checkAll() async {
    state = state.copyWith(isChecking: true);

    final results = <String, ServiceHealth>{};
    for (final def in _serviceDefs) {
      results[def.key] = await _checkService(def);
    }

    state = BackendHealthState(
      services: results,
      isChecking: false,
      lastFullCheck: DateTime.now(),
    );
  }

  Future<ServiceHealth> _checkService(_ServiceDef def) async {
    final sw = Stopwatch()..start();
    try {
      final response = await http
          .get(Uri.parse(def.endpoint))
          .timeout(const Duration(seconds: 5));
      sw.stop();

      if (response.statusCode == 200) {
        String? version;
        try {
          final body = jsonDecode(response.body);
          version = body['version']?.toString();
        } catch (_) {}

        return ServiceHealth(
          name: def.name,
          endpoint: def.endpoint,
          status: sw.elapsedMilliseconds > 2000
              ? ServiceStatus.degraded
              : ServiceStatus.online,
          latencyMs: sw.elapsedMilliseconds,
          version: version,
          checkedAt: DateTime.now(),
        );
      }

      return ServiceHealth(
        name: def.name,
        endpoint: def.endpoint,
        status: ServiceStatus.degraded,
        latencyMs: sw.elapsedMilliseconds,
        checkedAt: DateTime.now(),
        error: 'HTTP ${response.statusCode}',
      );
    } catch (e) {
      sw.stop();
      return ServiceHealth(
        name: def.name,
        endpoint: def.endpoint,
        status: ServiceStatus.offline,
        latencyMs: sw.elapsedMilliseconds,
        checkedAt: DateTime.now(),
        error: e.toString(),
      );
    }
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }
}

class _ServiceDef {
  final String name;
  final String endpoint;
  final String key;
  const _ServiceDef(this.name, this.endpoint, this.key);
}

// ═══════════════════════════════════════════════════════════════════════════════
// PROVIDERS
// ═══════════════════════════════════════════════════════════════════════════════

final backendHealthProvider =
    StateNotifierProvider<BackendHealthNotifier, BackendHealthState>(
  (ref) => BackendHealthNotifier(),
);

/// Quick check: is any service down?
final hasBackendOutageProvider = Provider<bool>((ref) {
  return ref.watch(backendHealthProvider).hasOutage;
});

/// Human-readable backend status summary
final backendStatusSummaryProvider = Provider<String>((ref) {
  return ref.watch(backendHealthProvider).summary;
});
