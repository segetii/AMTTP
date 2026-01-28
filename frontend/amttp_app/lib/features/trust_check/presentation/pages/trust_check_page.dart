/// Trust Check Page
/// 
/// Per Ground Truth v2.3:
/// - Pre-Transaction Trust Check in Focus Mode
/// - Shows risk indicators before proceeding with transfer
/// - Simple binary outcome with brief explanation

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';

class TrustCheckPage extends ConsumerStatefulWidget {
  final String counterpartyAddress;
  
  const TrustCheckPage({
    super.key,
    required this.counterpartyAddress,
  });

  @override
  ConsumerState<TrustCheckPage> createState() => _TrustCheckPageState();
}

class _TrustCheckPageState extends ConsumerState<TrustCheckPage> {
  bool _isLoading = true;
  TrustCheckResult? _result;

  @override
  void initState() {
    super.initState();
    _performTrustCheck();
  }

  Future<void> _performTrustCheck() async {
    // Simulate API call
    await Future.delayed(const Duration(seconds: 2));
    
    if (mounted) {
      setState(() {
        _isLoading = false;
        // Mock result - in production this would come from API
        _result = _mockTrustCheck(widget.counterpartyAddress);
      });
    }
  }

  TrustCheckResult _mockTrustCheck(String address) {
    // Demo: addresses starting with 0xBAD are flagged
    if (address.toLowerCase().startsWith('0xbad')) {
      return TrustCheckResult(
        address: address,
        trustLevel: TrustLevel.high,
        riskFactors: ['Address associated with known scam reports', 'Recently created wallet'],
        recommendation: 'Proceed with caution. Consider verifying recipient through other channels.',
      );
    } else if (address.toLowerCase().contains('new')) {
      return TrustCheckResult(
        address: address,
        trustLevel: TrustLevel.medium,
        riskFactors: ['New address with limited history'],
        recommendation: 'Limited transaction history available. Verify recipient if sending large amounts.',
      );
    }
    
    return TrustCheckResult(
      address: address,
      trustLevel: TrustLevel.low,
      riskFactors: [],
      recommendation: 'No significant risk factors detected.',
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    
    return Scaffold(
      appBar: AppBar(
        title: const Text('Trust Check'),
        backgroundColor: isDark ? AppTheme.slate900 : Colors.white,
        elevation: 0,
      ),
      body: _isLoading
          ? _buildLoadingState(theme, isDark)
          : _buildResultState(theme, isDark),
    );
  }

  Widget _buildLoadingState(ThemeData theme, bool isDark) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 80,
            height: 80,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation<Color>(
                isDark ? AppTheme.purple400 : AppTheme.purple600,
              ),
            ),
          ),
          const SizedBox(height: 24),
          Text(
            'Checking Trust Signals...',
            style: theme.textTheme.titleLarge?.copyWith(
              color: isDark ? Colors.white : AppTheme.slate800,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Analyzing on-chain data',
            style: theme.textTheme.bodyMedium?.copyWith(
              color: isDark ? AppTheme.slate400 : AppTheme.slate600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildResultState(ThemeData theme, bool isDark) {
    if (_result == null) return const SizedBox();

    final result = _result!;
    final colors = _getTrustLevelColors(result.trustLevel, isDark);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Trust Level Indicator
          Container(
            padding: const EdgeInsets.all(32),
            decoration: BoxDecoration(
              color: colors.background,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: colors.border),
            ),
            child: Column(
              children: [
                Icon(
                  colors.icon,
                  size: 64,
                  color: colors.iconColor,
                ),
                const SizedBox(height: 16),
                Text(
                  colors.label,
                  style: theme.textTheme.headlineSmall?.copyWith(
                    color: colors.textColor,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  result.recommendation,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: isDark ? AppTheme.slate300 : AppTheme.slate600,
                  ),
                ),
              ],
            ),
          ),
          
          const SizedBox(height: 24),
          
          // Address being checked
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isDark ? AppTheme.slate800 : Colors.grey.shade100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Recipient Address',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: isDark ? AppTheme.slate400 : AppTheme.slate600,
                  ),
                ),
                const SizedBox(height: 8),
                SelectableText(
                  result.address,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontFamily: 'monospace',
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
              ],
            ),
          ),
          
          // Risk Factors (if any)
          if (result.riskFactors.isNotEmpty) ...[
            const SizedBox(height: 24),
            Text(
              'Risk Factors',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.bold,
                color: isDark ? Colors.white : AppTheme.slate800,
              ),
            ),
            const SizedBox(height: 12),
            ...result.riskFactors.map((factor) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.warning_amber_rounded,
                    size: 20,
                    color: AppTheme.amber500,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      factor,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: isDark ? AppTheme.slate300 : AppTheme.slate700,
                      ),
                    ),
                  ),
                ],
              ),
            )),
          ],
          
          const SizedBox(height: 32),
          
          // Action Buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => Navigator.of(context).pop(),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    side: BorderSide(
                      color: isDark ? AppTheme.slate600 : AppTheme.slate300,
                    ),
                  ),
                  child: Text(
                    'Cancel',
                    style: TextStyle(
                      color: isDark ? AppTheme.slate300 : AppTheme.slate700,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: ElevatedButton(
                  onPressed: () {
                    // Return result to transfer page
                    Navigator.of(context).pop(result);
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: result.trustLevel == TrustLevel.high
                        ? AppTheme.amber500
                        : AppTheme.purple600,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: Text(
                    result.trustLevel == TrustLevel.high
                        ? 'Proceed Anyway'
                        : 'Continue',
                    style: const TextStyle(color: Colors.white),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  _TrustLevelColors _getTrustLevelColors(TrustLevel level, bool isDark) {
    switch (level) {
      case TrustLevel.low:
        return _TrustLevelColors(
          background: isDark ? const Color(0xFF064E3B) : const Color(0xFFD1FAE5),
          border: isDark ? const Color(0xFF059669) : const Color(0xFF6EE7B7),
          icon: Icons.check_circle_outline,
          iconColor: const Color(0xFF10B981),
          textColor: isDark ? const Color(0xFF6EE7B7) : const Color(0xFF047857),
          label: 'Low Risk',
        );
      case TrustLevel.medium:
        return _TrustLevelColors(
          background: isDark ? const Color(0xFF78350F) : const Color(0xFFFEF3C7),
          border: isDark ? const Color(0xFFF59E0B) : const Color(0xFFFCD34D),
          icon: Icons.info_outline,
          iconColor: const Color(0xFFF59E0B),
          textColor: isDark ? const Color(0xFFFCD34D) : const Color(0xFFB45309),
          label: 'Medium Risk',
        );
      case TrustLevel.high:
        return _TrustLevelColors(
          background: isDark ? const Color(0xFF7F1D1D) : const Color(0xFFFEE2E2),
          border: isDark ? const Color(0xFFEF4444) : const Color(0xFFFCA5A5),
          icon: Icons.warning_amber_outlined,
          iconColor: const Color(0xFFEF4444),
          textColor: isDark ? const Color(0xFFFCA5A5) : const Color(0xFFB91C1C),
          label: 'High Risk',
        );
    }
  }
}

class _TrustLevelColors {
  final Color background;
  final Color border;
  final IconData icon;
  final Color iconColor;
  final Color textColor;
  final String label;

  _TrustLevelColors({
    required this.background,
    required this.border,
    required this.icon,
    required this.iconColor,
    required this.textColor,
    required this.label,
  });
}

enum TrustLevel { low, medium, high }

class TrustCheckResult {
  final String address;
  final TrustLevel trustLevel;
  final List<String> riskFactors;
  final String recommendation;

  TrustCheckResult({
    required this.address,
    required this.trustLevel,
    required this.riskFactors,
    required this.recommendation,
  });
}
