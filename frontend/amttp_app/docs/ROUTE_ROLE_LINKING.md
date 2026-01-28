# Route-Role Linking Implementation

## Summary

**CLEAN ARCHITECTURE**: Each role has its own navigation config. Pages are ONLY loaded for the authorized role - no hiding, no filtering.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RoleNavigationConfig                          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │ R1 Config │  │ R2 Config │  │ R3 Config │  │ R4 Config │... │
│  │ (5 pages) │  │ (8 pages) │  │(15 pages) │  │(22 pages) │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
│        │              │              │              │           │
│        ▼              ▼              ▼              ▼           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              RoleBasedShell                              │   │
│  │  - Renders ONLY the nav items in the config              │   │
│  │  - Focus Mode (R1,R2) = bottom nav only                  │   │
│  │  - War Room (R3+) = sidebar + sections                   │   │
│  │  - Full Screen Mode for embedded Next.js pages           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Shell Modes

### Focus Mode (R1, R2)
- **Bottom navigation only** - no sidebar
- Clean mobile-first experience
- App bar with profile and trust badge

### War Room Mode (R3+)
- **Single sidebar** - NO duplicate navigation
- Collapsible for more screen space
- Sections organized by function

### Full Screen Mode (Embedded Pages)
- **Content fills entire screen**
- Back button overlay (top-left)
- No Flutter chrome
- Perfect for Next.js dashboard viewing

---

## Implementation Files

| File | Purpose |
|------|---------|
| `lib/core/rbac/role_navigation_config.dart` | **NEW** - Role-specific configs |
| `lib/shared/shells/role_based_shell.dart` | **NEW** - Clean shell that uses configs |
| `lib/core/router/app_router.dart` | Updated - Uses `canRoleAccessRoute()` |

---

## Role Configs

### R1: End User (Basic)
```dart
const r1EndUserConfig = RoleNavigationConfig(
  bottomNav: [home, wallet, transfer, history, profile],
  sections: [], // No sidebar - bottom nav only
);
```

### R2: Power User
```dart
const r2PowerUserConfig = RoleNavigationConfig(
  bottomNav: [home, wallet, transfer, history, more],
  quickActions: [send, nft-swap, cross-chain, disputes],
);
```

### R3: Institution Ops
```dart
const r3InstitutionOpsConfig = RoleNavigationConfig(
  sections: [
    MONITORING: [dashboard, detection, flagged, alerts],
    OPERATIONS: [cross-chain, disputes, audit],
  ],
);
```

### R4: Institution Compliance
```dart
const r4ComplianceConfig = RoleNavigationConfig(
  sections: [
    MONITORING: [dashboard, detection, flagged, transactions],
    COMPLIANCE: [policies, multisig, alerts],
    AUDIT: [audit, reports, disputes],
  ],
);
```

### R5: Platform Admin
```dart
const r5PlatformAdminConfig = RoleNavigationConfig(
  sections: [
    MONITORING: [...],
    COMPLIANCE: [...],
    ADMIN: [users, roles, config, integrations],
  ],
);
```

### R6: Super Admin
```dart
const r6SuperAdminConfig = RoleNavigationConfig(
  sections: [
    MONITORING: [...],
    COMPLIANCE: [...],
    ADMIN: [...],
    ML & AI: [ml-models, risk-engine],
    EMERGENCY: [emergency-controls],
  ],
);
```

---

## Usage

### 1. Get Config for Role
```dart
final config = getNavigationConfigForRole(role);
```

### 2. Check Route Access
```dart
if (config.canAccess('/war-room/policies')) {
  // User can see this route
}
```

### 3. Use in Router
```dart
if (!canRoleAccessRoute(currentRole, path)) {
  return '/unauthorized';
}
```

### 4. Build Navigation
```dart
// The shell ONLY renders items in config.sections
for (final section in config.sections) {
  for (final item in section.items) {
    // Render nav item
  }
}
```

---

## Benefits

1. **No Filtering** - Each role config defines exactly what they see
2. **No Hiding** - Nothing is loaded and then hidden
3. **Single Source of Truth** - One config file per role
4. **Easy to Audit** - Look at config to see what role can do
5. **Type Safe** - Compile-time checking of routes
    leading: Icon(item.icon),
    title: Text(item.label),
    onTap: () => context.go(item.path),
  );
}
```

### 3. Check Feature Access

```dart
final profileNav = ProfileNavigation(currentRole);

// Show War Room button?
if (profileNav.hasWarRoomAccess) {
  IconButton(
    icon: Icon(Icons.dashboard),
    onPressed: () => context.go('/war-room'),
  );
}
```

### 4. Handle Embedded Routes

```dart
// When navigating to a route
final route = RoutePermissions.getRoute(path);

if (route?.type == RouteType.embedded) {
  // Load in WebView/iframe
  final nextJsUrl = 'http://localhost:3006${route!.nextJsPath}?embed=true';
  Navigator.push(context, MaterialPageRoute(
    builder: (_) => NextJsEmbedPage(url: nextJsUrl),
  ));
} else {
  // Navigate to native Flutter page
  context.go(path);
}
```

---

## Migration Steps

1. ✅ Create `route_permissions.dart` - Single source of truth
2. ✅ Create `route_guard.dart` - Helper utilities
3. ⬜ Update router to use route guards
4. ⬜ Update navigation shells to use ProfileNavigation
5. ⬜ Test each role to verify access

---

## Benefits

1. **Single Source of Truth** - All route-role mappings in one file
2. **Type Safe** - Compile-time checks for route access
3. **Maintainable** - Easy to add new routes or change access
4. **Testable** - Can unit test route guards
5. **Consistent** - Same logic for navigation menus and route guards
