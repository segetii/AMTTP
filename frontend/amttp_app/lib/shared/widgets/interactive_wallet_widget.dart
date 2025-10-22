import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/web3/wallet_provider.dart';
import '../../core/theme/app_theme.dart';
import '../../services/web3_service.dart';

class InteractiveWalletWidget extends ConsumerWidget {
  const InteractiveWalletWidget({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final walletState = ref.watch(walletProvider);
    final web3Service = Web3Service.instance;

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppTheme.primaryPurple.withOpacity(0.1),
            blurRadius: 16,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          const Row(
            children: [
              Icon(
                Icons.account_balance_wallet,
                color: AppTheme.primaryPurple,
                size: 24,
              ),
              SizedBox(width: 12),
              Text(
                'Wallet Connection',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: AppTheme.primaryPurple,
                ),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // MetaMask Detection Status
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: web3Service.isMetaMaskAvailable
                  ? Colors.green.withOpacity(0.1)
                  : Colors.orange.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: web3Service.isMetaMaskAvailable
                    ? Colors.green
                    : Colors.orange,
                width: 1,
              ),
            ),
            child: Row(
              children: [
                Icon(
                  web3Service.isMetaMaskAvailable
                      ? Icons.check_circle
                      : Icons.warning,
                  color: web3Service.isMetaMaskAvailable
                      ? Colors.green
                      : Colors.orange,
                  size: 20,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    web3Service.isMetaMaskAvailable
                        ? 'MetaMask detected ✅'
                        : 'MetaMask not detected ⚠️',
                    style: TextStyle(
                      color: web3Service.isMetaMaskAvailable
                          ? Colors.green.shade700
                          : Colors.orange.shade700,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // Connection Status
          if (walletState.isConnected)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.green),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.check_circle, color: Colors.green, size: 20),
                      const SizedBox(width: 8),
                      Text(
                        'Wallet Connected',
                        style: TextStyle(
                          color: Colors.green.shade700,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Address: ${walletState.formattedAddress}',
                    style: TextStyle(
                      color: Colors.green.shade600,
                      fontSize: 12,
                      fontFamily: 'monospace',
                    ),
                  ),
                  if (walletState.balance != null)
                    Text(
                      'AMTTP Balance: ${walletState.balance!.toStringAsFixed(2)}',
                      style: TextStyle(
                        color: Colors.green.shade600,
                        fontSize: 12,
                      ),
                    ),
                  if (walletState.ethBalance != null)
                    Text(
                      'ETH Balance: ${walletState.ethBalance!.toStringAsFixed(4)}',
                      style: TextStyle(
                        color: Colors.green.shade600,
                        fontSize: 12,
                      ),
                    ),
                ],
              ),
            ),

          // Error Display
          if (walletState.hasError)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.red.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.red),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error, color: Colors.red, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      walletState.error ?? 'Unknown error',
                      style: TextStyle(
                        color: Colors.red.shade700,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
            ),

          const SizedBox(height: 20),

          // Action Buttons
          if (!walletState.isConnected) ...[
            // Connect Button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: walletState.isConnecting
                    ? null
                    : () async {
                        try {
                          await ref
                              .read(walletProvider.notifier)
                              .connectWallet();
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text('Wallet connected successfully!'),
                              backgroundColor: Colors.green,
                            ),
                          );
                        } catch (e) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Failed to connect: $e'),
                              backgroundColor: Colors.red,
                            ),
                          );
                        }
                      },
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.primaryPurple,
                  foregroundColor: AppTheme.cleanWhite,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                child: walletState.isConnecting
                    ? const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              color: AppTheme.cleanWhite,
                              strokeWidth: 2,
                            ),
                          ),
                          SizedBox(width: 12),
                          Text('Connecting...'),
                        ],
                      )
                    : const Text(
                        'Connect MetaMask Wallet',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
              ),
            ),

            const SizedBox(height: 12),

            // Install MetaMask Button (if not detected)
            if (!web3Service.isMetaMaskAvailable)
              SizedBox(
                width: double.infinity,
                child: OutlinedButton(
                  onPressed: () {
                    // Open MetaMask installation page
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content:
                            const Text('Please install MetaMask from metamask.io'),
                        action: SnackBarAction(
                          label: 'Got it',
                          onPressed: () {},
                        ),
                      ),
                    );
                  },
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.primaryPurple,
                    side: const BorderSide(color: AppTheme.primaryPurple),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: const Text(
                    'Install MetaMask Extension',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
          ] else ...[
            // Disconnect Button
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () {
                      ref.read(walletProvider.notifier).disconnect();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Wallet disconnected'),
                          backgroundColor: Colors.orange,
                        ),
                      );
                    },
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.orange,
                      side: const BorderSide(color: Colors.orange),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text('Disconnect'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: () {
                      ref.read(walletProvider.notifier).refreshBalance();
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('Refreshing balance...'),
                          backgroundColor: AppTheme.primaryPurple,
                        ),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.primaryPurple,
                      foregroundColor: AppTheme.cleanWhite,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                    child: const Text('Refresh'),
                  ),
                ),
              ],
            ),
          ],

          const SizedBox(height: 16),

          // Debug Information
          if (walletState.hasError || !web3Service.isMetaMaskAvailable)
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.lightAsh,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Troubleshooting:',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: AppTheme.textDark,
                    ),
                  ),
                  const SizedBox(height: 8),
                  if (!web3Service.isMetaMaskAvailable) ...[
                    const Text(
                      '1. Install MetaMask browser extension from metamask.io',
                      style: TextStyle(fontSize: 12, color: AppTheme.textLight),
                    ),
                    const Text(
                      '2. Refresh this page after installation',
                      style: TextStyle(fontSize: 12, color: AppTheme.textLight),
                    ),
                  ],
                  if (web3Service.isMetaMaskAvailable &&
                      walletState.hasError) ...[
                    const Text(
                      '1. Make sure MetaMask is unlocked',
                      style: TextStyle(fontSize: 12, color: AppTheme.textLight),
                    ),
                    const Text(
                      '2. Check if you have accounts in MetaMask',
                      style: TextStyle(fontSize: 12, color: AppTheme.textLight),
                    ),
                    const Text(
                      '3. Try refreshing the page',
                      style: TextStyle(fontSize: 12, color: AppTheme.textLight),
                    ),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }
}
