// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_theme.dart';

/// FATF Rules Page - Full-screen embed of Next.js FATF compliance dashboard
/// 
/// This is a SIMPLE page that shows ONLY the Next.js iframe.
/// All navigation happens INSIDE the iframe (Next.js handles it).
class FATFRulesPage extends ConsumerStatefulWidget {
  const FATFRulesPage({super.key});

  @override
  ConsumerState<FATFRulesPage> createState() => _FATFRulesPageState();
}

class _FATFRulesPageState extends ConsumerState<FATFRulesPage> {
  late String _nextJsUrl;
  late String _viewType;
  bool _registered = false;

  @override
  void initState() {
    super.initState();
    _nextJsUrl = _buildNextJsUrl();
    _viewType = 'fatf-frame-${DateTime.now().millisecondsSinceEpoch}';
    _registerIframe();
  }

  String _buildNextJsUrl() {
    if (!kIsWeb) return 'http://localhost:3006/compliance/fatf-rules';
    
    final loc = html.window.location;
    final host = loc.hostname ?? 'localhost';
    final proto = loc.protocol.isEmpty ? 'http:' : loc.protocol;
    
    // In production (non-localhost), use same origin via nginx proxy
    if (host != 'localhost' && host != '127.0.0.1') {
      final port = loc.port;
      if (port.isNotEmpty && port != '80' && port != '443') {
        return '$proto//$host:$port/compliance/fatf-rules';
      }
      return '$proto//$host/compliance/fatf-rules';
    }
    return '$proto//$host:3006/compliance/fatf-rules';
  }

  void _registerIframe() {
    if (!kIsWeb || _registered) return;
    
    ui.platformViewRegistry.registerViewFactory(
      _viewType,
      (int viewId) => html.IFrameElement()
        ..src = _nextJsUrl
        ..style.border = 'none'
        ..style.width = '100%'
        ..style.height = '100%'
        ..allow = 'clipboard-read; clipboard-write; fullscreen',
    );
    _registered = true;
  }

  void _openInNewTab() {
    if (kIsWeb) html.window.open(_nextJsUrl, '_blank');
  }

  void _refresh() {
    setState(() {
      _registered = false;
      _viewType = 'fatf-frame-${DateTime.now().millisecondsSinceEpoch}';
      _registerIframe();
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!kIsWeb) {
      return Scaffold(
        backgroundColor: AppTheme.darkBg,
        appBar: AppBar(title: const Text('FATF Rules'), backgroundColor: AppTheme.darkCard),
        body: Center(
          child: Text('FATF dashboard requires web.\n\nURL: $_nextJsUrl',
            textAlign: TextAlign.center, style: TextStyle(color: AppTheme.cleanWhite)),
        ),
      );
    }

    return Scaffold(
      backgroundColor: AppTheme.darkBg,
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go('/compliance'),
        ),
        title: Row(
          children: [
            const Icon(Icons.public, size: 20),
            const SizedBox(width: 8),
            const Text('FATF Rules'),
            const SizedBox(width: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.2),
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text('Next.js', style: TextStyle(fontSize: 10, color: Colors.green)),
            ),
          ],
        ),
        backgroundColor: AppTheme.darkCard,
        foregroundColor: AppTheme.cleanWhite,
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refresh, tooltip: 'Refresh'),
          IconButton(icon: const Icon(Icons.open_in_new), onPressed: _openInNewTab, tooltip: 'New tab'),
          const SizedBox(width: 8),
        ],
      ),
      body: HtmlElementView(viewType: _viewType),
    );
  }
}
