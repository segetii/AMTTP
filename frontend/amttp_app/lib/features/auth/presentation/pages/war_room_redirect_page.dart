import 'package:flutter/material.dart';
import 'dart:html' as html;

/// A trampoline page that performs a full browser redirect to the
/// standalone Next.js War Room. GoRouter navigates here for R3+ users,
/// and initState immediately triggers a full page navigation that
/// replaces the Flutter SPA with the Next.js app.
class WarRoomRedirectPage extends StatefulWidget {
  const WarRoomRedirectPage({super.key});

  @override
  State<WarRoomRedirectPage> createState() => _WarRoomRedirectPageState();
}

class _WarRoomRedirectPageState extends State<WarRoomRedirectPage> {
  @override
  void initState() {
    super.initState();
    // Use addPostFrameCallback to ensure the widget tree is fully built
    // and GoRouter has finished its navigation before we trigger the
    // browser-level redirect. This avoids conflicts with GoRouter's
    // history API manipulation.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Determine the correct Next.js War Room URL based on environment:
      // - Dev mode (Flutter on port 3010): redirect to localhost:3006/war-room
      // - Production/Docker (nginx): use relative /war-room path
      final currentPort = html.window.location.port;
      final String warRoomUrl;
      if (currentPort == '3010') {
        // Local dev: Next.js runs on port 3006
        warRoomUrl = 'http://localhost:3006/war-room';
      } else {
        // Production/Docker: nginx proxies /war-room to Next.js
        warRoomUrl = '/war-room';
      }
      html.window.location.replace(warRoomUrl);
    });
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0A0A0F),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              color: Color(0xFF00D4AA),
              strokeWidth: 3,
            ),
            SizedBox(height: 24),
            Text(
              'Loading War Room...',
              style: TextStyle(
                color: Colors.white70,
                fontSize: 16,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
