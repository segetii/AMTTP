import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

// Core pages - consolidated
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

// Auth & RBAC
import '../auth/auth_provider.dart';

/// Simplified navigation sections for bottom nav
enum AppSection { home, wallet, send, activity, profile }

AppSection sectionForRoute(String route) {
  final path = route.split('?').first.split('#').first;

  if (path == '/' || path == '/home') return AppSection.home;
  if (path == '/wallet' || path.startsWith('/wallet')) return AppSection.wallet;
  if (path == '/transfer' ||
      path == '/trust-check' ||
      path.startsWith('/transfer')) {
    return AppSection.send;
  }
  if (path == '/history' || path.startsWith('/history')) {
    return AppSection.activity;
  }
  if (path == '/profile' || path == '/settings' || path == '/more') {
    return AppSection.profile;
  }

  return AppSection.home;
}

/// Listenable for GoRouter refresh when auth state changes
class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(this._ref) {
    _ref.listen(authProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

/// Simplified router provider
final simplifiedRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final isAuthRoute = state.matchedLocation == '/sign-in' ||
          state.matchedLocation == '/register';

      // Redirect unauthenticated users to sign-in
      if (!isAuthenticated &&
          !isAuthRoute &&
          state.matchedLocation != '/unauthorized') {
        return '/sign-in';
      }

      // Redirect authenticated users away from auth pages
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
      // MAIN APP (Premium Fintech Shell)
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
          // CORE WALLET PAGES (5 main screens)
          // ──────────────────────────────────────────────────────────────────────
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
            path: '/settings',
            name: 'settings',
            builder: (context, state) => const SettingsPage(),
          ),

          // ──────────────────────────────────────────────────────────────────────
          // UTILITY PAGES
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/trust-check',
            name: 'trust-check',
            builder: (context, state) {
              final address = state.uri.queryParameters['address'];
              return PremiumTrustCheckPage(initialAddress: address);
            },
          ),
          GoRoute(
            path: '/connect',
            name: 'connect',
            builder: (context, state) => const PremiumWalletConnectPage(),
          ),

          // Aliases for navigation compatibility
          GoRoute(path: '/wallet-connect', redirect: (_, __) => '/connect'),
          GoRoute(path: '/profile', redirect: (_, __) => '/settings'),
          GoRoute(path: '/more', redirect: (_, __) => '/settings'),

          // ──────────────────────────────────────────────────────────────────────
          // ADVANCED FEATURES (Consolidated power user tools)
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/advanced',
            name: 'advanced',
            builder: (context, state) {
              final tab = state.uri.queryParameters['tab'];
              return AdvancedFeaturesPage(initialTab: tab);
            },
          ),
          // Deep links into advanced tabs
          GoRoute(path: '/nft-swap', redirect: (_, __) => '/advanced?tab=nft'),
          GoRoute(
              path: '/cross-chain',
              redirect: (_, __) => '/advanced?tab=crosschain'),
          GoRoute(path: '/safe', redirect: (_, __) => '/advanced?tab=safe'),
          GoRoute(
              path: '/session-keys',
              redirect: (_, __) => '/advanced?tab=sessions'),
          GoRoute(path: '/zknaf', redirect: (_, __) => '/advanced?tab=privacy'),

          // ──────────────────────────────────────────────────────────────────────
          // DISPUTES
          // ──────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/disputes',
            name: 'disputes',
            builder: (context, state) => const DisputeCenterPage(),
          ),
          GoRoute(
            path: '/dispute/:id',
            name: 'dispute-detail',
            builder: (context, state) {
              final disputeId = state.pathParameters['id'] ?? '';
              return DisputeDetailPage(disputeId: disputeId);
            },
          ),
        ],
      ),
    ],
  );
});
