import 'package:flutter/material.dart';
import '../../../../core/theme/app_theme.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../shared/layout/premium_centered_page.dart';
import '../../../trust_check/data/trust_check_repository.dart';
import '../../../../services/swap_service.dart';
import '../../../../core/web3/wallet_provider.dart';

/// Premium Transfer Page - Metamask/Revolut Style
/// Now connected to backend atomic swap logic via SwapService
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
  final _swapService = SwapService.instance;
  
  // Swap state
  bool _isProcessingSwap = false;
  SwapRiskResult? _riskResult;

  final List<Map<String, dynamic>> _tokens = [
    {'symbol': 'ETH', 'name': 'Ethereum', 'balance': '3.245', 'usd': '10,234.56', 'icon': '◆', 'color': AppTheme.brandETH},
    {'symbol': 'USDC', 'name': 'USD Coin', 'balance': '1,847.00', 'usd': '1,847.00', 'icon': '◎', 'color': AppTheme.brandUSDC},
    {'symbol': 'USDT', 'name': 'Tether', 'balance': '765.32', 'usd': '765.07', 'icon': '₮', 'color': AppTheme.brandUSDT},
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
                color: AppTheme.tokenCardElevated,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppTheme.tokenBorderStrong),
              ),
              child: const Icon(Icons.arrow_back_rounded, color: AppTheme.tokenText, size: 20),
            ),
          ),
          const Expanded(
            child: Text(
              'Send',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppTheme.tokenText,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: AppTheme.tokenCardElevated,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.tokenBorderStrong),
            ),
            child: const Icon(Icons.more_horiz_rounded, color: AppTheme.tokenText, size: 20),
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
            color: Colors.white.withAlpha(153),
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
              color: AppTheme.tokenSurface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppTheme.tokenBorderSubtle),
            ),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: (token['color'] as Color).withAlpha(38),
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
                          color: AppTheme.tokenText,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Balance: ${token['balance']} ${token['symbol']} (\$${token['usd']})',
                        style: TextStyle(
                          color: Colors.white.withAlpha(128),
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.keyboard_arrow_down_rounded, color: AppTheme.slate500, size: 24),
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
          color: AppTheme.tokenSurface,
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
                color: AppTheme.gray700,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(20),
              child: Text(
                'Select Token',
                style: TextStyle(
                  color: AppTheme.tokenText,
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
                  color: (token['color'] as Color).withAlpha(38),
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
                style: const TextStyle(color: AppTheme.tokenText, fontWeight: FontWeight.w600),
              ),
              subtitle: Text(
                '${token['balance']} ${token['symbol']}',
                style: TextStyle(color: Colors.white.withAlpha(128)),
              ),
              trailing: _selectedToken == token['symbol']
                  ? const Icon(Icons.check_circle, color: AppTheme.tokenSuccess)
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
            color: Colors.white.withAlpha(153),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(
            color: AppTheme.tokenSurface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppTheme.tokenBorderSubtle),
          ),
          child: Row(
            children: [
              Icon(Icons.person_outline_rounded, color: AppTheme.slate500, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _recipientController,
                  style: const TextStyle(color: AppTheme.tokenText, fontSize: 15),
                  decoration: InputDecoration(
                    hintText: 'Enter address or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withAlpha(77)),
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
                    color: AppTheme.tokenBorderSubtle,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    'Paste',
                    style: TextStyle(
                      color: AppTheme.tokenPrimary,
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
                    color: AppTheme.tokenBorderSubtle,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.qr_code_scanner_rounded, color: AppTheme.slate500, size: 20),
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
              Icon(Icons.shield_rounded, size: 16, color: Colors.white.withAlpha(179)),
              const SizedBox(width: 6),
              Text(
                'Check trust',
                style: TextStyle(
                  color: AppTheme.tokenPrimary,
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
            color: Colors.white.withAlpha(128),
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
                            colors: [AppTheme.tokenPrimary, AppTheme.tokenPrimarySoft],
                          ),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Center(
                          child: Text(
                            r['initials']!,
                            style: const TextStyle(
                              color: AppTheme.tokenText,
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
                          color: AppTheme.tokenText,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        r['address']!,
                        style: TextStyle(
                          color: Colors.white.withAlpha(102),
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
                child: SizedBox(
                  width: 72,
                  child: Column(
                    children: [
                      Container(
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          color: AppTheme.tokenBorderSubtle,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: AppTheme.tokenBorderStrong),
                        ),
                        child: const Icon(Icons.add_rounded, color: AppTheme.slate500, size: 24),
                      ),
                      const SizedBox(height: 8),
                      const Text(
                        'Add',
                        style: TextStyle(
                          color: AppTheme.slate500,
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
            color: Colors.white.withAlpha(153),
            fontSize: 13,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: AppTheme.tokenSurface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: AppTheme.tokenBorderSubtle),
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
                        color: AppTheme.tokenText,
                        fontSize: 42,
                        fontWeight: FontWeight.bold,
                      ),
                      decoration: InputDecoration(
                        hintText: '0',
                        hintStyle: TextStyle(color: Colors.white.withAlpha(51)),
                        border: InputBorder.none,
                      ),
                    ),
                  ),
                ],
              ),
              Text(
                _selectedToken,
                style: TextStyle(
                  color: Colors.white.withAlpha(128),
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '≈ \$${_calculateUsdValue()}',
                style: TextStyle(
                  color: Colors.white.withAlpha(102),
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
                        color: AppTheme.tokenBorderSubtle,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        pct,
                        style: const TextStyle(
                          color: AppTheme.slate400,
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
    if (_selectedToken == 'ETH') return (amount * AppTheme.ethUsdPrice).toStringAsFixed(2);
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
        color: AppTheme.tokenSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.tokenBorderSubtle),
      ),
      child: Row(
        children: const [
          SizedBox(
            width: 26,
            height: 26,
            child: CircularProgressIndicator(strokeWidth: 2.5, valueColor: AlwaysStoppedAnimation(AppTheme.tokenPrimary)),
          ),
          SizedBox(width: 12),
          Text('Running trust checks...', style: TextStyle(color: AppTheme.tokenText)),
        ],
      ),
    );
  }

  Widget _buildTrustError() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.tokenCardElevated,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.tokenDanger.withAlpha(102)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline_rounded, color: AppTheme.tokenDanger),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _trustError ?? 'Trust check failed',
              style: const TextStyle(color: AppTheme.tokenText),
            ),
          ),
          TextButton(
            onPressed: _checkTrust,
            child: const Text('Retry', style: TextStyle(color: AppTheme.tokenWarning)),
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
      bucketColor = AppTheme.tokenSuccess;
      bucketIcon = Icons.verified_rounded;
      label = 'Trusted';
    } else if (bucket == 'CAUTION') {
      bucketColor = AppTheme.tokenWarning;
      bucketIcon = Icons.warning_rounded;
      label = 'Caution';
    } else {
      bucketColor = AppTheme.tokenDanger;
      bucketIcon = Icons.dangerous_rounded;
      label = 'High Risk';
    }

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: bucketColor.withAlpha(20),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: bucketColor.withAlpha(77),
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
                  color: bucketColor.withAlpha(38),
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
                        color: Colors.white.withAlpha(179),
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton(
                onPressed: () => context.push('/trust-check?address=${_recipientController.text}'),
                child: Text('Details', style: TextStyle(color: AppTheme.tokenPrimaryLight)),
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
                    Expanded(child: Text(reason, style: TextStyle(color: Colors.white.withAlpha(179), fontSize: 12))),
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
                  backgroundColor: bucketColor.withAlpha(38),
                  foregroundColor: bucketColor,
                  side: BorderSide(color: bucketColor.withAlpha(102)),
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
                  foregroundColor: AppTheme.tokenSuccess,
                  side: const BorderSide(color: AppTheme.tokenSuccess),
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
                    backgroundColor: risky ? AppTheme.tokenDanger : AppTheme.tokenPrimary,
                  ),
                );
              }
            },
            icon: Icon(Icons.send_rounded, color: risky ? AppTheme.tokenDanger : AppTheme.tokenPrimaryLight),
            label: Text(
              risky ? 'Send anyway (confirm)' : 'Proceed to send',
              style: TextStyle(color: risky ? AppTheme.tokenDanger : AppTheme.tokenPrimaryLight, fontWeight: FontWeight.w700),
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
            backgroundColor: AppTheme.tokenSurface,
            title: Text('Proceed with risk?', style: TextStyle(color: AppTheme.tokenText)),
            content: Text(
              'This recipient has risk signals. Are you sure you want to continue?',
              style: TextStyle(color: AppTheme.tokenText.withAlpha(179)),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(false),
                child: const Text('Cancel', style: TextStyle(color: AppTheme.slate400)),
              ),
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(true),
                child: const Text('Proceed anyway', style: TextStyle(color: AppTheme.tokenDanger, fontWeight: FontWeight.bold)),
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
        color: AppTheme.tokenSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.tokenBorderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Network Fee',
                style: TextStyle(
                  color: AppTheme.tokenText,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: AppTheme.tokenBorderSubtle,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Text(
                      '~\$2.45',
                      style: const TextStyle(
                        color: AppTheme.tokenText,
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Icon(Icons.edit_rounded, color: AppTheme.slate500, size: 14),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(Icons.flash_on_rounded, color: AppTheme.tokenWarning, size: 18),
              const SizedBox(width: 6),
              Text(
                '$speedLabel ($speedTime)',
                style: const TextStyle(
                  color: AppTheme.slate400,
                  fontSize: 13,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SliderTheme(
            data: SliderThemeData(
              activeTrackColor: AppTheme.tokenPrimary,
              inactiveTrackColor: AppTheme.tokenBorderSubtle,
              thumbColor: AppTheme.tokenPrimary,
              overlayColor: AppTheme.tokenPrimary.withAlpha(51),
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
              Text('Slow', style: TextStyle(color: Colors.white.withAlpha(102), fontSize: 11)),
              Text('Normal', style: TextStyle(color: Colors.white.withAlpha(102), fontSize: 11)),
              Text('Fast', style: TextStyle(color: Colors.white.withAlpha(102), fontSize: 11)),
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
        color: AppTheme.tokenSurface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppTheme.tokenBorderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Summary',
            style: TextStyle(
              color: AppTheme.tokenText,
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
            child: Divider(color: AppTheme.tokenBorderSubtle),
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
            color: Colors.white.withAlpha(128),
            fontSize: 13,
          ),
        ),
        Text(
          value,
          style: TextStyle(
            color: isSubtle ? Colors.white.withAlpha(102) : AppTheme.tokenText,
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
        color: AppTheme.tokenBackground,
        border: Border(
          top: BorderSide(color: AppTheme.tokenBorderSubtle),
        ),
      ),
      child: GestureDetector(
        onTap: isValid ? () => _confirmSend() : null,
        child: Container(
          height: 56,
          decoration: BoxDecoration(
            gradient: isValid
                ? const LinearGradient(colors: [AppTheme.tokenPrimary, AppTheme.tokenPrimarySoft])
                : null,
            color: isValid ? null : AppTheme.tokenBorderSubtle,
            borderRadius: BorderRadius.circular(16),
            boxShadow: isValid
                ? [
                    BoxShadow(
                      color: AppTheme.tokenPrimary.withAlpha(102),
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
                    color: isValid ? AppTheme.tokenText : Colors.white.withAlpha(77),
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.arrow_forward_rounded,
                  color: isValid ? AppTheme.tokenText : Colors.white.withAlpha(77),
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
    final walletState = ref.read(walletProvider);
    
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => Container(
          height: MediaQuery.of(context).size.height * 0.7,
          decoration: const BoxDecoration(
            color: AppTheme.tokenSurface,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          ),
          child: Column(
            children: [
              Container(
                width: 40,
                height: 4,
                margin: const EdgeInsets.only(top: 12),
                decoration: BoxDecoration(
                  color: AppTheme.gray700,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Padding(
                padding: const EdgeInsets.all(20),
                child: Text(
                  _isProcessingSwap ? 'Processing...' : 'Confirm Transaction',
                  style: const TextStyle(
                    color: AppTheme.tokenText,
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
                          color: AppTheme.tokenBackground,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          children: [
                            Text(
                              '${_amountController.text} $_selectedToken',
                              style: const TextStyle(
                                color: AppTheme.tokenText,
                                fontSize: 32,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              '≈ \$${_calculateUsdValue()}',
                              style: TextStyle(
                                color: Colors.white.withAlpha(128),
                                fontSize: 16,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 20),
                      _buildConfirmRow('To', _recipientController.text),
                      _buildConfirmRow('Network', 'Sepolia Testnet'),
                      _buildConfirmRow('Fee', '~\$0.50'),
                      
                      // Risk Assessment Section
                      if (_riskResult != null) ...[
                        const SizedBox(height: 16),
                        Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: _riskResult!.isHighRisk 
                                ? AppTheme.tokenDangerStrong.withAlpha(26)
                                : _riskResult!.isMediumRisk
                                    ? AppTheme.tokenWarning.withAlpha(26)
                                    : AppTheme.tokenSuccess.withAlpha(26),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: _riskResult!.isHighRisk 
                                  ? AppTheme.tokenDangerStrong.withAlpha(77)
                                  : _riskResult!.isMediumRisk
                                      ? AppTheme.tokenWarning.withAlpha(77)
                                      : AppTheme.tokenSuccess.withAlpha(77),
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _riskResult!.isHighRisk 
                                    ? Icons.warning_rounded
                                    : _riskResult!.isMediumRisk
                                        ? Icons.info_rounded
                                        : Icons.check_circle_rounded,
                                color: _riskResult!.isHighRisk 
                                    ? AppTheme.tokenDangerStrong
                                    : _riskResult!.isMediumRisk
                                        ? AppTheme.tokenWarning
                                        : AppTheme.tokenSuccess,
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'Risk Score: ${(_riskResult!.riskScore * 100).toStringAsFixed(0)}%',
                                      style: const TextStyle(
                                        color: AppTheme.tokenText,
                                        fontWeight: FontWeight.w600,
                                      ),
                                    ),
                                    if (_riskResult!.reasons.isNotEmpty)
                                      Text(
                                        _riskResult!.reasons.first,
                                        style: TextStyle(
                                          color: Colors.white.withAlpha(179),
                                          fontSize: 12,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                      
                      const Spacer(),
                      
                      // Confirm Button
                      GestureDetector(
                        onTap: _isProcessingSwap ? null : () async {
                          if (!walletState.isConnected) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Please connect your wallet first'),
                                backgroundColor: AppTheme.tokenDangerStrong,
                              ),
                            );
                            return;
                          }
                          
                          setModalState(() {
                            _isProcessingSwap = true;
                          });
                          setState(() {
                            _isProcessingSwap = true;
                          });
                          
                          try {
                            final amount = double.parse(_amountController.text);
                            final toAddress = _recipientController.text.trim();
                            
                            // Execute the transfer via swap service
                            final result = await _swapService.executeTransfer(
                              toAddress: toAddress,
                              amountEth: amount,
                            );
                            
                            Navigator.pop(context);
                            
                            if (result.success) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text('Transaction submitted! Hash: ${result.transactionHash?.substring(0, 10)}...'),
                                  backgroundColor: AppTheme.tokenSuccess,
                                  duration: const Duration(seconds: 5),
                                ),
                              );
                              context.go('/history');
                            } else {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text(result.message),
                                  backgroundColor: result.status == SwapStatus.pendingApproval
                                      ? AppTheme.tokenWarning
                                      : AppTheme.tokenDangerStrong,
                                ),
                              );
                            }
                          } catch (e) {
                            Navigator.pop(context);
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('Transaction failed: $e'),
                                backgroundColor: AppTheme.tokenDangerStrong,
                              ),
                            );
                          } finally {
                            if (mounted) {
                              setState(() {
                                _isProcessingSwap = false;
                              });
                            }
                          }
                        },
                        child: Container(
                          height: 56,
                          margin: const EdgeInsets.only(bottom: 20),
                          decoration: BoxDecoration(
                            gradient: _isProcessingSwap 
                                ? null
                                : const LinearGradient(
                                    colors: [AppTheme.tokenPrimary, AppTheme.tokenPrimarySoft],
                                  ),
                            color: _isProcessingSwap ? AppTheme.gray700 : null,
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Center(
                            child: _isProcessingSwap
                                ? const SizedBox(
                                    width: 24,
                                    height: 24,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                      valueColor: AlwaysStoppedAnimation<Color>(AppTheme.tokenText),
                                    ),
                                  )
                                : const Text(
                                    'Confirm & Send',
                                    style: TextStyle(
                                      color: AppTheme.tokenText,
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
            style: TextStyle(color: Colors.white.withAlpha(128), fontSize: 14),
          ),
          Text(
            value,
            style: const TextStyle(color: AppTheme.tokenText, fontSize: 14),
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
          color: AppTheme.tokenSurface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: [
            Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppTheme.gray700,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 20),
            Text(
              'Scan Address',
              style: TextStyle(color: AppTheme.tokenText, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Scan a QR code to fill recipient address',
              style: TextStyle(color: Colors.white.withAlpha(128), fontSize: 14),
            ),
            const SizedBox(height: 32),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: AppTheme.tokenBackground,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: AppTheme.tokenBorderStrong),
                ),
                child: Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.qr_code_scanner_rounded, color: Colors.white.withAlpha(77), size: 80),
                      const SizedBox(height: 16),
                      Text(
                        'Camera permission required',
                        style: TextStyle(color: Colors.white.withAlpha(128), fontSize: 14),
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
            color: AppTheme.tokenSurface,
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
                    color: AppTheme.gray700,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'Add Contact',
                style: TextStyle(color: AppTheme.tokenText, fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 24),
              Text('Name', style: TextStyle(color: AppTheme.slate400, fontSize: 13)),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: AppTheme.tokenCardElevated,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.tokenBorderStrong),
                ),
                child: TextField(
                  controller: nameController,
                  style: const TextStyle(color: AppTheme.tokenText),
                  decoration: InputDecoration(
                    hintText: 'Contact name',
                    hintStyle: TextStyle(color: Colors.white.withAlpha(77)),
                    border: InputBorder.none,
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text('Address', style: TextStyle(color: AppTheme.slate400, fontSize: 13)),
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                decoration: BoxDecoration(
                  color: AppTheme.tokenCardElevated,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: AppTheme.tokenBorderStrong),
                ),
                child: TextField(
                  controller: addressController,
                  style: const TextStyle(color: AppTheme.tokenText),
                  decoration: InputDecoration(
                    hintText: '0x... or ENS name',
                    hintStyle: TextStyle(color: Colors.white.withAlpha(77)),
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
                      backgroundColor: AppTheme.tokenSuccess,
                    ),
                  );
                },
                child: Container(
                  height: 54,
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(colors: [AppTheme.tokenPrimary, AppTheme.tokenPrimarySoft]),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Center(
                    child: Text(
                      'Save Contact',
                      style: TextStyle(color: AppTheme.tokenText, fontSize: 16, fontWeight: FontWeight.w600),
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
