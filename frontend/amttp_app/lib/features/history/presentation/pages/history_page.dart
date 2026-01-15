import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/web3/wallet_provider.dart';
import '../../../../core/services/api_service.dart';

// Transaction history provider
final transactionHistoryProvider = FutureProvider.family<List<TransactionHistoryItem>, String>((ref, address) async {
  if (address.isEmpty) return [];
  
  try {
    final apiService = ApiService();
    return await apiService.getTransactionHistory(address);
  } catch (e) {
    // Return mock data for demo
    return _generateMockTransactions();
  }
});

List<TransactionHistoryItem> _generateMockTransactions() {
  final now = DateTime.now();
  return [
    TransactionHistoryItem(
      txId: '0x1a2b3c4d5e6f...',
      fromAddress: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
      toAddress: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
      amount: 0.15,
      asset: 'ETH',
      timestamp: now.subtract(const Duration(hours: 2)),
      status: 'confirmed',
      riskScore: 12.5,
    ),
    TransactionHistoryItem(
      txId: '0x2b3c4d5e6f7g...',
      fromAddress: '0x8ba1f109551bD432803012645Ac136ddd64DBA72',
      toAddress: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
      amount: 0.25,
      asset: 'ETH',
      timestamp: now.subtract(const Duration(hours: 5)),
      status: 'confirmed',
      riskScore: 8.2,
    ),
    TransactionHistoryItem(
      txId: '0x3c4d5e6f7g8h...',
      fromAddress: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
      toAddress: '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
      amount: 1.5,
      asset: 'ETH',
      timestamp: now.subtract(const Duration(days: 1)),
      status: 'confirmed',
      riskScore: 45.0,
    ),
    TransactionHistoryItem(
      txId: '0x4d5e6f7g8h9i...',
      fromAddress: '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
      toAddress: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
      amount: 0.5,
      asset: 'ETH',
      timestamp: now.subtract(const Duration(days: 2)),
      status: 'confirmed',
      riskScore: 5.0,
    ),
    TransactionHistoryItem(
      txId: '0x5e6f7g8h9i0j...',
      fromAddress: '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
      toAddress: '0xdAC17F958D2ee523a2206206994597C13D831ec7',
      amount: 0.08,
      asset: 'ETH',
      timestamp: now.subtract(const Duration(days: 3)),
      status: 'confirmed',
      riskScore: 22.0,
    ),
  ];
}

