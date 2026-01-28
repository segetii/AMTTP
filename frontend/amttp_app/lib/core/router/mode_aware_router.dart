/// AMTTP App Router - Mode-Aware Navigation
/// 
/// Per Ground Truth v2.3:
/// - Focus Mode (R1/R2): Simplified interface for end users
/// - War Room Mode (R3+): Full analytics dashboard for institutional users
/// 
/// Route Structure:
/// / - End User home (Focus Mode)
/// /war-room/* - Institutional interface (War Room Mode)

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

// Feature pages
import '../../features/home/presentation/pages/home_page.dart';
import '../../features/home/presentation/pages/focus_home_page.dart';
import '../../features/wallet/presentation/pages/wallet_page.dart';
import '../../features/transfer/presentation/pages/transfer_page.dart';
import '../../features/transfer/presentation/pages/premium_transfer_page.dart';
import '../../features/history/presentation/pages/history_page.dart';
import '../../features/settings/presentation/pages/settings_page.dart';
import '../../features/disputes/presentation/pages/dispute_center_page.dart';
import '../../features/disputes/presentation/pages/dispute_detail_page.dart';
import '../../features/nft_swap/presentation/pages/nft_swap_page.dart';
import '../../features/cross_chain/presentation/pages/cross_chain_page.dart';
import '../../features/safe/presentation/pages/safe_management_page.dart';
import '../../features/session_keys/presentation/pages/session_key_page.dart';
import '../../features/zknaf/presentation/pages/zknaf_page.dart';

// Premium fintech pages (Metamask/Revolut style)
import '../../features/trust_check/presentation/pages/premium_trust_check_page.dart';
import '../../features/wallet_connect/presentation/pages/premium_wallet_connect_page.dart';

// War Room pages
import '../../features/detection_studio/presentation/pages/detection_studio_page.dart';
import '../../features/compliance/presentation/pages/compliance_page.dart';
import '../../features/admin/presentation/pages/admin_page.dart';
import '../../features/audit/presentation/pages/audit_chain_replay_page.dart';
import '../../features/approver/presentation/pages/approver_portal_page.dart';

// War Room - new pages for Ground Truth alignment
import '../../features/war_room/presentation/pages/war_room_landing_page.dart';
import '../../features/war_room/presentation/pages/war_room_nextjs_page.dart';
import '../../features/war_room/presentation/pages/flagged_queue_page.dart';
import '../../features/war_room/presentation/pages/graph_explorer_page.dart';
// Visualization pages
import '../../features/war_room/presentation/pages/visualization_pages.dart';
// Compliance pages
import '../../features/war_room/presentation/pages/compliance_pages.dart';
// Admin pages
import '../../features/war_room/presentation/pages/admin_pages.dart';

// Pre-transaction trust check (Focus Mode)
import '../../features/trust_check/presentation/pages/trust_check_page.dart';

// Authentication
import '../../features/auth/presentation/pages/sign_in_page.dart';
import '../../features/auth/presentation/pages/light_sign_in_page.dart';
import '../../features/auth/presentation/pages/premium_sign_in_page.dart';
import '../../features/auth/presentation/pages/register_page.dart';

// Light-themed pages for Focus Mode
import '../../features/home/presentation/pages/light_home_page.dart';

// Navigation shells
import '../navigation/mode_aware_shell.dart';
import '../../shared/shells/premium_fintech_shell.dart'; // Premium fintech shell (Metamask/Revolut style)
import '../navigation/war_room_shell.dart';

// RBAC
import '../rbac/rbac_provider.dart';
import '../rbac/roles.dart';

/// Listenable for GoRouter refresh when RBAC state changes
class RBACRouterRefreshStream extends ChangeNotifier {
  RBACRouterRefreshStream(this._ref) {
    _ref.listen(rbacProvider, (_, __) => notifyListeners());
  }
  final Ref _ref;
}

