import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../shared/layout/premium_centered_page.dart';

/// Advanced Features Page - Consolidated power user tools
/// 
/// Combines functionality from:
/// - NFT Swap (AMTTPNFT.sol)
/// - Cross-Chain (AMTTPCrossChain.sol)
/// - Safe Management (AMTTPSafeModule.sol)
/// - Session Keys (AMTTPBiconomyModule.sol)
/// - zkNAF Privacy Proofs
class AdvancedFeaturesPage extends ConsumerStatefulWidget {
  final String? initialTab;
  
  const AdvancedFeaturesPage({super.key, this.initialTab});

  @override
  ConsumerState<AdvancedFeaturesPage> createState() => _AdvancedFeaturesPageState();
}

class _AdvancedFeaturesPageState extends ConsumerState<AdvancedFeaturesPage>
    with TickerProviderStateMixin {
  late TabController _tabController;
  
  final List<_FeatureTab> _tabs = [
    _FeatureTab(
      id: 'nft',
      title: 'NFT Swap',
      icon: Icons.collections_rounded,
      description: 'Swap NFTs securely with escrow protection',
    ),
    _FeatureTab(
      id: 'crosschain',
      title: 'Cross-Chain',
      icon: Icons.lan_rounded,
      description: 'Transfer across blockchains with LayerZero',
    ),
    _FeatureTab(
      id: 'safe',
      title: 'Safe',
      icon: Icons.security_rounded,
      description: 'Gnosis Safe multisig management',
    ),
    _FeatureTab(
      id: 'sessions',
      title: 'Sessions',
      icon: Icons.key_rounded,
      description: 'ERC-4337 session key management',
    ),
    _FeatureTab(
      id: 'privacy',
      title: 'Privacy',
      icon: Icons.shield_rounded,
      description: 'zkNAF zero-knowledge proofs',
    ),
  ];

  @override
  void initState() {
    super.initState();
    final initialIndex = _resolveInitialTab(widget.initialTab);
    _tabController = TabController(length: _tabs.length, vsync: this, initialIndex: initialIndex);
  }

  int _resolveInitialTab(String? tabId) {
    if (tabId == null) return 0;
    final index = _tabs.indexWhere((t) => t.id == tabId);
    return index >= 0 ? index : 0;
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: PremiumCenteredPage(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                    ),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.rocket_launch_rounded, color: Colors.white, size: 24),
                ),
                const SizedBox(width: 16),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Advanced Features',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        'Power user tools for DeFi operations',
                        style: TextStyle(color: Colors.white60, fontSize: 13),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            
            // Tab Bar
            Container(
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.05),
                borderRadius: BorderRadius.circular(12),
              ),
              child: TabBar(
                controller: _tabController,
                isScrollable: true,
                indicatorSize: TabBarIndicatorSize.tab,
                indicator: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                  ),
                  borderRadius: BorderRadius.circular(10),
                ),
                labelColor: Colors.white,
                unselectedLabelColor: Colors.white60,
                dividerColor: Colors.transparent,
                padding: const EdgeInsets.all(4),
                tabs: _tabs.map((tab) => Tab(
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(tab.icon, size: 18),
                      const SizedBox(width: 8),
                      Text(tab.title),
                    ],
                  ),
                )).toList(),
              ),
            ),
            const SizedBox(height: 20),
            
            // Tab Content
            Expanded(
              child: TabBarView(
                controller: _tabController,
                children: [
                  _NFTSwapTab(),
                  _CrossChainTab(),
                  _SafeTab(),
                  _SessionsTab(),
                  _PrivacyTab(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeatureTab {
  final String id;
  final String title;
  final IconData icon;
  final String description;

  const _FeatureTab({
    required this.id,
    required this.title,
    required this.icon,
    required this.description,
  });
}

// ═══════════════════════════════════════════════════════════════════════════════
// NFT SWAP TAB
// ═══════════════════════════════════════════════════════════════════════════════

class _NFTSwapTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFeatureCard(
            icon: Icons.swap_horiz_rounded,
            title: 'NFT ↔ ETH Swap',
            description: 'Exchange your NFT for ETH with escrow protection',
            action: 'Start Swap',
            onTap: () {},
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.compare_arrows_rounded,
            title: 'NFT ↔ NFT Swap',
            description: 'Trade NFTs directly with other collectors',
            action: 'Find Trades',
            onTap: () {},
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.history_rounded,
            title: 'Active Swaps',
            description: 'View and manage your pending swaps',
            action: 'View All',
            onTap: () {},
            badge: '2',
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// CROSS-CHAIN TAB
// ═══════════════════════════════════════════════════════════════════════════════

class _CrossChainTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Chain Status
          _buildChainStatusCard(),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.send_rounded,
            title: 'Cross-Chain Transfer',
            description: 'Send tokens across supported blockchains',
            action: 'Transfer',
            onTap: () {},
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.history_rounded,
            title: 'Bridge History',
            description: 'Track your cross-chain transactions',
            action: 'View History',
            onTap: () {},
          ),
        ],
      ),
    );
  }

  Widget _buildChainStatusCard() {
    final chains = [
      {'name': 'Ethereum', 'status': 'active', 'icon': '◆'},
      {'name': 'Polygon', 'status': 'active', 'icon': '⬡'},
      {'name': 'Arbitrum', 'status': 'active', 'icon': '◈'},
      {'name': 'Optimism', 'status': 'active', 'icon': '◉'},
    ];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Supported Chains',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: chains.map((chain) => Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.15),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.green.withOpacity(0.3)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(chain['icon']!, style: const TextStyle(fontSize: 16)),
                  const SizedBox(width: 8),
                  Text(chain['name']!, style: const TextStyle(color: Colors.white)),
                  const SizedBox(width: 8),
                  Container(
                    width: 8,
                    height: 8,
                    decoration: const BoxDecoration(
                      color: Colors.green,
                      shape: BoxShape.circle,
                    ),
                  ),
                ],
              ),
            )).toList(),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SAFE MANAGEMENT TAB
