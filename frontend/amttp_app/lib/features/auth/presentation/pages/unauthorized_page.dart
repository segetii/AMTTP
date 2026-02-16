/// Unauthorized Page - Displayed when user lacks permission for a route
/// 
/// Shows a friendly message explaining access restrictions and provides
/// navigation options to return to accessible areas.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/rbac/rbac.dart';
import '../../../../core/theme/app_theme.dart';

class UnauthorizedPage extends ConsumerWidget {
  final String? attemptedRoute;
  
  const UnauthorizedPage({
    super.key,
    this.attemptedRoute,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rbacState = ref.watch(rbacProvider);
    final role = rbacState.role;
    final profileNav = ProfileNavigation(role);
    
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      body: Center(
        child: Container(
          constraints: const BoxConstraints(maxWidth: 500),
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Lock Icon
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: AppTheme.riskMedium.withOpacity(0.1),
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: AppTheme.riskMedium.withOpacity(0.3),
                    width: 2,
                  ),
                ),
                child: Icon(
                  Icons.lock_outline_rounded,
                  size: 64,
                  color: AppTheme.riskMedium,
                ),
              ),
              
              const SizedBox(height: 32),
              
              // Title
              Text(
                'Access Restricted',
                style: TextStyle(
                  fontSize: 28,
                  fontWeight: FontWeight.bold,
                  color: AppTheme.textPrimary,
                ),
              ),
              
              const SizedBox(height: 16),
              
              // Message
              Text(
                'Your current role (${role.displayName}) does not have permission to access this area.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  color: AppTheme.textSecondary,
                  height: 1.5,
                ),
              ),
              
              if (attemptedRoute != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.white10,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    attemptedRoute!,
                    style: TextStyle(
                      fontFamily: 'monospace',
                      fontSize: 12,
                      color: AppTheme.textLight,
                    ),
                  ),
                ),
              ],
              
              const SizedBox(height: 32),
              
              // Current Role Badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                decoration: BoxDecoration(
                  gradient: _getRoleGradient(role),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _getRoleIcon(role),
                      color: Colors.white,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Current: ${role.displayName}',
                      style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              
              const SizedBox(height: 32),
              
              // Action Buttons
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  // Go Home
                  _buildActionButton(
                    context,
                    icon: Icons.home_rounded,
                    label: 'Go Home',
                    onTap: () => Navigator.pushReplacementNamed(context, '/'),
                    isPrimary: true,
                  ),
                  
                  const SizedBox(width: 16),
                  
                  // Go Back
                  _buildActionButton(
                    context,
                    icon: Icons.arrow_back_rounded,
                    label: 'Go Back',
                    onTap: () {
                      if (Navigator.canPop(context)) {
                        Navigator.pop(context);
                      } else {
                        Navigator.pushReplacementNamed(context, '/');
                      }
                    },
                    isPrimary: false,
                  ),
                ],
              ),
              
              // War Room Quick Access (if available)
              if (profileNav.hasWarRoomAccess) ...[
                const SizedBox(height: 24),
                const Divider(color: Colors.white10),
                const SizedBox(height: 24),
                Text(
                  'You have access to:',
                  style: TextStyle(
                    color: AppTheme.textSecondary,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: [
                    _buildQuickAccessChip(
                      context,
                      icon: Icons.dashboard_rounded,
                      label: 'War Room',
                      route: '/war-room',
                    ),
                    if (profileNav.hasComplianceAccess)
                      _buildQuickAccessChip(
                        context,
                        icon: Icons.policy_rounded,
                        label: 'Compliance',
                        route: '/war-room/compliance',
                      ),
                    if (profileNav.hasAdminAccess)
                      _buildQuickAccessChip(
                        context,
                        icon: Icons.admin_panel_settings_rounded,
                        label: 'Admin',
                        route: '/war-room/admin/users',
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildActionButton(
    BuildContext context, {
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    required bool isPrimary,
  }) {
    return Material(
      color: isPrimary ? AppTheme.primaryBlue : Colors.white10,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                color: isPrimary ? Colors.white : AppTheme.textSecondary,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  color: isPrimary ? Colors.white : AppTheme.textSecondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildQuickAccessChip(
    BuildContext context, {
    required IconData icon,
    required String label,
    required String route,
  }) {
    return ActionChip(
      avatar: Icon(icon, size: 16, color: AppTheme.primaryBlue),
      label: Text(label),
      backgroundColor: AppTheme.primaryBlue.withOpacity(0.1),
      labelStyle: TextStyle(
        color: AppTheme.primaryBlue,
        fontSize: 12,
      ),
      side: BorderSide(color: AppTheme.primaryBlue.withOpacity(0.3)),
      onPressed: () => Navigator.pushReplacementNamed(context, route),
    );
  }

  LinearGradient _getRoleGradient(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return const LinearGradient(colors: [Color(0xFF4CAF50), Color(0xFF8BC34A)]);
      case Role.r2EndUserPep:
        return const LinearGradient(colors: [Color(0xFF2196F3), Color(0xFF03A9F4)]);
      case Role.r3InstitutionOps:
        return const LinearGradient(colors: [Color(0xFF9C27B0), Color(0xFFE040FB)]);
      case Role.r4InstitutionCompliance:
        return const LinearGradient(colors: [Color(0xFFFF9800), Color(0xFFFFC107)]);
      case Role.r5PlatformAdmin:
        return const LinearGradient(colors: [Color(0xFFF44336), Color(0xFFE91E63)]);
      case Role.r6SuperAdmin:
        return LinearGradient(colors: [AppTheme.primaryBlue, AppTheme.accentPink]);
    }
  }

  IconData _getRoleIcon(Role role) {
    switch (role) {
      case Role.r1EndUser:
        return Icons.person_rounded;
      case Role.r2EndUserPep:
        return Icons.star_rounded;
      case Role.r3InstitutionOps:
        return Icons.business_rounded;
      case Role.r4InstitutionCompliance:
        return Icons.policy_rounded;
      case Role.r5PlatformAdmin:
        return Icons.admin_panel_settings_rounded;
      case Role.r6SuperAdmin:
        return Icons.shield_rounded;
    }
  }
}
