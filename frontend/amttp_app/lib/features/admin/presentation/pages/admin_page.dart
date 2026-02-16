import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fl_chart/fl_chart.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/providers/admin_providers.dart';
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
    final systemHealthAsync = ref.watch(systemHealthProvider);
    final riskDistribution = ref.watch(riskDistributionProvider);
    final realtimeTransactions = ref.watch(realtimeTransactionsProvider);
    
    return systemHealthAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (error, _) => Center(child: Text('Error: $error')),
      data: (health) => RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(systemHealthProvider);
          ref.read(realtimeTransactionsProvider.notifier).refresh();
        },
        child: SingleChildScrollView(
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
                    health.isOperational ? 'Operational' : 'Degraded',
                    Icons.check_circle,
                    health.isOperational ? AppTheme.accentGreen : AppTheme.dangerRed,
                    '${health.uptime}% uptime',
                  )),
                  const SizedBox(width: 16),
                  Expanded(
                      child: _buildMetricCard(
                    'DQN Model',
                    health.modelStatus,
                    Icons.psychology,
                    AppTheme.primaryBlue,
                    health.modelVersion,
                  )),
                ],
              ),
              const SizedBox(height: 16),

              Row(
                children: [
                  Expanded(
                      child: _buildMetricCard(
                    'Transactions',
                    health.todayTransactions.toString(),
                    Icons.trending_up,
                    AppTheme.accentGreen,
                    '+${health.todayTransactionsChange}% today',
                  )),
                  const SizedBox(width: 16),
                  Expanded(
                      child: _buildMetricCard(
                    'Fraud Blocked',
                    health.fraudBlocked.toString(),
                    Icons.security,
                    AppTheme.dangerRed,
                    '${health.fraudRate}% rate',
                  )),
                ],
              ),
              const SizedBox(height: 16),
              
              // Compliance Status Row
              Row(
                children: [
                  Expanded(
                      child: _buildMetricCard(
                    'Pending EDD',
                    health.pendingEDDCases.toString(),
                    Icons.assignment_late,
                    health.pendingEDDCases > 0 ? AppTheme.warningOrange : AppTheme.accentGreen,
                    'Cases awaiting review',
                  )),
                  const SizedBox(width: 16),
                  Expanded(
                      child: _buildMetricCard(
                    'Alerts',
                    health.unresolvedAlerts.toString(),
                    Icons.notification_important,
                    health.unresolvedAlerts > 0 ? AppTheme.warningOrange : AppTheme.accentGreen,
                    'Unresolved monitoring alerts',
                  )),
                ],
              ),
              const SizedBox(height: 24),

              // Real-time Transaction Feed
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Real-time Transaction Feed',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  IconButton(
                    icon: const Icon(Icons.refresh),
                    onPressed: () => ref.read(realtimeTransactionsProvider.notifier).refresh(),
                    tooltip: 'Refresh',
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Container(
                height: 300,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey[300]!),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: ListView.builder(
                  itemCount: realtimeTransactions.length,
                  itemBuilder: (context, index) =>
                      _buildRealtimeTransactionItem(realtimeTransactions[index]),
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
                        value: riskDistribution.lowRiskPercent,
                        title: 'Low Risk\n${riskDistribution.lowRiskPercent.toStringAsFixed(0)}%',
                        color: AppTheme.accentGreen,
                        radius: 60,
                      ),
                      PieChartSectionData(
                        value: riskDistribution.mediumRiskPercent,
                        title: 'Medium Risk\n${riskDistribution.mediumRiskPercent.toStringAsFixed(0)}%',
                        color: AppTheme.warningOrange,
                        radius: 55,
                      ),
                      PieChartSectionData(
                        value: riskDistribution.highRiskPercent,
                        title: 'High Risk\n${riskDistribution.highRiskPercent.toStringAsFixed(0)}%',
                        color: AppTheme.dangerRed,
                        radius: 50,
                      ),
                      PieChartSectionData(
                        value: riskDistribution.blockedPercent,
                        title: 'Blocked\n${riskDistribution.blockedPercent.toStringAsFixed(0)}%',
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
        ),
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
    final transactions = ref.watch(realtimeTransactionsProvider);
    final selectedFilter = ref.watch(_transactionFilterProvider);
    
    // Filter transactions based on selected filter
    final filteredTransactions = selectedFilter == 'all'
        ? transactions
        : transactions.where((tx) => tx.status == selectedFilter).toList();
    
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
                    selected: selectedFilter == 'all',
                    onSelected: (bool value) => ref.read(_transactionFilterProvider.notifier).state = 'all',
                  ),
                  const SizedBox(width: 8),
                  FilterChip(
                    label: const Text('High Risk'),
                    selected: selectedFilter == 'escrow',
                    onSelected: (bool value) => ref.read(_transactionFilterProvider.notifier).state = 'escrow',
                  ),
                  const SizedBox(width: 8),
                  FilterChip(
                    label: const Text('Blocked'),
                    selected: selectedFilter == 'blocked',
                    onSelected: (bool value) => ref.read(_transactionFilterProvider.notifier).state = 'blocked',
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Showing ${filteredTransactions.length} transactions',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 16),
          Expanded(
            child: filteredTransactions.isEmpty
                ? const Center(child: Text('No transactions match this filter'))
                : ListView.builder(
                    itemCount: filteredTransactions.length,
                    itemBuilder: (context, index) => _buildTransactionListItem(filteredTransactions[index]),
                  ),
          ),
        ],
      ),
    );
  }

  // Transaction filter state provider
  static final _transactionFilterProvider = StateProvider<String>((ref) => 'all');

  Widget _buildTransactionListItem(RealtimeTransaction tx) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: RiskLevelIndicator(riskScore: tx.riskScore),
        title: Text('${tx.amount.toStringAsFixed(4)} ETH'),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('From: ${tx.fromAddress}'),
            Text('To: ${tx.toAddress}'),
          ],
        ),
        isThreeLine: true,
        trailing: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: AppTheme.getRiskColor(tx.riskScore).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                tx.status.toUpperCase(),
                style: TextStyle(
                  fontSize: 12,
                  color: AppTheme.getRiskColor(tx.riskScore),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(height: 2),
            Text(
              '${(tx.riskScore * 100).toStringAsFixed(1)}%',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
        onTap: () => _showTransactionDetails(tx),
      ),
    );
  }

  void _showTransactionDetails(RealtimeTransaction tx) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.6,
        minChildSize: 0.3,
        maxChildSize: 0.9,
        expand: false,
        builder: (context, scrollController) => SingleChildScrollView(
          controller: scrollController,
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Transaction Details',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  RiskLevelIndicator(riskScore: tx.riskScore),
                ],
              ),
              const SizedBox(height: 24),
              _buildDetailRow('Transaction ID', tx.txId),
              _buildDetailRow('Amount', '${tx.amount.toStringAsFixed(6)} ETH'),
              _buildDetailRow('From', tx.fromAddress),
              _buildDetailRow('To', tx.toAddress),
              _buildDetailRow('Risk Score', '${(tx.riskScore * 100).toStringAsFixed(1)}%'),
              _buildDetailRow('Status', tx.status.toUpperCase()),
              _buildDetailRow('Time', tx.timestamp.toString()),
              const SizedBox(height: 24),
              if (tx.status == 'escrow' || tx.status == 'blocked') ...[
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Transaction approved')),
                          );
                        },
                        icon: const Icon(Icons.check),
                        label: const Text('Approve'),
                        style: ElevatedButton.styleFrom(backgroundColor: AppTheme.accentGreen),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: () {
                          Navigator.pop(context);
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Transaction rejected')),
                          );
                        },
                        icon: const Icon(Icons.close),
                        label: const Text('Reject'),
                        style: ElevatedButton.styleFrom(backgroundColor: AppTheme.dangerRed),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDetailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(
              label,
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ),
          Expanded(
            child: Text(value),
          ),
        ],
      ),
    );
  }

  Widget _buildPoliciesTab() {
    final policiesAsync = ref.watch(activePoliciesProvider);
    final webhooksAsync = ref.watch(registeredWebhooksProvider);
    
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

          // Active Policies
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Active Policies',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      IconButton(
                        icon: const Icon(Icons.refresh, size: 20),
                        onPressed: () => ref.invalidate(activePoliciesProvider),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  policiesAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (e, _) => Text('Error loading policies: $e'),
                    data: (policies) => policies.isEmpty
                        ? const Text('No policies configured')
                        : Column(
                            children: policies.map((policy) => ListTile(
                              leading: Icon(
                                policy.isActive ? Icons.check_circle : Icons.cancel,
                                color: policy.isActive ? AppTheme.accentGreen : Colors.grey,
                              ),
                              title: Text(policy.name),
                              subtitle: Text(policy.description),
                              trailing: Chip(
                                label: Text(policy.category),
                                backgroundColor: AppTheme.primaryBlue.withOpacity(0.1),
                              ),
                            )).toList(),
                          ),
                  ),
                ],
              ),
            ),
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
                  _buildThresholdSlider('Low Risk Threshold', AppConstants.lowRiskThreshold),
                  _buildThresholdSlider('Medium Risk Threshold', AppConstants.mediumRiskThreshold),
                  _buildThresholdSlider('High Risk Threshold', AppConstants.highRiskThreshold),
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
          const SizedBox(height: 16),

          // Registered Webhooks
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Registered Webhooks',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      IconButton(
                        icon: const Icon(Icons.add, size: 20),
                        onPressed: () => _showAddWebhookDialog(),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  webhooksAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (e, _) => Text('Error loading webhooks: $e'),
                    data: (webhooks) => webhooks.isEmpty
                        ? const Text('No webhooks registered')
                        : Column(
                            children: webhooks.map((webhook) => ListTile(
                              leading: Icon(
                                webhook.isActive ? Icons.webhook : Icons.webhook_outlined,
                                color: webhook.isActive ? AppTheme.accentGreen : Colors.grey,
                              ),
                              title: Text(webhook.url, overflow: TextOverflow.ellipsis),
                              subtitle: Text('Events: ${webhook.events.join(", ")}'),
                              trailing: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  IconButton(
                                    icon: const Icon(Icons.play_arrow, size: 20),
                                    onPressed: () => _testWebhook(webhook.webhookId),
                                    tooltip: 'Test',
                                  ),
                                  IconButton(
                                    icon: const Icon(Icons.delete, size: 20),
                                    onPressed: () => _deleteWebhook(webhook.webhookId),
                                    tooltip: 'Delete',
                                  ),
                                ],
                              ),
                            )).toList(),
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

  void _showAddWebhookDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add Webhook'),
        content: const Text('Webhook registration coming soon'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Future<void> _testWebhook(String webhookId) async {
    try {
      final result = await testWebhook(ref, webhookId);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(result.success 
            ? 'Webhook test successful (${result.responseTimeMs}ms)'
            : 'Webhook test failed: ${result.error}'),
          backgroundColor: result.success ? AppTheme.accentGreen : AppTheme.dangerRed,
        ),
      );
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Error: $e'), backgroundColor: AppTheme.dangerRed),
      );
    }
  }

  Future<void> _deleteWebhook(String webhookId) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Webhook'),
        content: const Text('Are you sure you want to delete this webhook?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete', style: TextStyle(color: AppTheme.dangerRed)),
          ),
        ],
      ),
    );

    if (confirm == true) {
      try {
        await deleteWebhook(ref, webhookId);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Webhook deleted')),
        );
      } catch (e) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: AppTheme.dangerRed),
        );
      }
    }
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

  Widget _buildRealtimeTransactionItem(RealtimeTransaction tx) {
    return ListTile(
      dense: true,
      leading: RiskLevelIndicator(riskScore: tx.riskScore, size: 20),
      title: Text(
        '${tx.amount.toStringAsFixed(4)} ETH',
        style: const TextStyle(fontWeight: FontWeight.w600),
      ),
      subtitle: Text('${tx.fromAddress} → ${tx.toAddress}'),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: AppTheme.getRiskColor(tx.riskScore).withOpacity(0.1),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              tx.status.toUpperCase(),
              style: TextStyle(
                fontSize: 10,
                color: AppTheme.getRiskColor(tx.riskScore),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          Text(
            tx.timestamp.toString().substring(11, 16),
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
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
