import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/security/ui_integrity_service.dart';
import '../../core/theme/app_theme.dart';

/// Multisig Approval Action Types
enum MultisigActionType {
  walletPause('WALLET_PAUSE', 'Wallet Pause', Icons.pause_circle),
  walletUnpause('WALLET_UNPAUSE', 'Wallet Unpause', Icons.play_circle),
  assetFreeze('ASSET_FREEZE', 'Asset Freeze', Icons.ac_unit),
  assetUnfreeze('ASSET_UNFREEZE', 'Asset Unfreeze', Icons.sunny),
  policyChange('POLICY_CHANGE', 'Policy Change', Icons.rule),
  roleAssignment('ROLE_ASSIGNMENT', 'Role Assignment', Icons.person_add),
  emergencyOverride('EMERGENCY_OVERRIDE', 'Emergency Override', Icons.warning_amber);

  final String code;
  final String displayName;
  final IconData icon;
  
  const MultisigActionType(this.code, this.displayName, this.icon);
}

/// Multisig Approval Request Model
class MultisigRequest {
  final String requestId;
  final MultisigActionType actionType;
  final String targetAddress;
  final String? targetScope;
  final String? duration;
  final String requestedBy;
  final DateTime requestedAt;
  final int requiredSignatures;
  final int currentSignatures;
  final List<String> signers;
  final Map<String, dynamic> riskContext;
  final String uiSnapshotHash;

  const MultisigRequest({
    required this.requestId,
    required this.actionType,
    required this.targetAddress,
    this.targetScope,
    this.duration,
    required this.requestedBy,
    required this.requestedAt,
    required this.requiredSignatures,
    required this.currentSignatures,
    required this.signers,
    required this.riskContext,
    required this.uiSnapshotHash,
  });

  bool get hasQuorum => currentSignatures >= requiredSignatures;
  int get remainingSignatures => requiredSignatures - currentSignatures;
}

/// Risk Context Item for WYA display
class RiskContextItem {
  final String label;
  final String value;
  final bool isHighlight;

  const RiskContextItem({
    required this.label,
    required this.value,
    this.isHighlight = false,
  });
}

/// WYA (What-You-Approve) Screen
/// 
/// Per Ground Truth spec: Users must verify UI integrity hash before signing.
/// 
/// Features:
/// - Clear display of what's being approved
/// - Risk context summary
/// - UI snapshot hash verification
/// - Checkbox acknowledgement before sign enabled
/// - MFA/Biometric integration point

class MultisigApprovalCard extends ConsumerStatefulWidget {
  final MultisigRequest request;
  final VoidCallback onApprove;
  final VoidCallback onReject;
  final VoidCallback? onViewInvestigation;

  const MultisigApprovalCard({
    super.key,
    required this.request,
    required this.onApprove,
    required this.onReject,
    this.onViewInvestigation,
  });

  @override
  ConsumerState<MultisigApprovalCard> createState() => _MultisigApprovalCardState();
}

class _MultisigApprovalCardState extends ConsumerState<MultisigApprovalCard> {
  bool _hashAcknowledged = false;
  bool _isVerifying = false;
  bool _isApproving = false;
  String? _verificationError;
  ComponentIntegrity? _currentIntegrity;

  @override
  void initState() {
    super.initState();
    _captureIntegrity();
  }

  void _captureIntegrity() {
    _currentIntegrity = UIIntegrityService.captureComponentIntegrity(
      componentId: 'MultisigApproval_${widget.request.requestId}',
      state: {
        'requestId': widget.request.requestId,
        'actionType': widget.request.actionType.code,
        'targetAddress': widget.request.targetAddress,
        'uiSnapshotHash': widget.request.uiSnapshotHash,
      },
      handlers: ['onApprove', 'onReject'],
    );
  }

