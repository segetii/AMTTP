import 'package:flutter/material.dart';
import '../../core/theme/app_theme.dart';
import '../../services/bridge/bridge.dart';

/// Analytics Hub Page
/// 
/// Main analytics page that embeds Next.js dashboards.
/// Users can:
/// - View embedded analytics (Detection Studio, Compliance, etc.)
/// - Switch between different analytics views
/// - Open any view in full-screen browser mode
/// 
/// This demonstrates the hybrid Flutter + Next.js architecture.

class AnalyticsHubPage extends StatefulWidget {
  const AnalyticsHubPage({super.key});

  @override
  State<AnalyticsHubPage> createState() => _AnalyticsHubPageState();
}

class _AnalyticsHubPageState extends State<AnalyticsHubPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final FlutterNextJSBridge _bridge = FlutterNextJSBridge();
  
  final List<_AnalyticsTab> _tabs = [
    _AnalyticsTab(
      label: 'War Room',
      icon: Icons.dashboard,
      route: '/war-room',
      description: 'Real-time monitoring & alerts',
    ),
    _AnalyticsTab(
      label: 'Detection Studio',
      icon: Icons.psychology,
      route: '/war-room/detection-studio',
      description: 'ML-powered fraud detection',
    ),
    _AnalyticsTab(
      label: 'Graph Explorer',
      icon: Icons.account_tree,
      route: '/war-room/graphs',
      description: 'Wallet relationship graphs',
    ),
    _AnalyticsTab(
      label: 'Compliance',
      icon: Icons.verified_user,
      route: '/war-room/compliance',
      description: 'Reports & audit trail',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _tabs.length, vsync: this);
    
    // Setup bridge callbacks
    _bridge.onRiskScoreUpdate = _handleRiskUpdate;
    _bridge.onAlertReceived = _handleAlert;
  }

  void _handleRiskUpdate(Map<String, dynamic> data) {
    final score = data['score'] as double?;
    final address = data['address'] as String?;
    
    if (score != null && score > 0.7) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('⚠️ High risk detected for ${address?.substring(0, 10)}...'),
          backgroundColor: Colors.red,
          action: SnackBarAction(
            label: 'View',
            textColor: Colors.white,
            onPressed: () => _bridge.showWalletGraph(address!),
          ),
        ),
      );
    }
  }

  void _handleAlert(Map<String, dynamic> data) {
    final title = data['title'] as String?;
    final message = data['message'] as String?;
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title ?? 'Alert'),
        content: Text(message ?? ''),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Dismiss'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.backgroundDarkOps,
      appBar: AppBar(
        backgroundColor: AppTheme.darkSurface,
        title: Text(
          'Analytics Hub',
          style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.bold),
        ),
        actions: [
          // Quick open full screen button
          IconButton(
            icon: Icon(Icons.open_in_new, color: AppTheme.textSecondary),
            onPressed: () => _bridge.openFullScreen(_tabs[_tabController.index].route),
            tooltip: 'Open in Browser',
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: AppTheme.primaryBlue,
          labelColor: AppTheme.textPrimary,
          unselectedLabelColor: AppTheme.textSecondary,
          tabs: _tabs.map((tab) => Tab(
            icon: Icon(tab.icon, size: 20),
            text: tab.label,
          )).toList(),
        ),
      ),
      body: Column(
        children: [
          // Tab description
          AnimatedBuilder(
            animation: _tabController,
            builder: (context, child) {
              final currentTab = _tabs[_tabController.index];
              return Container(
                padding: const EdgeInsets.all(12),
                color: AppTheme.darkSurface,
                child: Row(
                  children: [
                    Icon(currentTab.icon, color: AppTheme.primaryBlue, size: 20),
                    const SizedBox(width: 8),
                    Text(
                      currentTab.description,
                      style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                    ),
                    const Spacer(),
                    TextButton.icon(
                      onPressed: () => _bridge.openFullScreen(currentTab.route),
                      icon: const Icon(Icons.fullscreen, size: 18),
                      label: const Text('Full Screen'),
                      style: TextButton.styleFrom(
                        foregroundColor: AppTheme.primaryBlue,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                      ),
                    ),
                  ],
                ),
              );
            },
          ),
          
          // Embedded analytics views
          Expanded(
            child: TabBarView(
              controller: _tabController,
              physics: const NeverScrollableScrollPhysics(),
              children: _tabs.map((tab) => EmbeddedAnalytics(
                route: tab.route,
                showFullScreenButton: false, // We have our own header
                onRiskScoreUpdate: (score, address) {
                  debugPrint('Risk score: $score for $address');
                },
              )).toList(),
            ),
          ),
        ],
      ),
      
      // Bottom quick actions
      bottomNavigationBar: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        color: AppTheme.darkSurface,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _QuickAction(
              icon: Icons.search,
              label: 'Search Wallet',
              onTap: () => _showWalletSearch(context),
            ),
            _QuickAction(
              icon: Icons.receipt_long,
              label: 'Recent Tx',
              onTap: () => _tabController.animateTo(0),
            ),
            _QuickAction(
              icon: Icons.warning,
              label: 'Alerts',
              badge: 3,
              onTap: () => _bridge.navigateTo('/war-room/alerts'),
            ),
            _QuickAction(
              icon: Icons.download,
              label: 'Export',
              onTap: () => _tabController.animateTo(3),
            ),
          ],
        ),
      ),
    );
  }

  void _showWalletSearch(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => _WalletSearchDialog(
        onSearch: (address) {
          _bridge.showWalletGraph(address);
          Navigator.pop(context);
        },
      ),
    );
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER CLASSES
// ═══════════════════════════════════════════════════════════════════════════════

class _AnalyticsTab {
  final String label;
  final IconData icon;
  final String route;
  final String description;

  const _AnalyticsTab({
    required this.label,
    required this.icon,
    required this.route,
    required this.description,
  });
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final int? badge;

  const _QuickAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.badge,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Stack(
              clipBehavior: Clip.none,
              children: [
                Icon(icon, color: Colors.white54, size: 22),
                if (badge != null)
                  Positioned(
                    right: -8,
                    top: -4,
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: const BoxDecoration(
                        color: Colors.red,
                        shape: BoxShape.circle,
                      ),
                      child: Text(
                        badge.toString(),
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: const TextStyle(color: Colors.white54, fontSize: 11),
            ),
          ],
        ),
      ),
    );
  }
}

class _WalletSearchDialog extends StatefulWidget {
  final Function(String) onSearch;

  const _WalletSearchDialog({required this.onSearch});

  @override
  State<_WalletSearchDialog> createState() => _WalletSearchDialogState();
}

class _WalletSearchDialogState extends State<_WalletSearchDialog> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppTheme.darkSurface,
      title: Text(
        'Search Wallet',
        style: TextStyle(color: AppTheme.textPrimary),
      ),
      content: TextField(
        controller: _controller,
        style: TextStyle(color: AppTheme.textPrimary, fontFamily: 'JetBrains Mono'),
        decoration: InputDecoration(
          hintText: '0x...',
          hintStyle: TextStyle(color: AppTheme.textSecondary),
          prefixIcon: Icon(Icons.search, color: AppTheme.textSecondary),
          filled: true,
          fillColor: Colors.white.withOpacity(0.1),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(8),
            borderSide: BorderSide.none,
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: () {
            if (_controller.text.isNotEmpty) {
              widget.onSearch(_controller.text);
            }
          },
          child: const Text('Search'),
        ),
      ],
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}
