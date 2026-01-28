/// AMTTP Role-Based Access Control (RBAC) System
/// 
/// Canonical role definitions aligned with AMTTP UI/UX Ground Truth v2.3
/// 
/// Role Hierarchy:
/// - R1: End User (standard)
/// - R2: End User PEP (politically exposed person - enhanced monitoring)
/// - R3: Institution Ops (read-only analytics, no enforcement)
/// - R4: Institution Compliance (can enforce policies, requires multisig)
/// - R5: Platform Admin (system configuration)
/// - R6: Super Admin (full access, emergency controls)

library rbac;

/// Canonical role enum - R1 to R6
enum Role {
  /// Standard end user - wallet, transfers, basic features
  r1EndUser('R1_END_USER', 'End User', 1),
  
  /// Politically Exposed Person - same features, enhanced monitoring
  r2EndUserPep('R2_END_USER_PEP', 'End User (PEP)', 2),
  
  /// Institution Operations - read-only analytics, detection studio
  r3InstitutionOps('R3_INSTITUTION_OPS', 'Institution Ops', 3),
  
  /// Institution Compliance - can enforce policies (with multisig)
  r4InstitutionCompliance('R4_INSTITUTION_COMPLIANCE', 'Compliance Officer', 4),
  
  /// Platform Admin - system configuration, user management
  r5PlatformAdmin('R5_PLATFORM_ADMIN', 'Platform Admin', 5),
  
  /// Super Admin - full access, emergency override
  r6SuperAdmin('R6_SUPER_ADMIN', 'Super Admin', 6);

  final String code;
  final String displayName;
  final int level;
  
  const Role(this.code, this.displayName, this.level);
  
  /// Parse role from string code
  static Role fromCode(String code) {
    return Role.values.firstWhere(
      (r) => r.code == code,
      orElse: () => Role.r1EndUser,
    );
  }
  
  /// Check if this role has at least the given level
  bool hasLevel(int requiredLevel) => level >= requiredLevel;
  
  /// Check if this role is at least as privileged as another
  bool isAtLeast(Role other) => level >= other.level;
}

/// Application mode based on role
enum AppMode {
  /// Simplified interface for end users (R1, R2)
  focusMode('FOCUS_MODE', 'Focus Mode'),
  
  /// Full analytics dashboard for institutional users (R3+)
  warRoomMode('WAR_ROOM_MODE', 'War Room');

  final String code;
  final String displayName;
  
  const AppMode(this.code, this.displayName);
}

/// Get the default app mode for a role
AppMode getModeForRole(Role role) {
  switch (role) {
    case Role.r1EndUser:
    case Role.r2EndUserPep:
      return AppMode.focusMode;
    case Role.r3InstitutionOps:
    case Role.r4InstitutionCompliance:
    case Role.r5PlatformAdmin:
    case Role.r6SuperAdmin:
      return AppMode.warRoomMode;
  }
}

/// Role capabilities matrix
class RoleCapabilities {
  final bool canInitiateOwnTx;
  final bool canViewOthersTx;
  final bool canAccessDetectionStudio;
  final bool canEditPolicies;
  final bool canEnforceActions;
  final bool canSignMultisig;
  final String canViewUISnapshots; // 'none', 'view', 'verify', 'full'
  final bool canEmergencyOverride;
  final bool canManageUsers;
  final bool canExportReports;
  final bool canAccessCompliance;

  const RoleCapabilities({
    required this.canInitiateOwnTx,
    required this.canViewOthersTx,
    required this.canAccessDetectionStudio,
    required this.canEditPolicies,
    required this.canEnforceActions,
    required this.canSignMultisig,
    required this.canViewUISnapshots,
    required this.canEmergencyOverride,
    required this.canManageUsers,
    required this.canExportReports,
    required this.canAccessCompliance,
  });
}

