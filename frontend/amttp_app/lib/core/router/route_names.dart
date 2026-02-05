/// Route Names - Centralized Route Definitions
/// 
/// All route names and paths are defined here for consistency.
/// Use these constants instead of hardcoding strings.
/// 
/// Usage:
/// ```dart
/// context.goNamed(RouteNames.home);
/// context.push(RoutePaths.transfer);
/// ```

abstract class RoutePaths {
  // ═══════════════════════════════════════════════════════════════════════════
  // AUTH ROUTES
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String signIn = '/sign-in';
  static const String register = '/register';
  static const String unauthorized = '/unauthorized';
  static const String selectProfile = '/select-profile';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // CONSUMER ROUTES (End User)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String home = '/';
  static const String wallet = '/wallet';
  static const String transfer = '/transfer';
  static const String trustCheck = '/trust-check';
  static const String history = '/history';
  static const String disputes = '/disputes';
  static const String disputeDetail = '/dispute/:id';
  static const String walletConnect = '/wallet-connect';
  static const String settings = '/settings';
  static const String profile = '/profile';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // ADVANCED CONSUMER ROUTES (Power Users)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String nftSwap = '/nft-swap';
  static const String crossChain = '/cross-chain';
  static const String safe = '/safe';
  static const String sessionKeys = '/session-keys';
  static const String zknaf = '/zknaf';
  
  // ═══════════════════════════════════════════════════════════════════════════
  // INSTITUTIONAL ROUTES (War Room / Embedded Next.js)
  // ═══════════════════════════════════════════════════════════════════════════
  
  static const String warRoom = '/war-room';
  static const String warRoomLanding = '/war-room-landing';
  static const String detectionStudio = '/detection-studio';
  static const String graphExplorer = '/graph-explorer';
  static const String compliance = '/compliance';
  static const String fatfRules = '/fatf-rules';
  static const String audit = '/audit';
  static const String policyEngine = '/policy-engine';
  static const String enforcement = '/enforcement';
  static const String multisigQueue = '/multisig-queue';
  static const String pendingApprovals = '/pending-approvals';
  static const String flaggedQueue = '/flagged-queue';
  static const String uiSnapshots = '/ui-snapshots';
  static const String reports = '/reports';
  static const String userManagement = '/user-management';
  static const String systemSettings = '/system-settings';
  static const String mlModels = '/ml-models';
  static const String admin = '/admin';
  static const String approver = '/approver';
  
  /// Generate dispute detail path
  static String disputeDetailFor(String id) => '/dispute/$id';
  
  /// Generate trust check with address
  static String trustCheckFor(String address) => '/trust-check?address=$address';
}

abstract class RouteNames {
  // Auth
  static const String signIn = 'sign-in';
  static const String register = 'register';
  static const String unauthorized = 'unauthorized';
  static const String selectProfile = 'select-profile';
  
  // Consumer
  static const String home = 'home';
  static const String wallet = 'wallet';
  static const String transfer = 'transfer';
  static const String trustCheck = 'trust-check';
  static const String history = 'history';
  static const String disputes = 'disputes';
  static const String disputeDetail = 'dispute-detail';
  static const String walletConnect = 'wallet-connect';
  static const String settings = 'settings';
  static const String profile = 'profile';
  
  // Advanced
  static const String nftSwap = 'nft-swap';
  static const String crossChain = 'cross-chain';
  static const String safe = 'safe';
  static const String sessionKeys = 'session-keys';
  static const String zknaf = 'zknaf';
  
  // Institutional
  static const String warRoom = 'war-room';
  static const String warRoomLanding = 'war-room-landing';
  static const String detectionStudio = 'detection-studio';
  static const String graphExplorer = 'graph-explorer';
  static const String compliance = 'compliance';
  static const String audit = 'audit';
  static const String admin = 'admin';
}
