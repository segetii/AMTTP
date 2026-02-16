/// War Room Stub Pages
/// 
/// Placeholder pages for War Room features per Ground Truth v2.3
/// These will be implemented with full functionality in subsequent sprints
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';

// ═══════════════════════════════════════════════════════════════════════════
// DETECTION STUDIO PAGES (R3 Ops - Read Only)
// ═══════════════════════════════════════════════════════════════════════════

/// Graph Explorer Page - Memgraph based network visualization
class GraphExplorerPage extends ConsumerWidget {
  final String? initialTxId;
  
  const GraphExplorerPage({super.key, this.initialTxId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Graph Explorer',
      subtitle: 'Network visualization for wallet relationships',
      icon: Icons.hub,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.hub, size: 80, color: AppTheme.slate600),
            const SizedBox(height: 24),
            Text(
              'Graph Explorer',
              style: TextStyle(
                color: AppTheme.gray50,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            if (initialTxId != null)
              Text(
                'Investigating: $initialTxId',
                style: TextStyle(
                  color: AppTheme.indigo400,
                  fontSize: 14,
                  fontFamily: 'JetBrains Mono',
                ),
              ),
            const SizedBox(height: 16),
            Text(
              'Memgraph-powered network visualization coming soon.\nThis will show progressive hop expansion and time-travel.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.slate400,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: () => context.go('/war-room/detection-studio'),
              icon: const Icon(Icons.open_in_new),
              label: const Text('Use Next.js Detection Studio'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.indigo600,
                foregroundColor: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Velocity Heatmap Page
class VelocityHeatmapPage extends ConsumerWidget {
  const VelocityHeatmapPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Velocity Heatmap',
      subtitle: 'Temporal anomaly detection grid',
      icon: Icons.grid_on,
      child: _PlaceholderContent(
        icon: Icons.grid_on,
        title: 'Velocity Heatmap',
        description: 'Netflix-style hourly velocity grid showing z-score deviation vs 30-day baseline.',
      ),
    );
  }
}

/// Sankey Flow Page - Value conservation visualization
class SankeyFlowPage extends ConsumerWidget {
  const SankeyFlowPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Value Flow Auditor',
      subtitle: 'Sankey diagram for value conservation',
      icon: Icons.account_tree,
      child: _PlaceholderContent(
        icon: Icons.account_tree,
        title: 'Value Flow Sankey',
        description: 'Visualize fund flows from entry to exit. Width represents conserved value.',
      ),
    );
  }
}

/// ML Explainability Page
class MLExplainabilityPage extends ConsumerWidget {
  const MLExplainabilityPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'ML Explainability',
      subtitle: 'Human-readable model explanations',
      icon: Icons.psychology,
      child: _PlaceholderContent(
        icon: Icons.psychology,
        title: 'ML Explainability',
        description: 'Model stack: XGB → VAE → GNN → LGB\nTop feature contributors in plain language.',
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COMPLIANCE STUDIO PAGES (R4 - Can Enforce with Multisig)
// ═══════════════════════════════════════════════════════════════════════════

/// Policy Engine Page
class PolicyEnginePage extends ConsumerWidget {
  const PolicyEnginePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rbacState = ref.watch(rbacProvider);
    final canEdit = rbacState.capabilities.canEditPolicies;
    
    return _WarRoomPageScaffold(
      title: 'Policy Engine',
      subtitle: canEdit ? 'Configure institutional risk policies' : 'View policies (read-only)',
      icon: Icons.policy,
      child: _PlaceholderContent(
        icon: Icons.policy,
        title: 'Policy Engine',
        description: canEdit 
            ? 'Define velocity limits, jurisdiction rules, and threshold policies.'
            : 'You have read-only access to policies. Contact R4+ to make changes.',
      ),
    );
  }
}

/// Enforcement Actions Page
class EnforcementActionsPage extends ConsumerWidget {
  const EnforcementActionsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rbacState = ref.watch(rbacProvider);
    final canEnforce = rbacState.capabilities.canEnforceActions;
    
    return _WarRoomPageScaffold(
      title: 'Enforcement Actions',
      subtitle: canEnforce ? 'Execute policy enforcement' : 'View enforcement history',
      icon: Icons.security,
      child: _PlaceholderContent(
        icon: Icons.security,
        title: 'Enforcement Actions',
        description: canEnforce
            ? 'Execute scoped pauses, asset blocks, and mandatory escrow.\nHigh-impact actions require multisig approval.'
            : 'You need R4 (Compliance) role to execute enforcement actions.',
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// GOVERNANCE PAGES (R4+ Multisig)
// ═══════════════════════════════════════════════════════════════════════════

/// Multisig Queue Page
class MultisigQueuePage extends ConsumerWidget {
  const MultisigQueuePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Multisig Queue',
      subtitle: 'Pending approval requests',
      icon: Icons.how_to_vote,
      child: _PlaceholderContent(
        icon: Icons.how_to_vote,
        title: 'Multisig Queue',
        description: 'Review and sign pending enforcement actions.\nEach signature is bound to UI snapshot hash.',
      ),
    );
  }
}

/// Pending Approvals Page
class PendingApprovalsPage extends ConsumerWidget {
  const PendingApprovalsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Pending Approvals',
      subtitle: 'Actions awaiting your signature',
      icon: Icons.pending_actions,
      child: _PlaceholderContent(
        icon: Icons.pending_actions,
        title: 'Pending Approvals',
        description: 'What-You-Approve (WYA) summaries for each pending action.\nVerify UI integrity before signing.',
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// AUDIT & REPORTS
// ═══════════════════════════════════════════════════════════════════════════

/// UI Snapshots Page
class UISnapshotsPage extends ConsumerWidget {
  const UISnapshotsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'UI Snapshots',
      subtitle: 'Decision context evidence chain',
      icon: Icons.camera_alt,
      child: _PlaceholderContent(
        icon: Icons.camera_alt,
        title: 'UI Snapshots',
        description: 'Browse historical UI snapshots.\nEach snapshot is SHA-256 hashed and chain-linked.',
      ),
    );
  }
}

/// Reports Page
class ReportsPage extends ConsumerWidget {
  const ReportsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'Reports',
      subtitle: 'Generate compliance reports',
      icon: Icons.assessment,
      child: _PlaceholderContent(
        icon: Icons.assessment,
        title: 'Reports',
        description: 'Export PDF/JSON reports for regulators.\nIncludes full audit trail and evidence linking.',
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ADMINISTRATION (R5+)
// ═══════════════════════════════════════════════════════════════════════════

/// User Management Page
class UserManagementPage extends ConsumerWidget {
  const UserManagementPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'User Management',
      subtitle: 'Manage institutional users and roles',
      icon: Icons.people,
      child: _PlaceholderContent(
        icon: Icons.people,
        title: 'User Management',
        description: 'Assign roles (R1-R6) to users.\nManage institution access and permissions.',
      ),
    );
  }
}

/// System Settings Page
class SystemSettingsPage extends ConsumerWidget {
  const SystemSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return _WarRoomPageScaffold(
      title: 'System Settings',
      subtitle: 'Platform configuration',
      icon: Icons.settings,
      child: _PlaceholderContent(
        icon: Icons.settings,
        title: 'System Settings',
        description: 'Configure integrations, API keys, and system preferences.',
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SHARED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════

class _WarRoomPageScaffold extends StatelessWidget {
  final String title;
  final String subtitle;
  final IconData icon;
  final Widget child;
  final List<Widget>? actions;

  const _WarRoomPageScaffold({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: AppTheme.slate800)),
          ),
          child: Row(
            children: [
              Icon(icon, color: AppTheme.indigo400, size: 28),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: AppTheme.gray50,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      subtitle,
                      style: TextStyle(
                        color: AppTheme.slate400,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
              if (actions != null) ...actions!,
            ],
          ),
        ),
        
        // Content
        Expanded(child: child),
      ],
    );
  }
}

class _PlaceholderContent extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _PlaceholderContent({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Container(
        constraints: const BoxConstraints(maxWidth: 500),
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 64, color: AppTheme.slate600),
            const SizedBox(height: 24),
            Text(
              title,
              style: TextStyle(
                color: AppTheme.gray50,
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              description,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.slate400,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: AppTheme.amber500.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.amber500.withOpacity(0.3)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.construction, color: AppTheme.amber400, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Coming in Sprint 2',
                    style: TextStyle(
                      color: AppTheme.amber400,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
