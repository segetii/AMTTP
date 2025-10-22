import 'package:flutter/material.dart';

class RiskLevelIndicator extends StatelessWidget {
  final double riskScore;
  final double size;
  final bool showLabel;

  const RiskLevelIndicator({
    super.key,
    required this.riskScore,
    this.size = 16,
    this.showLabel = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = _getRiskColor(riskScore);
    final label = _getRiskLabel(riskScore);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
          ),
          child: Icon(
            _getRiskIcon(riskScore),
            color: Colors.white,
            size: size * 0.6,
          ),
        ),
        if (showLabel) ...[
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w600,
              fontSize: size * 0.8,
            ),
          ),
        ],
      ],
    );
  }

  Color _getRiskColor(double score) {
    if (score < 40) return Colors.green;
    if (score < 70) return Colors.orange;
    if (score < 80) return Colors.red;
    return Colors.red.shade900;
  }

  String _getRiskLabel(double score) {
    if (score < 40) return 'Low';
    if (score < 70) return 'Medium';
    if (score < 80) return 'High';
    return 'Critical';
  }

  IconData _getRiskIcon(double score) {
    if (score < 40) return Icons.check_circle;
    if (score < 70) return Icons.warning;
    if (score < 80) return Icons.error;
    return Icons.dangerous;
  }
}
