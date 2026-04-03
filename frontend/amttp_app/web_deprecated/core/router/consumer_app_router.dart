/// Consumer App Router - End User Only
/// 
/// This is the CLEAN router for consumer-facing Flutter app (R1/R2 users).
/// It ONLY includes pages that end users need - no institutional/War Room pages.
/// 
/// For institutional users, they access the Next.js War Room directly.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// CONSUMER PAGES ONLY
// ═══════════════════════════════════════════════════════════════════════════════
// Note: FintechHomePage is in premium_fintech_shell.dart, not home_page.dart
import '../../features/wallet/presentation/pages/wallet_page.dart';
import '../../features/transfer/presentation/pages/premium_transfer_page.dart';
import '../../features/history/presentation/pages/history_page.dart';
import '../../features/settings/presentation/pages/settings_page.dart';
import '../../features/trust_check/presentation/pages/premium_trust_check_page.dart';
import '../../features/disputes/presentation/pages/dispute_center_page.dart';
import '../../features/disputes/presentation/pages/dispute_detail_page.dart';
import '../../features/wallet_connect/presentation/pages/premium_wallet_connect_page.dart';
import '../../features/auth/presentation/pages/premium_sign_in_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';
// Advanced features
import '../../features/nft_swap/presentation/pages/nft_swap_page.dart';
import '../../features/cross_chain/presentation/pages/cross_chain_page.dart';
import '../../features/advanced/presentation/pages/advanced_features_page.dart';
// Premium Shell (includes FintechHomePage)
import '../../shared/shells/premium_fintech_shell.dart';
// Auth
import '../auth/auth_provider.dart';

/// Consumer app sections for bottom navigation
enum ConsumerSection {
  home,
  wallet,
  send,
  activity,
  profile,
}

ConsumerSection sectionForRoute(String route) {
  final path = route.split('?').first.split('#').first;
  
  if (path == '/' || path == '/home') return ConsumerSection.home;
  if (path == '/wallet' || path.startsWith('/wallet/')) return ConsumerSection.wallet;
  if (path == '/transfer' || path.startsWith('/transfer/') || 
      path == '/trust-check' || path.startsWith('/trust-check/')) {
    return ConsumerSection.send;
  }
  if (path == '/history' || path.startsWith('/history/') ||
      path == '/disputes' || path.startsWith('/dispute/')) {
    return ConsumerSection.activity;
  }
  if (path == '/profile' || path.startsWith('/profile/') || path == '/settings') {
    return ConsumerSection.profile;
  }
  
  return ConsumerSection.home;
}

/// Listenable for GoRouter refresh when auth state changes
class _GoRouterRefreshStream extends ChangeNotifier {
  _GoRouterRefreshStream(this._ref) {
    _ref.listen(authProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

/// Consumer App Router Provider
/// 
/// Use this for the consumer-facing app build.
final consumerRouterProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);
  
  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: _GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final isAuthRoute = state.matchedLocation == '/sign-in' || 
                          state.matchedLocation == '/register';
      
      // If not authenticated and not on auth route, redirect to sign-in
      if (!isAuthenticated && !isAuthRoute) {
        return '/sign-in';
      }
      
      // If authenticated and on auth route, redirect to home
      if (isAuthenticated && isAuthRoute) {
        return '/';
      }
      
      return null;
    },
    routes: [
      // ════════════════════════════════════════════════════════════════════════
      // AUTH ROUTES
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
      
      // ════════════════════════════════════════════════════════════════════════
      // CONSUMER APP - Premium Fintech Shell
      // ════════════════════════════════════════════════════════════════════════
      ShellRoute(
        builder: (context, state, child) {
          return PremiumFintechShell(
            currentRoute: state.matchedLocation,
            child: child,
          );
        },
        routes: [
          // ─────────────────────────────────────────────────────────────────────
          // HOME - Main dashboard with balance, quick actions
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/',
            name: 'home',
            builder: (context, state) => const FintechHomePage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // WALLET - Token balances, NFTs, receive address
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/wallet',
            name: 'wallet',
            builder: (context, state) => const WalletPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // TRANSFER - Send tokens with trust check
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/transfer',
            name: 'transfer',
            builder: (context, state) => const PremiumTransferPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // TRUST CHECK - Verify recipient before sending
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/trust-check',
            name: 'trust-check',
            builder: (context, state) {
              final address = state.uri.queryParameters['address'];
              return PremiumTrustCheckPage(initialAddress: address);
            },
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // HISTORY - Transaction history
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/history',
            name: 'history',
            builder: (context, state) => const HistoryPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // DISPUTES - View and manage disputes
          // ─────────────────────────────────────────────────────────────────────
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
          
          // ─────────────────────────────────────────────────────────────────────
          // WALLET CONNECT - Connect external wallets
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/wallet-connect',
            name: 'wallet-connect',
            builder: (context, state) => const PremiumWalletConnectPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // NFT SWAP - Advanced NFT swapping (NFT→ETH, NFT→NFT)
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/nft-swap',
            name: 'nft-swap',
            builder: (context, state) => const NFTSwapPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // CROSS-CHAIN - LayerZero cross-chain transfers
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/cross-chain',
            name: 'cross-chain',
            builder: (context, state) => const CrossChainPage(),
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // ADVANCED - Consolidated advanced features page
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/advanced',
            name: 'advanced',
            builder: (context, state) {
              final tab = state.uri.queryParameters['tab'];
              return AdvancedFeaturesPage(initialTab: tab);
            },
          ),
          
          // ─────────────────────────────────────────────────────────────────────
          // PROFILE & SETTINGS
          // ─────────────────────────────────────────────────────────────────────
          GoRoute(
            path: '/settings',
            name: 'settings',
            builder: (context, state) => const SettingsPage(),
          ),
          GoRoute(
            path: '/profile',
            name: 'profile',
            builder: (context, state) => const SettingsPage(),
          ),
        ],
      ),
    ],
  );
});
