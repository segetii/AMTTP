/// War Room Visualization Pages
/// 
/// Per Ground Truth v2.3:
/// - Velocity Heatmap: Activity intensity over time
/// - Sankey Flow: Value movement visualization
/// - ML Explainability: SHAP-based feature importance
library;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'dart:ui_web' as ui_web;
import 'dart:html' as html;
import '../../../../core/theme/app_theme.dart';
import '../../../../core/constants/app_constants.dart';
import '../../../../core/rbac/rbac_provider.dart';

// ═══════════════════════════════════════════════════════════════════════════
// VELOCITY HEATMAP PAGE
// ═══════════════════════════════════════════════════════════════════════════

class VelocityHeatmapPage extends ConsumerWidget {
  const VelocityHeatmapPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          // Header controls
          Container(
            padding: const EdgeInsets.all(16),
            color: isDark ? AppTheme.slate800 : Colors.white,
            child: Row(
              children: [
                _TimeRangeSelector(isDark: isDark),
                const SizedBox(width: 16),
                _MetricSelector(isDark: isDark),
                const Spacer(),
                IconButton.outlined(
                  onPressed: () {},
                  icon: const Icon(Icons.download),
                  tooltip: 'Export Data',
                ),
              ],
            ),
          ),
          
          // Heatmap visualization
          Expanded(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Container(
                decoration: BoxDecoration(
                  color: isDark ? AppTheme.slate800 : Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
                  ),
                ),
                child: Column(
                  children: [
                    // Title
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        children: [
                          Icon(
                            Icons.grid_4x4,
                            color: AppTheme.purple500,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            'Transaction Velocity by Hour',
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: isDark ? Colors.white : AppTheme.slate800,
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                    // Heatmap grid
                    Expanded(
                      child: _HeatmapGrid(isDark: isDark),
                    ),
                    
                    // Legend
                    _HeatmapLegend(isDark: isDark),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TimeRangeSelector extends StatelessWidget {
  final bool isDark;
  
  const _TimeRangeSelector({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate700 : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: '7d',
          items: ['24h', '7d', '30d', '90d'].map((range) {
            return DropdownMenuItem(
              value: range,
              child: Text(
                'Last $range',
                style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800),
              ),
            );
          }).toList(),
          onChanged: (value) {},
          dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
        ),
      ),
    );
  }
}

class _MetricSelector extends StatelessWidget {
  final bool isDark;
  
  const _MetricSelector({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate700 : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(8),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: 'count',
          items: [
            DropdownMenuItem(value: 'count', child: Text('TX Count', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800))),
            DropdownMenuItem(value: 'volume', child: Text('Volume', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800))),
            DropdownMenuItem(value: 'risk', child: Text('Risk Score', style: TextStyle(color: isDark ? Colors.white : AppTheme.slate800))),
          ],
          onChanged: (value) {},
          dropdownColor: isDark ? AppTheme.slate700 : Colors.white,
        ),
      ),
    );
  }
}

class _HeatmapGrid extends StatelessWidget {
  final bool isDark;
  
  const _HeatmapGrid({required this.isDark});

