/// Premium Fintech Shell - Complete Redesign
/// 
/// Inspired by Metamask, Revolut, and modern crypto wallets
/// 
/// Key Design Elements:
/// - Card-based wallet interface at top
/// - Action buttons row (Send, Receive, Swap, Buy)
/// - Token/Asset list below
/// - Floating bottom nav with blur

import 'dart:ui';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/rbac/rbac.dart';
import '../../core/rbac/role_navigation_config.dart';
import '../../core/rbac/roles.dart';
import '../../core/router/app_router.dart';
import '../../core/web3/wallet_provider.dart';
import '../widgets/platform_app_switcher.dart';

// ═══════════════════════════════════════════════════════════════════════════════
// PREMIUM FINTECH SHELL
// ═══════════════════════════════════════════════════════════════════════════════

class PremiumFintechShell extends ConsumerStatefulWidget {
  final Widget child;
  final String? currentRoute;
  final bool isPeP;

  const PremiumFintechShell({
    super.key,
    required this.child,
    this.currentRoute,
    this.isPeP = false,
  });

  @override
  ConsumerState<PremiumFintechShell> createState() => _PremiumFintechShellState();
}

class _PremiumFintechShellState extends ConsumerState<PremiumFintechShell> {
  int _currentNavIndex = 0;

  @override
  void initState() {
    super.initState();
    _updateNavIndex();
  }

