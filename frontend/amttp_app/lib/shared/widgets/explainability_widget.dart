import 'package:flutter/material.dart';
import '../../core/services/api_service.dart';
import '../../core/theme/app_theme.dart';

/// A reusable widget to display risk explainability information
/// Can be used in modals, cards, or inline
class ExplainabilityWidget extends StatelessWidget {
  final ExplainabilityResponse explanation;
  final bool compact;
  final VoidCallback? onClose;

  const ExplainabilityWidget({
    super.key,
    required this.explanation,
    this.compact = false,
    this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    if (compact) {
      return _buildCompactView(context);
    }
    return _buildFullView(context);
  }

  Widget _buildCompactView(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: _getRiskColor(explanation.riskLevel).withOpacity(0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(
                Icons.lightbulb,
                color: _getRiskColor(explanation.riskLevel),
                size: 18,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '${explanation.riskLevel.toUpperCase()} RISK',
                  style: TextStyle(
                    color: _getRiskColor(explanation.riskLevel),
                    fontWeight: FontWeight.bold,
                    fontSize: 12,
                  ),
                ),
              ),
              if (onClose != null)
                IconButton(
                  icon: const Icon(Icons.close, size: 16),
                  onPressed: onClose,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  color: AppTheme.mutedText,
                ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            explanation.narrative,
            style: const TextStyle(
              color: AppTheme.cleanWhite,
              fontSize: 12,
              height: 1.4,
            ),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
          if (explanation.patterns.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 4,
              runSpacing: 4,
              children: explanation.patterns.take(3).map((p) => _buildMiniPatternBadge(p)).toList(),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMiniPatternBadge(ExplainabilityPattern pattern) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: pattern.severityColor.withOpacity(0.2),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: pattern.severityColor.withOpacity(0.5)),
      ),
      child: Text(
        pattern.name.replaceAll('_', ' '),
        style: TextStyle(
          color: pattern.severityColor,
          fontSize: 10,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildFullView(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppTheme.darkCard,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
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
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    Text(
                      'Confidence: ${(explanation.confidence * 100).toStringAsFixed(0)}%',
                      style: const TextStyle(
                        color: AppTheme.mutedText,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              if (onClose != null)
                IconButton(
                  icon: const Icon(Icons.close, color: AppTheme.mutedText),
                  onPressed: onClose,
                ),
            ],
          ),
          const SizedBox(height: 16),

          // Risk Level Badge
          _buildRiskBadge(),
          const SizedBox(height: 16),

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

          // Patterns
          if (explanation.patterns.isNotEmpty) ...[
            _buildSectionHeader('🔍 Detected Patterns'),
            const SizedBox(height: 8),
            ...explanation.patterns.map((p) => _buildPatternCard(p)),
            const SizedBox(height: 16),
          ],

          // Factors
          if (explanation.factors.isNotEmpty) ...[
            _buildSectionHeader('📊 Risk Factors'),
            const SizedBox(height: 8),
            ...explanation.factors.map((f) => _buildFactorCard(f)),
            const SizedBox(height: 16),
          ],

          // Typologies
          if (explanation.typologies.isNotEmpty) ...[
            _buildSectionHeader('🏷️ Risk Typologies'),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: explanation.typologies.map((t) => _buildTypologyChip(t)).toList(),
            ),
            const SizedBox(height: 16),
          ],

          // Model Info
          _buildModelInfo(),
        ],
      ),
    );
  }

  Widget _buildRiskBadge() {
    return Container(
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
    );
  }

  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: const TextStyle(
        color: AppTheme.cleanWhite,
        fontSize: 16,
        fontWeight: FontWeight.bold,
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

  Widget _buildTypologyChip(String typology) {
    return Container(
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
    );
  }

  Widget _buildModelInfo() {
    return Container(
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
}

/// A button that fetches and displays explainability on tap
class ExplainRiskButton extends StatefulWidget {
  final String transactionHash;
  final double riskScore;
  final Map<String, dynamic> features;
  final Map<String, dynamic>? graphContext;
  final Map<String, dynamic>? ruleResults;
  final bool compact;

  const ExplainRiskButton({
    super.key,
    required this.transactionHash,
    required this.riskScore,
    required this.features,
    this.graphContext,
    this.ruleResults,
    this.compact = false,
  });

  @override
  State<ExplainRiskButton> createState() => _ExplainRiskButtonState();
}

class _ExplainRiskButtonState extends State<ExplainRiskButton> {
  bool _isLoading = false;
  final ApiService _apiService = ApiService();

  Future<void> _fetchAndShowExplanation() async {
    setState(() => _isLoading = true);

    try {
      final explanation = await _apiService.getExplanation(
        transactionHash: widget.transactionHash,
        riskScore: widget.riskScore,
        features: widget.features,
        graphContext: widget.graphContext,
        ruleResults: widget.ruleResults,
      );

      if (mounted) {
        showDialog(
          context: context,
          builder: (context) => Dialog(
            backgroundColor: Colors.transparent,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 600, maxHeight: 700),
              child: SingleChildScrollView(
                child: ExplainabilityWidget(
                  explanation: explanation,
                  onClose: () => Navigator.of(context).pop(),
                ),
              ),
            ),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to load explanation: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.compact) {
      return IconButton(
        onPressed: _isLoading ? null : _fetchAndShowExplanation,
        icon: _isLoading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.lightbulb_outline),
        tooltip: 'Explain Risk',
        color: AppTheme.primaryBlue,
      );
    }

    return OutlinedButton.icon(
      onPressed: _isLoading ? null : _fetchAndShowExplanation,
      icon: _isLoading
          ? const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.lightbulb_outline),
      label: Text(_isLoading ? 'Loading...' : 'Explain Risk'),
      style: OutlinedButton.styleFrom(
        foregroundColor: AppTheme.primaryBlue,
        side: const BorderSide(color: AppTheme.primaryBlue),
      ),
    );
  }
}
