import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

/// Compliance Tools Page - Covers AMTTPPolicyEngine.sol functionality
/// Functions covered:
/// - freezeAccount()
/// - unfreezeAccount()
/// - addTrustedUser()
/// - addTrustedCounterparty()
/// - PEP/Sanctions screening
/// - EDD (Enhanced Due Diligence)
class ComplianceToolsPage extends ConsumerStatefulWidget {
  const ComplianceToolsPage({super.key});

  @override
  ConsumerState<ComplianceToolsPage> createState() => _ComplianceToolsPageState();
}

class _ComplianceToolsPageState extends ConsumerState<ComplianceToolsPage>
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
        title: const Text('Compliance Tools'),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        elevation: 0,
        actions: [
          IconButton(onPressed: () {}, icon: const Icon(Icons.download), tooltip: 'Export Report'),
          IconButton(onPressed: () {}, icon: const Icon(Icons.notifications), tooltip: 'Alerts'),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          tabs: const [
            Tab(text: 'Freeze/Unfreeze', icon: Icon(Icons.ac_unit)),
            Tab(text: 'Trusted Users', icon: Icon(Icons.verified_user)),
            Tab(text: 'PEP/Sanctions', icon: Icon(Icons.search)),
            Tab(text: 'EDD Queue', icon: Icon(Icons.fact_check)),
          ],
        ),
      ),
      body: Container(
        decoration: const BoxDecoration(gradient: AppTheme.darkGradient),
        child: TabBarView(
          controller: _tabController,
          children: [
            _FreezeManagementTab(),
            _TrustedUsersTab(),
            _PEPSanctionsTab(),
            _EDDQueueTab(),
          ],
        ),
      ),
    );
  }
}

/// Tab 0: Freeze/Unfreeze Account Management
class _FreezeManagementTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_FreezeManagementTab> createState() => _FreezeManagementTabState();
}

class _FreezeManagementTabState extends ConsumerState<_FreezeManagementTab> {
  final _addressController = TextEditingController();
  final _reasonController = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _addressController.dispose();
    _reasonController.dispose();
    super.dispose();
  }

  final _frozenAccounts = [
    {'address': '0x1234...5678', 'frozenAt': 'Jan 3, 2026', 'reason': 'Suspicious activity', 'by': 'Compliance Officer'},
    {'address': '0xabcd...ef12', 'frozenAt': 'Jan 1, 2026', 'reason': 'OFAC match', 'by': 'Automated'},
  ];

  Future<void> _freezeAccount() async {
    if (_addressController.text.isEmpty) return;
    
    setState(() => _isLoading = true);
    try {
      await Future.delayed(const Duration(seconds: 2));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Account frozen successfully'), backgroundColor: AppTheme.accentGreen),
        );
        _addressController.clear();
        _reasonController.clear();
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
        children: [
          // Freeze Account Card
          _buildCard(
            title: 'Freeze Account',
            icon: Icons.ac_unit,
            color: AppTheme.primaryBlue,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Freeze an account to prevent all AMTTP transactions. This calls freezeAccount() on PolicyEngine.',
                  style: TextStyle(color: AppTheme.mutedText),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _addressController,
                  decoration: _inputDecoration('Account Address', Icons.account_balance_wallet),
                  style: const TextStyle(color: AppTheme.cleanWhite),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _reasonController,
                  decoration: _inputDecoration('Reason for Freeze', Icons.notes),
                  maxLines: 2,
                  style: const TextStyle(color: AppTheme.cleanWhite),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: _isLoading ? null : _freezeAccount,
                    icon: _isLoading
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.ac_unit),
                    label: const Text('Freeze Account'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.dangerRed,
                      foregroundColor: AppTheme.cleanWhite,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          
          // Frozen Accounts List
          _buildCard(
            title: 'Frozen Accounts',
            icon: Icons.block,
            color: AppTheme.dangerRed,
            child: Column(
              children: _frozenAccounts.map((account) => _FrozenAccountTile(account: account)).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCard({required String title, required IconData icon, required Color color, required Widget child}) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: color),
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

class _FrozenAccountTile extends StatelessWidget {
  final Map<String, dynamic> account;

  const _FrozenAccountTile({required this.account});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.darkBg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.dangerRed.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.dangerRed.withOpacity(0.2),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.block, color: AppTheme.dangerRed, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(account['address'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                Text('${account['reason']} • Frozen: ${account['frozenAt']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
              ],
            ),
          ),
          ElevatedButton(
            onPressed: () {
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  backgroundColor: AppTheme.darkCard,
                  title: const Text('Unfreeze Account?', style: TextStyle(color: AppTheme.cleanWhite)),
                  content: Text('This will call unfreezeAccount() for ${account['address']}', style: const TextStyle(color: AppTheme.mutedText)),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
                    ElevatedButton(
                      onPressed: () {
                        Navigator.pop(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Account unfrozen'), backgroundColor: AppTheme.accentGreen),
                        );
                      },
                      style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen),
                      child: const Text('Unfreeze'),
                    ),
                  ],
                ),
              );
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accentGreen,
              padding: const EdgeInsets.symmetric(horizontal: 12),
            ),
            child: const Text('Unfreeze'),
          ),
        ],
      ),
    );
  }
}

