import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Safe Management Page - Covers AMTTPSafeModule.sol functionality
/// Functions covered:
/// - registerSafe()
/// - updateSafeConfig()
/// - approveQueuedTransaction()
/// - rejectQueuedTransaction()
/// - executeQueuedTransaction()
/// - addToWhitelist()
/// - removeFromWhitelist()
/// - addToBlacklist()
/// - removeFromBlacklist()
class SafeManagementPage extends ConsumerStatefulWidget {
  const SafeManagementPage({super.key});

  @override
  ConsumerState<SafeManagementPage> createState() => _SafeManagementPageState();
}

class _SafeManagementPageState extends ConsumerState<SafeManagementPage>
    with TickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 5, vsync: this);
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
        title: const Text('Safe Management'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Register', icon: Icon(Icons.add_circle)),
            Tab(text: 'Queued TXs', icon: Icon(Icons.pending_actions)),
            Tab(text: 'Whitelist', icon: Icon(Icons.check_circle)),
            Tab(text: 'Blacklist', icon: Icon(Icons.block)),
            Tab(text: 'Audit Log', icon: Icon(Icons.history)),
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
            _RegisterSafeTab(),
            _QueuedTransactionsTab(),
            _WhitelistTab(),
            _BlacklistTab(),
            _AuditLogTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Register Safe
class _RegisterSafeTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_RegisterSafeTab> createState() => _RegisterSafeTabState();
}

class _RegisterSafeTabState extends ConsumerState<_RegisterSafeTab> {
  final _formKey = GlobalKey<FormState>();
  final _safeAddressController = TextEditingController();
  final _riskThresholdController = TextEditingController(text: '70');
  final List<TextEditingController> _operatorControllers = [TextEditingController()];
  bool _isLoading = false;

  // Mock registered safes
  final _registeredSafes = [
    {'address': '0x8ba1...f44e', 'operators': 3, 'threshold': 70, 'active': true},
    {'address': '0xAb58...eC9B', 'operators': 5, 'threshold': 85, 'active': true},
  ];

  @override
  void dispose() {
    _safeAddressController.dispose();
    _riskThresholdController.dispose();
    for (final c in _operatorControllers) {
      c.dispose();
    }
    super.dispose();
  }

  void _addOperatorField() {
    setState(() {
      _operatorControllers.add(TextEditingController());
    });
  }

  void _removeOperatorField(int index) {
    if (_operatorControllers.length > 1) {
      setState(() {
        _operatorControllers[index].dispose();
        _operatorControllers.removeAt(index);
      });
    }
  }

  Future<void> _registerSafe() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Safe registered with AMTTP successfully!'),
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Register New Safe Card
          _buildCard(
            title: 'Register Your Gnosis Safe',
            icon: Icons.add_moderator,
            child: Form(
              key: _formKey,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextFormField(
                    controller: _safeAddressController,
                    decoration: _inputDecoration('Safe Address', Icons.account_balance_wallet),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _riskThresholdController,
                    decoration: _inputDecoration('Risk Threshold (0-100)', Icons.security),
                    keyboardType: TextInputType.number,
                    validator: (v) {
                      if (v?.isEmpty == true) return 'Required';
                      final val = int.tryParse(v!);
                      if (val == null || val < 0 || val > 100) return 'Must be 0-100';
                      return null;
                    },
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Transactions with risk score above this threshold will require operator approval.',
                    style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Operators:',
                    style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  ...List.generate(_operatorControllers.length, (index) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Row(
                        children: [
                          Expanded(
                            child: TextFormField(
                              controller: _operatorControllers[index],
                              decoration: _inputDecoration('Operator ${index + 1} Address', Icons.person),
                              style: const TextStyle(color: AppTheme.cleanWhite),
                            ),
                          ),
                          if (_operatorControllers.length > 1)
                            IconButton(
                              onPressed: () => _removeOperatorField(index),
                              icon: const Icon(Icons.remove_circle, color: AppTheme.dangerRed),
                            ),
                        ],
                      ),
                    );
                  }),
                  TextButton.icon(
                    onPressed: _addOperatorField,
                    icon: const Icon(Icons.add),
                    label: const Text('Add Operator'),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.warningOrange.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTheme.warningOrange),
                    ),
                    child: const Row(
                      children: [
                        Icon(Icons.info, color: AppTheme.warningOrange, size: 20),
                        SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'AMTTP will act as a Guard for your Safe, requiring >50% operator approval for high-risk transactions.',
                            style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton.icon(
                      onPressed: _isLoading ? null : _registerSafe,
                      icon: _isLoading
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.cleanWhite))
                          : const Icon(Icons.verified_user),
                      label: const Text('Register Safe with AMTTP'),
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
          ),
          
          const SizedBox(height: 24),
          
