import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/auth/presentation/pages/war_room_redirect_page.dart';
import '../../features/home/presentation/pages/home_page.dart';
import '../../features/wallet/presentation/pages/wallet_page.dart';
import '../../features/transfer/presentation/pages/transfer_page.dart';
import '../../features/transfer/presentation/pages/premium_transfer_page.dart';
import '../../features/history/presentation/pages/history_page.dart';
import '../../features/admin/presentation/pages/admin_page.dart';
import '../../features/settings/presentation/pages/settings_page.dart';
import '../../features/detection_studio/presentation/pages/detection_studio_page.dart';
import '../../features/war_room/presentation/pages/war_room_nextjs_page.dart';
import '../../features/war_room/presentation/pages/war_room_landing_page.dart';
import '../../features/war_room/presentation/pages/graph_explorer_page.dart';
// New feature pages for complete contract coverage
import '../../features/nft_swap/presentation/pages/nft_swap_page.dart';
import '../../features/disputes/presentation/pages/dispute_center_page.dart';
import '../../features/disputes/presentation/pages/dispute_detail_page.dart';
import '../../features/cross_chain/presentation/pages/cross_chain_page.dart';
import '../../features/safe/presentation/pages/safe_management_page.dart';
import '../../features/session_keys/presentation/pages/session_key_page.dart';
import '../../features/approver/presentation/pages/approver_portal_page.dart';
import '../../features/compliance/presentation/pages/compliance_page.dart';
import '../../features/compliance/presentation/pages/fatf_rules_page.dart';
import '../../features/trust_check/presentation/pages/trust_check_page.dart';
import '../../features/trust_check/presentation/pages/premium_trust_check_page.dart';
import '../../features/wallet_connect/presentation/pages/premium_wallet_connect_page.dart';
// zkNAF Zero-Knowledge Privacy
import '../../features/zknaf/presentation/pages/zknaf_page.dart';
// Audit Chain Replay
import '../../features/audit/presentation/pages/audit_chain_replay_page.dart';
// Profile-based navigation
import '../../features/profile/presentation/pages/profile_selector_page.dart';
// War Room Native Pages (Compliance, Admin, Flagged)
import '../../features/war_room/presentation/pages/compliance_pages.dart';
import '../../features/war_room/presentation/pages/admin_pages.dart';
import '../../features/war_room/presentation/pages/flagged_queue_page.dart';
// Premium Fintech Shell (Metamask/Revolut style) for End Users
import '../../shared/shells/premium_fintech_shell.dart';
// Role-Based Shell for War Room (R3+)
import '../../shared/shells/role_based_shell.dart';
// ML Models - Super Admin only
import '../../features/ml_models/presentation/pages/ml_models_page.dart';
// Authentication pages
import '../../features/auth/presentation/pages/sign_in_page.dart';
import '../../features/auth/presentation/pages/premium_sign_in_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';
import '../../features/auth/presentation/pages/unauthorized_page.dart';
import '../auth/auth_provider.dart';
// RBAC Route Guards
import '../rbac/rbac.dart';

// Simple enum to represent the main premium shell sections for bottom nav
enum PremiumSection {
  home,
  wallet,
  send,
  activity,
  profile,
}

// Fintech section mapping for centralized routing decisions
enum FintechSection { home, wallet, send, activity, profile }

PremiumSection sectionForRoute(String route) {
  return _sectionFromPath(route.split('?').first.split('#').first);
}

FintechSection fintechSectionForRoute(String route) {
  return _sectionFromPath(route.split('?').first.split('#').first) == PremiumSection.home
      ? FintechSection.home
      : FintechSection.values[_sectionFromPath(route.split('?').first.split('#').first).index];
}

PremiumSection _sectionFromPath(String path) {
  if (path == '/' || path == '/home') return PremiumSection.home;

  if (path == '/wallet' || path.startsWith('/wallet/')) {
    return PremiumSection.wallet;
  }

  // Any transfer-related or trust-check flows are treated as "Send" section
  if (path == '/transfer' ||
      path.startsWith('/transfer/') ||
      path == '/trust-check' ||
      path.startsWith('/trust-check/')) {
    return PremiumSection.send;
  }

  if (path == '/history' || path.startsWith('/history/')) {
    return PremiumSection.activity;
  }

  if (path == '/profile' || path.startsWith('/profile/') || path == '/settings') {
    return PremiumSection.profile;
  }

  // Default to home for unknown paths inside the premium shell
  return PremiumSection.home;
}

