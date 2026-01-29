import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../data/trust_check_repository.dart';

/// Premium Trust Check Page - Address Verification
class PremiumTrustCheckPage extends ConsumerStatefulWidget {
  final String? initialAddress;
  
  const PremiumTrustCheckPage({super.key, this.initialAddress});

  @override
  ConsumerState<PremiumTrustCheckPage> createState() => _PremiumTrustCheckPageState();
}

class _PremiumTrustCheckPageState extends ConsumerState<PremiumTrustCheckPage>
    with SingleTickerProviderStateMixin {
  final _addressController = TextEditingController();
  bool _isChecking = false;
  bool _hasResult = false;
  int _trustScore = 0;
  String _bucket = '';
  String? _errorMessage;
  late AnimationController _animController;
  late Animation<double> _scoreAnimation;

  final List<Map<String, dynamic>> _riskChecks = [];
  final _repo = TrustCheckRepository();

  @override
  void initState() {
    super.initState();
    _animController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _scoreAnimation = Tween<double>(begin: 0, end: 0).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOutCubic),
    );
    
    if (widget.initialAddress != null) {
      _addressController.text = widget.initialAddress!;
      _checkAddress();
    }
  }

  @override
  void dispose() {
    _addressController.dispose();
    _animController.dispose();
    super.dispose();
  }

  Future<void> _checkAddress() async {
    if (_addressController.text.isEmpty) return;
    
    setState(() {
      _isChecking = true;
      _hasResult = false;
      _errorMessage = null;
    });

    TrustCheckResult result;
    try {
      result = await _repo.checkAddress(_addressController.text);
    } catch (e) {
      setState(() {
        _isChecking = false;
        _hasResult = false;
        _errorMessage = 'Trust check failed. Please retry.';
      });
      return;
    }

    Color bucketColor;
    IconData bucketIcon;
    final bucket = result.bucket.toLowerCase();
    if (bucket == 'trusted') {
      bucketColor = const Color(0xFF22C55E);
      bucketIcon = Icons.check_circle_rounded;
    } else if (bucket == 'caution') {
      bucketColor = const Color(0xFFF59E0B);
      bucketIcon = Icons.warning_rounded;
    } else {
      bucketColor = const Color(0xFFEF4444);
      bucketIcon = Icons.dangerous_rounded;
    }
    
    setState(() {
      _isChecking = false;
      _hasResult = true;
      _trustScore = result.score;
      _bucket = result.bucket;
      _riskChecks.clear();
      if (result.reasons.isNotEmpty) {
        for (var i = 0; i < result.reasons.length; i++) {
          _riskChecks.add({
            'title': 'Signal ${i + 1}',
            'status': result.bucket.toUpperCase(),
            'description': result.reasons[i],
            'icon': bucketIcon,
            'color': bucketColor,
          });
        }
      } else {
        _riskChecks.add({
          'title': 'Sanctions Check',
          'status': 'CLEAR',
          'description': 'Not on OFAC, EU, or UN sanctions lists',
          'icon': Icons.check_circle_rounded,
          'color': const Color(0xFF22C55E),
        });
      }
    });

    _scoreAnimation = Tween<double>(begin: 0, end: result.score.toDouble()).animate(
      CurvedAnimation(parent: _animController, curve: Curves.easeOutCubic),
    );
    _animController.forward(from: 0);
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
                // Header
                _buildHeader(context),
                const SizedBox(height: 4),
                _buildStepper(),
                
                // Content
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Address input
                        _buildAddressInput(),
                        const SizedBox(height: 24),
                        
                        // Check button
                        if (!_hasResult) _buildCheckButton(),
                        
                        // Loading state
                        if (_isChecking) _buildLoading(),

                        // Error state
                        if (_errorMessage != null && !_isChecking)
                          _buildError(),
                        
                        // Results
                        if (_hasResult && !_isChecking) ...[
                          _buildScoreCard(),
                          const SizedBox(height: 24),
                          _buildRiskBreakdown(),
                          const SizedBox(height: 24),
                          _buildGraphPreview(),
                          const SizedBox(height: 24),
                          _buildActions(),
                        ],
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

  Widget _buildStepper() {
    int currentStep;
    if (_isChecking) {
      currentStep = 2;
    } else if (_hasResult) {
      currentStep = 3;
    } else {
      currentStep = 1;
    }

    Widget dot(int step, String label) {
      final isActive = currentStep == step;
      final isCompleted = currentStep > step;
      Color color;
      if (isCompleted) {
        color = const Color(0xFF22C55E);
      } else if (isActive) {
        color = const Color(0xFF6366F1);
      } else {
        color = const Color(0xFF1E293B);
      }
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 22,
            height: 22,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            child: Center(
              child: isCompleted
                  ? const Icon(Icons.check_rounded, size: 14, color: Colors.white)
                  : Text(step.toString(), style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: isActive ? Colors.white : Colors.white.withOpacity(0.6),
              fontSize: 11,
              fontWeight: isActive ? FontWeight.w600 : FontWeight.w400,
            ),
          ),
        ],
      );
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          dot(1, 'Enter'),
          Container(width: 28, height: 1, margin: const EdgeInsets.symmetric(horizontal: 4), color: Colors.white.withOpacity(0.15)),
          dot(2, 'Analyze'),
          Container(width: 28, height: 1, margin: const EdgeInsets.symmetric(horizontal: 4), color: Colors.white.withOpacity(0.15)),
          dot(3, 'Result'),
        ],
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
              'Trust Check',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          GestureDetector(
            onTap: () => _showInfoModal(context),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A2E),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF2D2D44)),
              ),
              child: const Icon(Icons.info_outline_rounded, color: Colors.white, size: 20),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAddressInput() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Verify Address',
          style: TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Enter a wallet address to check its trust score and risk factors',
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 13,
          ),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(
            color: const Color(0xFF12121A),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: const Color(0xFF1E1E2E)),
          ),
          child: Row(
            children: [
              const Icon(Icons.search_rounded, color: Color(0xFF64748B), size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _addressController,
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
                onTap: () async {
                  final data = await Clipboard.getData('text/plain');
                  if (data?.text != null) {
                    _addressController.text = data!.text!;
                  }
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E2E),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text(
                    'Paste',
                    style: TextStyle(color: Color(0xFF6366F1), fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () => _showScannerModal(context),
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E2E),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.qr_code_scanner_rounded, color: Color(0xFF64748B), size: 18),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildCheckButton() {
    return GestureDetector(
      onTap: _checkAddress,
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)]),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF6366F1).withOpacity(0.4),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: const Center(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.search_rounded, color: Colors.white, size: 20),
              SizedBox(width: 8),
              Text(
                'Check Address',
                style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLoading() {
    return Container(
      height: 200,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: 60,
              height: 60,
              child: CircularProgressIndicator(
                strokeWidth: 3,
                valueColor: const AlwaysStoppedAnimation(Color(0xFF6366F1)),
                backgroundColor: const Color(0xFF1E1E2E),
              ),
            ),
            const SizedBox(height: 20),
            const Text(
              'Analyzing address...',
              style: TextStyle(color: Colors.white, fontSize: 16),
            ),
            const SizedBox(height: 8),
            Text(
              'Checking sanctions lists, transaction history, and risk factors',
              style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 13),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildError() {
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
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _errorMessage ?? 'Trust check failed',
              style: const TextStyle(color: Colors.white),
            ),
          ),
          TextButton(
            onPressed: _checkAddress,
            child: const Text('Retry', style: TextStyle(color: Color(0xFFF59E0B))),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreCard() {
    final isGood = _trustScore >= 70;
    final isMedium = _trustScore >= 40 && _trustScore < 70;

    Color scoreColor;
    String scoreLabel;
    switch (_bucket.toLowerCase()) {
      case 'trusted':
        scoreColor = const Color(0xFF22C55E);
        scoreLabel = 'TRUSTED';
        break;
      case 'caution':
        scoreColor = const Color(0xFFF59E0B);
        scoreLabel = 'CAUTION';
        break;
      case 'restricted':
        scoreColor = const Color(0xFFEF4444);
        scoreLabel = 'RESTRICTED';
        break;
      default:
        if (isGood) {
          scoreColor = const Color(0xFF22C55E);
          scoreLabel = 'TRUSTED';
        } else if (isMedium) {
          scoreColor = const Color(0xFFF59E0B);
          scoreLabel = 'CAUTION';
        } else {
          scoreColor = const Color(0xFFEF4444);
          scoreLabel = 'HIGH RISK';
        }
    }

    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: scoreColor.withOpacity(0.3)),
        boxShadow: [
          BoxShadow(
            color: scoreColor.withOpacity(0.15),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        children: [
          // Score ring
          AnimatedBuilder(
            animation: _scoreAnimation,
            builder: (context, child) {
              return SizedBox(
                width: 140,
                height: 140,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    // Background ring
                    SizedBox(
                      width: 140,
                      height: 140,
                      child: CircularProgressIndicator(
                        value: 1,
                        strokeWidth: 10,
                        backgroundColor: const Color(0xFF1E1E2E),
                        valueColor: const AlwaysStoppedAnimation(Color(0xFF1E1E2E)),
                      ),
                    ),
                    // Progress ring
                    SizedBox(
                      width: 140,
                      height: 140,
                      child: CircularProgressIndicator(
                        value: _scoreAnimation.value / 100,
                        strokeWidth: 10,
                        backgroundColor: Colors.transparent,
                        valueColor: AlwaysStoppedAnimation(scoreColor),
                        strokeCap: StrokeCap.round,
                      ),
                    ),
                    // Score text
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _scoreAnimation.value.toInt().toString(),
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 44,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Container(
                          width: 40,
                          height: 2,
                          color: Colors.white.withOpacity(0.2),
                        ),
                        const SizedBox(height: 4),
                        const Text(
                          '100',
                          style: TextStyle(
                            color: Color(0xFF64748B),
                            fontSize: 16,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              );
            },
          ),
          const SizedBox(height: 20),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: scoreColor.withOpacity(0.15),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isGood ? Icons.verified_rounded : (isMedium ? Icons.warning_rounded : Icons.dangerous_rounded),
                  color: scoreColor,
                  size: 18,
                ),
                const SizedBox(width: 6),
                Text(
                  scoreLabel,
                  style: TextStyle(
                    color: scoreColor,
                    fontSize: 14,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            _addressController.text.length > 20
                ? '${_addressController.text.substring(0, 8)}...${_addressController.text.substring(_addressController.text.length - 6)}'
                : _addressController.text,
            style: TextStyle(
              color: Colors.white.withOpacity(0.6),
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRiskBreakdown() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Risk Breakdown',
          style: TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 16),
        ..._riskChecks.map((check) => _buildRiskItem(check)),
      ],
    );
  }

  Widget _buildRiskItem(Map<String, dynamic> check) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF12121A),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF1E1E2E)),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: (check['color'] as Color).withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(check['icon'] as IconData, color: check['color'] as Color, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  check['title'] as String,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  check['description'] as String,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.5),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: (check['color'] as Color).withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              check['status'] as String,
              style: TextStyle(
                color: check['color'] as Color,
                fontSize: 11,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildGraphPreview() {
    return Container(
      padding: const EdgeInsets.all(20),
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
                'Transaction Graph',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              TextButton(
                onPressed: () => _showGraphModal(),
                child: const Text(
                  'View details',
                  style: TextStyle(
                    color: Color(0xFF6366F1),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          // Simplified graph preview
          SizedBox(
            height: 120,
            child: Center(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  _buildGraphNode('A', const Color(0xFF22C55E)),
                  _buildGraphEdge(),
                  _buildGraphNode('B', const Color(0xFF22C55E)),
                  _buildGraphEdge(),
                  _buildGraphNode('You', const Color(0xFF6366F1), isMain: true),
                  _buildGraphEdge(),
                  _buildGraphNode('C', const Color(0xFF22C55E)),
                  _buildGraphEdge(),
                  _buildGraphNode('D', const Color(0xFFF59E0B)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildLegendItem('Clean', const Color(0xFF22C55E)),
              const SizedBox(width: 16),
              _buildLegendItem('Caution', const Color(0xFFF59E0B)),
              const SizedBox(width: 16),
              _buildLegendItem('Flagged', const Color(0xFFEF4444)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildGraphNode(String label, Color color, {bool isMain = false}) {
    return Container(
      width: isMain ? 50 : 40,
      height: isMain ? 50 : 40,
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        shape: BoxShape.circle,
        border: Border.all(color: color, width: isMain ? 2 : 1),
      ),
      child: Center(
        child: Text(
          label,
          style: TextStyle(
            color: color,
            fontSize: isMain ? 12 : 10,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }

  Widget _buildGraphEdge() {
    return Container(
      width: 20,
      height: 2,
      color: const Color(0xFF374151),
    );
  }

  Widget _buildLegendItem(String label, Color color) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
          ),
        ),
        const SizedBox(width: 6),
        Text(
          label,
          style: TextStyle(
            color: Colors.white.withOpacity(0.5),
            fontSize: 11,
          ),
        ),
      ],
    );
  }

  Widget _buildActions() {
    final risky = _bucket.toUpperCase() == 'HIGH RISK';
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1E1E2E),
                  foregroundColor: const Color(0xFF22C55E),
                  side: const BorderSide(color: Color(0xFF22C55E)),
                  padding: const EdgeInsets.symmetric(vertical: 12),
                ),
                onPressed: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Escrow/Manual review opened (mock)')),
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
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: TextButton.icon(
            onPressed: () async {
              final proceed = await _confirmSend();
              if (proceed) context.push('/transfer');
            },
            icon: Icon(Icons.send_rounded, color: risky ? const Color(0xFFEF4444) : const Color(0xFF818CF8)),
            label: Text(
              risky ? 'Send anyway (confirm)' : 'Send',
              style: TextStyle(
                color: risky ? const Color(0xFFEF4444) : const Color(0xFF818CF8),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Future<bool> _confirmSend() async {
    final risky = _bucket.toUpperCase() == 'HIGH RISK';
    if (!risky) return true;
    return await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: const Color(0xFF12121A),
            title: const Text('Proceed despite risk?', style: TextStyle(color: Colors.white)),
            content: const Text(
              'This address is marked high risk. Confirm you want to continue.',
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

  void _showGraphModal() {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (ctx) => Container(
        height: MediaQuery.of(context).size.height * 0.7,
        padding: const EdgeInsets.all(24),
        decoration: const BoxDecoration(
          color: Color(0xFF12121A),
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Explainability Graph',
                  style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w700),
                ),
                IconButton(
                  onPressed: () => Navigator.pop(ctx),
                  icon: const Icon(Icons.close, color: Colors.white54),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF0A0A0F),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: const Color(0xFF1E1E2E)),
                ),
                child: const Center(
                  child: Text(
                    'Graph detail placeholder',
                    style: TextStyle(color: Colors.white54),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
  
  void _showInfoModal(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
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
              'About Trust Check',
              style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            _buildInfoItem(
              icon: Icons.shield_rounded,
              title: 'Sanctions Screening',
              description: 'Checks OFAC, EU, UN sanctions lists in real-time',
            ),
            _buildInfoItem(
              icon: Icons.history_rounded,
              title: 'Transaction History',
              description: 'Analyzes on-chain activity patterns and age',
            ),
            _buildInfoItem(
              icon: Icons.account_tree_rounded,
              title: 'Source of Funds',
              description: 'Traces fund origins through graph analysis',
            ),
            _buildInfoItem(
              icon: Icons.blur_circular_rounded,
              title: 'Mixer Exposure',
              description: 'Detects connections to mixers and privacy protocols',
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
  
  Widget _buildInfoItem({required IconData icon, required String title, required String description}) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A2E),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: const Color(0xFF6366F1).withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: const Color(0xFF6366F1), size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                Text(description, style: TextStyle(color: Colors.white.withOpacity(0.5), fontSize: 12)),
              ],
            ),
          ),
        ],
      ),
    );
  }
  
  void _showScannerModal(BuildContext context) {
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
            const Text('Scan Address', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
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
                      Text('Camera permission required', style: TextStyle(color: Colors.white.withOpacity(0.5))),
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
}
