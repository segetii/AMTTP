import 'package:flutter_riverpod/flutter_riverpod.dart';

/// User Profile Types for role-based navigation
/// Each profile has access to different sections of the app based on the sitemap
enum UserProfile {
  /// Standard end user - wallet, transfers, history, NFT swaps, disputes
  endUser,
  
  /// Administrator - full system oversight, DQN analytics, transactions, policies
  admin,
  
  /// Compliance Officer - KYC/AML tools, freeze accounts, PEP screening, EDD
  complianceOfficer,
}

/// User profile state with associated permissions and navigation items
class UserProfileState {
  final UserProfile profile;
  final String displayName;
  final String walletAddress;
  final bool isConnected;
  final List<String> permissions;

  const UserProfileState({
    this.profile = UserProfile.endUser,
    this.displayName = 'User',
    this.walletAddress = '',
    this.isConnected = false,
    this.permissions = const [],
  });

  UserProfileState copyWith({
    UserProfile? profile,
    String? displayName,
    String? walletAddress,
    bool? isConnected,
    List<String>? permissions,
  }) {
    return UserProfileState(
      profile: profile ?? this.profile,
      displayName: displayName ?? this.displayName,
      walletAddress: walletAddress ?? this.walletAddress,
      isConnected: isConnected ?? this.isConnected,
      permissions: permissions ?? this.permissions,
    );
  }

  /// Get navigation items based on user profile (sitemap implementation)
  List<NavigationItem> get navigationItems {
    switch (profile) {
      case UserProfile.endUser:
        return _endUserNavItems;
      case UserProfile.admin:
        return _adminNavItems;
      case UserProfile.complianceOfficer:
        return _complianceNavItems;
    }
  }

  /// Check if user has access to a specific route
  bool hasAccessTo(String route) {
    return navigationItems.any((item) => 
      item.route == route || 
      item.children.any((child) => child.route == route)
    );
  }
}

/// Navigation item for profile-based sitemap
class NavigationItem {
  final String title;
  final String route;
  final String icon;
  final String? badge;
  final List<NavigationItem> children;
  final bool isSection;

  const NavigationItem({
    required this.title,
    required this.route,
    required this.icon,
    this.badge,
    this.children = const [],
    this.isSection = false,
  });
}

// ==================== END USER NAVIGATION (Sitemap Profile 1) ====================
const _endUserNavItems = [
  // Main Section
  NavigationItem(
    title: 'Dashboard',
    route: '/',
    icon: 'home',
    isSection: true,
  ),
  NavigationItem(
    title: 'Wallet',
    route: '/wallet',
    icon: 'account_balance_wallet',
  ),
  
  // Transfers Section
  NavigationItem(
    title: 'Transfers',
    route: '',
    icon: 'swap_horiz',
    isSection: true,
    children: [
      NavigationItem(title: 'Send Money', route: '/transfer', icon: 'send'),
      NavigationItem(title: 'NFT Swap', route: '/nft-swap', icon: 'collections'),
      NavigationItem(title: 'Cross-Chain', route: '/cross-chain', icon: 'link'),
    ],
  ),
  
  // History & Tracking
  NavigationItem(
    title: 'History',
    route: '/history',
    icon: 'history',
  ),
  NavigationItem(
    title: 'My Disputes',
    route: '/disputes',
    icon: 'gavel',
  ),
  
  // Advanced Section
  NavigationItem(
    title: 'Advanced',
    route: '',
    icon: 'settings',
    isSection: true,
    children: [
      NavigationItem(title: 'Session Keys', route: '/session-keys', icon: 'key'),
      NavigationItem(title: 'Safe Management', route: '/safe', icon: 'security'),
      NavigationItem(title: 'Privacy (zkNAF)', route: '/zknaf', icon: 'shield'),
    ],
  ),
  
  // Settings
  NavigationItem(
    title: 'Settings',
    route: '/settings',
    icon: 'settings',
  ),
];

// ==================== ADMIN NAVIGATION (Sitemap Profile 2) ====================
const _adminNavItems = [
  // Dashboard
  NavigationItem(
    title: 'Admin Dashboard',
    route: '/admin',
    icon: 'dashboard',
    isSection: true,
  ),
  
  // User Features (inherit from end user)
  NavigationItem(
    title: 'User Features',
    route: '',
    icon: 'person',
    isSection: true,
    children: [
      NavigationItem(title: 'Home', route: '/', icon: 'home'),
      NavigationItem(title: 'Wallet', route: '/wallet', icon: 'account_balance_wallet'),
      NavigationItem(title: 'Transfer', route: '/transfer', icon: 'send'),
      NavigationItem(title: 'History', route: '/history', icon: 'history'),
    ],
  ),
  
  // Transaction Management
  NavigationItem(
    title: 'Transactions',
    route: '',
    icon: 'receipt_long',
    isSection: true,
    children: [
      NavigationItem(title: 'Approver Portal', route: '/approver', icon: 'approval'),
      NavigationItem(title: 'NFT Swaps', route: '/nft-swap', icon: 'collections'),
      NavigationItem(title: 'Cross-Chain', route: '/cross-chain', icon: 'link'),
    ],
  ),
  
  // Dispute Resolution
  NavigationItem(
    title: 'Disputes',
    route: '/disputes',
    icon: 'gavel',
    badge: '3',
  ),
  
  // Safe & Session Key Management
  NavigationItem(
    title: 'MultiSig & AA',
    route: '',
    icon: 'security',
    isSection: true,
    children: [
      NavigationItem(title: 'Safe Management', route: '/safe', icon: 'shield'),
      NavigationItem(title: 'Session Keys', route: '/session-keys', icon: 'key'),
      NavigationItem(title: 'zkNAF Privacy', route: '/zknaf', icon: 'lock'),
    ],
  ),
  
  // Compliance Tools (subset for admin)
  NavigationItem(
    title: 'Compliance',
    route: '/compliance',
    icon: 'policy',
  ),

  // FATF Rules (links to Next.js)
  NavigationItem(
    title: 'FATF Rules',
    route: '/fatf-rules',
    icon: 'public',
  ),

  // Detection Studio (Next.js)
  NavigationItem(
    title: 'Detection Studio',
    route: '/detection-studio',
    icon: 'visibility',
  ),
  
  // Settings
  NavigationItem(
    title: 'Settings',
    route: '/settings',
    icon: 'settings',
  ),
];

