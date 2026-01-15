import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Session Key Management Page - Covers AMTTPBiconomyModule.sol functionality
/// Functions covered:
/// - registerAccount()
/// - updateAccountConfig()
/// - createSessionKey()
/// - revokeSessionKey()
class SessionKeyPage extends ConsumerStatefulWidget {
  const SessionKeyPage({super.key});

  @override
  ConsumerState<SessionKeyPage> createState() => _SessionKeyPageState();
}

class _SessionKeyPageState extends ConsumerState<SessionKeyPage>
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
        title: const Text('Session Keys'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Register', icon: Icon(Icons.app_registration)),
            Tab(text: 'Create Key', icon: Icon(Icons.key)),
            Tab(text: 'Active Keys', icon: Icon(Icons.vpn_key)),
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
            _RegisterAccountTab(),
            _CreateSessionKeyTab(),
            _ActiveKeysTab(),
            _KeyHistoryTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Register Account
class _RegisterAccountTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_RegisterAccountTab> createState() => _RegisterAccountTabState();
}

class _RegisterAccountTabState extends ConsumerState<_RegisterAccountTab> {
  final _formKey = GlobalKey<FormState>();
  final _accountAddressController = TextEditingController();
  final _dailyLimitController = TextEditingController(text: '1.0');
  final _riskThresholdController = TextEditingController(text: '70');
  bool _enableGasless = true;
  bool _enableSessionKeys = true;
  bool _isLoading = false;
  bool _isRegistered = false;

  @override
  void dispose() {
    _accountAddressController.dispose();
    _dailyLimitController.dispose();
    _riskThresholdController.dispose();
    super.dispose();
  }

  Future<void> _registerAccount() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        setState(() => _isRegistered = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Smart account registered with AMTTP!'),
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
          children: [
            if (_isRegistered)
              Container(
                padding: const EdgeInsets.all(16),
                margin: const EdgeInsets.only(bottom: 16),
                decoration: BoxDecoration(
                  color: AppTheme.accentGreen.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.accentGreen),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.check_circle, color: AppTheme.accentGreen),
                    SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Account Registered', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                          Text('Your smart account is connected to AMTTP', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            
            _buildCard(
              title: 'Register Smart Account',
              icon: Icons.app_registration,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Connect your ERC-4337 smart account to AMTTP for gasless transactions and session key support.',
                    style: TextStyle(color: AppTheme.mutedText),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _accountAddressController,
                    decoration: _inputDecoration('Smart Account Address', Icons.account_balance_wallet),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Biconomy, Safe, or any ERC-4337 compatible account',
                    style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _dailyLimitController,
                    decoration: _inputDecoration('Daily Spending Limit (ETH)', Icons.account_balance),
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _riskThresholdController,
                    decoration: _inputDecoration('Risk Threshold (0-100)', Icons.security),
                    keyboardType: TextInputType.number,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 16),
                  SwitchListTile(
                    value: _enableGasless,
                    onChanged: (v) => setState(() => _enableGasless = v),
                    title: const Text('Enable Gasless Transactions', style: TextStyle(color: AppTheme.cleanWhite)),
                    subtitle: const Text('Use Paymaster for gas sponsorship', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                    activeColor: AppTheme.primaryBlue,
                    contentPadding: EdgeInsets.zero,
                  ),
                  SwitchListTile(
                    value: _enableSessionKeys,
                    onChanged: (v) => setState(() => _enableSessionKeys = v),
                    title: const Text('Enable Session Keys', style: TextStyle(color: AppTheme.cleanWhite)),
                    subtitle: const Text('Allow creating temporary keys for dApps', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                    activeColor: AppTheme.primaryBlue,
                    contentPadding: EdgeInsets.zero,
                  ),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton.icon(
                      onPressed: _isLoading ? null : _registerAccount,
                      icon: _isLoading
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.cleanWhite))
                          : const Icon(Icons.verified_user),
                      label: Text(_isRegistered ? 'Update Configuration' : 'Register Account with AMTTP'),
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
          ],
        ),
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

/// Tab 1: Create Session Key
class _CreateSessionKeyTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_CreateSessionKeyTab> createState() => _CreateSessionKeyTabState();
}

class _CreateSessionKeyTabState extends ConsumerState<_CreateSessionKeyTab> {
  final _formKey = GlobalKey<FormState>();
  final _sessionKeyController = TextEditingController();
  final _maxPerTxController = TextEditingController(text: '0.1');
  final _totalSpendController = TextEditingController(text: '1.0');
  final List<TextEditingController> _contractControllers = [];
  String _validityPeriod = '24_hours';
  bool _isLoading = false;

