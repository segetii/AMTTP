// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';

/// Detection Studio Page - Embeds the Next.js SIEM dashboard inside Flutter
/// This allows Admin and Compliance users to access the full Next.js UI
/// within the Flutter app for advanced risk analysis and detection features.
/// 
/// Role Integration:
/// - Passes Flutter RBAC role to Next.js via query params
/// - Next.js uses embed mode to hide redundant chrome
/// - Syncs session between Flutter and Next.js
///
/// FULL SCREEN MODE:
/// - Shell will hide Flutter chrome when this page is displayed
/// - Only back button overlay will be visible
/// - Content fills the entire screen
class DetectionStudioPage extends ConsumerStatefulWidget {
  final String? initialView; // 'velocity', 'network', 'flow', 'distribution'
  
  const DetectionStudioPage({super.key, this.initialView});

  @override
  ConsumerState<DetectionStudioPage> createState() => _DetectionStudioPageState();
}

class _DetectionStudioPageState extends ConsumerState<DetectionStudioPage> {
  // Resolved URL pointing to Next.js SIEM dashboard
  late String _nextJsUrl;
  late String _viewType;
  bool _registered = false;

  // Optional override (use --dart-define=DETECTION_STUDIO_URL=https://your.host/)
  static const String _overrideUrl = String.fromEnvironment('DETECTION_STUDIO_URL');

  @override
  void initState() {
    super.initState();
    // Generate unique view type to allow re-registration with different URLs
    _viewType = 'detection-studio-iframe-${DateTime.now().millisecondsSinceEpoch}';
    _initUrl();
  }

  void _initUrl() {
    final rbacState = ref.read(rbacProvider);
    final role = rbacState.role.code;
    final view = widget.initialView ?? 'overview';
    
    String baseUrl;
    if (_overrideUrl.isNotEmpty) {
      baseUrl = _overrideUrl;
    } else {
      // Detect host/port to decide where Next.js lives
      final location = html.window.location;
      final host = location.hostname ?? 'localhost';
      final protocol = location.protocol;
      final port = location.port;

      // In production (non-localhost), Next.js is served via nginx on same origin
      // In dev (localhost), use port 3006
      if (host == 'localhost' || host == '127.0.0.1') {
        const nextJsPort = '3006';
        if (location.port == nextJsPort) {
          baseUrl = '$protocol//$host:${location.port}';
        } else {
          baseUrl = '$protocol//$host:$nextJsPort';
        }
      } else {
        baseUrl = '$protocol//$host';
        if (port.isNotEmpty && port != '80' && port != '443') {
          baseUrl = '$protocol//$host:$port';
        }
      }
    }
    
    // Build URL with embed mode, role, and view parameters
    _nextJsUrl = '$baseUrl/war-room/detection-studio?embed=true&role=$role&view=$view';
    
    _registerIframe();
  }

  void _registerIframe() {
    if (!kIsWeb || _registered) return;

    final url = _nextJsUrl;
    ui.platformViewRegistry.registerViewFactory(
      _viewType,
      (int viewId) => html.IFrameElement()
        ..src = url
        ..style.border = '0'
        ..style.width = '100%'
        ..style.height = '100%'
        ..allow = 'clipboard-read; clipboard-write',
    );
    _registered = true;
  }

  @override
  Widget build(BuildContext context) {
    
    if (!kIsWeb) {
      // Fallback for non-web platforms
      return Scaffold(
        backgroundColor: AppTheme.darkBg,
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(Icons.computer, size: 64, color: AppTheme.mutedText),
                const SizedBox(height: 16),
                Text(
                  'Detection Studio is only available on web.',
                  style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Please access via: $_nextJsUrl',
                  style: TextStyle(color: AppTheme.mutedText),
                ),
              ],
            ),
          ),
        ),
      );
    }
    return HtmlElementView(viewType: _viewType);
  }
}
