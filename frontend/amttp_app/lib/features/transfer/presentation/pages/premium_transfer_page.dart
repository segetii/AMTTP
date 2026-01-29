import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../shared/layout/premium_centered_page.dart';
import '../../../trust_check/data/trust_check_repository.dart';

/// Premium Transfer Page - Metamask/Revolut Style
class PremiumTransferPage extends ConsumerStatefulWidget {
  const PremiumTransferPage({super.key});

  @override
  ConsumerState<PremiumTransferPage> createState() => _PremiumTransferPageState();
}

class _PremiumTransferPageState extends ConsumerState<PremiumTransferPage> {
  final _recipientController = TextEditingController();
  final _amountController = TextEditingController();
  String _selectedToken = 'ETH';
  double _gasSpeed = 0.5; // 0 = slow, 0.5 = normal, 1 = fast
  bool _showTrustCheck = false;
  bool _isCheckingTrust = false;
  bool _hasTrustResult = false;
  String _trustBucket = '';
  int _trustScore = 0;
  List<String> _trustReasons = [];
  String? _trustError;
  final _trustRepo = TrustCheckRepository();

  final List<Map<String, dynamic>> _tokens = [
    {'symbol': 'ETH', 'name': 'Ethereum', 'balance': '3.245', 'usd': '10,234.56', 'icon': '◆', 'color': Color(0xFF627EEA)},
    {'symbol': 'USDC', 'name': 'USD Coin', 'balance': '1,847.00', 'usd': '1,847.00', 'icon': '◎', 'color': Color(0xFF2775CA)},
    {'symbol': 'USDT', 'name': 'Tether', 'balance': '765.32', 'usd': '765.07', 'icon': '₮', 'color': Color(0xFF26A17B)},
  ];

  final List<Map<String, String>> _recentRecipients = [
    {'name': 'John D.', 'address': '0x1234...5678', 'initials': 'JD'},
    {'name': 'Alice S.', 'address': '0xABCD...EFGH', 'initials': 'AS'},
    {'name': 'Mike K.', 'address': '0x9876...5432', 'initials': 'MK'},
  ];

