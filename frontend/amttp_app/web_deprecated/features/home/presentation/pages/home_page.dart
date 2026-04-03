/// @deprecated — This file is DEAD CODE. All R1/R2 routing now uses
/// [FintechHomePage] in `shared/shells/premium_fintech_shell.dart`.
/// Retained for reference only. Safe to delete.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'dart:ui';
import '../../../../core/web3/wallet_provider.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/secure_transfer_widget.dart';
import '../../../../shared/widgets/risk_visualizer_widget.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with TickerProviderStateMixin {
  late TabController _tabController;
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) {
        setState(() {
          _selectedIndex = _tabController.index;
        });
      }
    });
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _fadeAnimation = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeOut),
    );
    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(
        parent: _animationController, curve: Curves.easeOutCubic));
    _animationController.forward();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _animationController.dispose();
    super.dispose();
  }

  int _selectedIndex = 0;

  void _onNavItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
      _tabController.animateTo(index);
    });
  }

  @override
  Widget build(BuildContext context) {
    final walletState = ref.watch(walletProvider);

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: SafeArea(
          child: walletState.isConnected
              ? _buildMainContent(walletState)
              : _buildWelcomeScreen(),
        ),
      ),
      bottomNavigationBar:
          walletState.isConnected ? _buildBottomNavBar() : null,
    );
  }

  Widget _buildBottomNavBar() {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, -5),
          ),
        ],
      ),
      child: BottomNavigationBar(
        currentIndex: _selectedIndex,
        onTap: (index) {
          setState(() {
            _selectedIndex = index;
            _tabController.animateTo(index);
          });
        },
        type: BottomNavigationBarType.fixed,
        backgroundColor: AppTheme.darkCard,
        selectedItemColor: AppTheme.primaryPurple,
        unselectedItemColor: AppTheme.textLight,
        selectedLabelStyle:
            const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        unselectedLabelStyle: const TextStyle(fontSize: 11),
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.send_rounded),
            label: 'Send',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.history_rounded),
            label: 'History',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.analytics_rounded),
            label: 'Analytics',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.shield_rounded),
            label: 'Security',
          ),
        ],
      ),
    );
  }

  Widget _buildWelcomeScreen() {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Animated background orbs - already has IgnorePointer built in
        _buildBackgroundOrbs(),

        // Main content
        SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: FadeTransition(
            opacity: _fadeAnimation,
            child: SlideTransition(
              position: _slideAnimation,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const SizedBox(height: 40),

                  // Animated Logo
                  _buildAnimatedLogo(),

                  const SizedBox(height: 40),

                  // Welcome Title with Gradient
                  ShaderMask(
                    shaderCallback: (bounds) => const LinearGradient(
                      colors: [
                        AppTheme.cleanWhite,
                        AppTheme.primaryPurpleLight
                      ],
                    ).createShader(bounds),
                    child: Text(
                      'Advanced Money\nTransfer Protocol',
                      textAlign: TextAlign.center,
                      style:
                          Theme.of(context).textTheme.headlineLarge?.copyWith(
                                color: AppTheme.cleanWhite,
                                fontWeight: FontWeight.w800,
                                fontSize: 36,
                                height: 1.2,
                                letterSpacing: -1,
                              ),
                    ),
                  ),

                  const SizedBox(height: 20),

                  // Subtitle
                  Text(
                    'Next-generation blockchain security\nwith AI-powered fraud detection',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                          color: AppTheme.textLight,
                          height: 1.6,
                          fontSize: 16,
                        ),
                  ),

                  const SizedBox(height: 48),

                  // Feature Cards
                  _buildFeatureCards(),

                  const SizedBox(height: 48),

                  // Modern Wallet Connection
                  _buildModernWalletConnect(),

                  const SizedBox(height: 32),

                  // Quick Navigation Links
                  _buildQuickLinks(),

                  const SizedBox(height: 32),

                  // Trust Badges
                  _buildTrustBadges(),

                  const SizedBox(height: 40),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBackgroundOrbs() {
    return Positioned.fill(
      child: IgnorePointer(
        child: Stack(
          children: [
            Positioned(
              top: -100,
              right: -100,
              child: Container(
                width: 300,
                height: 300,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      AppTheme.primaryPurple.withOpacity(0.3),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              bottom: 100,
              left: -150,
              child: Container(
                width: 400,
                height: 400,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      AppTheme.accentCyan.withOpacity(0.2),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAnimatedLogo() {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0.8, end: 1.0),
      duration: const Duration(seconds: 2),
      curve: Curves.elasticOut,
      builder: (context, value, child) {
        return Transform.scale(
          scale: value,
          child: Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(32),
              gradient: AppTheme.primaryGradient,
              boxShadow: AppTheme.glowShadow,
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Outer glow ring
                Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(26),
                    border: Border.all(
                      color: AppTheme.cleanWhite.withOpacity(0.3),
                      width: 2,
                    ),
                  ),
                ),
                const Icon(
                  Icons.security_rounded,
                  size: 56,
                  color: AppTheme.cleanWhite,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFeatureCards() {
    return Row(
      children: [
        Expanded(
            child: _buildFeatureCard(
          Icons.shield_outlined,
          'AI Protection',
          'Real-time fraud detection',
          AppTheme.primaryPurple,
        )),
        const SizedBox(width: 12),
        Expanded(
            child: _buildFeatureCard(
          Icons.speed_rounded,
          'Instant',
          'Sub-second transfers',
          AppTheme.accentCyan,
        )),
        const SizedBox(width: 12),
        Expanded(
            child: _buildFeatureCard(
          Icons.verified_rounded,
          'Compliant',
          'FCA regulated',
          AppTheme.successGreen,
        )),
      ],
    );
  }

  Widget _buildFeatureCard(
      IconData icon, String title, String subtitle, Color color) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(20),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.glassWhite,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: AppTheme.cleanWhite.withOpacity(0.2),
            ),
          ),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: color, size: 28),
              ),
              const SizedBox(height: 12),
              Text(
                title,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                subtitle,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.7),
                  fontSize: 11,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildModernWalletConnect() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [
            AppTheme.cleanWhite.withOpacity(0.15),
            AppTheme.cleanWhite.withOpacity(0.05),
          ],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(
          color: AppTheme.cleanWhite.withOpacity(0.2),
        ),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.premiumGold.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(
                  Icons.workspace_premium,
                  color: AppTheme.premiumGold,
                  size: 20,
                ),
              ),
              const SizedBox(width: 8),
              const Text(
                'Premium Access',
                style: TextStyle(
                  color: AppTheme.premiumGold,
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          const Text(
            'Connect Your Wallet',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: FontWeight.w700,
              fontSize: 24,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Secure connection with MetaMask or WalletConnect',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.7),
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 28),

          // Show loading or error state
          Consumer(
            builder: (context, ref, child) {
              final walletState = ref.watch(walletProvider);

              if (walletState.isConnecting) {
                return Container(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    children: [
                      const CircularProgressIndicator(
                        color: AppTheme.primaryPurple,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        'Connecting to MetaMask...',
                        style: TextStyle(
                          color: AppTheme.cleanWhite.withOpacity(0.8),
                          fontSize: 14,
                        ),
                      ),
                    ],
                  ),
                );
              }

              if (walletState.hasError && walletState.error != null) {
                return Container(
                  padding: const EdgeInsets.all(16),
                  margin: const EdgeInsets.only(bottom: 16),
                  decoration: BoxDecoration(
                    color: AppTheme.dangerRed.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                    border:
                        Border.all(color: AppTheme.dangerRed.withOpacity(0.5)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.error_outline,
                          color: AppTheme.dangerRed),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          walletState.error!,
                          style: const TextStyle(
                            color: AppTheme.dangerRed,
                            fontSize: 13,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              }

              return const SizedBox.shrink();
            },
          ),

          // MetaMask Button
          ElevatedButton(
            onPressed: () {
              debugPrint('MetaMask button pressed!');
              ref.read(walletProvider.notifier).connectWallet();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFFF6851B),
              foregroundColor: Colors.white,
              minimumSize: const Size(double.infinity, 56),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              elevation: 8,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: const [
                Icon(Icons.account_balance_wallet_rounded, size: 24),
                SizedBox(width: 12),
                Text(
                  'MetaMask',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 16,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // WalletConnect Button
          ElevatedButton(
            onPressed: () {
              debugPrint('WalletConnect button pressed!');
              ref.read(walletProvider.notifier).connectWallet();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.infoBlue,
              foregroundColor: Colors.white,
              minimumSize: const Size(double.infinity, 56),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
              ),
              elevation: 8,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: const [
                Icon(Icons.qr_code_scanner_rounded, size: 24),
                SizedBox(width: 12),
                Text(
                  'WalletConnect',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 16,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 20),

          // Explore Demo Button
          TextButton(
            onPressed: () {
              debugPrint('Explore Demo pressed');
              context.push('/transfer');
            },
            child: Text(
              'Explore Demo →',
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.8),
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickLinks() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite.withOpacity(0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
      ),
      child: Column(
        children: [
          const Text(
            'Quick Links',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: FontWeight.w700,
              fontSize: 18,
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              Expanded(
                child: _buildLinkButton(
                  Icons.send_rounded,
                  'Transfer',
                  '/transfer',
                  AppTheme.primaryPurple,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildLinkButton(
                  Icons.history_rounded,
                  'History',
                  '/history',
                  AppTheme.infoBlue,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _buildLinkButton(
                  Icons.account_balance_wallet_rounded,
                  'Wallet',
                  '/wallet',
                  AppTheme.successGreen,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _buildLinkButton(
                  Icons.admin_panel_settings_rounded,
                  'Admin',
                  '/admin',
                  AppTheme.warningOrange,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildLinkButton(
      IconData icon, String label, String route, Color color) {
    return ElevatedButton(
      onPressed: () {
        debugPrint('Navigating to $route');
        context.push(route);
      },
      style: ElevatedButton.styleFrom(
        backgroundColor: color.withOpacity(0.2),
        foregroundColor: color,
        padding: const EdgeInsets.symmetric(vertical: 16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: color.withOpacity(0.3)),
        ),
        elevation: 0,
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 20),
          const SizedBox(width: 8),
          Text(
            label,
            style: const TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConnectButton(
      String label, IconData icon, Gradient gradient, VoidCallback onTap) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Ink(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 16),
          decoration: BoxDecoration(
            gradient: gradient,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2),
                blurRadius: 15,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: AppTheme.cleanWhite, size: 24),
              const SizedBox(width: 12),
              Text(
                label,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontWeight: FontWeight.w600,
                  fontSize: 16,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTrustBadges() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        _buildTrustBadge(Icons.lock_rounded, 'AES-256'),
        const SizedBox(width: 24),
        _buildTrustBadge(Icons.verified_user_rounded, 'SOC 2'),
        const SizedBox(width: 24),
        _buildTrustBadge(Icons.security_rounded, 'GDPR'),
      ],
    );
  }

  Widget _buildTrustBadge(IconData icon, String label) {
    return Column(
      children: [
        Icon(icon, color: AppTheme.textLight, size: 20),
        const SizedBox(height: 4),
        Text(
          label,
          style: TextStyle(
            color: AppTheme.cleanWhite.withOpacity(0.5),
            fontSize: 11,
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildMainContent(WalletState walletState) {
    return Stack(
      fit: StackFit.expand,
      children: [
        // Background gradient orbs - already has IgnorePointer built in
        _buildBackgroundOrbs(),

        // Main content column
        Column(
          children: [
            // Modern App Bar
            _buildModernAppBar(walletState),

            // Balance Card
            _buildModernBalanceCard(walletState),

            // Tab Content
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: AppTheme.darkCard,
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(32),
                    topRight: Radius.circular(32),
                  ),
                ),
                child: ClipRRect(
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(32),
                    topRight: Radius.circular(32),
                  ),
                  child: Column(
                    children: [
                      const SizedBox(height: 8),
                      // Handle indicator
                      Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: AppTheme.textLight.withOpacity(0.3),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Expanded(
                        child: TabBarView(
                          controller: _tabController,
                          children: [
                            _buildTransferTab(),
                            _buildHistoryTab(),
                            _buildAnalyticsTab(),
                            _buildPoliciesTab(),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildModernAppBar(WalletState walletState) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      child: Row(
        children: [
          // Logo
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              gradient: AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(14),
            ),
            child: const Icon(
              Icons.security_rounded,
              color: AppTheme.cleanWhite,
              size: 24,
            ),
          ),
          const SizedBox(width: 12),
          const Text(
            'AMTTP',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: FontWeight.w800,
              fontSize: 22,
              letterSpacing: -0.5,
            ),
          ),
          const Spacer(),
          // Address pill
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
            decoration: BoxDecoration(
              color: AppTheme.glassWhite,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.2)),
            ),
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: AppTheme.successGreen,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _formatAddress(walletState.address ?? ''),
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildModernBalanceCard(WalletState walletState) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 2, 16, 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        gradient: AppTheme.premiumGradient,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppTheme.primaryPurple.withOpacity(0.2),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                walletState.balance != null
                    ? '${_formatTokenAmount(walletState.balance!)} ETH'
                    : '0.00 ETH',
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.5,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.premiumGold,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text(
                  'PRO',
                  style: TextStyle(
                    color: AppTheme.darkBg,
                    fontSize: 8,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ],
          ),
          Text(
            '≈ \$${walletState.balance != null ? (walletState.balance! * 3500).toStringAsFixed(2) : "0.00"} USD',
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.7),
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _buildQuickAction(Icons.arrow_upward_rounded, 'Send', () {
                _showFullScreenView('Send ETH', _buildSendContent());
              }),
              const SizedBox(width: 8),
              _buildQuickAction(Icons.arrow_downward_rounded, 'Receive', () {
                _showFullScreenView(
                    'Receive ETH', _buildReceiveContent(walletState));
              }),
              const SizedBox(width: 8),
              _buildQuickAction(Icons.swap_horiz_rounded, 'History', () {
                _showFullScreenView(
                    'Transaction History', _buildHistoryContent());
              }),
              const SizedBox(width: 8),
              _buildQuickAction(Icons.settings_rounded, 'Settings', () {
                _showFullScreenView('Settings', _buildSettingsContent());
              }),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildQuickAction(IconData icon, String label, VoidCallback onTap) {
    return Expanded(
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(8),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 6),
            decoration: BoxDecoration(
              color: AppTheme.cleanWhite.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.2)),
            ),
            child: Column(
              children: [
                Icon(icon, color: AppTheme.cleanWhite, size: 14),
                const SizedBox(height: 2),
                Text(
                  label,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 8,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showFullScreenView(String title, Widget content) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => Scaffold(
          backgroundColor: AppTheme.darkBg,
          appBar: AppBar(
            backgroundColor: AppTheme.darkCard,
            leading: IconButton(
              icon: const Icon(Icons.arrow_back_rounded,
                  color: AppTheme.cleanWhite),
              onPressed: () => Navigator.of(context).pop(),
            ),
            title: Text(
              title,
              style: const TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            elevation: 0,
          ),
          body: Container(
            decoration: const BoxDecoration(
              gradient: AppTheme.darkGradient,
            ),
            child: SafeArea(child: content),
          ),
        ),
      ),
    );
  }

  Widget _buildSendContent() {
    return const SingleChildScrollView(
      padding: EdgeInsets.all(20),
      child: SecureTransferWidget(),
    );
  }

  Widget _buildReceiveContent(WalletState walletState) {
    return Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        children: [
          const SizedBox(height: 40),
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
            ),
            child: Column(
              children: [
                const Icon(Icons.qr_code_rounded,
                    color: AppTheme.primaryPurple, size: 80),
                const SizedBox(height: 24),
                const Text(
                  'Your Wallet Address',
                  style: TextStyle(color: AppTheme.textLight, fontSize: 14),
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: AppTheme.darkBg,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    walletState.address ?? 'Not connected',
                    style: const TextStyle(
                      color: AppTheme.cleanWhite,
                      fontSize: 12,
                      fontFamily: 'monospace',
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Share this address to receive ETH on Sepolia network',
                  style: TextStyle(color: AppTheme.textLight, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHistoryContent() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children:
          List.generate(10, (index) => _buildModernTransactionItem(index)),
    );
  }

  Widget _buildSettingsContent() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildSettingsItem(
            Icons.security_rounded, 'Security', 'Manage security settings'),
        _buildSettingsItem(
            Icons.notifications_rounded, 'Notifications', 'Configure alerts'),
        _buildSettingsItem(
            Icons.palette_rounded, 'Appearance', 'Theme and display'),
        _buildSettingsItem(Icons.language_rounded, 'Language', 'English'),
        _buildSettingsItem(Icons.info_rounded, 'About', 'Version 1.0.0'),
      ],
    );
  }

  Widget _buildSettingsItem(IconData icon, String title, String subtitle) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.08)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppTheme.primaryPurple.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: AppTheme.primaryPurple, size: 22),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style:
                      const TextStyle(color: AppTheme.textLight, fontSize: 12),
                ),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: AppTheme.textLight),
        ],
      ),
    );
  }

  void _showReceiveDialog() {
    final walletState = ref.read(walletProvider);
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.darkCard,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text(
          'Receive ETH',
          style: TextStyle(
              color: AppTheme.cleanWhite, fontWeight: FontWeight.w700),
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppTheme.darkBg,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                walletState.address ?? 'Not connected',
                style: const TextStyle(
                  color: AppTheme.textLight,
                  fontSize: 12,
                  fontFamily: 'monospace',
                ),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Share this address to receive ETH',
              style: TextStyle(color: AppTheme.textLight, fontSize: 13),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close',
                style: TextStyle(color: AppTheme.primaryPurple)),
          ),
        ],
      ),
    );
  }

  Widget _buildFloatingNavBar() {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Container(
          color: AppTheme.darkCard.withOpacity(0.95),
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNavItem(0, Icons.send_rounded, 'Send'),
              _buildNavItem(1, Icons.history_rounded, 'History'),
              _buildNavItem(2, Icons.analytics_rounded, 'Analytics'),
              _buildNavItem(3, Icons.shield_rounded, 'Security'),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNavItem(int index, IconData icon, String label) {
    final isSelected = _tabController.index == index;
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: () {
          debugPrint('Nav item tapped: $index - $label');
          _tabController.animateTo(index);
          setState(() {});
        },
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          decoration: BoxDecoration(
            gradient: isSelected ? AppTheme.primaryGradient : null,
            borderRadius: BorderRadius.circular(18),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                icon,
                size: 22,
                color: isSelected ? AppTheme.cleanWhite : AppTheme.textLight,
              ),
              const SizedBox(height: 4),
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w500,
                  color: isSelected ? AppTheme.cleanWhite : AppTheme.textLight,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTransferTab() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      child: const SecureTransferWidget(),
    );
  }

  Widget _buildHistoryTab() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      children: [
        const Text(
          'Recent Transactions',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w700,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 16),
        ...List.generate(10, (index) => _buildModernTransactionItem(index)),
      ],
    );
  }

  Widget _buildAnalyticsTab() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      children: [
        const Text(
          'Risk Analytics',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w700,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 16),
        // Risk Score Card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppTheme.darkBg,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Current Risk Score',
                    style: TextStyle(
                      color: AppTheme.textLight,
                      fontSize: 14,
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTheme.successGreen.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      'LOW RISK',
                      style: TextStyle(
                        color: AppTheme.successGreen,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  ShaderMask(
                    shaderCallback: (bounds) => const LinearGradient(
                      colors: [AppTheme.successGreen, AppTheme.accentCyan],
                    ).createShader(bounds),
                    child: const Text(
                      '31.4',
                      style: TextStyle(
                        fontSize: 48,
                        fontWeight: FontWeight.w800,
                        color: AppTheme.cleanWhite,
                      ),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(bottom: 10),
                    child: Text(
                      ' / 100',
                      style: TextStyle(
                        color: AppTheme.textLight,
                        fontSize: 18,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              ClipRRect(
                borderRadius: BorderRadius.circular(6),
                child: LinearProgressIndicator(
                  value: 0.314,
                  backgroundColor: AppTheme.cleanWhite.withOpacity(0.1),
                  valueColor: const AlwaysStoppedAnimation<Color>(
                      AppTheme.successGreen),
                  minHeight: 8,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        const SizedBox(
          height: 400,
          child: RiskVisualizerWidget(
            riskScore: 31.4,
            riskScores: [25.5, 32.1, 18.9, 45.3, 28.7, 52.1, 31.4],
            featureContributions: {
              'Amount': 8.5,
              'Frequency': 6.2,
              'Geography': 4.3,
              'Time': 3.1,
              'Velocity': 1.4,
            },
          ),
        ),
      ],
    );
  }

  Widget _buildPoliciesTab() {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
      children: [
        const Text(
          'Security Policies',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w700,
            fontSize: 20,
          ),
        ),
        const SizedBox(height: 16),
        _buildModernPolicyCard(
          'Risk Threshold',
          '70%',
          'Transactions above this risk level require manual review',
          Icons.warning_amber_rounded,
          AppTheme.warningOrange,
        ),
        _buildModernPolicyCard(
          'Daily Limit',
          '10 ETH',
          'Maximum amount that can be transferred per day',
          Icons.account_balance_wallet_rounded,
          AppTheme.premiumGold,
        ),
        _buildModernPolicyCard(
          'KYC Status',
          'Verified',
          'Identity verification completed with compliance standards',
          Icons.verified_user_rounded,
          AppTheme.successGreen,
        ),
        _buildModernPolicyCard(
          'Two-Factor Auth',
          'Enabled',
          'Additional security layer for high-value transactions',
          Icons.security_rounded,
          AppTheme.accentCyan,
        ),
      ],
    );
  }

  Widget _buildModernTransactionItem(int index) {
    final bool isIncoming = index % 2 == 0;
    final double amount = (index + 1) * 150.0;
    final List<String> timeAgo = [
      '2 min',
      '15 min',
      '1 hr',
      '3 hrs',
      '6 hrs',
      '12 hrs',
      '1 day',
      '2 days',
      '3 days',
      '1 week'
    ];

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.08)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              gradient: isIncoming
                  ? const LinearGradient(
                      colors: [AppTheme.successGreen, Color(0xFF059669)])
                  : AppTheme.primaryGradient,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(
              isIncoming
                  ? Icons.arrow_downward_rounded
                  : Icons.arrow_upward_rounded,
              color: AppTheme.cleanWhite,
              size: 22,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isIncoming ? 'Received from' : 'Sent to',
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.7),
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  _formatAddress(
                      '0x${(1234567890 + index * 111111111).toRadixString(16)}abcd'),
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    color: AppTheme.cleanWhite,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${isIncoming ? '+' : '-'}${_formatTokenAmount(amount)} ETH',
                style: TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                  color:
                      isIncoming ? AppTheme.successGreen : AppTheme.cleanWhite,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${timeAgo[index]} ago',
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.5),
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildModernPolicyCard(String title, String value, String description,
      IconData icon, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.darkBg,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.08)),
      ),
      child: Row(
        children: [
          Container(
            width: 52,
            height: 52,
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(icon, color: color, size: 26),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      title,
                      style: const TextStyle(
                        color: AppTheme.cleanWhite,
                        fontWeight: FontWeight.w600,
                        fontSize: 15,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: color.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        value,
                        style: TextStyle(
                          color: color,
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  description,
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.6),
                    fontSize: 13,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatAddress(String address) {
    if (address.length <= 10) return address;
    return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
  }

  String _formatTokenAmount(double amount) {
    if (amount >= 1000000) {
      return '${(amount / 1000000).toStringAsFixed(2)}M';
    } else if (amount >= 1000) {
      return '${(amount / 1000).toStringAsFixed(2)}K';
    } else {
      return amount.toStringAsFixed(2);
    }
  }
}
