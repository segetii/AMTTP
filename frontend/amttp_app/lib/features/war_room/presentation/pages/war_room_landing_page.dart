/// War Room Landing Page - Active Investigations
/// 
/// Per Ground Truth v2.3:
/// - KPI Strip (Passive, Non-Interactive) - handled by shell
/// - Flagged Queue (Primary Action Surface)
/// - Right Context Panel (Read-only policy snapshot)
/// 
/// "Fast triage, No charts yet, Forces click-through for depth"

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';
import '../../../../core/services/unified_data_service.dart';

class WarRoomLandingPage extends ConsumerStatefulWidget {
  const WarRoomLandingPage({super.key});

  @override
  ConsumerState<WarRoomLandingPage> createState() => _WarRoomLandingPageState();
}

class _WarRoomLandingPageState extends ConsumerState<WarRoomLandingPage> {
  final _dataService = UnifiedDataService();
  List<FlaggedTransaction> _flaggedItems = [];
  DashboardStats _stats = DashboardStats.empty();
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    try {
      final results = await Future.wait([
        _dataService.getFlaggedQueue(),
        _dataService.getDashboardStats(),
      ]);
      setState(() {
        _flaggedItems = results[0] as List<FlaggedTransaction>;
        _stats = results[1] as DashboardStats;
      });
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final screenWidth = MediaQuery.of(context).size.width;
    final isWideScreen = screenWidth > 1200;

    return Row(
      children: [
        // Main content - Flagged Queue
        Expanded(
          flex: 3,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          'Active Investigations',
                          style: TextStyle(
                            color: AppTheme.gray50,
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        if (_isLoading)
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation(AppTheme.cyan500),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${_stats.flaggedCount} flagged transactions • ${_stats.totalTransactions.toString()} total',
                      style: TextStyle(
                        color: AppTheme.slate400,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              ),
              
              // Flagged Queue Table
              Expanded(
                child: _FlaggedQueueTable(flaggedItems: _flaggedItems, isLoading: _isLoading),
              ),
            ],
          ),
        ),
        
        // Right Context Panel (on wide screens)
        if (isWideScreen)
          Container(
            width: 320,
            decoration: BoxDecoration(
              color: AppTheme.slate900,
              border: Border(left: BorderSide(color: AppTheme.slate800)),
            ),
            child: _ContextPanel(rbacState: rbacState, stats: _stats),
          ),
      ],
    );
  }
}

class _FlaggedQueueTable extends StatelessWidget {
  final List<FlaggedTransaction> flaggedItems;
  final bool isLoading;

  const _FlaggedQueueTable({required this.flaggedItems, required this.isLoading});

