import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';

class RiskVisualizerWidget extends StatelessWidget {
  final double riskScore;
  final List<double>? riskScores; // Add this parameter
  final Map<String, double>? featureContributions;

  const RiskVisualizerWidget({
    super.key,
    required this.riskScore,
    this.riskScores, // Add this parameter
    this.featureContributions,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.analytics,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 8),
                Text(
                  'DQN Risk Analysis',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const SizedBox(height: 20),

            // Risk Score Gauge
            _buildRiskGauge(context),

            const SizedBox(height: 20),

            // Risk Scores History (if provided)
            if (riskScores != null) ...[
              Text(
                'Risk Trend',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
              const SizedBox(height: 10),
              _buildRiskTrendChart(context),
              const SizedBox(height: 20),
            ],

            // Feature Contributions
            if (featureContributions != null) ...[
              Text(
                'Feature Contributions',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
              ),
              const SizedBox(height: 10),
              _buildFeatureChart(context),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildRiskGauge(BuildContext context) {
    final color = _getRiskColor(riskScore);

    return SizedBox(
      height: 200,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox(
            width: 150,
            height: 150,
            child: CircularProgressIndicator(
              value: riskScore / 100,
              strokeWidth: 12,
              backgroundColor: Colors.grey.shade300,
              valueColor: AlwaysStoppedAnimation<Color>(color),
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${riskScore.toStringAsFixed(1)}%',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: color,
                    ),
              ),
              Text(
                _getRiskLabel(riskScore),
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: color,
                      fontWeight: FontWeight.w600,
                    ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRiskTrendChart(BuildContext context) {
    if (riskScores == null || riskScores!.isEmpty) {
      return const SizedBox.shrink();
    }

    return SizedBox(
      height: 100,
      child: LineChart(
        LineChartData(
          gridData: const FlGridData(show: false),
          titlesData: const FlTitlesData(show: false),
          borderData: FlBorderData(show: false),
          lineBarsData: [
            LineChartBarData(
              spots: riskScores!.asMap().entries.map((entry) {
                return FlSpot(entry.key.toDouble(), entry.value);
              }).toList(),
              isCurved: true,
              color: Theme.of(context).colorScheme.primary,
              barWidth: 3,
              dotData: const FlDotData(show: false),
              belowBarData: BarAreaData(
                show: true,
                color: Theme.of(context).colorScheme.primary.withOpacity(0.1),
              ),
            ),
          ],
          minY: 0,
          maxY: 100,
        ),
      ),
    );
  }

  Widget _buildFeatureChart(BuildContext context) {
    if (featureContributions == null || featureContributions!.isEmpty) {
      return const SizedBox.shrink();
    }

      final sortedFeatures = List<MapEntry<String, double>>.from(featureContributions!.entries)
        ..sort((a, b) => b.value.compareTo(a.value));

    return SizedBox(
      height: 200,
      child: BarChart(
        BarChartData(
          alignment: BarChartAlignment.spaceAround,
          maxY: sortedFeatures.first.value * 1.2,
          titlesData: FlTitlesData(
            show: true,
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index >= 0 && index < sortedFeatures.length) {
                    return Padding(
                      padding: const EdgeInsets.only(top: 8.0),
                      child: Text(
                        sortedFeatures[index].key,
                        style: const TextStyle(fontSize: 10),
                        textAlign: TextAlign.center,
                      ),
                    );
                  }
                  return const Text('');
                },
              ),
            ),
            leftTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            topTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
            rightTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false),
            ),
          ),
          borderData: FlBorderData(show: false),
          barGroups: sortedFeatures.asMap().entries.map((entry) {
            return BarChartGroupData(
              x: entry.key,
              barRods: [
                BarChartRodData(
                  toY: entry.value.value,
                  color: _getFeatureColor(entry.value.value),
                  width: 16,
                  borderRadius: BorderRadius.circular(4),
                ),
              ],
            );
          }).toList(),
        ),
      ),
    );
  }

  Color _getRiskColor(double score) {
    if (score < 40) return Colors.green;
    if (score < 70) return Colors.orange;
    if (score < 80) return Colors.red;
    return Colors.red.shade900;
  }

  String _getRiskLabel(double score) {
    if (score < 40) return 'Low Risk';
    if (score < 70) return 'Medium Risk';
    if (score < 80) return 'High Risk';
    return 'Very High Risk';
  }

  Color _getFeatureColor(double contribution) {
    final normalized = contribution / 100;
    return Color.lerp(
      Colors.blue.shade100,
      Colors.blue.shade700,
      normalized,
    )!;
  }
}
