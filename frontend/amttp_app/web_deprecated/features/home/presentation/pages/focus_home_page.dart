/// @deprecated — This file is DEAD CODE. All R1/R2 routing now uses
/// [FintechHomePage] in `shared/shells/premium_fintech_shell.dart`.
/// Retained for reference only. Safe to delete.
///
/// Focus Mode Home Page - Sleek End User Interface
///
/// Per Ground Truth v2.3:
/// - Simplified interface for R1/R2 end users
/// - No complex charts or analytics
/// - Clean, modern, consumer-grade UX
/// - Quick access to core features: Send, Trust Check, History
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';

class FocusHomePage extends ConsumerStatefulWidget {
  const FocusHomePage({super.key});

  @override
  ConsumerState<FocusHomePage> createState() => _FocusHomePageState();
}

class _FocusHomePageState extends ConsumerState<FocusHomePage>
    with SingleTickerProviderStateMixin {
  late AnimationController _animController;
  late Animation<double> _fadeAnim;
  late Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _fadeAnim = CurvedAnimation(parent: _animController, curve: Curves.easeOut);
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 0.1),
      end: Offset.zero,
    ).animate(
        CurvedAnimation(parent: _animController, curve: Curves.easeOutCubic));
    _animController.forward();
  }

  @override
  void dispose() {
    _animController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final rbacState = ref.watch(rbacProvider);
    final screenWidth = MediaQuery.of(context).size.width;
    final isWide = screenWidth > 600;

    return Scaffold(
      backgroundColor: AppTheme.gray950,
      body: SafeArea(
        child: FadeTransition(
          opacity: _fadeAnim,
          child: SlideTransition(
            position: _slideAnim,
            child: CustomScrollView(
              slivers: [
                // Greeting Section
                SliverToBoxAdapter(
                  child: _buildGreetingSection(rbacState),
                ),

                // Balance Card
                SliverToBoxAdapter(
                  child: _buildBalanceCard(),
                ),

                // Quick Actions
                SliverToBoxAdapter(
                  child: _buildQuickActions(isWide),
                ),

                // Recent Activity
                SliverToBoxAdapter(
                  child: _buildRecentActivity(),
                ),

                // Security Status
                SliverToBoxAdapter(
                  child: _buildSecurityStatus(),
                ),

                const SliverToBoxAdapter(
                  child: SizedBox(height: 100),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildGreetingSection(RBACState rbacState) {
    final hour = DateTime.now().hour;
    String greeting;
    if (hour < 12) {
      greeting = 'Good morning';
    } else if (hour < 17) {
      greeting = 'Good afternoon';
    } else {
      greeting = 'Good evening';
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            greeting,
            style: TextStyle(
              fontSize: 14,
              color: AppTheme.slate400,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            rbacState.displayName.isNotEmpty
                ? rbacState.displayName
                : 'Welcome back',
            style: TextStyle(
              fontSize: 28,
              color: AppTheme.gray50,
              fontWeight: FontWeight.w700,
              letterSpacing: -0.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBalanceCard() {
    return Container(
      margin: const EdgeInsets.fromLTRB(24, 16, 24, 24),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.indigo600,
            AppTheme.purple600,
          ],
        ),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: AppTheme.indigo600.withOpacity(0.3),
            blurRadius: 20,
            offset: const Offset(0, 10),
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
                'Total Balance',
                style: TextStyle(
                  fontSize: 14,
                  color: Colors.white.withOpacity(0.8),
                  fontWeight: FontWeight.w500,
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.lock, size: 12, color: Colors.white),
                    const SizedBox(width: 4),
                    Text(
                      'Secure',
                      style: TextStyle(
                        fontSize: 11,
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '\$12,450',
                style: TextStyle(
                  fontSize: 42,
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -1,
                ),
              ),
              Padding(
                padding: const EdgeInsets.only(bottom: 8, left: 4),
                child: Text(
                  '.00',
                  style: TextStyle(
                    fontSize: 24,
                    color: Colors.white.withOpacity(0.7),
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '≈ 4.82 ETH',
            style: TextStyle(
              fontSize: 14,
              color: Colors.white.withOpacity(0.7),
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickActions(bool isWide) {
    final actions = [
      _QuickAction(
        icon: Icons.arrow_upward_rounded,
        label: 'Send',
        color: AppTheme.indigo500,
        onTap: () => context.go('/transfer'),
      ),
      _QuickAction(
        icon: Icons.search_rounded,
        label: 'Trust Check',
        color: AppTheme.purple500,
        onTap: () => context.go('/trust-check'),
      ),
      _QuickAction(
        icon: Icons.history_rounded,
        label: 'History',
        color: AppTheme.cyan500,
        onTap: () => context.go('/history'),
      ),
      _QuickAction(
        icon: Icons.shield_rounded,
        label: 'Security',
        color: AppTheme.green500,
        onTap: () => context.go('/settings'),
      ),
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Quick Actions',
            style: TextStyle(
              fontSize: 16,
              color: AppTheme.gray50,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children:
                actions.map((action) => _buildActionButton(action)).toList(),
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton(_QuickAction action) {
    return GestureDetector(
      onTap: action.onTap,
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: action.color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: action.color.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Icon(
              action.icon,
              color: action.color,
              size: 28,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            action.label,
            style: TextStyle(
              fontSize: 12,
              color: AppTheme.slate300,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRecentActivity() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 32, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Recent Activity',
                style: TextStyle(
                  fontSize: 16,
                  color: AppTheme.gray50,
                  fontWeight: FontWeight.w600,
                ),
              ),
              TextButton(
                onPressed: () => context.go('/history'),
                child: Text(
                  'See All',
                  style: TextStyle(
                    fontSize: 13,
                    color: AppTheme.indigo400,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _buildActivityItem(
            icon: Icons.arrow_upward_rounded,
            iconBg: AppTheme.red500,
            title: 'Sent to 0x8f2...4a1',
            subtitle: '2 hours ago',
            amount: '-0.25 ETH',
            isNegative: true,
          ),
          _buildActivityItem(
            icon: Icons.arrow_downward_rounded,
            iconBg: AppTheme.green500,
            title: 'Received from 0x3c1...b2f',
            subtitle: 'Yesterday',
            amount: '+1.50 ETH',
            isNegative: false,
          ),
          _buildActivityItem(
            icon: Icons.swap_horiz_rounded,
            iconBg: AppTheme.purple500,
            title: 'Swap ETH → USDC',
            subtitle: '3 days ago',
            amount: '500 USDC',
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
    required bool isNegative,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.slate800.withOpacity(0.5),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.slate700.withOpacity(0.5)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: iconBg.withOpacity(0.2),
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
                  style: TextStyle(
                    fontSize: 14,
                    color: AppTheme.gray50,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
                    fontSize: 12,
                    color: AppTheme.slate400,
                  ),
                ),
              ],
            ),
          ),
          Text(
            amount,
            style: TextStyle(
              fontSize: 14,
              color: isNegative ? AppTheme.slate300 : AppTheme.green400,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSecurityStatus() {
    return Container(
      margin: const EdgeInsets.fromLTRB(24, 24, 24, 0),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.green500.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.green500.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.green500.withOpacity(0.2),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Icon(
              Icons.verified_user_rounded,
              color: AppTheme.green500,
              size: 24,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Your account is protected',
                  style: TextStyle(
                    fontSize: 15,
                    color: AppTheme.gray50,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'All transactions are verified with ML-powered fraud detection',
                  style: TextStyle(
                    fontSize: 12,
                    color: AppTheme.slate400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _QuickAction {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  _QuickAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });
}
