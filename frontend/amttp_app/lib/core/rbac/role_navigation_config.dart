/// Role Navigation Configuration
/// 
/// CLEAN ARCHITECTURE: Each role has its own navigation config.
/// Pages are ONLY loaded for the authorized role - no hiding, no filtering.
/// 
/// This replaces the old approach of loading everything and filtering.
library;

import 'package:flutter/material.dart';
import 'roles.dart';

/// Navigation item for role-specific menus
class RoleNavItem {
  final String id;
  final String label;
  final String route;
  final IconData icon;
  final String? badge;
  final List<RoleNavItem> children;
  final bool isEmbedded; // True if it's a Next.js embedded page

  const RoleNavItem({
    required this.id,
    required this.label,
    required this.route,
    required this.icon,
    this.badge,
    this.children = const [],
    this.isEmbedded = false,
  });
}

/// Navigation section grouping
class RoleNavSection {
  final String title;
  final List<RoleNavItem> items;

  const RoleNavSection({
    required this.title,
    required this.items,
  });
}

/// Complete navigation config for a role
class RoleNavigationConfig {
  final Role role;
  final String shellTitle;
  final String shellSubtitle;
  final List<RoleNavSection> sections;
  final List<RoleNavItem> bottomNav;
  final List<RoleNavItem> quickActions;
  final Color accentColor;
  final List<String> extraRoutes; // Non-nav routes that are still allowed (details, read-only, etc.)

  const RoleNavigationConfig({
    required this.role,
    required this.shellTitle,
    required this.shellSubtitle,
    required this.sections,
    required this.bottomNav,
    required this.quickActions,
    required this.accentColor,
    this.extraRoutes = const [],
  });

  /// Get all routes this role can access
  List<String> get allRoutes {
    final routes = <String>{};
    void addNavItem(RoleNavItem item) {
      routes.add(item.route);
      for (final child in item.children) {
        routes.add(child.route);
      }
    }

    for (final section in sections) {
      for (final item in section.items) {
        addNavItem(item);
      }
    }

    for (final item in bottomNav) {
      addNavItem(item);
    }

    for (final item in quickActions) {
      addNavItem(item);
    }

    routes.addAll(extraRoutes);

    return routes.toList();
  }

  /// Check if a route is accessible
  bool canAccess(String route) => allRoutes.any((allowed) => _routeMatches(allowed, route));
}

