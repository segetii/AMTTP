/// War Room Next.js Page - Embeds Full Next.js War Room Dashboard
/// 
/// For R4+ users (Compliance, Platform Admin, Super Admin)
/// Opens the complete Next.js SIEM dashboard in an iframe
/// 
/// FULL SCREEN MODE:
/// - Shell provides back button overlay
/// - Content fills the entire screen
/// - No Flutter chrome, pure Next.js experience
library;

// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:ui_web' as ui;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/rbac/rbac_provider.dart';

class WarRoomNextJSPage extends ConsumerStatefulWidget {
  /// Optional deep link path inside Next.js (e.g., '/war-room/alerts')
  final String? nextPath;

  const WarRoomNextJSPage({super.key, this.nextPath});

  @override
  ConsumerState<WarRoomNextJSPage> createState() => _WarRoomNextJSPageState();
}

class _WarRoomNextJSPageState extends ConsumerState<WarRoomNextJSPage> {
  late String _nextJsUrl;
  late String _viewType;
  bool _registered = false;

  @override
  void initState() {
    super.initState();
    _viewType = 'war-room-nextjs-iframe-${DateTime.now().millisecondsSinceEpoch}';
    _initUrl();
  }

  void _initUrl() {
    final rbacState = ref.read(rbacProvider);
    final role = rbacState.role.code;
    
    // Detect host/port for Next.js
    final location = html.window.location;
    final host = location.hostname ?? 'localhost';
    final protocol = location.protocol;
    final port = location.port;
    
    // In production (no port or port 80/443), use relative URL via nginx proxy
    // In dev (port 3010/3003), use Next.js on port 3006
    String baseUrl;
    if (host == 'localhost' || host == '127.0.0.1') {
      const nextJsPort = '3006';
      baseUrl = '$protocol//$host:$nextJsPort';
    } else {
      baseUrl = '$protocol//$host';
      if (port.isNotEmpty && port != '80' && port != '443') {
        baseUrl = '$protocol//$host:$port';
      }
    }
    final path = (widget.nextPath?.startsWith('/') ?? false)
        ? widget.nextPath!
        : '/war-room';

    // Full War Room dashboard (or deep link) with role context and embed mode
    final uri = Uri.parse(baseUrl).replace(
      path: path,
      queryParameters: {
        'embed': 'true',
        'role': role,
      },
    );

    _nextJsUrl = uri.toString();
    
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
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.computer, size: 64, color: AppTheme.mutedText),
              const SizedBox(height: 16),
              Text(
                'War Room is only available on web.',
                style: TextStyle(color: AppTheme.cleanWhite, fontSize: 18),
              ),
            ],
          ),
        ),
      );
    }
    return HtmlElementView(viewType: _viewType);
  }
}