/// Capabilities for each role
/// Per AMTTP UI/UX Ground Truth v2.3 - Section 8
const Map<Role, RoleCapabilities> roleCapabilities = {
  // R1: End User - Focus Mode, can initiate own transactions
  Role.r1EndUser: RoleCapabilities(
    canInitiateOwnTx: true,  // ✅ Per matrix
    canViewOthersTx: false,
    canAccessDetectionStudio: false,  // ❌ Per matrix
    canEditPolicies: false,  // ❌ Per matrix
    canEnforceActions: false,  // ❌ Per matrix
    canSignMultisig: false,  // ❌ Per matrix
    canViewUISnapshots: 'view',  // View per matrix
    canEmergencyOverride: false,  // ❌ Per matrix
    canManageUsers: false,
    canExportReports: false,
    canAccessCompliance: false,
  ),
  // R2: End User PEP - Same as R1, enhanced monitoring
  Role.r2EndUserPep: RoleCapabilities(
    canInitiateOwnTx: true,  // ✅ Per matrix
    canViewOthersTx: false,
    canAccessDetectionStudio: false,  // ❌ Per matrix
    canEditPolicies: false,  // ❌ Per matrix
    canEnforceActions: false,  // ❌ Per matrix
    canSignMultisig: false,  // ❌ Per matrix
    canViewUISnapshots: 'view',  // View per matrix
    canEmergencyOverride: false,  // ❌ Per matrix
    canManageUsers: false,
    canExportReports: false,
    canAccessCompliance: false,
  ),
  // R3: Institution Ops - War Room, READ-ONLY analytics
  Role.r3InstitutionOps: RoleCapabilities(
    canInitiateOwnTx: false,  // ❌ Per matrix - NO TX for institution roles
    canViewOthersTx: true,
    canAccessDetectionStudio: true,  // ✅ Full access per matrix
    canEditPolicies: false,  // ❌ READ-ONLY per matrix
    canEnforceActions: false,  // ❌ CANNOT ENFORCE per matrix
    canSignMultisig: false,  // ❌ Per matrix
    canViewUISnapshots: 'view',  // View per matrix
    canEmergencyOverride: false,  // ❌ Per matrix
    canManageUsers: false,
    canExportReports: true,
    canAccessCompliance: true,
  ),
  // R4: Institution Compliance - War Room, can enforce (with multisig)
  Role.r4InstitutionCompliance: RoleCapabilities(
    canInitiateOwnTx: false,  // ❌ Per matrix - NO TX for institution roles
    canViewOthersTx: true,
    canAccessDetectionStudio: true,  // View per matrix (not full)
    canEditPolicies: true,  // ✅ Per matrix
    canEnforceActions: true,  // ✅ Per matrix (requires multisig)
    canSignMultisig: true,  // ✅ Per matrix
    canViewUISnapshots: 'full',  // Full per matrix
    canEmergencyOverride: false,  // ❌ Per matrix
    canManageUsers: false,
    canExportReports: true,
    canAccessCompliance: true,
  ),
  // R5: Platform Admin - System config (not in matrix, inferred)
  Role.r5PlatformAdmin: RoleCapabilities(
    canInitiateOwnTx: false,  // Platform admin - not for transactions
    canViewOthersTx: true,
    canAccessDetectionStudio: true,  // System oversight
    canEditPolicies: true,  // Platform-level policies
    canEnforceActions: false,  // Cannot enforce on behalf of institutions
    canSignMultisig: false,  // Not institutional
    canViewUISnapshots: 'full',
    canEmergencyOverride: false,  // No emergency override
    canManageUsers: true,  // Primary purpose
    canExportReports: true,
    canAccessCompliance: true,
  ),
  // R6: Super Admin - Emergency override ONLY
  Role.r6SuperAdmin: RoleCapabilities(
    canInitiateOwnTx: false,  // ❌ Per matrix - NO TX
    canViewOthersTx: true,
    canAccessDetectionStudio: false,  // ❌ Per matrix - NOT for investigation
    canEditPolicies: false,  // ❌ Per matrix
    canEnforceActions: false,  // ❌ Per matrix
    canSignMultisig: false,  // ❌ Per matrix
    canViewUISnapshots: 'full',  // Full per matrix
    canEmergencyOverride: true,  // ✅ ONLY R6 can do this
    canManageUsers: true,
    canExportReports: true,
    canAccessCompliance: true,
  ),
};

/// Get capabilities for a role
RoleCapabilities getCapabilities(Role role) {
  return roleCapabilities[role] ?? roleCapabilities[Role.r1EndUser]!;
}

/// Check if a role can perform a specific action
bool canPerform(Role role, String action) {
  final caps = getCapabilities(role);
  switch (action) {
    case 'initiate_tx':
      return caps.canInitiateOwnTx;
    case 'view_others_tx':
      return caps.canViewOthersTx;
    case 'detection_studio':
      return caps.canAccessDetectionStudio;
    case 'edit_policies':
      return caps.canEditPolicies;
    case 'enforce_actions':
      return caps.canEnforceActions;
    case 'sign_multisig':
      return caps.canSignMultisig;
    case 'emergency_override':
      return caps.canEmergencyOverride;
    case 'manage_users':
      return caps.canManageUsers;
    case 'export_reports':
      return caps.canExportReports;
    case 'compliance':
      return caps.canAccessCompliance;
    default:
      return false;
  }
}
