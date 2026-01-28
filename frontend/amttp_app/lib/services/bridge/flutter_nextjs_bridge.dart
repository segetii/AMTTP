import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

/// Bridge Service for Flutter ↔ Next.js Communication
/// 
/// Enables bidirectional data sync between:
/// - Flutter native views (transfers, auth, wallet)
/// - Next.js analytics (charts, graphs, heatmaps)
/// 
/// Supports:
/// - Embedded WebView mode (inside Flutter)
/// - Full-screen browser mode (standalone Next.js)
/// - Session synchronization
/// - Real-time data updates

class FlutterNextJSBridge {
  static final FlutterNextJSBridge _instance = FlutterNextJSBridge._internal();
  factory FlutterNextJSBridge() => _instance;
  FlutterNextJSBridge._internal();

  WebViewController? _webViewController;
  
  // Configuration
  static const String nextJsBaseUrl = 'http://localhost:3006';
  static const String flutterChannelName = 'FlutterBridge';
  
  // Callbacks for handling messages from Next.js
  Function(Map<String, dynamic>)? onRiskScoreUpdate;
  Function(Map<String, dynamic>)? onAlertReceived;
  Function(String)? onNavigationRequest;
  Function(Map<String, dynamic>)? onComplianceAction;

  // Current session state (shared with Next.js)
  String? _sessionToken;
  String? _userId;
  String? _userRole;
  String? _walletAddress;

  /// Initialize the bridge with a WebViewController
  void initialize(WebViewController controller) {
    _webViewController = controller;
    _setupJavaScriptChannel();
    debugPrint('🌉 FlutterNextJSBridge initialized');
  }

  /// Setup JavaScript channel to receive messages from Next.js
  void _setupJavaScriptChannel() {
    _webViewController?.addJavaScriptChannel(
      flutterChannelName,
      onMessageReceived: (JavaScriptMessage message) {
        _handleMessageFromNextJS(message.message);
      },
    );
  }

  /// Handle incoming messages from Next.js
  void _handleMessageFromNextJS(String messageJson) {
    try {
      final data = jsonDecode(messageJson) as Map<String, dynamic>;
      final type = data['type'] as String?;
      final payload = data['payload'] as Map<String, dynamic>?;

      debugPrint('📩 Received from Next.js: $type');

      switch (type) {
        case 'RISK_SCORE_UPDATE':
          onRiskScoreUpdate?.call(payload ?? {});
          break;
        case 'ALERT_RECEIVED':
          onAlertReceived?.call(payload ?? {});
          break;
        case 'NAVIGATION_REQUEST':
          onNavigationRequest?.call(payload?['route'] ?? '');
          break;
        case 'COMPLIANCE_ACTION':
          onComplianceAction?.call(payload ?? {});
          break;
        case 'REQUEST_SESSION':
          // Next.js is asking for current session
          sendUserContext();
          break;
        case 'OPEN_FULL_SCREEN':
          openFullScreen(payload?['route'] ?? '/war-room');
          break;
        case 'READY':
          debugPrint('✅ Next.js WebView is ready');
          sendUserContext();
          break;
        default:
          debugPrint('⚠️ Unknown message type: $type');
      }
    } catch (e) {
      debugPrint('❌ Error parsing message from Next.js: $e');
    }
  }

  /// Set session data (call after login)
  void setSession({
    required String sessionToken,
    required String userId,
    required String userRole,
    String? walletAddress,
  }) {
    _sessionToken = sessionToken;
    _userId = userId;
    _userRole = userRole;
    _walletAddress = walletAddress;
    
    // Sync with Next.js if WebView is active
    sendUserContext();
    
    debugPrint('🔐 Session set: $_userId ($_userRole)');
  }

  /// Clear session (call on logout)
  void clearSession() {
    _sessionToken = null;
    _userId = null;
    _userRole = null;
    _walletAddress = null;
    
    _sendToNextJS('SESSION_CLEARED', {});
    debugPrint('🔓 Session cleared');
  }

  /// Send current user context to Next.js
  void sendUserContext() {
    if (_sessionToken == null) return;
    
    _sendToNextJS('FLUTTER_USER_CONTEXT', {
      'sessionToken': _sessionToken,
      'userId': _userId,
      'userRole': _userRole,
      'walletAddress': _walletAddress,
      'timestamp': DateTime.now().toIso8601String(),
    });
  }

  /// Request Next.js to analyze a specific transaction
  void analyzeTransaction(String txHash) {
    _sendToNextJS('ANALYZE_TRANSACTION', {
      'txHash': txHash,
      'timestamp': DateTime.now().toIso8601String(),
    });
  }

  /// Request Next.js to show a specific wallet's graph
  void showWalletGraph(String walletAddress) {
    _sendToNextJS('SHOW_WALLET_GRAPH', {
      'walletAddress': walletAddress,
    });
  }

  /// Request Next.js to navigate to a specific route
  void navigateTo(String route) {
    _sendToNextJS('NAVIGATE_TO', {
      'route': route,
    });
  }

  /// Request risk check for a counterparty
  void requestRiskCheck(String counterpartyAddress, double amount) {
    _sendToNextJS('REQUEST_RISK_CHECK', {
      'counterpartyAddress': counterpartyAddress,
      'amount': amount,
    });
  }

  /// Notify Next.js of a new transaction
  void notifyNewTransaction({
    required String txHash,
    required String from,
    required String to,
    required double amount,
    required String currency,
  }) {
    _sendToNextJS('NEW_TRANSACTION', {
      'txHash': txHash,
      'from': from,
      'to': to,
      'amount': amount,
      'currency': currency,
      'timestamp': DateTime.now().toIso8601String(),
    });
  }

  /// Send a message to Next.js via JavaScript
  void _sendToNextJS(String type, Map<String, dynamic> payload) {
    if (_webViewController == null) {
      debugPrint('⚠️ WebViewController not initialized');
      return;
    }

    final message = jsonEncode({
      'type': type,
      'payload': payload,
      'source': 'flutter',
    });

    final jsCode = '''
      window.postMessage($message, '*');
    ''';

    _webViewController!.runJavaScript(jsCode);
    debugPrint('📤 Sent to Next.js: $type');
  }

  /// Open Next.js in full-screen browser mode
  Future<void> openFullScreen([String route = '/war-room']) async {
    // Build URL with session token for seamless auth
    final uri = Uri.parse(nextJsBaseUrl).replace(
      path: route,
      queryParameters: {
        'token': _sessionToken ?? '',
        'source': 'flutter',
        'userId': _userId ?? '',
        'role': _userRole ?? '',
      },
    );

    debugPrint('🖥️ Opening full screen: $uri');

    if (await canLaunchUrl(uri)) {
      await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );
    } else {
      debugPrint('❌ Could not launch URL: $uri');
    }
  }

  /// Get the URL for embedding Next.js in a WebView
  String getEmbeddedUrl(String route) {
    final uri = Uri.parse(nextJsBaseUrl).replace(
      path: route,
      queryParameters: {
        'embedded': 'true',
        'token': _sessionToken ?? '',
        'source': 'flutter',
      },
    );
    return uri.toString();
  }

  /// Check if session is active
  bool get hasSession => _sessionToken != null;

  /// Get current user role
  String? get userRole => _userRole;

  /// Dispose resources
  void dispose() {
    _webViewController = null;
    debugPrint('🌉 FlutterNextJSBridge disposed');
  }
}