  @override
  void dispose() {
    _recipientController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  Future<void> _checkTrust() async {
    final value = _recipientController.text.trim();
    if (value.isEmpty) return;

    setState(() {
      _showTrustCheck = true;
      _isCheckingTrust = true;
      _hasTrustResult = false;
      _trustError = null;
    });

    try {
      final result = await _trustRepo.checkAddress(value);
      setState(() {
        _isCheckingTrust = false;
        _hasTrustResult = true;
        _trustScore = result.score;
        _trustBucket = result.bucket;
        _trustReasons = result.reasons;
      });
    } catch (e) {
      setState(() {
        _isCheckingTrust = false;
        _hasTrustResult = false;
        _trustError = 'Unable to check trust right now. Please retry.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: PremiumCenteredPage(
        child: Column(
          children: [
            // Header
            _buildHeader(context),

            // Scrollable content
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Token selector
                    _buildTokenSelector(),
                    const SizedBox(height: 24),

                    // Recipient input
                    _buildRecipientInput(),
                    const SizedBox(height: 16),

                    // Recent recipients
                    _buildRecentRecipients(),
                    const SizedBox(height: 24),

                    // Amount input
                    _buildAmountInput(),
                    const SizedBox(height: 24),

                    // Trust check result
                    if (_showTrustCheck) ...[
                      _buildTrustState(),
                      const SizedBox(height: 24),
                    ],

                    // Gas settings
                    _buildGasSettings(),
                    const SizedBox(height: 24),

                    // Summary
                    _buildSummary(),
                    const SizedBox(height: 32),
                  ],
                ),
              ),
            ),

            // Bottom button
            _buildSendButton(),
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
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF2D2D44)),
              ),
              child: const Icon(Icons.arrow_back_rounded, color: Colors.white, size: 20),
            ),
          ),
          const Expanded(
            child: Text(
              'Send',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFF1A1A2E),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFF2D2D44)),
            ),
            child: const Icon(Icons.more_horiz_rounded, color: Colors.white, size: 20),
          ),
        ],
      ),
    );
  }

  Widget _buildTokenSelector() {
    final token = _tokens.firstWhere((t) => t['symbol'] == _selectedToken);
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Select Asset',
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        GestureDetector(
          onTap: () => _showTokenPicker(),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF12121A),
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: const Color(0xFF1E1E2E)),
            ),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: (token['color'] as Color).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Center(
                    child: Text(
                      token['icon'] as String,
                      style: TextStyle(
                        color: token['color'] as Color,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        '${token['name']} (${token['symbol']})',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Balance: ${token['balance']} ${token['symbol']} (\$${token['usd']})',
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.5),
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.keyboard_arrow_down_rounded, color: Color(0xFF64748B), size: 24),
              ],
            ),
          ),
        ),
      ],
    );
  }

  void _showTokenPicker() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
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
              margin: const EdgeInsets.only(top: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(20),
              child: Text(
                'Select Token',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            ..._tokens.map((token) => ListTile(
              onTap: () {
                setState(() => _selectedToken = token['symbol'] as String);
                Navigator.pop(context);
              },
              leading: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: (token['color'] as Color).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Center(
                  child: Text(
                    token['icon'] as String,
                    style: TextStyle(
                      color: token['color'] as Color,
                      fontSize: 20,
                    ),
                  ),
                ),
              ),
              title: Text(
                token['name'] as String,
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(
                '${token['balance']} ${token['symbol']}',
                style: TextStyle(color: Colors.white.withOpacity(0.5)),
              ),
              trailing: _selectedToken == token['symbol']
                  ? const Icon(Icons.check_circle, color: Color(0xFF22C55E))
                  : null,
            )),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }

  Widget _buildRecipientInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Recipient',
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFF12121A),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF1E1E2E)),
          ),
          child: Row(
            children: [
              const Icon(Icons.person_outline_rounded, color: Color(0xFF64748B), size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _recipientController,
                  style: const TextStyle(color: Colors.white, fontSize: 15),
                  decoration: InputDecoration(
                    hintText: 'Enter address or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
                    border: InputBorder.none,
                    contentPadding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ),
              GestureDetector(
                onTap: () async {
                  final data = await Clipboard.getData('text/plain');
                  if (data?.text != null) {
                    _recipientController.text = data!.text!;
                  }
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E2E),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    'Paste',
                    style: TextStyle(
                      color: Color(0xFF6366F1),
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () => _showScannerSheet(context),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E2E),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.qr_code_scanner_rounded, color: Color(0xFF64748B), size: 20),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 10),
        GestureDetector(
          onTap: _checkTrust,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              Icon(Icons.shield_rounded, size: 16, color: Colors.white.withOpacity(0.7)),
              const SizedBox(width: 6),
              Text(
                'Check trust',
                style: TextStyle(
                  color: const Color(0xFF6366F1),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildRecentRecipients() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Recent',
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 12,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              ..._recentRecipients.map((r) => GestureDetector(
                onTap: () {
                  _recipientController.text = r['address']!;
                  _checkTrust();
                },
                child: Container(
                  width: 72,
                  margin: const EdgeInsets.only(right: 12),
                  child: Column(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                          ),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Center(
                          child: Text(
                            r['initials']!,
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        r['name']!,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        r['address']!,
                        style: TextStyle(
                          color: Colors.white.withOpacity(0.4),
                          fontSize: 10,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
              )),
              GestureDetector(
                onTap: () => _showAddContactSheet(context),
                child: Container(
                  width: 72,
                  child: Column(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E1E2E),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFF2D2D44)),
                        ),
                        child: const Icon(Icons.add_rounded, color: Color(0xFF64748B), size: 24),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Add',
                        style: TextStyle(
                          color: Color(0xFF64748B),
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAmountInput() {
    final token = _tokens.firstWhere((t) => t['symbol'] == _selectedToken);
    
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Amount',
          style: TextStyle(
            color: Colors.white.withOpacity(0.6),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFF12121A),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF1E1E2E)),
          ),
          child: Column(
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _amountController,
                      keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 42,
                        fontWeight: FontWeight.bold,
                      ),
                      decoration: InputDecoration(
                        hintText: '0',
                        hintStyle: TextStyle(color: Colors.white.withOpacity(0.2)),
                        border: InputBorder.none,
                      ),
                    ),
                  ),
                ],
              ),
              Text(
                _selectedToken,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.5),
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '≈ \$${_calculateUsdValue()}',
                style: TextStyle(
                  color: Colors.white.withOpacity(0.4),
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: ['25%', '50%', '75%', 'MAX'].map((pct) {
                  return GestureDetector(
                    onTap: () => _setPercentage(pct),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1E1E2E),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        pct,
                        style: const TextStyle(
                          color: Color(0xFF94A3B8),
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _calculateUsdValue() {
    final amount = double.tryParse(_amountController.text) ?? 0;
    if (_selectedToken == 'ETH') return (amount * 3154.56).toStringAsFixed(2);
    return amount.toStringAsFixed(2);
  }

  void _setPercentage(String pct) {
    final token = _tokens.firstWhere((t) => t['symbol'] == _selectedToken);
    final balance = double.parse((token['balance'] as String).replaceAll(',', ''));
    double amount;
    switch (pct) {
      case '25%': amount = balance * 0.25; break;
      case '50%': amount = balance * 0.50; break;
      case '75%': amount = balance * 0.75; break;
      case 'MAX': amount = balance; break;
      default: amount = 0;
    }
    _amountController.text = amount.toStringAsFixed(4);
    setState(() {});
  }

  Widget _buildTrustState() {
    if (_isCheckingTrust) {
      return _buildTrustLoading();
    }
    if (_trustError != null) {
      return _buildTrustError();
    }
    if (_hasTrustResult) {
      return _buildTrustCheckResult();
    }
    return const SizedBox.shrink();
  }

  Widget _buildTrustLoading() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Row(
        children: const [
          SizedBox(
            width: 26,
            height: 26,
            child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation(Color(0xFF6366F1))),
          ),
          SizedBox(width: 12),
          Text('Running trust checks...', style: TextStyle(color: Colors.white)),
        ],
      ),
    );
  }

  Widget _buildTrustError() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFEF4444).withOpacity(0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: Color(0xFFEF4444)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _trustError ?? 'Trust check failed',
              style: const TextStyle(color: Colors.white),
            ),
          ),
          TextButton(
            onPressed: _checkTrust,
            child: const Text('Retry', style: TextStyle(color: Color(0xFFF59E0B))),
          ),
        ],
      ),
    );
  }

  Widget _buildTrustCheckResult() {
    final bucket = _trustBucket.toUpperCase();
    Color bucketColor;
    IconData bucketIcon;
    String label;
    if (bucket == 'TRUSTED') {
      bucketColor = const Color(0xFF22C55E);
      bucketIcon = Icons.verified_rounded;
      label = 'Trusted';
    } else if (bucket == 'CAUTION') {
      bucketColor = const Color(0xFFF59E0B);
      bucketIcon = Icons.warning_rounded;
      label = 'Caution';
    } else {
      bucketColor = const Color(0xFFEF4444);
      bucketIcon = Icons.dangerous_rounded;
      label = 'High Risk';
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: bucketColor.withOpacity(0.08),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: bucketColor.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: bucketColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(bucketIcon, color: bucketColor, size: 24),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '$label recipient',
                      style: TextStyle(
                        color: bucketColor,
                        fontSize: 15,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Trust Score: $_trustScore/100 • Bucket: $bucket',
                      style: TextStyle(
                        color: Colors.white.withOpacity(0.7),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () => context.push('/trust-check?address=${_recipientController.text}'),
                child: const Text('Details', style: TextStyle(color: Color(0xFF818CF8))),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (_trustReasons.isNotEmpty)
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: _trustReasons.map((reason) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    Icon(Icons.fiber_manual_record, size: 8, color: bucketColor),
                    const SizedBox(width: 6),
                    Expanded(child: Text(reason, style: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 12))),
                  ],
                ),
              )).toList(),
            ),
          const SizedBox(height: 12),
          _buildTrustActions(bucketColor),
        ],
      ),
    );
  }

  Widget _buildTrustActions(Color bucketColor) {
    final risky = _trustBucket.toUpperCase() == 'HIGH RISK';

    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: bucketColor.withOpacity(0.15),
                  foregroundColor: bucketColor,
                  side: BorderSide(color: bucketColor.withOpacity(0.4)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Escrow/Manual review requested')),
                  );
                },
                icon: const Icon(Icons.shield_moon_rounded),
                label: const Text('Escrow / Manual review'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF22C55E),
                  side: const BorderSide(color: Color(0xFF22C55E)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Address added to whitelist (mock)')),
                  );
                },
                icon: const Icon(Icons.check_circle_outline_rounded),
                label: const Text('Whitelist'),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: TextButton.icon(
            onPressed: () async {
              final proceed = await _confirmSendAnyway();
              if (proceed) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(risky ? 'Proceeding despite risk' : 'Proceeding to send'),
                    backgroundColor: risky ? const Color(0xFFEF4444) : const Color(0xFF6366F1),
                  ),
                );
              }
            },
            icon: Icon(Icons.send_rounded, color: risky ? const Color(0xFFEF4444) : const Color(0xFF818CF8)),
            label: Text(
              risky ? 'Send anyway (confirm)' : 'Proceed to send',
              style: TextStyle(color: risky ? const Color(0xFFEF4444) : const Color(0xFF818CF8), fontWeight: FontWeight.w700),
            ),
          ),
        ),
      ],
    );
  }

  Future<bool> _confirmSendAnyway() async {
    return await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: const Color(0xFF12121A),
            title: const Text('Proceed with risk?', style: TextStyle(color: Colors.white)),
            content: const Text(
              'This recipient has risk signals. Are you sure you want to continue?',
              style: TextStyle(color: Colors.white70),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Cancel', style: TextStyle(color: Color(0xFF94A3B8))),
              ),
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('Proceed anyway', style: TextStyle(color: Color(0xFFEF4444), fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ) ??
        false;
  }

  Widget _buildGasSettings() {
    String speedLabel;
    String speedTime;
    if (_gasSpeed < 0.33) {
      speedLabel = 'Slow';
      speedTime = '~5 min';
    } else if (_gasSpeed < 0.66) {
      speedLabel = 'Normal';
      speedTime = '~30 sec';
    } else {
      speedLabel = 'Fast';
      speedTime = '~15 sec';
    }
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'Network Fee',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E1E2E),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Text(
                      '~\$2.45',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.edit_rounded, color: Color(0xFF64748B), size: 14),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              const Icon(Icons.flash_on_rounded, color: Color(0xFFF59E0B), size: 18),
              const SizedBox(width: 6),
              Text(
                '$speedLabel ($speedTime)',
                style: const TextStyle(
                  color: Color(0xFF94A3B8),
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SliderTheme(
            data: SliderThemeData(
              activeTrackColor: const Color(0xFF6366F1),
              inactiveTrackColor: const Color(0xFF1E1E2E),
              thumbColor: const Color(0xFF6366F1),
              overlayColor: const Color(0xFF6366F1).withOpacity(0.2),
              trackHeight: 6,
            ),
            child: Slider(
              value: _gasSpeed,
              onChanged: (v) => setState(() => _gasSpeed = v),
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Slow', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 11)),
              Text('Normal', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 11)),
              Text('Fast', style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 11)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSummary() {
    final amount = _amountController.text.isNotEmpty ? _amountController.text : '0';
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Summary',
            style: TextStyle(
              color: Colors.white,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 16),
          _buildSummaryRow('Amount', '$amount $_selectedToken'),
          const SizedBox(height: 8),
          _buildSummaryRow('Network fee', '~\$2.45'),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Divider(color: Color(0xFF1E1E2E)),
          ),
          _buildSummaryRow('Total', '$amount $_selectedToken + gas', isBold: true),
          _buildSummaryRow('', '≈ \$${_calculateUsdValue()}', isSubtle: true),
        ],
      ),
    );
  }

  Widget _buildSummaryRow(String label, String value, {bool isBold = false, bool isSubtle = false}) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 13,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: isSubtle ? Colors.white.withOpacity(0.4) : Colors.white,
            fontSize: isBold ? 15 : 13,
            fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ],
    );
  }

  Widget _buildSendButton() {
    final isValid = _recipientController.text.isNotEmpty && 
                    _amountController.text.isNotEmpty &&
                    double.tryParse(_amountController.text) != null &&
                    double.parse(_amountController.text) > 0;
    
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF0A0A0F),
        border: Border(
          top: BorderSide(color: const Color(0xFF1E1E2E)),
        ),
      ),
      child: GestureDetector(
        onTap: isValid ? () => _confirmSend() : null,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            gradient: isValid
                ? const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)])
                : null,
            color: isValid ? null : const Color(0xFF1E1E2E),
            borderRadius: BorderRadius.circular(16),
            boxShadow: isValid
                ? [
                    BoxShadow(
                      color: const Color(0xFF6366F1).withOpacity(0.4),
                      blurRadius: 20,
                      offset: const Offset(0, 8),
                    ),
                  ]
                : null,
          ),
          child: Center(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Review & Send',
                  style: TextStyle(
                    color: isValid ? Colors.white : Colors.white.withOpacity(0.3),
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.arrow_forward_rounded,
                  color: isValid ? Colors.white : Colors.white.withOpacity(0.3),
                  size: 20,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _confirmSend() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.6,
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(top: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(20),
              child: Text(
                'Confirm Transaction',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Column(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0A0A0F),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Column(
                        children: [
                          Text(
                            '${_amountController.text} $_selectedToken',
                            style: const TextStyle(
                              color: Colors.white,
                              fontSize: 32,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '≈ \$${_calculateUsdValue()}',
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.5),
                              fontSize: 16,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),
                    _buildConfirmRow('To', _recipientController.text),
                    _buildConfirmRow('Network', 'Ethereum Mainnet'),
                    _buildConfirmRow('Fee', '~\$2.45'),
                    const Spacer(),
                    GestureDetector(
                      onTap: () {
                        Navigator.pop(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Transaction submitted!'),
                            backgroundColor: Color(0xFF22C55E),
                          ),
                        );
                        context.go('/');
                      },
                      child: Container(
                        height: 56,
                        margin: const EdgeInsets.only(bottom: 20),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                          ),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: const Center(
                          child: Text(
                            'Confirm & Send',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConfirmRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
          ),
          Text(
            value,
            style: const TextStyle(color: Colors.white, fontSize: 14),
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
  
  void _showScannerSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Container(
        height: MediaQuery.of(context).size.height * 0.6,
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF374151),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Scan Address',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Scan a QR code to fill recipient address',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
            ),
            const SizedBox(height: 32),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF0A0A0F),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: const Color(0xFF2D2D44)),
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.qr_code_scanner_rounded, color: Colors.white.withOpacity(0.3), size: 80),
                      const SizedBox(height: 16),
                      Text(
                        'Camera permission required',
                        style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 14),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 20),
          ],
        ),
      ),
    );
  }
  
  void _showAddContactSheet(BuildContext context) {
    final nameController = TextEditingController();
    final addressController = TextEditingController();
    
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: const BoxDecoration(
            color: Color(0xFF12121A),
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFF374151),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              const Text(
                'Add Contact',
                style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),
              const Text('Name', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A2E),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF2D2D44)),
                ),
                child: TextField(
                  controller: nameController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: 'Contact name',
                    hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
                    border: InputBorder.none,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text('Address', style: TextStyle(color: Color(0xFF94A3B8), fontSize: 13)),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A2E),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFF2D2D44)),
                ),
                child: TextField(
                  controller: addressController,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    hintText: '0x... or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withOpacity(0.3)),
                    border: InputBorder.none,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              GestureDetector(
                onTap: () {
                  Navigator.pop(context);
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Contact saved!'),
                      backgroundColor: Color(0xFF22C55E),
                    ),
                  );
                },
                child: Container(
                  height: 54,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)]),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Center(
                    child: Text(
                      'Save Contact',
                      style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        ),
      ),
    );
  }
}