/// Listenable for GoRouter refresh when auth or RBAC state changes
class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(this._ref) {
    _ref.listen(authProvider, (_, __) => notifyListeners());
    _ref.listen(rbacProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

final routerProvider = Provider<GoRouter>((ref) {
  // IMPORTANT: Do NOT ref.watch(authProvider) or ref.watch(rbacProvider) here.
  // That would recreate the GoRouter (resetting to initialLocation) on every
  // state change. Instead, read current state inside the redirect callback
  // and rely on GoRouterRefreshStream to trigger re-evaluation.
  ref.keepAlive();
  
  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      final rbacState = ref.read(rbacProvider);
      final isAuthenticated = authState.isAuthenticated;
      final isAuthRoute = state.matchedLocation == '/sign-in' || 
                          state.matchedLocation == '/register' ||
                          state.matchedLocation == '/select-profile';
      
      // ═══════════════════════════════════════════════════════════════════════
      // DEBUG PREVIEW MODE - Skip auth for these routes to evaluate pages
      // TODO: Remove this block before production
      // ═══════════════════════════════════════════════════════════════════════
      const debugPreviewRoutes = [
        '/war-room-landing',
        '/flagged-queue',
        '/policy-engine',
        '/enforcement',
        '/multisig-queue',
        '/pending-approvals',
        '/ui-snapshots',
        '/reports',
        '/user-management',
        '/system-settings',
      ];
      if (debugPreviewRoutes.contains(state.matchedLocation)) {
        return null; // Allow access without auth for preview
      }
      
      // If not authenticated and not on auth route, redirect to sign-in
      if (!isAuthenticated && !isAuthRoute) {
        return '/sign-in';
      }
      
      // Allow the war-room-redirect trampoline page without further checks
      if (state.matchedLocation == '/war-room-redirect') {
        return null;
      }
      
      // If authenticated and on auth route, redirect to home
      if (isAuthenticated && isAuthRoute) {
        final user = authState.user;
        if (user != null) {
          // R3+ users → trampoline page that does a full browser redirect
          if (user.role.level >= 3) {
            return '/war-room-redirect';
          }
          return _defaultRouteForRole(user.role);
        }
        return '/';
      }
      
      // ═══════════════════════════════════════════════════════════════════════
      // RBAC ROUTE GUARD - Clean role-based access check
      // Each role only sees routes in their RoleNavigationConfig
      // ═══════════════════════════════════════════════════════════════════════
      if (isAuthenticated) {
        final currentRole = rbacState.role;
        final path = state.matchedLocation;
        
        // Skip route guard for system pages
        if (path == '/unauthorized' || 
            path == '/settings' || 
            path == '/profile' ||
            path == '/more') {
          return null;
        }
        
        // Use clean role-based config check
        if (!canRoleAccessRoute(currentRole, path)) {
          debugPrint('[RouteGuard] Access denied to $path for role ${currentRole.displayName}');
          return '/unauthorized?from=${Uri.encodeComponent(path)}';
        }
      }
      
      return null;
    },
    routes: [
      // ========== AUTH ROUTES (Public) - Premium Fintech Design ==========
      GoRoute(
        path: '/sign-in',
        name: 'sign-in',
        builder: (context, state) => const PremiumSignInPage(),
      ),
      // Trampoline: shows spinner then does full browser redirect to Next.js War Room
      GoRoute(
        path: '/war-room-redirect',
        name: 'war-room-redirect',
        builder: (context, state) => const WarRoomRedirectPage(),
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
      
      // ========== PROFILE SELECTOR (Demo/Onboarding) ==========
      GoRoute(
        path: '/select-profile',
        name: 'select-profile',
        builder: (context, state) => const ProfileSelectorPage(),
      ),
      
      // ========== END USER ROUTES (R1/R2) - Premium Fintech Shell ==========
      ShellRoute(
        builder: (context, state, child) {
          return PremiumFintechShell(
            currentRoute: state.matchedLocation,
            child: child,
          );
        },
        routes: [
          // Home - Premium Fintech Wallet Interface
          GoRoute(
            path: '/',
            name: 'home',
            builder: (context, state) => const FintechHomePage(),
          ),
          GoRoute(
            path: '/wallet',
            name: 'wallet',
            builder: (context, state) => const WalletPage(),
          ),
          GoRoute(
            path: '/transfer',
            name: 'transfer',
            builder: (context, state) => const PremiumTransferPage(),
          ),
          GoRoute(
            path: '/history',
            name: 'history',
            builder: (context, state) => const HistoryPage(),
          ),
          GoRoute(
            path: '/trust-check',
            name: 'trust-check',
            builder: (context, state) {
              final address = state.uri.queryParameters['address'];
              return PremiumTrustCheckPage(initialAddress: address);
            },
          ),
          GoRoute(
            path: '/wallet-connect',
            name: 'wallet-connect',
            builder: (context, state) => const PremiumWalletConnectPage(),
          ),
          GoRoute(
            path: '/settings',
            name: 'settings',
            builder: (context, state) => const SettingsPage(),
          ),
          
          // Profile page
          GoRoute(
            path: '/profile',
            name: 'profile',
            builder: (context, state) => const SettingsPage(),
          ),
          
          // More menu - redirect to settings
          GoRoute(
            path: '/more',
            name: 'more',
            builder: (context, state) => const SettingsPage(),
          ),

          // Detection Studio (embeds Next.js dashboard)
          GoRoute(
            path: '/detection-studio',
            name: 'detection-studio',
            builder: (context, state) => const DetectionStudioPage(),
          ),

          // War Room (embedded Next.js) - single entry point
          GoRoute(
            path: '/war-room',
            name: 'war-room',
            builder: (context, state) => const WarRoomNextJSPage(),
          ),

          // War Room landing (Flutter native) for direct viewing/testing
          GoRoute(
            path: '/war-room-landing',
            name: 'war-room-landing',
            builder: (context, state) => const WarRoomLandingPage(),
          ),

          // War Room deep links (embedded Next.js) to expose Next features via Flutter nav
          GoRoute(
            path: '/war-room/alerts',
            name: 'war-room-alerts',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/alerts'),
          ),
          GoRoute(
            path: '/war-room/transactions',
            name: 'war-room-transactions',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/transactions'),
          ),
          GoRoute(
            path: '/war-room/cross-chain',
            name: 'war-room-cross-chain',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/cross-chain'),
          ),
          GoRoute(
            path: '/war-room/detection/graph',
            name: 'war-room-detection-graph',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/detection/graph'),
          ),
          GoRoute(
            path: '/war-room/detection/models',
            name: 'war-room-detection-models',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/detection/models'),
          ),
          GoRoute(
            path: '/war-room/detection/risk',
            name: 'war-room-detection-risk',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/detection/risk'),
          ),
          GoRoute(
            path: '/war-room/approvals',
            name: 'war-room-approvals',
            builder: (context, state) => const WarRoomNextJSPage(nextPath: '/war-room/approvals'),
          ),

          // Graph Explorer (embedded Next.js)
          GoRoute(
            path: '/graph-explorer',
            name: 'graph-explorer',
            builder: (context, state) {
              final txId = state.uri.queryParameters['tx'];
              return GraphExplorerPage(initialTxId: txId);
            },
          ),
          
          // NFT Swap - covers AMTTPNFT.sol functions
          GoRoute(
            path: '/nft-swap',
            name: 'nft-swap',
            builder: (context, state) => const NFTSwapPage(),
          ),
          
          // Dispute Center - covers AMTTPDisputeResolver.sol
          GoRoute(
            path: '/disputes',
            name: 'disputes',
            builder: (context, state) => const DisputeCenterPage(),
          ),
          
          // Dispute Detail - detailed view with evidence/appeals
          GoRoute(
            path: '/dispute/:id',
            name: 'dispute-detail',
            builder: (context, state) {
              final disputeId = state.pathParameters['id'] ?? '';
              return DisputeDetailPage(disputeId: disputeId);
            },
          ),
          
          // Cross-Chain - covers AMTTPCrossChain.sol
          GoRoute(
            path: '/cross-chain',
            name: 'cross-chain',
            builder: (context, state) => const CrossChainPage(),
          ),
          
          // Safe Management - covers AMTTPSafeModule.sol (Gnosis Safe)
          GoRoute(
            path: '/safe',
            name: 'safe',
            builder: (context, state) => const SafeManagementPage(),
          ),
          
          // Session Keys - covers AMTTPBiconomyModule.sol (ERC-4337)
          GoRoute(
            path: '/session-keys',
            name: 'session-keys',
            builder: (context, state) => const SessionKeyPage(),
          ),
          
          // zkNAF - Zero-Knowledge Non-disclosure Attestation Framework
          GoRoute(
            path: '/zknaf',
            name: 'zknaf',
            builder: (context, state) => const ZkNAFPage(),
          ),

          // ========== ADMIN ROUTES (Profile 2: Sitemap) ==========
          GoRoute(
            path: '/admin',
            name: 'admin',
            builder: (context, state) => const AdminPage(),
          ),
          
          // Approver Portal - covers approveSwap/rejectSwap from AMTTPCore.sol
          GoRoute(
            path: '/approver',
            name: 'approver',
            builder: (context, state) => const ApproverPortalPage(),
          ),
          
          // ========== COMPLIANCE ROUTES (Profile 3: Sitemap) ==========
          // Compliance Tools - covers AMTTPPolicyEngine.sol
          GoRoute(
            path: '/compliance',
            name: 'compliance',
            builder: (context, state) {
              // Extract tab query parameter (freeze, trusted, pep, edd)
              final tab = state.uri.queryParameters['tab'];
              return ComplianceToolsPage(initialTab: tab);
            },
          ),
          
          // FATF Rules - Links to Next.js compliance tools & Detection Studio
          GoRoute(
            path: '/fatf-rules',
            name: 'fatf-rules',
            builder: (context, state) => const FATFRulesPage(),
          ),
          
          // Audit Chain Replay - For auditors (R6)
          GoRoute(
            path: '/audit',
            name: 'audit',
            builder: (context, state) => const AuditChainReplayTool(),
          ),
          
          // ========== WAR ROOM NATIVE PAGES (R3+) ==========
          // Policy Engine - Rule configuration (R4+)
          GoRoute(
            path: '/policy-engine',
            name: 'policy-engine',
            builder: (context, state) => const PolicyEnginePage(),
          ),
          
          // Enforcement Actions - Freeze/unfreeze controls (R4 with multisig)
          GoRoute(
            path: '/enforcement',
            name: 'enforcement',
            builder: (context, state) => const EnforcementActionsPage(),
          ),
          
          // Multisig Queue - Pending multisig approvals (R4+)
          GoRoute(
            path: '/multisig-queue',
            name: 'multisig-queue',
            builder: (context, state) => const MultisigQueuePage(),
          ),
          
          // Pending Approvals - Transfer approval queue (R3+)
          GoRoute(
            path: '/pending-approvals',
            name: 'pending-approvals',
            builder: (context, state) => const PendingApprovalsPage(),
          ),
          
          // Flagged Queue - Review flagged transactions (R3+)
          GoRoute(
            path: '/flagged-queue',
            name: 'flagged-queue',
            builder: (context, state) => const FlaggedQueuePage(),
          ),
          
          // UI Snapshots - Audit trail screenshots (R4+, R6)
          GoRoute(
            path: '/ui-snapshots',
            name: 'ui-snapshots',
            builder: (context, state) => const UISnapshotsPage(),
          ),
          
          // Reports - Compliance & platform reporting (R4+)
          GoRoute(
            path: '/reports',
            name: 'reports',
            builder: (context, state) => const ReportsPage(),
          ),
          
          // User Management - RBAC user administration (R5)
          GoRoute(
            path: '/user-management',
            name: 'user-management',
            builder: (context, state) => const UserManagementPage(),
          ),
          
          // System Settings - Platform configuration (R5)
          GoRoute(
            path: '/system-settings',
            name: 'system-settings',
            builder: (context, state) => const SystemSettingsPage(),
          ),
          
          // ML Models - Machine Learning model management (R6 Super Admin)
          // Configure, pause, retrain ML models for fraud detection
          GoRoute(
            path: '/ml-models',
            name: 'ml-models',
            builder: (context, state) => const MLModelsPage(),
          ),
        ],
      ),
    ],
  );
});

String _defaultRouteForRole(Role role) {
  // R3+ users are redirected to Next.js War Room via html.window.location.href
  // in the GoRouter redirect above. This function is only called for R1/R2.

  final config = getNavigationConfigForRole(role);

  if (config.bottomNav.isNotEmpty) {
    return config.bottomNav.first.route;
  }

  return '/';
}