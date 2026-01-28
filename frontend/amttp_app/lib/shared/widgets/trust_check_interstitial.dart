import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';

/// Trust Pillar Status - Per Ground Truth Colors
/// - Low Risk (Verified): #3FB950
/// - Medium Risk (Limited): #F5A524
/// - Unknown: #9AA1AC (secondary text)
/// - High Risk (Unverified/Anomalous): #E5484D
enum TrustPillarStatus {
  verified('Verified', AppTheme.riskLow, Icons.check_circle),           // #3FB950
  limited('Limited', AppTheme.riskMedium, Icons.warning_amber),         // #F5A524
  unknown('Unknown', AppTheme.textSecondary, Icons.help_outline),       // #9AA1AC
  unverified('Unverified', AppTheme.riskHigh, Icons.cancel),            // #E5484D
  anomalous('Anomalous', AppTheme.riskHigh, Icons.error);               // #E5484D

  final String label;
  final Color color;
  final IconData icon;
  
  const TrustPillarStatus(this.label, this.color, this.icon);
}

/// Trust Pillars (Qualitative, Non-Numeric per Ground Truth)
class TrustPillars {
  final TrustPillarStatus identity;
  final TrustPillarStatus transactionHistory;
  final TrustPillarStatus disputeRecord;
  final TrustPillarStatus networkProximity;
  final TrustPillarStatus behavioralSignals;

  const TrustPillars({
    this.identity = TrustPillarStatus.unknown,
    this.transactionHistory = TrustPillarStatus.unknown,
    this.disputeRecord = TrustPillarStatus.unknown,
    this.networkProximity = TrustPillarStatus.unknown,
    this.behavioralSignals = TrustPillarStatus.unknown,
  });

  /// Overall trust level (not numeric, just an aggregate status)
  TrustPillarStatus get overallStatus {
    final statuses = [identity, transactionHistory, disputeRecord, networkProximity, behavioralSignals];
    
    // If any are unverified/anomalous, overall is at risk
    if (statuses.any((s) => s == TrustPillarStatus.unverified || s == TrustPillarStatus.anomalous)) {
      return TrustPillarStatus.anomalous;
    }
    
    // If all verified, overall is verified
    if (statuses.every((s) => s == TrustPillarStatus.verified)) {
      return TrustPillarStatus.verified;
    }
    
    // If mostly verified or limited, overall is limited
    final verifiedCount = statuses.where((s) => s == TrustPillarStatus.verified).length;
    if (verifiedCount >= 3) {
      return TrustPillarStatus.limited;
    }
    
    return TrustPillarStatus.unknown;
  }

  /// Should show escrow recommendation
  bool get shouldRecommendEscrow {
    return overallStatus == TrustPillarStatus.unknown || 
           overallStatus == TrustPillarStatus.anomalous ||
           disputeRecord != TrustPillarStatus.verified;
  }
}

/// Trust Check Result
class TrustCheckResult {
  final String counterpartyAddress;
  final TrustPillars pillars;
  final bool isFirstInteraction;
  final DateTime checkedAt;
  final String? institutionName;

  const TrustCheckResult({
    required this.counterpartyAddress,
    required this.pillars,
    this.isFirstInteraction = true,
    required this.checkedAt,
    this.institutionName,
  });
}

/// Pre-Transaction Trust Check Interstitial
/// 
/// Mandatory screen before any transfer (per Ground Truth spec).
/// Shows trust pillars in qualitative form (NOT numeric scores).
/// User must make informed decision: Continue, Use Escrow, or Cancel.

class TrustCheckInterstitial extends StatefulWidget {
  final String counterpartyAddress;
  final String amount;
  final String currency;
  final TrustCheckResult? preloadedResult;
  final VoidCallback onContinue;
  final VoidCallback onUseEscrow;
  final VoidCallback onCancel;

  const TrustCheckInterstitial({
    super.key,
    required this.counterpartyAddress,
    required this.amount,
    required this.currency,
    this.preloadedResult,
    required this.onContinue,
    required this.onUseEscrow,
    required this.onCancel,
  });

  @override
  State<TrustCheckInterstitial> createState() => _TrustCheckInterstitialState();
}

class _TrustCheckInterstitialState extends State<TrustCheckInterstitial> {
  bool _isLoading = true;
  TrustCheckResult? _result;
  bool _acknowledged = false;

  @override
  void initState() {
    super.initState();
    if (widget.preloadedResult != null) {
      _result = widget.preloadedResult;
      _isLoading = false;
    } else {
      _performTrustCheck();
    }
  }

  Future<void> _performTrustCheck() async {
    // Simulate API call to trust check service
    await Future.delayed(const Duration(milliseconds: 1500));
    
    // Mock result - in production this would come from the API
    setState(() {
      _result = TrustCheckResult(
        counterpartyAddress: widget.counterpartyAddress,
        pillars: const TrustPillars(
          identity: TrustPillarStatus.verified,
          transactionHistory: TrustPillarStatus.limited,
          disputeRecord: TrustPillarStatus.verified,
          networkProximity: TrustPillarStatus.unknown,
          behavioralSignals: TrustPillarStatus.verified,
        ),
        isFirstInteraction: true,
        checkedAt: DateTime.now(),
      );
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black54,
      child: Center(
        child: Container(
          margin: const EdgeInsets.all(24),
          constraints: const BoxConstraints(maxWidth: 480),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(24),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2),
                blurRadius: 20,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: _isLoading ? _buildLoading() : _buildContent(),
        ),
      ),
    );
  }

