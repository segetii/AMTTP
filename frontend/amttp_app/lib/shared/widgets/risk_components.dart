import 'package:flutter/material.dart';
import '../../core/theme/design_tokens.dart';
import '../../core/theme/typography.dart';
import '../../core/theme/spacing.dart';

/// Risk score indicator with visual representation
class AppRiskScore extends StatelessWidget {
  final double score;
  final String? label;
  final bool showPercentage;
  final double size;

  const AppRiskScore({
    super.key,
    required this.score,
    this.label,
    this.showPercentage = true,
    this.size = 80,
  });

  RiskLevel get riskLevel => RiskColors.getRiskLevel(score);

  Color get riskColor => RiskColors.fromScore(score);

  String get riskLabel {
    switch (riskLevel) {
      case RiskLevel.low:
        return 'Low Risk';
      case RiskLevel.medium:
        return 'Medium Risk';
      case RiskLevel.high:
        return 'High Risk';
      case RiskLevel.critical:
        return 'Critical Risk';
    }
  }

  IconData get riskIcon {
    switch (riskLevel) {
      case RiskLevel.low:
        return Icons.check_circle_outline;
      case RiskLevel.medium:
        return Icons.info_outline;
      case RiskLevel.high:
        return Icons.warning_amber_outlined;
      case RiskLevel.critical:
        return Icons.error_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: size,
          height: size,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Background circle
              SizedBox(
                width: size,
                height: size,
                child: CircularProgressIndicator(
                  value: 1.0,
                  strokeWidth: 8,
                  backgroundColor: SemanticColors.border,
                  valueColor: AlwaysStoppedAnimation(
                    SemanticColors.border,
                  ),
                ),
              ),
              // Progress circle
              SizedBox(
                width: size,
                height: size,
                child: CircularProgressIndicator(
                  value: score / 100,
                  strokeWidth: 8,
                  backgroundColor: Colors.transparent,
                  valueColor: AlwaysStoppedAnimation(riskColor),
                ),
              ),
              // Center content
              Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (showPercentage)
                    Text(
                      '${score.toInt()}',
                      style: AppTypography.headlineMedium.copyWith(
                        color: riskColor,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  Icon(riskIcon, color: riskColor, size: 20),
                ],
              ),
            ],
          ),
        ),
        if (label != null) ...[
          Gaps.sm,
          Text(
            label!,
            style: AppTypography.labelMedium.copyWith(
              color: SemanticColors.textSecondary,
            ),
          ),
        ],
        Gaps.xs,
        Text(
          riskLabel,
          style: AppTypography.labelSmall.copyWith(
            color: riskColor,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}

/// Horizontal risk bar indicator
class AppRiskBar extends StatelessWidget {
  final double score;
  final double height;
  final bool showLabel;
  final bool animate;

  const AppRiskBar({
    super.key,
    required this.score,
    this.height = 8,
    this.showLabel = true,
    this.animate = true,
  });

  @override
  Widget build(BuildContext context) {
    final color = RiskColors.fromScore(score);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (showLabel) ...[
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Risk Score',
                style: AppTypography.labelMedium.copyWith(
                  color: SemanticColors.textSecondary,
                ),
              ),
              Text(
                '${score.toInt()}%',
                style: AppTypography.labelMedium.copyWith(
                  color: color,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          Gaps.xs,
        ],
        ClipRRect(
          borderRadius: BorderRadius.circular(height / 2),
          child: SizedBox(
            height: height,
            child: Stack(
              children: [
                // Background
                Container(
                  width: double.infinity,
                  color: SemanticColors.border,
                ),
                // Filled portion
                LayoutBuilder(
                  builder: (context, constraints) {
                    return AnimatedContainer(
                      duration: animate
                          ? const Duration(milliseconds: 500)
                          : Duration.zero,
                      width: constraints.maxWidth * (score / 100),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            color.withOpacity(0.8),
                            color,
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Risk factor breakdown item
class AppRiskFactor extends StatelessWidget {
  final String name;
  final double score;
  final double weight;
  final String? description;

  const AppRiskFactor({
    super.key,
    required this.name,
    required this.score,
    required this.weight,
    this.description,
  });

  @override
  Widget build(BuildContext context) {
    final color = RiskColors.fromScore(score);

    return Padding(
      padding: Insets.listItemPadding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  name,
                  style: AppTypography.bodyMedium.copyWith(
                    color: SemanticColors.textPrimary,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: SpacingTokens.sm,
                  vertical: SpacingTokens.xxs,
                ),
                decoration: BoxDecoration(
                  color: color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(RadiusTokens.sm),
                ),
                child: Text(
                  '${score.toInt()}%',
                  style: AppTypography.labelSmall.copyWith(
                    color: color,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ),
          if (description != null) ...[
            Gaps.xxs,
            Text(
              description!,
              style: AppTypography.bodySmall.copyWith(
                color: SemanticColors.textTertiary,
              ),
            ),
          ],
          Gaps.xs,
          Row(
            children: [
              Expanded(
                flex: 3,
                child: AppRiskBar(
                  score: score,
                  height: 4,
                  showLabel: false,
                ),
              ),
              Gaps.md,
              Text(
                'Weight: ${(weight * 100).toInt()}%',
                style: AppTypography.labelSmall.copyWith(
                  color: SemanticColors.textTertiary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Risk summary card with multiple factors
class AppRiskSummary extends StatelessWidget {
  final double overallScore;
  final List<RiskFactorData> factors;
  final VoidCallback? onViewDetails;

  const AppRiskSummary({
    super.key,
    required this.overallScore,
    required this.factors,
    this.onViewDetails,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: SemanticColors.surfaceElevated,
        borderRadius: BorderRadius.circular(RadiusTokens.lg),
        border: Border.all(color: SemanticColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: Insets.cardPadding,
            child: Row(
              children: [
                AppRiskScore(score: overallScore, size: 64),
                Gaps.lg,
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Risk Assessment',
                        style: AppTypography.titleMedium.copyWith(
                          color: SemanticColors.textPrimary,
                        ),
                      ),
                      Gaps.xs,
                      Text(
                        '${factors.length} factors analyzed',
                        style: AppTypography.bodySmall.copyWith(
                          color: SemanticColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                if (onViewDetails != null)
                  IconButton(
                    icon: const Icon(Icons.arrow_forward_ios, size: 16),
                    onPressed: onViewDetails,
                    color: SemanticColors.textSecondary,
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          ...factors.map((factor) => AppRiskFactor(
                name: factor.name,
                score: factor.score,
                weight: factor.weight,
                description: factor.description,
              )),
        ],
      ),
    );
  }
}

/// Data model for risk factors
class RiskFactorData {
  final String name;
  final double score;
  final double weight;
  final String? description;

  const RiskFactorData({
    required this.name,
    required this.score,
    required this.weight,
    this.description,
  });
}

/// Animated risk transition indicator
class AppRiskTransition extends StatelessWidget {
  final double previousScore;
  final double currentScore;
  final String? reason;

  const AppRiskTransition({
    super.key,
    required this.previousScore,
    required this.currentScore,
    this.reason,
  });

  bool get isImproved => currentScore < previousScore;
  double get change => (currentScore - previousScore).abs();

  @override
  Widget build(BuildContext context) {
    final changeColor = isImproved
        ? SemanticColors.statusSuccess
        : SemanticColors.statusError;

    return Container(
      padding: Insets.cardPadding,
      decoration: BoxDecoration(
        color: changeColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(RadiusTokens.md),
        border: Border.all(color: changeColor.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Icon(
            isImproved ? Icons.trending_down : Icons.trending_up,
            color: changeColor,
            size: 32,
          ),
          Gaps.md,
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      '${previousScore.toInt()}%',
                      style: AppTypography.bodyMedium.copyWith(
                        color: SemanticColors.textSecondary,
                        decoration: TextDecoration.lineThrough,
                      ),
                    ),
                    Gaps.sm,
                    Icon(
                      Icons.arrow_forward,
                      size: 16,
                      color: SemanticColors.textSecondary,
                    ),
                    Gaps.sm,
                    Text(
                      '${currentScore.toInt()}%',
                      style: AppTypography.titleMedium.copyWith(
                        color: RiskColors.fromScore(currentScore),
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ],
                ),
                if (reason != null) ...[
                  Gaps.xs,
                  Text(
                    reason!,
                    style: AppTypography.bodySmall.copyWith(
                      color: SemanticColors.textSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: SpacingTokens.sm,
              vertical: SpacingTokens.xs,
            ),
            decoration: BoxDecoration(
              color: changeColor,
              borderRadius: BorderRadius.circular(RadiusTokens.full),
            ),
            child: Text(
              '${isImproved ? '-' : '+'}${change.toInt()}%',
              style: AppTypography.labelSmall.copyWith(
                color: Colors.white,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