final appRouterProvider = Provider<GoRouter>((ref) {
  final rbacState = ref.watch(rbacProvider);
  
  return GoRouter(
    initialLocation: '/sign-in',
    refreshListenable: RBACRouterRefreshStream(ref),
    
    // Global redirect based on authentication and role
    redirect: (context, state) {
      final isAuthenticated = rbacState.isAuthenticated;
      final location = state.matchedLocation;
      
      // Auth routes
      final isAuthRoute = location == '/sign-in' || location == '/register';
      
      // If not authenticated and not on auth route, redirect to sign-in
      if (!isAuthenticated && !isAuthRoute) {
        return '/sign-in';
      }
      
      // If authenticated and on auth route, redirect based on mode
      if (isAuthenticated && isAuthRoute) {
        return rbacState.isFocusMode ? '/' : '/war-room';
      }
      
      // Enforce mode restrictions
      if (isAuthenticated) {
        final isWarRoomRoute = location.startsWith('/war-room');
        
        // End users cannot access War Room
        if (rbacState.isEndUser && isWarRoomRoute) {
          return '/';
        }
        
        // Check role-specific route access
        if (isWarRoomRoute) {
          // Compliance routes require R4+
          final isComplianceRoute = location.contains('/policies') || 
                                    location.contains('/enforcement') ||
                                    location.contains('/multisig') ||
                                    location.contains('/approvals');
          if (isComplianceRoute && !rbacState.role.isAtLeast(Role.r4InstitutionCompliance)) {
            return '/war-room';
          }
          
          // Admin routes require R5+
          final isAdminRoute = location.contains('/users') || 
                               location.contains('/system');
          if (isAdminRoute && !rbacState.role.isAtLeast(Role.r5PlatformAdmin)) {
            return '/war-room';
          }
        }
      }
      
      return null;
    },
    
    routes: [
      // ═══════════════════════════════════════════════════════════════════════
      // AUTH ROUTES (Public) - Premium Fintech Design
      // ═══════════════════════════════════════════════════════════════════════
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
      
      // ═══════════════════════════════════════════════════════════════════════
      // FOCUS MODE ROUTES (R1/R2 End Users) - Premium Fintech Design
      // ═══════════════════════════════════════════════════════════════════════
      ShellRoute(
        builder: (context, state, child) => PremiumFintechShell(
          currentRoute: state.uri.toString(),
          child: child,
        ),
        routes: [
          // Home - Premium Fintech Wallet Interface
          GoRoute(
            path: '/',
            name: 'home',
            builder: (context, state) => const FintechHomePage(),
          ),
          
          // Wallet
          GoRoute(
            path: '/wallet',
            name: 'wallet',
            builder: (context, state) => const WalletPage(),
          ),
          
          // Transfer (with pre-transaction trust check) - Premium Fintech Design
          GoRoute(
            path: '/transfer',
            name: 'transfer',
            builder: (context, state) => const PremiumTransferPage(),
          ),
          
          // Pre-Transaction Trust Check (per Ground Truth) - Premium Fintech Design
          GoRoute(
            path: '/trust-check',
            name: 'trust-check',
            builder: (context, state) {
              final address = state.uri.queryParameters['address'] ?? '';
              return PremiumTrustCheckPage(initialAddress: address.isEmpty ? null : address);
            },
          ),
          
          // Wallet Connect - Premium Fintech Design
          GoRoute(
            path: '/wallet-connect',
            name: 'wallet-connect',
            builder: (context, state) => const PremiumWalletConnectPage(),
          ),
          
          // Transaction History
          GoRoute(
            path: '/history',
            name: 'history',
            builder: (context, state) => const HistoryPage(),
          ),
          
          // Disputes (user's own disputes)
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
          
          // NFT Swap
          GoRoute(
            path: '/nft-swap',
            name: 'nft-swap',
            builder: (context, state) => const NFTSwapPage(),
          ),
          
          // Cross-Chain Transfers
          GoRoute(
            path: '/cross-chain',
            name: 'cross-chain',
            builder: (context, state) => const CrossChainPage(),
          ),
          
          // Safe Management (Gnosis Safe)
          GoRoute(
            path: '/safe',
            name: 'safe',
            builder: (context, state) => const SafeManagementPage(),
          ),
          
          // Session Keys (ERC-4337)
          GoRoute(
            path: '/session-keys',
            name: 'session-keys',
            builder: (context, state) => const SessionKeyPage(),
          ),
          
          // zkNAF Privacy
          GoRoute(
            path: '/zknaf',
            name: 'zknaf',
            builder: (context, state) => const ZkNAFPage(),
          ),
          
          // Settings
          GoRoute(
            path: '/settings',
            name: 'settings',
            builder: (context, state) => const SettingsPage(),
          ),
          
          // Profile (alias for settings)
          GoRoute(
            path: '/profile',
            name: 'profile',
            builder: (context, state) => const SettingsPage(),
          ),
        ],
      ),
      
      // ═══════════════════════════════════════════════════════════════════════
      // WAR ROOM MODE ROUTES (R3+ Institutional Users)
      // ═══════════════════════════════════════════════════════════════════════
      ShellRoute(
        builder: (context, state, child) => WarRoomShell(child: child),
        routes: [
          // War Room Landing - Full Next.js War Room for R4+ users
          GoRoute(
            path: '/war-room',
            name: 'war-room',
            builder: (context, state) => const WarRoomNextJSPage(),
          ),
          
          // ───────────────────────────────────────────────────────────────────
          // DETECTION STUDIO (R3 Ops - Read Only)
          // ───────────────────────────────────────────────────────────────────
          
          // Flagged Queue (Primary Action Surface)
          GoRoute(
            path: '/war-room/queue',
            name: 'flagged-queue',
            builder: (context, state) => const FlaggedQueuePage(),
          ),
          
          // Graph Explorer (Memgraph)
          GoRoute(
            path: '/war-room/graph',
            name: 'graph-explorer',
            builder: (context, state) {
              final txId = state.uri.queryParameters['tx'];
              return GraphExplorerPage(initialTxId: txId);
            },
          ),
          
          // Velocity Heatmap
          GoRoute(
            path: '/war-room/heatmap',
            name: 'velocity-heatmap',
            builder: (context, state) => const VelocityHeatmapPage(),
          ),
          
          // Value Flow Sankey
          GoRoute(
            path: '/war-room/sankey',
            name: 'sankey-flow',
            builder: (context, state) => const SankeyFlowPage(),
          ),
          
          // ML Explainability
          GoRoute(
            path: '/war-room/ml',
            name: 'ml-explainability',
            builder: (context, state) => const MLExplainabilityPage(),
          ),
          
          // Legacy Detection Studio (iframe to Next.js)
          GoRoute(
            path: '/war-room/detection-studio',
            name: 'detection-studio',
            builder: (context, state) => const DetectionStudioPage(),
          ),
          
          // ───────────────────────────────────────────────────────────────────
          // COMPLIANCE STUDIO (R4 - Can Enforce with Multisig)
          // ───────────────────────────────────────────────────────────────────
          
          // Policy Engine
          GoRoute(
            path: '/war-room/policies',
            name: 'policy-engine',
            builder: (context, state) => const PolicyEnginePage(),
          ),
          
          // Enforcement Actions
          GoRoute(
            path: '/war-room/enforcement',
            name: 'enforcement-actions',
            builder: (context, state) => const EnforcementActionsPage(),
          ),
          
          // Compliance Tools (legacy)
          GoRoute(
            path: '/war-room/compliance',
            name: 'compliance-tools',
            builder: (context, state) {
              final tab = state.uri.queryParameters['tab'];
              return ComplianceToolsPage(initialTab: tab);
            },
          ),
          
          // ───────────────────────────────────────────────────────────────────
          // GOVERNANCE (R4+ Multisig)
          // ───────────────────────────────────────────────────────────────────
          
          // Multisig Queue
          GoRoute(
            path: '/war-room/multisig',
            name: 'multisig-queue',
            builder: (context, state) => const MultisigQueuePage(),
          ),
          
          // Pending Approvals
          GoRoute(
            path: '/war-room/approvals',
            name: 'pending-approvals',
            builder: (context, state) => const PendingApprovalsPage(),
          ),
          
          // Legacy Approver Portal
          GoRoute(
            path: '/war-room/approver',
            name: 'approver-portal',
            builder: (context, state) => const ApproverPortalPage(),
          ),
          
          // ───────────────────────────────────────────────────────────────────
          // AUDIT & REPORTS
          // ───────────────────────────────────────────────────────────────────
          
          // UI Snapshots
          GoRoute(
            path: '/war-room/snapshots',
            name: 'ui-snapshots',
            builder: (context, state) => const UISnapshotsPage(),
          ),
          
          // Audit Chain
          GoRoute(
            path: '/war-room/audit',
            name: 'audit-chain',
            builder: (context, state) => const AuditChainReplayTool(),
          ),
          
          // Reports
          GoRoute(
            path: '/war-room/reports',
            name: 'reports',
            builder: (context, state) => const ReportsPage(),
          ),
          
          // ───────────────────────────────────────────────────────────────────
          // ADMINISTRATION (R5+)
          // ───────────────────────────────────────────────────────────────────
          
          // User Management
          GoRoute(
            path: '/war-room/users',
            name: 'user-management',
            builder: (context, state) => const UserManagementPage(),
          ),
          
          // System Settings
          GoRoute(
            path: '/war-room/system',
            name: 'system-settings',
            builder: (context, state) => const SystemSettingsPage(),
          ),
          
          // Legacy Admin Page
          GoRoute(
            path: '/war-room/admin',
            name: 'admin-legacy',
            builder: (context, state) => const AdminPage(),
          ),
        ],
      ),
    ],
  );
});
