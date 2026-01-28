/// Flagged Queue Page - Primary Investigation Surface
/// 
/// Per Ground Truth:
/// - Virtualized rows (10k+ safe)
/// - Sticky header
/// - Keyboard navigable (↑ ↓ Enter)
/// - Columns: TxID, Risk Class, Primary Reason, Asset, Amount, Age, CTA
/// - Click to show decision explainability modal

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/services/unified_data_service.dart';
import '../../../../core/services/action_service.dart';
import '../../../../core/services/api_service.dart';
import '../../../../shared/widgets/explainability_widget.dart';

class FlaggedQueuePage extends ConsumerStatefulWidget {
  const FlaggedQueuePage({super.key});

  @override
  ConsumerState<FlaggedQueuePage> createState() => _FlaggedQueuePageState();
}

class _FlaggedQueuePageState extends ConsumerState<FlaggedQueuePage> {
  int _selectedIndex = -1;
  String _filterRisk = 'All';
  String _sortBy = 'age';
  bool _sortAsc = false;
  bool _isLoading = true;
  bool _useDemoData = false;
  bool _isLoadingExplanation = false;

  final _dataService = UnifiedDataService();
  final _actionService = ActionService();
  final _apiService = ApiService();
  List<Map<String, dynamic>> _flags = [];

  @override
  void initState() {
    super.initState();
    _loadFlaggedQueue();
  }

  Future<void> _loadFlaggedQueue() async {
    setState(() => _isLoading = true);
    try {
      final flaggedTx = await _dataService.getFlaggedQueue();
      if (flaggedTx.isNotEmpty) {
        setState(() {
          _flags = flaggedTx.map((tx) => <String, dynamic>{
            'txId': tx.hash.isNotEmpty ? tx.hash : tx.id,
            'riskClass': tx.riskScore > 0.7 ? 'High' : tx.riskScore > 0.4 ? 'Medium' : 'Low',
            'reason': tx.flags.isNotEmpty ? tx.flags.first : 'Flagged for review',
            'asset': 'ETH',
            'amount': tx.value.toStringAsFixed(2),
            'age': _formatAge(tx.timestamp),
            'timestamp': DateTime.tryParse(tx.timestamp) ?? DateTime.now(),
            'from': tx.from,
            'to': tx.to,
            'status': tx.status,
          }).toList();
          _useDemoData = false;
        });
      } else {
        _loadDemoData();
      }
    } catch (e) {
      debugPrint('Error loading flagged queue: $e');
      _loadDemoData();
    }
    setState(() => _isLoading = false);
  }

  void _loadDemoData() {
    final risks = ['High', 'Medium', 'Low'];
    final reasons = ['Fan-Out Pattern', 'Velocity Spike', 'Layering Suspected', 'New Counterparty', 'Unusual Time', 'High Value'];
    final assets = ['ETH', 'USDT', 'USDC', 'WBTC', 'DAI'];
    setState(() {
      _flags = List.generate(50, (i) => <String, dynamic>{
        'txId': '0x${(i * 1234567890).toRadixString(16).substring(0, 8)}...${(i * 9876543210).toRadixString(16).substring(0, 4)}',
        'riskClass': risks[i % 3],
        'reason': reasons[i % reasons.length],
        'asset': assets[i % assets.length],
        'amount': (((i + 1) * 12.5) % 1000).toStringAsFixed(2),
        'age': '${(i * 7 % 180) + 1}m',
        'timestamp': DateTime.now().subtract(Duration(minutes: (i * 7 % 180) + 1)),
        'from': '0x${(i * 111).toRadixString(16).padLeft(8, '0')}...${(i * 222).toRadixString(16).padLeft(4, '0')}',
        'to': '0x${(i * 333).toRadixString(16).padLeft(8, '0')}...${(i * 444).toRadixString(16).padLeft(4, '0')}',
        'status': 'pending',
      });
      _useDemoData = true;
    });
  }

  String _formatAge(String timestamp) {
    try {
      final dt = DateTime.parse(timestamp);
      final diff = DateTime.now().difference(dt);
      if (diff.inDays > 0) return '${diff.inDays}d';
      if (diff.inHours > 0) return '${diff.inHours}h';
      return '${diff.inMinutes}m';
    } catch (_) {
      return '?m';
    }
  }

