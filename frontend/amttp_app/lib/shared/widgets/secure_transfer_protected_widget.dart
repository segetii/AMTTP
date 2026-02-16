/// Secure Transfer Widget with UI Integrity Protection
/// 
/// Flutter port of SecurePayment.tsx - prevents Bybit-style attacks
/// 
/// 5-Stage Protection Flow:
/// 1. Input & Validation
/// 2. Integrity Verification
/// 3. Visual Confirmation (hash-verified data)
/// 4. Intent Signing (user signs actual data, not UI)
/// 5. Execution & Monitoring
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/security/ui_integrity_service.dart';
import '../../core/services/api_service.dart';
import '../../core/web3/wallet_provider.dart';
import '../../core/theme/app_theme.dart';

/// Transfer stage enumeration
enum TransferStage {
  input,
  verifying,
  confirming,
  signing,
  complete,
}

/// Secure Transfer Widget
/// 
/// Provides integrity-protected payment flow for mobile apps
class SecureTransferWidget extends ConsumerStatefulWidget {
  const SecureTransferWidget({super.key});

  @override
  ConsumerState<SecureTransferWidget> createState() =>
      _SecureTransferWidgetState();
}

class _SecureTransferWidgetState extends ConsumerState<SecureTransferWidget>
    with IntegrityProtectedState<SecureTransferWidget> {
  // Controllers
  final _recipientController = TextEditingController();
  final _amountController = TextEditingController();
  final _memoController = TextEditingController();

  // State
  TransferStage _stage = TransferStage.input;
  TransactionIntent? _intent;
  String? _intentHash;
  ComponentIntegrity? _initialIntegrity;
  ComplianceDecision? _complianceResult;
  String? _transactionHash;
  String? _errorMessage;
  bool _isLoading = false;

  static const String _componentId = 'SecureTransfer';
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

  /// Capture initial integrity snapshot
  void _captureInitialIntegrity() {
    _initialIntegrity = UIIntegrityService.captureComponentIntegrity(
      componentId: _componentId,
      state: _getCurrentState(),
      handlers: _handlers,
    );
  }

  /// Get current form state
  Map<String, dynamic> _getCurrentState() {
    return {
      'recipient': _recipientController.text,
      'amount': _amountController.text,
      'memo': _memoController.text,
      'stage': _stage.toString(),
    };
  }

  /// Validate current integrity
  Future<bool> _validateIntegrity() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      // Generate integrity report
      final report = UIIntegrityService.generateReport(
        componentId: _componentId,
        state: _getCurrentState(),
        handlers: _handlers,
        trustedSnapshot: _initialIntegrity,
      );

      // Check for violations
      if (report.violations.isNotEmpty) {
        final critical = report.violations
            .where((v) => v.severity == ViolationSeverity.critical);

        if (critical.isNotEmpty) {
          setState(() {
            _errorMessage =
                '🚨 SECURITY ALERT: UI manipulation detected!\n${critical.first.details}';
          });
          return false;
        }
      }

      // Verify with server
      final apiService = ApiService();
      final verificationResult =
          await apiService.verifyIntegrity(report.toJson());

      if (!verificationResult['verified']) {
        setState(() {
          _errorMessage =
              'Server integrity check failed: ${verificationResult['reason']}';
        });
        return false;
      }

      return true;
    } catch (e) {
      setState(() {
        _errorMessage = 'Integrity validation error: $e';
      });
      return false;
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// Stage 1: Handle submit from input form
  Future<void> _handleSubmit() async {
    // Validate inputs
    if (_recipientController.text.isEmpty) {
      _showError('Please enter recipient address');
      return;
    }
    if (_amountController.text.isEmpty) {
      _showError('Please enter amount');
      return;
    }

    final amount = double.tryParse(_amountController.text);
    if (amount == null || amount <= 0) {
      _showError('Please enter valid amount');
      return;
    }

    // Validate integrity
    setState(() {
      _stage = TransferStage.verifying;
    });

    if (!await _validateIntegrity()) {
      setState(() {
        _stage = TransferStage.input;
      });
      return;
    }

    // Create transaction intent
    final wallet = ref.read(walletProvider);
    if (wallet.address == null) {
      _showError('Please connect wallet');
      setState(() {
        _stage = TransferStage.input;
      });
      return;
    }

    _intent = UIIntegrityService.createTransactionIntent(
      from: wallet.address!,
      to: _recipientController.text.trim(),
      amount: _amountController.text.trim(),
      currency: 'ETH',
      memo: _memoController.text.isNotEmpty ? _memoController.text : null,
    );

    _intentHash = _intent!.getIntentHash();

    // Check compliance with integrity
    await _checkComplianceWithIntegrity();
  }

  /// Stage 2: Check compliance with integrity verification
  Future<void> _checkComplianceWithIntegrity() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final apiService = ApiService();
      final wallet = ref.read(walletProvider);

      // Generate integrity report
      final integrityReport = UIIntegrityService.generateReport(
        componentId: _componentId,
        state: _getCurrentState(),
        handlers: _handlers,
        trustedSnapshot: _initialIntegrity,
      );

      // Call orchestrator with integrity
      final result = await apiService.evaluateWithIntegrity(
        address: wallet.address!,
        amount: _amountController.text,
        destination: _recipientController.text,
        profile: 'retail_user', // Default profile
        intentHash: _intentHash!,
        integrityReport: integrityReport.toJson(),
      );

      _complianceResult = result;

      // Check if blocked
      if (result.action == 'BLOCK') {
        setState(() {
          _errorMessage =
              '❌ Transaction Blocked\n\n${result.reason}\n\nRisk Score: ${result.riskScore.toStringAsFixed(2)}';
          _stage = TransferStage.input;
        });
        return;
      }

      // Proceed to confirmation
      setState(() {
        _stage = TransferStage.confirming;
      });
    } catch (e) {
      _showError('Compliance check failed: $e');
      setState(() {
        _stage = TransferStage.input;
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// Stage 3: User confirms transaction (visual verification)
  Future<void> _handleConfirm() async {
    // Re-validate integrity before signing
    if (!await _validateIntegrity()) {
      setState(() {
        _stage = TransferStage.input;
      });
      return;
    }

    setState(() {
      _stage = TransferStage.signing;
    });

    await _executeTransaction();
  }

  /// Stage 4: Execute transaction with intent signing
  Future<void> _executeTransaction() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final walletNotifier = ref.read(walletProvider.notifier);

      // Sign transaction intent (not UI display!)
      // In production, this would use EIP-712 structured data signing
      final txHash = await walletNotifier.sendTransaction(
        to: _intent!.to,
        amount: double.parse(_intent!.amount),
        // Attach intent hash for verification
        data: _intentHash,
      );

      setState(() {
        _transactionHash = txHash;
        _stage = TransferStage.complete;
      });
    } catch (e) {
      _showError('Transaction failed: $e');
      setState(() {
        _stage = TransferStage.input;
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// Go back to previous stage
  void _handleBack() {
    setState(() {
      switch (_stage) {
        case TransferStage.verifying:
        case TransferStage.confirming:
          _stage = TransferStage.input;
          _complianceResult = null;
          break;
        case TransferStage.signing:
          _stage = TransferStage.confirming;
          break;
        default:
          break;
      }
    });
  }

  /// Cancel and reset
  void _handleCancel() {
    setState(() {
      _stage = TransferStage.input;
      _intent = null;
      _intentHash = null;
      _complianceResult = null;
      _transactionHash = null;
      _errorMessage = null;
      _recipientController.clear();
      _amountController.clear();
      _memoController.clear();
    });

    // Recapture initial integrity
    _captureInitialIntegrity();
  }

  void _showError(String message) {
    setState(() {
      _errorMessage = message;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: AppTheme.errorRed,
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
          // Security indicator
          _buildSecurityIndicator(),

          // Stage content
          Expanded(
            child: _buildStageContent(),
          ),

          // Error message
          if (_errorMessage != null) _buildErrorMessage(),
        ],
      ),
    );
  }

  /// Security indicator banner
  Widget _buildSecurityIndicator() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
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
          Icon(
            Icons.verified_user,
            color: AppTheme.neonGreen,
            size: 20,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'UI Integrity Protection Active',
              style: TextStyle(
                color: AppTheme.neonGreen,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          if (_initialIntegrity != null)
            Text(
              'Hash: ${_initialIntegrity!.stateHash.substring(0, 8)}...',
              style: TextStyle(
                color: AppTheme.neonGreen.withOpacity(0.7),
                fontSize: 10,
                fontFamily: 'monospace',
              ),
            ),
        ],
      ),
    );
  }

  /// Build content based on current stage
  Widget _buildStageContent() {
    switch (_stage) {
      case TransferStage.input:
        return _buildInputStage();
      case TransferStage.verifying:
        return _buildVerifyingStage();
      case TransferStage.confirming:
        return _buildConfirmingStage();
      case TransferStage.signing:
        return _buildSigningStage();
      case TransferStage.complete:
        return _buildCompleteStage();
    }
  }

  /// Stage 1: Input form
  Widget _buildInputStage() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Send Payment',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Protected by UI integrity verification',
            style: TextStyle(
              color: AppTheme.mutedText,
              fontSize: 14,
            ),
          ),
          const SizedBox(height: 24),

          // Recipient
          TextField(
            controller: _recipientController,
            style: TextStyle(color: AppTheme.cleanWhite),
            decoration: InputDecoration(
              labelText: 'Recipient Address',
              labelStyle: TextStyle(color: AppTheme.mutedText),
              prefixIcon: Icon(Icons.account_balance_wallet,
                  color: AppTheme.neonBlue),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.neonBlue, width: 2),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Amount
          TextField(
            controller: _amountController,
            keyboardType: TextInputType.numberWithOptions(decimal: true),
            style: TextStyle(color: AppTheme.cleanWhite),
            decoration: InputDecoration(
              labelText: 'Amount (ETH)',
              labelStyle: TextStyle(color: AppTheme.mutedText),
              prefixIcon:
                  Icon(Icons.attach_money, color: AppTheme.neonGreen),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.neonBlue, width: 2),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Memo (optional)
          TextField(
            controller: _memoController,
            style: TextStyle(color: AppTheme.cleanWhite),
            maxLines: 2,
            decoration: InputDecoration(
              labelText: 'Memo (optional)',
              labelStyle: TextStyle(color: AppTheme.mutedText),
              prefixIcon: Icon(Icons.note, color: AppTheme.mutedText),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.mutedText),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: AppTheme.neonBlue, width: 2),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Submit button
          ElevatedButton(
            onPressed: _isLoading ? null : _handleSubmit,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.neonBlue,
              foregroundColor: AppTheme.darkBg,
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
            child: _isLoading
                ? SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor:
                          AlwaysStoppedAnimation<Color>(AppTheme.darkBg),
                    ),
                  )
                : Text(
                    'Continue',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  /// Stage 2: Verifying integrity
  Widget _buildVerifyingStage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(AppTheme.neonBlue),
          ),
          const SizedBox(height: 24),
          Text(
            'Verifying UI Integrity...',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Checking for tampering',
            style: TextStyle(
              color: AppTheme.mutedText,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  /// Stage 3: Confirmation with visual verification
  Widget _buildConfirmingStage() {
    if (_intent == null) return const SizedBox.shrink();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Title
          Text(
            'Confirm Transaction',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 24,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Verify these details match what you entered',
            style: TextStyle(
              color: AppTheme.warningYellow,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 24),

          // Hash-verified transaction details
          _buildVerifiedDetail('From', _formatAddress(_intent!.from)),
          _buildVerifiedDetail('To', _formatAddress(_intent!.to)),
          _buildVerifiedDetail(
              'Amount', '${_intent!.amount} ${_intent!.currency ?? 'ETH'}'),
          if (_intent!.memo != null)
            _buildVerifiedDetail('Memo', _intent!.memo!),
          _buildVerifiedDetail(
            'Intent Hash',
            '${_intentHash!.substring(0, 16)}...${_intentHash!.substring(_intentHash!.length - 8)}',
          ),

          const SizedBox(height: 24),

          // Compliance warnings (if any)
          if (_complianceResult != null &&
              _complianceResult!.warnings.isNotEmpty) ...[
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.warningYellow.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: AppTheme.warningYellow.withOpacity(0.3),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.warning,
                          color: AppTheme.warningYellow, size: 20),
                      const SizedBox(width: 8),
                      Text(
                        'Compliance Warnings',
                        style: TextStyle(
                          color: AppTheme.warningYellow,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  ..._complianceResult!.warnings
                      .map((w) => Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Text(
                              '• $w',
                              style: TextStyle(
                                color: AppTheme.cleanWhite,
                                fontSize: 13,
                              ),
                            ),
                          ))
                      ,
                ],
              ),
            ),
            const SizedBox(height: 24),
          ],

          // Action buttons
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: _handleBack,
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppTheme.mutedText,
                    side: BorderSide(color: AppTheme.mutedText),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: Text('Back'),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 2,
                child: ElevatedButton(
                  onPressed: _isLoading ? null : _handleConfirm,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.neonGreen,
                    foregroundColor: AppTheme.darkBg,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                  child: Text(
                    'Confirm & Sign',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Build verified detail row
  Widget _buildVerifiedDetail(String label, String value) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.neonGreen.withOpacity(0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: AppTheme.neonGreen.withOpacity(0.2),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.verified, color: AppTheme.neonGreen, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    color: AppTheme.mutedText,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  value,
                  style: TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Stage 4: Signing transaction
  Widget _buildSigningStage() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(AppTheme.neonGreen),
          ),
          const SizedBox(height: 24),
          Text(
            'Signing Transaction...',
            style: TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Please approve in your wallet',
            style: TextStyle(
              color: AppTheme.mutedText,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  /// Stage 5: Transaction complete
  Widget _buildCompleteStage() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: AppTheme.neonGreen.withOpacity(0.2),
                shape: BoxShape.circle,
              ),
              child: Icon(
                Icons.check_circle,
                color: AppTheme.neonGreen,
                size: 48,
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'Transaction Submitted!',
              style: TextStyle(
                color: AppTheme.cleanWhite,
                fontSize: 24,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Your payment is being processed',
              style: TextStyle(
                color: AppTheme.mutedText,
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 24),
            if (_transactionHash != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTheme.cardBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  children: [
                    Text(
                      'Transaction Hash',
                      style: TextStyle(
                        color: AppTheme.mutedText,
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '${_transactionHash!.substring(0, 10)}...${_transactionHash!.substring(_transactionHash!.length - 8)}',
                      style: TextStyle(
                        color: AppTheme.neonBlue,
                        fontSize: 14,
                        fontFamily: 'monospace',
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
            ElevatedButton(
              onPressed: _handleCancel,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.neonBlue,
                foregroundColor: AppTheme.darkBg,
                padding:
                    const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              child: Text(
                'New Transfer',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Error message display
  Widget _buildErrorMessage() {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.errorRed.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: AppTheme.errorRed.withOpacity(0.3),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.error, color: AppTheme.errorRed, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              _errorMessage!,
              style: TextStyle(
                color: AppTheme.errorRed,
                fontSize: 13,
              ),
            ),
          ),
          IconButton(
            icon: Icon(Icons.close, color: AppTheme.errorRed, size: 20),
            onPressed: () {
              setState(() {
                _errorMessage = null;
              });
            },
          ),
        ],
      ),
    );
  }

  String _formatAddress(String address) {
    if (address.length <= 10) return address;
    return '${address.substring(0, 6)}...${address.substring(address.length - 4)}';
  }
}
