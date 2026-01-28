/// Graph Explorer Page - War Room Visualization
/// 
/// Per Ground Truth v2.3:
/// - Embeds Next.js network graph (WebGL powered)
/// - Full-screen mode via shell
/// - Role-aware integration

// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';
import '../../../../shared/shells/role_based_shell.dart';

class GraphExplorerPage extends ConsumerStatefulWidget {
  final String? initialTxId;
  
  const GraphExplorerPage({super.key, this.initialTxId});

  @override
  ConsumerState<GraphExplorerPage> createState() => _GraphExplorerPageState();
}

class _GraphExplorerPageState extends ConsumerState<GraphExplorerPage> {
  late String _nextJsUrl;
  late String _viewType;
  bool _registered = false;

  @override
  void initState() {
    super.initState();
    _viewType = 'graph-explorer-iframe-${DateTime.now().millisecondsSinceEpoch}';
    _initUrl();
  }

  void _initUrl() {
    final rbacState = ref.read(rbacProvider);
    final role = rbacState.role.code;
    
    // Detect host/port for Next.js
    final location = html.window.location;
    final host = location.hostname ?? 'localhost';
    final protocol = location.protocol;
    const nextJsPort = '3006';
    
    final baseUrl = '$protocol//$host:$nextJsPort';
    
    // Point to the detection studio network view
    _nextJsUrl = '$baseUrl/war-room/detection-studio?embed=true&role=$role&view=network';
    
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
        ..allow = 'clipboard-read; clipboard-write; fullscreen',
    );
    _registered = true;
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) {
      return Scaffold(
        backgroundColor: AppTheme.darkBg,
        body: Center(
          child: Text(
            'Graph Explorer is only available on web.',
            style: TextStyle(color: AppTheme.cleanWhite),
          ),
        ),
      );
    }
    return HtmlElementView(viewType: _viewType);
  }
}
