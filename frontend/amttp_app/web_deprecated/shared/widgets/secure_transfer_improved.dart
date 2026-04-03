/// Improved Secure Transfer Widget using Repository Pattern
/// 
/// This version uses domain-specific repositories instead of monolithic ApiService:
/// - RiskRepository for ML risk scoring
/// - ComplianceRepository for transaction evaluation  
/// - Clear separation of concerns
/// - Proper error handling that NEVER silently approves
/// 
/// All other security features maintained:
/// - UI integrity protection
/// - Intent hashing
/// - Multi-stage confirmation flow
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/security/ui_integrity_service.dart';
import '../../core/providers/repository_providers.dart';
import '../../core/services/repositories/repositories.dart';
import '../../core/web3/wallet_provider.dart';
import '../../core/theme/app_theme.dart';

/// Transfer stages
enum TransferStage {
  input,
  riskAssessment,
  compliance,
  confirming,
  signing,
  complete,
  error,
}

/// Improved Secure Transfer Widget
/// 
/// Uses repository pattern for cleaner code and proper error handling
class SecureTransferImproved extends ConsumerStatefulWidget {
  const SecureTransferImproved({super.key});

  @override
  ConsumerState<SecureTransferImproved> createState() => _SecureTransferImprovedState();
}

class _SecureTransferImprovedState extends ConsumerState<SecureTransferImproved> {
  // Controllers
  final _recipientController = TextEditingController();
  final _amountController = TextEditingController();
  final _memoController = TextEditingController();

  // State
  TransferStage _stage = TransferStage.input;
  TransactionIntent? _intent;
  String? _intentHash;
  ComponentIntegrity? _initialIntegrity;
  
  // Risk assessment results
  RiskScore? _riskScore;
  ComplianceDecision? _complianceResult;
  
  // Transaction results
  String? _transactionHash;
  String? _errorMessage;
  String? _errorDetails;
  bool _isLoading = false;

  static const String _componentId = 'SecureTransferImproved';
  static const List<String> _handlers = [
    'onSubmit',
    'onCancel',
    'onConfirm',
    'onBack',
  ];

  @override
  void initState() {
    super.initState();
    _captureInitialIntegrity();
  }

  @override
  void dispose() {
    _recipientController.dispose();
    _amountController.dispose();
    _memoController.dispose();
    super.dispose();
  }

  void _captureInitialIntegrity() {
    _initialIntegrity = UIIntegrityService.captureComponentIntegrity(
      componentId: _componentId,
      state: _getCurrentState(),
      handlers: _handlers,
    );
  }

  Map<String, dynamic> _getCurrentState() => {
    'recipient': _recipientController.text,
    'amount': _amountController.text,
    'memo': _memoController.text,
    'stage': _stage.toString(),
  };

  /// Stage 1: Validate inputs and begin assessment
  Future<void> _handleSubmit() async {
    // Validate inputs
    final validationError = _validateInputs();
    if (validationError != null) {
      _showError(validationError);
      return;
    }

    // Get wallet address
    final wallet = ref.read(walletProvider);
    if (wallet.address == null) {
      _showError('Please connect wallet first');
      return;
    }

    // Create transaction intent
    _intent = UIIntegrityService.createTransactionIntent(
      from: wallet.address!,
      to: _recipientController.text.trim(),
      amount: _amountController.text.trim(),
      currency: 'ETH',
      memo: _memoController.text.isNotEmpty ? _memoController.text : null,
    );
    _intentHash = _intent!.getIntentHash();

    // Begin risk assessment
    setState(() {
      _stage = TransferStage.riskAssessment;
      _isLoading = true;
      _errorMessage = null;
    });

    await _performRiskAssessment();
  }

  String? _validateInputs() {
    if (_recipientController.text.isEmpty) {
      return 'Please enter recipient address';
    }
    
    final recipient = _recipientController.text.trim();
    if (!_isValidAddress(recipient)) {
      return 'Invalid Ethereum address format';
    }

    if (_amountController.text.isEmpty) {
      return 'Please enter amount';
    }

    final amount = double.tryParse(_amountController.text);
    if (amount == null || amount <= 0) {
      return 'Please enter a valid positive amount';
    }

    return null;
  }

  bool _isValidAddress(String address) {
    final regex = RegExp(r'^0x[a-fA-F0-9]{40}$');
    return regex.hasMatch(address);
  }

