import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/web3/wallet_provider.dart';
import '../../../../core/theme/app_theme.dart';

class WalletPage extends ConsumerWidget {
  const WalletPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final walletState = ref.watch(walletProvider);
    final walletNotifier = ref.read(walletProvider.notifier);

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: const Text('My Wallet'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          if (walletState.isConnected)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: () => walletNotifier.refreshBalance(),
              tooltip: 'Refresh Balance',
            ),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Balance Card
                _buildBalanceCard(walletState),
                const SizedBox(height: 24),

                // Wallet Address Section
                _buildAddressSection(context, walletState),
                const SizedBox(height: 24),

                // Token Balances
                if (walletState.isConnected) ...[
                  _buildTokenBalances(walletState),
                  const SizedBox(height: 24),
                ],

                // Quick Actions
                if (walletState.isConnected) _buildQuickActions(context),

                // Connection Button (if not connected)
                if (!walletState.isConnected) ...[
                  const SizedBox(height: 24),
                  _buildConnectButton(context, ref),
                ],

                // Error Message
                if (walletState.hasError) ...[
                  const SizedBox(height: 16),
                  _buildErrorMessage(walletState.error ?? 'Unknown error'),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBalanceCard(WalletState walletState) {
    final ethBalance = walletState.ethBalance ?? 0.0;
    final usdValue = ethBalance * 2300; // Approximate ETH/USD

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        gradient: AppTheme.premiumGradient,
        borderRadius: BorderRadius.circular(24),
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
              Text(
                'Total Balance',
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.8),
                  fontSize: 14,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: walletState.isConnected
                      ? AppTheme.successGreen.withOpacity(0.2)
                      : AppTheme.textLight.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      walletState.isConnected ? Icons.link : Icons.link_off,
                      size: 12,
                      color: walletState.isConnected
                          ? AppTheme.successGreen
                          : AppTheme.textLight,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      walletState.isConnected ? 'Connected' : 'Disconnected',
                      style: TextStyle(
                        fontSize: 10,
                        color: walletState.isConnected
                            ? AppTheme.successGreen
                            : AppTheme.textLight,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            walletState.isConnected
                ? '${ethBalance.toStringAsFixed(4)} ETH'
                : '0.00 ETH',
            style: const TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: FontWeight.w800,
              fontSize: 36,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            walletState.isConnected
                ? '≈ \$${usdValue.toStringAsFixed(2)} USD'
                : '≈ \$0.00 USD',
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.7),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAddressSection(BuildContext context, WalletState walletState) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Wallet Address',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w600,
            fontSize: 16,
          ),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  walletState.isConnected
                      ? walletState.addressString
                      : 'Connect wallet to see address',
                  style: TextStyle(
                    color: walletState.isConnected
                        ? AppTheme.cleanWhite
                        : AppTheme.cleanWhite.withOpacity(0.7),
                    fontSize: 14,
                    fontFamily: walletState.isConnected ? 'monospace' : null,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              if (walletState.isConnected)
                IconButton(
                  icon: const Icon(Icons.copy, size: 20),
                  color: AppTheme.cleanWhite.withOpacity(0.7),
                  onPressed: () {
                    Clipboard.setData(
                        ClipboardData(text: walletState.addressString));
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text('Address copied to clipboard'),
                        duration: Duration(seconds: 2),
                      ),
                    );
                  },
                )
              else
                Icon(
                  Icons.wallet,
                  color: AppTheme.cleanWhite.withOpacity(0.5),
                  size: 20,
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTokenBalances(WalletState walletState) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Token Balances',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w600,
            fontSize: 16,
          ),
        ),
        const SizedBox(height: 12),
        _buildTokenRow(
          'Ethereum',
          'ETH',
          walletState.ethBalance ?? 0.0,
          Icons.currency_bitcoin,
          AppTheme.primaryBlue,
        ),
      ],
    );
  }

  Widget _buildTokenRow(
    String name,
    String symbol,
    double balance,
    IconData icon,
    Color color,
  ) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: color.withOpacity(0.2),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                Text(
                  symbol,
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.5),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Text(
            balance.toStringAsFixed(4),
            style: const TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: FontWeight.w600,
              fontSize: 16,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickActions(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Quick Actions',
          style: TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w600,
            fontSize: 16,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: _buildActionButton(
                context,
                'Transfer',
                Icons.arrow_upward_rounded,
                AppTheme.primaryPurple,
                () => context.go('/transfer'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildActionButton(
                context,
                'Receive',
                Icons.arrow_downward_rounded,
                AppTheme.successGreen,
                () {
                  // Show receive dialog with QR
                  _showReceiveDialog(context);
                },
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _buildActionButton(
                context,
                'History',
                Icons.history,
                AppTheme.primaryBlue,
                () => context.go('/history'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildActionButton(
    BuildContext context,
    String label,
    IconData icon,
    Color color,
    VoidCallback onTap,
  ) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: color.withOpacity(0.15),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 8),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConnectButton(BuildContext context, WidgetRef ref) {
    final walletState = ref.watch(walletProvider);
    final walletNotifier = ref.read(walletProvider.notifier);

    return SizedBox(
      width: double.infinity,
      child: ElevatedButton.icon(
        onPressed: walletState.isConnecting
            ? null
            : () => walletNotifier.connectWallet(),
        icon: walletState.isConnecting
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppTheme.cleanWhite,
                ),
              )
            : const Icon(Icons.account_balance_wallet),
        label: Text(
          walletState.isConnecting ? 'Connecting...' : 'Connect MetaMask',
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: AppTheme.primaryPurple,
          foregroundColor: AppTheme.cleanWhite,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
    );
  }

  Widget _buildErrorMessage(String error) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.errorRed.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.errorRed.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppTheme.errorRed, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              error,
              style: const TextStyle(color: AppTheme.errorRed, fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  void _showReceiveDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => Consumer(
        builder: (context, ref, _) {
          final walletState = ref.watch(walletProvider);
          return AlertDialog(
            backgroundColor: AppTheme.darkCard,
            title: const Text(
              'Receive',
              style: TextStyle(color: AppTheme.cleanWhite),
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: AppTheme.cleanWhite,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.qr_code_2,
                    size: 150,
                    color: AppTheme.darkBg,
                  ),
                ),
                const SizedBox(height: 16),
                SelectableText(
                  walletState.addressString,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 12,
                    fontFamily: 'monospace',
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () {
                  Clipboard.setData(
                      ClipboardData(text: walletState.addressString));
                  Navigator.pop(context);
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Address copied!')),
                  );
                },
                child: const Text('Copy Address'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: const Text('Close'),
              ),
            ],
          );
        },
      ),
    );
  }
}
