/// War Room Compliance & Governance Pages
/// 
/// Per Ground Truth v2.3:
/// - Policy Engine: Rule configuration (R4+)
/// - Enforcement Actions: Freeze/unfreeze controls (R4 with multisig)
/// - Multisig Queue: Pending multisig approvals
/// - Pending Approvals: Transfer approval queue

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';
import '../../../../core/rbac/roles.dart';
import '../../../../core/services/action_service.dart';

// ═══════════════════════════════════════════════════════════════════════════
// POLICY ENGINE PAGE
// ═══════════════════════════════════════════════════════════════════════════

class PolicyEnginePage extends ConsumerStatefulWidget {
  const PolicyEnginePage({super.key});

  @override
  ConsumerState<PolicyEnginePage> createState() => _PolicyEnginePageState();
}

class _PolicyEnginePageState extends ConsumerState<PolicyEnginePage> {
  final _actionService = ActionService();
  
  final List<Map<String, dynamic>> _policies = [
    {'id': '1', 'name': 'High Value Transfer', 'description': 'Requires approval for transfers > 10 ETH', 'status': PolicyStatus.active, 'threshold': '10 ETH', 'action': 'Require Approval'},
    {'id': '2', 'name': 'Velocity Limit', 'description': 'Flag accounts exceeding 50 TX/day', 'status': PolicyStatus.active, 'threshold': '50 TX/day', 'action': 'Auto-Flag'},
    {'id': '3', 'name': 'PEP Screening', 'description': 'Enhanced monitoring for PEP accounts', 'status': PolicyStatus.active, 'threshold': 'PEP Match', 'action': 'Enhanced Monitoring'},
    {'id': '4', 'name': 'Sanctions Check', 'description': 'Block transactions with sanctioned entities', 'status': PolicyStatus.active, 'threshold': 'OFAC Match', 'action': 'Block + Alert'},
    {'id': '5', 'name': 'New Address Risk', 'description': 'Flag transfers to addresses < 7 days old', 'status': PolicyStatus.inactive, 'threshold': '< 7 days', 'action': 'Flag for Review'},
  ];

