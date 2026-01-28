import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// Premium Wallet Connect Page - Web3 Wallet Connection
class PremiumWalletConnectPage extends ConsumerStatefulWidget {
  const PremiumWalletConnectPage({super.key});

  @override
  ConsumerState<PremiumWalletConnectPage> createState() => _PremiumWalletConnectPageState();
}

class _PremiumWalletConnectPageState extends ConsumerState<PremiumWalletConnectPage>
    with SingleTickerProviderStateMixin {
  final _watchAddressController = TextEditingController();
  bool _isConnecting = false;
  String? _connectingWallet;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  final List<Map<String, dynamic>> _wallets = [
    {
      'name': 'MetaMask',
      'icon': 'metamask',
      'color': const Color(0xFFF6851B),
      'popular': true,
      'installed': true,
    },
    {
      'name': 'WalletConnect',
      'icon': 'walletconnect',
      'color': const Color(0xFF3B99FC),
      'popular': true,
    },
    {
      'name': 'Coinbase Wallet',
      'icon': 'coinbase',
      'color': const Color(0xFF0052FF),
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
    setState(() {
      _isConnecting = true;
      _connectingWallet = walletName;
    });

    _showConnectionModal(walletName);
    
    // Simulate connection
    await Future.delayed(const Duration(seconds: 3));
    
    if (mounted) {
      Navigator.pop(context); // Close modal
      _showSuccessModal(walletName);
    }
  }

  void _showConnectionModal(String walletName) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: false,
      builder: (context) => Container(
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
                color: Colors.white.withOpacity(0.2),
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
                      color: const Color(0xFFF6851B).withOpacity(0.15),
                      shape: BoxShape.circle,
                      border: Border.all(color: const Color(0xFFF6851B), width: 2),
                    ),
                    child: const Center(
                      child: Icon(Icons.account_balance_wallet_rounded, color: Color(0xFFF6851B), size: 36),
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 24),
            
            Text(
              'Connecting to $walletName',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Please approve the connection in your wallet',
              style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            
            // Progress steps
            _buildConnectionSteps(),
            const SizedBox(height: 24),
            
            // Cancel button
            TextButton(
              onPressed: () {
                setState(() {
                  _isConnecting = false;
                  _connectingWallet = null;
                });
                Navigator.pop(context);
              },
              child: Text(
                'Cancel',
                style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
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
                        ? const Color(0xFF22C55E)
                        : (step['active'] == true
                            ? const Color(0xFF6366F1)
                            : const Color(0xFF1E1E2E)),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: step['done'] == true
                        ? const Icon(Icons.check_rounded, color: Colors.white, size: 16)
                        : (step['active'] == true
                            ? const SizedBox(
                                width: 14,
                                height: 14,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation(Colors.white),
                                ),
                              )
                            : null),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  step['label'] as String,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
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
                    ? const Color(0xFF22C55E)
                    : const Color(0xFF1E1E2E),
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
                color: Colors.white.withOpacity(0.2),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 24),
            
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: const Color(0xFF22C55E).withOpacity(0.15),
                shape: BoxShape.circle,
                border: Border.all(color: const Color(0xFF22C55E), width: 2),
              ),
              child: const Center(
                child: Icon(Icons.check_rounded, color: Color(0xFF22C55E), size: 40),
              ),
            ),
            const SizedBox(height: 24),
            
            const Text(
              'Connected!',
              style: TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              'Your $walletName is now connected',
              style: TextStyle(color: Colors.white.withOpacity(0.6), fontSize: 14),
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: const Color(0xFF1E1E2E),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                '0x7F3a...9b2C',
                style: TextStyle(
                  color: Color(0xFF6366F1),
                  fontSize: 14,
                  fontFamily: 'monospace',
                ),
              ),
            ),
            const SizedBox(height: 24),
            
            GestureDetector(
              onTap: () {
                Navigator.pop(context);
                context.go('/');
              },
              child: Container(
                height: 54,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)]),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Center(
                  child: Text(
                    'Continue to Wallet',
                    style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
    
    setState(() {
      _isConnecting = false;
      _connectingWallet = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0A0F),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.of(context).size.width > 680 ? 624.0 : MediaQuery.of(context).size.width - 40,
            ),
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
                            color: Colors.white,
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
                            Expanded(child: Container(height: 1, color: const Color(0xFF1E1E2E))),
                            Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 16),
                              child: Text(
                                'OR',
                                style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 12),
                              ),
                            ),
                            Expanded(child: Container(height: 1, color: const Color(0xFF1E1E2E))),
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
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF2D2D44)),
              ),
              child: const Icon(Icons.arrow_back_rounded, color: Colors.white, size: 20),
            ),
          ),
          const Expanded(
            child: Text(
              'Connect Wallet',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
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
            const Color(0xFF6366F1).withOpacity(0.15),
            const Color(0xFF8B5CF6).withOpacity(0.1),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: const Color(0xFF6366F1).withOpacity(0.2)),
      ),
      child: Column(
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: const Color(0xFF6366F1).withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.account_balance_wallet_rounded,
              color: Color(0xFF6366F1),
              size: 32,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Link Your Wallet',
            style: TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Connect your Web3 wallet to access compliant transfers with zkNAF privacy',
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 13,
              height: 1.4,
            ),
            textAlign: TextAlign.center,
          ),
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
              ? const Color(0xFFF6851B).withOpacity(0.08)
              : const Color(0xFF12121A),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isMetaMask
                ? const Color(0xFFF6851B).withOpacity(0.4)
                : const Color(0xFF1E1E2E),
            width: isMetaMask ? 1.5 : 1,
          ),
          boxShadow: isMetaMask
              ? [
                  BoxShadow(
                    color: const Color(0xFFF6851B).withOpacity(0.15),
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
                color: (wallet['color'] as Color).withOpacity(0.15),
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
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (wallet['popular'] == true) ...[
                        const SizedBox(width: 8),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF6366F1).withOpacity(0.15),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Popular',
                            style: TextStyle(color: Color(0xFF6366F1), fontSize: 9, fontWeight: FontWeight.bold),
                          ),
                        ),
                      ],
                      if (wallet['installed'] == true) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFF22C55E).withOpacity(0.15),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: const Text(
                            'Installed',
                            style: TextStyle(color: Color(0xFF22C55E), fontSize: 9, fontWeight: FontWeight.bold),
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
                        color: Colors.white.withOpacity(0.5),
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
                  valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1)),
                ),
              )
            else
              Icon(
                Icons.arrow_forward_ios_rounded,
                color: Colors.white.withOpacity(0.3),
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
            Icon(Icons.visibility_rounded, color: Color(0xFF64748B), size: 18),
            SizedBox(width: 8),
            Text(
              'Watch Address (Read-only)',
              style: TextStyle(
                color: Colors.white,
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
            color: Colors.white.withOpacity(0.5),
            fontSize: 12,
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFF12121A),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: const Color(0xFF1E1E2E)),
          ),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _watchAddressController,
                  style: const TextStyle(color: Colors.white, fontSize: 14),
                  decoration: InputDecoration(
                    hintText: '0x... or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
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
                    color: const Color(0xFF1E1E2E),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text(
                    'Watch',
                    style: TextStyle(
                      color: Color(0xFF6366F1),
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
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: const Color(0xFF22C55E).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.shield_rounded, color: Color(0xFF22C55E), size: 18),
              ),
              const SizedBox(width: 12),
              const Expanded(
                child: Text(
                  'Your Security, Our Priority',
                  style: TextStyle(
                    color: Colors.white,
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
          Icon(icon, color: const Color(0xFF64748B), size: 16),
          const SizedBox(width: 10),
          Text(
            text,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}
