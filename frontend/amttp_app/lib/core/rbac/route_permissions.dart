/// Route Permissions Configuration
/// 
/// Single source of truth for route-role access mapping.
/// This file defines which user roles can access each route.
/// 
/// Roles (from RBAC system):
/// - R1: End User (Basic)
/// - R2: Power User  
/// - R3: Institution Ops
/// - R4: Institution Compliance
/// - R5: Platform Admin
/// - R6: Super Admin
///
/// Route Types:
/// - native: Flutter-native page
/// - embedded: Next.js page embedded via iframe
/// - external: Opens in external browser

import 'package:flutter/material.dart';

/// User role levels (matches existing RBAC)
enum UserRole {
  R1_END_USER,
  R2_POWER_USER,
  R3_INSTITUTION_OPS,
  R4_INSTITUTION_COMPLIANCE,
  R5_PLATFORM_ADMIN,
  R6_SUPER_ADMIN,
}

/// Route implementation type
enum RouteType {
  native,    // Flutter-native page
  embedded,  // Next.js embedded via iframe
  external,  // Opens in browser
}

/// Route permission definition
class RoutePermission {
  final String path;
  final String label;
  final IconData icon;
  final List<UserRole> allowedRoles;
  final RouteType type;
  final String? nextJsPath;  // For embedded routes
  final String? description;
  final bool showInNav;  // Whether to show in navigation menus

  const RoutePermission({
    required this.path,
    required this.label,
    required this.icon,
    required this.allowedRoles,
    this.type = RouteType.native,
    this.nextJsPath,
    this.description,
    this.showInNav = true,
  });

  /// Check if a role has access to this route
  bool hasAccess(UserRole role) => allowedRoles.contains(role);
  
  /// Check if role level is sufficient (R6 can access everything R1 can)
  bool hasAccessByLevel(UserRole role) {
    final roleIndex = UserRole.values.indexOf(role);
    return allowedRoles.any((allowed) => 
      UserRole.values.indexOf(allowed) <= roleIndex
    );
  }
}

/// ═══════════════════════════════════════════════════════════════════════════════
/// ROUTE PERMISSIONS REGISTRY
/// ═══════════════════════════════════════════════════════════════════════════════

class RoutePermissions {
  RoutePermissions._();

  // ─────────────────────────────────────────────────────────────────────────────
  // END USER ROUTES (R1+)
  // Basic financial operations available to all users
  // ─────────────────────────────────────────────────────────────────────────────

  static const home = RoutePermission(
    path: '/',
    label: 'Home',
    icon: Icons.home_rounded,
    allowedRoles: UserRole.values, // All roles
    description: 'Dashboard home',
  );

  static const wallet = RoutePermission(
    path: '/wallet',
    label: 'Wallet',
    icon: Icons.account_balance_wallet_rounded,
    allowedRoles: UserRole.values,
    description: 'View wallet balance and tokens',
  );

  static const transfer = RoutePermission(
    path: '/transfer',
    label: 'Transfer',
    icon: Icons.send_rounded,
    allowedRoles: UserRole.values,
    description: 'Send funds securely',
  );

  static const history = RoutePermission(
    path: '/history',
    label: 'History',
    icon: Icons.history_rounded,
    allowedRoles: UserRole.values,
    description: 'Transaction history',
  );

  static const settings = RoutePermission(
    path: '/settings',
    label: 'Settings',
    icon: Icons.settings_rounded,
    allowedRoles: UserRole.values,
    description: 'App settings and preferences',
  );

  // ─────────────────────────────────────────────────────────────────────────────
  // POWER USER ROUTES (R2+)
  // Advanced features for experienced users
  // ─────────────────────────────────────────────────────────────────────────────

