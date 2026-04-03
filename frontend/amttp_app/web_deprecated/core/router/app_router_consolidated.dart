/// Consolidated App Router
///
/// SIMPLIFIED STRUCTURE:
/// - 10 core pages for end users
/// - No RBAC route guards (handled by Next.js for institutional users)
/// - Sign-in routes users to appropriate app based on role
///
/// Routing Logic:
/// - End Users (R1, R2) → Stay in Flutter Wallet App
/// - Institutional (R3+) → Redirected to Next.js War Room
///
/// See CONSOLIDATION_PLAN.md for details.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// CORE PAGES (Consolidated)
// ═══════════════════════════════════════════════════════════════════════════════
// Dead import removed: home_page.dart (only FintechHomePage from premium_fintech_shell.dart is used)
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

// Shell
import '../../shared/shells/premium_fintech_shell.dart';

// Auth
import '../auth/auth_provider.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// NAVIGATION SECTIONS
// ═══════════════════════════════════════════════════════════════════════════════

enum PremiumSection { home, wallet, send, activity, profile }

PremiumSection sectionForRoute(String route) {
  final path = route.split('?').first.split('#').first;

  if (path == '/' || path == '/home') return PremiumSection.home;
  if (path == '/wallet' || path.startsWith('/wallet')) {
    return PremiumSection.wallet;
  }
  if (path == '/transfer' ||
      path == '/trust-check' ||
      path.startsWith('/transfer')) {
    return PremiumSection.send;
  }
  if (path == '/history' || path.startsWith('/history')) {
    return PremiumSection.activity;
  }
  if (path == '/profile' || path == '/settings' || path == '/more') {
    return PremiumSection.profile;
  }

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
// SIMPLIFIED ROUTER PROVIDER (No RBAC)
// ═══════════════════════════════════════════════════════════════════════════════

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final path = state.matchedLocation;
      final isAuthRoute = path == '/sign-in' || path == '/register';

      // Redirect unauthenticated users to sign-in
      if (!isAuthenticated && !isAuthRoute && path != '/unauthorized') {
        return '/sign-in';
      }

      // Redirect authenticated users away from auth pages to home
      // (Role-based routing is handled in sign-in page)
      if (isAuthenticated && isAuthRoute) {
        return '/';
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
      // MAIN APP (Premium Fintech Shell) - End User Wallet
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
          GoRoute(
              path: '/cross-chain',
              redirect: (_, __) => '/advanced?tab=crosschain'),
          GoRoute(path: '/safe', redirect: (_, __) => '/advanced?tab=safe'),
          GoRoute(
              path: '/session-keys',
              redirect: (_, __) => '/advanced?tab=sessions'),
          GoRoute(path: '/zknaf', redirect: (_, __) => '/advanced?tab=privacy'),
        ],
      ),
    ],
  );
});
