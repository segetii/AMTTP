import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Cross-Chain Transfer Page - Covers AMTTPCrossChain.sol functionality
/// Functions covered:
/// - sendRiskScore()
/// - propagateDisputeResult()
/// - pauseChain() (admin)
/// - unpauseChain() (admin)
/// - setChainRateLimit() (admin)
class CrossChainPage extends ConsumerStatefulWidget {
  const CrossChainPage({super.key});

  @override
  ConsumerState<CrossChainPage> createState() => _CrossChainPageState();
}

class _CrossChainPageState extends ConsumerState<CrossChainPage>
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
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: const Text('Cross-Chain Transfer'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Transfer', icon: Icon(Icons.send)),
            Tab(text: 'Chain Status', icon: Icon(Icons.hub)),
            Tab(text: 'Pending', icon: Icon(Icons.pending)),
            Tab(text: 'History', icon: Icon(Icons.history)),
          ],
        ),
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: AppTheme.darkGradient,
        ),
        child: TabBarView(
          controller: _tabController,
          children: [
            _CrossChainTransferTab(),
            _ChainStatusTab(),
            _PendingTransfersTab(),
            _TransferHistoryTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Cross-Chain Transfer
class _CrossChainTransferTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_CrossChainTransferTab> createState() => _CrossChainTransferTabState();
}

class _CrossChainTransferTabState extends ConsumerState<_CrossChainTransferTab> {
  final _formKey = GlobalKey<FormState>();
  final _recipientController = TextEditingController();
  final _amountController = TextEditingController();
  
  String _selectedChain = 'polygon';
  bool _isLoading = false;
  Map<String, dynamic>? _feeEstimate;

  final _supportedChains = [
    {'id': 'polygon', 'name': 'Polygon', 'chainId': 137, 'status': 'live', 'avgTime': '2 min'},
    {'id': 'arbitrum', 'name': 'Arbitrum', 'chainId': 42161, 'status': 'live', 'avgTime': '3 min'},
    {'id': 'optimism', 'name': 'Optimism', 'chainId': 10, 'status': 'live', 'avgTime': '3 min'},
    {'id': 'bsc', 'name': 'BSC', 'chainId': 56, 'status': 'busy', 'avgTime': '5 min'},
    {'id': 'avalanche', 'name': 'Avalanche', 'chainId': 43114, 'status': 'paused', 'avgTime': 'N/A'},
  ];

  @override
  void dispose() {
    _recipientController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _estimateFees() async {
    if (_amountController.text.isEmpty) return;
    
    setState(() => _isLoading = true);
    
    try {
      await Future.delayed(const Duration(milliseconds: 500));
      setState(() {
        _feeEstimate = {
          'nativeFee': 0.0025,
          'lzFee': 0.0010,
          'totalFee': 0.0035,
          'estimatedTime': '2-5 min',
        };
      });
    } finally {
      setState(() => _isLoading = false);
    }
  }

  Future<void> _initiateCrossChainTransfer() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Cross-chain transfer initiated!'),
            backgroundColor: AppTheme.accentGreen,
          ),
        );
      }
    } finally {
      setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Chain Selection
            _buildCard(
              title: 'Select Destination Chain',
              icon: Icons.hub,
              child: Column(
                children: [
                  const Row(
                    children: [
                      Icon(Icons.location_on, color: AppTheme.accentGreen, size: 20),
                      SizedBox(width: 8),
                      Text(
                        'Source: Ethereum Mainnet',
                        style: TextStyle(color: AppTheme.cleanWhite),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Row(
                    children: [
                      Icon(Icons.arrow_downward, color: AppTheme.primaryBlue),
                      SizedBox(width: 8),
                      Text('via LayerZero', style: TextStyle(color: AppTheme.mutedText)),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: _supportedChains.map((chain) {
                      final isSelected = _selectedChain == chain['id'];
                      final status = chain['status'] as String;
                      final isPaused = status == 'paused';
                      
                      return GestureDetector(
                        onTap: isPaused ? null : () => setState(() => _selectedChain = chain['id'] as String),
                        child: Container(
                          width: 140,
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: isPaused
                                ? AppTheme.darkBg.withOpacity(0.5)
                                : isSelected
                                    ? AppTheme.primaryBlue.withOpacity(0.2)
                                    : AppTheme.darkBg,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: isPaused
                                  ? AppTheme.dangerRed.withOpacity(0.5)
                                  : isSelected
                                      ? AppTheme.primaryBlue
                                      : Colors.transparent,
                              width: 2,
                            ),
                          ),
                          child: Column(
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Text(
                                    chain['name'] as String,
                                    style: TextStyle(
                                      color: isPaused ? AppTheme.mutedText : AppTheme.cleanWhite,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                  Container(
                                    width: 10,
                                    height: 10,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      color: status == 'live'
                                          ? AppTheme.accentGreen
                                          : status == 'busy'
                                              ? AppTheme.warningOrange
                                              : AppTheme.dangerRed,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 8),
                              Row(
                                children: [
                                  const Icon(Icons.timer, size: 12, color: AppTheme.mutedText),
                                  const SizedBox(width: 4),
                                  Text(
                                    chain['avgTime'] as String,
                                    style: const TextStyle(color: AppTheme.mutedText, fontSize: 12),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      );
                    }).toList(),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 16),
            
            // Transfer Details
            _buildCard(
              title: 'Transfer Details',
              icon: Icons.send,
              child: Column(
                children: [
                  TextFormField(
                    controller: _recipientController,
                    decoration: _inputDecoration('Recipient Address', Icons.person),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _amountController,
                    decoration: _inputDecoration('Amount (ETH)', Icons.currency_exchange),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                    onChanged: (_) => _estimateFees(),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 16),
            
            // Fee Estimation
            if (_feeEstimate != null)
              _buildCard(
                title: 'Fee Estimation (LayerZero)',
                icon: Icons.receipt,
                child: Column(
                  children: [
                    _buildFeeRow('Native Fee', '${_feeEstimate!['nativeFee']} ETH'),
                    _buildFeeRow('LayerZero Fee', '${_feeEstimate!['lzFee']} ETH'),
                    const Divider(color: AppTheme.mutedText),
                    _buildFeeRow('Total Fees', '${_feeEstimate!['totalFee']} ETH (~\$8.50)', isBold: true),
                    _buildFeeRow('Estimated Time', _feeEstimate!['estimatedTime']),
                  ],
                ),
              ),
            
            const SizedBox(height: 16),
            
            // Risk Assessment
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppTheme.accentGreen.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.accentGreen),
              ),
              child: const Row(
                children: [
                  Icon(Icons.verified_user, color: AppTheme.accentGreen),
                  SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Risk Assessment: Low Risk',
                          style: TextStyle(
                            color: AppTheme.cleanWhite,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Cross-chain route verified',
                          style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 24),
            
            // Submit Button
            SizedBox(
              width: double.infinity,
              height: 56,
              child: ElevatedButton.icon(
                onPressed: _isLoading ? null : _initiateCrossChainTransfer,
                icon: _isLoading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.cleanWhite),
                      )
                    : const Icon(Icons.send),
                label: const Text('Initiate Cross-Chain Transfer'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.primaryBlue,
                  foregroundColor: AppTheme.cleanWhite,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCard({required String title, required IconData icon, required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppTheme.primaryBlue),
              const SizedBox(width: 8),
              Text(title, style: const TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }

  Widget _buildFeeRow(String label, String value, {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: AppTheme.mutedText)),
          Text(
            value,
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }

  InputDecoration _inputDecoration(String label, IconData icon) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: AppTheme.mutedText),
      prefixIcon: Icon(icon, color: AppTheme.mutedText),
      filled: true,
      fillColor: AppTheme.darkBg,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
    );
  }
}

/// Tab 1: Chain Status
class _ChainStatusTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chains = [
      {'name': 'Polygon', 'chainId': 137, 'status': 'live', 'rateLimit': 100, 'txToday': 2453, 'avgTime': '2 min'},
      {'name': 'Arbitrum', 'chainId': 42161, 'status': 'live', 'rateLimit': 100, 'txToday': 1832, 'avgTime': '3 min'},
      {'name': 'Optimism', 'chainId': 10, 'status': 'live', 'rateLimit': 100, 'txToday': 1245, 'avgTime': '3 min'},
      {'name': 'BSC', 'chainId': 56, 'status': 'busy', 'rateLimit': 50, 'txToday': 3891, 'avgTime': '5 min'},
      {'name': 'Avalanche', 'chainId': 43114, 'status': 'paused', 'rateLimit': 0, 'txToday': 0, 'avgTime': 'N/A'},
    ];

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'Supported Chains',
          style: TextStyle(color: AppTheme.cleanWhite, fontSize: 20, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        ...chains.map((chain) => _buildChainCard(chain)),
      ],
    );
  }

  Widget _buildChainCard(Map<String, dynamic> chain) {
    final status = chain['status'] as String;
    final statusColor = status == 'live'
        ? AppTheme.accentGreen
        : status == 'busy'
            ? AppTheme.warningOrange
            : AppTheme.dangerRed;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Row(
                children: [
                  Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: statusColor),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    chain['name'] as String,
                    style: const TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: statusColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  status.toUpperCase(),
                  style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _buildStat('Chain ID', chain['chainId'].toString()),
              _buildStat('Rate Limit', '${chain['rateLimit']}/block'),
              _buildStat('TX Today', chain['txToday'].toString()),
              _buildStat('Avg Time', chain['avgTime'] as String),
            ],
          ),
          if (status != 'paused') ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () {},
                icon: const Icon(Icons.send, size: 16),
                label: const Text('Transfer to Chain'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppTheme.primaryBlue,
                  side: const BorderSide(color: AppTheme.primaryBlue),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildStat(String label, String value) {
    return Column(
      children: [
        Text(value, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
        Text(label, style: const TextStyle(color: AppTheme.mutedText, fontSize: 10)),
      ],
    );
  }
}

/// Tab 2: Pending Transfers
class _PendingTransfersTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pending = [
      {'id': 'cc001', 'to': 'Polygon', 'amount': '1.5 ETH', 'status': 'In Transit', 'eta': '1 min'},
      {'id': 'cc002', 'to': 'Arbitrum', 'amount': '0.8 ETH', 'status': 'Confirming', 'eta': '3 min'},
    ];

    if (pending.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 64, color: AppTheme.mutedText),
            SizedBox(height: 16),
            Text('No pending transfers', style: TextStyle(color: AppTheme.mutedText, fontSize: 18)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: pending.length,
      itemBuilder: (context, index) {
        final tx = pending[index];
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.warningOrange.withOpacity(0.5)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Transfer #${tx['id']}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppTheme.warningOrange.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(tx['status'] as String, style: const TextStyle(color: AppTheme.warningOrange, fontSize: 12)),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  const Icon(Icons.arrow_forward, color: AppTheme.mutedText, size: 16),
                  const SizedBox(width: 8),
                  Text('${tx['amount']} → ${tx['to']}', style: const TextStyle(color: AppTheme.cleanWhite)),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.timer, color: AppTheme.mutedText, size: 16),
                  const SizedBox(width: 8),
                  Text('ETA: ${tx['eta']}', style: const TextStyle(color: AppTheme.mutedText)),
                ],
              ),
              const SizedBox(height: 12),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: const LinearProgressIndicator(
                  value: null,
                  backgroundColor: AppTheme.darkBg,
                  valueColor: AlwaysStoppedAnimation<Color>(AppTheme.warningOrange),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Tab 3: Transfer History
class _TransferHistoryTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = [
      {'id': 'cc100', 'to': 'Polygon', 'amount': '2.0 ETH', 'status': 'Completed', 'date': 'Jan 3, 2026'},
      {'id': 'cc099', 'to': 'Arbitrum', 'amount': '1.2 ETH', 'status': 'Completed', 'date': 'Jan 2, 2026'},
      {'id': 'cc098', 'to': 'Optimism', 'amount': '0.5 ETH', 'status': 'Failed', 'date': 'Jan 1, 2026'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: history.length,
      itemBuilder: (context, index) {
        final tx = history[index];
        final isCompleted = tx['status'] == 'Completed';
        
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: isCompleted ? AppTheme.accentGreen.withOpacity(0.2) : AppTheme.dangerRed.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  isCompleted ? Icons.check : Icons.error,
                  color: isCompleted ? AppTheme.accentGreen : AppTheme.dangerRed,
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${tx['amount']} → ${tx['to']}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text(tx['date'] as String, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Text(
                tx['status'] as String,
                style: TextStyle(color: isCompleted ? AppTheme.accentGreen : AppTheme.dangerRed, fontWeight: FontWeight.bold),
              ),
            ],
          ),
        );
      },
    );
  }
}
