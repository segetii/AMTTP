import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../shared/layout/premium_centered_page.dart';
import '../../../../core/web3/wallet_provider.dart';

/// Premium Wallet Connect Page - Web3 Wallet Connection
class PremiumWalletConnectPage extends ConsumerStatefulWidget {
  final bool isDemo;
  const PremiumWalletConnectPage({super.key, this.isDemo = false});

  @override
  ConsumerState<PremiumWalletConnectPage> createState() => _PremiumWalletConnectPageState();
}

class _PremiumWalletConnectPageState extends ConsumerState<PremiumWalletConnectPage>
    with SingleTickerProviderStateMixin {
  final _watchAddressController = TextEditingController();
  String? _connectingWallet;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  final List<Map<String, dynamic>> _wallets = [
    {
      'name': 'MetaMask',
      'icon': 'metamask',
      'color': AppTheme.brandMetaMask,
      'popular': true,
      'installed': true,
    },
    {
      'name': 'WalletConnect',
      'icon': 'walletconnect',
      'color': AppTheme.brandWalletConnect,
      'popular': true,
    },
    {
      'name': 'Coinbase Wallet',
      'icon': 'coinbase',
      'color': AppTheme.brandCoinbase,
      'popular': true,
    },
    {
      'name': 'Web3Auth',
      'icon': 'web3auth',
      'color': const Color(0xFF0364FF),
      'description': 'Social Login (Google, Apple)',
    },
  ];

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.15).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _watchAddressController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _connectWallet(String walletName) async {
    // For now, all wallet options trigger the same MetaMask-based
    // connection flow via the shared walletProvider.
    setState(() {
      _connectingWallet = walletName;
    });

    _showConnectionModal(walletName);

    // Demo mode: simulate a quick success without touching the real provider
    if (widget.isDemo) {
      await Future.delayed(const Duration(seconds: 2));
      if (!mounted) return;
      Navigator.of(context).maybePop();
      _showSuccessModal(walletName);
      setState(() {
        _connectingWallet = null;
      });
      return;
    }

    final notifier = ref.read(walletProvider.notifier);

    try {
      await notifier.connectWallet();
      if (!mounted) return;

      // Close the bottom sheet first
      Navigator.of(context).maybePop();

      final state = ref.read(walletProvider);
      if (state.isConnected) {
        _showSuccessModal(walletName);
      } else if (state.hasError && state.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(state.error!),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _connectingWallet = null;
        });
      }
    }
  }

  void _showConnectionModal(String walletName) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: true,
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: AppTheme.tokenSurface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(51),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 24),
            
            // Wallet icon with pulse
            AnimatedBuilder(
              animation: _pulseAnimation,
              builder: (context, child) {
                return Transform.scale(
                  scale: _pulseAnimation.value,
                  child: Container(
                    width: 80,
                    height: 80,
                    decoration: BoxDecoration(
                      color: AppTheme.brandMetaMask.withAlpha(38),
                      shape: BoxShape.circle,
                      border: Border.all(color: AppTheme.brandMetaMask, width: 2),
                    ),
                    child: const Center(
                      child: Icon(Icons.account_balance_wallet_rounded, color: AppTheme.brandMetaMask, size: 36),
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 24),
            
            Text(
              'Connecting to $walletName',
              style: const TextStyle(
                color: AppTheme.tokenText,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Please approve the connection in your wallet',
              style: TextStyle(color: Colors.white.withAlpha(153), fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            
            // Progress steps
            _buildConnectionSteps(),
            const SizedBox(height: 24),
            
            // Cancel button
            Semantics(
              label: 'Cancel wallet connection',
              button: true,
              child: TextButton(
                onPressed: () {
                  setState(() {
                    _connectingWallet = null;
                  });
                  Navigator.pop(context);
                },
                child: Text(
                  'Cancel',
                  style: TextStyle(color: Colors.white.withAlpha(128), fontSize: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConnectionSteps() {
    final steps = [
      {'label': 'Connecting', 'done': true},
      {'label': 'Awaiting approval', 'done': false, 'active': true},
      {'label': 'Complete', 'done': false},
    ];

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: steps.asMap().entries.map((entry) {
        final step = entry.value;
        final isLast = entry.key == steps.length - 1;
        
        return Row(
          children: [
            Column(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: step['done'] == true
                        ? AppTheme.tokenSuccess
                        : (step['active'] == true
                            ? AppTheme.tokenPrimary
                            : AppTheme.tokenBorderSubtle),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: step['done'] == true
                        ? const Icon(Icons.check_rounded, color: AppTheme.tokenText, size: 16)
                        : (step['active'] == true
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(AppTheme.tokenText),
                                ),
                              )
                            : null),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  step['label'] as String,
                  style: TextStyle(
                    color: Colors.white.withAlpha(128),
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            if (!isLast)
              Container(
                width: 30,
                height: 2,
                margin: const EdgeInsets.only(bottom: 20, left: 4, right: 4),
                color: step['done'] == true
                    ? AppTheme.tokenSuccess
                    : AppTheme.tokenBorderSubtle,
              ),
          ],
        );
      }).toList(),
    );
  }

  void _showSuccessModal(String walletName) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: AppTheme.tokenSurface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(51),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 24),
            
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: AppTheme.tokenSuccess.withAlpha(38),
                shape: BoxShape.circle,
                border: Border.all(color: AppTheme.tokenSuccess, width: 2),
              ),
              child: const Center(
                child: Icon(Icons.check_rounded, color: AppTheme.tokenSuccess, size: 40),
              ),
            ),
            const SizedBox(height: 24),
            
            const Text(
              'Connected!',
              style: TextStyle(
                color: AppTheme.tokenText,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Your $walletName is now connected',
              style: TextStyle(color: Colors.white.withAlpha(153), fontSize: 14),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.tokenBorderSubtle,
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                '0x7F3a...9b2C',
                style: TextStyle(
                  color: AppTheme.tokenPrimary,
                  fontSize: 14,
                  fontFamily: 'JetBrains Mono',
                ),
              ),
            ),
            const SizedBox(height: 24),
            
            GestureDetector(
              onTap: () {
                Navigator.pop(context);
                // After a successful connection, send the user to the
                // main wallet page so they immediately see balances
                // and address instead of just landing back on home.
                context.go('/wallet');
              },
              child: Container(
                height: 54,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [AppTheme.tokenPrimary, AppTheme.tokenPrimarySoft]),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Center(
                  child: Text(
                    'Continue to Wallet',
                    style: TextStyle(color: AppTheme.tokenText, fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
    
    setState(() {
      _connectingWallet = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: PremiumCenteredPage(
        child: Column(
          children: [
            _buildHeader(context),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Hero
                    _buildHero(),
                    const SizedBox(height: 32),

                    // Wallet options
                    const Text(
                      'Connect Wallet',
                      style: TextStyle(
                        color: AppTheme.tokenText,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),
                    ..._wallets.map((wallet) => _buildWalletOption(wallet)),

                    const SizedBox(height: 24),

                    // Divider
                    Row(
                      children: [
                        Expanded(child: Container(height: 1, color: AppTheme.tokenBorderSubtle)),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Text(
                            'OR',
                            style: TextStyle(color: Colors.white.withAlpha(102), fontSize: 12),
                          ),
                        ),
                        Expanded(child: Container(height: 1, color: AppTheme.tokenBorderSubtle)),
                      ],
                    ),

                    const SizedBox(height: 24),

                    // Watch address
                    _buildWatchAddress(),

                    const SizedBox(height: 32),

                    // Security section
                    _buildSecuritySection(),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          GestureDetector(
            onTap: () => context.pop(),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: AppTheme.tokenCardElevated,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.tokenBorderStrong),
              ),
              child: const Icon(Icons.arrow_back_rounded, color: AppTheme.tokenText, size: 20),
            ),
          ),
          const Expanded(
            child: Text(
              'Connect Wallet',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.tokenText,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(width: 40),
        ],
      ),
    );
  }

  Widget _buildHero() {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppTheme.tokenPrimary.withAlpha(38),
            AppTheme.tokenPrimarySoft.withAlpha(26),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: AppTheme.tokenPrimary.withAlpha(51)),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: AppTheme.tokenPrimary.withAlpha(51),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.account_balance_wallet_rounded,
              color: AppTheme.tokenPrimary,
              size: 32,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Link Your Wallet',
            style: TextStyle(
              color: AppTheme.tokenText,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Connect your Web3 wallet to access compliant transfers with zkNAF privacy',
            style: TextStyle(
              color: Colors.white.withAlpha(153),
              fontSize: 13,
              height: 1.4,
            ),
            textAlign: TextAlign.center,
          ),
          if (widget.isDemo) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.orange.withAlpha(38),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.orange.withAlpha(128)),
              ),
              child: const Text(
                'Demo environment — no real funds',
                style: TextStyle(color: Colors.orange, fontSize: 12, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildWalletOption(Map<String, dynamic> wallet) {
    final isMetaMask = wallet['name'] == 'MetaMask';
    final isConnecting = _connectingWallet == wallet['name'];
    
    return GestureDetector(
      onTap: isConnecting ? null : () => _connectWallet(wallet['name'] as String),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isMetaMask
              ? AppTheme.brandMetaMask.withAlpha(20)
              : AppTheme.tokenSurface,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isMetaMask
                ? AppTheme.brandMetaMask.withAlpha(102)
                : AppTheme.tokenBorderSubtle,
            width: isMetaMask ? 1.5 : 1,
          ),
          boxShadow: isMetaMask
              ? [
                  BoxShadow(
                    color: AppTheme.brandMetaMask.withAlpha(38),
                    blurRadius: 20,
                    offset: const Offset(0, 4),
                  ),
                ]
              : null,
        ),
        child: Row(
          children: [
            // Wallet icon
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: (wallet['color'] as Color).withAlpha(38),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: _getWalletIcon(wallet['icon'] as String, wallet['color'] as Color),
              ),
            ),
            const SizedBox(width: 14),
            
            // Info
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        wallet['name'] as String,
                        style: const TextStyle(
                          color: AppTheme.tokenText,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (widget.isDemo) ...[
                        const SizedBox(width: 8),
                        const Tooltip(
                          message: 'Demo mode uses simulated connections only',
                          child: Icon(Icons.info_outline_rounded, size: 14, color: Colors.orange),
                        ),
                      ],
                      if (wallet['popular'] == true) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppTheme.tokenPrimary.withAlpha(38),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Popular',
                            style: TextStyle(color: AppTheme.tokenPrimary, fontSize: 9, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                      if (wallet['installed'] == true) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppTheme.tokenSuccess.withAlpha(38),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Installed',
                            style: TextStyle(color: AppTheme.tokenSuccess, fontSize: 9, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                    ],
                  ),
                  if (wallet['description'] != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      wallet['description'] as String,
                      style: TextStyle(
                        color: Colors.white.withAlpha(128),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            
            // Arrow or connecting indicator
            if (isConnecting)
              const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation(AppTheme.tokenPrimary),
                ),
              )
            else
              Icon(
                Icons.arrow_forward_ios_rounded,
                color: Colors.white.withAlpha(77),
                size: 16,
              ),
          ],
        ),
      ),
    );
  }

  Widget _getWalletIcon(String iconName, Color color) {
    switch (iconName) {
      case 'metamask':
        return Icon(Icons.pets, color: color, size: 24); // Fox placeholder
      case 'walletconnect':
        return Icon(Icons.link_rounded, color: color, size: 24);
      case 'coinbase':
        return Icon(Icons.currency_bitcoin, color: color, size: 24);
      case 'web3auth':
        return Icon(Icons.key_rounded, color: color, size: 24);
      default:
        return Icon(Icons.account_balance_wallet_rounded, color: color, size: 24);
    }
  }

  Widget _buildWatchAddress() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.visibility_rounded, color: AppTheme.slate500, size: 18),
            SizedBox(width: 8),
            Text(
              'Watch Address (Read-only)',
              style: TextStyle(
                color: AppTheme.tokenText,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'Monitor any address without connecting a wallet',
          style: TextStyle(
            color: Colors.white.withAlpha(128),
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(
            color: AppTheme.tokenSurface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppTheme.tokenBorderSubtle),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _watchAddressController,
                  style: const TextStyle(color: AppTheme.tokenText, fontSize: 14),
                  decoration: InputDecoration(
                    hintText: '0x... or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withAlpha(77)),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
              GestureDetector(
                onTap: () {/* Watch address */},
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: AppTheme.tokenBorderSubtle,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text(
                    'Watch',
                    style: TextStyle(
                      color: AppTheme.tokenPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSecuritySection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.tokenSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.tokenBorderSubtle),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: AppTheme.tokenSuccess.withAlpha(38),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.shield_rounded, color: AppTheme.tokenSuccess, size: 18),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  'Your Security, Our Priority',
                  style: TextStyle(
                    color: AppTheme.tokenText,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildSecurityItem(Icons.lock_outline_rounded, 'We never store your private keys'),
          _buildSecurityItem(Icons.visibility_off_rounded, 'zkNAF protects your identity'),
          _buildSecurityItem(Icons.code_rounded, 'Open-source smart contracts'),
        ],
      ),
    );
  }

  Widget _buildSecurityItem(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.slate500, size: 16),
          const SizedBox(width: 10),
          Text(
            text,
            style: TextStyle(
              color: Colors.white.withAlpha(153),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}