// ==================== COMPLIANCE OFFICER NAVIGATION (Sitemap Profile 3) ====================
const _complianceNavItems = [
  // Compliance Dashboard
  NavigationItem(
    title: 'Compliance Dashboard',
    route: '/compliance',
    icon: 'verified_user',
    isSection: true,
  ),
  
  // Account Management
  NavigationItem(
    title: 'Account Controls',
    route: '',
    icon: 'manage_accounts',
    isSection: true,
    children: [
      NavigationItem(title: 'Freeze/Unfreeze', route: '/compliance', icon: 'ac_unit'),
      NavigationItem(title: 'Trusted Users', route: '/compliance', icon: 'verified_user'),
    ],
  ),
  
  // Screening & Verification
  NavigationItem(
    title: 'Screening',
    route: '',
    icon: 'search',
    isSection: true,
    children: [
      NavigationItem(title: 'PEP/Sanctions', route: '/compliance', icon: 'policy'),
      NavigationItem(title: 'EDD Queue', route: '/compliance', icon: 'fact_check'),
    ],
  ),
  
  // Approvals
  NavigationItem(
    title: 'Approver Portal',
    route: '/approver',
    icon: 'approval',
    badge: '5',
  ),
  
  // Disputes
  NavigationItem(
    title: 'Dispute Review',
    route: '/disputes',
    icon: 'gavel',
    badge: '2',
  ),
  
  // Transaction History
  NavigationItem(
    title: 'Transaction Audit',
    route: '/history',
    icon: 'history',
  ),
  
  // Cross-Chain Monitoring
  NavigationItem(
    title: 'Cross-Chain',
    route: '/cross-chain',
    icon: 'link',
  ),

  // FATF Rules (links to Next.js)
  NavigationItem(
    title: 'FATF Rules',
    route: '/fatf-rules',
    icon: 'public',
  ),

  // Detection Studio (Next.js)
  NavigationItem(
    title: 'Detection Studio',
    route: '/detection-studio',
    icon: 'visibility',
  ),
  
  // zkNAF Zero-Knowledge Proofs
  NavigationItem(
    title: 'zkNAF Privacy Layer',
    route: '/zknaf',
    icon: 'privacy_tip',
  ),
  
  // Admin Access (if authorized)
  NavigationItem(
    title: 'Admin Panel',
    route: '/admin',
    icon: 'admin_panel_settings',
  ),
  
  // Settings
  NavigationItem(
    title: 'Settings',
    route: '/settings',
    icon: 'settings',
  ),
];

// ==================== PROVIDERS ====================

class UserProfileNotifier extends StateNotifier<UserProfileState> {
  UserProfileNotifier() : super(const UserProfileState());

  /// Set user profile after wallet connection / authentication
  void setProfile({
    required UserProfile profile,
    required String walletAddress,
    String? displayName,
    List<String>? permissions,
  }) {
    state = state.copyWith(
      profile: profile,
      walletAddress: walletAddress,
      displayName: displayName ?? _getDefaultDisplayName(profile),
      isConnected: true,
      permissions: permissions ?? _getDefaultPermissions(profile),
    );
  }

  /// Update profile type (for demo/testing purposes)
  void switchProfile(UserProfile profile) {
    state = state.copyWith(
      profile: profile,
      displayName: _getDefaultDisplayName(profile),
      permissions: _getDefaultPermissions(profile),
    );
  }

  /// Disconnect wallet and reset profile
  void disconnect() {
    state = const UserProfileState();
  }

  String _getDefaultDisplayName(UserProfile profile) {
    switch (profile) {
      case UserProfile.endUser:
        return 'User';
      case UserProfile.admin:
        return 'Administrator';
      case UserProfile.complianceOfficer:
        return 'Compliance Officer';
    }
  }

  List<String> _getDefaultPermissions(UserProfile profile) {
    switch (profile) {
      case UserProfile.endUser:
        return ['transfer', 'history', 'nft_swap', 'disputes', 'settings'];
      case UserProfile.admin:
        return ['all'];
      case UserProfile.complianceOfficer:
        return ['compliance', 'approver', 'disputes', 'history', 'admin', 'settings'];
    }
  }
}

/// Main user profile provider
final userProfileProvider = StateNotifierProvider<UserProfileNotifier, UserProfileState>((ref) {
  return UserProfileNotifier();
});

/// Provider for current navigation items based on profile
final navigationItemsProvider = Provider<List<NavigationItem>>((ref) {
  final profileState = ref.watch(userProfileProvider);
  return profileState.navigationItems;
});

/// Provider to check route access
final routeAccessProvider = Provider.family<bool, String>((ref, route) {
  final profileState = ref.watch(userProfileProvider);
  return profileState.hasAccessTo(route);
});