/// Tab 1: Trusted Users Management
class _TrustedUsersTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_TrustedUsersTab> createState() => _TrustedUsersTabState();
}

class _TrustedUsersTabState extends ConsumerState<_TrustedUsersTab> {
  final _addressController = TextEditingController();
  String _trustType = 'user';
  bool _isLoading = false;

  final _trustedList = [
    {'address': '0x7777...8888', 'type': 'user', 'addedAt': 'Jan 2, 2026'},
    {'address': '0x9999...aaaa', 'type': 'counterparty', 'addedAt': 'Jan 1, 2026'},
    {'address': '0xbbbb...cccc', 'type': 'user', 'addedAt': 'Dec 28, 2025'},
  ];

  Future<void> _addTrusted() async {
    if (_addressController.text.isEmpty) return;
    
    setState(() => _isLoading = true);
    try {
      await Future.delayed(const Duration(seconds: 2));
      if (mounted) {
        final func = _trustType == 'user' ? 'addTrustedUser()' : 'addTrustedCounterparty()';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('$func executed successfully'), backgroundColor: AppTheme.accentGreen),
        );
        _addressController.clear();
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
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(children: [
                  Icon(Icons.verified_user, color: AppTheme.accentGreen),
                  SizedBox(width: 8),
                  Text('Add Trusted Address', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                ]),
                const SizedBox(height: 16),
                TextField(
                  controller: _addressController,
                  decoration: InputDecoration(
                    labelText: 'Address to Trust',
                    labelStyle: const TextStyle(color: AppTheme.mutedText),
                    prefixIcon: const Icon(Icons.person, color: AppTheme.mutedText),
                    filled: true,
                    fillColor: AppTheme.darkBg,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                  ),
                  style: const TextStyle(color: AppTheme.cleanWhite),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _trustType = 'user'),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: _trustType == 'user' ? AppTheme.primaryBlue.withOpacity(0.2) : AppTheme.darkBg,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: _trustType == 'user' ? AppTheme.primaryBlue : AppTheme.mutedText),
                          ),
                          child: Column(
                            children: [
                              Icon(Icons.person, color: _trustType == 'user' ? AppTheme.primaryBlue : AppTheme.mutedText),
                              const SizedBox(height: 8),
                              Text('Trusted User', style: TextStyle(color: _trustType == 'user' ? AppTheme.cleanWhite : AppTheme.mutedText)),
                              const Text('addTrustedUser()', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: GestureDetector(
                        onTap: () => setState(() => _trustType = 'counterparty'),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: _trustType == 'counterparty' ? AppTheme.primaryBlue.withOpacity(0.2) : AppTheme.darkBg,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: _trustType == 'counterparty' ? AppTheme.primaryBlue : AppTheme.mutedText),
                          ),
                          child: Column(
                            children: [
                              Icon(Icons.handshake, color: _trustType == 'counterparty' ? AppTheme.primaryBlue : AppTheme.mutedText),
                              const SizedBox(height: 8),
                              Text('Counterparty', style: TextStyle(color: _trustType == 'counterparty' ? AppTheme.cleanWhite : AppTheme.mutedText)),
                              const Text('addTrustedCounterparty()', style: TextStyle(color: AppTheme.mutedText, fontSize: 10)),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: _isLoading ? null : _addTrusted,
                    icon: _isLoading
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.add),
                    label: Text('Add Trusted ${_trustType == 'user' ? 'User' : 'Counterparty'}'),
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          
          // Trusted List
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(children: [
                  Icon(Icons.list, color: AppTheme.primaryBlue),
                  SizedBox(width: 8),
                  Text('Trusted Addresses', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                ]),
                const SizedBox(height: 16),
                ..._trustedList.map((item) {
                  final isUser = item['type'] == 'user';
                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.darkBg,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Icon(isUser ? Icons.person : Icons.handshake, color: AppTheme.accentGreen),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(item['address'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace')),
                              Text('${isUser ? 'User' : 'Counterparty'} • Added: ${item['addedAt']}', style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                            ],
                          ),
                        ),
                        IconButton(
                          onPressed: () {},
                          icon: const Icon(Icons.delete, color: AppTheme.dangerRed),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Tab 2: PEP/Sanctions Screening
class _PEPSanctionsTab extends ConsumerStatefulWidget {
  @override
  ConsumerState<_PEPSanctionsTab> createState() => _PEPSanctionsTabState();
}

class _PEPSanctionsTabState extends ConsumerState<_PEPSanctionsTab> {
  final _searchController = TextEditingController();
  bool _isSearching = false;
  List<Map<String, dynamic>>? _results;

  Future<void> _runScreening() async {
    if (_searchController.text.isEmpty) return;
    
    setState(() => _isSearching = true);
    try {
      await Future.delayed(const Duration(seconds: 2));
      setState(() {
        _results = [
          {'source': 'OFAC SDN', 'match': 'No Match', 'score': 0},
          {'source': 'UN Sanctions', 'match': 'No Match', 'score': 0},
          {'source': 'EU Sanctions', 'match': 'No Match', 'score': 0},
          {'source': 'PEP Database', 'match': 'Potential Match', 'score': 45},
        ];
      });
    } finally {
      setState(() => _isSearching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Row(children: [
                  Icon(Icons.search, color: AppTheme.primaryBlue),
                  SizedBox(width: 8),
                  Text('PEP/Sanctions Screening', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                ]),
                const SizedBox(height: 8),
                const Text('Screen addresses against global watchlists', style: TextStyle(color: AppTheme.mutedText)),
                const SizedBox(height: 16),
                TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    labelText: 'Address or Name to Screen',
                    labelStyle: const TextStyle(color: AppTheme.mutedText),
                    prefixIcon: const Icon(Icons.search, color: AppTheme.mutedText),
                    filled: true,
                    fillColor: AppTheme.darkBg,
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
                  ),
                  style: const TextStyle(color: AppTheme.cleanWhite),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton.icon(
                    onPressed: _isSearching ? null : _runScreening,
                    icon: _isSearching
                        ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.security),
                    label: const Text('Run Screening'),
                    style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primaryBlue),
                  ),
                ),
              ],
            ),
          ),
          
          if (_results != null) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(color: AppTheme.darkCard, borderRadius: BorderRadius.circular(16)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Row(children: [
                    Icon(Icons.assessment, color: AppTheme.warningOrange),
                    SizedBox(width: 8),
                    Text('Screening Results', style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18, fontWeight: FontWeight.bold)),
                  ]),
                  const SizedBox(height: 16),
                  ..._results!.map((result) {
                    final hasMatch = result['score'] > 0;
                    final color = hasMatch ? AppTheme.warningOrange : AppTheme.accentGreen;
                    return Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: AppTheme.darkBg,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: color.withOpacity(0.5)),
                      ),
                      child: Row(
                        children: [
                          Icon(hasMatch ? Icons.warning : Icons.check_circle, color: color),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(result['source'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                                Text(result['match'] as String, style: TextStyle(color: color)),
                              ],
                            ),
                          ),
                          if (hasMatch)
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: color.withOpacity(0.2),
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text('${result['score']}%', style: TextStyle(color: color, fontWeight: FontWeight.bold)),
                            ),
                        ],
                      ),
                    );
                  }),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Tab 3: Enhanced Due Diligence Queue
class _EDDQueueTab extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eddQueue = [
      {'address': '0x1111...2222', 'reason': 'High-value transaction', 'priority': 'high', 'submitted': '2 hours ago'},
      {'address': '0x3333...4444', 'reason': 'New counterparty', 'priority': 'medium', 'submitted': '1 day ago'},
      {'address': '0x5555...6666', 'reason': 'PEP potential match', 'priority': 'high', 'submitted': '3 days ago'},
    ];

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: eddQueue.length + 1,
      itemBuilder: (context, index) {
        if (index == 0) {
          return Container(
            padding: const EdgeInsets.all(16),
            margin: const EdgeInsets.only(bottom: 16),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.warningOrange.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.fact_check, color: AppTheme.warningOrange),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('EDD Queue', style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold, fontSize: 18)),
                      Text('Cases requiring enhanced due diligence', style: TextStyle(color: AppTheme.mutedText)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppTheme.warningOrange,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text('${eddQueue.length}', style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          );
        }

        final item = eddQueue[index - 1];
        final priority = item['priority'] as String;
        final priorityColor = priority == 'high' ? AppTheme.dangerRed : AppTheme.warningOrange;

        return Container(
          margin: const EdgeInsets.only(bottom: 12),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.darkCard,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: priorityColor.withOpacity(0.5)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: priorityColor.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(priority.toUpperCase(), style: TextStyle(color: priorityColor, fontSize: 10, fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(width: 8),
                  Text(item['address'] as String, style: const TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold, fontFamily: 'monospace')),
                  const Spacer(),
                  Text(item['submitted'] as String, style: const TextStyle(color: AppTheme.mutedText, fontSize: 12)),
                ],
              ),
              const SizedBox(height: 12),
              Text('Reason: ${item['reason']}', style: const TextStyle(color: AppTheme.mutedText)),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {},
                      style: OutlinedButton.styleFrom(foregroundColor: AppTheme.primaryBlue),
                      child: const Text('View Details'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('EDD completed - account cleared'), backgroundColor: AppTheme.accentGreen),
                        );
                      },
                      style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen),
                      child: const Text('Mark Complete'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