// ═══════════════════════════════════════════════════════════════════════════════
// R1: END USER CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r1EndUserConfig = RoleNavigationConfig(
  role: Role.r1EndUser,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Secure Transfers',
  accentColor: Color(0xFF4CAF50), // Green
  sections: [],  // No sidebar sections - uses bottom nav only
  bottomNav: [
    RoleNavItem(id: 'home', label: 'Home', route: '/', icon: Icons.home_rounded),
    RoleNavItem(id: 'wallet', label: 'Wallet', route: '/wallet', icon: Icons.account_balance_wallet_rounded),
    RoleNavItem(id: 'transfer', label: 'Send', route: '/transfer', icon: Icons.send_rounded),
    RoleNavItem(id: 'history', label: 'History', route: '/history', icon: Icons.history_rounded),
    RoleNavItem(id: 'profile', label: 'Profile', route: '/profile', icon: Icons.person_rounded),
  ],
  quickActions: [
    RoleNavItem(id: 'send', label: 'Send', route: '/transfer', icon: Icons.send_rounded),
    RoleNavItem(id: 'trust-check', label: 'Trust Check', route: '/trust-check', icon: Icons.verified_rounded),
  ],
  extraRoutes: [
    '/trust-check',
    '/disputes',
    '/dispute/:id',
    '/settings',
    '/profile',
    '/more',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// R2: POWER USER CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r2PowerUserConfig = RoleNavigationConfig(
  role: Role.r2EndUserPep,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Power User',
  accentColor: Color(0xFF2196F3), // Blue
  sections: [], // Uses bottom nav primarily
  bottomNav: [
    RoleNavItem(id: 'home', label: 'Home', route: '/', icon: Icons.home_rounded),
    RoleNavItem(id: 'wallet', label: 'Wallet', route: '/wallet', icon: Icons.account_balance_wallet_rounded),
    RoleNavItem(id: 'transfer', label: 'Send', route: '/transfer', icon: Icons.send_rounded),
    RoleNavItem(id: 'history', label: 'History', route: '/history', icon: Icons.history_rounded),
    RoleNavItem(id: 'more', label: 'More', route: '/more', icon: Icons.more_horiz_rounded),
  ],
  quickActions: [
    RoleNavItem(id: 'send', label: 'Send', route: '/transfer', icon: Icons.send_rounded),
    RoleNavItem(id: 'nft-swap', label: 'NFT Swap', route: '/nft-swap', icon: Icons.swap_horizontal_circle_rounded),
    RoleNavItem(id: 'cross-chain', label: 'Bridge', route: '/cross-chain', icon: Icons.link_rounded),
    RoleNavItem(id: 'disputes', label: 'Disputes', route: '/disputes', icon: Icons.gavel_rounded),
    RoleNavItem(id: 'trust-check', label: 'Trust Check', route: '/trust-check', icon: Icons.verified_rounded),
  ],
  extraRoutes: [
    '/trust-check',
    '/disputes',
    '/dispute/:id',
    '/zknaf',
    '/safe',
    '/session-keys',
    '/cross-chain',
    '/nft-swap',
    '/settings',
    '/profile',
    '/more',
    '/approver',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// R3: INSTITUTION OPS CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r3InstitutionOpsConfig = RoleNavigationConfig(
  role: Role.r3InstitutionOps,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Operations',
  accentColor: Color(0xFF9C27B0), // Purple
  sections: [
    RoleNavSection(
      title: 'MONITORING',
      items: [
        RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded, isEmbedded: true),
        RoleNavItem(id: 'alerts', label: 'Alerts', route: '/war-room/alerts', icon: Icons.notification_important_rounded, isEmbedded: true),
        RoleNavItem(id: 'flagged', label: 'Flagged Queue', route: '/flagged-queue', icon: Icons.flag_rounded),
        RoleNavItem(id: 'transactions', label: 'Transactions', route: '/war-room/transactions', icon: Icons.swap_horiz_rounded, isEmbedded: true),
        RoleNavItem(id: 'cross-chain', label: 'Cross-Chain', route: '/war-room/cross-chain', icon: Icons.device_hub_rounded, isEmbedded: true),
        RoleNavItem(id: 'detection', label: 'Detection Studio', route: '/detection-studio', icon: Icons.psychology_rounded, isEmbedded: true),
        RoleNavItem(id: 'graph', label: 'Graph Explorer', route: '/graph-explorer', icon: Icons.account_tree_rounded, isEmbedded: true),
        RoleNavItem(id: 'risk', label: 'Risk Scoring', route: '/war-room/detection/risk', icon: Icons.assessment_rounded, isEmbedded: true),
      ],
    ),
    RoleNavSection(
      title: 'OPERATIONS',
      items: [
        RoleNavItem(id: 'compliance', label: 'Compliance', route: '/compliance', icon: Icons.shield_rounded),
        RoleNavItem(id: 'disputes', label: 'Disputes', route: '/disputes', icon: Icons.gavel_rounded),
        RoleNavItem(id: 'pending', label: 'Pending Approvals', route: '/pending-approvals', icon: Icons.pending_actions_rounded),
        RoleNavItem(id: 'audit', label: 'Audit Trail', route: '/audit', icon: Icons.history_edu_rounded),
        RoleNavItem(id: 'approver', label: 'Approvals', route: '/approver', icon: Icons.verified_rounded),
      ],
    ),
  ],
  bottomNav: [
    RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded),
    RoleNavItem(id: 'detection', label: 'Detection', route: '/detection-studio', icon: Icons.psychology_rounded),
    RoleNavItem(id: 'graph', label: 'Graph', route: '/graph-explorer', icon: Icons.account_tree_rounded),
    RoleNavItem(id: 'settings', label: 'Settings', route: '/settings', icon: Icons.settings_rounded),
  ],
  quickActions: [],
  extraRoutes: [
    '/',
    '/wallet',
    '/history',
    '/trust-check',
    '/dispute/:id',
    '/war-room/alerts',
    '/war-room/transactions',
    '/war-room/cross-chain',
    '/war-room/detection/graph',
    '/war-room/detection/models',
    '/war-room/detection/risk',
    '/war-room/approvals',
    '/settings',
    '/profile',
    '/more',
    '/cross-chain',
    '/nft-swap',
    '/zknaf',
    '/safe',
    '/session-keys',
    '/flagged-queue',
    '/pending-approvals',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// R4: INSTITUTION COMPLIANCE CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r4ComplianceConfig = RoleNavigationConfig(
  role: Role.r4InstitutionCompliance,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Compliance',
  accentColor: Color(0xFFFF9800), // Orange
  sections: [
    RoleNavSection(
      title: 'MONITORING',
      items: [
        RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded, isEmbedded: true),
        RoleNavItem(id: 'alerts', label: 'Alerts', route: '/war-room/alerts', icon: Icons.notification_important_rounded, isEmbedded: true),
        RoleNavItem(id: 'flagged', label: 'Flagged Queue', route: '/flagged-queue', icon: Icons.flag_rounded),
        RoleNavItem(id: 'transactions', label: 'Transactions', route: '/war-room/transactions', icon: Icons.swap_horiz_rounded, isEmbedded: true),
        RoleNavItem(id: 'cross-chain', label: 'Cross-Chain', route: '/war-room/cross-chain', icon: Icons.device_hub_rounded, isEmbedded: true),
        RoleNavItem(id: 'detection', label: 'Detection Studio', route: '/detection-studio', icon: Icons.psychology_rounded, isEmbedded: true),
        RoleNavItem(id: 'graph', label: 'Graph Explorer', route: '/graph-explorer', icon: Icons.account_tree_rounded, isEmbedded: true),
        RoleNavItem(id: 'risk', label: 'Risk Scoring', route: '/war-room/detection/risk', icon: Icons.assessment_rounded, isEmbedded: true),
      ],
    ),
    RoleNavSection(
      title: 'COMPLIANCE',
      items: [
        RoleNavItem(id: 'compliance', label: 'Compliance Hub', route: '/compliance', icon: Icons.shield_rounded),
        RoleNavItem(id: 'policy', label: 'Policy Engine', route: '/policy-engine', icon: Icons.tune_rounded),
        RoleNavItem(id: 'enforcement', label: 'Enforcement', route: '/enforcement', icon: Icons.security_rounded),
        RoleNavItem(id: 'fatf', label: 'FATF Rules', route: '/fatf-rules', icon: Icons.public_rounded),
        RoleNavItem(id: 'disputes', label: 'Disputes', route: '/disputes', icon: Icons.gavel_rounded),
      ],
    ),
    RoleNavSection(
      title: 'GOVERNANCE',
      items: [
        RoleNavItem(id: 'multisig', label: 'Multisig Queue', route: '/multisig-queue', icon: Icons.how_to_vote_rounded),
        RoleNavItem(id: 'pending', label: 'Pending Approvals', route: '/pending-approvals', icon: Icons.pending_actions_rounded),
        RoleNavItem(id: 'audit', label: 'Audit Chain Replay', route: '/audit', icon: Icons.history_edu_rounded),
        RoleNavItem(id: 'snapshots', label: 'UI Snapshots', route: '/ui-snapshots', icon: Icons.photo_camera_rounded),
        RoleNavItem(id: 'reports', label: 'Reports', route: '/reports', icon: Icons.summarize_rounded),
        RoleNavItem(id: 'approver', label: 'Approvals', route: '/approver', icon: Icons.verified_rounded),
      ],
    ),
  ],
  bottomNav: [
    RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded),
    RoleNavItem(id: 'compliance', label: 'Compliance', route: '/compliance', icon: Icons.shield_rounded),
    RoleNavItem(id: 'audit', label: 'Audit', route: '/audit', icon: Icons.history_edu_rounded),
    RoleNavItem(id: 'settings', label: 'Settings', route: '/settings', icon: Icons.settings_rounded),
  ],
  quickActions: [],
  extraRoutes: [
    '/',
    '/wallet',
    '/history',
    '/trust-check',
    '/dispute/:id',
    '/war-room/alerts',
    '/war-room/transactions',
    '/war-room/cross-chain',
    '/war-room/detection/graph',
    '/war-room/detection/models',
    '/war-room/detection/risk',
    '/war-room/approvals',
    '/settings',
    '/profile',
    '/more',
    '/cross-chain',
    '/nft-swap',
    '/zknaf',
    '/safe',
    '/session-keys',
    '/flagged-queue',
    '/pending-approvals',
    '/policy-engine',
    '/enforcement',
    '/multisig-queue',
    '/ui-snapshots',
    '/reports',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// R5: PLATFORM ADMIN CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r5PlatformAdminConfig = RoleNavigationConfig(
  role: Role.r5PlatformAdmin,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Platform Admin',
  accentColor: Color(0xFFF44336), // Red
  sections: [
    RoleNavSection(
      title: 'MONITORING',
      items: [
        RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded, isEmbedded: true),
        RoleNavItem(id: 'alerts', label: 'Alerts', route: '/war-room/alerts', icon: Icons.notification_important_rounded, isEmbedded: true),
        RoleNavItem(id: 'flagged', label: 'Flagged Queue', route: '/flagged-queue', icon: Icons.flag_rounded),
        RoleNavItem(id: 'transactions', label: 'Transactions', route: '/war-room/transactions', icon: Icons.swap_horiz_rounded, isEmbedded: true),
        RoleNavItem(id: 'cross-chain', label: 'Cross-Chain', route: '/war-room/cross-chain', icon: Icons.device_hub_rounded, isEmbedded: true),
        RoleNavItem(id: 'detection', label: 'Detection Studio', route: '/detection-studio', icon: Icons.psychology_rounded, isEmbedded: true),
        RoleNavItem(id: 'graph', label: 'Graph Explorer', route: '/graph-explorer', icon: Icons.account_tree_rounded, isEmbedded: true),
        RoleNavItem(id: 'risk', label: 'Risk Scoring', route: '/war-room/detection/risk', icon: Icons.assessment_rounded, isEmbedded: true),
      ],
    ),
    RoleNavSection(
      title: 'ADMIN',
      items: [
        RoleNavItem(id: 'admin', label: 'Admin Console', route: '/admin', icon: Icons.admin_panel_settings_rounded),
        RoleNavItem(id: 'users', label: 'User Management', route: '/user-management', icon: Icons.people_rounded),
        RoleNavItem(id: 'system', label: 'System Settings', route: '/system-settings', icon: Icons.settings_applications_rounded),
        RoleNavItem(id: 'session-keys', label: 'Session Keys', route: '/session-keys', icon: Icons.vpn_key_rounded),
        RoleNavItem(id: 'safe', label: 'Safes', route: '/safe', icon: Icons.lock_rounded),
      ],
    ),
    RoleNavSection(
      title: 'COMPLIANCE',
      items: [
        RoleNavItem(id: 'compliance', label: 'Compliance Hub', route: '/compliance', icon: Icons.shield_rounded),
        RoleNavItem(id: 'policy', label: 'Policy Engine', route: '/policy-engine', icon: Icons.tune_rounded),
        RoleNavItem(id: 'enforcement', label: 'Enforcement', route: '/enforcement', icon: Icons.security_rounded),
        RoleNavItem(id: 'reports', label: 'Reports', route: '/reports', icon: Icons.summarize_rounded),
      ],
    ),
    RoleNavSection(
      title: 'GOVERNANCE',
      items: [
        RoleNavItem(id: 'multisig', label: 'Multisig Queue', route: '/multisig-queue', icon: Icons.how_to_vote_rounded),
        RoleNavItem(id: 'audit', label: 'Audit Trail', route: '/audit', icon: Icons.history_edu_rounded),
      ],
    ),
  ],
  bottomNav: [
    RoleNavItem(id: 'dashboard', label: 'Dashboard', route: '/war-room', icon: Icons.dashboard_rounded),
    RoleNavItem(id: 'admin', label: 'Admin', route: '/admin', icon: Icons.admin_panel_settings_rounded),
    RoleNavItem(id: 'users', label: 'Users', route: '/user-management', icon: Icons.people_rounded),
    RoleNavItem(id: 'settings', label: 'Settings', route: '/settings', icon: Icons.settings_rounded),
  ],
  quickActions: [],
  extraRoutes: [
    '/',
    '/wallet',
    '/history',
    '/trust-check',
    '/disputes',
    '/dispute/:id',
    '/compliance',
    '/audit',
    '/war-room/alerts',
    '/war-room/transactions',
    '/war-room/cross-chain',
    '/war-room/detection/graph',
    '/war-room/detection/models',
    '/war-room/detection/risk',
    '/war-room/approvals',
    '/settings',
    '/profile',
    '/more',
    '/cross-chain',
    '/nft-swap',
    '/zknaf',
    '/safe',
    '/session-keys',
    '/detection-studio',
    '/graph-explorer',
    '/flagged-queue',
    '/pending-approvals',
    '/policy-engine',
    '/enforcement',
    '/multisig-queue',
    '/ui-snapshots',
    '/reports',
    '/user-management',
    '/system-settings',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// R6: SUPER ADMIN CONFIG
// ═══════════════════════════════════════════════════════════════════════════════

const r6SuperAdminConfig = RoleNavigationConfig(
  role: Role.r6SuperAdmin,
  shellTitle: 'AMTTP',
  shellSubtitle: 'Super Admin',
  accentColor: Color(0xFF6366F1), // Indigo
  sections: [
    RoleNavSection(
      title: 'AUDIT',
      items: [
        RoleNavItem(id: 'audit', label: 'Audit Chain Replay', route: '/audit', icon: Icons.history_edu_rounded),
        RoleNavItem(id: 'snapshots', label: 'UI Snapshots', route: '/ui-snapshots', icon: Icons.photo_camera_rounded),
        RoleNavItem(id: 'reports', label: 'Reports', route: '/reports', icon: Icons.summarize_rounded),
        RoleNavItem(id: 'fatf', label: 'FATF Rules', route: '/fatf-rules', icon: Icons.public_rounded),
      ],
    ),
    RoleNavSection(
      title: 'ML & DETECTION',
      items: [
        RoleNavItem(id: 'ml-models', label: 'ML Models', route: '/ml-models', icon: Icons.psychology_rounded, isEmbedded: true),
        RoleNavItem(id: 'detection', label: 'Detection Studio', route: '/detection-studio', icon: Icons.radar_rounded, isEmbedded: true),
        RoleNavItem(id: 'risk', label: 'Risk Scoring', route: '/war-room/detection/risk', icon: Icons.assessment_rounded, isEmbedded: true),
      ],
    ),
    RoleNavSection(
      title: 'READ-ONLY VIEWS',
      items: [
        RoleNavItem(id: 'dashboard', label: 'War Room', route: '/war-room', icon: Icons.dashboard_rounded, isEmbedded: true),
        RoleNavItem(id: 'alerts', label: 'Alerts', route: '/war-room/alerts', icon: Icons.notification_important_rounded, isEmbedded: true),
        RoleNavItem(id: 'flagged', label: 'Flagged Queue', route: '/flagged-queue', icon: Icons.flag_rounded),
        RoleNavItem(id: 'transactions', label: 'Transactions', route: '/war-room/transactions', icon: Icons.swap_horiz_rounded, isEmbedded: true),
        RoleNavItem(id: 'cross-chain', label: 'Cross-Chain', route: '/war-room/cross-chain', icon: Icons.device_hub_rounded, isEmbedded: true),
        RoleNavItem(id: 'graph', label: 'Graph Explorer', route: '/graph-explorer', icon: Icons.account_tree_rounded, isEmbedded: true),
        RoleNavItem(id: 'disputes', label: 'Disputes', route: '/disputes', icon: Icons.gavel_rounded),
      ],
    ),
    RoleNavSection(
      title: 'ADMIN (RO)',
      items: [
        RoleNavItem(id: 'admin', label: 'Admin (ro)', route: '/admin', icon: Icons.admin_panel_settings_rounded),
        RoleNavItem(id: 'compliance', label: 'Compliance (ro)', route: '/compliance', icon: Icons.shield_rounded),
      ],
    ),
  ],
  bottomNav: [
    RoleNavItem(id: 'audit', label: 'Audit', route: '/audit', icon: Icons.history_edu_rounded),
    RoleNavItem(id: 'dashboard', label: 'War Room', route: '/war-room', icon: Icons.dashboard_rounded),
    RoleNavItem(id: 'snapshots', label: 'Snapshots', route: '/ui-snapshots', icon: Icons.photo_camera_rounded),
    RoleNavItem(id: 'settings', label: 'Settings', route: '/settings', icon: Icons.settings_rounded),
  ],
  quickActions: [],
  extraRoutes: [
    '/',
    '/wallet',
    '/history',
    '/trust-check',
    '/disputes',
    '/dispute/:id',
    '/compliance',
    '/fatf-rules',
    '/admin',
    '/war-room/alerts',
    '/war-room/transactions',
    '/war-room/cross-chain',
    '/war-room/detection/graph',
    '/war-room/detection/models',
    '/war-room/detection/risk',
    '/war-room/approvals',
    '/settings',
    '/profile',
    '/more',
    '/cross-chain',
    '/nft-swap',
    '/zknaf',
    '/safe',
    '/session-keys',
    '/detection-studio',
    '/graph-explorer',
    '/flagged-queue',
    '/ui-snapshots',
    '/reports',
    '/ml-models',
  ],
);

// ═══════════════════════════════════════════════════════════════════════════════
// CONFIG GETTER
// ═══════════════════════════════════════════════════════════════════════════════

/// Get navigation config for a specific role
RoleNavigationConfig getNavigationConfigForRole(Role role) {
  switch (role) {
    case Role.r1EndUser:
      return r1EndUserConfig;
    case Role.r2EndUserPep:
      return r2PowerUserConfig;
    case Role.r3InstitutionOps:
      return r3InstitutionOpsConfig;
    case Role.r4InstitutionCompliance:
      return r4ComplianceConfig;
    case Role.r5PlatformAdmin:
      return r5PlatformAdminConfig;
    case Role.r6SuperAdmin:
      return r6SuperAdminConfig;
  }
}

/// Check if a role can access a specific route
bool canRoleAccessRoute(Role role, String route) {
  final config = getNavigationConfigForRole(role);
  return config.canAccess(route);
}

// Basic pattern matcher for dynamic routes like /dispute/:id
bool _routeMatches(String pattern, String route) {
  if (pattern == route) return true;

  final patternParts = pattern.split('/').where((p) => p.isNotEmpty).toList();
  final routeParts = route.split('/').where((p) => p.isNotEmpty).toList();

  if (patternParts.length != routeParts.length) return false;

  for (var i = 0; i < patternParts.length; i++) {
    final patternPart = patternParts[i];
    final routePart = routeParts[i];

    if (patternPart.startsWith(':')) {
      continue; // dynamic segment
    }

    if (patternPart != routePart) {
      return false;
    }
  }

  return true;
}
