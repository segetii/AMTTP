// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';

/// ML Models Page - Embeds the Next.js ML Models management dashboard
/// 
/// RBAC: R6 SUPER ADMIN ONLY
/// Features:
/// - View all ML model status (active, training, paused, error)
/// - Pause/Resume models
/// - Trigger model retraining
/// - View model performance metrics (accuracy, precision, recall, F1)
/// - Monitor predictions and latency
/// 
/// FULL SCREEN MODE:
/// - Shell will hide Flutter chrome when this page is displayed
/// - Only back button overlay will be visible
/// - Content fills the entire screen
class MLModelsPage extends ConsumerStatefulWidget {
  const MLModelsPage({super.key});

  @override
  ConsumerState<MLModelsPage> createState() => _MLModelsPageState();
}

class _MLModelsPageState extends ConsumerState<MLModelsPage> {
  late String _nextJsUrl;
  late String _viewType;
  bool _registered = false;

  static const String _overrideUrl = String.fromEnvironment('ML_MODELS_URL');

  @override
  void initState() {
    super.initState();
    _viewType = 'ml-models-iframe-${DateTime.now().millisecondsSinceEpoch}';
    _initUrl();
  }

  void _initUrl() {
    final rbacState = ref.read(rbacProvider);
    final role = rbacState.role.code;
    
    String baseUrl;
    if (_overrideUrl.isNotEmpty) {
      baseUrl = _overrideUrl;
    } else {
      final location = html.window.location;
      final host = location.hostname ?? 'localhost';
      final protocol = location.protocol;
      final port = location.port;
      
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
    
    // Build URL with embed mode and role parameters
    _nextJsUrl = '$baseUrl/war-room/detection/models?embed=true&role=$role';
    
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
      return _buildNonWebFallback(context);
    }

    return Container(
      color: AppTheme.darkBg,
      child: HtmlElementView(viewType: _viewType),
    );
  }

  Widget _buildNonWebFallback(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.psychology_rounded,
              size: 64,
              color: AppTheme.mutedText,
            ),
            const SizedBox(height: 16),
            Text(
              'ML Models Dashboard',
              style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18),
            ),
            const SizedBox(height: 8),
            Text(
              'Available on web platform only',
              style: TextStyle(color: AppTheme.mutedText),
            ),
          ],
        ),
      ),
    );
  }
}
