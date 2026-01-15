import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/home/presentation/pages/home_page.dart';
import '../../features/wallet/presentation/pages/wallet_page.dart';
import '../../features/transfer/presentation/pages/transfer_page.dart';
import '../../features/history/presentation/pages/history_page.dart';
import '../../features/admin/presentation/pages/admin_page.dart';
import '../../features/settings/presentation/pages/settings_page.dart';
import '../../features/detection_studio/presentation/pages/detection_studio_page.dart';
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
// zkNAF Zero-Knowledge Privacy
import '../../features/zknaf/presentation/pages/zknaf_page.dart';
// Profile-based navigation
import '../navigation/profile_navigation_shell.dart';
import '../../features/profile/presentation/pages/profile_selector_page.dart';
// Authentication pages
import '../../features/auth/presentation/pages/sign_in_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';
import '../auth/auth_provider.dart';
import '../auth/user_profile_provider.dart';

/// Listenable for GoRouter refresh when auth state changes
class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(this._ref) {
    _ref.listen(authProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authProvider);
  
  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: GoRouterRefreshStream(ref),
    redirect: (context, state) {
      final isAuthenticated = authState.isAuthenticated;
      final isAuthRoute = state.matchedLocation == '/sign-in' || 
                          state.matchedLocation == '/register' ||
                          state.matchedLocation == '/select-profile';
      
      // If not authenticated and not on auth route, redirect to sign-in
      if (!isAuthenticated && !isAuthRoute) {
        return '/sign-in';
      }
      
      // If authenticated and on auth route, redirect to home
      if (isAuthenticated && isAuthRoute) {
        final user = authState.user;
        if (user != null) {
          switch (user.profile) {
            case UserProfile.endUser:
              return '/';
            case UserProfile.admin:
              return '/admin';
            case UserProfile.complianceOfficer:
              return '/compliance';
          }
        }
        return '/';
      }
      
      return null;
    },
    routes: [
      // ========== AUTH ROUTES (Public) ==========
      GoRoute(
        path: '/sign-in',
        name: 'sign-in',
        builder: (context, state) => const SignInPage(),
      ),
      GoRoute(
        path: '/register',
        name: 'register',
        builder: (context, state) => const RegisterPage(),
      ),
      
      // ========== PROFILE SELECTOR (Demo/Onboarding) ==========
      GoRoute(
        path: '/select-profile',
        name: 'select-profile',
        builder: (context, state) => const ProfileSelectorPage(),
      ),
      
      // ========== SHELL ROUTE WITH PROFILE NAVIGATION ==========
      ShellRoute(
        builder: (context, state, child) {
          return ProfileNavigationShell(child: child);
        },
        routes: [
          // ========== END USER ROUTES (Profile 1: Sitemap) ==========
          GoRoute(
            path: '/',
            name: 'home',
            builder: (context, state) => const HomePage(),
          ),
          GoRoute(
            path: '/wallet',
            name: 'wallet',
            builder: (context, state) => const WalletPage(),
          ),
          GoRoute(
            path: '/transfer',
            name: 'transfer',
            builder: (context, state) => const TransferPage(),
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

          // Detection Studio (embeds Next.js dashboard)
          GoRoute(
            path: '/detection-studio',
            name: 'detection-studio',
            builder: (context, state) => const DetectionStudioPage(),
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
            builder: (context, state) => const ComplianceToolsPage(),
          ),
          
          // FATF Rules - Links to Next.js compliance tools & Detection Studio
          GoRoute(
            path: '/fatf-rules',
            name: 'fatf-rules',
            builder: (context, state) => const FATFRulesPage(),
          ),
        ],
      ),
    ],
  );
});