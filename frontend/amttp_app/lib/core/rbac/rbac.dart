/// RBAC Library Export
/// 
/// Provides role-based access control for the AMTTP Flutter app.
/// 
/// Usage:
/// ```dart
/// import 'package:amttp_app/core/rbac/rbac.dart';
/// 
/// // Get role config
/// final config = getNavigationConfigForRole(role);
/// 
/// // Check route access
/// if (config.canAccess('/war-room/policies')) {
///   // Show policies link
/// }
/// 
/// // Check capability
/// if (canPerform(role, 'enforce_actions')) {
///   // Show enforce button
/// }
/// ```

library;

export 'roles.dart';
export 'rbac_provider.dart';
export 'rbac_navigation.dart';
export 'role_navigation_config.dart';  // NEW: Clean role-specific configs
export 'route_permissions.dart';
export 'route_guard.dart';