  @override
  Widget build(BuildContext context) {
    if (isLoading && flaggedItems.isEmpty) {
      return Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation(AppTheme.cyan500),
        ),
      );
    }

    if (flaggedItems.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 64, color: AppTheme.green400),
            const SizedBox(height: 16),
            Text(
              'No flagged transactions',
              style: TextStyle(color: AppTheme.slate400, fontSize: 16),
            ),
          ],
        ),
      );
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      decoration: BoxDecoration(
        color: AppTheme.slate800,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.slate700),
      ),
      child: Column(
        children: [
          // Table Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppTheme.slate900,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            child: Row(
              children: [
                _HeaderCell('TxID', flex: 2),
                _HeaderCell('Risk', flex: 1),
                _HeaderCell('Reason', flex: 2),
                _HeaderCell('Value', flex: 1),
                _HeaderCell('Status', flex: 1),
                const SizedBox(width: 48), // Action column
              ],
            ),
          ),
          
          // Table Rows
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.all(8),
              itemCount: flaggedItems.length,
              separatorBuilder: (_, __) => Divider(
                color: AppTheme.slate700,
                height: 1,
              ),
              itemBuilder: (context, index) {
                final item = flaggedItems[index];
                return _FlaggedRow(
                  item: item,
                  onTap: () {
                    context.go('/war-room/graph?tx=${item.hash}');
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderCell extends StatelessWidget {
  final String label;
  final int flex;

  const _HeaderCell(this.label, {this.flex = 1});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      flex: flex,
      child: Text(
        label,
        style: TextStyle(
          color: AppTheme.slate400,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

class _FlaggedRow extends StatelessWidget {
  final FlaggedTransaction item;
  final VoidCallback onTap;

  const _FlaggedRow({required this.item, required this.onTap});

  String _getRiskLevel(double score) {
    if (score >= 70) return 'High';
    if (score >= 40) return 'Medium';
    return 'Low';
  }

  @override
  Widget build(BuildContext context) {
    final riskLevel = _getRiskLevel(item.riskScore);
    
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        hoverColor: AppTheme.slate700.withOpacity(0.5),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 12),
          child: Row(
            children: [
              // TxID
              Expanded(
                flex: 2,
                child: Text(
                  item.hash.length > 16 
                      ? '${item.hash.substring(0, 8)}...${item.hash.substring(item.hash.length - 6)}'
                      : item.hash,
                  style: TextStyle(
                    color: AppTheme.gray50,
                    fontSize: 13,
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ),
              // Risk Class
              Expanded(
                flex: 1,
                child: _RiskBadge(riskLevel),
              ),
              // Reason
              Expanded(
                flex: 2,
                child: Text(
                  item.flags.isNotEmpty ? item.flags.first : 'Flagged',
                  style: TextStyle(
                    color: AppTheme.slate300,
                    fontSize: 13,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              // Value
              Expanded(
                flex: 1,
                child: Text(
                  '${item.value.toStringAsFixed(2)} ETH',
                  style: TextStyle(
                    color: AppTheme.gray50,
                    fontSize: 13,
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ),
              // Status
              Expanded(
                flex: 1,
                child: _StatusBadge(item.status),
              ),
              // Action
              IconButton(
                icon: Icon(Icons.arrow_forward, color: AppTheme.indigo400, size: 18),
                onPressed: onTap,
                tooltip: 'Investigate',
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final String status;

  const _StatusBadge(this.status);

  @override
  Widget build(BuildContext context) {
    Color bgColor;
    Color textColor;
    
    switch (status.toLowerCase()) {
      case 'escalated':
        bgColor = AppTheme.red500.withOpacity(0.2);
        textColor = AppTheme.red400;
        break;
      case 'reviewing':
        bgColor = AppTheme.amber500.withOpacity(0.2);
        textColor = AppTheme.amber400;
        break;
      case 'resolved':
        bgColor = AppTheme.green500.withOpacity(0.2);
        textColor = AppTheme.green400;
        break;
      default: // pending
        bgColor = AppTheme.slate600.withOpacity(0.3);
        textColor = AppTheme.slate400;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        status.substring(0, 1).toUpperCase() + status.substring(1),
        style: TextStyle(
          color: textColor,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _RiskBadge extends StatelessWidget {
  final String riskClass;

  const _RiskBadge(this.riskClass);

  @override
  Widget build(BuildContext context) {
    Color bgColor;
    Color textColor;
    
    switch (riskClass.toLowerCase()) {
      case 'high':
        bgColor = AppTheme.red500.withOpacity(0.2);
        textColor = AppTheme.red400;
        break;
      case 'medium':
        bgColor = AppTheme.amber500.withOpacity(0.2);
        textColor = AppTheme.amber400;
        break;
      default:
        bgColor = AppTheme.green500.withOpacity(0.2);
        textColor = AppTheme.green400;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        riskClass,
        style: TextStyle(
          color: textColor,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _ContextPanel extends StatelessWidget {
  final RBACState rbacState;
  final DashboardStats stats;

  const _ContextPanel({required this.rbacState, required this.stats});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Panel Title
          Text(
            'CONTEXT',
            style: TextStyle(
              color: AppTheme.slate500,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 16),
          
          // Live Stats from Memgraph
          _ContextCard(
            title: 'Live Statistics',
            icon: Icons.analytics,
            children: [
              _ContextRow('Transactions', stats.totalTransactions.toString()),
              _ContextRow('Volume', '${stats.totalVolume.toStringAsFixed(0)} ETH'),
              _ContextRow('Flagged', stats.flaggedCount.toString(), valueColor: stats.flaggedCount > 0 ? AppTheme.amber400 : AppTheme.green400),
              _ContextRow('Compliance', '${stats.complianceRate.toStringAsFixed(1)}%', valueColor: stats.complianceRate > 95 ? AppTheme.green400 : AppTheme.amber400),
            ],
          ),
          const SizedBox(height: 12),
          
          // Active Policy
          _ContextCard(
            title: 'Active Policy',
            icon: Icons.policy,
            children: [
              _ContextRow('Version', 'v3.2.1'),
              _ContextRow('Updated', '2 hours ago'),
              _ContextRow('Status', 'Active', valueColor: AppTheme.green400),
            ],
          ),
          const SizedBox(height: 12),
          
          // Model Version
          _ContextCard(
            title: 'ML Model',
            icon: Icons.psychology,
            children: [
              _ContextRow('Stack', 'XGB→VAE→GNN'),
              _ContextRow('Version', 'v2.1.0'),
              _ContextRow('Avg Risk', stats.averageRiskScore.toStringAsFixed(1)),
            ],
          ),
          
          const Spacer(),
          
          // Quick Actions
          Text(
            'QUICK ACTIONS',
            style: TextStyle(
              color: AppTheme.slate500,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 12),
          
          _QuickActionButton(
            label: 'View Detection Studio',
            icon: Icons.hub,
            onTap: () => context.go('/war-room/detection-studio'),
          ),
          const SizedBox(height: 8),
          
          if (rbacState.capabilities.canEditPolicies)
            _QuickActionButton(
              label: 'Edit Policies',
              icon: Icons.edit,
              onTap: () => context.go('/war-room/policies'),
            ),
        ],
      ),
    );
  }
}

class _ContextCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color? iconColor;
  final List<Widget> children;

  const _ContextCard({
    required this.title,
    required this.icon,
    this.iconColor,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.slate800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.slate700),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: iconColor ?? AppTheme.slate400, size: 16),
              const SizedBox(width: 8),
              Text(
                title,
                style: TextStyle(
                  color: AppTheme.gray50,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ...children,
        ],
      ),
    );
  }
}

class _ContextRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? valueColor;

  const _ContextRow(this.label, this.value, {this.valueColor});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              color: AppTheme.slate400,
              fontSize: 12,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: valueColor ?? AppTheme.slate300,
              fontSize: 12,
              fontFamily: value.contains('.') || value.contains('v') 
                  ? 'JetBrains Mono' 
                  : null,
            ),
          ),
        ],
      ),
    );
  }
}

class _QuickActionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  const _QuickActionButton({
    required this.label,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppTheme.slate800,
      borderRadius: BorderRadius.circular(8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: AppTheme.slate700),
          ),
          child: Row(
            children: [
              Icon(icon, color: AppTheme.indigo400, size: 18),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    color: AppTheme.gray50,
                    fontSize: 13,
                  ),
                ),
              ),
              Icon(Icons.chevron_right, color: AppTheme.slate400, size: 18),
            ],
          ),
        ),
      ),
    );
  }
}