class HistoryPage extends ConsumerWidget {
  const HistoryPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final walletState = ref.watch(walletProvider);
    final address = walletState.addressString;
    final transactionsAsync = ref.watch(transactionHistoryProvider(address));

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: const Text('Transaction History'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.filter_list),
            onPressed: () => _showFilterSheet(context),
            tooltip: 'Filter',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.refresh(transactionHistoryProvider(address)),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: SafeArea(
          child: !walletState.isConnected
              ? _buildConnectPrompt(context, ref)
              : transactionsAsync.when(
                  loading: () => const Center(
                    child: CircularProgressIndicator(color: AppTheme.primaryPurple),
                  ),
                  error: (error, stack) => _buildErrorState(error.toString()),
                  data: (transactions) => transactions.isEmpty
                      ? _buildEmptyState()
                      : _buildTransactionList(context, transactions, address),
                ),
        ),
      ),
    );
  }

  Widget _buildConnectPrompt(BuildContext context, WidgetRef ref) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.account_balance_wallet_outlined,
              size: 64,
              color: AppTheme.cleanWhite.withOpacity(0.5),
            ),
            const SizedBox(height: 16),
            Text(
              'Connect Wallet',
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.8),
                fontSize: 20,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Connect your wallet to view transaction history',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.5),
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: () => ref.read(walletProvider.notifier).connectWallet(),
              icon: const Icon(Icons.account_balance_wallet),
              label: const Text('Connect MetaMask'),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primaryPurple,
                foregroundColor: AppTheme.cleanWhite,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.receipt_long_outlined,
            size: 64,
            color: AppTheme.cleanWhite.withOpacity(0.5),
          ),
          const SizedBox(height: 16),
          Text(
            'No Transactions',
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.8),
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Your transaction history will appear here',
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.5),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorState(String error) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(
            Icons.error_outline,
            size: 64,
            color: AppTheme.errorRed,
          ),
          const SizedBox(height: 16),
          Text(
            'Error Loading History',
            style: TextStyle(
              color: AppTheme.cleanWhite.withOpacity(0.8),
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Text(
              error,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.5),
                fontSize: 14,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTransactionList(BuildContext context, List<TransactionHistoryItem> transactions, String currentAddress) {
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: transactions.length,
      itemBuilder: (context, index) {
        final tx = transactions[index];
        final isReceived = tx.toAddress.toLowerCase() == currentAddress.toLowerCase();
        
        return GestureDetector(
          onTap: () => _showTransactionDetails(context, tx),
          child: Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
            ),
            child: Row(
              children: [
                // Direction icon
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: (isReceived ? AppTheme.successGreen : AppTheme.primaryPurple).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    isReceived ? Icons.arrow_downward_rounded : Icons.arrow_upward_rounded,
                    color: isReceived ? AppTheme.successGreen : AppTheme.primaryPurple,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 16),
                
                // Transaction info
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            isReceived ? 'Received' : 'Sent',
                            style: const TextStyle(
                              color: AppTheme.cleanWhite,
                              fontWeight: FontWeight.w600,
                              fontSize: 16,
                            ),
                          ),
                          const SizedBox(width: 8),
                          _buildRiskBadge(tx.riskScore),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        isReceived 
                            ? 'From: ${_shortenAddress(tx.fromAddress)}'
                            : 'To: ${_shortenAddress(tx.toAddress)}',
                        style: TextStyle(
                          color: AppTheme.cleanWhite.withOpacity(0.6),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                
                // Amount and time
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '${isReceived ? '+' : '-'}${tx.amount.toStringAsFixed(4)} ${tx.asset}',
                      style: TextStyle(
                        color: isReceived ? AppTheme.successGreen : AppTheme.cleanWhite,
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _formatTimestamp(tx.timestamp),
                      style: TextStyle(
                        color: AppTheme.cleanWhite.withOpacity(0.5),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildRiskBadge(double riskScore) {
    Color color;
    String label;
    
    if (riskScore < 25) {
      color = AppTheme.successGreen;
      label = 'Low';
    } else if (riskScore < 50) {
      color = AppTheme.warningOrange;
      label = 'Med';
    } else if (riskScore < 75) {
      color = AppTheme.errorRed;
      label = 'High';
    } else {
      color = Colors.red.shade900;
      label = 'Crit';
    }
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withOpacity(0.2),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  String _shortenAddress(String address) {
    if (address.length < 10) return address;
    return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
  }

  String _formatTimestamp(DateTime timestamp) {
    final now = DateTime.now();
    final diff = now.difference(timestamp);
    
    if (diff.inMinutes < 60) {
      return '${diff.inMinutes} min ago';
    } else if (diff.inHours < 24) {
      return '${diff.inHours} hours ago';
    } else if (diff.inDays < 7) {
      return '${diff.inDays} days ago';
    } else {
      return '${timestamp.day}/${timestamp.month}/${timestamp.year}';
    }
  }

  void _showFilterSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTheme.darkCard,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Container(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Filter Transactions',
              style: TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 20),
            _buildFilterOption('All Transactions', true),
            _buildFilterOption('Sent', false),
            _buildFilterOption('Received', false),
            _buildFilterOption('High Risk Only', false),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildFilterOption(String label, bool selected) {
    return ListTile(
      title: Text(
        label,
        style: TextStyle(
          color: AppTheme.cleanWhite.withOpacity(selected ? 1.0 : 0.7),
        ),
      ),
      trailing: selected 
          ? const Icon(Icons.check, color: AppTheme.primaryPurple)
          : null,
      onTap: () {},
    );
  }

  void _showTransactionDetails(BuildContext context, TransactionHistoryItem tx) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTheme.darkCard,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => Container(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Transaction Details',
                  style: TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: AppTheme.cleanWhite),
                  onPressed: () => Navigator.pop(context),
                ),
              ],
            ),
            const SizedBox(height: 20),
            _buildDetailRow('Status', tx.status.toUpperCase(), AppTheme.successGreen),
            _buildDetailRow('Amount', '${tx.amount} ${tx.asset}', null),
            _buildDetailRow('Risk Score', '${tx.riskScore.toStringAsFixed(1)}%', _getRiskColor(tx.riskScore)),
            _buildDetailRow('From', tx.fromAddress, null, isAddress: true),
            _buildDetailRow('To', tx.toAddress, null, isAddress: true),
            _buildDetailRow('Transaction ID', tx.txId, null, isAddress: true),
            _buildDetailRow('Timestamp', tx.timestamp.toString(), null),
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {
                  // Open in block explorer
                },
                icon: const Icon(Icons.open_in_new),
                label: const Text('View on Explorer'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.primaryPurple,
                  foregroundColor: AppTheme.cleanWhite,
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailRow(String label, String value, Color? valueColor, {bool isAddress = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.6),
                fontSize: 14,
              ),
            ),
          ),
          Expanded(
            child: Text(
              isAddress ? _shortenAddress(value) : value,
              style: TextStyle(
                color: valueColor ?? AppTheme.cleanWhite,
                fontSize: 14,
                fontWeight: FontWeight.w500,
                fontFamily: isAddress ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Color _getRiskColor(double score) {
    if (score < 25) return AppTheme.successGreen;
    if (score < 50) return AppTheme.warningOrange;
    if (score < 75) return AppTheme.errorRed;
    return Colors.red.shade900;
  }
}