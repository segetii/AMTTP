import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'dart:ui_web' as ui_web;
import 'dart:html' as html;
import '../../core/theme/app_theme.dart';
import 'flutter_nextjs_bridge.dart';

/// Embedded Analytics Widget
/// 
/// Displays Next.js analytics dashboard inside Flutter app.
/// Supports:
/// - Embedded mode (inside Flutter screen)
/// - Full-screen mode (opens in browser)
/// - Route-specific loading
/// - Session synchronization via bridge

class EmbeddedAnalytics extends StatefulWidget {
  /// The Next.js route to display (e.g., '/war-room', '/detection-studio')
  final String route;
  
  /// Whether to show the "Open Full Screen" button
  final bool showFullScreenButton;
  
  /// Custom height (null = expand to fill available space)
  final double? height;
  
  /// Callback when a transaction is selected in the analytics view
  final Function(String txHash)? onTransactionSelected;
  
  /// Callback when risk score is updated
  final Function(double score, String address)? onRiskScoreUpdate;

  const EmbeddedAnalytics({
    super.key,
    this.route = '/war-room',
    this.showFullScreenButton = true,
    this.height,
    this.onTransactionSelected,
    this.onRiskScoreUpdate,
  });

  @override
  State<EmbeddedAnalytics> createState() => _EmbeddedAnalyticsState();
}

class _EmbeddedAnalyticsState extends State<EmbeddedAnalytics> {
  final FlutterNextJSBridge _bridge = FlutterNextJSBridge();
  bool _isLoading = true;
  String? _error;
  late final String _viewId;
  html.IFrameElement? _iframe;

  @override
  void initState() {
    super.initState();
    _viewId = 'embedded-analytics-${DateTime.now().millisecondsSinceEpoch}';
    _initializeWebView();
  }

  void _initializeWebView() {
    if (kIsWeb) {
      final url = _bridge.getEmbeddedUrl(widget.route);
      
      ui_web.platformViewRegistry.registerViewFactory(
        _viewId,
        (int viewId) {
          _iframe = html.IFrameElement()
            ..src = url
            ..style.border = 'none'
            ..style.width = '100%'
            ..style.height = '100%'
            ..allow = 'fullscreen'
            ..onLoad.listen((_) {
              if (mounted) {
                setState(() => _isLoading = false);
              }
            })
            ..onError.listen((_) {
              if (mounted) {
                setState(() {
                  _isLoading = false;
                  _error = 'Failed to load analytics';
                });
              }
            });
          return _iframe!;
        },
      );
      
      // Timeout fallback
      Future.delayed(const Duration(seconds: 5), () {
        if (mounted && _isLoading) {
          setState(() => _isLoading = false);
        }
      });
    }
    
    // Setup callbacks
    _bridge.onRiskScoreUpdate = (data) {
      widget.onRiskScoreUpdate?.call(
        (data['score'] as num?)?.toDouble() ?? 0.0,
        data['address'] as String? ?? '',
      );
    };
  }

  void _reloadIframe() {
    if (_iframe != null) {
      final url = _bridge.getEmbeddedUrl(widget.route);
      _iframe!.src = url;
      setState(() {
        _isLoading = true;
        _error = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: widget.height,
      decoration: BoxDecoration(
        color: AppTheme.backgroundDarkOps,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white10),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: Column(
          children: [
            // Header with full-screen button
            if (widget.showFullScreenButton)
              _buildHeader(),
            
            // WebView content - using iframe for web
            Expanded(
              child: kIsWeb 
                  ? Stack(
                      children: [
                        HtmlElementView(viewType: _viewId),
                        if (_isLoading) _buildLoadingOverlay(),
                        if (_error != null) _buildErrorOverlay(),
                      ],
                    )
                  : _buildNonWebFallback(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: AppTheme.darkSurface,
        border: const Border(bottom: BorderSide(color: Colors.white10)),
      ),
      child: Row(
        children: [
          // Route indicator
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: AppTheme.primaryBlue.withOpacity(0.2),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.analytics, size: 14, color: AppTheme.primaryBlue),
                const SizedBox(width: 4),
                Text(
                  _getRouteLabel(widget.route),
                  style: TextStyle(
                    color: AppTheme.primaryBlue,
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          
          const Spacer(),
          
          // Refresh button
          IconButton(
            onPressed: _reloadIframe,
            icon: const Icon(Icons.refresh, size: 18),
            color: Colors.white54,
            tooltip: 'Refresh',
          ),
          
          // Full screen button
          TextButton.icon(
            onPressed: () => _bridge.openFullScreen(widget.route),
            icon: const Icon(Icons.open_in_new, size: 16),
            label: const Text('Full Screen'),
            style: TextButton.styleFrom(
              foregroundColor: AppTheme.textSecondary,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingOverlay() {
    return Container(
      color: AppTheme.backgroundDarkOps,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(color: AppTheme.primaryBlue),
            const SizedBox(height: 16),
            Text(
              'Loading Analytics...',
              style: TextStyle(color: AppTheme.textSecondary),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorOverlay() {
    return Container(
      color: AppTheme.backgroundDarkOps,
      padding: const EdgeInsets.all(24),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: AppTheme.riskHigh),
            const SizedBox(height: 16),
            Text(
              _error!,
              style: TextStyle(color: AppTheme.textSecondary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 16),
            ElevatedButton.icon(
              onPressed: () {
                setState(() => _error = null);
                _reloadIframe();
              },
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }

  String _getRouteLabel(String route) {
    switch (route) {
      case '/war-room':
        return 'War Room';
      case '/detection-studio':
        return 'Detection Studio';
      case '/war-room/compliance':
        return 'Compliance';
      case '/war-room/graphs':
        return 'Graph Explorer';
      default:
        return 'Analytics';
    }
  }

  Widget _buildNonWebFallback() {
    return Container(
      color: AppTheme.backgroundDarkOps,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.web, size: 48, color: AppTheme.textSecondary),
            const SizedBox(height: 16),
            Text(
              'Analytics available on web platform',
              style: TextStyle(color: AppTheme.textSecondary),
            ),
            const SizedBox(height: 8),
            TextButton.icon(
              onPressed: () => _bridge.openFullScreen(widget.route),
              icon: const Icon(Icons.open_in_browser),
              label: const Text('Open in Browser'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    super.dispose();
  }
}
