/// Role-Based Shell - Clean Implementation
/// 
/// ARCHITECTURE:
/// - Single sidebar navigation (no double bars)
/// - Full screen mode for embedded Next.js pages (top bar hides)
/// - Back arrow overlay for navigation

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/rbac/rbac.dart';
import '../../core/rbac/role_navigation_config.dart';
import '../../core/theme/app_theme.dart';
// Import the Premium Fintech Shell (Metamask/Revolut style)
import 'premium_fintech_shell.dart';

/// Provider to track if we're in full screen mode
final fullScreenModeProvider = StateProvider<bool>((ref) => false);

/// Provider to track the current embedded route
final currentEmbeddedRouteProvider = StateProvider<String?>((ref) => null);

/// Provider to track the previous route for back navigation
final previousRouteProvider = StateProvider<String?>((ref) => null);

/// Unified shell that adapts to the user's role
class RoleBasedShell extends ConsumerStatefulWidget {
  final Widget child;
  final String? currentRoute;
  final bool isEmbeddedPage; // True when showing embedded Next.js content

  const RoleBasedShell({
    super.key,
    required this.child,
    this.currentRoute,
    this.isEmbeddedPage = false,
  });

  @override
  ConsumerState<RoleBasedShell> createState() => _RoleBasedShellState();
}

class _RoleBasedShellState extends ConsumerState<RoleBasedShell> {
  bool _sidebarExpanded = true;
  String? _expandedSection;

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final role = rbacState.role;
    final config = getNavigationConfigForRole(role);
    final isFullScreen = ref.watch(fullScreenModeProvider);
    
    // End users (R1, R2) get the Premium Fintech Shell
    if (role == Role.r1EndUser || role == Role.r2EndUserPep) {
      if (isFullScreen || widget.isEmbeddedPage) {
        return _buildFullScreenMode(config);
      }
      
      final isPeP = role == Role.r2EndUserPep;
      
      // Use the Premium Fintech Shell (Metamask/Revolut style)
      return PremiumFintechShell(
        currentRoute: widget.currentRoute,
        isPeP: isPeP,
        child: widget.child,
      );
    }

    // Institutional users (R3+) keep the sidebar with embedded pages
    // Only go full screen if explicitly requested (not just because it's embedded)
    if (isFullScreen) {
      return _buildFullScreenMode(config);
    }

    return _buildWarRoomShell(config, rbacState);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // FULL SCREEN MODE - For embedded Next.js pages
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildFullScreenMode(RoleNavigationConfig config) {
    return Scaffold(
      backgroundColor: AppTheme.backgroundDarkOps,
      body: Stack(
        children: [
          // Full screen content - no padding, no decoration
          Positioned.fill(
            child: widget.child,
          ),
          
          // Back button overlay (top left)
          Positioned(
            top: MediaQuery.of(context).padding.top + 12,
            left: 12,
            child: _buildBackButton(config),
          ),
        ],
      ),
    );
  }

  Widget _buildBackButton(RoleNavigationConfig config) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          // Exit full screen mode
          ref.read(fullScreenModeProvider.notifier).state = false;
          ref.read(currentEmbeddedRouteProvider.notifier).state = null;
          
          // Get the previous route or calculate default
          final previousRoute = ref.read(previousRouteProvider);
          
          // Go to default route for this role (sidebar first item or home)
          final defaultRoute = config.sections.isNotEmpty 
            ? config.sections.first.items.first.route 
            : (config.bottomNav.isNotEmpty ? config.bottomNav.first.route : '/');
          
