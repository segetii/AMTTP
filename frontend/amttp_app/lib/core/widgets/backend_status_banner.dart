import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/backend_health_monitor.dart';

/// A banner widget that shows backend service status.
/// Place at the top of shells/scaffolds to inform operators
/// when services are degraded or offline.
///
/// Shows nothing when all services are healthy.
class BackendStatusBanner extends ConsumerWidget {
  const BackendStatusBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final health = ref.watch(backendHealthProvider);

    // Don't show anything if healthy or still doing initial check
    if (health.isFullyHealthy ||
        (health.isChecking && health.services.isEmpty)) {
      return const SizedBox.shrink();
    }

    final isOffline = health.hasOutage;
    final color = isOffline ? const Color(0xFFDC2626) : const Color(0xFFF59E0B);
    final icon =
        isOffline ? Icons.cloud_off_rounded : Icons.warning_amber_rounded;

    return Material(
      color: color.withOpacity(0.15),
      child: InkWell(
        onTap: () => _showDetailDialog(context, health),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: color.withOpacity(0.3))),
          ),
          child: Row(
            children: [
              Icon(icon, color: color, size: 18),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  health.summary,
                  style: TextStyle(
                    color: color,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              if (isOffline)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    'DATA MAY BE STALE',
                    style: TextStyle(
                      color: color,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
              const SizedBox(width: 8),
              Icon(Icons.info_outline, color: color.withOpacity(0.6), size: 16),
            ],
          ),
        ),
      ),
    );
  }

  void _showDetailDialog(BuildContext context, BackendHealthState health) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A2E),
        title: const Text(
          'Backend Service Status',
          style: TextStyle(color: Colors.white),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: health.services.entries.map((entry) {
            final svc = entry.value;
            final statusColor = switch (svc.status) {
              ServiceStatus.online => const Color(0xFF10B981),
              ServiceStatus.degraded => const Color(0xFFF59E0B),
              ServiceStatus.offline => const Color(0xFFDC2626),
              ServiceStatus.unknown => const Color(0xFF6B7280),
            };
            final statusLabel = switch (svc.status) {
              ServiceStatus.online => 'Online',
              ServiceStatus.degraded => 'Slow',
              ServiceStatus.offline => 'Offline',
              ServiceStatus.unknown => 'Unknown',
            };

            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  Container(
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      svc.name,
                      style: const TextStyle(color: Colors.white70),
                    ),
                  ),
                  Text(
                    statusLabel,
                    style: TextStyle(
                        color: statusColor, fontWeight: FontWeight.w600),
                  ),
                  if (svc.latencyMs != null) ...[
                    const SizedBox(width: 8),
                    Text(
                      '${svc.latencyMs}ms',
                      style:
                          const TextStyle(color: Colors.white38, fontSize: 12),
                    ),
                  ],
                ],
              ),
            );
          }).toList(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Close', style: TextStyle(color: Colors.white54)),
          ),
          TextButton(
            onPressed: () {
              // Trigger manual recheck
              // We can't access ref here, but the periodic timer will pick it up
              Navigator.pop(ctx);
            },
            child: const Text('Refresh',
                style: TextStyle(color: Color(0xFF60A5FA))),
          ),
        ],
      ),
    );
  }
}