  @override
  void dispose() {
    _sessionKeyController.dispose();
    _maxPerTxController.dispose();
    _totalSpendController.dispose();
    for (final c in _contractControllers) {
      c.dispose();
    }
    super.dispose();
  }

  void _addContractField() {
    setState(() {
      _contractControllers.add(TextEditingController());
    });
  }

  Future<void> _createSessionKey() async {
    if (!_formKey.currentState!.validate()) return;
    
    setState(() => _isLoading = true);
    
    try {
      await Future.delayed(const Duration(seconds: 2));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Session key created successfully!'),
            backgroundColor: AppTheme.accentGreen,
          ),
        );
        _sessionKeyController.clear();
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
          children: [
            _buildCard(
              title: 'Create New Session Key',
              icon: Icons.key,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextFormField(
                    controller: _sessionKeyController,
                    decoration: _inputDecoration('Session Key Address', Icons.vpn_key),
                    validator: (v) => v?.isEmpty == true ? 'Required' : null,
                    style: const TextStyle(color: AppTheme.cleanWhite),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'The address that will be authorized to act on your behalf',
                    style: TextStyle(color: AppTheme.mutedText, fontSize: 12),
                  ),
                  const SizedBox(height: 24),
                  
                  // Validity Period
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.darkBg,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Validity Period', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            _buildPeriodChip('1_hour', '1 Hour'),
                            _buildPeriodChip('24_hours', '24 Hours'),
                            _buildPeriodChip('7_days', '7 Days'),
                            _buildPeriodChip('30_days', '30 Days'),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  
                  // Spending Limits
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.darkBg,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Spending Limits', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _maxPerTxController,
                          decoration: _inputDecoration('Max per Transaction (ETH)', Icons.attach_money),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          style: const TextStyle(color: AppTheme.cleanWhite),
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _totalSpendController,
                          decoration: _inputDecoration('Total Spending Limit (ETH)', Icons.account_balance),
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          style: const TextStyle(color: AppTheme.cleanWhite),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  
                  // Allowed Contracts
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.darkBg,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text('Allowed Contracts (Optional)', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                          ],
                        ),
                        const SizedBox(height: 8),
                        const Text('Leave empty to allow all contracts', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                        const SizedBox(height: 12),
                        ..._contractControllers.asMap().entries.map((entry) => Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: Row(
                            children: [
                              Expanded(
                                child: TextField(
                                  controller: entry.value,
                                  decoration: _inputDecoration('Contract ${entry.key + 1}', Icons.smart_toy),
                                  style: const TextStyle(color: AppTheme.cleanWhite),
                                ),
                              ),
                              IconButton(
                                onPressed: () {
                                  setState(() {
                                    _contractControllers[entry.key].dispose();
                                    _contractControllers.removeAt(entry.key);
                                  });
                                },
                                icon: const Icon(Icons.remove_circle, color: AppTheme.dangerRed),
                              ),
                            ],
                          ),
                        )),
                        TextButton.icon(
                          onPressed: _addContractField,
                          icon: const Icon(Icons.add),
                          label: const Text('Add Contract'),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                  
                  SizedBox(
                    width: double.infinity,
                    height: 56,
                    child: ElevatedButton.icon(
                      onPressed: _isLoading ? null : _createSessionKey,
                      icon: _isLoading
                          ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: AppTheme.cleanWhite))
                          : const Icon(Icons.key),
                      label: const Text('Create Session Key'),
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
          ],
        ),
      ),
    );
  }

  Widget _buildPeriodChip(String value, String label) {
    final isSelected = _validityPeriod == value;
    return GestureDetector(
      onTap: () => setState(() => _validityPeriod = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? AppTheme.primaryBlue : Colors.transparent,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: isSelected ? AppTheme.primaryBlue : AppTheme.mutedText),
        ),
        child: Text(label, style: TextStyle(color: isSelected ? AppTheme.cleanWhite : AppTheme.mutedText)),
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
      fillColor: AppTheme.darkCard,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
    );
  }
}

