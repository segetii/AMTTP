/// Consolidated App Router
/// 
/// SIMPLIFIED STRUCTURE:
/// - 10 core pages (down from 35+)
/// - Single implementation per feature (no Premium vs Standard duplicates)
/// - Advanced features consolidated into single tabbed page
/// - Backward-compatible redirects for old routes
/// 
/// See CONSOLIDATION_PLAN.md for details.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// CORE PAGES (Consolidated)
// ═══════════════════════════════════════════════════════════════════════════════
import '../../features/home/presentation/pages/home_page.dart';
import '../../features/wallet/presentation/pages/wallet_page.dart';
import '../../features/transfer/presentation/pages/premium_transfer_page.dart';
import '../../features/history/presentation/pages/history_page.dart';
import '../../features/trust_check/presentation/pages/premium_trust_check_page.dart';
import '../../features/wallet_connect/presentation/pages/premium_wallet_connect_page.dart';
import '../../features/settings/presentation/pages/settings_page.dart';
import '../../features/disputes/presentation/pages/dispute_center_page.dart';
import '../../features/disputes/presentation/pages/dispute_detail_page.dart';
import '../../features/advanced/presentation/pages/advanced_features_page.dart';

// Auth pages
import '../../features/auth/presentation/pages/premium_sign_in_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';
import '../../features/auth/presentation/pages/unauthorized_page.dart';

// Admin pages (kept for institutional users)
import '../../features/admin/presentation/pages/admin_page.dart';
import '../../features/compliance/presentation/pages/compliance_page.dart';
import '../../features/approver/presentation/pages/approver_portal_page.dart';
import '../../features/audit/presentation/pages/audit_chain_replay_page.dart';
import '../../features/war_room/presentation/pages/flagged_queue_page.dart';
import '../../features/war_room/presentation/pages/compliance_pages.dart';
import '../../features/war_room/presentation/pages/admin_pages.dart';

// Shell
import '../../shared/shells/premium_fintech_shell.dart';

// Auth & RBAC
import '../auth/auth_provider.dart';
import '../rbac/rbac.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION SECTIONS
// ═══════════════════════════════════════════════════════════════════════════════

enum PremiumSection { home, wallet, send, activity, profile }

PremiumSection sectionForRoute(String route) {
  final path = route.split('?').first.split('#').first;
  
  if (path == '/' || path == '/home') return PremiumSection.home;
  if (path == '/wallet' || path.startsWith('/wallet')) return PremiumSection.wallet;
  if (path == '/transfer' || path == '/trust-check' || path.startsWith('/transfer')) return PremiumSection.send;
  if (path == '/history' || path.startsWith('/history')) return PremiumSection.activity;
  if (path == '/profile' || path == '/settings' || path == '/more') return PremiumSection.profile;
  
  return PremiumSection.home;
}

// Alias for compatibility
enum FintechSection { home, wallet, send, activity, profile }

FintechSection fintechSectionForRoute(String route) {
  final section = sectionForRoute(route);
  return FintechSection.values[section.index];
}

// ═══════════════════════════════════════════════════════════════════════════════
// ROUTER REFRESH STREAM
// ═══════════════════════════════════════════════════════════════════════════════

class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(this._ref) {
    _ref.listen(authProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

// ═══════════════════════════════════════════════════════════════════════════════
// CONSOLIDATED ROUTER PROVIDER
// ═══════════════════════════════════════════════════════════════════════════════

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);
  final rbacState = ref.watch(rbacProvider);
  
  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final path = state.matchedLocation;
      final isAuthRoute = path == '/sign-in' || path == '/register' || path == '/select-profile';
      
      // Redirect unauthenticated users to sign-in
      if (!isAuthenticated && !isAuthRoute && path != '/unauthorized') {
        return '/sign-in';
      }
      
      // Redirect authenticated users away from auth pages
      if (isAuthenticated && isAuthRoute) {
        final user = authState.user;
        return user != null ? _defaultRouteForRole(user.role) : '/';
      }
      
      // RBAC route guard for institutional routes
      if (isAuthenticated && _isInstitutionalRoute(path)) {
        final currentRole = rbacState.role;
        if (!canRoleAccessRoute(currentRole, path)) {
          return '/unauthorized?from=${Uri.encodeComponent(path)}';
        }
      }
      
