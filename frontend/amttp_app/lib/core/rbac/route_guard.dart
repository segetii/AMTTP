/// Route Guard - Enforces role-based access at the router level
/// 
/// Uses RoutePermissions config to determine if a user can access a route.
/// Integrates with existing RBAC Role enum.

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'roles.dart';
import 'route_permissions.dart';

/// Convert existing Role enum to RoutePermissions UserRole
UserRole roleToUserRole(Role role) {
  switch (role) {
    case Role.r1EndUser:
      return UserRole.R1_END_USER;
    case Role.r2EndUserPep:
      return UserRole.R2_POWER_USER; // PEP users get power user features
    case Role.r3InstitutionOps:
      return UserRole.R3_INSTITUTION_OPS;
    case Role.r4InstitutionCompliance:
      return UserRole.R4_INSTITUTION_COMPLIANCE;
    case Role.r5PlatformAdmin:
      return UserRole.R5_PLATFORM_ADMIN;
    case Role.r6SuperAdmin:
      return UserRole.R6_SUPER_ADMIN;
  }
}

/// Convert UserRole back to Role enum
Role userRoleToRole(UserRole userRole) {
  switch (userRole) {
    case UserRole.R1_END_USER:
      return Role.r1EndUser;
    case UserRole.R2_POWER_USER:
      return Role.r2EndUserPep;
    case UserRole.R3_INSTITUTION_OPS:
      return Role.r3InstitutionOps;
    case UserRole.R4_INSTITUTION_COMPLIANCE:
      return Role.r4InstitutionCompliance;
    case UserRole.R5_PLATFORM_ADMIN:
      return Role.r5PlatformAdmin;
    case UserRole.R6_SUPER_ADMIN:
      return Role.r6SuperAdmin;
  }
}

/// Route guard result
enum RouteGuardResult {
  allowed,
  redirectToHome,
  redirectToLogin,
  redirectToUpgrade, // User needs higher role
}

/// Check if a user with given role can access a path
RouteGuardResult checkRouteAccess(String path, Role? role) {
  // Not logged in
  if (role == null) {
    // Allow public routes
    if (path == '/sign-in' || path == '/register' || path == '/select-profile') {
      return RouteGuardResult.allowed;
    }
    return RouteGuardResult.redirectToLogin;
  }

  // Convert to UserRole
  final userRole = roleToUserRole(role);

  // Check route permissions
  final routePermission = RoutePermissions.getRoute(path);
  
  // Route not in config - allow (it may be a system route)
  if (routePermission == null) {
    return RouteGuardResult.allowed;
  }

  // Check access
  if (routePermission.hasAccess(userRole)) {
    return RouteGuardResult.allowed;
  }

  // User doesn't have access
  return RouteGuardResult.redirectToUpgrade;
}

/// Get the redirect path for a guard result
String getRedirectPath(RouteGuardResult result) {
  switch (result) {
    case RouteGuardResult.allowed:
      return ''; // No redirect
    case RouteGuardResult.redirectToHome:
      return '/';
    case RouteGuardResult.redirectToLogin:
      return '/sign-in';
    case RouteGuardResult.redirectToUpgrade:
      return '/'; // Redirect to home with a message
  }
}

/// Get all accessible routes for a role
List<RoutePermission> getAccessibleRoutes(Role role) {
  final userRole = roleToUserRole(role);
  return RoutePermissions.getRoutesForRole(userRole);
}

/// Get navigation items for a role (for sidebar/bottom nav)
/// NOTE: Uses RoutePermissions config - separate from rbac_navigation.dart
List<RoutePermission> getRouteNavItemsForRole(Role role) {
  final userRole = roleToUserRole(role);
  return RoutePermissions.getNavRoutes(userRole);
}

/// Check if route is embedded (requires iframe)
bool isEmbeddedRoute(String path) {
  final route = RoutePermissions.getRoute(path);
  return route?.type == RouteType.embedded;
}

/// Get Next.js URL for embedded route
String? getNextJsPath(String path) {
  final route = RoutePermissions.getRoute(path);
  return route?.nextJsPath;
}

/// ═══════════════════════════════════════════════════════════════════════════════
/// NAVIGATION HELPERS
/// ═══════════════════════════════════════════════════════════════════════════════

/// Get profile-based navigation structure
class ProfileNavigation {
  final Role role;
  
  ProfileNavigation(this.role);
  
  /// Get main nav items (sidebar)
  List<RoutePermission> get mainNav => getRouteNavItemsForRole(role);
  
  /// Get bottom nav items (mobile)
  List<RoutePermission> get bottomNav {
    final userRole = roleToUserRole(role);
    
    // End users get simplified bottom nav
    if (userRole == UserRole.R1_END_USER || userRole == UserRole.R2_POWER_USER) {
      return [
        RoutePermissions.home,
        RoutePermissions.wallet,
        RoutePermissions.transfer,
        RoutePermissions.history,
        RoutePermissions.settings,
      ];
    }
    
    // Institutional users get different bottom nav
    return [
      RoutePermissions.home,
      RoutePermissions.warRoom,
      RoutePermissions.compliance,
      RoutePermissions.settings,
    ];
  }
  
  /// Get quick action routes (FAB menu, etc.)
  List<RoutePermission> get quickActions {
    final userRole = roleToUserRole(role);
    
    final actions = <RoutePermission>[
      RoutePermissions.transfer,
    ];
    
    // Add more actions for higher roles
    if (RoutePermissions.nftSwap.hasAccess(userRole)) {
      actions.add(RoutePermissions.nftSwap);
    }
    if (RoutePermissions.crossChain.hasAccess(userRole)) {
      actions.add(RoutePermissions.crossChain);
    }
    
    return actions;
  }
  
  /// Check if War Room access is available
  bool get hasWarRoomAccess {
    final userRole = roleToUserRole(role);
    return RoutePermissions.warRoom.hasAccess(userRole);
  }
  
  /// Check if Compliance tools are available
  bool get hasComplianceAccess {
    final userRole = roleToUserRole(role);
    return RoutePermissions.compliance.hasAccess(userRole);
  }
  
  /// Check if Admin tools are available
  bool get hasAdminAccess {
    final userRole = roleToUserRole(role);
    return RoutePermissions.admin.hasAccess(userRole);
  }
  
  /// Check if Super Admin tools are available
  bool get hasSuperAdminAccess {
    final userRole = roleToUserRole(role);
    return RoutePermissions.mlModels.hasAccess(userRole);
  }
}

/// ═══════════════════════════════════════════════════════════════════════════════
/// RIVERPOD PROVIDER
/// ═══════════════════════════════════════════════════════════════════════════════

/// Provider for profile navigation
final profileNavigationProvider = Provider.family<ProfileNavigation, Role>((ref, role) {
  return ProfileNavigation(role);
});
