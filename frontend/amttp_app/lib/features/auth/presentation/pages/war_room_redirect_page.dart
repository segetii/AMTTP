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
      // Now that cross-app auth bridge cookie is set, no need for ?embed=true
      html.window.location.replace('/war-room');
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