  @override
  void didUpdateWidget(PremiumFintechShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentRoute != widget.currentRoute) {
      _updateNavIndex();
    }
  }

  void _updateNavIndex() {
    final route = widget.currentRoute ?? '/';
    final section = fintechSectionForRoute(route);

    switch (section) {
      case FintechSection.home:
        _currentNavIndex = 0;
        break;
      case FintechSection.wallet:
        _currentNavIndex = 1;
        break;
      case FintechSection.send:
        _currentNavIndex = 2;
        break;
      case FintechSection.activity:
        _currentNavIndex = 3;
        break;
      case FintechSection.profile:
        _currentNavIndex = 4;
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ));

    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0F),
      body: Column(
        children: [
          // Fixed platform header at top
          const CompactPlatformHeader(currentApp: 'wallet'),
          
          // Top navigation bar (moved from bottom)
          _buildTopNav(),
          
          // Main scrollable content
          Expanded(
            child: widget.child,
          ),
        ],
      ),
    );
  }

  Widget _buildTopNav() {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          decoration: BoxDecoration(
            color: const Color(0xFF0A0A0F).withOpacity(0.85),
            border: const Border(
              bottom: BorderSide(
                color: Color(0xFF1E1E2D),
                width: 1,
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildNavItem(0, Icons.home_rounded, 'Home', '/'),
                _buildNavItem(1, Icons.account_balance_wallet_rounded, 'Wallet', '/wallet'),
                _buildNavItem(2, Icons.swap_horiz_rounded, 'Send', '/transfer'),
                _buildNavItem(3, Icons.history_rounded, 'Activity', '/history'),
                _buildMoreNavItem(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomNav() {
    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).padding.bottom,
          ),
          decoration: BoxDecoration(
            color: const Color(0xFF0A0A0F).withOpacity(0.85),
            border: const Border(
              top: BorderSide(
                color: Color(0xFF1E1E2D),
                width: 1,
              ),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: [
                _buildNavItem(0, Icons.home_rounded, 'Home', '/'),
                _buildNavItem(1, Icons.account_balance_wallet_rounded, 'Wallet', '/wallet'),
                _buildNavItem(2, Icons.swap_horiz_rounded, 'Send', '/transfer'),
                _buildNavItem(3, Icons.history_rounded, 'Activity', '/history'),
                _buildMoreNavItem(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem(int index, IconData icon, String label, String route) {
    final isSelected = _currentNavIndex == index;
    
    return GestureDetector(
      onTap: () {
        if (!isSelected) {
          setState(() => _currentNavIndex = index);
          context.go(route);
        }
      },
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: 64,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: isSelected 
                    ? const Color(0xFF6366F1).withOpacity(0.2) 
                    : Colors.transparent,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                icon,
                color: isSelected 
                    ? const Color(0xFF818CF8) 
                    : const Color(0xFF64748B),
                size: 24,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                color: isSelected 
                    ? const Color(0xFF818CF8) 
                    : const Color(0xFF64748B),
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// More menu with Advanced features, Settings, etc.
  Widget _buildMoreNavItem() {
    final isSelected = _currentNavIndex == 4;
    
    return PopupMenuButton<String>(
      offset: const Offset(0, -200),
      color: const Color(0xFF1A1A2E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      onSelected: (route) {
        setState(() => _currentNavIndex = 4);
        context.go(route);
      },
      itemBuilder: (context) => [
        _buildPopupItem(Icons.rocket_launch_rounded, 'Advanced', '/advanced', 'NFT, Cross-Chain, Safe'),
        _buildPopupItem(Icons.verified_user_rounded, 'Trust Check', '/trust-check', 'Verify addresses'),
        _buildPopupItem(Icons.gavel_rounded, 'Disputes', '/disputes', 'Raise & track disputes'),
        const PopupMenuDivider(),
        _buildPopupItem(Icons.settings_rounded, 'Settings', '/settings', 'App preferences'),
        _buildPopupItem(Icons.link_rounded, 'Connect Wallet', '/wallet-connect', 'Web3 connection'),
      ],
      child: SizedBox(
        width: 64,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: isSelected 
                    ? const Color(0xFF6366F1).withOpacity(0.2) 
                    : Colors.transparent,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(
                Icons.more_horiz_rounded,
                color: isSelected 
                    ? const Color(0xFF818CF8) 
                    : const Color(0xFF64748B),
                size: 24,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'More',
              style: TextStyle(
                color: isSelected 
                    ? const Color(0xFF818CF8) 
                    : const Color(0xFF64748B),
                fontSize: 11,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  PopupMenuItem<String> _buildPopupItem(IconData icon, String title, String route, String subtitle) {
    return PopupMenuItem<String>(
      value: route,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFF6366F1).withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(icon, color: const Color(0xFF818CF8), size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                Text(subtitle, style: const TextStyle(color: Colors.white54, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HOME PAGE - Complete Redesign (Metamask/Revolut Style)
// Centralized layout with auto-scrolling carousel
// ═══════════════════════════════════════════════════════════════════════════════

class FintechHomePage extends ConsumerStatefulWidget {
  const FintechHomePage({super.key});

  @override
  ConsumerState<FintechHomePage> createState() => _FintechHomePageState();
}

class _FintechHomePageState extends ConsumerState<FintechHomePage> {
  late PageController _carouselController;
  int _currentCarouselIndex = 0;
  DateTime _lastUserInteraction = DateTime.now();
  
  @override
  void initState() {
    super.initState();
    _carouselController = PageController(viewportFraction: 0.85);
    _startAutoScroll();
  }
  
  @override
  void dispose() {
    _carouselController.dispose();
    super.dispose();
  }
  
  void _startAutoScroll() {
    Future.delayed(const Duration(seconds: 3), () {
      if (mounted) {
        final reduceMotion = MediaQuery.maybeOf(context)?.accessibleNavigation ?? false;
        if (reduceMotion) return;

        // Only auto-advance if user has been idle for at least 5 seconds
        final idleDuration = DateTime.now().difference(_lastUserInteraction);
        if (idleDuration < const Duration(seconds: 5)) {
          _startAutoScroll();
          return;
        }

        final rbacState = ref.read(rbacProvider);
        final isPeP = rbacState.role == Role.r2EndUserPep;
        final products = isPeP ? _getPepProducts() : _getStandardProducts();
        final nextIndex = (_currentCarouselIndex + 1) % products.length;
        
        _carouselController.animateToPage(
          nextIndex,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
        );
        
        setState(() => _currentCarouselIndex = nextIndex);
        _startAutoScroll();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final isPeP = rbacState.role == Role.r2EndUserPep;
    final screenWidth = MediaQuery.of(context).size.width;
    
    // Calculate max width for centralized MetaMask-style layout
    // Max content width is 624px (30% wider than original 480px)
    final maxContentWidth = screenWidth > 680 ? 624.0 : screenWidth - 40;
    final horizontalPadding = (screenWidth - maxContentWidth) / 2;
    
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            Color(0xFF0F0F1A),
            Color(0xFF0A0A0F),
          ],
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: SingleChildScrollView(
          padding: const EdgeInsets.only(bottom: 120),
          child: Center(
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxContentWidth),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Top header (network + profile)
                  _buildHeader(context, rbacState, isPeP),

                  // Hero spotlight
                  _buildHero(context, isPeP, rbacState),
                  
                  // Main wallet card
                  _buildWalletCard(context, isPeP),
                  
                  // Quick actions row
                  _buildQuickActions(context),

                  // Product carousel with auto-scroll
                  _buildProductCarousel(context, isPeP),

                  // PeP compliance strip
                  if (isPeP) _buildPepAlertStrip(context),

                  // Insights / security
                  _buildInsightsRow(context, isPeP),
                  
                  // Assets section
                  _buildAssetsSection(context),
                  
                  // Recent activity
                  _buildRecentActivity(context),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
  
  void _showScannerModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Container(
        height: MediaQuery.of(context).size.height * 0.7,
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Scan QR Code',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Scan a wallet address or payment request',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
            ),
            const SizedBox(height: 32),
            // Camera placeholder
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF0A0A0F),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFF2D2D44)),
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.camera_alt_rounded, color: Colors.white.withOpacity(0.3), size: 64),
                      const SizedBox(height: 16),
                      Text(
                        'Camera access required',
                        style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
                      ),
                      const SizedBox(height: 16),
                      GestureDetector(
                        onTap: () => Navigator.pop(context),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                          decoration: BoxDecoration(
                            color: const Color(0xFF6366F1),
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: const Text('Enable Camera', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }
  
  void _showNotificationsModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Container(
        height: MediaQuery.of(context).size.height * 0.6,
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: const Color(0xFF374151),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Notifications',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20),
            Expanded(
              child: ListView(
                children: [
                  _buildNotificationItem(
                    icon: Icons.arrow_downward_rounded,
                    iconColor: const Color(0xFF22C55E),
                    title: 'Received 0.5 ETH',
                    subtitle: 'From 0x1234...5678',
                    time: '2 min ago',
                    isNew: true,
                  ),
                  _buildNotificationItem(
                    icon: Icons.check_circle_rounded,
                    iconColor: const Color(0xFF22C55E),
                    title: 'Transaction confirmed',
                    subtitle: 'Your transfer of 1.2 ETH was successful',
                    time: '1 hour ago',
                    isNew: true,
                  ),
                  _buildNotificationItem(
                    icon: Icons.shield_rounded,
                    iconColor: const Color(0xFF6366F1),
                    title: 'Security check passed',
                    subtitle: 'Address 0xABCD verified as trusted',
                    time: 'Yesterday',
                    isNew: false,
                  ),
                  _buildNotificationItem(
                    icon: Icons.trending_up_rounded,
                    iconColor: const Color(0xFFF59E0B),
                    title: 'ETH up 5.2%',
                    subtitle: 'Your portfolio gained \$234.50',
                    time: '2 days ago',
                    isNew: false,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
  
  Widget _buildNotificationItem({
    required IconData icon,
    required Color iconColor,
    required String title,
    required String subtitle,
    required String time,
    required bool isNew,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isNew ? const Color(0xFF1A1A2E) : Colors.transparent,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2D2D44)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: iconColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: iconColor, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(title, style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600)),
                    if (isNew) ...[
                      const SizedBox(width: 8),
                      Container(
                        width: 8,
                        height: 8,
                        decoration: const BoxDecoration(
                          color: Color(0xFF6366F1),
                          shape: BoxShape.circle,
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 4),
                Text(subtitle, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
              ],
            ),
          ),
          Text(time, style: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 11)),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context, RBACState rbacState, bool isPeP) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
      child: Row(
        children: [
          // Network selector (Metamask style)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A2E),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: const Color(0xFF2D2D44)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 24,
                  height: 24,
                  decoration: BoxDecoration(
                    color: const Color(0xFF627EEA),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Center(
                    child: Text('Ξ', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold)),
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  'Ethereum',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 4),
                const Icon(Icons.keyboard_arrow_down_rounded, color: Color(0xFF64748B), size: 20),
              ],
            ),
          ),
          
          const Spacer(),
          
          // Primary CTA shortcuts
          ElevatedButton.icon(
            onPressed: () => context.go('/trust'),
            icon: const Icon(Icons.verified_user, size: 18),
            label: const Text('Trust check'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF6366F1),
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
          const SizedBox(width: 10),
          OutlinedButton.icon(
            onPressed: () => context.go('/transfer'),
            icon: const Icon(Icons.send_rounded, size: 18),
            label: const Text('Send'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.white,
              side: const BorderSide(color: Color(0xFF6366F1)),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
          const SizedBox(width: 12),

          // Consolidated secondary actions
          _buildIconButton(
            icon: Icons.more_horiz,
            onTap: () => _showMoreActions(context),
          ),
          const SizedBox(width: 12),

          // Profile
          GestureDetector(
            onTap: () => context.go('/profile'),
            child: Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: isPeP
                      ? [const Color(0xFFFB923C), const Color(0xFFF97316)]
                      : [const Color(0xFF6366F1), const Color(0xFF8B5CF6)],
                ),
                borderRadius: BorderRadius.circular(21),
                boxShadow: [
                  BoxShadow(
                    color: (isPeP ? const Color(0xFFF97316) : const Color(0xFF6366F1)).withOpacity(0.35),
                    blurRadius: 16,
                    offset: const Offset(0, 8),
                  ),
                ],
              ),
              child: Center(
                child: Text(
                  rbacState.displayName.isNotEmpty 
                      ? rbacState.displayName[0].toUpperCase() 
                      : 'U',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _showMoreActions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return Container(
          padding: const EdgeInsets.all(20),
          decoration: const BoxDecoration(
            color: Color(0xFF12121A),
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 36,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 16),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E1E2E),
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ],
              ),
              ListTile(
                leading: const Icon(Icons.notifications_none_rounded, color: Colors.white),
                title: const Text('Notifications', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Compliance and security alerts', style: TextStyle(color: Color(0xFF9CA3AF))),
                onTap: () {
                  Navigator.pop(ctx);
                  _showNotificationsModal(context);
                },
              ),
              ListTile(
                leading: const Icon(Icons.qr_code_scanner_rounded, color: Colors.white),
                title: const Text('Scan QR', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Move scanner into flows when needed', style: TextStyle(color: Color(0xFF9CA3AF))),
                onTap: () {
                  Navigator.pop(ctx);
                  _showScannerModal(context);
                },
              ),
              ListTile(
                leading: const Icon(Icons.settings_outlined, color: Colors.white),
                title: const Text('Preferences', style: TextStyle(color: Colors.white)),
                subtitle: const Text('Network, limits, accessibility', style: TextStyle(color: Color(0xFF9CA3AF))),
                onTap: () {
                  Navigator.pop(ctx);
                  context.go('/settings');
                },
              ),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }

  Widget _buildHero(BuildContext context, bool isPeP, RBACState rbacState) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 20, 12),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: isPeP
                ? [const Color(0xFF1F0A0A), const Color(0xFF0F0A0A)]
                : [const Color(0xFF131326), const Color(0xFF0B0B1A)],
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: Colors.white.withOpacity(0.04)),
          boxShadow: [
            BoxShadow(
              color: (isPeP ? const Color(0xFFF97316) : const Color(0xFF6366F1)).withOpacity(0.25),
              blurRadius: 28,
              offset: const Offset(0, 16),
            ),
          ],
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  colors: isPeP
                      ? [const Color(0xFFFB923C), const Color(0xFFF97316)]
                      : [const Color(0xFF6366F1), const Color(0xFF8B5CF6)],
                ),
              ),
              child: Icon(
                isPeP ? Icons.shield_outlined : Icons.auto_graph,
                color: Colors.white,
                size: 26,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        isPeP ? 'Enhanced due diligence enabled' : 'Smart wallet overview',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: (isPeP ? const Color(0xFFF97316) : const Color(0xFF22C55E)).withOpacity(0.14),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              isPeP ? Icons.shield : Icons.check_circle,
                              color: isPeP ? const Color(0xFFF97316) : const Color(0xFF22C55E),
                              size: 14,
                            ),
                            const SizedBox(width: 6),
                            Text(
                              isPeP ? 'PEP MONITORING' : 'TRUSTED',
                              style: TextStyle(
                                color: isPeP ? const Color(0xFFF97316) : const Color(0xFF22C55E),
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.6,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Text(
                    isPeP
                        ? 'Politically exposed user • Continuous screening + higher velocity checks active.'
                        : 'Multi-chain balance, smart actions, and live portfolio signals at a glance.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.6),
                      fontSize: 14,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      _buildHeroChip(
                        icon: Icons.timeline_rounded,
                        label: isPeP ? 'Enhanced monitoring' : 'Live insights',
                      ),
                      const SizedBox(width: 10),
                      _buildHeroChip(
                        icon: isPeP ? Icons.policy_rounded : Icons.flash_on_rounded,
                        label: isPeP ? 'Compliance guardrails' : 'Gas-optimized',
                      ),
                      const SizedBox(width: 10),
                      _buildHeroChip(
                        icon: Icons.lock_clock_rounded,
                        label: isPeP ? 'Screening every 30m' : 'Secure by default',
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeroChip({required IconData icon, required String label}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: const Color(0xFF94A3B8), size: 16),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFFCBD5E1),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPepAlertStrip(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 20, 12),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF1C0F0A),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFFF97316).withOpacity(0.4)),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFFF97316).withOpacity(0.15),
              blurRadius: 20,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: const Color(0xFFF97316).withOpacity(0.14),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Icon(Icons.shield_outlined, color: Color(0xFFF97316), size: 20),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'PEP monitoring active',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Higher scrutiny on inbound/outbound transfers. Velocity limits and sanctions screening enforced.',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.65),
                      fontSize: 12,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF0F172A),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFF97316).withOpacity(0.4)),
              ),
              child: const Text(
                'Enhanced KYC',
                style: TextStyle(
                  color: Color(0xFFF97316),
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInsightsRow(BuildContext context, bool isPeP) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 20, 10),
      child: Row(
        children: [
          Expanded(
            flex: 3,
            child: _buildInsightCard(
              title: isPeP ? 'Risk score' : 'Portfolio alpha',
              value: isPeP ? 'Low • 18%' : '+12.4%',
              accent: isPeP ? const Color(0xFFF97316) : const Color(0xFF22C55E),
              subtitle: isPeP ? 'Last scan • 5m ago' : 'Beating benchmark',
              chartColor: isPeP ? const Color(0xFFF97316) : const Color(0xFF22C55E),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            flex: 4,
            child: _buildInsightCard(
              title: isPeP ? 'Controls' : 'Insights',
              value: isPeP ? 'Velocity: 2.5k/day' : '2 signals',
              accent: isPeP ? const Color(0xFFF97316) : const Color(0xFF6366F1),
              subtitle: isPeP ? 'Manual review above 10k' : 'Gas saving + ARB yield',
              chartColor: isPeP ? const Color(0xFFF97316) : const Color(0xFF6366F1),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInsightCard({
    required String title,
    required String value,
    required Color accent,
    required String subtitle,
    required Color chartColor,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0F172A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.04)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 28,
                height: 28,
                decoration: BoxDecoration(
                  color: accent.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(Icons.analytics_outlined, color: accent, size: 16),
              ),
              const SizedBox(width: 10),
              Text(
                title,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: TextStyle(
              color: accent,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            subtitle,
            style: const TextStyle(
              color: Color(0xFF94A3B8),
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 14),
          Container(
            height: 4,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [accent.withOpacity(0.5), chartColor],
              ),
              borderRadius: BorderRadius.circular(10),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildIconButton({
    required IconData icon,
    bool badge = false,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A2E),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: const Color(0xFF2D2D44)),
        ),
        child: Stack(
          children: [
            Center(child: Icon(icon, color: const Color(0xFF94A3B8), size: 22)),
            if (badge)
              Positioned(
                top: 8,
                right: 8,
                child: Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: Color(0xFFEF4444),
                    shape: BoxShape.circle,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildWalletCard(BuildContext context, bool isPeP) {
    // Get real wallet data from provider
    final walletState = ref.watch(walletProvider);
    final isConnected = walletState.isConnected;
    final address = walletState.address ?? '';
    final ethBalance = walletState.ethBalance ?? 0.0;
    
    // Format address for display
    final formattedAddress = address.length > 10 
        ? '${address.substring(0, 6)}...${address.substring(address.length - 4)}'
        : address;
    
    // Format balance (ETH value, not USD for now)
    final balanceWhole = ethBalance.floor();
    final balanceDecimal = ((ethBalance - balanceWhole) * 100).round().toString().padLeft(2, '0');
    
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF1E1E3F),
              Color(0xFF0F0F2D),
            ],
          ),
          borderRadius: BorderRadius.circular(24),
          border: Border.all(
            color: const Color(0xFF2D2D5A).withOpacity(0.5),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF6366F1).withOpacity(0.1),
              blurRadius: 40,
              offset: const Offset(0, 20),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Card header - show connection status based on real wallet state
            Row(
              children: [
                if (isConnected)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: const Color(0xFF22C55E).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.check_circle, color: Color(0xFF22C55E), size: 14),
                        SizedBox(width: 4),
                        Text(
                          'Connected',
                          style: TextStyle(
                            color: Color(0xFF22C55E),
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  )
                else
                  GestureDetector(
                    onTap: () => ref.read(walletProvider.notifier).connectWallet(),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: const Color(0xFF6366F1).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.account_balance_wallet, color: Color(0xFF6366F1), size: 14),
                          SizedBox(width: 4),
                          Text(
                            'Connect Wallet',
                            style: TextStyle(
                              color: Color(0xFF6366F1),
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                const Spacer(),
                if (isConnected)
                  GestureDetector(
                  onTap: () {
                    Clipboard.setData(ClipboardData(text: address));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Address copied!'), backgroundColor: Color(0xFF22C55E)),
                    );
                  },
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        formattedAddress,
                        style: const TextStyle(
                          color: Color(0xFF94A3B8),
                          fontSize: 12,
                          fontFamily: 'monospace',
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.05),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(
                          Icons.copy_rounded,
                          color: Color(0xFF64748B),
                          size: 18,
                        ),
                      ),
                    ],
                  ),
                ),
                if (isPeP) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF97316).withOpacity(0.18),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: const Color(0xFFF97316).withOpacity(0.35)),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.shield_outlined, color: Color(0xFFF97316), size: 16),
                        SizedBox(width: 6),
                        Text(
                          'PEP WATCH',
                          style: TextStyle(
                            color: Color(0xFFF97316),
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
            
            const SizedBox(height: 32),
            
            // Balance label
            Text(
              isConnected ? 'ETH Balance' : 'Connect to View Balance',
              style: const TextStyle(
                color: Color(0xFF94A3B8),
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 8),
            
            // Balance amount - show real ETH balance
            if (isConnected)
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    ethBalance.toStringAsFixed(4),
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 44,
                      fontWeight: FontWeight.bold,
                      letterSpacing: -2,
                      height: 1,
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(bottom: 6, left: 8),
                    child: Text(
                      'ETH',
                      style: TextStyle(
                        color: Color(0xFF64748B),
                        fontSize: 24,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ],
              )
            else
              GestureDetector(
                onTap: () => ref.read(walletProvider.notifier).connectWallet(),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.account_balance_wallet, color: Colors.white, size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Connect MetaMask',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            
            const SizedBox(height: 16),
            
            // Network indicator (only show when connected)
            if (isConnected)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFF6366F1).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.circle, color: Color(0xFF22C55E), size: 8),
                    SizedBox(width: 6),
                    Text(
                      'Sepolia Testnet',
                      style: TextStyle(
                        color: Color(0xFF818CF8),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          Expanded(child: _buildActionButton(
            context,
            icon: Icons.arrow_upward_rounded,
            label: 'Send',
            gradient: const [Color(0xFF6366F1), Color(0xFF8B5CF6)],
            onTap: () => context.go('/transfer'),
          )),
          const SizedBox(width: 12),
          Expanded(child: _buildActionButton(
            context,
            icon: Icons.arrow_downward_rounded,
            label: 'Receive',
            gradient: const [Color(0xFF22C55E), Color(0xFF16A34A)],
            onTap: () => _showReceiveModal(context),
          )),
          const SizedBox(width: 12),
          Expanded(child: _buildActionButton(
            context,
            icon: Icons.swap_horiz_rounded,
            label: 'Swap',
            gradient: const [Color(0xFFF59E0B), Color(0xFFD97706)],
            onTap: () => context.go('/nft-swap'),
          )),
          const SizedBox(width: 12),
          Expanded(child: _buildActionButton(
            context,
            icon: Icons.add_rounded,
            label: 'Buy',
            gradient: const [Color(0xFF06B6D4), Color(0xFF0891B2)],
            onTap: () => _showBuyModal(context),
          )),
        ],
      ),
    );
  }
  
  void _showReceiveModal(BuildContext context) {
    final walletState = ref.read(walletProvider);
    final address = walletState.address ?? '';
    final formattedAddress = address.length > 10 
        ? '${address.substring(0, 6)}...${address.substring(address.length - 4)}'
        : address;
    
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Receive',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
              ),
              child: Column(
                children: [
                  // QR Code placeholder - shows address
                  Container(
                    width: 180,
                    height: 180,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      border: Border.all(color: const Color(0xFF1E1E2E)),
                    ),
                    child: address.isNotEmpty
                        ? const Center(
                            child: Icon(Icons.qr_code_rounded, size: 160, color: Color(0xFF0A0A0F)),
                          )
                        : const Center(
                            child: Text('Connect wallet first', style: TextStyle(color: Colors.grey)),
                          ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      address.isNotEmpty ? formattedAddress : 'No wallet connected',
                      style: const TextStyle(color: Colors.white, fontSize: 16, fontFamily: 'monospace'),
                    ),
                  ),
                  if (address.isNotEmpty)
                    GestureDetector(
                      onTap: () {
                        Clipboard.setData(ClipboardData(text: address));
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Address copied!'), backgroundColor: Color(0xFF22C55E)),
                        );
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF6366F1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Text('Copy', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                      ),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }
  
  void _showBuyModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Buy Crypto',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Purchase crypto with card or bank transfer',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
            ),
            const SizedBox(height: 24),
            _buildBuyOption(
              icon: Icons.credit_card_rounded,
              title: 'Card Payment',
              subtitle: 'Visa, Mastercard • Instant',
              color: const Color(0xFF6366F1),
            ),
            const SizedBox(height: 12),
            _buildBuyOption(
              icon: Icons.account_balance_rounded,
              title: 'Bank Transfer',
              subtitle: 'SEPA, Wire • 1-2 days',
              color: const Color(0xFF22C55E),
            ),
            const SizedBox(height: 12),
            _buildBuyOption(
              icon: Icons.apple,
              title: 'Apple Pay',
              subtitle: 'Fast & Secure',
              color: const Color(0xFF64748B),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }
  
  Widget _buildBuyOption({
    required IconData icon,
    required String title,
    required String subtitle,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF2D2D44)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w600)),
                Text(subtitle, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: Color(0xFF64748B)),
        ],
      ),
    );
  }

  Widget _buildActionButton(
    BuildContext context, {
    required IconData icon,
    required String label,
    required List<Color> gradient,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A2E),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFF2D2D44)),
        ),
        child: Column(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: gradient),
                borderRadius: BorderRadius.circular(14),
                boxShadow: [
                  BoxShadow(
                    color: gradient[0].withOpacity(0.3),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(height: 10),
            Text(
              label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildProductCarousel(BuildContext context, bool isPeP) {
    final products = isPeP ? _getPepProducts() : _getStandardProducts();
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Discover',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              Row(
                children: List.generate(products.length, (i) => GestureDetector(
                  onTap: () {
                    _lastUserInteraction = DateTime.now();
                    _carouselController.animateToPage(
                      i,
                      duration: const Duration(milliseconds: 350),
                      curve: Curves.easeInOut,
                    );
                  },
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    width: i == _currentCarouselIndex ? 20 : 8,
                    height: 8,
                    margin: const EdgeInsets.only(left: 4),
                    decoration: BoxDecoration(
                      color: i == _currentCarouselIndex 
                          ? (isPeP ? const Color(0xFFF97316) : const Color(0xFF6366F1))
                          : const Color(0xFF374151),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                )),
              ),
            ],
          ),
        ),
        SizedBox(
          height: 180,
          child: Listener(
            onPointerDown: (_) {
              // Treat any pointer interaction as user activity to pause auto-scroll
              _lastUserInteraction = DateTime.now();
            },
            child: PageView.builder(
              controller: _carouselController,
              onPageChanged: (index) {
                _lastUserInteraction = DateTime.now();
                setState(() => _currentCarouselIndex = index);
              },
              itemCount: products.length,
              itemBuilder: (context, index) {
                final product = products[index];
                return _buildProductCard(
                  context,
                  icon: product['icon'] as IconData,
                  title: product['title'] as String,
                  description: product['description'] as String,
                  gradient: product['gradient'] as List<Color>,
                  route: product['route'] as String,
                  cta: product['cta'] as String,
                );
              },
            ),
          ),
        ),
      ],
    );
  }

  List<Map<String, dynamic>> _getStandardProducts() {
    return [
      {
        'icon': Icons.lock_outline_rounded,
        'title': 'zkNAF Privacy',
        'description': 'Zero-knowledge proof transfers for ultimate financial privacy',
        'gradient': [const Color(0xFF6366F1), const Color(0xFF8B5CF6)],
        'route': '/zknaf',
        'cta': 'Try Now',
      },
      {
        'icon': Icons.flash_on_rounded,
        'title': 'Session Keys',
        'description': 'Gas-free transactions with ERC-4337 smart accounts',
        'gradient': [const Color(0xFF22C55E), const Color(0xFF14B8A6)],
        'route': '/session-keys',
        'cta': 'Enable',
      },
      {
        'icon': Icons.language_rounded,
        'title': 'Cross-Chain',
        'description': 'Bridge assets across 12+ networks instantly',
        'gradient': [const Color(0xFFF59E0B), const Color(0xFFEF4444)],
        'route': '/cross-chain',
        'cta': 'Bridge',
      },
      {
        'icon': Icons.account_balance_rounded,
        'title': 'Safe Multisig',
        'description': 'Enterprise-grade custody with Gnosis Safe',
        'gradient': [const Color(0xFF06B6D4), const Color(0xFF3B82F6)],
        'route': '/safe',
        'cta': 'Create Safe',
      },
    ];
  }

  List<Map<String, dynamic>> _getPepProducts() {
    return [
      {
        'icon': Icons.verified_user_outlined,
        'title': 'Enhanced Screening',
        'description': 'Real-time sanctions & watchlist verification',
        'gradient': [const Color(0xFFF97316), const Color(0xFFEF4444)],
        'route': '/trust-check',
        'cta': 'View Status',
      },
      {
        'icon': Icons.speed_rounded,
        'title': 'Velocity Controls',
        'description': 'Smart transaction limits protect your account',
        'gradient': [const Color(0xFFF59E0B), const Color(0xFFF97316)],
        'route': '/settings',
        'cta': 'Configure',
      },
      {
        'icon': Icons.history_rounded,
        'title': 'Audit Trail',
        'description': 'Complete transaction history for compliance',
        'gradient': [const Color(0xFF8B5CF6), const Color(0xFFA855F7)],
        'route': '/history',
        'cta': 'View History',
      },
      {
        'icon': Icons.group_outlined,
        'title': 'Approved Contacts',
        'description': 'Pre-verified counterparties for faster transfers',
        'gradient': [const Color(0xFF22C55E), const Color(0xFF14B8A6)],
        'route': '/settings',
        'cta': 'Manage',
      },
    ];
  }

  Widget _buildProductCard(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String description,
    required List<Color> gradient,
    required String route,
    required String cta,
  }) {
    return GestureDetector(
      onTap: () => context.go(route),
      child: Container(
        margin: const EdgeInsets.only(right: 12, bottom: 8),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              gradient[0].withOpacity(0.2),
              gradient[1].withOpacity(0.1),
            ],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: gradient[0].withOpacity(0.3),
          ),
          boxShadow: [
            BoxShadow(
              color: gradient[0].withOpacity(0.2),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                gradient: LinearGradient(colors: gradient),
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(height: 16),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              description,
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
                fontSize: 13,
                height: 1.4,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            const Spacer(),
            Row(
              children: [
                Text(
                  cta,
                  style: TextStyle(
                    color: gradient[0],
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 4),
                Icon(Icons.arrow_forward_rounded, color: gradient[0], size: 16),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSecurityBanner(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: GestureDetector(
        onTap: () => context.go('/trust-check'),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                const Color(0xFF22C55E).withOpacity(0.1),
                const Color(0xFF22C55E).withOpacity(0.05),
              ],
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFF22C55E).withOpacity(0.2),
            ),
          ),
          child: Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: const Color(0xFF22C55E).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.shield_rounded,
                  color: Color(0xFF22C55E),
                  size: 24,
                ),
              ),
              const SizedBox(width: 14),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Trust Check Active',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: 2),
                    Text(
                      'All transactions are verified',
                      style: TextStyle(
                        color: Color(0xFF94A3B8),
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(
                Icons.chevron_right_rounded,
                color: Color(0xFF64748B),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAssetsSection(BuildContext context) {
    // Get real wallet data
    final walletState = ref.watch(walletProvider);
    final isConnected = walletState.isConnected;
    final ethBalance = walletState.ethBalance ?? 0.0;
    
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Assets',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Spacer(),
              if (isConnected)
                GestureDetector(
                  onTap: () => ref.read(walletProvider.notifier).refreshBalance(),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1A1A2E),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.refresh_rounded, color: Color(0xFF818CF8), size: 16),
                        SizedBox(width: 4),
                        Text(
                          'Refresh',
                          style: TextStyle(
                            color: Color(0xFF818CF8),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 16),
          
          // Asset items - show real balance if connected
          if (isConnected) ...[
            _buildAssetItem(
              symbol: 'ETH',
              name: 'Ethereum (Sepolia)',
              balance: ethBalance.toStringAsFixed(6),
              value: 'Testnet',
              change: '',
              isPositive: true,
              color: const Color(0xFF627EEA),
              icon: 'Ξ',
            ),
          ] else ...[
            // Show placeholder when not connected
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: const Color(0xFF2D2D44)),
              ),
              child: Column(
                children: [
                  const Icon(
                    Icons.account_balance_wallet_outlined,
                    color: Color(0xFF64748B),
                    size: 48,
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'Connect your wallet to view assets',
                    style: TextStyle(
                      color: Color(0xFF94A3B8),
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 16),
                  GestureDetector(
                    onTap: () => ref.read(walletProvider.notifier).connectWallet(),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                        ),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: const Text(
                        'Connect Wallet',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildAssetItem({
    required String symbol,
    required String name,
    required String balance,
    required String value,
    required String change,
    required bool isPositive,
    required Color color,
    required String icon,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF2D2D44)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(
                icon,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  symbol,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  name,
                  style: const TextStyle(
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                value,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '$balance $symbol',
                    style: const TextStyle(
                      color: Color(0xFF64748B),
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    decoration: BoxDecoration(
                      color: isPositive 
                          ? const Color(0xFF22C55E).withOpacity(0.1)
                          : const Color(0xFFEF4444).withOpacity(0.1),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      change,
                      style: TextStyle(
                        color: isPositive 
                            ? const Color(0xFF22C55E)
                            : const Color(0xFFEF4444),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRecentActivity(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Text(
                'Recent Activity',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => context.go('/history'),
                child: const Text(
                  'See All',
                  style: TextStyle(
                    color: Color(0xFF818CF8),
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          
          _buildActivityItem(
            icon: Icons.arrow_upward_rounded,
            iconBg: const Color(0xFF6366F1),
            title: 'Sent ETH',
            subtitle: 'To 0xabcd...efgh',
            amount: '-0.5 ETH',
            time: '2 hours ago',
            isNegative: true,
          ),
          const SizedBox(height: 12),
          _buildActivityItem(
            icon: Icons.arrow_downward_rounded,
            iconBg: const Color(0xFF22C55E),
            title: 'Received USDC',
            subtitle: 'From 0x1234...5678',
            amount: '+500 USDC',
            time: 'Yesterday',
            isNegative: false,
          ),
          const SizedBox(height: 12),
          _buildActivityItem(
            icon: Icons.swap_horiz_rounded,
            iconBg: const Color(0xFFF59E0B),
            title: 'Swapped',
            subtitle: 'ETH → USDC',
            amount: '1.2 ETH',
            time: '3 days ago',
            isNegative: false,
          ),
        ],
      ),
    );
  }

  Widget _buildActivityItem({
    required IconData icon,
    required Color iconBg,
    required String title,
    required String subtitle,
    required String amount,
    required String time,
    required bool isNegative,
  }) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF2D2D44)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: iconBg.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: iconBg, size: 22),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  subtitle,
                  style: const TextStyle(
                    color: Color(0xFF64748B),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                amount,
                style: TextStyle(
                  color: isNegative ? Colors.white : const Color(0xFF22C55E),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Text(
                time,
                style: const TextStyle(
                  color: Color(0xFF64748B),
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