  /// Stage 2: Risk Assessment using ML service
  Future<void> _performRiskAssessment() async {
    try {
      final riskRepo = ref.read(riskRepositoryProvider);

      // Score the transaction
      _riskScore = await riskRepo.scoreTransaction(
        from: _intent!.from,
        to: _intent!.to,
        value: _intent!.amount,
      );

      // Check risk level
      if (_riskScore!.level == RiskLevel.critical) {
        setState(() {
          _stage = TransferStage.error;
          _errorMessage = '🚫 Transaction Blocked - Critical Risk';
          _errorDetails = '''
Risk Score: ${_riskScore!.score.toStringAsFixed(2)}
Risk Level: ${_riskScore!.level.name.toUpperCase()}

Factors:
${_riskScore!.factors.map((f) => '• $f').join('\n')}

${_riskScore!.explanation ?? ''}

This transaction cannot proceed due to severe risk indicators.
''';
          _isLoading = false;
        });
        return;
      }

      // Proceed to compliance check
      setState(() {
        _stage = TransferStage.compliance;
      });
      await _performComplianceCheck();
    } catch (e) {
      // On error, DENY the transaction - never silently approve
      setState(() {
        _stage = TransferStage.error;
        _errorMessage = '⚠️ Risk Assessment Failed';
        _errorDetails = '''
Unable to complete risk assessment. For security reasons, the transaction cannot proceed.

Error: $e

Please try again later or contact support if the issue persists.
''';
        _isLoading = false;
      });
    }
  }

  /// Stage 3: Compliance Check using policy engine
  Future<void> _performComplianceCheck() async {
    try {
      final complianceRepo = ref.read(complianceRepositoryProvider);

      // Evaluate with integrity
      final integrityReport = UIIntegrityService.generateReport(
        componentId: _componentId,
        state: _getCurrentState(),
        handlers: _handlers,
        trustedSnapshot: _initialIntegrity,
      );

      _complianceResult = await complianceRepo.evaluateWithIntegrity(
        from: _intent!.from,
        to: _intent!.to,
        value: _intent!.amount,
        intentHash: _intentHash!,
        integrityReport: integrityReport.toJson(),
      );

      // Check compliance decision
      if (_complianceResult!.action == 'BLOCK') {
        setState(() {
          _stage = TransferStage.error;
          _errorMessage = '❌ Transaction Blocked by Compliance';
          _errorDetails = '''
${_complianceResult!.reason}

Risk Score: ${_complianceResult!.riskScore.toStringAsFixed(2)}

${_complianceResult!.warnings.isNotEmpty ? 'Warnings:\n${_complianceResult!.warnings.map((w) => '• $w').join('\n')}' : ''}

This transaction has been blocked by compliance policy.
''';
          _isLoading = false;
        });
        return;
      }

      // Proceed to confirmation
      setState(() {
        _stage = TransferStage.confirming;
        _isLoading = false;
      });
    } catch (e) {
      // On error, DENY - compliance failures must block
      setState(() {
        _stage = TransferStage.error;
        _errorMessage = '⚠️ Compliance Check Failed';
        _errorDetails = '''
Unable to complete compliance check. For security reasons, the transaction cannot proceed.

Error: $e

Please try again later or contact support.
''';
        _isLoading = false;
      });
    }
  }

  /// Stage 4: User confirms after visual verification
  Future<void> _handleConfirm() async {
    // Re-validate integrity before signing
    final integrityReport = UIIntegrityService.generateReport(
      componentId: _componentId,
      state: _getCurrentState(),
      handlers: _handlers,
      trustedSnapshot: _initialIntegrity,
    );

    if (integrityReport.violations.any((v) => v.severity == ViolationSeverity.critical)) {
      setState(() {
        _stage = TransferStage.error;
        _errorMessage = '🚨 Security Alert: UI Manipulation Detected';
        _errorDetails = '''
The transaction interface has been tampered with.

This could indicate:
• Malware on your device
• Browser extension interference
• Man-in-the-middle attack

Please:
1. Do NOT proceed with this transaction
2. Clear your browser cache
3. Scan your device for malware
4. Contact support
''';
      });
      return;
    }

    setState(() {
      _stage = TransferStage.signing;
      _isLoading = true;
    });

    await _executeTransaction();
  }

  /// Stage 5: Execute the transaction
  Future<void> _executeTransaction() async {
    try {
      final walletNotifier = ref.read(walletProvider.notifier);

      // Sign and send transaction
      final txHash = await walletNotifier.sendTransaction(
        to: _intent!.to,
        amount: double.parse(_intent!.amount),
        data: _intentHash,
      );

      setState(() {
        _transactionHash = txHash;
        _stage = TransferStage.complete;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _stage = TransferStage.error;
        _errorMessage = '❌ Transaction Failed';
        _errorDetails = '''
The transaction could not be completed.

Error: $e

Your funds have not been transferred.
''';
        _isLoading = false;
      });
    }
  }