  Future<void> _verifyAndSign() async {
    if (!_hashAcknowledged) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please acknowledge the UI integrity hash first'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    setState(() {
      _isVerifying = true;
      _verificationError = null;
    });

    try {
      // Verify current UI matches stored hash
      final currentHash = _currentIntegrity?.stateHash ?? '';
      
      // In production, this would verify against server
      await Future.delayed(const Duration(milliseconds: 500));
      
      // Simulate verification
      final hashMatches = currentHash.isNotEmpty;
      
      if (!hashMatches) {
        setState(() {
          _verificationError = 'UI integrity verification failed. Please refresh and try again.';
          _isVerifying = false;
        });
        return;
      }

      setState(() {
        _isVerifying = false;
        _isApproving = true;
      });

      // MFA/Biometric would go here
      await Future.delayed(const Duration(milliseconds: 300));
      
      // Call the approval callback
      widget.onApprove();
      
    } catch (e) {
      setState(() {
        _verificationError = 'Verification error: $e';
        _isVerifying = false;
        _isApproving = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppTheme.darkCard,
      elevation: 8,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: AppTheme.primaryBlue.withOpacity(0.3),
          width: 1,
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
            _buildHeader(),
            const SizedBox(height: 24),
            
            // Divider
            Divider(color: AppTheme.cleanWhite.withOpacity(0.1)),
            const SizedBox(height: 16),
            
            // WYA Section
            _buildWYASection(),
            const SizedBox(height: 24),
            
            // Risk Context
            _buildRiskContext(),
            const SizedBox(height: 24),
            
            // Divider
            Divider(color: AppTheme.cleanWhite.withOpacity(0.1)),
            const SizedBox(height: 16),
            
            // UI Integrity Section
            _buildIntegritySection(),
            const SizedBox(height: 24),
            
            // Error message if any
            if (_verificationError != null)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.red.withOpacity(0.3)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.error_outline, color: Colors.red, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _verificationError!,
                        style: const TextStyle(color: Colors.red, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
            
            // Actions
            _buildActions(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppTheme.primaryBlue.withOpacity(0.15),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Icon(
            widget.request.actionType.icon,
            color: AppTheme.primaryBlue,
            size: 28,
          ),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'MULTISIG APPROVAL',
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.6),
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Signature ${widget.request.currentSignatures + 1} of ${widget.request.requiredSignatures} required',
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        // Signature progress
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: widget.request.currentSignatures > 0
                ? AppTheme.neonGreen.withOpacity(0.15)
                : AppTheme.cleanWhite.withOpacity(0.05),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: List.generate(widget.request.requiredSignatures, (i) {
              final isSigned = i < widget.request.currentSignatures;
              return Container(
                margin: const EdgeInsets.symmetric(horizontal: 2),
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isSigned ? AppTheme.neonGreen : AppTheme.cleanWhite.withOpacity(0.3),
                ),
              );
            }),
          ),
        ),
      ],
    );
  }

  Widget _buildWYASection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.cleanWhite.withOpacity(0.03),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.cleanWhite.withOpacity(0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.visibility, color: AppTheme.primaryBlue, size: 20),
              const SizedBox(width: 8),
              Text(
                'WHAT YOU ARE APPROVING (WYA)',
                style: TextStyle(
                  color: AppTheme.primaryBlue,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          
          _buildInfoRow('Action', widget.request.actionType.displayName),
          _buildInfoRow('Target', widget.request.targetAddress, isMono: true),
          if (widget.request.targetScope != null)
            _buildInfoRow('Scope', widget.request.targetScope!),
          if (widget.request.duration != null)
            _buildInfoRow('Duration', widget.request.duration!),
          _buildInfoRow('Requested By', widget.request.requestedBy),
          _buildInfoRow('Requested At', _formatDateTime(widget.request.requestedAt)),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value, {bool isMono = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: TextStyle(
                color: AppTheme.cleanWhite.withOpacity(0.5),
                fontSize: 13,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 13,
                fontWeight: FontWeight.w500,
                fontFamily: isMono ? 'JetBrains Mono' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildRiskContext() {
    final items = _parseRiskContext(widget.request.riskContext);
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.orange.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.orange.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.analytics, color: Colors.orange, size: 20),
              const SizedBox(width: 8),
              const Text(
                'RISK CONTEXT SUMMARY',
                style: TextStyle(
                  color: Colors.orange,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          
          ...items.map((item) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              children: [
                Icon(
                  item.isHighlight ? Icons.warning_amber : Icons.circle,
                  size: item.isHighlight ? 18 : 6,
                  color: item.isHighlight 
                      ? Colors.orange 
                      : AppTheme.cleanWhite.withOpacity(0.4),
                ),
                SizedBox(width: item.isHighlight ? 8 : 10),
                Text(
                  '${item.label}: ',
                  style: TextStyle(
                    color: AppTheme.cleanWhite.withOpacity(0.6),
                    fontSize: 13,
                  ),
                ),
                Text(
                  item.value,
                  style: TextStyle(
                    color: item.isHighlight ? Colors.orange : AppTheme.cleanWhite,
                    fontSize: 13,
                    fontWeight: item.isHighlight ? FontWeight.w600 : FontWeight.normal,
                  ),
                ),
              ],
            ),
          )),
          
          if (widget.onViewInvestigation != null) ...[
            const SizedBox(height: 12),
            TextButton.icon(
              onPressed: widget.onViewInvestigation,
              icon: const Icon(Icons.search, size: 18),
              label: const Text('View Full Investigation'),
              style: TextButton.styleFrom(
                foregroundColor: AppTheme.primaryBlue,
                padding: EdgeInsets.zero,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildIntegritySection() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.primaryBlue.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: _hashAcknowledged 
              ? AppTheme.neonGreen.withOpacity(0.5)
              : AppTheme.primaryBlue.withOpacity(0.2),
          width: _hashAcknowledged ? 2 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                _hashAcknowledged ? Icons.verified : Icons.lock,
                color: _hashAcknowledged ? AppTheme.neonGreen : AppTheme.primaryBlue,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                'UI INTEGRITY VERIFICATION',
                style: TextStyle(
                  color: _hashAcknowledged ? AppTheme.neonGreen : AppTheme.primaryBlue,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.5,
                ),
              ),
              if (_hashAcknowledged) ...[
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: AppTheme.neonGreen.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'VERIFIED',
                    style: TextStyle(
                      color: AppTheme.neonGreen,
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          
          // Snapshot hash
          Row(
            children: [
              Text(
                'Snapshot Hash: ',
                style: TextStyle(
                  color: AppTheme.cleanWhite.withOpacity(0.5),
                  fontSize: 12,
                ),
              ),
              Expanded(
                child: Text(
                  widget.request.uiSnapshotHash.length > 20
                      ? '${widget.request.uiSnapshotHash.substring(0, 16)}…'
                      : widget.request.uiSnapshotHash,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 12,
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ),
              IconButton(
                icon: Icon(
                  Icons.copy,
                  size: 16,
                  color: AppTheme.cleanWhite.withOpacity(0.5),
                ),
                onPressed: () {
                  // Copy to clipboard
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Hash copied to clipboard')),
                  );
                },
                tooltip: 'Copy full hash',
              ),
            ],
          ),
          
          const SizedBox(height: 16),
          
          // Acknowledgement checkbox
          InkWell(
            onTap: () {
              setState(() {
                _hashAcknowledged = !_hashAcknowledged;
              });
            },
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Row(
                children: [
                  Container(
                    width: 24,
                    height: 24,
                    decoration: BoxDecoration(
                      color: _hashAcknowledged 
                          ? AppTheme.neonGreen 
                          : Colors.transparent,
                      border: Border.all(
                        color: _hashAcknowledged 
                            ? AppTheme.neonGreen 
                            : AppTheme.cleanWhite.withOpacity(0.4),
                        width: 2,
                      ),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: _hashAcknowledged
                        ? const Icon(Icons.check, size: 16, color: Colors.white)
                        : null,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'I verify this view matches the integrity hash',
                      style: TextStyle(
                        color: AppTheme.cleanWhite,
                        fontSize: 14,
                        fontWeight: _hashAcknowledged ? FontWeight.w500 : FontWeight.normal,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildActions() {
    return Row(
      children: [
        // Reject button
        Expanded(
          child: OutlinedButton.icon(
            onPressed: widget.onReject,
            icon: const Icon(Icons.close),
            label: const Text('REJECT'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
              side: const BorderSide(color: Colors.red),
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
        const SizedBox(width: 16),
        
        // Sign button
        Expanded(
          flex: 2,
          child: ElevatedButton.icon(
            onPressed: _hashAcknowledged && !_isVerifying && !_isApproving
                ? _verifyAndSign
                : null,
            icon: _isVerifying || _isApproving
                ? SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppTheme.cleanWhite,
                    ),
                  )
                : const Icon(Icons.fingerprint),
            label: Text(
              _isVerifying ? 'VERIFYING...' : (_isApproving ? 'SIGNING...' : 'SIGN APPROVAL'),
            ),
            style: ElevatedButton.styleFrom(
              backgroundColor: _hashAcknowledged 
                  ? AppTheme.neonGreen 
                  : AppTheme.cleanWhite.withOpacity(0.2),
              foregroundColor: _hashAcknowledged 
                  ? Colors.white 
                  : AppTheme.cleanWhite.withOpacity(0.5),
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
          ),
        ),
      ],
    );
  }

  List<RiskContextItem> _parseRiskContext(Map<String, dynamic> context) {
    final items = <RiskContextItem>[];
    
    if (context['fanOut'] != null) {
      items.add(RiskContextItem(
        label: 'Fan-Out',
        value: 'Across ${context['fanOut']} wallets',
        isHighlight: (context['fanOut'] as int) > 5,
      ));
    }
    
    if (context['velocitySpike'] != null) {
      items.add(RiskContextItem(
        label: 'Velocity Spike',
        value: '${context['velocitySpike']}σ above baseline',
        isHighlight: true,
      ));
    }
    
    if (context['priorDisputes'] != null) {
      items.add(RiskContextItem(
        label: 'Prior Dispute History',
        value: context['priorDisputes'] ? 'Yes' : 'No',
        isHighlight: context['priorDisputes'] as bool,
      ));
    }
    
    if (context['layering'] != null) {
      items.add(RiskContextItem(
        label: 'Layering Detected',
        value: context['layering'] ? 'Yes' : 'No',
        isHighlight: context['layering'] as bool,
      ));
    }
    
    if (context['mixerExposure'] != null) {
      items.add(RiskContextItem(
        label: 'Mixer Exposure',
        value: context['mixerExposure'] ? 'Detected' : 'None',
        isHighlight: context['mixerExposure'] as bool,
      ));
    }
    
    return items;
  }

  String _formatDateTime(DateTime dt) {
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} '
           '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
