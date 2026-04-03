/// War Room Shell - Institutional Interface (R3+)
/// 
/// Per Ground Truth v2.3:
/// - Full analytics dashboard for institutional users
/// - Tabbed interface with one active view at a time
/// - KPI Health Strip (passive, non-interactive)
/// - Flagged Queue as primary action surface
/// - Detection Studio: Graph Explorer, Velocity Heatmap, Sankey
/// - Compliance Studio: Policy Engine, Enforcement Actions (R4+)
/// - Multisig Governance (R4+)
/// - UI Integrity always visible
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../rbac/roles.dart';
import '../rbac/rbac_provider.dart';
import '../theme/app_theme.dart';
import 'mode_aware_shell.dart';

class WarRoomShell extends ConsumerStatefulWidget {
  final Widget child;

  const WarRoomShell({super.key, required this.child});

  @override
  ConsumerState<WarRoomShell> createState() => _WarRoomShellState();
}

class _WarRoomShellState extends ConsumerState<WarRoomShell> {
  bool _isSidebarExpanded = true;

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final currentRoute = GoRouterState.of(context).uri.toString();
    final screenWidth = MediaQuery.of(context).size.width;
    final isWideScreen = screenWidth > 1200;
    final isMediumScreen = screenWidth > 800;

    return Scaffold(
      backgroundColor: AppTheme.darkOpsBackground,
      appBar: _buildAppBar(rbacState, currentRoute),
      drawer: !isMediumScreen ? _buildDrawer(rbacState, currentRoute) : null,
      body: Row(
        children: [
          // Sidebar (permanent on wide screens)
          if (isMediumScreen)
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: _isSidebarExpanded ? 260 : 72,
              child: _buildSidebar(rbacState, currentRoute),
            ),
          
          // Main content area
          Expanded(
            child: Column(
              children: [
                // KPI Health Strip (per Ground Truth)
                _buildKPIStrip(rbacState),
                
                // Main content
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      color: AppTheme.darkOpsBackground,
                    ),
                    child: widget.child,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  PreferredSizeWidget _buildAppBar(RBACState rbacState, String currentRoute) {
    return AppBar(
      backgroundColor: AppTheme.slate900,
      foregroundColor: AppTheme.gray50,
      elevation: 0,
      leading: MediaQuery.of(context).size.width > 800
          ? IconButton(
              icon: Icon(_isSidebarExpanded ? Icons.menu_open : Icons.menu),
              onPressed: () => setState(() => _isSidebarExpanded = !_isSidebarExpanded),
              tooltip: _isSidebarExpanded ? 'Collapse sidebar' : 'Expand sidebar',
            )
          : null,
      title: Row(
        children: [
          // AMTTP Logo
          Container(
            padding: const EdgeInsets.all(6),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [AppTheme.red500, AppTheme.amber500],
              ),
              borderRadius: BorderRadius.circular(6),
            ),
            child: const Icon(Icons.security, color: Colors.white, size: 18),
          ),
          const SizedBox(width: 10),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'AMTTP',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
              Text(
                'WAR ROOM',
                style: TextStyle(
                  color: AppTheme.red400,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.5,
                ),
              ),
            ],
          ),
          const SizedBox(width: 16),
          // Institution name
          if (rbacState.institutionId != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.slate800,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: AppTheme.slate700),
              ),
              child: Text(
                rbacState.institutionId ?? 'Institution',
                style: TextStyle(
                  color: AppTheme.slate300,
                  fontSize: 12,
                ),
              ),
            ),
        ],
      ),
      actions: [
        // Search
        IconButton(
          icon: const Icon(Icons.search),
          onPressed: () => _showSearch(context),
          tooltip: 'Search',
        ),
        
        // UI Integrity Status (per Ground Truth)
        _buildIntegrityStatus(),
        const SizedBox(width: 8),
        
        // Notifications (for pending approvals)
        _buildNotificationBadge(rbacState),
        const SizedBox(width: 8),
        
        // User info
        _buildUserChip(rbacState),
        const SizedBox(width: 16),
      ],
    );
  }

  Widget _buildIntegrityStatus() {
    // Per Ground Truth: Integrity Status Dot
    // Green = chain valid, Amber = pending verification, Red = violation
    return Tooltip(
      message: 'UI Integrity Chain: Valid\nLast verified: Just now',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: AppTheme.green500.withOpacity(0.15),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppTheme.green500.withOpacity(0.4)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: AppTheme.green500,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: AppTheme.green500.withOpacity(0.5),
                    blurRadius: 4,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 6),
            Icon(Icons.lock, color: AppTheme.green500, size: 14),
            const SizedBox(width: 4),
            Text(
              'Integrity OK',
              style: TextStyle(
                color: AppTheme.green500,
                fontSize: 11,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNotificationBadge(RBACState rbacState) {
    // Only show if user can sign multisig
    if (!rbacState.capabilities.canSignMultisig) {
      return const SizedBox.shrink();
    }

    return Stack(
      children: [
        IconButton(
          icon: const Icon(Icons.notifications_outlined),
          onPressed: () => context.go('/war-room/multisig'),
          tooltip: 'Pending Approvals',
        ),
        Positioned(
          right: 6,
          top: 6,
          child: Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: AppTheme.red500,
              shape: BoxShape.circle,
            ),
            child: const Text(
              '3',
              style: TextStyle(
                color: Colors.white,
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildUserChip(RBACState rbacState) {
    return PopupMenuButton<String>(
      offset: const Offset(0, 50),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: AppTheme.slate800,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppTheme.slate700),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircleAvatar(
              radius: 12,
              backgroundColor: _getRoleColor(rbacState.role),
              child: Text(
                rbacState.displayName.isNotEmpty 
                    ? rbacState.displayName[0].toUpperCase() 
                    : 'U',
                style: const TextStyle(fontSize: 10, color: Colors.white),
              ),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  rbacState.displayName,
                  style: TextStyle(
                    color: AppTheme.gray50,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  rbacState.role.displayName,
                  style: TextStyle(
                    color: _getRoleColor(rbacState.role),
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            const SizedBox(width: 4),
            Icon(Icons.arrow_drop_down, color: AppTheme.slate400, size: 16),
          ],
        ),
      ),
      itemBuilder: (context) => [
        PopupMenuItem(
          value: 'profile',
          child: ListTile(
            leading: const Icon(Icons.person_outline),
            title: const Text('Profile'),
            dense: true,
          ),
        ),
        const PopupMenuDivider(),
        // Role switcher (demo)
        ...Role.values.map((role) => PopupMenuItem(
          value: 'role_${role.code}',
          child: ListTile(
            leading: Icon(
              _getRoleIcon(role),
              color: rbacState.role == role ? AppTheme.indigo400 : null,
            ),
            title: Text(role.displayName),
            trailing: rbacState.role == role 
                ? const Icon(Icons.check, color: AppTheme.green500, size: 18)
                : null,
            dense: true,
          ),
        )),
        const PopupMenuDivider(),
        PopupMenuItem(
          value: 'logout',
          child: ListTile(
            leading: const Icon(Icons.logout, color: AppTheme.red500),
            title: const Text('Sign Out', style: TextStyle(color: AppTheme.red500)),
            dense: true,
          ),
        ),
      ],
      onSelected: (value) {
        if (value == 'logout') {
          ref.read(rbacProvider.notifier).logout();
          context.go('/sign-in');
        } else if (value.startsWith('role_')) {
          final roleCode = value.substring(5);
          final role = Role.fromCode(roleCode);
          ref.read(rbacProvider.notifier).switchRole(role);
          final mode = getModeForRole(role);
          if (mode == AppMode.focusMode) {
            context.go('/');
          }
        }
      },
    );
  }

  /// KPI Health Strip - Per Ground Truth
  /// "Small inline sparkline + number, Non-clickable, Auto-refresh (30s)"
  Widget _buildKPIStrip(RBACState rbacState) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.slate900,
        border: Border(bottom: BorderSide(color: AppTheme.slate800)),
      ),
      child: Row(
        children: [
          _buildKPICard('Active Flags', '12', Icons.flag, AppTheme.red400),
          _buildKPICard('Pending Signatures', '3', Icons.how_to_vote, AppTheme.amber400),
          _buildKPICard('Escrowed', '₿ 2.4M', Icons.lock_clock, AppTheme.blue400),
          _buildKPICard('Paused Wallets', '5', Icons.pause_circle, AppTheme.purple400),
          const Spacer(),
          // Last updated
          Text(
            'Updated: Just now',
            style: TextStyle(
              color: AppTheme.slate500,
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildKPICard(String label, String value, IconData icon, Color color) {
    return Container(
      margin: const EdgeInsets.only(right: 24),
      child: Row(
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                value,
                style: TextStyle(
                  color: AppTheme.gray50,
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  fontFamily: 'JetBrains Mono',
                ),
              ),
              Text(
                label,
                style: TextStyle(
                  color: AppTheme.slate400,
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSidebar(RBACState rbacState, String currentRoute) {
    final sections = WarRoomNavigation.getForRole(rbacState.role);
    
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.slate900,
        border: Border(right: BorderSide(color: AppTheme.slate800)),
      ),
      child: ListView(
        padding: const EdgeInsets.symmetric(vertical: 8),
        children: [
          for (final section in sections) ...[
            if (_isSidebarExpanded)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                child: Text(
                  section.title,
                  style: TextStyle(
                    color: AppTheme.slate500,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 1.2,
                  ),
                ),
              ),
            ...section.items.map((item) => _buildNavItem(item, currentRoute)),
          ],
        ],
      ),
    );
  }

  Widget _buildNavItem(NavItem item, String currentRoute) {
    final isActive = _isRouteActive(item.route, currentRoute);
    
    return Tooltip(
      message: _isSidebarExpanded ? '' : item.title,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        child: Material(
          color: isActive ? AppTheme.indigo500.withOpacity(0.15) : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
          child: InkWell(
            onTap: () => context.go(item.route),
            borderRadius: BorderRadius.circular(8),
            hoverColor: AppTheme.slate800,
            child: Container(
              padding: EdgeInsets.symmetric(
                horizontal: _isSidebarExpanded ? 12 : 16,
                vertical: 10,
              ),
              child: Row(
                children: [
                  Icon(
                    isActive ? item.activeIcon : item.icon,
                    color: isActive ? AppTheme.indigo400 : AppTheme.slate400,
                    size: 20,
                  ),
                  if (_isSidebarExpanded) ...[
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        item.title,
                        style: TextStyle(
                          color: isActive ? AppTheme.indigo400 : AppTheme.gray200,
                          fontSize: 13,
                          fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                        ),
                      ),
                    ),
                    if (item.badge != null)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: AppTheme.red500,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(
                          item.badge!,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDrawer(RBACState rbacState, String currentRoute) {
    final sections = WarRoomNavigation.getForRole(rbacState.role);
    
    return Drawer(
      backgroundColor: AppTheme.slate900,
      child: ListView(
        padding: EdgeInsets.zero,
        children: [
          DrawerHeader(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [AppTheme.red600, AppTheme.amber600],
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                const Icon(Icons.security, color: Colors.white, size: 40),
                const SizedBox(height: 8),
                const Text(
                  'AMTTP',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Text(
                  'WAR ROOM',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 14,
                    letterSpacing: 2,
                  ),
                ),
              ],
            ),
          ),
          for (final section in sections) ...[
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text(
                section.title,
                style: TextStyle(
                  color: AppTheme.slate500,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1,
                ),
              ),
            ),
            ...section.items.map((item) {
              final isActive = _isRouteActive(item.route, currentRoute);
              return ListTile(
                leading: Icon(
                  isActive ? item.activeIcon : item.icon,
                  color: isActive ? AppTheme.indigo400 : AppTheme.slate400,
                ),
                title: Text(
                  item.title,
                  style: TextStyle(
                    color: isActive ? AppTheme.indigo400 : AppTheme.gray200,
                    fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
                selected: isActive,
                selectedTileColor: AppTheme.indigo500.withOpacity(0.1),
                onTap: () {
                  Navigator.pop(context);
                  context.go(item.route);
                },
              );
            }),
          ],
        ],
      ),
    );
  }

  bool _isRouteActive(String itemRoute, String currentRoute) {
    if (itemRoute == '/war-room' && currentRoute == '/war-room') {
      return true;
    }
    if (itemRoute != '/war-room' && currentRoute.startsWith(itemRoute)) {
      return true;
    }
    return false;
  }

  void _showSearch(BuildContext context) {
    showSearch(
      context: context,
      delegate: _WarRoomSearchDelegate(),
    );
  }

  Color _getRoleColor(Role role) {
    switch (role) {
      case Role.r1EndUser:
      case Role.r2EndUserPep:
        return AppTheme.indigo500;
      case Role.r3InstitutionOps:
        return AppTheme.blue500;
      case Role.r4InstitutionCompliance:
        return AppTheme.purple500;
      case Role.r5PlatformAdmin:
        return AppTheme.amber500;
      case Role.r6SuperAdmin:
        return AppTheme.red500;
    }
  }

  IconData _getRoleIcon(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return Icons.person_outline;
      case Role.r2EndUserPep:
        return Icons.verified_user_outlined;
      case Role.r3InstitutionOps:
        return Icons.analytics_outlined;
      case Role.r4InstitutionCompliance:
        return Icons.gavel_outlined;
      case Role.r5PlatformAdmin:
        return Icons.admin_panel_settings_outlined;
      case Role.r6SuperAdmin:
        return Icons.shield_outlined;
    }
  }
}

class _WarRoomSearchDelegate extends SearchDelegate<String> {
  @override
  ThemeData appBarTheme(BuildContext context) {
    return ThemeData.dark().copyWith(
      scaffoldBackgroundColor: AppTheme.darkOpsBackground,
      appBarTheme: AppBarTheme(
        backgroundColor: AppTheme.slate900,
        foregroundColor: AppTheme.gray50,
      ),
      inputDecorationTheme: InputDecorationTheme(
        hintStyle: TextStyle(color: AppTheme.slate400),
      ),
    );
  }

  @override
  List<Widget> buildActions(BuildContext context) {
    return [
      IconButton(
        icon: const Icon(Icons.clear),
        onPressed: () => query = '',
      ),
    ];
  }

  @override
  Widget buildLeading(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.arrow_back),
      onPressed: () => close(context, ''),
    );
  }

  @override
  Widget buildResults(BuildContext context) {
    return _buildSearchResults();
  }

  @override
  Widget buildSuggestions(BuildContext context) {
    return _buildSearchResults();
  }

  Widget _buildSearchResults() {
    return Container(
      color: AppTheme.darkOpsBackground,
      child: Center(
        child: Text(
          'Search for wallet addresses, transaction IDs, or case numbers',
          style: TextStyle(color: AppTheme.slate400),
        ),
      ),
    );
  }
}
