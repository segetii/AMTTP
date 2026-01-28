import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/rbac/rbac.dart';
import '../../core/theme/app_theme.dart';
import '../../services/bridge/bridge.dart';

/// War Room Mode Shell
/// 
/// Full analytics interface for institutional users (R3+).
/// Features:
/// - Sidebar navigation with sections
/// - Role-based menu items
/// - Embedded Next.js analytics
/// - Full-screen mode support
/// - Dark theme (Ops background)

class WarRoomShell extends ConsumerStatefulWidget {
  final Widget child;
  final String? currentRoute;
  final bool showSidebar;

  const WarRoomShell({
    super.key,
    required this.child,
    this.currentRoute,
    this.showSidebar = true,
  });

  @override
  ConsumerState<WarRoomShell> createState() => _WarRoomShellState();
}

class _WarRoomShellState extends ConsumerState<WarRoomShell> {
  bool _sidebarExpanded = true;
  String? _expandedSection;
  final FlutterNextJSBridge _bridge = FlutterNextJSBridge();

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final role = rbacState.role;
    final navItems = filterNavItemsForRole(warRoomNavItems, role);
    
    // Use ProfileNavigation for feature access checks
    final profileNav = ProfileNavigation(role);
    
    return Scaffold(
      backgroundColor: AppTheme.backgroundDarkOps,
      body: Row(
        children: [
          // Sidebar
          if (widget.showSidebar)
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: _sidebarExpanded ? 260 : 72,
              child: _buildSidebar(navItems, rbacState, profileNav),
            ),
          
          // Main Content
          Expanded(
            child: Column(
              children: [
                // Top Bar
                _buildTopBar(rbacState),
                
                // Content
                Expanded(
                  child: Container(
                    margin: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.darkSurface,
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: Colors.white10),
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(16),
                      child: widget.child,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSidebar(List<NavItem> navItems, RBACState rbacState, ProfileNavigation profileNav) {
    return Container(
      color: const Color(0xFF0D1117),
      child: Column(
        children: [
          // Logo Section
          Container(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    gradient: AppTheme.primaryGradient,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.shield, color: Colors.white, size: 24),
                ),
                if (_sidebarExpanded) ...[
                  const SizedBox(width: 12),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'AMTTP',
                        style: TextStyle(
                          color: AppTheme.textPrimary,
                          fontWeight: FontWeight.bold,
                          fontSize: 18,
                        ),
                      ),
                      Text(
                        'War Room',
                        style: TextStyle(
                          color: AppTheme.textSecondary,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          
          const Divider(color: Colors.white10, height: 1),
          
          // Navigation Items
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                // Monitoring Section (R3+ has basic War Room access)
                _buildSection('MONITORING', navItems.where((i) => 
                  ['dashboard', 'detection', 'flagged'].contains(i.id)).toList()),
                
                // Compliance Section (Uses ProfileNavigation)
                if (profileNav.hasComplianceAccess)
                  _buildSection('COMPLIANCE', navItems.where((i) => 
                    ['compliance', 'multisig', 'audit'].contains(i.id)).toList()),
                
                // Admin Section (Uses ProfileNavigation)
                if (profileNav.hasAdminAccess)
                  _buildSection('ADMIN', navItems.where((i) => 
                    ['users', 'system', 'emergency'].contains(i.id)).toList()),
                
                // Super Admin Section (Uses ProfileNavigation)
                if (profileNav.hasSuperAdminAccess)
                  _buildSection('ML & AI', [
                    NavItem(
                      id: 'ml-models',
                      title: 'ML Models',
                      route: '/war-room/detection/models',
                      icon: Icons.model_training_rounded,
                      minRoleLevel: 6,
                    ),
                  ]),
                
                // Analytics (Embedded Next.js)
                const SizedBox(height: 16),
                _buildAnalyticsSection(),
              ],
            ),
          ),
          
          // Sidebar Toggle
          const Divider(color: Colors.white10, height: 1),
          InkWell(
            onTap: () => setState(() => _sidebarExpanded = !_sidebarExpanded),
            child: Container(
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: _sidebarExpanded 
                  ? MainAxisAlignment.spaceBetween
                  : MainAxisAlignment.center,
                children: [
                  if (_sidebarExpanded)
                    Text(
                      'Collapse',
                      style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                    ),
                  Icon(
                    _sidebarExpanded 
                      ? Icons.chevron_left 
                      : Icons.chevron_right,
                    color: AppTheme.textSecondary,
                    size: 20,
                  ),
                ],
              ),
            ),
          ),
          
          // User Profile
          const Divider(color: Colors.white10, height: 1),
          _buildUserProfile(rbacState),
        ],
      ),
    );
  }

  Widget _buildSection(String title, List<NavItem> items) {
    if (items.isEmpty) return const SizedBox.shrink();
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_sidebarExpanded)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              title,
              style: TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 1,
              ),
            ),
          ),
        ...items.map((item) => _buildNavItem(item)),
      ],
    );
  }

  Widget _buildNavItem(NavItem item) {
    final isSelected = widget.currentRoute == item.route;
    final hasChildren = item.children.isNotEmpty;
    final isExpanded = _expandedSection == item.id;
    
    return Column(
      children: [
        InkWell(
          onTap: () {
            if (hasChildren) {
              setState(() {
                _expandedSection = isExpanded ? null : item.id;
              });
            } else {
              Navigator.pushNamed(context, item.route);
            }
          },
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            padding: EdgeInsets.symmetric(
              horizontal: _sidebarExpanded ? 12 : 16,
              vertical: 10,
            ),
            decoration: BoxDecoration(
              color: isSelected 
                ? AppTheme.primaryBlue.withOpacity(0.15)
                : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              border: isSelected 
                ? Border.all(color: AppTheme.primaryBlue.withOpacity(0.3))
                : null,
            ),
            child: Row(
              children: [
                Icon(
                  item.icon,
                  color: isSelected 
                    ? AppTheme.primaryBlue
                    : AppTheme.textLight,
                  size: 20,
                ),
                if (_sidebarExpanded) ...[
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      item.title,
                      style: TextStyle(
                        color: isSelected 
                          ? AppTheme.textPrimary
                          : AppTheme.mediumAsh,
                        fontSize: 14,
                        fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                      ),
                    ),
                  ),
                  if (item.badge != null)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: AppTheme.riskHigh,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        item.badge!,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  if (hasChildren)
                    Icon(
                      isExpanded 
                        ? Icons.keyboard_arrow_down 
                        : Icons.keyboard_arrow_right,
                      color: AppTheme.textSecondary,
                      size: 18,
                    ),
                ],
              ],
            ),
          ),
        ),
        
        // Child items
        if (hasChildren && isExpanded && _sidebarExpanded)
          Padding(
            padding: const EdgeInsets.only(left: 20),
            child: Column(
              children: item.children.map((child) => _buildNavItem(child)).toList(),
            ),
          ),
      ],
    );
  }

  Widget _buildAnalyticsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_sidebarExpanded)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              'ANALYTICS',
              style: TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 1,
              ),
            ),
          ),
        InkWell(
          onTap: () => Navigator.pushNamed(context, '/analytics'),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            padding: EdgeInsets.symmetric(
              horizontal: _sidebarExpanded ? 12 : 16,
              vertical: 10,
            ),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AppTheme.primaryBlue.withOpacity(0.1),
                  AppTheme.accentPink.withOpacity(0.1),
                ],
              ),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.primaryBlue.withOpacity(0.2)),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.analytics_rounded,
                  color: AppTheme.primaryBlue,
                  size: 20,
                ),
                if (_sidebarExpanded) ...[
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Analytics Hub',
                      style: TextStyle(
                        color: AppTheme.textPrimary,
                        fontSize: 14,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppTheme.riskLow,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: const Text(
                      'LIVE',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        
        // Open in Browser
        if (_sidebarExpanded)
          InkWell(
            onTap: () => _bridge.openFullScreen('/war-room'),
            child: Container(
              margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: const Row(
                children: [
                  Icon(
                    Icons.open_in_new,
                    color: Color(0xFF64748B),
                    size: 18,
                  ),
                  SizedBox(width: 12),
                  Text(
                    'Open Full Screen',
                    style: TextStyle(
                      color: Color(0xFF64748B),
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildUserProfile(RBACState rbacState) {
    return Container(
      padding: const EdgeInsets.all(12),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
              ),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Center(
              child: Text(
                rbacState.displayName.isNotEmpty 
                  ? rbacState.displayName[0].toUpperCase()
                  : 'U',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
            ),
          ),
          if (_sidebarExpanded) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    rbacState.displayName,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    rbacState.role.displayName,
                    style: const TextStyle(
                      color: Color(0xFF64748B),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            PopupMenuButton<String>(
              icon: const Icon(Icons.more_vert, color: Color(0xFF64748B), size: 18),
              color: const Color(0xFF1A1F2E),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: const BorderSide(color: Colors.white10),
              ),
              itemBuilder: (context) => [
                const PopupMenuItem(
                  value: 'profile',
                  child: Row(
                    children: [
                      Icon(Icons.person, color: Colors.white70, size: 18),
                      SizedBox(width: 8),
                      Text('Profile', style: TextStyle(color: Colors.white)),
                    ],
                  ),
                ),
                const PopupMenuItem(
                  value: 'settings',
                  child: Row(
                    children: [
                      Icon(Icons.settings, color: Colors.white70, size: 18),
                      SizedBox(width: 8),
                      Text('Settings', style: TextStyle(color: Colors.white)),
                    ],
                  ),
                ),
                const PopupMenuDivider(),
                const PopupMenuItem(
                  value: 'logout',
                  child: Row(
                    children: [
                      Icon(Icons.logout, color: Color(0xFFEF4444), size: 18),
                      SizedBox(width: 8),
                      Text('Logout', style: TextStyle(color: Color(0xFFEF4444))),
                    ],
                  ),
                ),
              ],
              onSelected: (value) {
                switch (value) {
                  case 'profile':
                    Navigator.pushNamed(context, '/profile');
                    break;
                  case 'settings':
                    Navigator.pushNamed(context, '/settings');
                    break;
                  case 'logout':
                    ref.read(rbacProvider.notifier).logout();
                    Navigator.pushReplacementNamed(context, '/login');
                    break;
                }
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTopBar(RBACState rbacState) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
      decoration: const BoxDecoration(
        color: Color(0xFF0D1117),
        border: Border(bottom: BorderSide(color: Colors.white10)),
      ),
      child: Row(
        children: [
          // Search
          Expanded(
            child: Container(
              height: 40,
              decoration: BoxDecoration(
                color: const Color(0xFF1A1F2E),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white10),
              ),
              child: const TextField(
                style: TextStyle(color: Colors.white, fontSize: 14),
                decoration: InputDecoration(
                  hintText: 'Search transactions, addresses...',
                  hintStyle: TextStyle(color: Color(0xFF64748B), fontSize: 14),
                  prefixIcon: Icon(Icons.search, color: Color(0xFF64748B), size: 20),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
          ),
          
          const SizedBox(width: 16),
          
          // Quick Actions
          _buildTopBarButton(
            icon: Icons.refresh,
            tooltip: 'Refresh Data',
            onTap: () {},
          ),
          _buildTopBarButton(
            icon: Icons.notifications_outlined,
            tooltip: 'Alerts',
            badge: '5',
            onTap: () => Navigator.pushNamed(context, '/war-room/alerts'),
          ),
          _buildTopBarButton(
            icon: Icons.help_outline,
            tooltip: 'Help',
            onTap: () {},
          ),
          
          const SizedBox(width: 8),
          
          // Back to Focus Mode
          TextButton.icon(
            onPressed: () => Navigator.pushReplacementNamed(context, '/'),
            icon: const Icon(Icons.home_outlined, size: 16),
            label: const Text('Focus Mode'),
            style: TextButton.styleFrom(
              foregroundColor: AppTheme.textSecondary,
              backgroundColor: Colors.white.withOpacity(0.05),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(6),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            ),
          ),
          
          const SizedBox(width: 8),
          
          // Role Badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: _getRoleColor(rbacState.role).withOpacity(0.15),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: _getRoleColor(rbacState.role).withOpacity(0.3)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  _getRoleIcon(rbacState.role),
                  color: _getRoleColor(rbacState.role),
                  size: 14,
                ),
                const SizedBox(width: 6),
                Text(
                  rbacState.role.code,
                  style: TextStyle(
                    color: _getRoleColor(rbacState.role),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopBarButton({
    required IconData icon,
    required String tooltip,
    String? badge,
    required VoidCallback onTap,
  }) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          width: 40,
          height: 40,
          margin: const EdgeInsets.symmetric(horizontal: 4),
          child: Stack(
            alignment: Alignment.center,
            children: [
              Icon(icon, color: const Color(0xFF94A3B8), size: 20),
              if (badge != null)
                Positioned(
                  right: 6,
                  top: 6,
                  child: Container(
                    padding: const EdgeInsets.all(4),
                    decoration: const BoxDecoration(
                      color: Color(0xFFEF4444),
                      shape: BoxShape.circle,
                    ),
                    child: Text(
                      badge,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 9,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Color _getRoleColor(Role role) {
    switch (role) {
      case Role.r3InstitutionOps:
        return const Color(0xFF3B82F6);
      case Role.r4InstitutionCompliance:
        return const Color(0xFFF59E0B);
      case Role.r5PlatformAdmin:
        return const Color(0xFF8B5CF6);
      case Role.r6SuperAdmin:
        return const Color(0xFFEF4444);
      default:
        return const Color(0xFF10B981);
    }
  }

  IconData _getRoleIcon(Role role) {
    switch (role) {
      case Role.r3InstitutionOps:
        return Icons.visibility;
      case Role.r4InstitutionCompliance:
        return Icons.policy;
      case Role.r5PlatformAdmin:
        return Icons.admin_panel_settings;
      case Role.r6SuperAdmin:
        return Icons.security;
      default:
        return Icons.person;
    }
  }
}