          // Registered Safes
          const Text(
            'Your Registered Safes',
            style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          ..._registeredSafes.map((safe) => _buildSafeCard(safe)),
        ],
      ),
    );
  }

  Widget _buildSafeCard(Map<String, dynamic> safe) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.accentGreen.withOpacity(0.5)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.accentGreen.withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.account_balance_wallet, color: AppTheme.accentGreen),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Safe ${safe['address']}',
                  style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
                ),
                Text(
                  '${safe['operators']} Operators • Threshold: ${safe['threshold']}',
                  style: const TextStyle(color: AppTheme.mutedText, fontSize: 12),
                ),
              ],
            ),
          ),
          Row(
            children: [
              OutlinedButton(
                onPressed: () {},
                style: OutlinedButton.styleFrom(foregroundColor: AppTheme.primaryBlue),
                child: const Text('Manage'),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: () {},
                style: OutlinedButton.styleFrom(foregroundColor: AppTheme.mutedText),
                child: const Text('Config'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildCard({required String title, required IconData icon, required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: AppTheme.primaryBlue),
            const SizedBox(width: 8),
            Text(title, style: const TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
          ]),
          const SizedBox(height: 16),
          child,
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

/// Tab 1: Queued Transactions
class _QueuedTransactionsTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queuedTxs = [
      {
        'hash': '0xabc123...',
        'to': '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
        'value': '5.0 ETH',
        'riskScore': 78,
        'approvals': 2,
        'required': 4,
        'approvers': ['You', '0x8ba1...'],
      },
      {
        'hash': '0xdef456...',
        'to': '0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B',
        'value': '10.0 ETH',
        'riskScore': 65,
        'approvals': 3,
        'required': 4,
        'approvers': ['You', '0x8ba1...', '0xAb58...'],
      },
    ];

    if (queuedTxs.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.check_circle_outline, size: 64, color: AppTheme.mutedText),
            SizedBox(height: 16),
            Text('No queued transactions', style: TextStyle(color: AppTheme.mutedText, fontSize: 18)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: queuedTxs.length,
      itemBuilder: (context, index) {
        final tx = queuedTxs[index];
        return _QueuedTxCard(tx: tx);
      },
    );
  }
}

class _QueuedTxCard extends StatelessWidget {
  final Map<String, dynamic> tx;

  const _QueuedTxCard({required this.tx});

  @override
  Widget build(BuildContext context) {
    final approvals = tx['approvals'] as int;
    final required = tx['required'] as int;
    final progress = approvals / required;
    final canExecute = approvals >= (required * 0.5).ceil();
    final riskScore = tx['riskScore'] as int;
    final riskColor = riskScore >= 70 ? AppTheme.dangerRed : riskScore >= 50 ? AppTheme.warningOrange : AppTheme.accentGreen;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: riskColor.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('TX Hash: ${tx['hash']}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(color: riskColor.withOpacity(0.2), borderRadius: BorderRadius.circular(20)),
                child: Text('Risk: $riskScore', style: TextStyle(color: riskColor, fontSize: 12, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text('To: ${tx['to']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
          Text('Value: ${tx['value']}', style: const TextStyle(color: AppTheme.cleanWhite)),
          const SizedBox(height: 16),
          const Text('Approval Progress:', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: progress,
                    backgroundColor: AppTheme.darkBg,
                    valueColor: AlwaysStoppedAnimation<Color>(canExecute ? AppTheme.accentGreen : AppTheme.warningOrange),
                    minHeight: 8,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text('$approvals/$required (${(progress * 100).toInt()}%)', style: const TextStyle(color: AppTheme.cleanWhite)),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: (tx['approvers'] as List).map((a) => Chip(
              label: Text(a, style: const TextStyle(fontSize: 10)),
              backgroundColor: AppTheme.accentGreen.withOpacity(0.2),
              labelStyle: const TextStyle(color: AppTheme.accentGreen),
              avatar: const Icon(Icons.check, size: 14, color: AppTheme.accentGreen),
            )).toList(),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.check),
                  label: const Text('Approve'),
                  style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen, foregroundColor: AppTheme.cleanWhite),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.close),
                  label: const Text('Reject'),
                  style: OutlinedButton.styleFrom(foregroundColor: AppTheme.dangerRed, side: const BorderSide(color: AppTheme.dangerRed)),
                ),
              ),
              if (canExecute) ...[
                const SizedBox(width: 8),
                Expanded(
                  child: ElevatedButton.icon(
                    onPressed: () {},
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Execute'),
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primaryBlue, foregroundColor: AppTheme.cleanWhite),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

/// Tab 2: Whitelist
class _WhitelistTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_WhitelistTab> createState() => _WhitelistTabState();
}

class _WhitelistTabState extends ConsumerState<_WhitelistTab> {
  final _addressController = TextEditingController();
  final _whitelist = [
    {'address': '0x742d...f44e', 'label': 'Exchange'},
    {'address': '0x8ba1...DBA72', 'label': 'Partner'},
    {'address': '0xAb58...eC9B', 'label': 'Treasury'},
  ];

  @override
  void dispose() {
    _addressController.dispose();
    super.dispose();
  }

  void _addToWhitelist() {
    if (_addressController.text.isEmpty) return;
    setState(() {
      _whitelist.add({'address': _addressController.text, 'label': 'New'});
      _addressController.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Address added to whitelist'), backgroundColor: AppTheme.accentGreen),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.add_circle, color: AppTheme.accentGreen),
                  SizedBox(width: 8),
                  Text('Add to Whitelist', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _addressController,
                      decoration: InputDecoration(
                        hintText: 'Enter address to whitelist',
                        hintStyle: const TextStyle(color: AppTheme.mutedText),
                        filled: true,
                        fillColor: AppTheme.darkBg,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                      ),
                      style: const TextStyle(color: AppTheme.cleanWhite),
                    ),
                  ),
                  const SizedBox(width: 12),
                  ElevatedButton(
                    onPressed: _addToWhitelist,
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen, padding: const EdgeInsets.all(16)),
                    child: const Icon(Icons.add, color: AppTheme.cleanWhite),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const Text('Whitelisted Addresses', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        ..._whitelist.map((item) => Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(12)),
          child: Row(
            children: [
              const Icon(Icons.check_circle, color: AppTheme.accentGreen),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item['address']!, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text(item['label']!, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              IconButton(
                onPressed: () {
                  setState(() => _whitelist.remove(item));
                },
                icon: const Icon(Icons.delete, color: AppTheme.dangerRed),
              ),
            ],
          ),
        )),
      ],
    );
  }
}

/// Tab 3: Blacklist
class _BlacklistTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_BlacklistTab> createState() => _BlacklistTabState();
}

class _BlacklistTabState extends ConsumerState<_BlacklistTab> {
  final _addressController = TextEditingController();
  final _blacklist = [
    {'address': '0xdead...beef', 'label': 'Sanctioned'},
    {'address': '0xbeef...dead', 'label': 'Scammer'},
  ];

  @override
  void dispose() {
    _addressController.dispose();
    super.dispose();
  }

  void _addToBlacklist() {
    if (_addressController.text.isEmpty) return;
    setState(() {
      _blacklist.add({'address': _addressController.text, 'label': 'Blocked'});
      _addressController.clear();
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Address added to blacklist'), backgroundColor: AppTheme.dangerRed),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Row(
                children: [
                  Icon(Icons.block, color: AppTheme.dangerRed),
                  SizedBox(width: 8),
                  Text('Add to Blacklist', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _addressController,
                      decoration: InputDecoration(
                        hintText: 'Enter address to block',
                        hintStyle: const TextStyle(color: AppTheme.mutedText),
                        filled: true,
                        fillColor: AppTheme.darkBg,
                        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                      ),
                      style: const TextStyle(color: AppTheme.cleanWhite),
                    ),
                  ),
                  const SizedBox(width: 12),
                  ElevatedButton(
                    onPressed: _addToBlacklist,
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.dangerRed, padding: const EdgeInsets.all(16)),
                    child: const Icon(Icons.block, color: AppTheme.cleanWhite),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        const Text('Blacklisted Addresses', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
        const SizedBox(height: 12),
        ..._blacklist.map((item) => Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppTheme.dangerRed.withOpacity(0.5))),
          child: Row(
            children: [
              const Icon(Icons.block, color: AppTheme.dangerRed),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item['address']!, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text(item['label']!, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              IconButton(
                onPressed: () {
                  setState(() => _blacklist.remove(item));
                },
                icon: const Icon(Icons.remove_circle, color: AppTheme.warningOrange),
              ),
            ],
          ),
        )),
      ],
    );
  }
}

/// Tab 4: Audit Log
class _AuditLogTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final logs = [
      {'action': 'TX Approved', 'txHash': '0xdef456...', 'by': '0x742d...', 'time': '2 min ago'},
      {'action': 'TX Approved', 'txHash': '0xdef456...', 'by': '0x8ba1...', 'time': '15 min ago'},
      {'action': 'Safe Registered', 'txHash': '', 'by': 'You', 'time': '1 hour ago'},
      {'action': 'Whitelist Added', 'txHash': '0xAb58...', 'by': 'You', 'time': '2 hours ago'},
      {'action': 'TX Executed', 'txHash': '0xabc123...', 'by': '0x742d...', 'time': '3 hours ago'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: logs.length,
      itemBuilder: (context, index) {
        final log = logs[index];
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(12)),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: AppTheme.primaryBlue.withOpacity(0.2), shape: BoxShape.circle),
                child: const Icon(Icons.history, color: AppTheme.primaryBlue, size: 20),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(log['action']!, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    if (log['txHash']!.isNotEmpty)
                      Text('TX: ${log['txHash']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                    Text('By: ${log['by']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Text(log['time']!, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
            ],
          ),
        );
      },
    );
  }
}
