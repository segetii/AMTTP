import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/web3/wallet_provider.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/secure_transfer_widget.dart';
import '../../../../shared/widgets/risk_visualizer_widget.dart';
import '../../../../shared/widgets/interactive_wallet_widget.dart';
import '../../../../shared/widgets/features_carousel.dart';

class HomePage extends ConsumerStatefulWidget {
  const HomePage({super.key});

  @override
  ConsumerState<HomePage> createState() => _HomePageState();
}

class _HomePageState extends ConsumerState<HomePage>
    with TickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final walletState = ref.watch(walletProvider);

    return Scaffold(
      backgroundColor: AppTheme.lightAsh,
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: AppTheme.premiumGold,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(
                Icons.security,
                color: AppTheme.darkAsh,
                size: 20,
              ),
            ),
            const SizedBox(width: 12),
            const Text(
              'AMTTP',
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: AppTheme.cleanWhite,
              ),
            ),
          ],
        ),
        actions: [
          if (walletState.isConnected)
            Container(
              margin: const EdgeInsets.only(right: 16),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.supportLilac,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                _formatAddress(walletState.address!),
                style: const TextStyle(
                  color: AppTheme.darkAsh,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
        ],
      ),
      body: walletState.isConnected
          ? _buildMainContent(walletState)
          : _buildWelcomeScreen(),
      bottomNavigationBar:
          walletState.isConnected ? _buildBottomNavigation() : null,
    );
  }

  Widget _buildWelcomeScreen() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 60),

          // AMTTP Logo & Branding
          Container(
            width: 120,
            height: 120,
            decoration: BoxDecoration(
              color: AppTheme.primaryPurple,
              borderRadius: BorderRadius.circular(30),
              boxShadow: [
                BoxShadow(
                  color: AppTheme.primaryPurple.withOpacity(0.3),
                  blurRadius: 20,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: const Icon(
              Icons.security,
              size: 60,
              color: AppTheme.cleanWhite,
            ),
          ),

          const SizedBox(height: 32),

          // Welcome Title
          Text(
            'Advanced Money Transfer\nTrust Protocol',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                  color: AppTheme.darkAsh,
                  fontWeight: FontWeight.bold,
                ),
          ),

          const SizedBox(height: 16),

          // Subtitle
          Text(
            'Secure, compliant, and fraud-protected\ndigital transactions',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: AppTheme.textMedium,
                  height: 1.5,
                ),
          ),

          const SizedBox(height: 48),

          // Interactive Features Carousel
          const FeaturesCarousel(),

          const SizedBox(height: 48),

          // Interactive Wallet Connection Widget
          const InteractiveWalletWidget(),

          const SizedBox(height: 24),

          // Security Notice
          Text(
            'Your security is our priority. AMTTP uses enterprise-grade encryption and never stores your private keys.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: AppTheme.textLight,
                  fontStyle: FontStyle.italic,
                ),
          ),
        ],
      ),
    );
  }

  Widget _buildMainContent(WalletState walletState) {
    return Column(
      children: [
        _buildBalanceCard(walletState),
        Expanded(
          child: Container(
            color: AppTheme.lightAsh,
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
        ),
      ],
    );
  }

  Widget _buildBalanceCard(WalletState walletState) {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primaryPurple, AppTheme.supportLilac],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: AppTheme.primaryPurple.withOpacity(0.3),
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
              const Text(
                'AMTTP Balance',
                style: TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 16,
                  fontWeight: FontWeight.w500,
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: AppTheme.premiumGold,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Text(
                  'PREMIUM',
                  style: TextStyle(
                    color: AppTheme.darkAsh,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            walletState.balance != null
                ? '${_formatTokenAmount(walletState.balance!)} AMTTP'
                : 'Loading...',
            style: const TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 32,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              _buildBalanceAction(Icons.send, 'Send', () {
                _tabController.animateTo(0);
              }),
              _buildBalanceAction(Icons.history, 'History', () {
                _tabController.animateTo(1);
              }),
              _buildBalanceAction(Icons.analytics, 'Analytics', () {
                _tabController.animateTo(2);
              }),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildBalanceAction(IconData icon, String label, VoidCallback onTap) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: AppTheme.cleanWhite.withOpacity(0.2),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Column(
            children: [
              Icon(icon, color: AppTheme.cleanWhite, size: 24),
              const SizedBox(height: 4),
              Text(
                label,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTransferTab() {
    return const Padding(
      padding: EdgeInsets.all(16),
      child: SecureTransferWidget(),
    );
  }

  Widget _buildHistoryTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Transaction History',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: AppTheme.darkAsh,
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 16),
          Expanded(
            child: ListView.builder(
              itemCount: 10,
              itemBuilder: (context, index) => _buildTransactionItem(index),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAnalyticsTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Risk Analytics',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: AppTheme.darkAsh,
                  fontWeight: FontWeight.bold,
                ),
          ),
          const Expanded(
            child: RiskVisualizerWidget(
              riskScore: 31.4, // Current risk score
              riskScores: [
                25.5,
                32.1,
                18.9,
                45.3,
                28.7,
                52.1,
                31.4
              ], // Historical scores
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
      ),
    );
  }

  Widget _buildPoliciesTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Security Policies',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: AppTheme.darkAsh,
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 16),
          _buildPolicyCard(
            'Risk Threshold',
            '70%',
            'Transactions above this risk level require manual review',
            Icons.warning_amber,
            AppTheme.warningOrange,
          ),
          _buildPolicyCard(
            'Daily Limit',
            '10,000 AMTTP',
            'Maximum amount that can be transferred per day',
            Icons.account_balance_wallet,
            AppTheme.premiumGold,
          ),
          _buildPolicyCard(
            'KYC Status',
            'Verified',
            'Identity verification completed with compliance standards',
            Icons.verified_user,
            AppTheme.successGreen,
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionItem(int index) {
    final bool isIncoming = index % 2 == 0;
    final double amount = (index + 1) * 150.0;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.mediumAsh, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color:
                  isIncoming ? AppTheme.successGreen : AppTheme.primaryPurple,
              borderRadius: BorderRadius.circular(20),
            ),
            child: Icon(
              isIncoming ? Icons.arrow_downward : Icons.arrow_upward,
              color: AppTheme.cleanWhite,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${isIncoming ? 'From' : 'To'}: ${_formatAddress('0x1234...5678')}',
                  style: const TextStyle(
                    fontWeight: FontWeight.w500,
                    color: AppTheme.darkAsh,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  '2 hours ago',
                  style: TextStyle(
                    color: AppTheme.textMedium,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${isIncoming ? '+' : '-'}${_formatTokenAmount(amount)} AMTTP',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: isIncoming ? AppTheme.successGreen : AppTheme.darkAsh,
                ),
              ),
              const SizedBox(height: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: AppTheme.successGreen,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'Completed',
                  style: TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildPolicyCard(String title, String value, String description,
      IconData icon, Color color) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.mediumAsh, width: 0.5),
      ),
      child: Row(
        children: [
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: color, size: 24),
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
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: AppTheme.darkAsh,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                    Text(
                      value,
                      style: TextStyle(
                        color: color,
                        fontWeight: FontWeight.bold,
                        fontSize: 16,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: AppTheme.textMedium,
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

  Widget _buildBottomNavigation() {
    return Container(
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite,
        boxShadow: [
          BoxShadow(
            color: AppTheme.darkAsh.withOpacity(0.1),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: TabBar(
        controller: _tabController,
        indicator: BoxDecoration(
          color: AppTheme.primaryPurple.withOpacity(0.1),
          borderRadius: BorderRadius.circular(8),
        ),
        tabs: const [
          Tab(icon: Icon(Icons.send), text: 'Transfer'),
          Tab(icon: Icon(Icons.history), text: 'History'),
          Tab(icon: Icon(Icons.analytics), text: 'Analytics'),
          Tab(icon: Icon(Icons.policy), text: 'Policies'),
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
