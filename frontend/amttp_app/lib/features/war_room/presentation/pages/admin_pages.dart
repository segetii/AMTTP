/// War Room Admin Pages
/// 
/// Per Ground Truth v2.3:
/// - UI Snapshots: Audit trail screenshots
/// - Reports: Compliance reporting
/// - User Management: RBAC user administration (R5+)
/// - System Settings: Platform configuration (R5+)
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';
import '../../../../core/rbac/roles.dart';
import '../../../../core/services/action_service.dart';

// ═══════════════════════════════════════════════════════════════════════════
// UI SNAPSHOTS PAGE
// ═══════════════════════════════════════════════════════════════════════════

class UISnapshotsPage extends ConsumerWidget {
  const UISnapshotsPage({super.key});

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
                Icon(Icons.photo_camera, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'UI Snapshots',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Automated audit trail screenshots',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton.outlined(
                  onPressed: () {},
                  icon: const Icon(Icons.filter_list),
                  tooltip: 'Filter',
                ),
              ],
            ),
          ),
          Expanded(
            child: GridView.builder(
              padding: const EdgeInsets.all(16),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 3,
                crossAxisSpacing: 16,
                mainAxisSpacing: 16,
                childAspectRatio: 1.6,
              ),
              itemCount: 9,
              itemBuilder: (context, index) {
                return _SnapshotCard(
                  index: index,
                  isDark: isDark,
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SnapshotCard extends StatelessWidget {
  final int index;
  final bool isDark;
  
  const _SnapshotCard({required this.index, required this.isDark});

  @override
  Widget build(BuildContext context) {
    final actions = [
      'Freeze Action',
      'Policy Update',
      'Transfer Approval',
      'User Role Change',
      'Threshold Adjustment',
      'Unfreeze Action',
      'Report Generated',
      'System Config',
      'Bulk Export',
    ];
    
    return Container(
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
          // Placeholder for screenshot
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: isDark ? AppTheme.slate700 : Colors.grey.shade100,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
              ),
              child: Center(
                child: Icon(
                  Icons.image,
                  size: 40,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate300,
                ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  actions[index],
                  style: TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 13,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  DateTime.now().subtract(Duration(hours: index * 3)).toString().substring(0, 16),
                  style: TextStyle(
                    fontSize: 11,
                    color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// REPORTS PAGE
// ═══════════════════════════════════════════════════════════════════════════

class ReportsPage extends ConsumerWidget {
  const ReportsPage({super.key});

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
                Icon(Icons.assessment, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Reports',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Generate and download compliance reports',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.add, size: 18),
                  label: const Text('New Report'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.purple600,
                    foregroundColor: Colors.white,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _ReportCard(
                  name: 'Monthly Compliance Summary',
                  description: 'Summary of all compliance activities',
                  schedule: 'Monthly',
                  lastRun: '2024-01-01',
                  isDark: isDark,
                ),
                _ReportCard(
                  name: 'Transaction Anomaly Report',
                  description: 'ML-flagged suspicious transactions',
                  schedule: 'Daily',
                  lastRun: '2024-01-15',
                  isDark: isDark,
                ),
                _ReportCard(
                  name: 'FATF Travel Rule Audit',
                  description: 'Compliance with FATF guidelines',
                  schedule: 'Quarterly',
                  lastRun: '2023-10-01',
                  isDark: isDark,
                ),
                _ReportCard(
                  name: 'Enforcement Actions Log',
                  description: 'All freeze/unfreeze actions',
                  schedule: 'Weekly',
                  lastRun: '2024-01-08',
                  isDark: isDark,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ReportCard extends StatelessWidget {
  final String name;
  final String description;
  final String schedule;
  final String lastRun;
  final bool isDark;
  
  const _ReportCard({
    required this.name,
    required this.description,
    required this.schedule,
    required this.lastRun,
    required this.isDark,
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
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.purple500.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(Icons.description, color: AppTheme.purple500),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: TextStyle(
                    fontSize: 13,
                    color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    _InfoChip(label: schedule, isDark: isDark),
                    const SizedBox(width: 8),
                    Text(
                      'Last: $lastRun',
                      style: TextStyle(
                        fontSize: 11,
                        color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Column(
            children: [
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.play_arrow),
                color: AppTheme.green500,
                tooltip: 'Run Now',
              ),
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.download),
                color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                tooltip: 'Download Last',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final String label;
  final bool isDark;
  
  const _InfoChip({required this.label, required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.purple500.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: AppTheme.purple500,
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// USER MANAGEMENT PAGE (R5+)
// ═══════════════════════════════════════════════════════════════════════════

class UserManagementPage extends ConsumerStatefulWidget {
  const UserManagementPage({super.key});

  @override
  ConsumerState<UserManagementPage> createState() => _UserManagementPageState();
}

class _UserManagementPageState extends ConsumerState<UserManagementPage> {
  final _actionService = ActionService();
  
  // Demo users list (in production would come from API)
  final List<Map<String, dynamic>> _users = [
    {'name': 'Alice Johnson', 'email': 'alice@institution.com', 'role': Role.r5PlatformAdmin, 'lastActive': '2 min ago'},
    {'name': 'Bob Smith', 'email': 'bob@institution.com', 'role': Role.r4InstitutionCompliance, 'lastActive': '1 hour ago'},
    {'name': 'Carol Davis', 'email': 'carol@institution.com', 'role': Role.r3InstitutionOps, 'lastActive': '3 hours ago'},
  ];

  void _showAddUserDialog(BuildContext context, bool isDark) {
    final nameController = TextEditingController();
    final emailController = TextEditingController();
    Role selectedRole = Role.r1EndUser;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
          title: Row(
            children: [
              Icon(Icons.person_add, color: AppTheme.purple500),
              const SizedBox(width: 8),
              Text('Add New User', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
            ],
          ),
          content: SizedBox(
            width: 400,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Full Name',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                    prefixIcon: const Icon(Icons.person),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: emailController,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Email Address',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                    prefixIcon: const Icon(Icons.email),
                  ),
                ),
                const SizedBox(height: 16),
                DropdownButtonFormField<Role>(
                  initialValue: selectedRole,
                  dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black),
                  decoration: InputDecoration(
                    labelText: 'Role',
                    labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
                    border: const OutlineInputBorder(),
                    prefixIcon: const Icon(Icons.admin_panel_settings),
                  ),
                  items: Role.values.map((r) => DropdownMenuItem(
                    value: r,
                    child: Text(r.displayName),
                  )).toList(),
                  onChanged: (r) => setDialogState(() => selectedRole = r!),
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
                if (nameController.text.isEmpty || emailController.text.isEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Please fill all fields'), backgroundColor: Colors.red),
                  );
                  return;
                }
                Navigator.pop(ctx);
                final result = await _actionService.addUser(
                  email: emailController.text,
                  name: nameController.text,
                  role: selectedRole.name,
                );
                if (mounted) {
                  showActionResult(context, result);
                  if (result.success) {
                    setState(() {
                      _users.add({
                        'name': nameController.text,
                        'email': emailController.text,
                        'role': selectedRole,
                        'lastActive': 'Just now',
                      });
                    });
                  }
                }
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.purple600,
                foregroundColor: Colors.white,
              ),
              child: const Text('Add User'),
            ),
          ],
        ),
      ),
    );
  }

  void _handleUserAction(BuildContext context, String action, Map<String, dynamic> user, bool isDark) async {
    switch (action) {
      case 'edit':
        _showEditRoleDialog(context, user, isDark);
        break;
      case 'disable':
        final result = await _actionService.disableUser(user['email']);
        if (mounted) showActionResult(context, result);
        break;
      case 'delete':
        final confirm = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
            title: Text('Remove User', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
            content: Text(
              'Are you sure you want to remove ${user['name']}? This action cannot be undone.',
              style: TextStyle(color: isDark ? AppTheme.slate300 : AppTheme.slate600),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
              ElevatedButton(
                onPressed: () => Navigator.pop(ctx, true),
                style: ElevatedButton.styleFrom(backgroundColor: AppTheme.red500),
                child: const Text('Remove', style: TextStyle(color: Colors.white)),
              ),
            ],
          ),
        );
        if (confirm == true) {
          final result = await _actionService.removeUser(user['email']);
          if (mounted) {
            showActionResult(context, result);
            if (result.success) {
              setState(() => _users.removeWhere((u) => u['email'] == user['email']));
            }
          }
        }
        break;
    }
  }

  void _showEditRoleDialog(BuildContext context, Map<String, dynamic> user, bool isDark) {
    Role selectedRole = user['role'] as Role;
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
          title: Text('Edit Role: ${user['name']}', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800)),
          content: DropdownButtonFormField<Role>(
            initialValue: selectedRole,
            dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
            style: TextStyle(color: isDark ? Colors.white : Colors.black),
            decoration: InputDecoration(
              labelText: 'New Role',
              labelStyle: TextStyle(color: isDark ? AppTheme.slate400 : AppTheme.slate500),
              border: const OutlineInputBorder(),
            ),
            items: Role.values.map((r) => DropdownMenuItem(
              value: r,
              child: Text(r.displayName),
            )).toList(),
            onChanged: (r) => setDialogState(() => selectedRole = r!),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(ctx);
                final result = await _actionService.updateUserRole(
                  userId: user['email'],
                  newRole: selectedRole.name,
                );
                if (mounted) {
                  showActionResult(context, result);
                  if (result.success) {
                    setState(() {
                      final idx = _users.indexWhere((u) => u['email'] == user['email']);
                      if (idx >= 0) _users[idx]['role'] = selectedRole;
                    });
                  }
                }
              },
              style: ElevatedButton.styleFrom(backgroundColor: AppTheme.purple600),
              child: const Text('Save', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final rbac = ref.watch(rbacProvider);
    
    if (!rbac.role.isAtLeast(Role.r5PlatformAdmin)) {
      return _AccessDeniedView(isDark: isDark);
    }

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.people, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'User Management',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Manage platform users and roles',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                        ),
                      ),
                    ],
                  ),
                ),
                ElevatedButton.icon(
                  onPressed: () => _showAddUserDialog(context, isDark),
                  icon: const Icon(Icons.person_add, size: 18),
                  label: const Text('Add User'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.purple600,
                    foregroundColor: Colors.white,
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _users.length,
              itemBuilder: (context, index) {
                final user = _users[index];
                return _UserCard(
                  name: user['name'],
                  email: user['email'],
                  role: user['role'],
                  lastActive: user['lastActive'],
                  isDark: isDark,
                  onAction: (action) => _handleUserAction(context, action, user, isDark),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _UserCard extends StatelessWidget {
  final String name;
  final String email;
  final Role role;
  final String lastActive;
  final bool isDark;
  final void Function(String action)? onAction;
  
  const _UserCard({
    required this.name,
    required this.email,
    required this.role,
    required this.lastActive,
    required this.isDark,
    this.onAction,
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
      child: Row(
        children: [
          CircleAvatar(
            radius: 24,
            backgroundColor: AppTheme.purple500.withValues(alpha: 0.2),
            child: Text(
              name[0],
              style: TextStyle(
                color: AppTheme.purple500,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
                Text(
                  email,
                  style: TextStyle(
                    fontSize: 13,
                    color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: _getRoleColor(role).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  role.displayName,
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                    color: _getRoleColor(role),
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                lastActive,
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? AppTheme.slate500 : AppTheme.slate400,
                ),
              ),
            ],
          ),
          const SizedBox(width: 8),
          PopupMenuButton<String>(
            icon: Icon(
              Icons.more_vert,
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
            onSelected: onAction,
            itemBuilder: (context) => [
              const PopupMenuItem(value: 'edit', child: Text('Edit Role')),
              const PopupMenuItem(value: 'disable', child: Text('Disable')),
              PopupMenuItem(
                value: 'delete',
                child: Text('Remove', style: TextStyle(color: AppTheme.red500)),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Color _getRoleColor(Role role) {
    switch (role) {
      case Role.r6SuperAdmin:
        return AppTheme.red500;
      case Role.r5PlatformAdmin:
        return AppTheme.purple500;
      case Role.r4InstitutionCompliance:
        return AppTheme.blue500;
      case Role.r3InstitutionOps:
        return AppTheme.green500;
      default:
        return AppTheme.slate500;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SYSTEM SETTINGS PAGE (R5+)
// ═══════════════════════════════════════════════════════════════════════════

class SystemSettingsPage extends ConsumerWidget {
  const SystemSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final rbac = ref.watch(rbacProvider);
    
    if (!rbac.role.isAtLeast(Role.r5PlatformAdmin)) {
      return _AccessDeniedView(isDark: isDark);
    }

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                Icon(Icons.settings, color: AppTheme.purple500),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'System Settings',
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: isDark ? Colors.white : AppTheme.slate800,
                        ),
                      ),
                      Text(
                        'Platform configuration',
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
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _SettingsSection(
                  title: 'Risk Thresholds',
                  isDark: isDark,
                  children: [
                    _SettingsRow(
                      label: 'High Risk Score',
                      value: '0.75',
                      isDark: isDark,
                    ),
                    _SettingsRow(
                      label: 'Medium Risk Score',
                      value: '0.50',
                      isDark: isDark,
                    ),
                    _SettingsRow(
                      label: 'Auto-Flag Threshold',
                      value: '0.85',
                      isDark: isDark,
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _SettingsSection(
                  title: 'Transfer Limits',
                  isDark: isDark,
                  children: [
                    _SettingsRow(
                      label: 'Approval Required Above',
                      value: '10 ETH',
                      isDark: isDark,
                    ),
                    _SettingsRow(
                      label: 'Daily Limit',
                      value: '100 ETH',
                      isDark: isDark,
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _SettingsSection(
                  title: 'Integration',
                  isDark: isDark,
                  children: [
                    _SettingsRow(
                      label: 'Memgraph Endpoint',
                      value: 'localhost:7687',
                      isDark: isDark,
                    ),
                    _SettingsRow(
                      label: 'ML Service URL',
                      value: 'http://ml:8000',
                      isDark: isDark,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsSection extends StatelessWidget {
  final String title;
  final bool isDark;
  final List<Widget> children;
  
  const _SettingsSection({
    required this.title,
    required this.isDark,
    required this.children,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
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
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              title,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 15,
                color: isDark ? Colors.white : AppTheme.slate800,
              ),
            ),
          ),
          const Divider(height: 1),
          ...children,
        ],
      ),
    );
  }
}

class _SettingsRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isDark;
  
  const _SettingsRow({
    required this.label,
    required this.value,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: isDark ? AppTheme.slate300 : AppTheme.slate600,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontWeight: FontWeight.w500,
              fontFamily: 'monospace',
              color: isDark ? Colors.white : AppTheme.slate800,
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.edit, size: 18),
            color: isDark ? AppTheme.slate400 : AppTheme.slate500,
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ACCESS DENIED VIEW
// ═══════════════════════════════════════════════════════════════════════════

class _AccessDeniedView extends StatelessWidget {
  final bool isDark;
  
  const _AccessDeniedView({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.lock,
              size: 64,
              color: AppTheme.red500,
            ),
            const SizedBox(height: 16),
            Text(
              'Access Denied',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: isDark ? Colors.white : AppTheme.slate800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'You need Platform Admin (R5) role or higher',
              style: TextStyle(
                color: isDark ? AppTheme.slate400 : AppTheme.slate500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
