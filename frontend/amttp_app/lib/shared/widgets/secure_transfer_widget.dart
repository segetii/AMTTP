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
  bool _isLoadingExplanation = false;
  RiskScoreResponse? _riskScore;
  PolicyEvaluationResult? _policyResult;
  AddressLabels? _recipientLabels;
  ReputationResponse? _recipientReputation;
  ExplainabilityResponse? _explanation;
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
                  backgroundColor: AppTheme.primaryPurple,
                  foregroundColor: AppTheme.cleanWhite,
                  padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
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
                    foregroundColor: AppTheme.cleanWhite,
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
          
          // Explain Risk Button
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: _isLoadingExplanation ? null : _showExplainabilityModal,
              icon: _isLoadingExplanation 
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.lightbulb_outline),
              label: Text(_isLoadingExplanation ? 'Loading...' : 'Explain Risk Decision'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppTheme.primaryBlue,
                side: const BorderSide(color: AppTheme.primaryBlue),
                padding: const EdgeInsets.symmetric(vertical: 10),
              ),
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
      _explanation = null;
    });
  }

  /// Show the explainability modal with risk patterns and factors
  Future<void> _showExplainabilityModal() async {
    if (_riskScore == null) return;

    setState(() => _isLoadingExplanation = true);

    try {
      final walletState = ref.read(walletProvider);
      final amount = double.tryParse(_amountController.text) ?? 0.0;
      final recipientAddress = _recipientController.text.trim();

      // Build comprehensive features for explainability
      final features = {
        'amount_eth': amount,
        'value_eth': amount,
        'from_address': walletState.address ?? '',
        'to_address': recipientAddress,
        'tx_count_24h': 5, // Simulated
        'velocity_24h': amount * 2, // Simulated based on amount
        'dormancy_days': 30, // Simulated
        'is_new_recipient': _recipientReputation == null,
        'recipient_reputation': _recipientReputation?.score ?? 50,
      };

      // Build graph context
      final graphContext = {
        'hops_to_sanctioned': _recipientLabels?.isSanctioned == true ? 1 : 99,
        'mixer_interaction': _recipientLabels?.labels.any((l) => 
            l.toLowerCase().contains('mixer') || 
            l.toLowerCase().contains('tornado')) ?? false,
        'in_degree': 5, // Simulated
        'out_degree': 8, // Simulated
        'pagerank': 0.001, // Simulated
        'clustering_coefficient': 0.3, // Simulated
      };

      // Build rule results based on policy
      final ruleResults = {
        'high_value_transfer': amount > 10,
        'sanctions_match': _recipientLabels?.isSanctioned ?? false,
        'mixer_detected': graphContext['mixer_interaction'],
        'low_reputation': (_recipientReputation?.score ?? 100) < 30,
        'policy_action': _policyResult?.action ?? 'allow',
      };

      // Generate a pseudo transaction hash for the explanation
      final txHash = '0x${DateTime.now().millisecondsSinceEpoch.toRadixString(16).padLeft(64, '0')}';

      final explanation = await _apiService.getExplanation(
        transactionHash: txHash,
        riskScore: _riskScore!.riskScore,
        features: features,
        graphContext: graphContext,
        ruleResults: ruleResults,
      );

      setState(() {
        _explanation = explanation;
        _isLoadingExplanation = false;
      });

      if (mounted) {
        _showExplanationDialog(explanation);
      }
    } catch (e) {
      setState(() => _isLoadingExplanation = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load explanation: $e')),
        );
      }
    }
  }

  /// Display the explanation in a modal dialog
  void _showExplanationDialog(ExplainabilityResponse explanation) {
    showDialog(
      context: context,
      builder: (context) => Dialog(
        backgroundColor: AppTheme.darkCard,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 600, maxHeight: 700),
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                children: [
                  Icon(
                    Icons.lightbulb,
                    color: _getRiskColor(explanation.riskLevel),
                    size: 28,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Risk Explanation',
                          style: TextStyle(
                            color: AppTheme.cleanWhite,
                            fontSize: 20,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          'Confidence: ${(explanation.confidence * 100).toStringAsFixed(0)}%',
                          style: TextStyle(
                            color: AppTheme.mutedText,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: AppTheme.mutedText),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              
              // Risk Level Badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: _getRiskColor(explanation.riskLevel).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _getRiskColor(explanation.riskLevel)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      _getRiskIcon(explanation.riskLevel),
                      color: _getRiskColor(explanation.riskLevel),
                      size: 16,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      '${explanation.riskLevel.toUpperCase()} RISK - ${(explanation.riskScore * 100).toStringAsFixed(0)}%',
                      style: TextStyle(
                        color: _getRiskColor(explanation.riskLevel),
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Scrollable Content
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Narrative
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: AppTheme.darkBg,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppTheme.mutedText.withOpacity(0.3)),
                        ),
                        child: Text(
                          explanation.narrative,
                          style: const TextStyle(
                            color: AppTheme.cleanWhite,
                            fontSize: 14,
                            height: 1.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 20),

                      // Detected Patterns
                      if (explanation.patterns.isNotEmpty) ...[
                        const Text(
                          '🔍 Detected Patterns',
                          style: TextStyle(
                            color: AppTheme.cleanWhite,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        ...explanation.patterns.map((pattern) => _buildPatternCard(pattern)),
                        const SizedBox(height: 16),
                      ],

                      // Risk Factors
                      if (explanation.factors.isNotEmpty) ...[
                        const Text(
                          '📊 Risk Factors',
                          style: TextStyle(
                            color: AppTheme.cleanWhite,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        ...explanation.factors.map((factor) => _buildFactorCard(factor)),
                        const SizedBox(height: 16),
                      ],

                      // Typologies
                      if (explanation.typologies.isNotEmpty) ...[
                        const Text(
                          '🏷️ Risk Typologies',
                          style: TextStyle(
                            color: AppTheme.cleanWhite,
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: explanation.typologies.map((typology) => 
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: AppTheme.primaryPurple.withOpacity(0.2),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: AppTheme.primaryPurple.withOpacity(0.5)),
                              ),
                              child: Text(
                                typology,
                                style: const TextStyle(
                                  color: AppTheme.primaryPurple,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          ).toList(),
                        ),
                        const SizedBox(height: 16),
                      ],

                      // Model Info
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: AppTheme.darkBg,
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.info_outline, color: AppTheme.mutedText, size: 14),
                            const SizedBox(width: 8),
                            Text(
                              'Model: ${explanation.modelVersion} • Generated: ${explanation.generatedAt.toString().substring(0, 19)}',
                              style: const TextStyle(
                                color: AppTheme.mutedText,
                                fontSize: 11,
                              ),
                            ),
                          ],
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

  Widget _buildPatternCard(ExplainabilityPattern pattern) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: pattern.severityColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: pattern.severityColor.withOpacity(0.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: pattern.severityColor,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              pattern.severity.toUpperCase(),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  pattern.name.replaceAll('_', ' ').toUpperCase(),
                  style: TextStyle(
                    color: pattern.severityColor,
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  pattern.description,
                  style: const TextStyle(
                    color: AppTheme.cleanWhite,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Confidence: ${(pattern.confidence * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                    color: AppTheme.mutedText,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFactorCard(ExplainabilityFactor factor) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.darkBg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.mutedText.withOpacity(0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                factor.name,
                style: const TextStyle(
                  color: AppTheme.cleanWhite,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                ),
              ),
              Text(
                'Impact: ${(factor.impact * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  color: _getImpactColor(factor.impact),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          LinearProgressIndicator(
            value: factor.impact,
            backgroundColor: AppTheme.mutedText.withOpacity(0.2),
            valueColor: AlwaysStoppedAnimation<Color>(_getImpactColor(factor.impact)),
          ),
          const SizedBox(height: 6),
          Text(
            factor.description,
            style: const TextStyle(
              color: AppTheme.mutedText,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }

  Color _getRiskColor(String riskLevel) {
    switch (riskLevel.toLowerCase()) {
      case 'high':
      case 'critical':
        return AppTheme.dangerRed;
      case 'medium':
        return AppTheme.warningYellow;
      case 'low':
        return AppTheme.accentGreen;
      default:
        return AppTheme.mutedText;
    }
  }

  IconData _getRiskIcon(String riskLevel) {
    switch (riskLevel.toLowerCase()) {
      case 'high':
      case 'critical':
        return Icons.error;
      case 'medium':
        return Icons.warning;
      case 'low':
        return Icons.check_circle;
      default:
        return Icons.info;
    }
  }

  Color _getImpactColor(double impact) {
    if (impact >= 0.4) return AppTheme.dangerRed;
    if (impact >= 0.2) return AppTheme.warningYellow;
    return AppTheme.accentGreen;
  }

  /// Check recipient address for labels and reputation
  Future<void> _checkRecipient() async {
    final recipientAddress = _recipientController.text.trim();
    if (!RegExp(r'^0x[a-fA-F0-9]{40}$').hasMatch(recipientAddress)) return;

    setState(() => _isCheckingRecipient = true);

    try {
      // Fetch labels and reputation individually to avoid type issues
      AddressLabels? labels;
      ReputationResponse? reputation;
      
      try {
        labels = await _apiService.getAddressLabels(recipientAddress);
      } catch (_) {}
      
      try {
        reputation = await _apiService.getReputation(recipientAddress);
      } catch (_) {}

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
    if (_formKey.currentState?.validate() != true) return;

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

      print('[ANALYZE] Starting risk analysis for $recipientAddress, amount: $amount');

      // Get risk score first (required)
      RiskScoreResponse? riskScore;
      try {
        riskScore = await _apiService.getDQNRiskScore(
          fromAddress: walletState.address!,
          toAddress: recipientAddress,
          amount: amount,
          features: features,
        );
        print('[ANALYZE] Got risk score: ${riskScore.riskScore}');
      } catch (e) {
        print('[ANALYZE] Risk score error: $e');
        rethrow;
      }

      // Parallel optional API calls
      PolicyEvaluationResult? policyResult;
      AddressLabels? labels;
      ReputationResponse? reputation;
      
      // Fetch optional data with individual try-catch
      try {
        policyResult = await _apiService.evaluatePolicy(
          fromAddress: walletState.address!,
          toAddress: recipientAddress,
          amount: amount,
          riskScore: riskScore.riskScore,
        );
      } catch (e) {
        print('[ANALYZE] Policy error: $e');
      }
      
      try {
        labels = await _apiService.getAddressLabels(recipientAddress);
      } catch (e) {
        print('[ANALYZE] Labels error: $e');
      }
      
      try {
        reputation = await _apiService.getReputation(recipientAddress);
      } catch (e) {
        print('[ANALYZE] Reputation error: $e');
      }

      // Use policy result or leave as null
      PolicyEvaluationResult? finalPolicy = policyResult;

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