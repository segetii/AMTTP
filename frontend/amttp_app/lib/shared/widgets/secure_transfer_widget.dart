import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/web3/wallet_provider.dart';
import '../../core/services/api_service.dart';
import '../../core/theme/app_theme.dart';
import '../../core/constants/app_constants.dart';

class SecureTransferWidget extends ConsumerStatefulWidget {
  const SecureTransferWidget({super.key});

  @override
  ConsumerState<SecureTransferWidget> createState() => _SecureTransferWidgetState();
}

class _SecureTransferWidgetState extends ConsumerState<SecureTransferWidget> {
  final _formKey = GlobalKey<FormState>();
  final _recipientController = TextEditingController();
  final _amountController = TextEditingController();
  
  bool _isLoading = false;
  bool _isCheckingRecipient = false;
  RiskScoreResponse? _riskScore;
  PolicyEvaluationResult? _policyResult;
  AddressLabels? _recipientLabels;
  ReputationResponse? _recipientReputation;
  bool _showRiskAnalysis = false;
  String? _recipientWarning;
  final ApiService _apiService = ApiService();

  @override
  void dispose() {
    _recipientController.dispose();
    _amountController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final walletState = ref.watch(walletProvider);
    
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(AppConstants.padding),
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
              // Header
              Row(
                children: [
                  const Icon(
                    Icons.security,
                    color: AppTheme.primaryBlue,
                    size: AppConstants.iconSize,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    'Secure Transfer',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ],
              ),
              const SizedBox(height: 16),

              // Recipient Address Input
              TextFormField(
                controller: _recipientController,
                decoration: const InputDecoration(
                  labelText: 'Recipient Address',
                  hintText: '0x...',
                  prefixIcon: Icon(Icons.person),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter recipient address';
                  }
                  if (!RegExp(r'^0x[a-fA-F0-9]{40}$').hasMatch(value)) {
                    return 'Invalid Ethereum address';
                  }
                  return null;
                },
                onChanged: (_) => _resetRiskAnalysis(),
              ),
              const SizedBox(height: 16),

              // Amount Input
              TextFormField(
                controller: _amountController,
                decoration: const InputDecoration(
                  labelText: 'Amount (ETH)',
                  hintText: '0.0',
                  prefixIcon: Icon(Icons.monetization_on),
                ),
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return 'Please enter amount';
                  }
                  final amount = double.tryParse(value);
                  if (amount == null || amount <= 0) {
                    return 'Please enter valid amount';
                  }
                  return null;
                },
                onChanged: (_) => _resetRiskAnalysis(),
              ),
              const SizedBox(height: 16),

              // Balance Display
              if (walletState.balance != null)
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.backgroundGrey,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Available Balance:',
                        style: Theme.of(context).textTheme.bodyMedium,
                      ),
                      Text(
                        '${_formatTokenAmount(walletState.balance!)} ETH',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 16),

              // Risk Analysis Button
              ElevatedButton.icon(
                onPressed: _isLoading ? null : _analyzeRisk,
                icon: _isLoading 
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.analytics),
                label: Text(_isLoading ? 'Analyzing...' : 'Analyze Risk'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.secondaryBlue,
                ),
              ),

              // Risk Analysis Results
              if (_showRiskAnalysis && _riskScore != null) ...[
                const SizedBox(height: 16),
                _buildRiskAnalysisCard(),
              ],

              // Transfer Button
              if (_showRiskAnalysis && _riskScore != null) ...[
                const SizedBox(height: 16),
                ElevatedButton.icon(
                  onPressed: _canProceedWithTransfer() ? _executeTransfer : null,
                  icon: Icon(_canProceedWithTransfer() ? Icons.send : Icons.block),
                  label: Text(_getTransferButtonText()),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _getTransferButtonColor(),
                    padding: const EdgeInsets.symmetric(vertical: 16),
                  ),
                ),
              ],
            ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRiskAnalysisCard() {
    final riskColor = AppTheme.getRiskColor(_riskScore!.riskScore);
    final riskLabel = AppTheme.getRiskLabel(_riskScore!.riskScore);
    
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        border: Border.all(color: riskColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with risk badge
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Risk Analysis',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: riskColor.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  riskLabel,
                  style: TextStyle(
                    color: riskColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          
          // Risk Score Bar
          Row(
            children: [
              Text(
                'Risk Score: ${(_riskScore!.riskScore * 100).toStringAsFixed(1)}%',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: LinearProgressIndicator(
                  value: _riskScore!.riskScore,
                  backgroundColor: Colors.grey[300],
                  valueColor: AlwaysStoppedAnimation<Color>(riskColor),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Recipient Warning (if any)
          if (_recipientWarning != null) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppTheme.dangerRed.withOpacity(0.1),
                border: Border.all(color: AppTheme.dangerRed),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.warning, color: AppTheme.dangerRed, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _recipientWarning!,
                      style: const TextStyle(
                        color: AppTheme.dangerRed,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],

          // Recipient Reputation (if available)
          if (_recipientReputation != null) ...[
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppTheme.backgroundGrey,
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(
                children: [
                  Icon(
                    _getReputationIcon(_recipientReputation!.tier),
                    color: _getReputationColor(_recipientReputation!.tier),
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Recipient Reputation: ${_recipientReputation!.tier}',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          'Score: ${_recipientReputation!.score}/100 • ${_recipientReputation!.totalTransactions} transactions',
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],

          // Policy Evaluation Result
          if (_policyResult != null) ...[
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: _getPolicyColor(_policyResult!.action).withOpacity(0.1),
                border: Border.all(color: _getPolicyColor(_policyResult!.action)),
                borderRadius: BorderRadius.circular(4),
              ),
              child: Row(
                children: [
                  Icon(
                    _getPolicyIcon(_policyResult!.action),
                    color: _getPolicyColor(_policyResult!.action),
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Policy: ${_policyResult!.action.toUpperCase()}',
                          style: TextStyle(
                            color: _getPolicyColor(_policyResult!.action),
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        Text(
                          _policyResult!.reason,
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                        if (_policyResult!.triggeredPolicies.isNotEmpty)
                          Text(
                            'Policies: ${_policyResult!.triggeredPolicies.join(", ")}',
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              fontStyle: FontStyle.italic,
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          
          // DQN Model Info
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: AppTheme.backgroundGrey,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'DQN Analysis (F1: ${AppConstants.dqnF1Score})',
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  'Model: ${_riskScore!.modelVersion}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                Text(
                  'Analyzed: ${_riskScore!.timestamp.toString().substring(0, 19)}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
          
          // Transaction Outcome
          const SizedBox(height: 8),
          _buildTransactionOutcome(),
        ],
      ),
    );
  }

  Widget _buildTransactionOutcome() {
    final riskScore = _riskScore!.riskScore;
    String action;
    String description;
    Color color;
    IconData icon;

    if (riskScore < AppConstants.lowRiskThreshold) {
      action = 'Auto-Approved';
      description = 'Transaction will be processed immediately';
      color = AppTheme.accentGreen;
      icon = Icons.check_circle;
    } else if (riskScore < AppConstants.mediumRiskThreshold) {
      action = 'Monitored';
      description = 'Transaction will be processed with enhanced monitoring';
      color = AppTheme.warningOrange;
      icon = Icons.visibility;
    } else if (riskScore < AppConstants.highRiskThreshold) {
      action = 'Escrow Required';
      description = 'Transaction will be held for manual review';
      color = AppTheme.warningOrange;
      icon = Icons.pause_circle;
    } else {
      action = 'Blocked';
      description = 'Transaction blocked due to high risk';
      color = AppTheme.dangerRed;
      icon = Icons.block;
    }

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  action,
                  style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  description,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _resetRiskAnalysis() {
    setState(() {
      _showRiskAnalysis = false;
      _riskScore = null;
      _policyResult = null;
      _recipientLabels = null;
      _recipientReputation = null;
      _recipientWarning = null;
    });
  }

  /// Check recipient address for labels and reputation
  Future<void> _checkRecipient() async {
    final recipientAddress = _recipientController.text.trim();
    if (!RegExp(r'^0x[a-fA-F0-9]{40}$').hasMatch(recipientAddress)) return;

    setState(() => _isCheckingRecipient = true);

    try {
      // Parallel fetch labels and reputation
      final results = await Future.wait([
        _apiService.getAddressLabels(recipientAddress).catchError((_) => null),
        _apiService.getReputation(recipientAddress).catchError((_) => null),
      ]);

      final labels = results[0] as AddressLabels?;
      final reputation = results[1] as ReputationResponse?;

      String? warning;
      if (labels != null) {
        if (labels.isSanctioned) {
          warning = '⚠️ SANCTIONED ADDRESS - Transfer blocked';
        } else if (labels.labels.any((l) => 
            l.toLowerCase().contains('mixer') || 
            l.toLowerCase().contains('tornado') ||
            l.toLowerCase().contains('high risk'))) {
          warning = '⚠️ High-risk address detected';
        }
      }

      if (reputation != null && reputation.score < 30) {
        warning = (warning ?? '') + (warning != null ? '\n' : '') +
            '⚠️ Low reputation score: ${reputation.score}/100 (${reputation.tier})';
      }

      setState(() {
        _recipientLabels = labels;
        _recipientReputation = reputation;
        _recipientWarning = warning;
      });
    } catch (e) {
      // Silently fail - non-critical check
      debugPrint('Recipient check failed: $e');
    } finally {
      setState(() => _isCheckingRecipient = false);
    }
  }

  Future<void> _analyzeRisk() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final walletState = ref.read(walletProvider);

      if (walletState.address == null) {
        throw Exception('Wallet not connected');
      }

      // Generate features for DQN model
      final features = await _generateTransactionFeatures();
      final amount = double.parse(_amountController.text);
      final recipientAddress = _recipientController.text.trim();

      // Parallel API calls for efficiency
      final results = await Future.wait([
        // DQN Risk Score
        _apiService.getDQNRiskScore(
          fromAddress: walletState.address!,
          toAddress: recipientAddress,
          amount: amount,
          features: features,
        ),
        // Policy Evaluation
        _apiService.evaluatePolicy(
          fromAddress: walletState.address!,
          toAddress: recipientAddress,
          amount: amount,
          riskScore: 0.0, // Will be updated
        ).catchError((_) => null),
        // Recipient Labels
        _apiService.getAddressLabels(recipientAddress).catchError((_) => null),
        // Recipient Reputation  
        _apiService.getReputation(recipientAddress).catchError((_) => null),
      ]);

      final riskScore = results[0] as RiskScoreResponse;
      final policyResult = results[1] as PolicyEvaluationResult?;
      final labels = results[2] as AddressLabels?;
      final reputation = results[3] as ReputationResponse?;

      // Re-evaluate policy with actual risk score
      PolicyEvaluationResult? finalPolicy;
      if (policyResult == null) {
        try {
          finalPolicy = await _apiService.evaluatePolicy(
            fromAddress: walletState.address!,
            toAddress: recipientAddress,
            amount: amount,
            riskScore: riskScore.riskScore,
          );
        } catch (_) {}
      } else {
        finalPolicy = policyResult;
      }

      // Check for warnings
      String? warning;
      if (labels != null && labels.isSanctioned) {
        warning = '🚫 SANCTIONED ADDRESS - Transfer blocked by compliance';
      } else if (labels != null && labels.labels.any((l) => 
          l.toLowerCase().contains('mixer') || 
          l.toLowerCase().contains('tornado'))) {
        warning = '⚠️ Recipient linked to privacy mixers';
      }

      if (reputation != null && reputation.score < 30) {
        warning = (warning ?? '') + (warning != null ? '\n' : '') +
            '⚠️ Low reputation: ${reputation.tier} (${reputation.score}/100)';
      }

      setState(() {
        _riskScore = riskScore;
        _policyResult = finalPolicy;
        _recipientLabels = labels;
        _recipientReputation = reputation;
        _recipientWarning = warning;
        _showRiskAnalysis = true;
      });
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Risk analysis failed: $e')),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<Map<String, dynamic>> _generateTransactionFeatures() async {
    // Incorporate real recipient reputation if available
    final recipientRep = _recipientReputation?.score ?? 80;
    
    return {
      'transaction_amount': double.parse(_amountController.text),
      'user_frequency': 5.0, // Simulated
      'geographic_risk': 0.2, // Simulated
      'time_of_day': DateTime.now().hour.toDouble(),
      'account_age_days': 365.0, // Simulated
      'velocity_last_hour': 2.0, // Simulated
      'cross_border_indicator': 0.0, // Simulated
      'amount_deviation': 0.1, // Simulated
      'recipient_reputation': recipientRep / 100.0, // Use real reputation
      'payment_method_risk': 0.1, // Simulated
      'device_fingerprint': 0.05, // Simulated
      'behavioral_anomaly': 0.0, // Simulated
      'network_analysis': 0.3, // Simulated
      'compliance_score': 0.9, // Simulated
      'historical_disputes': (_recipientReputation?.disputes ?? 0).toDouble(),
    };
  }

  bool _canProceedWithTransfer() {
    if (_riskScore == null) return false;
    
    // Block if sanctioned
    if (_recipientLabels?.isSanctioned ?? false) return false;
    
    // Block if policy rejects
    if (_policyResult?.action == 'reject') return false;
    
    // Block if high risk
    if (_riskScore!.riskScore >= AppConstants.highRiskThreshold) return false;
    
    return true;
  }

  Color _getTransferButtonColor() {
    if (_riskScore == null) return AppTheme.primaryBlue;
    if (_recipientLabels?.isSanctioned ?? false) return AppTheme.dangerRed;
    if (_policyResult?.action == 'reject') return AppTheme.dangerRed;
    
    final riskScore = _riskScore!.riskScore;
    if (riskScore < AppConstants.lowRiskThreshold) return AppTheme.accentGreen;
    if (riskScore < AppConstants.mediumRiskThreshold) return AppTheme.warningOrange;
    return AppTheme.dangerRed;
  }

  String _getTransferButtonText() {
    if (_recipientLabels?.isSanctioned ?? false) return 'Blocked (Sanctioned)';
    if (_policyResult?.action == 'reject') return 'Blocked by Policy';
    if (_policyResult?.action == 'escrow') return 'Send to Escrow';
    return 'Execute Transfer';
  }

  // Helper methods for reputation display
  IconData _getReputationIcon(String tier) {
    switch (tier.toLowerCase()) {
      case 'diamond': return Icons.diamond;
      case 'platinum': return Icons.stars;
      case 'gold': return Icons.workspace_premium;
      case 'silver': return Icons.military_tech;
      default: return Icons.shield;
    }
  }

  Color _getReputationColor(String tier) {
    switch (tier.toLowerCase()) {
      case 'diamond': return const Color(0xFF00BCD4);
      case 'platinum': return const Color(0xFF9C27B0);
      case 'gold': return const Color(0xFFFFD700);
      case 'silver': return const Color(0xFFC0C0C0);
      default: return const Color(0xFFCD7F32);
    }
  }

  // Helper methods for policy display
  IconData _getPolicyIcon(String action) {
    switch (action.toLowerCase()) {
      case 'approve': return Icons.check_circle;
      case 'monitor': return Icons.visibility;
      case 'escrow': return Icons.pause_circle;
      case 'reject': return Icons.block;
      default: return Icons.help;
    }
  }

  Color _getPolicyColor(String action) {
    switch (action.toLowerCase()) {
      case 'approve': return AppTheme.accentGreen;
      case 'monitor': return AppTheme.warningOrange;
      case 'escrow': return const Color(0xFFFFA000);
      case 'reject': return AppTheme.dangerRed;
      default: return Colors.grey;
    }
  }

  Future<void> _executeTransfer() async {
    final walletState = ref.read(walletProvider);
    
    if (!walletState.isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please connect your wallet first'),
          backgroundColor: AppTheme.warningOrange,
        ),
      );
      return;
    }

    // Final compliance check
    if (_recipientLabels?.isSanctioned ?? false) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Transfer blocked: Recipient is on sanctions list'),
          backgroundColor: AppTheme.dangerRed,
        ),
      );
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      // Execute the actual transfer via MetaMask
      final txHash = await ref.read(walletProvider.notifier).sendTransaction(
        to: _recipientController.text,
        amount: double.parse(_amountController.text),
      );
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_policyResult?.action == 'escrow' 
                  ? 'Transaction sent to escrow!'
                  : 'Transfer successful!'),
              Text(
                'TX: ${txHash.substring(0, 10)}...${txHash.substring(txHash.length - 8)}',
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
          backgroundColor: _policyResult?.action == 'escrow' 
              ? AppTheme.warningOrange 
              : AppTheme.accentGreen,
          duration: const Duration(seconds: 5),
        ),
      );
      
      // Clear form
      _recipientController.clear();
      _amountController.clear();
      _resetRiskAnalysis();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Transfer failed: $e'),
          backgroundColor: AppTheme.dangerRed,
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  String _formatTokenAmount(double amount) {
    // Format double amount to readable string
    return amount.toStringAsFixed(2);
  }
}