  Widget _buildLoading() {
    return const Padding(
      padding: EdgeInsets.all(48),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          CircularProgressIndicator(color: Color(0xFF6366F1)),
          SizedBox(height: 24),
          Text(
            'Checking Trust Status...',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w600,
              color: Color(0xFF1E293B),
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Verifying recipient address against our trust database',
            style: TextStyle(
              color: Color(0xFF64748B),
              fontSize: 14,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildContent() {
    final result = _result!;
    final pillars = result.pillars;
    final overall = pillars.overallStatus;
    
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: overall.color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(overall.icon, color: overall.color, size: 24),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Pre-Transaction Trust Check',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF1E293B),
                        ),
                      ),
                      Text(
                        'Overall: ${overall.label}',
                        style: TextStyle(
                          color: overall.color,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: Color(0xFF64748B)),
                  onPressed: widget.onCancel,
                ),
              ],
            ),
            
            const SizedBox(height: 24),
            
            // Transfer Summary
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Amount', style: TextStyle(color: Color(0xFF64748B))),
                      Text(
                        '${widget.amount} ${widget.currency}',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('To', style: TextStyle(color: Color(0xFF64748B))),
                      Text(
                        '${widget.counterpartyAddress.substring(0, 8)}...${widget.counterpartyAddress.substring(widget.counterpartyAddress.length - 6)}',
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],
                  ),
                  if (result.isFirstInteraction) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFEF3C7),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.info, color: Color(0xFFF59E0B), size: 14),
                          SizedBox(width: 4),
                          Text(
                            'First interaction with this address',
                            style: TextStyle(
                              color: Color(0xFFB45309),
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            
            const SizedBox(height: 24),
            
            // Trust Pillars (Qualitative, Non-Numeric)
            const Text(
              'Trust Pillars',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: Color(0xFF1E293B),
              ),
            ),
            const SizedBox(height: 12),
            
            _buildPillarRow('Identity Confidence', pillars.identity),
            _buildPillarRow('Transaction History', pillars.transactionHistory),
            _buildPillarRow('Dispute Record', pillars.disputeRecord),
            _buildPillarRow('Network Proximity', pillars.networkProximity),
            _buildPillarRow('Behavioral Signals', pillars.behavioralSignals),
            
            const SizedBox(height: 24),
            
            // UI Integrity Badge - Ground Truth: #4CC9F0 (integrityLock)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.integrityLock.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.integrityLock.withOpacity(0.3)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.lock, color: AppTheme.integrityLock, size: 16),
                  const SizedBox(width: 8),
                  Text(
                    'UI Integrity Verified',
                    style: TextStyle(
                      color: AppTheme.integrityLock,
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                ],
              ),
            ),
            
            const SizedBox(height: 24),
            
            // Acknowledgement for risky transfers
            if (pillars.shouldRecommendEscrow || pillars.overallStatus != TrustPillarStatus.verified)
              CheckboxListTile(
                value: _acknowledged,
                onChanged: (v) => setState(() => _acknowledged = v ?? false),
                title: const Text(
                  'I understand the trust status and wish to proceed',
                  style: TextStyle(fontSize: 14),
                ),
                controlAffinity: ListTileControlAffinity.leading,
                contentPadding: EdgeInsets.zero,
                activeColor: const Color(0xFF6366F1),
              ),
            
            const SizedBox(height: 16),
            
            // Action Buttons
            Row(
              children: [
                // Cancel
                Expanded(
                  child: OutlinedButton(
                    onPressed: widget.onCancel,
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      side: const BorderSide(color: Color(0xFFE2E8F0)),
                    ),
                    child: const Text(
                      'Cancel',
                      style: TextStyle(color: Color(0xFF64748B)),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                
                // Use Escrow (Recommended if risky)
                if (pillars.shouldRecommendEscrow)
                  Expanded(
                    child: ElevatedButton(
                      onPressed: widget.onUseEscrow,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF3B82F6),
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.shield, size: 18),
                          SizedBox(width: 8),
                          Text('Use Escrow'),
                        ],
                      ),
                    ),
                  ),
                
                if (pillars.shouldRecommendEscrow) const SizedBox(width: 12),
                
                // Continue
                Expanded(
                  child: ElevatedButton(
                    onPressed: (pillars.overallStatus == TrustPillarStatus.verified || _acknowledged)
                      ? widget.onContinue
                      : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF10B981),
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text('Continue'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPillarRow(String label, TrustPillarStatus status) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(status.icon, color: status.color, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: const TextStyle(color: Color(0xFF64748B)),
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: status.color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              status.label,
              style: TextStyle(
                color: status.color,
                fontWeight: FontWeight.w600,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
