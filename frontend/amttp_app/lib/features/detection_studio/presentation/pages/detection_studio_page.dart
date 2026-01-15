// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';

/// Detection Studio Page - Embeds the Next.js dashboard inside Flutter
/// This allows Admin and Compliance users to access the full Next.js UI
/// within the Flutter app for advanced risk analysis and detection features.
class DetectionStudioPage extends StatefulWidget {
  const DetectionStudioPage({super.key});

  @override
  State<DetectionStudioPage> createState() => _DetectionStudioPageState();
}

class _DetectionStudioPageState extends State<DetectionStudioPage> {
  // Resolved URL pointing to Next.js SIEM dashboard
  static String _nextJsUrl = '';
  static const _viewType = 'detection-studio-iframe';
  static bool _registered = false;

  // Optional override (use --dart-define=DETECTION_STUDIO_URL=https://your.host/siem/)
  static const String _overrideUrl = String.fromEnvironment('DETECTION_STUDIO_URL');

  @override
  void initState() {
    super.initState();
    _initUrl();
    _registerIframe();
  }

  void _initUrl() {
    // Compute URL once per app lifetime (static)
    if (_nextJsUrl.isNotEmpty) return;

    if (_overrideUrl.isNotEmpty) {
      _nextJsUrl = _overrideUrl;
      return;
    }

    // Detect host/port to decide where nginx lives
    final location = html.window.location;
    final host = location.host; // may include port
    final protocol = location.protocol; // includes trailing ':'

    if (host.contains(':3003')) {
      // Flutter dev on :3003 -> nginx on same host default port
      _nextJsUrl = '${protocol}//${location.hostname}/siem/';
    } else {
      // Production: same origin (Flutter served via nginx)
      _nextJsUrl = '/siem/';
    }
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
        appBar: AppBar(
          title: const Text('Detection Studio'),
          backgroundColor: AppTheme.darkCard,
          foregroundColor: AppTheme.cleanWhite,
        ),
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

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        title: Row(
          children: [
            Icon(Icons.visibility, color: AppTheme.primaryBlue),
            const SizedBox(width: 8),
            const Text('Detection Studio'),
          ],
        ),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        actions: [
          IconButton(
            icon: const Icon(Icons.open_in_new),
            onPressed: () => html.window.open(_nextJsUrl, '_blank'),
            tooltip: 'Open in new tab',
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: () => setState(() {}),
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: const HtmlElementView(viewType: _viewType),
    );
  }
}