      return null;
    },
    routes: [
      // ════════════════════════════════════════════════════════════════════════
      // AUTH ROUTES (Public)
      // ════════════════════════════════════════════════════════════════════════
      GoRoute(
        path: '/sign-in',
        name: 'sign-in',
        builder: (context, state) => const PremiumSignInPage(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterPage(),
      ),
      GoRoute(
        path: '/unauthorized',
        name: 'unauthorized',
        builder: (context, state) {
          final attemptedRoute = state.uri.queryParameters['from'];
          return UnauthorizedPage(attemptedRoute: attemptedRoute);
        },
      ),
      
      // ════════════════════════════════════════════════════════════════════════
      // MAIN APP (Premium Fintech Shell) - 10 Core Pages
      // ════════════════════════════════════════════════════════════════════════
      ShellRoute(
        builder: (context, state, child) {
          return PremiumFintechShell(
            currentRoute: state.matchedLocation,
            child: child,
          );
        },
        routes: [
          // ──────────────────────────────────────────────────────────────────────
          // 1. HOME
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/',
            name: 'home',
            builder: (context, state) => const FintechHomePage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 2. WALLET
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/wallet',
            name: 'wallet',
            builder: (context, state) => const WalletPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 3. TRANSFER (includes trust check)
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/transfer',
            name: 'transfer',
            builder: (context, state) => const PremiumTransferPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 4. HISTORY
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/history',
            name: 'history',
            builder: (context, state) => const HistoryPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 5. SETTINGS
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/settings',
            name: 'settings',
            builder: (context, state) => const SettingsPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 6. TRUST CHECK (standalone page)
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/trust-check',
            name: 'trust-check',
            builder: (context, state) {
              final address = state.uri.queryParameters['address'];
              return PremiumTrustCheckPage(initialAddress: address);
            },
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 7. WALLET CONNECT
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/connect',
            name: 'connect',
            builder: (context, state) => const PremiumWalletConnectPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 8. ADVANCED FEATURES (Consolidated: NFT, CrossChain, Safe, Sessions, zkNAF)
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/advanced',
            name: 'advanced',
            builder: (context, state) {
              final tab = state.uri.queryParameters['tab'];
              return AdvancedFeaturesPage(initialTab: tab);
            },
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 9. DISPUTES
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/disputes',
            name: 'disputes',
            builder: (context, state) => const DisputeCenterPage(),
          ),
          
          // ──────────────────────────────────────────────────────────────────────
          // 10. DISPUTE DETAIL
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/dispute/:id',
            name: 'dispute-detail',
            builder: (context, state) {
              final disputeId = state.pathParameters['id'] ?? '';
              return DisputeDetailPage(disputeId: disputeId);
            },
          ),
          
          // ════════════════════════════════════════════════════════════════════════
          // BACKWARD COMPATIBILITY REDIRECTS
          // ════════════════════════════════════════════════════════════════════════
          
          // Navigation aliases
          GoRoute(path: '/wallet-connect', redirect: (_, __) => '/connect'),
          GoRoute(path: '/profile', redirect: (_, __) => '/settings'),
          GoRoute(path: '/more', redirect: (_, __) => '/settings'),
          
          // Advanced features deep links → consolidated page
          GoRoute(path: '/nft-swap', redirect: (_, __) => '/advanced?tab=nft'),
          GoRoute(path: '/cross-chain', redirect: (_, __) => '/advanced?tab=crosschain'),
          GoRoute(path: '/safe', redirect: (_, __) => '/advanced?tab=safe'),
          GoRoute(path: '/session-keys', redirect: (_, __) => '/advanced?tab=sessions'),
          GoRoute(path: '/zknaf', redirect: (_, __) => '/advanced?tab=privacy'),
          
          // ════════════════════════════════════════════════════════════════════════
          // INSTITUTIONAL ROUTES (R3+) - Kept for Admin/Compliance users
          // ════════════════════════════════════════════════════════════════════════
          GoRoute(
            path: '/admin',
            name: 'admin',
            builder: (context, state) => const AdminPage(),
          ),
          GoRoute(
            path: '/compliance',
            name: 'compliance',
            builder: (context, state) {
              final tab = state.uri.queryParameters['tab'];
              return ComplianceToolsPage(initialTab: tab);
            },
          ),
          GoRoute(
            path: '/approver',
            name: 'approver',
            builder: (context, state) => const ApproverPortalPage(),
          ),
          GoRoute(
            path: '/audit',
            name: 'audit',
            builder: (context, state) => const AuditChainReplayTool(),
          ),
          GoRoute(
            path: '/flagged-queue',
            name: 'flagged-queue',
            builder: (context, state) => const FlaggedQueuePage(),
          ),
          GoRoute(
            path: '/policy-engine',
            name: 'policy-engine',
            builder: (context, state) => const PolicyEnginePage(),
          ),
          GoRoute(
            path: '/enforcement',
            name: 'enforcement',
            builder: (context, state) => const EnforcementActionsPage(),
          ),
          GoRoute(
            path: '/pending-approvals',
            name: 'pending-approvals',
            builder: (context, state) => const PendingApprovalsPage(),
          ),
          GoRoute(
            path: '/multisig-queue',
            name: 'multisig-queue',
            builder: (context, state) => const MultisigQueuePage(),
          ),
          GoRoute(
            path: '/ui-snapshots',
            name: 'ui-snapshots',
            builder: (context, state) => const UISnapshotsPage(),
          ),
          GoRoute(
            path: '/reports',
            name: 'reports',
            builder: (context, state) => const ReportsPage(),
          ),
          GoRoute(
            path: '/user-management',
            name: 'user-management',
            builder: (context, state) => const UserManagementPage(),
          ),
          GoRoute(
            path: '/system-settings',
            name: 'system-settings',
            builder: (context, state) => const SystemSettingsPage(),
          ),
        ],
      ),
    ],
  );
});

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

/// Check if route is for institutional users (R3+)
bool _isInstitutionalRoute(String path) {
  const institutionalPaths = [
    '/admin', '/compliance', '/approver', '/audit', '/flagged-queue',
    '/policy-engine', '/enforcement', '/pending-approvals', '/multisig-queue',
    '/ui-snapshots', '/reports', '/user-management', '/system-settings',
  ];
  return institutionalPaths.any((p) => path.startsWith(p));
}

/// Get default route for user role
String _defaultRouteForRole(Role role) {
  // End users go to home
  if (role.level <= 2) return '/';
  
  // Institutional users go to admin or compliance based on role
  if (role.level >= 4) return '/admin';
  
  return '/flagged-queue';
}