  void _showNewRuleDialog(BuildContext context, bool isDark) {
    final nameController = TextEditingController();
    final descController = TextEditingController();
    final thresholdController = TextEditingController();
    String selectedAction = 'Auto-Flag';

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
          title: Row(
            children: [
              Icon(Icons.policy, color: AppTheme.purple500),
              const SizedBox(width: 8),
              Text('Create New Rule', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
            ],
          ),
          content: SizedBox(
            width: 450,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Rule Name',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: descController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  maxLines: 2,
                  decoration: InputDecoration(
                    labelText: 'Description',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: thresholdController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Threshold (e.g., "10 ETH", "100 TX/day")',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: selectedAction,
                  dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Action',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                  items: ['Auto-Flag', 'Require Approval', 'Block + Alert', 'Enhanced Monitoring', 'Flag for Review']
                      .map((a) => DropdownMenuItem(value: a, child: Text(a)))
                      .toList(),
                  onChanged: (v) => setDialogState(() => selectedAction = v!),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text('Cancel', style: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate600)),
            ),
            ElevatedButton(
              onPressed: () async {
                if (nameController.text.isEmpty || thresholdController.text.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Please fill required fields'), backgroundColor: Colors.red),
                  );
                  return;
                }
                Navigator.pop(ctx);
                final result = await _actionService.createPolicy(
                  name: nameController.text,
                  description: descController.text,
                  threshold: thresholdController.text,
                  action: selectedAction,
                );
                if (mounted) {
                  showActionResult(context, result);
                  if (result.success) {
                    setState(() {
                      _policies.add({
                        'id': DateTime.now().millisecondsSinceEpoch.toString(),
                        'name': nameController.text,
                        'description': descController.text,
                        'status': PolicyStatus.draft,
                        'threshold': thresholdController.text,
                        'action': selectedAction,
                      });
                    });
                  }
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: AppTheme.purple600),
              child: const Text('Create Rule', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _togglePolicyStatus(int index) async {
    final policy = _policies[index];
    final currentStatus = policy['status'] as PolicyStatus;
    final activate = currentStatus != PolicyStatus.active;
    
    final result = await _actionService.togglePolicyStatus(
      policyId: policy['id'],
      activate: activate,
    );
    
    if (mounted) {
      showActionResult(context, result);
      if (result.success) {
        setState(() {
          _policies[index]['status'] = activate ? PolicyStatus.active : PolicyStatus.inactive;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final rbac = ref.watch(rbacProvider);
    final canEdit = rbac.role.isAtLeast(Role.r4InstitutionCompliance);

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.policy, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Policy Engine',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Configure compliance rules and thresholds',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
                if (canEdit)
                  ElevatedButton.icon(
                    onPressed: () => _showNewRuleDialog(context, isDark),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('New Rule'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.purple600,
                      foregroundColor: Colors.white,
                    ),
                  ),
              ],
            ),
          ),
          
          // Policy list
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _policies.length,
              itemBuilder: (context, index) {
                final p = _policies[index];
                return _PolicyCard(
                  name: p['name'],
                  description: p['description'],
                  status: p['status'],
                  threshold: p['threshold'],
                  action: p['action'],
                  isDark: isDark,
                  canEdit: canEdit,
                  onToggle: () => _togglePolicyStatus(index),
                  onEdit: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('Edit policy: ${p['name']} (demo mode)'),
                        backgroundColor: Colors.orange,
                      ),
                    );
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

enum PolicyStatus { active, inactive, draft }

class _PolicyCard extends StatelessWidget {
  final String name;
  final String description;
  final PolicyStatus status;
  final String threshold;
  final String action;
  final bool isDark;
  final bool canEdit;
  final VoidCallback? onToggle;
  final VoidCallback? onEdit;
  
  const _PolicyCard({
    required this.name,
    required this.description,
    required this.status,
    required this.threshold,
    required this.action,
    required this.isDark,
    required this.canEdit,
    this.onToggle,
    this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  name,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
              ),
              _StatusBadge(status: status),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            description,
            style: TextStyle(
              fontSize: 13,
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              _PolicyChip(label: 'Threshold: $threshold', isDark: isDark),
              const SizedBox(width: 8),
              _PolicyChip(label: 'Action: $action', isDark: isDark),
              const Spacer(),
              if (canEdit) ...[
                IconButton(
                  onPressed: onEdit,
                  icon: const Icon(Icons.edit_outlined, size: 20),
                  color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  tooltip: 'Edit Policy',
                ),
                IconButton(
                  onPressed: onToggle,
                  icon: Icon(
                    status == PolicyStatus.active
                        ? Icons.pause_circle_outline
                        : Icons.play_circle_outline,
                    size: 20,
                  ),
                  color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  tooltip: status == PolicyStatus.active ? 'Deactivate' : 'Activate',
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  final PolicyStatus status;
  
  const _StatusBadge({required this.status});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;
    
    switch (status) {
      case PolicyStatus.active:
        color = AppTheme.green500;
        label = 'Active';
        break;
      case PolicyStatus.inactive:
        color = AppTheme.slate400;
        label = 'Inactive';
        break;
      case PolicyStatus.draft:
        color = AppTheme.amber500;
        label = 'Draft';
        break;
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: color,
        ),
      ),
    );
  }
}

class _PolicyChip extends StatelessWidget {
  final String label;
  final bool isDark;
  
  const _PolicyChip({required this.label, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate700 : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          color: isDark ? AppTheme.slate300 : AppTheme.slate600,
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ENFORCEMENT ACTIONS PAGE
// ═══════════════════════════════════════════════════════════════════════════

class EnforcementActionsPage extends ConsumerStatefulWidget {
  const EnforcementActionsPage({super.key});

  @override
  ConsumerState<EnforcementActionsPage> createState() => _EnforcementActionsPageState();
}

class _EnforcementActionsPageState extends ConsumerState<EnforcementActionsPage> {
  final _actionService = ActionService();
  
  final List<Map<String, dynamic>> _actions = [
    {'id': 'act-001', 'type': EnforcementType.freeze, 'target': '0x742d...1ab12', 'reason': 'Suspicious activity pattern detected', 'status': 'Pending Multisig (2/3)', 'initiatedBy': 'compliance@institution.com', 'timestamp': '2024-01-15 14:32 UTC'},
    {'id': 'act-002', 'type': EnforcementType.freeze, 'target': '0x8f3C...A063', 'reason': 'OFAC sanctions match', 'status': 'Executed', 'initiatedBy': 'system@amttp.io', 'timestamp': '2024-01-14 09:15 UTC'},
    {'id': 'act-003', 'type': EnforcementType.unfreeze, 'target': '0x3f5C...0bE', 'reason': 'False positive - verified legitimate', 'status': 'Pending Multisig (1/3)', 'initiatedBy': 'admin@institution.com', 'timestamp': '2024-01-13 16:45 UTC'},
  ];

  void _showNewActionDialog(BuildContext context, bool isDark) {
    final targetController = TextEditingController();
    final reasonController = TextEditingController();
    EnforcementType actionType = EnforcementType.freeze;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
          title: Row(
            children: [
              Icon(Icons.gavel, color: AppTheme.red500),
              const SizedBox(width: 8),
              Text('New Enforcement Action', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
            ],
          ),
          content: SizedBox(
            width: 400,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<EnforcementType>(
                  value: actionType,
                  dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Action Type',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                  items: const [
                    DropdownMenuItem(value: EnforcementType.freeze, child: Text('Freeze')),
                    DropdownMenuItem(value: EnforcementType.unfreeze, child: Text('Unfreeze')),
                  ],
                  onChanged: (v) => setDialogState(() => actionType = v!),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: targetController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Target Address',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                    hintText: '0x...',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: reasonController,
                  maxLines: 2,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Reason',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: Text('Cancel', style: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate600)),
            ),
            ElevatedButton(
              onPressed: () async {
                if (targetController.text.isEmpty || reasonController.text.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Please fill all fields'), backgroundColor: Colors.red),
                  );
                  return;
                }
                Navigator.pop(ctx);
                final result = await _actionService.createFreezeAction(
                  targetAddress: targetController.text,
                  reason: reasonController.text,
                  initiatorAddress: '0xCurrentUser',
                );
                if (mounted) {
                  showActionResult(context, result);
                  if (result.success) {
                    setState(() {
                      _actions.insert(0, {
                        'id': 'act-${DateTime.now().millisecondsSinceEpoch}',
                        'type': actionType,
                        'target': targetController.text,
                        'reason': reasonController.text,
                        'status': 'Pending Multisig (1/3)',
                        'initiatedBy': 'you@institution.com',
                        'timestamp': DateTime.now().toString().substring(0, 19),
                      });
                    });
                  }
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: AppTheme.red600),
              child: const Text('Create Action', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleApprove(int index) async {
    final action = _actions[index];
    final result = await _actionService.approveEnforcement(
      actionId: action['id'],
      signerAddress: '0xCurrentUser',
    );
    
    if (mounted) {
      showActionResult(context, result);
      if (result.success) {
        setState(() {
          // Update status to show more signatures collected
          final currentStatus = action['status'] as String;
          if (currentStatus.contains('2/3')) {
            _actions[index]['status'] = 'Executed';
          } else if (currentStatus.contains('1/3')) {
            _actions[index]['status'] = 'Pending Multisig (2/3)';
          }
        });
      }
    }
  }

  Future<void> _handleReject(int index, bool isDark) async {
    final action = _actions[index];
    final reasonController = TextEditingController();
    
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
        title: Text('Reject Action', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Target: ${action['target']}', style: TextStyle(color: isDark ? AppTheme.slate300 : AppTheme.slate600)),
            const SizedBox(height: 12),
            TextField(
              controller: reasonController,
              maxLines: 2,
              style: TextStyle(color: isDark ? Colors.white : Colors.black),
              decoration: InputDecoration(
                labelText: 'Rejection Reason',
                labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                border: const OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.red500),
            child: const Text('Reject', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final result = await _actionService.rejectEnforcement(
        actionId: action['id'],
        signerAddress: '0xCurrentUser',
        reason: reasonController.text.isNotEmpty ? reasonController.text : 'Rejected by signer',
      );
      
      if (mounted) {
        showActionResult(context, result);
        if (result.success) {
          setState(() {
            _actions[index]['status'] = 'Rejected';
          });
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final rbac = ref.watch(rbacProvider);
    final canEnforce = rbac.role.isAtLeast(Role.r4InstitutionCompliance);

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.gavel, color: AppTheme.red500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Enforcement Actions',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Freeze/unfreeze accounts and assets',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
                if (canEnforce)
                  ElevatedButton.icon(
                    onPressed: () => _showNewActionDialog(context, isDark),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('New Action'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.red600,
                      foregroundColor: Colors.white,
                    ),
                  ),
              ],
            ),
          ),
          
          // Warning banner
          if (!canEnforce)
            Container(
              padding: const EdgeInsets.all(12),
              color: AppTheme.amber500.withValues(alpha: 0.1),
              child: Row(
                children: [
                  Icon(Icons.info_outline, color: AppTheme.amber600, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'You have read-only access. Contact a Compliance Officer (R4+) to request enforcement actions.',
                      style: TextStyle(
                        fontSize: 13,
                        color: AppTheme.amber700,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          
          // Actions list
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _actions.length,
              itemBuilder: (context, index) {
                final a = _actions[index];
                return _EnforcementCard(
                  type: a['type'],
                  target: a['target'],
                  reason: a['reason'],
                  status: a['status'],
                  initiatedBy: a['initiatedBy'],
                  timestamp: a['timestamp'],
                  isDark: isDark,
                  canEnforce: canEnforce,
                  onApprove: () => _handleApprove(index),
                  onReject: () => _handleReject(index, isDark),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

enum EnforcementType { freeze, unfreeze }

class _EnforcementCard extends StatelessWidget {
  final EnforcementType type;
  final String target;
  final String reason;
  final String status;
  final String initiatedBy;
  final String timestamp;
  final bool isDark;
  final bool canEnforce;
  final VoidCallback? onApprove;
  final VoidCallback? onReject;
  
  const _EnforcementCard({
    required this.type,
    required this.target,
    required this.reason,
    required this.status,
    required this.initiatedBy,
    required this.timestamp,
    required this.isDark,
    required this.canEnforce,
    this.onApprove,
    this.onReject,
  });

  @override
  Widget build(BuildContext context) {
    final isFreeze = type == EnforcementType.freeze;
    final isPending = status.contains('Pending');
    
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isPending
              ? AppTheme.amber500.withValues(alpha: 0.5)
              : (isDark ? AppTheme.slate700 : Colors.grey.shade200),
          width: isPending ? 2 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: (isFreeze ? AppTheme.red500 : AppTheme.green500).withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(
                  isFreeze ? Icons.lock : Icons.lock_open,
                  color: isFreeze ? AppTheme.red500 : AppTheme.green500,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${isFreeze ? "FREEZE" : "UNFREEZE"}: $target',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                        fontFamily: 'monospace',
                        color: isDark ? Colors.white : AppTheme.slate800,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      status,
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: isPending ? AppTheme.amber500 : (status.contains('Rejected') ? AppTheme.red500 : AppTheme.green500),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            reason,
            style: TextStyle(
              fontSize: 13,
              color: isDark ? AppTheme.slate300 : AppTheme.slate600,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Icon(
                Icons.person_outline,
                size: 14,
                color: isDark ? AppTheme.slate500 : AppTheme.slate400,
              ),
              const SizedBox(width: 4),
              Text(
                initiatedBy,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                ),
              ),
              const SizedBox(width: 16),
              Icon(
                Icons.access_time,
                size: 14,
                color: isDark ? AppTheme.slate500 : AppTheme.slate400,
              ),
              const SizedBox(width: 4),
              Text(
                timestamp,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                ),
              ),
            ],
          ),
          if (isPending && canEnforce) ...[
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                OutlinedButton(
                  onPressed: onReject,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.red500,
                    side: BorderSide(color: AppTheme.red500),
                  ),
                  child: const Text('Reject'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: onApprove,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.green600,
                    foregroundColor: Colors.white,
                  ),
                  child: const Text('Approve'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MULTISIG QUEUE PAGE
// ═══════════════════════════════════════════════════════════════════════════

class MultisigQueuePage extends ConsumerWidget {
  const MultisigQueuePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.how_to_vote, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Multisig Queue',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Actions requiring multiple signatures',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.check_circle_outline,
                    size: 64,
                    color: isDark ? AppTheme.slate600 : AppTheme.slate300,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'No pending multisig actions',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// PENDING APPROVALS PAGE
// ═══════════════════════════════════════════════════════════════════════════

class PendingApprovalsPage extends ConsumerStatefulWidget {
  const PendingApprovalsPage({super.key});

  @override
  ConsumerState<PendingApprovalsPage> createState() => _PendingApprovalsPageState();
}

class _PendingApprovalsPageState extends ConsumerState<PendingApprovalsPage> {
  final _actionService = ActionService();
  
  final List<Map<String, dynamic>> _approvals = [
    {'id': 'tx-001', 'from': '0x742d...1ab12', 'to': '0x8f3C...A063', 'amount': '25.5 ETH', 'reason': 'High value transfer', 'timestamp': '2 minutes ago'},
    {'id': 'tx-002', 'from': '0x3f5C...0bE', 'to': '0x1234...5678', 'amount': '100 ETH', 'reason': 'New recipient address', 'timestamp': '15 minutes ago'},
  ];

  Future<void> _handleApprove(int index) async {
    final approval = _approvals[index];
    final result = await _actionService.approveTransaction(
      transactionId: approval['id'],
      approverAddress: '0xCurrentUser', // Would come from auth
      comment: 'Approved via dashboard',
    );
    
    if (mounted) {
      showActionResult(context, result);
      if (result.success) {
        setState(() => _approvals.removeAt(index));
      }
    }
  }

  Future<void> _handleReject(int index, bool isDark) async {
    final approval = _approvals[index];
    final reasonController = TextEditingController();
    
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
        title: Text('Reject Transfer', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Amount: ${approval['amount']}', style: TextStyle(color: isDark ? AppTheme.slate300 : AppTheme.slate600)),
            const SizedBox(height: 12),
            TextField(
              controller: reasonController,
              maxLines: 2,
              style: TextStyle(color: isDark ? Colors.white : Colors.black),
              decoration: InputDecoration(
                labelText: 'Rejection Reason',
                labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                border: const OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.red500),
            child: const Text('Reject', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final result = await _actionService.rejectTransaction(
        transactionId: approval['id'],
        rejecterAddress: '0xCurrentUser',
        reason: reasonController.text.isNotEmpty ? reasonController.text : 'Rejected by compliance',
      );
      
      if (mounted) {
        showActionResult(context, result);
        if (result.success) {
          setState(() => _approvals.removeAt(index));
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.pending_actions, color: AppTheme.amber500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Pending Approvals',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        '${_approvals.length} transfers awaiting approval',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (_approvals.isEmpty)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.check_circle, size: 64, color: AppTheme.green500),
                    const SizedBox(height: 16),
                    Text(
                      'All transfers approved!',
                      style: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500, fontSize: 16),
                    ),
                  ],
                ),
              ),
            )
          else
            Expanded(
              child: ListView.builder(
                padding: const EdgeInsets.all(16),
                itemCount: _approvals.length,
                itemBuilder: (context, index) {
                  final a = _approvals[index];
                  return _ApprovalCard(
                    from: a['from'],
                    to: a['to'],
                    amount: a['amount'],
                    flagReason: a['reason'],
                    timestamp: a['timestamp'],
                    isDark: isDark,
                    onApprove: () => _handleApprove(index),
                    onReject: () => _handleReject(index, isDark),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _ApprovalCard extends StatelessWidget {
  final String from;
  final String to;
  final String amount;
  final String flagReason;
  final String timestamp;
  final bool isDark;
  final VoidCallback? onApprove;
  final VoidCallback? onReject;
  
  const _ApprovalCard({
    required this.from,
    required this.to,
    required this.amount,
    required this.flagReason,
    required this.timestamp,
    required this.isDark,
    this.onApprove,
    this.onReject,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: AppTheme.amber500.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.amber500.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(Icons.swap_horiz, color: AppTheme.amber500, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      amount,
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                        color: isDark ? Colors.white : AppTheme.slate800,
                      ),
                    ),
                    Text(
                      timestamp,
                      style: TextStyle(
                        fontSize: 12,
                        color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Text(
                'From: ',
                style: TextStyle(
                  fontSize: 12,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                ),
              ),
              Text(
                from,
                style: TextStyle(
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: isDark ? AppTheme.slate300 : AppTheme.slate600,
                ),
              ),
            ],
          ),
          Row(
            children: [
              Text(
                'To: ',
                style: TextStyle(
                  fontSize: 12,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                ),
              ),
              Text(
                to,
                style: TextStyle(
                  fontSize: 12,
                  fontFamily: 'monospace',
                  color: isDark ? AppTheme.slate300 : AppTheme.slate600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: AppTheme.amber500.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              flagReason,
              style: TextStyle(
                fontSize: 11,
                color: AppTheme.amber600,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              OutlinedButton(
                onPressed: onReject,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppTheme.red500,
                  side: BorderSide(color: AppTheme.red500),
                ),
                child: const Text('Reject'),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: onApprove,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.green600,
                  foregroundColor: Colors.white,
                ),
                child: const Text('Approve'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
