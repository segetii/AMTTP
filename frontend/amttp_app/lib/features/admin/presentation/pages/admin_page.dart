import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../shared/widgets/risk_visualizer_widget.dart';
import '../../../../shared/widgets/risk_level_indicator.dart';

class AdminPage extends ConsumerStatefulWidget {
  const AdminPage({super.key});

  @override
  ConsumerState<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends ConsumerState<AdminPage>
    with TickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 4, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AMTTP Admin Dashboard'),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabs: const [
            Tab(text: 'Overview', icon: Icon(Icons.dashboard)),
            Tab(text: 'DQN Analytics', icon: Icon(Icons.psychology)),
            Tab(text: 'Transactions', icon: Icon(Icons.list)),
            Tab(text: 'Policies', icon: Icon(Icons.admin_panel_settings)),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildOverviewTab(),
          _buildDQNAnalyticsTab(),
          _buildTransactionsTab(),
          _buildPoliciesTab(),
        ],
      ),
    );
  }

  Widget _buildOverviewTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // System Health Cards
          Row(
            children: [
              Expanded(
                  child: _buildMetricCard(
                'System Status',
                'Operational',
                Icons.check_circle,
                AppTheme.accentGreen,
                '99.9% uptime',
              )),
              const SizedBox(width: 16),
              Expanded(
                  child: _buildMetricCard(
                'DQN Model',
                'Active',
                Icons.psychology,
                AppTheme.primaryBlue,
                'F1: ${AppConstants.dqnF1Score}',
              )),
            ],
          ),
          const SizedBox(height: 16),

          Row(
            children: [
              Expanded(
                  child: _buildMetricCard(
                'Transactions',
                '2,847',
                Icons.trending_up,
                AppTheme.accentGreen,
                '+12% today',
              )),
              const SizedBox(width: 16),
              Expanded(
                  child: _buildMetricCard(
                'Fraud Blocked',
                '23',
                Icons.security,
                AppTheme.dangerRed,
                '0.8% rate',
              )),
            ],
          ),
          const SizedBox(height: 24),

          // Real-time Transaction Feed
          Text(
            'Real-time Transaction Feed',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          Container(
            height: 300,
            decoration: BoxDecoration(
              border: Border.all(color: Colors.grey[300]!),
              borderRadius: BorderRadius.circular(8),
            ),
            child: ListView.builder(
              itemCount: 10,
              itemBuilder: (context, index) =>
                  _buildRealtimeTransactionItem(index),
            ),
          ),
          const SizedBox(height: 24),

          // Risk Distribution Chart
          Text(
            'Risk Distribution (Last 24h)',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 200,
            child: PieChart(
              PieChartData(
                sections: [
                  PieChartSectionData(
                    value: 70,
                    title: 'Low Risk\n70%',
                    color: AppTheme.accentGreen,
                    radius: 60,
                  ),
                  PieChartSectionData(
                    value: 20,
                    title: 'Medium Risk\n20%',
                    color: AppTheme.warningOrange,
                    radius: 55,
                  ),
                  PieChartSectionData(
                    value: 8,
                    title: 'High Risk\n8%',
                    color: AppTheme.dangerRed,
                    radius: 50,
                  ),
                  PieChartSectionData(
                    value: 2,
                    title: 'Blocked\n2%',
                    color: Colors.grey[600]!,
                    radius: 45,
                  ),
                ],
                centerSpaceRadius: 40,
                sectionsSpace: 2,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDQNAnalyticsTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // DQN Performance Metrics
          Text(
            'DQN Model Performance',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 16),

          Row(
            children: [
              Expanded(
                  child: _buildDQNMetricCard('F1 Score', '0.669', '66.9%')),
              const SizedBox(width: 12),
              Expanded(
                  child: _buildDQNMetricCard('Precision', '0.723', '72.3%')),
              const SizedBox(width: 12),
              Expanded(child: _buildDQNMetricCard('Recall', '0.625', '62.5%')),
            ],
          ),
          const SizedBox(height: 24),

          // Feature Importance Chart
          Text(
            'Feature Importance Analysis',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 300,
            child: BarChart(
              BarChartData(
                alignment: BarChartAlignment.spaceAround,
                maxY: 1.0,
                barTouchData: BarTouchData(enabled: true),
                titlesData: FlTitlesData(
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (value, meta) {
                        const features = [
                          'Amount',
                          'Frequency',
                          'Geographic',
                          'Time',
                          'Age',
                          'Velocity',
                          'Cross-border',
                          'Deviation',
                          'Reputation'
                        ];
                        if (value.toInt() >= features.length) {
                          return const SizedBox.shrink();
                        }
                        return Transform.rotate(
                          angle: -0.5,
                          child: Text(
                            features[value.toInt()],
                            style: const TextStyle(fontSize: 10),
                          ),
                        );
                      },
                      reservedSize: 60,
                    ),
                  ),
                ),
                barGroups: List.generate(9, (index) {
                  final importance = [
                    0.85,
                    0.72,
                    0.68,
                    0.54,
                    0.49,
                    0.43,
                    0.38,
                    0.31,
                    0.27
                  ];
                  return BarChartGroupData(
                    x: index,
                    barRods: [
                      BarChartRodData(
                        toY: importance[index],
                        color: AppTheme.primaryBlue,
                        width: 16,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ],
                  );
                }),
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Model Training Progress
          Text(
            'Training Dataset Analysis',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _buildDatasetRow('Total Transactions', '28,457'),
                  _buildDatasetRow('Fraud Cases', '1,842 (6.5%)'),
                  _buildDatasetRow('Legitimate Cases', '26,615 (93.5%)'),
                  _buildDatasetRow('Training Time', '2.3 hours'),
                  _buildDatasetRow('Model Size', '15.2 MB'),
                  _buildDatasetRow('Inference Time', '<100ms'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),

          // Live DQN Performance
          Text(
            'Live Performance Monitoring',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 200,
            child: LineChart(
              LineChartData(
                gridData: const FlGridData(show: true),
                titlesData: const FlTitlesData(
                  rightTitles:
                      AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles:
                      AxisTitles(sideTitles: SideTitles(showTitles: false)),
                ),
                borderData: FlBorderData(show: true),
                lineBarsData: [
                  LineChartBarData(
                    spots: List.generate(24, (index) {
                      // Simulate hourly accuracy data
                      return FlSpot(
                          index.toDouble(), 0.65 + (index % 5) * 0.02);
                    }),
                    isCurved: true,
                    color: AppTheme.primaryBlue,
                    barWidth: 3,
                    dotData: const FlDotData(show: false),
                    belowBarData: BarAreaData(
                      show: true,
                      color: AppTheme.primaryBlue.withOpacity(0.3),
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

  Widget _buildTransactionsTab() {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Transaction Monitoring',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              Row(
                children: [
                  FilterChip(
                    label: const Text('All'),
                    selected: true,
                    onSelected: (bool value) {},
                  ),
                  const SizedBox(width: 8),
                  FilterChip(
                    label: const Text('High Risk'),
                    selected: false,
                    onSelected: (bool value) {},
                  ),
                  const SizedBox(width: 8),
                  FilterChip(
                    label: const Text('Blocked'),
                    selected: false,
                    onSelected: (bool value) {},
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          Expanded(
            child: ListView.builder(
              itemCount: 20,
              itemBuilder: (context, index) => _buildTransactionListItem(index),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPoliciesTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Policy Management',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 16),

          // Global Risk Thresholds
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Risk Thresholds',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  _buildThresholdSlider('Low Risk Threshold', 0.4),
                  _buildThresholdSlider('Medium Risk Threshold', 0.7),
                  _buildThresholdSlider('High Risk Threshold', 0.8),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Transaction Limits
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Transaction Limits',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 12),
                  _buildLimitField('Daily Limit',
                      '\$${AppConstants.defaultDailyLimit.toInt()}'),
                  _buildLimitField('Transaction Limit',
                      '\$${AppConstants.defaultTransactionLimit.toInt()}'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetricCard(
      String title, String value, IconData icon, Color color, String subtitle) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 24),
                const SizedBox(width: 8),
                Text(
                  title,
                  style: Theme.of(context).textTheme.titleSmall,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              value,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: color,
                  ),
            ),
            Text(
              subtitle,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: AppTheme.textMedium,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDQNMetricCard(String title, String value, String percentage) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            Text(
              value,
              style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: AppTheme.primaryBlue,
                  ),
            ),
            Text(
              percentage,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: AppTheme.textMedium,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRealtimeTransactionItem(int index) {
    final riskScore = 0.1 + (index * 0.08) % 0.8;
    final amount = 100 + (index * 150) % 1000;

    return ListTile(
      dense: true,
      leading: RiskLevelIndicator(riskScore: riskScore, size: 20),
      title: Text(
        '${amount.toStringAsFixed(0)} AMTTP',
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      subtitle: Text('Risk: ${(riskScore * 100).toStringAsFixed(1)}%'),
      trailing: Text(
        DateTime.now()
            .subtract(Duration(minutes: index))
            .toString()
            .substring(11, 16),
        style: Theme.of(context).textTheme.bodySmall,
      ),
    );
  }

  Widget _buildTransactionListItem(int index) {
    final riskScore = 0.05 + (index * 0.07) % 0.9;
    final amount = 50 + (index * 200) % 2000;
    final status = riskScore < 0.4
        ? 'Approved'
        : riskScore < 0.7
            ? 'Monitoring'
            : riskScore < 0.8
                ? 'Escrow'
                : 'Blocked';

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: RiskLevelIndicator(riskScore: riskScore),
        title: Text('${amount.toStringAsFixed(0)} AMTTP'),
        subtitle: Text('From: 0x1234...${(1000 + index).toString()}'),
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.getRiskColor(riskScore).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                status,
                style: TextStyle(
                  fontSize: 12,
                  color: AppTheme.getRiskColor(riskScore),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 2),
            Text(
              '${(riskScore * 100).toStringAsFixed(1)}%',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDatasetRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  Widget _buildThresholdSlider(String label, double value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label),
        Slider(
          value: value,
          onChanged: (newValue) {},
          min: 0.0,
          max: 1.0,
          divisions: 100,
          label: '${(value * 100).toStringAsFixed(0)}%',
        ),
      ],
    );
  }

  Widget _buildLimitField(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: TextFormField(
        initialValue: value,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}
