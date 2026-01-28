/// Mode-Aware Navigation Shell
/// 
/// Implements the Ground Truth specification for Focus Mode vs War Room Mode
/// Based on AMTTP UI/UX Ground Truth v2.3
/// 
/// Focus Mode (R1/R2): Simplified interface for end users
/// War Room Mode (R3+): Full analytics dashboard for institutional users

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../rbac/roles.dart';
import '../rbac/rbac_provider.dart';
import '../theme/app_theme.dart';
import 'focus_mode_shell.dart';
import 'war_room_shell.dart';

/// Main navigation shell that switches between Focus and War Room modes
class ModeAwareShell extends ConsumerWidget {
  final Widget child;

  const ModeAwareShell({super.key, required this.child});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rbacState = ref.watch(rbacProvider);
    
    // Route to appropriate shell based on mode
    if (rbacState.isFocusMode) {
      return FocusModeShell(child: child);
    } else {
      return WarRoomShell(child: child);
    }
  }
}

/// Navigation items for Focus Mode (R1/R2 End Users)
/// Per Ground Truth: "No charts, no risk scores, no enforcement controls"
class FocusModeNavigation {
  static const List<NavItem> items = [
    NavItem(
      title: 'Home',
      route: '/',
      icon: Icons.home_outlined,
      activeIcon: Icons.home,
    ),
    NavItem(
      title: 'Wallet',
      route: '/wallet',
      icon: Icons.account_balance_wallet_outlined,
      activeIcon: Icons.account_balance_wallet,
    ),
    NavItem(
      title: 'Transfer',
      route: '/transfer',
      icon: Icons.swap_horiz_outlined,
      activeIcon: Icons.swap_horiz,
    ),
    NavItem(
      title: 'History',
      route: '/history',
      icon: Icons.history_outlined,
      activeIcon: Icons.history,
    ),
    NavItem(
      title: 'Disputes',
      route: '/disputes',
      icon: Icons.gavel_outlined,
      activeIcon: Icons.gavel,
    ),
    NavItem(
      title: 'Settings',
      route: '/settings',
      icon: Icons.settings_outlined,
      activeIcon: Icons.settings,
    ),
  ];
}

/// Navigation items for War Room Mode (R3+ Institutional Users)
/// Per Ground Truth: Tabbed interface with one active view at a time
class WarRoomNavigation {
  static const List<NavSection> sections = [
    // Overview Section
    NavSection(
      title: 'OVERVIEW',
      items: [
        NavItem(
          title: 'Active Investigations',
          route: '/war-room',
          icon: Icons.dashboard_outlined,
          activeIcon: Icons.dashboard,
        ),
      ],
    ),
    // Detection Studio (R3 Ops - Read Only)
    NavSection(
      title: 'DETECTION STUDIO',
      items: [
        NavItem(
          title: 'Flagged Queue',
          route: '/war-room/queue',
          icon: Icons.flag_outlined,
          activeIcon: Icons.flag,
        ),
        NavItem(
          title: 'Graph Explorer',
          route: '/war-room/graph',
          icon: Icons.hub_outlined,
          activeIcon: Icons.hub,
        ),
        NavItem(
          title: 'Velocity Heatmap',
          route: '/war-room/heatmap',
          icon: Icons.grid_on_outlined,
          activeIcon: Icons.grid_on,
        ),
        NavItem(
          title: 'Value Flow (Sankey)',
          route: '/war-room/sankey',
          icon: Icons.account_tree_outlined,
          activeIcon: Icons.account_tree,
        ),
        NavItem(
          title: 'ML Explainability',
          route: '/war-room/ml',
          icon: Icons.psychology_outlined,
          activeIcon: Icons.psychology,
        ),
      ],
    ),
    // Compliance Studio (R4 - Can Enforce with Multisig)
    NavSection(
      title: 'COMPLIANCE STUDIO',
      requiredRole: Role.r4InstitutionCompliance,
      items: [
        NavItem(
          title: 'Policy Engine',
          route: '/war-room/policies',
          icon: Icons.policy_outlined,
          activeIcon: Icons.policy,
        ),
        NavItem(
          title: 'Enforcement Actions',
          route: '/war-room/enforcement',
          icon: Icons.security_outlined,
          activeIcon: Icons.security,
        ),
      ],
    ),
    // Governance (R4+ Multisig)
    NavSection(
      title: 'GOVERNANCE',
      requiredRole: Role.r4InstitutionCompliance,
      items: [
        NavItem(
          title: 'Multisig Queue',
          route: '/war-room/multisig',
          icon: Icons.how_to_vote_outlined,
          activeIcon: Icons.how_to_vote,
        ),
        NavItem(
          title: 'Pending Approvals',
          route: '/war-room/approvals',
          icon: Icons.pending_actions_outlined,
          activeIcon: Icons.pending_actions,
        ),
      ],
    ),
    // Audit & Reports
    NavSection(
      title: 'AUDIT',
      items: [
        NavItem(
          title: 'UI Snapshots',
          route: '/war-room/snapshots',
          icon: Icons.camera_alt_outlined,
          activeIcon: Icons.camera_alt,
        ),
        NavItem(
          title: 'Audit Chain',
          route: '/war-room/audit',
          icon: Icons.link_outlined,
          activeIcon: Icons.link,
        ),
        NavItem(
          title: 'Reports',
          route: '/war-room/reports',
          icon: Icons.assessment_outlined,
          activeIcon: Icons.assessment,
        ),
      ],
    ),
    // Admin (R5+)
    NavSection(
      title: 'ADMINISTRATION',
      requiredRole: Role.r5PlatformAdmin,
      items: [
        NavItem(
          title: 'User Management',
          route: '/war-room/users',
          icon: Icons.people_outlined,
          activeIcon: Icons.people,
        ),
        NavItem(
          title: 'System Settings',
          route: '/war-room/system',
          icon: Icons.settings_outlined,
          activeIcon: Icons.settings,
        ),
      ],
    ),
  ];
  
  /// Get navigation items filtered by role
  static List<NavSection> getForRole(Role role) {
    return sections.where((section) {
      if (section.requiredRole == null) return true;
      return role.isAtLeast(section.requiredRole!);
    }).toList();
  }
}

/// Navigation item model
class NavItem {
  final String title;
  final String route;
  final IconData icon;
  final IconData activeIcon;
  final String? badge;
  
  const NavItem({
    required this.title,
    required this.route,
    required this.icon,
    required this.activeIcon,
    this.badge,
  });
}

/// Navigation section model (for War Room grouped nav)
class NavSection {
  final String title;
  final List<NavItem> items;
  final Role? requiredRole;
  
  const NavSection({
    required this.title,
    required this.items,
    this.requiredRole,
  });
}