  /// Show explainability modal for a flagged transaction
  Future<void> _showExplainabilityModal(Map<String, dynamic> item) async {
    setState(() => _isLoadingExplanation = true);
    
    // Extract risk score from risk class
    double riskScore;
    switch (item['riskClass']?.toLowerCase()) {
      case 'high':
        riskScore = 0.85;
        break;
      case 'medium':
        riskScore = 0.55;
        break;
      default:
        riskScore = 0.25;
    }
    
    // Build features map from available data
    final features = <String, dynamic>{
      'amount_eth': double.tryParse(item['amount']?.toString() ?? '0') ?? 0.0,
      'tx_count_24h': 1,
      'velocity_24h': 1.0,
      'reason': item['reason'] ?? 'Unknown',
    };
    
    // Graph context (simulated for demo, would come from Memgraph in production)
    final graphContext = <String, dynamic>{
      'hops_to_sanctioned': item['riskClass'] == 'High' ? 2 : 5,
      'mixer_interaction': item['riskClass'] == 'High',
      'in_degree': 5,
      'out_degree': 3,
      'pagerank': 0.001,
      'clustering_coefficient': 0.3,
    };
    
    try {
      final explanation = await _apiService.getExplanation(
        transactionHash: item['txId'] ?? '',
        riskScore: riskScore,
        features: features,
        graphContext: graphContext,
      );
      
      setState(() => _isLoadingExplanation = false);
      
      if (!mounted) return;
      
      // Show modal with explanation
      showDialog(
        context: context,
        builder: (ctx) => _ExplainabilityModal(
          item: item,
          explanation: explanation,
          onInvestigate: () {
            Navigator.pop(ctx);
            context.go('/war-room/graph?tx=${item['txId']}');
          },
          onDismiss: () => Navigator.pop(ctx),
        ),
      );
    } catch (e) {
      setState(() => _isLoadingExplanation = false);
      debugPrint('Error fetching explanation: $e');
      
      if (!mounted) return;
      
      // Show error snackbar
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to load explanation: $e'),
          backgroundColor: AppTheme.red500,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Focus(
      autofocus: true,
      onKeyEvent: _handleKeyEvent,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header with filters
          _buildHeader(),
          
          // Table
          Expanded(
            child: _buildTable(),
          ),
        ],
      ),
    );
  }

  KeyEventResult _handleKeyEvent(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    
    if (event.logicalKey == LogicalKeyboardKey.arrowDown) {
      setState(() {
        _selectedIndex = (_selectedIndex + 1).clamp(0, _flags.length - 1);
      });
      return KeyEventResult.handled;
    } else if (event.logicalKey == LogicalKeyboardKey.arrowUp) {
      setState(() {
        _selectedIndex = (_selectedIndex - 1).clamp(0, _flags.length - 1);
      });
      return KeyEventResult.handled;
    } else if (event.logicalKey == LogicalKeyboardKey.enter && _selectedIndex >= 0) {
      final item = _flags[_selectedIndex];
      _showExplainabilityModal(item);
      return KeyEventResult.handled;
    }
    
    return KeyEventResult.ignored;
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_useDemoData)
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.amber500.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.amber500.withOpacity(0.3)),
              ),
              child: Row(
                children: [
                  Icon(Icons.info_outline, color: AppTheme.amber400, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Demo Mode: Showing sample data. Connect to backend for live flags.',
                    style: TextStyle(color: AppTheme.amber400, fontSize: 13),
                  ),
                ],
              ),
            ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Text(
                        'Flagged Queue',
                        style: TextStyle(
                          color: AppTheme.gray50,
                          fontSize: 24,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      if (_isLoading)
                        Padding(
                          padding: const EdgeInsets.only(left: 12),
                          child: SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation(AppTheme.cyan500),
                            ),
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${_flags.length} transactions pending review',
                    style: TextStyle(
                      color: AppTheme.slate400,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
              Row(
                children: [
                  // Refresh button
                  IconButton(
                    onPressed: _loadFlaggedQueue,
                    icon: Icon(Icons.refresh, color: AppTheme.slate400),
                    tooltip: 'Refresh',
                  ),
                  const SizedBox(width: 8),
                  // Risk Filter
                  _FilterDropdown(
                    label: 'Risk',
                    value: _filterRisk,
                    options: ['All', 'High', 'Medium', 'Low'],
                    onChanged: (v) => setState(() => _filterRisk = v),
                  ),
                  const SizedBox(width: 12),
                  // Sort
                  _FilterDropdown(
                    label: 'Sort',
                    value: _sortBy,
                    options: ['age', 'amount', 'risk'],
                    onChanged: (v) => setState(() => _sortBy = v),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildTable() {
    final filteredFlags = _filterRisk == 'All' 
        ? _flags 
        : _flags.where((f) => f['riskClass'] == _filterRisk).toList();

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 24),
      decoration: BoxDecoration(
        color: AppTheme.slate800,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.slate700),
      ),
      child: Column(
        children: [
          // Header row
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: AppTheme.slate900,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
            ),
            child: Row(
              children: [
                _HeaderCell('TxID', flex: 2),
                _HeaderCell('Risk', flex: 1),
                _HeaderCell('Reason', flex: 2),
                _HeaderCell('Asset', flex: 1),
                _HeaderCell('Amount', flex: 1),
                _HeaderCell('Age', flex: 1),
                const SizedBox(width: 48),
              ],
            ),
          ),
          
          // Virtualized list
          Expanded(
            child: ListView.builder(
              itemCount: filteredFlags.length,
              itemBuilder: (context, index) {
                final item = filteredFlags[index];
                final isSelected = index == _selectedIndex;
                
                return Container(
                  decoration: BoxDecoration(
                    color: isSelected ? AppTheme.indigo500.withOpacity(0.15) : null,
                    border: Border(
                      bottom: BorderSide(color: AppTheme.slate700, width: 0.5),
                    ),
                  ),
                  child: Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        setState(() => _selectedIndex = index);
                        _showExplainabilityModal(item);
                      },
                      hoverColor: AppTheme.slate700.withOpacity(0.5),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        child: Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                item['txId'],
                                style: TextStyle(
                                  color: AppTheme.gray50,
                                  fontSize: 13,
                                  fontFamily: 'JetBrains Mono',
                                ),
                              ),
                            ),
                            Expanded(
                              flex: 1,
                              child: _RiskBadge(item['riskClass']),
                            ),
                            Expanded(
                              flex: 2,
                              child: Text(
                                item['reason'],
                                style: TextStyle(
                                  color: AppTheme.slate300,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                            Expanded(
                              flex: 1,
                              child: Text(
                                item['asset'],
                                style: TextStyle(
                                  color: AppTheme.slate300,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                            Expanded(
                              flex: 1,
                              child: Text(
                                item['amount'],
                                style: TextStyle(
                                  color: AppTheme.gray50,
                                  fontSize: 13,
                                  fontFamily: 'JetBrains Mono',
                                ),
                              ),
                            ),
                            Expanded(
                              flex: 1,
                              child: Text(
                                item['age'],
                                style: TextStyle(
                                  color: AppTheme.slate400,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                            IconButton(
                              icon: Icon(Icons.arrow_forward, 
                                color: isSelected ? AppTheme.indigo300 : AppTheme.indigo400, 
                                size: 18,
                              ),
                              onPressed: () => context.go('/war-room/graph?tx=${item['txId']}'),
                              tooltip: 'Investigate',
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderCell extends StatelessWidget {
  final String label;
  final int flex;

  const _HeaderCell(this.label, {this.flex = 1});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      flex: flex,
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          color: AppTheme.slate400,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.5,
        ),
      ),
    );
  }
}

class _RiskBadge extends StatelessWidget {
  final String riskClass;

  const _RiskBadge(this.riskClass);

  @override
  Widget build(BuildContext context) {
    Color bgColor;
    Color textColor;
    
    switch (riskClass.toLowerCase()) {
      case 'high':
        bgColor = AppTheme.red500.withOpacity(0.2);
        textColor = AppTheme.red400;
        break;
      case 'medium':
        bgColor = AppTheme.amber500.withOpacity(0.2);
        textColor = AppTheme.amber400;
        break;
      default:
        bgColor = AppTheme.green500.withOpacity(0.2);
        textColor = AppTheme.green400;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        riskClass,
        style: TextStyle(
          color: textColor,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _FilterDropdown extends StatelessWidget {
  final String label;
  final String value;
  final List<String> options;
  final Function(String) onChanged;

  const _FilterDropdown({
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      decoration: BoxDecoration(
        color: AppTheme.slate800,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppTheme.slate700),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: value,
          isDense: true,
          dropdownColor: AppTheme.slate800,
          style: TextStyle(color: AppTheme.gray50, fontSize: 13),
          items: options.map((o) => DropdownMenuItem(
            value: o,
            child: Text(o),
          )).toList(),
          onChanged: (v) => onChanged(v ?? value),
        ),
      ),
    );
  }
}

/// Modal dialog showing decision explainability for a flagged transaction
class _ExplainabilityModal extends StatelessWidget {
  final Map<String, dynamic> item;
  final ExplainabilityResponse explanation;
  final VoidCallback onInvestigate;
  final VoidCallback onDismiss;

  const _ExplainabilityModal({
    required this.item,
    required this.explanation,
    required this.onInvestigate,
    required this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        width: 600,
        constraints: const BoxConstraints(maxHeight: 700),
        decoration: BoxDecoration(
          color: AppTheme.slate900,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: AppTheme.slate700),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.5),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Header
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppTheme.slate800,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
                border: Border(bottom: BorderSide(color: AppTheme.slate700)),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: _getRiskColor(explanation.riskLevel).withOpacity(0.2),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(
                      Icons.psychology,
                      color: _getRiskColor(explanation.riskLevel),
                      size: 24,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Decision Explainability',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Transaction: ${item['txId']}',
                          style: TextStyle(
                            color: AppTheme.slate400,
                            fontSize: 12,
                            fontFamily: 'JetBrains Mono',
                          ),
                        ),
                      ],
                    ),
                  ),
                  // Risk Badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: _getRiskColor(explanation.riskLevel).withOpacity(0.2),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: _getRiskColor(explanation.riskLevel).withOpacity(0.5)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.warning_amber,
                          color: _getRiskColor(explanation.riskLevel),
                          size: 16,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          '${explanation.riskLevel.toUpperCase()} RISK',
                          style: TextStyle(
                            color: _getRiskColor(explanation.riskLevel),
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  IconButton(
                    onPressed: onDismiss,
                    icon: Icon(Icons.close, color: AppTheme.slate400),
                  ),
                ],
              ),
            ),
            
            // Content
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Risk Score
                    _buildSection(
                      'Risk Score',
                      child: Row(
                        children: [
                          SizedBox(
                            width: 80,
                            height: 80,
                            child: Stack(
                              alignment: Alignment.center,
                              children: [
                                CircularProgressIndicator(
                                  value: explanation.riskScore,
                                  strokeWidth: 8,
                                  backgroundColor: AppTheme.slate700,
                                  valueColor: AlwaysStoppedAnimation(_getRiskColor(explanation.riskLevel)),
                                ),
                                Text(
                                  '${(explanation.riskScore * 100).toInt()}',
                                  style: TextStyle(
                                    color: _getRiskColor(explanation.riskLevel),
                                    fontSize: 24,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(width: 20),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Confidence: ${(explanation.confidence * 100).toInt()}%',
                                  style: TextStyle(color: AppTheme.slate300, fontSize: 14),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Model: ${explanation.modelVersion.isNotEmpty ? explanation.modelVersion : 'GraphSAGE+XGBoost'}',
                                  style: TextStyle(color: AppTheme.slate400, fontSize: 12),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                    
                    const SizedBox(height: 20),
                    
                    // Narrative
                    _buildSection(
                      'Analysis Summary',
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppTheme.slate800,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppTheme.slate700),
                        ),
                        child: Text(
                          explanation.narrative.isNotEmpty 
                              ? explanation.narrative 
                              : 'This transaction was flagged due to ${item['reason']}. The ML model detected patterns consistent with potentially suspicious activity.',
                          style: TextStyle(
                            color: AppTheme.slate200,
                            fontSize: 14,
                            height: 1.6,
                          ),
                        ),
                      ),
                    ),
                    
                    const SizedBox(height: 20),
                    
                    // Detected Patterns
                    if (explanation.patterns.isNotEmpty)
                      _buildSection(
                        'Detected Patterns',
                        child: Column(
                          children: explanation.patterns.map((p) => _PatternCard(pattern: p)).toList(),
                        ),
                      ),
                    
                    if (explanation.patterns.isNotEmpty)
                      const SizedBox(height: 20),
                    
                    // Contributing Factors
                    if (explanation.factors.isNotEmpty)
                      _buildSection(
                        'Contributing Factors (SHAP)',
                        child: Column(
                          children: explanation.factors.map((f) => _FactorBar(factor: f)).toList(),
                        ),
                      ),
                    
                    if (explanation.factors.isNotEmpty)
                      const SizedBox(height: 20),
                    
                    // Typologies
                    if (explanation.typologies.isNotEmpty)
                      _buildSection(
                        'AML Typologies',
                        child: Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: explanation.typologies.map((t) => Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: AppTheme.red500.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: AppTheme.red500.withOpacity(0.3)),
                            ),
                            child: Text(
                              t,
                              style: TextStyle(
                                color: AppTheme.red400,
                                fontSize: 12,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          )).toList(),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            
            // Footer actions
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: AppTheme.slate800,
                borderRadius: const BorderRadius.vertical(bottom: Radius.circular(16)),
                border: Border(top: BorderSide(color: AppTheme.slate700)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: onDismiss,
                    child: Text(
                      'Close',
                      style: TextStyle(color: AppTheme.slate400),
                    ),
                  ),
                  const SizedBox(width: 12),
                  ElevatedButton.icon(
                    onPressed: onInvestigate,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.indigo500,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                    ),
                    icon: const Icon(Icons.search, size: 18),
                    label: const Text('Investigate in Graph'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSection(String title, {required Widget child}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            color: AppTheme.slate400,
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
        const SizedBox(height: 12),
        child,
      ],
    );
  }

  Color _getRiskColor(String riskLevel) {
    switch (riskLevel.toLowerCase()) {
      case 'critical':
      case 'high':
        return AppTheme.red500;
      case 'medium':
        return AppTheme.amber500;
      case 'low':
        return AppTheme.green500;
      default:
        return AppTheme.slate400;
    }
  }
}

/// Card showing a detected pattern
class _PatternCard extends StatelessWidget {
  final ExplainabilityPattern pattern;

  const _PatternCard({required this.pattern});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: pattern.severityColor.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: pattern.severityColor.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 40,
            decoration: BoxDecoration(
              color: pattern.severityColor,
              borderRadius: BorderRadius.circular(4),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      pattern.name.replaceAll('_', ' ').toUpperCase(),
                      style: TextStyle(
                        color: pattern.severityColor,
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${(pattern.confidence * 100).toInt()}% confidence',
                      style: TextStyle(
                        color: AppTheme.slate400,
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  pattern.description,
                  style: TextStyle(
                    color: AppTheme.slate300,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Bar chart showing factor contribution
class _FactorBar extends StatelessWidget {
  final ExplainabilityFactor factor;

  const _FactorBar({required this.factor});

  @override
  Widget build(BuildContext context) {
    final isPositive = factor.impact > 0;
    final barColor = isPositive ? AppTheme.red400 : AppTheme.green400;
    
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          SizedBox(
            width: 140,
            child: Text(
              factor.name,
              style: TextStyle(
                color: AppTheme.slate300,
                fontSize: 12,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Stack(
              children: [
                Container(
                  height: 20,
                  decoration: BoxDecoration(
                    color: AppTheme.slate800,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                FractionallySizedBox(
                  widthFactor: factor.impact.abs().clamp(0.0, 1.0),
                  child: Container(
                    height: 20,
                    decoration: BoxDecoration(
                      color: barColor.withOpacity(0.7),
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
              '${isPositive ? '+' : ''}${(factor.impact * 100).toInt()}%',
              style: TextStyle(
                color: barColor,
                fontSize: 12,
                fontWeight: FontWeight.bold,
              ),
              textAlign: TextAlign.right,
            ),
          ),
        ],
      ),
    );
  }
}