  static const nftSwap = RoutePermission(
    path: '/nft-swap',
    label: 'NFT Swap',
    icon: Icons.swap_horiz_rounded,
    allowedRoles: [
      UserRole.R2_POWER_USER,
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Swap NFTs with escrow protection',
  );

  static const crossChain = RoutePermission(
    path: '/cross-chain',
    label: 'Cross-Chain',
    icon: Icons.link_rounded,
    allowedRoles: [
      UserRole.R2_POWER_USER,
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Cross-chain transfers',
  );

  static const disputes = RoutePermission(
    path: '/disputes',
    label: 'Disputes',
    icon: Icons.gavel_rounded,
    allowedRoles: [
      UserRole.R2_POWER_USER,
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'View and manage disputes',
  );

  static const sessionKeys = RoutePermission(
    path: '/session-keys',
    label: 'Session Keys',
    icon: Icons.key_rounded,
    allowedRoles: [
      UserRole.R2_POWER_USER,
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Manage session keys (ERC-4337)',
  );

  static const safe = RoutePermission(
    path: '/safe',
    label: 'Safe',
    icon: Icons.security_rounded,
    allowedRoles: [
      UserRole.R2_POWER_USER,
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Gnosis Safe management',
  );

  // ─────────────────────────────────────────────────────────────────────────────
  // INSTITUTION OPS ROUTES (R3+)
  // Operational tools for institutions
  // ─────────────────────────────────────────────────────────────────────────────

  static const approver = RoutePermission(
    path: '/approver',
    label: 'Approver Portal',
    icon: Icons.check_circle_rounded,
    allowedRoles: [
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Approve/reject pending transactions',
  );

  static const detectionStudio = RoutePermission(
    path: '/detection-studio',
    label: 'Detection Studio',
    icon: Icons.analytics_rounded,
    allowedRoles: [
      UserRole.R3_INSTITUTION_OPS,
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    type: RouteType.embedded,
    nextJsPath: '/war-room/detection-studio',
    description: 'Visual fraud detection tools',
  );

  // ─────────────────────────────────────────────────────────────────────────────
  // COMPLIANCE ROUTES (R4+)
  // Compliance and regulatory tools
  // ─────────────────────────────────────────────────────────────────────────────

  static const compliance = RoutePermission(
    path: '/compliance',
    label: 'Compliance',
    icon: Icons.policy_rounded,
    allowedRoles: [
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Compliance tools and checks',
  );

  static const fatfRules = RoutePermission(
    path: '/fatf-rules',
    label: 'FATF Rules',
    icon: Icons.public_rounded,
    allowedRoles: [
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'FATF country risk and rules',
  );

  static const warRoom = RoutePermission(
    path: '/war-room',
    label: 'War Room',
    icon: Icons.dashboard_rounded,
    allowedRoles: [
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    type: RouteType.embedded,
    nextJsPath: '/war-room',
    description: 'Full institutional dashboard',
  );

  static const sanctions = RoutePermission(
    path: '/sanctions',
    label: 'Sanctions Check',
    icon: Icons.block_rounded,
    allowedRoles: [
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    type: RouteType.embedded,
    nextJsPath: '/compliance/sanctions',
    description: 'Sanctions screening',
  );

  static const complianceAlerts = RoutePermission(
    path: '/compliance-alerts',
    label: 'Compliance Alerts',
    icon: Icons.notifications_active_rounded,
    allowedRoles: [
      UserRole.R4_INSTITUTION_COMPLIANCE,
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    type: RouteType.embedded,
    nextJsPath: '/compliance/alerts',
    description: 'Real-time compliance alerts',
  );

  // ─────────────────────────────────────────────────────────────────────────────
  // ADMIN ROUTES (R5+)
  // Platform administration
  // ─────────────────────────────────────────────────────────────────────────────

  static const admin = RoutePermission(
    path: '/admin',
    label: 'Admin',
    icon: Icons.admin_panel_settings_rounded,
    allowedRoles: [
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Admin dashboard with DQN analytics',
  );

  static const audit = RoutePermission(
    path: '/audit',
    label: 'Audit',
    icon: Icons.verified_rounded,
    allowedRoles: [
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Audit chain replay tool',
  );

  static const zknaf = RoutePermission(
    path: '/zknaf',
    label: 'zkNAF',
    icon: Icons.verified_user_rounded,
    allowedRoles: [
      UserRole.R5_PLATFORM_ADMIN,
      UserRole.R6_SUPER_ADMIN,
    ],
    description: 'Zero-Knowledge attestations',
  );

  // ─────────────────────────────────────────────────────────────────────────────
  // SUPER ADMIN ROUTES (R6 only)
  // System-level controls
  // ─────────────────────────────────────────────────────────────────────────────

  static const mlModels = RoutePermission(
    path: '/ml-models',
    label: 'ML Models',
    icon: Icons.psychology_rounded,
    allowedRoles: [UserRole.R6_SUPER_ADMIN],
    type: RouteType.embedded,
    nextJsPath: '/war-room/detection/models',
    description: 'ML model configuration (pause/retrain)',
  );

  static const roleManagement = RoutePermission(
    path: '/role-management',
    label: 'Role Management',
    icon: Icons.manage_accounts_rounded,
    allowedRoles: [UserRole.R6_SUPER_ADMIN],
    type: RouteType.embedded,
    nextJsPath: '/war-room/admin/roles',
    description: 'Manage user roles',
  );

  // ═══════════════════════════════════════════════════════════════════════════════
  // ROUTE LISTS BY PROFILE
  // ═══════════════════════════════════════════════════════════════════════════════

  /// All routes
  static const List<RoutePermission> allRoutes = [
    home, wallet, transfer, history, settings,
    nftSwap, crossChain, disputes, sessionKeys, safe,
    approver, detectionStudio,
    compliance, fatfRules, warRoom, sanctions, complianceAlerts,
    admin, audit, zknaf,
    mlModels, roleManagement,
  ];

  /// Get routes accessible by a specific role
  static List<RoutePermission> getRoutesForRole(UserRole role) {
    return allRoutes.where((r) => r.hasAccess(role) && r.showInNav).toList();
  }

  /// Get routes for navigation display (by role)
  static List<RoutePermission> getNavRoutes(UserRole role) {
    return allRoutes.where((r) => r.hasAccess(role) && r.showInNav).toList();
  }

  /// Check if a path is accessible by role
  static bool canAccess(String path, UserRole role) {
    final route = allRoutes.firstWhere(
      (r) => r.path == path,
      orElse: () => home, // Default to home if not found
    );
    return route.hasAccess(role);
  }

  /// Get route by path
  static RoutePermission? getRoute(String path) {
    try {
      return allRoutes.firstWhere((r) => r.path == path);
    } catch (_) {
      return null;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════════
  // PROFILE-BASED NAVIGATION GROUPS
  // ═══════════════════════════════════════════════════════════════════════════════

  /// End User navigation (Focus Mode)
  static const List<RoutePermission> endUserNav = [
    home, wallet, transfer, history, settings,
  ];

  /// Power User additions
  static const List<RoutePermission> powerUserNav = [
    nftSwap, crossChain, disputes, sessionKeys, safe,
  ];

  /// Institution Ops additions  
  static const List<RoutePermission> institutionOpsNav = [
    approver, detectionStudio,
  ];

  /// Compliance additions
  static const List<RoutePermission> complianceNav = [
    compliance, fatfRules, warRoom, sanctions, complianceAlerts,
  ];

  /// Admin additions
  static const List<RoutePermission> adminNav = [
    admin, audit, zknaf,
  ];

  /// Super Admin additions
  static const List<RoutePermission> superAdminNav = [
    mlModels, roleManagement,
  ];
}
