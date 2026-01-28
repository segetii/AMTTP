/// RBAC Navigation - Role-based navigation items
/// 
/// Defines navigation structure for each app mode:
/// - Focus Mode: Simple navigation for end users (R1, R2)
/// - War Room Mode: Full analytics for institutional users (R3+)

import 'package:flutter/material.dart';
import 'roles.dart';

/// Navigation item definition
class NavItem {
  final String id;
  final String title;
  final String route;
  final IconData icon;
  final String? badge;
  final List<NavItem> children;
  final int minRoleLevel;
  final bool requiresMultisig;
  final String? capability; // Required capability to access

  const NavItem({
    required this.id,
    required this.title,
    required this.route,
    required this.icon,
    this.badge,
    this.children = const [],
    this.minRoleLevel = 1,
    this.requiresMultisig = false,
    this.capability,
  });

  /// Check if a role can access this item
  bool canAccess(Role role) {
    if (role.level < minRoleLevel) return false;
    if (capability != null && !canPerform(role, capability!)) return false;
    return true;
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// FOCUS MODE NAVIGATION (R1, R2)
// ═══════════════════════════════════════════════════════════════════════════════

const List<NavItem> focusModeNavItems = [
  NavItem(
    id: 'home',
    title: 'Home',
    route: '/',
    icon: Icons.home_rounded,
  ),
  NavItem(
    id: 'wallet',
    title: 'Wallet',
    route: '/wallet',
    icon: Icons.account_balance_wallet_rounded,
  ),
  NavItem(
    id: 'transfer',
    title: 'Send',
    route: '/transfer',
    icon: Icons.send_rounded,
  ),
  NavItem(
    id: 'history',
    title: 'History',
    route: '/history',
    icon: Icons.history_rounded,
  ),
  NavItem(
    id: 'trust',
    title: 'Trust',
    route: '/trust',
    icon: Icons.verified_user_rounded,
  ),
];

// Bottom nav for Focus Mode
const List<NavItem> focusModeBottomNav = [
  NavItem(id: 'home', title: 'Home', route: '/', icon: Icons.home_rounded),
  NavItem(id: 'wallet', title: 'Wallet', route: '/wallet', icon: Icons.account_balance_wallet_rounded),
  NavItem(id: 'transfer', title: 'Send', route: '/transfer', icon: Icons.send_rounded),
  NavItem(id: 'history', title: 'History', route: '/history', icon: Icons.history_rounded),
  NavItem(id: 'profile', title: 'Profile', route: '/profile', icon: Icons.person_rounded),
];

// ═══════════════════════════════════════════════════════════════════════════════
// WAR ROOM MODE NAVIGATION (R3+)
// ═══════════════════════════════════════════════════════════════════════════════

const List<NavItem> warRoomNavItems = [
  // Overview
  NavItem(
    id: 'dashboard',
    title: 'Dashboard',
    route: '/war-room',
    icon: Icons.dashboard_rounded,
    minRoleLevel: 3,
  ),
  
  // Detection & Analytics
  NavItem(
    id: 'detection',
    title: 'Detection Studio',
    route: '/war-room/detection-studio',
    icon: Icons.psychology_rounded,
    minRoleLevel: 3,
    capability: 'detection_studio',
    children: [
      NavItem(
        id: 'graph-explorer',
        title: 'Graph Explorer',
        route: '/war-room/detection-studio/graph',
        icon: Icons.account_tree_rounded,
        minRoleLevel: 3,
      ),
      NavItem(
        id: 'velocity-heatmap',
        title: 'Velocity Heatmap',
        route: '/war-room/detection-studio/heatmap',
        icon: Icons.grid_on_rounded,
        minRoleLevel: 3,
      ),
      NavItem(
        id: 'sankey-flow',
        title: 'Flow Analysis',
        route: '/war-room/detection-studio/sankey',
        icon: Icons.waterfall_chart_rounded,
        minRoleLevel: 3,
      ),
    ],
  ),
  
  // Flagged Queue
  NavItem(
    id: 'flagged',
    title: 'Flagged Queue',
    route: '/war-room/flagged',
    icon: Icons.flag_rounded,
    badge: '12',
    minRoleLevel: 3,
  ),
  
  // Compliance (R4+)
  NavItem(
    id: 'compliance',
    title: 'Compliance',
    route: '/war-room/compliance',
    icon: Icons.policy_rounded,
    minRoleLevel: 4,
    capability: 'compliance',
    children: [
      NavItem(
        id: 'policies',
        title: 'Policy Engine',
        route: '/war-room/compliance/policies',
        icon: Icons.rule_rounded,
        minRoleLevel: 4,
      ),
      NavItem(
        id: 'enforcement',
        title: 'Enforcement',
        route: '/war-room/compliance/enforcement',
        icon: Icons.gavel_rounded,
        minRoleLevel: 4,
        capability: 'enforce_actions',
        requiresMultisig: true,
      ),
      NavItem(
        id: 'reports',
        title: 'Reports',
        route: '/war-room/compliance/reports',
        icon: Icons.assessment_rounded,
        minRoleLevel: 4,
        capability: 'export_reports',
      ),
    ],
  ),
  
  // Multisig Governance (R4+)
  NavItem(
    id: 'multisig',
    title: 'Multisig Queue',
    route: '/war-room/multisig',
    icon: Icons.how_to_vote_rounded,
    badge: '3',
    minRoleLevel: 4,
    capability: 'sign_multisig',
  ),
  
  // Audit Trail
  NavItem(
    id: 'audit',
    title: 'Audit Trail',
    route: '/war-room/audit',
    icon: Icons.history_edu_rounded,
    minRoleLevel: 3,
  ),
  
  // User Management (R5+)
  NavItem(
    id: 'users',
    title: 'User Management',
    route: '/war-room/admin/users',
    icon: Icons.people_rounded,
    minRoleLevel: 5,
    capability: 'manage_users',
  ),
  
  // System Settings (R5+)
  NavItem(
    id: 'system',
    title: 'System',
    route: '/war-room/admin/system',
    icon: Icons.settings_applications_rounded,
    minRoleLevel: 5,
    children: [
      NavItem(
        id: 'config',
        title: 'Configuration',
        route: '/war-room/admin/system/config',
        icon: Icons.tune_rounded,
        minRoleLevel: 5,
      ),
      NavItem(
        id: 'integrations',
        title: 'Integrations',
        route: '/war-room/admin/system/integrations',
        icon: Icons.extension_rounded,
        minRoleLevel: 5,
      ),
    ],
  ),
  
  // Emergency Controls (R6 only)
  NavItem(
    id: 'emergency',
    title: 'Emergency',
    route: '/war-room/emergency',
    icon: Icons.emergency_rounded,
    minRoleLevel: 6,
    capability: 'emergency_override',
  ),
];

// Sidebar sections for War Room
const List<String> warRoomSections = [
  'MONITORING',   // dashboard, detection, flagged
  'COMPLIANCE',   // compliance, multisig, audit
  'ADMIN',        // users, system, emergency
];

/// Get nav items for a specific section
List<NavItem> getWarRoomSection(String section) {
  switch (section) {
    case 'MONITORING':
      return warRoomNavItems.where((i) => 
        ['dashboard', 'detection', 'flagged'].contains(i.id)
      ).toList();
    case 'COMPLIANCE':
      return warRoomNavItems.where((i) => 
        ['compliance', 'multisig', 'audit'].contains(i.id)
      ).toList();
    case 'ADMIN':
      return warRoomNavItems.where((i) => 
        ['users', 'system', 'emergency'].contains(i.id)
      ).toList();
    default:
      return [];
  }
}

/// Filter nav items based on role
List<NavItem> filterNavItemsForRole(List<NavItem> items, Role role) {
  return items
    .where((item) => item.canAccess(role))
    .map((item) => NavItem(
      id: item.id,
      title: item.title,
      route: item.route,
      icon: item.icon,
      badge: item.badge,
      minRoleLevel: item.minRoleLevel,
      requiresMultisig: item.requiresMultisig,
      capability: item.capability,
      children: filterNavItemsForRole(item.children, role),
    ))
    .toList();
}

/// Get navigation items for current mode and role
List<NavItem> getNavItemsForRole(Role role, AppMode mode) {
  if (mode == AppMode.focusMode) {
    return focusModeNavItems;
  } else {
    return filterNavItemsForRole(warRoomNavItems, role);
  }
}
