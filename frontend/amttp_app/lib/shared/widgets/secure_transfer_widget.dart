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
  RiskScoreResponse? _riskScore;
  bool _showRiskAnalysis = false;

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
                  labelText: 'Amount (AMTTP)',
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
                        '${_formatTokenAmount(walletState.balance!)} AMTTP',
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
                  icon: const Icon(Icons.send),
                  label: const Text('Execute Transfer'),
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
    });
  }

  Future<void> _analyzeRisk() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
    });

    try {
      final apiService = ApiService();
      final walletState = ref.read(walletProvider);

      if (walletState.address == null) {
        throw Exception('Wallet not connected');
      }

      // Generate features for DQN model
      final features = await _generateTransactionFeatures();

      final riskScore = await apiService.getDQNRiskScore(
        fromAddress: walletState.address!,
        toAddress: _recipientController.text,
        amount: double.parse(_amountController.text),
        features: features,
      );

      setState(() {
        _riskScore = riskScore;
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
    // This would typically gather real data about the transaction
    // For now, we'll simulate the 15 features your DQN model expects
    return {
      'transaction_amount': double.parse(_amountController.text),
      'user_frequency': 5.0, // Simulated
      'geographic_risk': 0.2, // Simulated
      'time_of_day': DateTime.now().hour.toDouble(),
      'account_age_days': 365.0, // Simulated
      'velocity_last_hour': 2.0, // Simulated
      'cross_border_indicator': 0.0, // Simulated
      'amount_deviation': 0.1, // Simulated
      'recipient_reputation': 0.8, // Simulated
      'payment_method_risk': 0.1, // Simulated
      'device_fingerprint': 0.05, // Simulated
      'behavioral_anomaly': 0.0, // Simulated
      'network_analysis': 0.3, // Simulated
      'compliance_score': 0.9, // Simulated
      'historical_disputes': 0.0, // Simulated
    };
  }

  bool _canProceedWithTransfer() {
    return _riskScore != null && _riskScore!.riskScore < AppConstants.highRiskThreshold;
  }

  Color _getTransferButtonColor() {
    if (_riskScore == null) return AppTheme.primaryBlue;
    
    final riskScore = _riskScore!.riskScore;
    if (riskScore < AppConstants.lowRiskThreshold) return AppTheme.accentGreen;
    if (riskScore < AppConstants.mediumRiskThreshold) return AppTheme.warningOrange;
    return AppTheme.dangerRed;
  }

  Future<void> _executeTransfer() async {
    // This would implement the actual transfer logic
    // For now, we'll show a success message
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Transfer initiated successfully!'),
        backgroundColor: AppTheme.accentGreen,
      ),
    );
    
    // Clear form
    _recipientController.clear();
    _amountController.clear();
    _resetRiskAnalysis();
  }

  String _formatTokenAmount(double amount) {
    // Format double amount to readable string
    return amount.toStringAsFixed(2);
  }
}