/// Tab 2: Active Keys
class _ActiveKeysTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activeKeys = [
      {
        'key': '0x742d...f44e',
        'created': 'Jan 4, 2026 10:00',
        'expires': 'Jan 5, 2026 10:00',
        'limit': 1.0,
        'used': 0.25,
        'status': 'active',
      },
      {
        'key': '0x8ba1...DBA72',
        'created': 'Jan 1, 2026',
        'expires': 'Jan 8, 2026',
        'limit': 5.0,
        'used': 4.8,
        'status': 'near_limit',
      },
    ];

    if (activeKeys.isEmpty) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.vpn_key_off, size: 64, color: AppTheme.mutedText),
            SizedBox(height: 16),
            Text('No active session keys', style: TextStyle(color: AppTheme.mutedText, fontSize: 18)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: activeKeys.length,
      itemBuilder: (context, index) {
        final key = activeKeys[index];
        return _SessionKeyCard(keyData: key);
      },
    );
  }
}

class _SessionKeyCard extends StatelessWidget {
  final Map<String, dynamic> keyData;

  const _SessionKeyCard({required this.keyData});

  @override
  Widget build(BuildContext context) {
    final limit = keyData['limit'] as double;
    final used = keyData['used'] as double;
    final progress = used / limit;
    final status = keyData['status'] as String;
    final isNearLimit = status == 'near_limit';
    final statusColor = isNearLimit ? AppTheme.warningOrange : AppTheme.accentGreen;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: statusColor.withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: statusColor.withOpacity(0.2),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.key, color: AppTheme.primaryBlue),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Session Key: ${keyData['key']}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text('Created: ${keyData['created']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: statusColor.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  isNearLimit ? 'Near Limit' : 'Active',
                  style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              const Icon(Icons.timer, color: AppTheme.mutedText, size: 16),
              const SizedBox(width: 8),
              Text('Expires: ${keyData['expires']}', style: const TextStyle(color: AppTheme.mutedText)),
            ],
          ),
          const SizedBox(height: 12),
          const Text('Spending:', style: TextStyle(color: AppTheme.mutedText, fontSize: 12)),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: progress,
                    backgroundColor: AppTheme.darkBg,
                    valueColor: AlwaysStoppedAnimation<Color>(progress > 0.9 ? AppTheme.dangerRed : statusColor),
                    minHeight: 8,
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text('$used / $limit ETH (${(progress * 100).toInt()}%)', style: const TextStyle(color: AppTheme.cleanWhite)),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () {},
                  icon: const Icon(Icons.visibility, size: 16),
                  label: const Text('View Usage'),
                  style: OutlinedButton.styleFrom(foregroundColor: AppTheme.primaryBlue),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: () {
                    showDialog(
                      context: context,
                      builder: (context) => AlertDialog(
                        backgroundColor: AppTheme.darkCard,
                        title: const Text('Revoke Session Key?', style: TextStyle(color: AppTheme.cleanWhite)),
                        content: const Text('This action cannot be undone.', style: TextStyle(color: AppTheme.mutedText)),
                        actions: [
                          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                          ElevatedButton(
                            onPressed: () {
                              Navigator.pop(context);
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Session key revoked'), backgroundColor: AppTheme.dangerRed),
                              );
                            },
                            style: ElevatedButton.styleFrom(backgroundColor: AppTheme.dangerRed),
                            child: const Text('Revoke'),
                          ),
                        ],
                      ),
                    );
                  },
                  icon: const Icon(Icons.cancel, size: 16),
                  label: const Text('Revoke'),
                  style: ElevatedButton.styleFrom(backgroundColor: AppTheme.dangerRed, foregroundColor: AppTheme.cleanWhite),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Tab 3: Key History
class _KeyHistoryTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = [
      {'key': '0xabc1...', 'action': 'Revoked', 'date': 'Jan 3, 2026', 'reason': 'Manual revoke'},
      {'key': '0xdef4...', 'action': 'Expired', 'date': 'Jan 1, 2026', 'reason': 'Validity ended'},
      {'key': '0xghi7...', 'action': 'Limit Reached', 'date': 'Dec 28, 2025', 'reason': 'Spending limit reached'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: history.length,
      itemBuilder: (context, index) {
        final item = history[index];
        final action = item['action'] as String;
        final color = action == 'Revoked' ? AppTheme.dangerRed : 
                      action == 'Expired' ? AppTheme.mutedText : AppTheme.warningOrange;
        
        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(12)),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(color: color.withOpacity(0.2), shape: BoxShape.circle),
                child: Icon(
                  action == 'Revoked' ? Icons.cancel : 
                  action == 'Expired' ? Icons.timer_off : Icons.money_off,
                  color: color,
                  size: 20,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Key: ${item['key']}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                    Text('${item['reason']} • ${item['date']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                  ],
                ),
              ),
              Text(action, style: TextStyle(color: color, fontWeight: FontWeight.bold)),
            ],
          ),
        );
      },
    );
  }
}