// ═══════════════════════════════════════════════════════════════════════════════

class _SafeTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildFeatureCard(
            icon: Icons.add_circle_outline_rounded,
            title: 'Register Safe',
            description: 'Connect your Gnosis Safe for multisig protection',
            action: 'Connect',
            onTap: () {},
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.pending_actions_rounded,
            title: 'Pending Transactions',
            description: 'Approve or reject queued transactions',
            action: 'Review',
            onTap: () {},
            badge: '3',
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.checklist_rounded,
            title: 'Whitelist',
            description: 'Manage trusted addresses for faster transfers',
            action: 'Manage',
            onTap: () {},
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SESSION KEYS TAB
// ═══════════════════════════════════════════════════════════════════════════════

class _SessionsTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Info banner
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.primaryBlue.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.primaryBlue.withOpacity(0.3)),
            ),
            child: const Row(
              children: [
                Icon(Icons.info_outline_rounded, color: AppTheme.primaryBlue),
                SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Session keys allow dApps to sign transactions on your behalf with limited permissions.',
                    style: TextStyle(color: Colors.white70, fontSize: 13),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.key_rounded,
            title: 'Create Session Key',
            description: 'Generate a new session key for a dApp',
            action: 'Create',
            onTap: () {},
          ),
          const SizedBox(height: 16),
          _buildFeatureCard(
            icon: Icons.vpn_key_rounded,
            title: 'Active Sessions',
            description: 'View and revoke active session keys',
            action: 'Manage',
            onTap: () {},
            badge: '1',
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PRIVACY (zkNAF) TAB
// ═══════════════════════════════════════════════════════════════════════════════

class _PrivacyTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Proof status cards
          _buildProofCard(
            title: 'Sanctions Clearance',
            description: 'Prove you\'re not on sanctions lists',
            status: 'valid',
            expiresIn: '28 days',
          ),
          const SizedBox(height: 12),
          _buildProofCard(
            title: 'Low Risk Score',
            description: 'Prove your risk score is below threshold',
            status: 'expired',
            expiresIn: null,
          ),
          const SizedBox(height: 12),
          _buildProofCard(
            title: 'KYC Verification',
            description: 'Prove identity without revealing details',
            status: 'not_generated',
            expiresIn: null,
          ),
          const SizedBox(height: 20),
          
          // Generate new proof
          _buildFeatureCard(
            icon: Icons.add_circle_outline_rounded,
            title: 'Generate New Proof',
            description: 'Create a zero-knowledge proof for compliance',
            action: 'Generate',
            onTap: () {},
          ),
        ],
      ),
    );
  }

  Widget _buildProofCard({
    required String title,
    required String description,
    required String status,
    String? expiresIn,
  }) {
    Color statusColor;
    IconData statusIcon;
    String statusText;

    switch (status) {
      case 'valid':
        statusColor = Colors.green;
        statusIcon = Icons.check_circle_rounded;
        statusText = 'Valid';
        break;
      case 'expired':
        statusColor = Colors.orange;
        statusIcon = Icons.warning_rounded;
        statusText = 'Expired';
        break;
      default:
        statusColor = Colors.grey;
        statusIcon = Icons.radio_button_unchecked_rounded;
        statusText = 'Not Generated';
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: statusColor.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Icon(statusIcon, color: statusColor, size: 32),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                const SizedBox(height: 4),
                Text(description, style: const TextStyle(color: Colors.white60, fontSize: 12)),
                if (expiresIn != null) ...[
                  const SizedBox(height: 4),
                  Text('Expires in $expiresIn', style: TextStyle(color: statusColor, fontSize: 12)),
                ],
              ],
            ),
          ),
          if (status != 'valid')
            TextButton(
              onPressed: () {},
              child: Text(status == 'expired' ? 'Renew' : 'Generate'),
            ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SHARED WIDGETS
// ═══════════════════════════════════════════════════════════════════════════════

Widget _buildFeatureCard({
  required IconData icon,
  required String title,
  required String description,
  required String action,
  required VoidCallback onTap,
  String? badge,
}) {
  return Container(
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.05),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: Colors.white.withOpacity(0.1)),
    ),
    child: Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.primaryBlue.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(icon, color: AppTheme.primaryBlue, size: 24),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                            fontSize: 16,
                          ),
                        ),
                        if (badge != null) ...[
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: AppTheme.primaryBlue,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(
                              badge,
                              style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      description,
                      style: const TextStyle(color: Colors.white60, fontSize: 13),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [AppTheme.primaryBlue, AppTheme.primaryPurple],
                  ),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  action,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