  @override
  Widget build(BuildContext context) {
    final days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
    final hours = List.generate(24, (i) => i);
    
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: [
          // Hour labels
          Row(
            children: [
              const SizedBox(width: 40), // Spacer for day labels
              ...hours.where((h) => h % 3 == 0).map((h) => Expanded(
                child: Text(
                  '${h.toString().padLeft(2, '0')}:00',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 10,
                    color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  ),
                ),
              )),
            ],
          ),
          const SizedBox(height: 8),
          
          // Grid rows
          ...days.asMap().entries.map((entry) {
            final dayIndex = entry.key;
            final day = entry.value;
            
            return Expanded(
              child: Row(
                children: [
                  SizedBox(
                    width: 40,
                    child: Text(
                      day,
                      style: TextStyle(
                        fontSize: 12,
                        color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                      ),
                    ),
                  ),
                  ...hours.map((h) {
                    // Generate mock intensity
                    final intensity = _getMockIntensity(dayIndex, h);
                    return Expanded(
                      child: Container(
                        margin: const EdgeInsets.all(1),
                        decoration: BoxDecoration(
                          color: _getHeatColor(intensity),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    );
                  }),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  double _getMockIntensity(int day, int hour) {
    // Simulate higher activity during business hours on weekdays
    if (day < 5 && hour >= 9 && hour <= 17) {
      return 0.6 + (hour % 3) * 0.1;
    } else if (day >= 5) {
      return 0.2 + (hour % 5) * 0.05;
    }
    return 0.1 + (hour % 7) * 0.05;
  }

  Color _getHeatColor(double intensity) {
    if (intensity < 0.2) return AppTheme.purple900.withValues(alpha: 0.2);
    if (intensity < 0.4) return AppTheme.purple700.withValues(alpha: 0.4);
    if (intensity < 0.6) return AppTheme.purple500.withValues(alpha: 0.6);
    if (intensity < 0.8) return AppTheme.purple400.withValues(alpha: 0.8);
    return AppTheme.purple300;
  }
}

class _HeatmapLegend extends StatelessWidget {
  final bool isDark;
  
  const _HeatmapLegend({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            'Low',
            style: TextStyle(
              fontSize: 12,
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
          ),
          const SizedBox(width: 8),
          Container(
            width: 200,
            height: 16,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4),
              gradient: LinearGradient(
                colors: [
                  AppTheme.purple900.withValues(alpha: 0.2),
                  AppTheme.purple700.withValues(alpha: 0.4),
                  AppTheme.purple500.withValues(alpha: 0.6),
                  AppTheme.purple400.withValues(alpha: 0.8),
                  AppTheme.purple300,
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text(
            'High',
            style: TextStyle(
              fontSize: 12,
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// SANKEY FLOW PAGE
// ═══════════════════════════════════════════════════════════════════════════

class SankeyFlowPage extends ConsumerStatefulWidget {
  const SankeyFlowPage({super.key});

  @override
  ConsumerState<SankeyFlowPage> createState() => _SankeyFlowPageState();
}

class _SankeyFlowPageState extends ConsumerState<SankeyFlowPage> {
  bool _isLoading = true;
  final String _viewId = 'sankey-iframe-${DateTime.now().millisecondsSinceEpoch}';

  @override
  void initState() {
    super.initState();
    _registerIframe();
  }

  void _registerIframe() {
    if (kIsWeb) {
      final rbacState = ref.read(rbacProvider);
      final role = rbacState.role.code;
      final sankeyUrl = '${AppConstants.nextJsUrl}/war-room/detection-studio?view=flow&embed=true&role=$role';
      
      // Register the iframe view factory for web
      ui_web.platformViewRegistry.registerViewFactory(
        _viewId,
        (int viewId) {
          final iframe = html.IFrameElement()
            ..src = sankeyUrl
            ..style.border = 'none'
            ..style.width = '100%'
            ..style.height = '100%'
            ..allow = 'fullscreen'
            ..onLoad.listen((_) {
              if (mounted) {
                setState(() => _isLoading = false);
              }
            });
          return iframe;
        },
      );
      
      // Set loading to false after a timeout as backup
      Future.delayed(const Duration(seconds: 3), () {
        if (mounted && _isLoading) {
          setState(() => _isLoading = false);
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: Column(
        children: [
          // Header
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isDark ? AppTheme.slate800 : Colors.white,
              border: Border(
                bottom: BorderSide(
                  color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
                ),
              ),
            ),
            child: Row(
              children: [
                Icon(Icons.show_chart, color: AppTheme.purple500),
                const SizedBox(width: 8),
                Text(
                  'Value Flow Analysis',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
                const Spacer(),
                if (_isLoading)
                  SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppTheme.purple500,
                    ),
                  ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: () {
                    setState(() => _isLoading = true);
                    _registerIframe();
                  },
                  icon: const Icon(Icons.refresh),
                  tooltip: 'Refresh',
                ),
              ],
            ),
          ),
          
          // Content - iframe for web
          Expanded(
            child: kIsWeb
                ? Stack(
                    children: [
                      HtmlElementView(viewType: _viewId),
                      if (_isLoading)
                        Container(
                          color: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
                          child: Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                CircularProgressIndicator(color: AppTheme.purple500),
                                const SizedBox(height: 16),
                                Text(
                                  'Loading Sankey visualization...',
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                    ],
                  )
                : _buildNativeFallback(isDark),
          ),
        ],
      ),
    );
  }

  Widget _buildNativeFallback(bool isDark) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.account_tree,
            size: 64,
            color: isDark ? AppTheme.slate600 : AppTheme.slate400,
          ),
          const SizedBox(height: 16),
          Text(
            'Sankey visualization is available on web platform',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Please use the web version for this feature',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: isDark ? AppTheme.slate500 : AppTheme.slate400,
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// ML EXPLAINABILITY PAGE
// ═══════════════════════════════════════════════════════════════════════════

class MLExplainabilityPage extends ConsumerStatefulWidget {
  const MLExplainabilityPage({super.key});

  @override
  ConsumerState<MLExplainabilityPage> createState() => _MLExplainabilityPageState();
}

class _MLExplainabilityPageState extends ConsumerState<MLExplainabilityPage> {
  bool _isLoadingPredictions = false;
  List<Map<String, dynamic>> _recentPredictions = [];
  
  @override
  void initState() {
    super.initState();
    _loadRecentPredictions();
  }
  
  Future<void> _loadRecentPredictions() async {
    setState(() => _isLoadingPredictions = true);
    
    // Simulate API call - in production this would call the explainability service
    await Future.delayed(const Duration(milliseconds: 500));
    
    setState(() {
      _recentPredictions = [
        {'txId': '0xabc...123', 'prediction': 'High Risk', 'confidence': 0.92, 'time': '2m ago'},
        {'txId': '0xdef...456', 'prediction': 'Medium Risk', 'confidence': 0.78, 'time': '5m ago'},
        {'txId': '0xghi...789', 'prediction': 'Low Risk', 'confidence': 0.95, 'time': '8m ago'},
        {'txId': '0xjkl...012', 'prediction': 'High Risk', 'confidence': 0.88, 'time': '12m ago'},
        {'txId': '0xmno...345', 'prediction': 'Low Risk', 'confidence': 0.91, 'time': '15m ago'},
      ];
      _isLoadingPredictions = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: isDark ? AppTheme.darkOpsBackground : Colors.grey.shade50,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Model overview card
            _ModelOverviewCard(isDark: isDark),
            
            const SizedBox(height: 16),
            
            // Feature importance
            _FeatureImportanceCard(isDark: isDark),
            
            const SizedBox(height: 16),
            
            // Recent predictions
            _RecentPredictionsCard(
              isDark: isDark,
              predictions: _recentPredictions,
              isLoading: _isLoadingPredictions,
              onViewAll: () => _showAllPredictions(context, isDark),
              onRefresh: _loadRecentPredictions,
            ),
          ],
        ),
      ),
    );
  }
  
  void _showAllPredictions(BuildContext context, bool isDark) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: isDark ? AppTheme.slate800 : Colors.white,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.9,
        expand: false,
        builder: (context, scrollController) => Column(
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
                  ),
                ),
              ),
              child: Row(
                children: [
                  Icon(Icons.history, color: AppTheme.purple500),
                  const SizedBox(width: 8),
                  Text(
                    'All Recent Predictions',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: isDark ? Colors.white : AppTheme.slate800,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: Icon(Icons.close, color: isDark ? Colors.white : AppTheme.slate600),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                controller: scrollController,
                padding: const EdgeInsets.all(16),
                itemCount: _recentPredictions.length,
                itemBuilder: (context, index) {
                  final pred = _recentPredictions[index];
                  return _PredictionListItem(prediction: pred, isDark: isDark);
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModelOverviewCard extends StatelessWidget {
  final bool isDark;
  
  const _ModelOverviewCard({required this.isDark});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.psychology, color: AppTheme.purple500),
              const SizedBox(width: 8),
              Text(
                'Model Overview',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: isDark ? Colors.white : AppTheme.slate800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              _MetricTile(
                label: 'Model Version',
                value: 'v2.4.1',
                isDark: isDark,
              ),
              _MetricTile(
                label: 'Accuracy',
                value: '94.2%',
                isDark: isDark,
                valueColor: AppTheme.green500,
              ),
              _MetricTile(
                label: 'Precision',
                value: '92.8%',
                isDark: isDark,
                valueColor: AppTheme.green500,
              ),
              _MetricTile(
                label: 'Recall',
                value: '89.5%',
                isDark: isDark,
                valueColor: AppTheme.amber500,
              ),
              _MetricTile(
                label: 'F1 Score',
                value: '91.1%',
                isDark: isDark,
                valueColor: AppTheme.green500,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  final String label;
  final String value;
  final bool isDark;
  final Color? valueColor;
  
  const _MetricTile({
    required this.label,
    required this.value,
    required this.isDark,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: 24,
              fontWeight: FontWeight.bold,
              color: valueColor ?? (isDark ? Colors.white : AppTheme.slate800),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: isDark ? AppTheme.slate400 : AppTheme.slate500,
            ),
          ),
        ],
      ),
    );
  }
}

class _FeatureImportanceCard extends StatelessWidget {
  final bool isDark;
  
  const _FeatureImportanceCard({required this.isDark});

  @override
  Widget build(BuildContext context) {
    final features = [
      ('Transaction Velocity', 0.85),
      ('Counterparty Risk', 0.72),
      ('Value Anomaly', 0.68),
      ('Time Pattern', 0.54),
      ('Network Position', 0.48),
      ('Historical Behavior', 0.42),
    ];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.bar_chart, color: AppTheme.purple500),
              const SizedBox(width: 8),
              Text(
                'SHAP Feature Importance',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: isDark ? Colors.white : AppTheme.slate800,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          ...features.map((f) => _FeatureBar(
            name: f.$1,
            importance: f.$2,
            isDark: isDark,
          )),
        ],
      ),
    );
  }
}

class _FeatureBar extends StatelessWidget {
  final String name;
  final double importance;
  final bool isDark;
  
  const _FeatureBar({
    required this.name,
    required this.importance,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          SizedBox(
            width: 150,
            child: Text(
              name,
              style: TextStyle(
                fontSize: 13,
                color: isDark ? AppTheme.slate300 : AppTheme.slate600,
              ),
            ),
          ),
          Expanded(
            child: Stack(
              children: [
                Container(
                  height: 24,
                  decoration: BoxDecoration(
                    color: isDark ? AppTheme.slate700 : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: importance,
                  child: Container(
                    height: 24,
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [AppTheme.purple600, AppTheme.purple400],
                      ),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          SizedBox(
            width: 50,
            child: Text(
              '${(importance * 100).toStringAsFixed(0)}%',
              textAlign: TextAlign.right,
              style: TextStyle(
                fontWeight: FontWeight.w500,
                color: isDark ? Colors.white : AppTheme.slate800,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RecentPredictionsCard extends StatelessWidget {
  final bool isDark;
  final List<Map<String, dynamic>> predictions;
  final bool isLoading;
  final VoidCallback onViewAll;
  final VoidCallback onRefresh;
  
  const _RecentPredictionsCard({
    required this.isDark,
    required this.predictions,
    required this.isLoading,
    required this.onViewAll,
    required this.onRefresh,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate800 : Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? AppTheme.slate700 : Colors.grey.shade200,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.history, color: AppTheme.purple500),
              const SizedBox(width: 8),
              Text(
                'Recent Predictions',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: isDark ? Colors.white : AppTheme.slate800,
                ),
              ),
              const Spacer(),
              IconButton(
                icon: Icon(Icons.refresh, 
                  color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  size: 20,
                ),
                onPressed: onRefresh,
              ),
              TextButton(
                onPressed: onViewAll,
                child: const Text('View All'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (isLoading)
            const Center(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: CircularProgressIndicator(),
              ),
            )
          else if (predictions.isEmpty)
            Text(
              'No recent predictions',
              style: TextStyle(
                fontSize: 13,
                color: isDark ? AppTheme.slate400 : AppTheme.slate500,
              ),
            )
          else
            ...predictions.take(3).map((pred) => _PredictionListItem(
              prediction: pred,
              isDark: isDark,
            )),
        ],
      ),
    );
  }
}

class _PredictionListItem extends StatelessWidget {
  final Map<String, dynamic> prediction;
  final bool isDark;
  
  const _PredictionListItem({
    required this.prediction,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    final riskLevel = prediction['prediction'] as String;
    final color = riskLevel.contains('High') 
        ? AppTheme.red500 
        : riskLevel.contains('Medium') 
            ? AppTheme.amber500 
            : AppTheme.green500;
    
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? AppTheme.slate700 : Colors.grey.shade50,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 40,
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  prediction['txId'] as String,
                  style: TextStyle(
                    fontWeight: FontWeight.w500,
                    color: isDark ? Colors.white : AppTheme.slate800,
                  ),
                ),
                Text(
                  '${prediction['time']}',
                  style: TextStyle(
                    fontSize: 12,
                    color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  riskLevel,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: color,
                  ),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '${((prediction['confidence'] as double) * 100).toStringAsFixed(0)}% confidence',
                style: TextStyle(
                  fontSize: 11,
                  color: isDark ? AppTheme.slate400 : AppTheme.slate500,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