          // Navigate to previous or default
          final targetRoute = previousRoute ?? defaultRoute;
          context.go(targetRoute);
        },
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E1E).withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white24),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.3),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: const Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.arrow_back, color: Colors.white, size: 18),
              SizedBox(width: 6),
              Text(
                'Back',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // WAR ROOM MODE (R3+) - Single sidebar, content fills rest
  // ═══════════════════════════════════════════════════════════════════════════

  Widget _buildWarRoomShell(RoleNavigationConfig config, RBACState rbacState) {
    return Scaffold(
      backgroundColor: AppTheme.backgroundDarkOps,
      body: Row(
        children: [
          // SINGLE Sidebar - Flutter navigation only
          AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            width: _sidebarExpanded ? 260 : 72,
            child: _buildSidebar(config, rbacState),
          ),
          // Main Content - fills the rest, no extra bars
          Expanded(
            child: widget.child,
          ),
        ],
      ),
    );
  }

  Widget _buildSidebar(RoleNavigationConfig config, RBACState rbacState) {
    return Container(
      color: const Color(0xFF0D1117),
      child: Column(
        children: [
          // Logo Section
          _buildSidebarHeader(config),
          const Divider(color: Colors.white10, height: 1),
          
          // Navigation Sections - ONLY for this role
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                for (final section in config.sections)
                  _buildSection(section, config),
              ],
            ),
          ),
          
          // Sidebar Toggle
          const Divider(color: Colors.white10, height: 1),
          _buildSidebarToggle(),
          
          // User Profile
          const Divider(color: Colors.white10, height: 1),
          _buildUserProfile(rbacState, config),
        ],
      ),
    );
  }

  Widget _buildSidebarHeader(RoleNavigationConfig config) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: config.accentColor,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Icon(Icons.shield, color: Colors.white, size: 24),
          ),
          if (_sidebarExpanded) ...[
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    config.shellTitle,
                    style: TextStyle(
                      color: AppTheme.textPrimary,
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                    ),
                  ),
                  Container(
                    margin: const EdgeInsets.only(top: 4),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: config.accentColor.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      config.shellSubtitle,
                      style: TextStyle(
                        color: config.accentColor,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSection(RoleNavSection section, RoleNavigationConfig config) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (_sidebarExpanded)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            child: Text(
              section.title,
              style: TextStyle(
                color: AppTheme.textSecondary,
                fontSize: 11,
                fontWeight: FontWeight.w600,
                letterSpacing: 1,
              ),
            ),
          ),
        ...section.items.map((item) => _buildNavItem(item, config)),
      ],
    );
  }

  Widget _buildNavItem(RoleNavItem item, RoleNavigationConfig config) {
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
              _navigateToRoute(item);
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
                ? config.accentColor.withValues(alpha: 0.15)
                : Colors.transparent,
              borderRadius: BorderRadius.circular(8),
              border: isSelected 
                ? Border.all(color: config.accentColor.withValues(alpha: 0.3))
                : null,
            ),
            child: Row(
              children: [
                Icon(
                  item.icon,
                  color: isSelected ? config.accentColor : AppTheme.textLight,
                  size: 20,
                ),
                if (_sidebarExpanded) ...[
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      item.label,
                      style: TextStyle(
                        color: isSelected ? AppTheme.textPrimary : AppTheme.mediumAsh,
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
                  if (item.isEmbedded)
                    Padding(
                      padding: const EdgeInsets.only(left: 4),
                      child: Icon(
                        Icons.open_in_new,
                        color: AppTheme.textSecondary,
                        size: 12,
                      ),
                    ),
                  if (hasChildren)
                    Icon(
                      isExpanded ? Icons.keyboard_arrow_down : Icons.keyboard_arrow_right,
                      color: AppTheme.textSecondary,
                      size: 18,
                    ),
                ],
              ],
            ),
          ),
        ),
        // Children
        if (hasChildren && isExpanded && _sidebarExpanded)
          Padding(
            padding: const EdgeInsets.only(left: 20),
            child: Column(
              children: item.children.map((child) => _buildNavItem(child, config)).toList(),
            ),
          ),
      ],
    );
  }

  void _navigateToRoute(RoleNavItem item) {
    // Store current route as previous before navigating
    if (widget.currentRoute != null && widget.currentRoute != item.route) {
      ref.read(previousRouteProvider.notifier).state = widget.currentRoute;
    }
    
    // Get current role to decide if full screen mode applies
    final rbacState = ref.read(rbacProvider);
    final role = rbacState.role;
    final isEndUser = role == Role.r1EndUser || role == Role.r2EndUserPep;
    
    if (item.isEmbedded) {
      // Only R1/R2 users go to full screen mode for embedded pages
      // R3+ users keep the sidebar visible
      if (isEndUser) {
        ref.read(fullScreenModeProvider.notifier).state = true;
      }
      ref.read(currentEmbeddedRouteProvider.notifier).state = item.route;
    } else {
      // Ensure we exit embedded mode when navigating to native pages
      ref.read(fullScreenModeProvider.notifier).state = false;
      ref.read(currentEmbeddedRouteProvider.notifier).state = null;
    }
    context.go(item.route);
  }

  Widget _buildSidebarToggle() {
    return InkWell(
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
              _sidebarExpanded ? Icons.chevron_left : Icons.chevron_right,
              color: AppTheme.textSecondary,
              size: 20,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildUserProfile(RBACState rbacState, RoleNavigationConfig config) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: config.accentColor,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Center(
              child: Text(
                rbacState.displayName.isNotEmpty 
                  ? rbacState.displayName[0].toUpperCase()
                  : 'U',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
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
                    rbacState.displayName.isNotEmpty ? rbacState.displayName : 'User',
                    style: TextStyle(
                      color: AppTheme.textPrimary,
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  Text(
                    rbacState.role.displayName,
                    style: TextStyle(
                      color: config.accentColor,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              icon: Icon(Icons.logout, color: AppTheme.textSecondary, size: 18),
              onPressed: () => ref.read(rbacProvider.notifier).logout(),
              tooltip: 'Logout',
            ),
          ],
        ],
      ),
    );
  }
}