  void _handleBack() {
    setState(() {
      switch (_stage) {
        case TransferStage.riskAssessment:
        case TransferStage.compliance:
        case TransferStage.confirming:
        case TransferStage.error:
          _stage = TransferStage.input;
          _riskScore = null;
          _complianceResult = null;
          _errorMessage = null;
          _errorDetails = null;
          _isLoading = false;
          break;
        case TransferStage.signing:
          _stage = TransferStage.confirming;
          _isLoading = false;
          break;
        default:
          break;
      }
    });
  }

  void _handleNewTransfer() {
    setState(() {
      _stage = TransferStage.input;
      _intent = null;
      _intentHash = null;
      _riskScore = null;
      _complianceResult = null;
      _transactionHash = null;
      _errorMessage = null;
      _errorDetails = null;
      _isLoading = false;
      _recipientController.clear();
      _amountController.clear();
      _memoController.clear();
    });
    _captureInitialIntegrity();
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: AppTheme.errorRed,
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: AppTheme.backgroundGradient,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        children: [
          _buildSecurityIndicator(),
          _buildProgressIndicator(),
          Expanded(child: _buildStageContent()),
        ],
      ),
    );
  }

  Widget _buildSecurityIndicator() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: AppTheme.neonGreen.withOpacity(0.1),
        border: Border(
          bottom: BorderSide(
            color: AppTheme.neonGreen.withOpacity(0.3),
            width: 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.verified_user, color: AppTheme.neonGreen, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Repository-Based Protection Active',
                  style: TextStyle(
                    color: AppTheme.neonGreen,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  'Using modular risk & compliance services',
                  style: TextStyle(
                    color: AppTheme.neonGreen.withOpacity(0.7),
                    fontSize: 10,
                  ),
                ),
              ],
            ),
          ),
          if (_initialIntegrity != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.darkCard,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Text(
                '${_initialIntegrity!.stateHash.substring(0, 8)}...',
                style: TextStyle(
                  color: AppTheme.neonGreen.withOpacity(0.7),
                  fontSize: 10,
                  fontFamily: 'monospace',
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildProgressIndicator() {
    final stages = [
      ('Input', TransferStage.input),
      ('Risk', TransferStage.riskAssessment),
      ('Compliance', TransferStage.compliance),
      ('Confirm', TransferStage.confirming),
      ('Sign', TransferStage.signing),
      ('Complete', TransferStage.complete),
    ];

    final currentIndex = stages.indexWhere((s) => s.$2 == _stage);
    final isError = _stage == TransferStage.error;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: stages.asMap().entries.map((entry) {
          final index = entry.key;
          final (label, stage) = entry.value;
          final isActive = index <= currentIndex && !isError;
          final isCurrent = stage == _stage;

          return Expanded(
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    children: [
                      Container(
                        width: 24,
                        height: 24,
                        decoration: BoxDecoration(
                          color: isError && isCurrent
                              ? AppTheme.errorRed
                              : isActive
                                  ? AppTheme.neonGreen
                                  : AppTheme.darkCard,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: isError && isCurrent
                                ? AppTheme.errorRed
                                : isActive
                                    ? AppTheme.neonGreen
                                    : AppTheme.darkBorder,
                            width: 2,
                          ),
                        ),
                        child: Center(
                          child: isError && isCurrent
                              ? const Icon(Icons.error, size: 14, color: Colors.white)
                              : stage == TransferStage.complete && _stage == TransferStage.complete
                                  ? const Icon(Icons.check, size: 14, color: AppTheme.darkBg)
                                  : Text(
                                      '${index + 1}',
                                      style: TextStyle(
                                        color: isActive ? AppTheme.darkBg : AppTheme.cleanWhite,
                                        fontSize: 10,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        label,
                        style: TextStyle(
                          color: isActive ? AppTheme.cleanWhite : AppTheme.lightGrey,
                          fontSize: 9,
                          fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
                if (index < stages.length - 1)
                  Expanded(
                    child: Container(
                      height: 2,
                      color: index < currentIndex && !isError
                          ? AppTheme.neonGreen
                          : AppTheme.darkBorder,
                    ),
                  ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildStageContent() {
    switch (_stage) {
      case TransferStage.input:
        return _buildInputStage();
      case TransferStage.riskAssessment:
        return _buildRiskAssessmentStage();
      case TransferStage.compliance:
        return _buildComplianceStage();
      case TransferStage.confirming:
        return _buildConfirmingStage();
      case TransferStage.signing:
        return _buildSigningStage();
      case TransferStage.complete:
        return _buildCompleteStage();
      case TransferStage.error:
        return _buildErrorStage();
    }
  }

  Widget _buildInputStage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Recipient field
          _buildFieldLabel('Recipient Address', Icons.account_balance_wallet),
          const SizedBox(height: 8),
          TextFormField(
            controller: _recipientController,
            style: const TextStyle(color: AppTheme.cleanWhite, fontFamily: 'monospace'),
            decoration: InputDecoration(
              hintText: '0x...',
              hintStyle: TextStyle(color: AppTheme.lightGrey.withOpacity(0.5)),
              filled: true,
              fillColor: AppTheme.darkCard,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.neonGreen, width: 2),
              ),
              contentPadding: const EdgeInsets.all(16),
              suffixIcon: IconButton(
                icon: const Icon(Icons.qr_code_scanner, color: AppTheme.neonGreen),
                onPressed: () {
                  // TODO: QR scanner
                },
                tooltip: 'Scan QR Code',
              ),
            ),
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[0-9a-fA-Fx]')),
            ],
          ),
          
          const SizedBox(height: 20),
          
          // Amount field
          _buildFieldLabel('Amount (ETH)', Icons.attach_money),
          const SizedBox(height: 8),
          TextFormField(
            controller: _amountController,
            style: const TextStyle(color: AppTheme.cleanWhite, fontSize: 24, fontWeight: FontWeight.bold),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
              hintText: '0.0',
              hintStyle: TextStyle(color: AppTheme.lightGrey.withOpacity(0.5)),
              filled: true,
              fillColor: AppTheme.darkCard,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.neonGreen, width: 2),
              ),
              contentPadding: const EdgeInsets.all(16),
              suffix: const Text('ETH', style: TextStyle(color: AppTheme.neonGreen)),
            ),
            inputFormatters: [
              FilteringTextInputFormatter.allow(RegExp(r'[\d.]')),
            ],
          ),

          const SizedBox(height: 20),

          // Memo field (optional)
          _buildFieldLabel('Memo (Optional)', Icons.note),
          const SizedBox(height: 8),
          TextFormField(
            controller: _memoController,
            style: const TextStyle(color: AppTheme.cleanWhite),
            maxLines: 2,
            decoration: InputDecoration(
              hintText: 'Add a note...',
              hintStyle: TextStyle(color: AppTheme.lightGrey.withOpacity(0.5)),
              filled: true,
              fillColor: AppTheme.darkCard,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(color: AppTheme.neonGreen, width: 2),
              ),
              contentPadding: const EdgeInsets.all(16),
            ),
          ),

          const SizedBox(height: 32),

          // Submit button
          SizedBox(
            width: double.infinity,
            height: 56,
            child: ElevatedButton(
              onPressed: _handleSubmit,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.neonGreen,
                foregroundColor: AppTheme.darkBg,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                elevation: 0,
              ),
              child: const Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.security),
                  SizedBox(width: 8),
                  Text(
                    'Begin Secure Transfer',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFieldLabel(String label, IconData icon) {
    return Row(
      children: [
        Icon(icon, color: AppTheme.neonGreen, size: 18),
        const SizedBox(width: 8),
        Text(
          label,
          style: const TextStyle(
            color: AppTheme.cleanWhite,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _buildRiskAssessmentStage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 60,
            height: 60,
            child: CircularProgressIndicator(
              color: AppTheme.neonGreen,
              strokeWidth: 3,
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'Analyzing Risk Profile',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Using ML-powered risk scoring...',
            style: TextStyle(color: AppTheme.lightGrey),
          ),
          const SizedBox(height: 32),
          OutlinedButton(
            onPressed: _handleBack,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppTheme.lightGrey,
              side: BorderSide(color: AppTheme.darkBorder),
            ),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  Widget _buildComplianceStage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 60,
            height: 60,
            child: CircularProgressIndicator(
              color: AppTheme.warningOrange,
              strokeWidth: 3,
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'Compliance Check',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Verifying against policies...',
            style: TextStyle(color: AppTheme.lightGrey),
          ),
          if (_riskScore != null) ...[
            const SizedBox(height: 24),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.darkCard,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _getRiskIcon(_riskScore!.level),
                    color: _getRiskColor(_riskScore!.level),
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Risk Score: ${_riskScore!.score.toStringAsFixed(2)}',
                    style: TextStyle(
                      color: _getRiskColor(_riskScore!.level),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildConfirmingStage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Risk summary
          if (_riskScore != null) _buildRiskSummaryCard(),
          
          const SizedBox(height: 16),
          
          // Compliance summary
          if (_complianceResult != null) _buildComplianceSummaryCard(),
          
          const SizedBox(height: 20),
          
          // Transaction details
          _buildTransactionDetailsCard(),
          
          const SizedBox(height: 24),
          
          // Warning for non-low risk
          if (_riskScore?.level != RiskLevel.low) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.warningOrange.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.warningOrange.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.warning, color: AppTheme.warningOrange),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'This transaction has elevated risk. Please review carefully before proceeding.',
                      style: TextStyle(color: AppTheme.warningOrange),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
          ],
          
          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _handleBack,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.lightGrey,
                    side: BorderSide(color: AppTheme.darkBorder),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Text('Back'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 2,
                child: ElevatedButton(
                  onPressed: _handleConfirm,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.neonGreen,
                    foregroundColor: AppTheme.darkBg,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                  child: const Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.verified),
                      SizedBox(width: 8),
                      Text('Confirm & Sign', style: TextStyle(fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRiskSummaryCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _getRiskColor(_riskScore!.level).withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(_getRiskIcon(_riskScore!.level), color: _getRiskColor(_riskScore!.level)),
              const SizedBox(width: 8),
              const Text(
                'Risk Assessment',
                style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: _getRiskColor(_riskScore!.level).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  _riskScore!.level.name.toUpperCase(),
                  style: TextStyle(
                    color: _getRiskColor(_riskScore!.level),
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          LinearProgressIndicator(
            value: _riskScore!.score / 100,
            backgroundColor: AppTheme.darkBg,
            valueColor: AlwaysStoppedAnimation(_getRiskColor(_riskScore!.level)),
          ),
          const SizedBox(height: 8),
          Text(
            'Score: ${_riskScore!.score.toStringAsFixed(1)}/100',
            style: TextStyle(color: AppTheme.lightGrey, fontSize: 12),
          ),
          if (_riskScore!.factors.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: _riskScore!.factors.take(3).map((f) => Chip(
                label: Text(f, style: const TextStyle(fontSize: 10)),
                backgroundColor: AppTheme.darkBg,
                labelStyle: const TextStyle(color: AppTheme.lightGrey),
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                padding: EdgeInsets.zero,
                visualDensity: VisualDensity.compact,
              )).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildComplianceSummaryCard() {
    final isApproved = _complianceResult!.action == 'APPROVE';
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isApproved 
              ? AppTheme.neonGreen.withOpacity(0.3)
              : AppTheme.warningOrange.withOpacity(0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isApproved ? Icons.check_circle : Icons.warning,
                color: isApproved ? AppTheme.neonGreen : AppTheme.warningOrange,
              ),
              const SizedBox(width: 8),
              const Text(
                'Compliance Check',
                style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: (isApproved ? AppTheme.neonGreen : AppTheme.warningOrange).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  _complianceResult!.action,
                  style: TextStyle(
                    color: isApproved ? AppTheme.neonGreen : AppTheme.warningOrange,
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _complianceResult!.reason,
            style: TextStyle(color: AppTheme.lightGrey, fontSize: 13),
          ),
          if (_complianceResult!.warnings.isNotEmpty) ...[
            const SizedBox(height: 8),
            ...(_complianceResult!.warnings.map((w) => Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  const Icon(Icons.info_outline, size: 14, color: AppTheme.warningOrange),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(w, style: const TextStyle(color: AppTheme.warningOrange, fontSize: 12)),
                  ),
                ],
              ),
            ))),
          ],
        ],
      ),
    );
  }

  Widget _buildTransactionDetailsCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Transaction Details',
            style: TextStyle(color: AppTheme.cleanWhite, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          _buildDetailRow('To', _intent!.to, isAddress: true),
          _buildDetailRow('Amount', '${_intent!.amount} ETH'),
          if (_intent!.memo != null && _intent!.memo!.isNotEmpty)
            _buildDetailRow('Memo', _intent!.memo!),
          const Divider(color: AppTheme.darkBorder),
          _buildDetailRow('Intent Hash', _intentHash!, isHash: true),
        ],
      ),
    );
  }

  Widget _buildDetailRow(String label, String value, {bool isAddress = false, bool isHash = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(label, style: TextStyle(color: AppTheme.lightGrey)),
          ),
          Expanded(
            child: Text(
              isHash ? '${value.substring(0, 10)}...${value.substring(value.length - 8)}' : value,
              style: TextStyle(
                color: AppTheme.cleanWhite,
                fontFamily: (isAddress || isHash) ? 'monospace' : null,
                fontSize: (isAddress || isHash) ? 12 : 14,
              ),
            ),
          ),
          if (isAddress || isHash)
            IconButton(
              icon: const Icon(Icons.copy, size: 16, color: AppTheme.neonGreen),
              onPressed: () {
                Clipboard.setData(ClipboardData(text: value));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Copied to clipboard'), duration: Duration(seconds: 1)),
                );
              },
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
              tooltip: 'Copy',
            ),
        ],
      ),
    );
  }

  Widget _buildSigningStage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              shape: BoxShape.circle,
              border: Border.all(color: AppTheme.neonGreen, width: 2),
            ),
            child: SizedBox(
              width: 48,
              height: 48,
              child: CircularProgressIndicator(
                color: AppTheme.neonGreen,
                strokeWidth: 3,
              ),
            ),
          ),
          const SizedBox(height: 24),
          const Text(
            'Awaiting Signature',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Please confirm in your wallet...',
            style: TextStyle(color: AppTheme.lightGrey),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTheme.darkCard,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.lock, color: AppTheme.neonGreen, size: 16),
                const SizedBox(width: 8),
                Text(
                  'Signing intent hash, not UI display',
                  style: TextStyle(color: AppTheme.lightGrey, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCompleteStage() {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppTheme.neonGreen.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.check_circle, color: AppTheme.neonGreen, size: 64),
            ),
            const SizedBox(height: 24),
            const Text(
              'Transfer Complete!',
              style: TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${_intent!.amount} ETH sent successfully',
              style: TextStyle(color: AppTheme.lightGrey, fontSize: 16),
            ),
            const SizedBox(height: 24),
            if (_transactionHash != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppTheme.darkCard,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Column(
                  children: [
                    const Text('Transaction Hash', style: TextStyle(color: AppTheme.lightGrey)),
                    const SizedBox(height: 8),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(
                          '${_transactionHash!.substring(0, 10)}...${_transactionHash!.substring(_transactionHash!.length - 8)}',
                          style: const TextStyle(
                            color: AppTheme.cleanWhite,
                            fontFamily: 'monospace',
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.copy, size: 16, color: AppTheme.neonGreen),
                          onPressed: () {
                            Clipboard.setData(ClipboardData(text: _transactionHash!));
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Hash copied'), duration: Duration(seconds: 1)),
                            );
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: _handleNewTransfer,
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.neonGreen,
                  foregroundColor: AppTheme.darkBg,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                ),
                child: const Text('New Transfer', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorStage() {
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppTheme.errorRed.withOpacity(0.1),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.error, color: AppTheme.errorRed, size: 64),
            ),
            const SizedBox(height: 24),
            Text(
              _errorMessage ?? 'An Error Occurred',
              style: const TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.center,
            ),
            if (_errorDetails != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppTheme.darkCard,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  _errorDetails!,
                  style: TextStyle(color: AppTheme.lightGrey, fontSize: 13),
                ),
              ),
            ],
            const SizedBox(height: 32),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _handleNewTransfer,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppTheme.lightGrey,
                      side: BorderSide(color: AppTheme.darkBorder),
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: const Text('Start Over'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: _handleBack,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.neonGreen,
                      foregroundColor: AppTheme.darkBg,
                      padding: const EdgeInsets.symmetric(vertical: 16),
                    ),
                    child: const Text('Go Back'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  IconData _getRiskIcon(RiskLevel level) {
    switch (level) {
      case RiskLevel.low:
        return Icons.verified;
      case RiskLevel.medium:
        return Icons.warning_amber;
      case RiskLevel.high:
        return Icons.warning;
      case RiskLevel.critical:
        return Icons.dangerous;
    }
  }

  Color _getRiskColor(RiskLevel level) {
    switch (level) {
      case RiskLevel.low:
        return AppTheme.neonGreen;
      case RiskLevel.medium:
        return AppTheme.warningOrange;
      case RiskLevel.high:
        return Colors.orange;
      case RiskLevel.critical:
        return AppTheme.errorRed;
    }
  }
}
